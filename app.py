# app.py
# Flask web + persistent Stockfish engine wrapper + simple chess front-end
from flask import Flask, request, jsonify, render_template_string
import subprocess, threading, time, os, random, atexit, signal, sys

app = Flask(__name__)

# Configuration via env
STOCKFISH_PATH = os.environ.get("STOCKFISH_PATH", "./stockfish")  # build.sh sẽ copy binary ra root
THREADS = int(os.environ.get("THREADS", "2"))
HASH = int(os.environ.get("HASH", "128"))   # MB
DEFAULT_MOVETIME = int(os.environ.get("MOVETIME", "300"))  # ms

# --- find binary sanity check ---
def find_stockfish():
    candidates = [STOCKFISH_PATH, "/usr/games/stockfish", "/usr/bin/stockfish", "stockfish"]
    for p in candidates:
        if not p:
            continue
        try:
            subprocess.run([p, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            return p
        except Exception:
            continue
    return None

SF_BIN = find_stockfish()
if not SF_BIN:
    # in production you should build or install; here we fail early with clear message
    print("ERROR: stockfish binary not found. Expected at ./stockfish or system path.", file=sys.stderr)
    # don't exit here to allow Render build logs to show; but subsequent requests will error
    SF_BIN = None

# --- Persistent Engine Class (thread-safe, restarts on crash) ---
class PersistentEngine:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.proc = None
        if path:
            self._start()

    def _start(self):
        try:
            self.proc = subprocess.Popen(
                [self.path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            # init uci and apply default options
            time.sleep(0.05)
            self._write("uci")
            # set sensible defaults
            self._write(f"setoption name Threads value {THREADS}")
            self._write(f"setoption name Hash value {HASH}")
            # wait a small time and drain initial output
            time.sleep(0.05)
            for _ in range(10):
                _ = self._readline(timeout=0.01)
        except Exception as e:
            print("Engine start failed:", e, file=sys.stderr)
            self.proc = None

    def _write(self, cmd):
        if not self.proc or self.proc.stdin.closed:
            raise RuntimeError("Engine not running")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _readline(self, timeout=1.0):
        if not self.proc:
            return None
        # blocking readline with small timeouts loop
        end = time.time() + timeout
        while time.time() < end:
            try:
                ln = self.proc.stdout.readline()
            except Exception:
                return None
            if ln:
                return ln.rstrip("\n")
            time.sleep(0.01)
        return None

    def get_move(self, fen, movetime_ms=None, multipv=1):
        if movetime_ms is None:
            movetime_ms = DEFAULT_MOVETIME
        if not self.proc:
            # try restart
            self._start()
            if not self.proc:
                return "e2e4"
        with self.lock:
            try:
                self._write(f"position fen {fen}")
                # use movetime (ms). multipv for multiple pv if desired.
                self._write(f"go movetime {int(movetime_ms)} multipv {multipv}")
                cands = []
                best = None
                start = time.time()
                timeout = (movetime_ms / 1000.0) + 2.0
                while True:
                    line = self._readline(timeout=0.5)
                    if line is None:
                        if time.time() - start > timeout:
                            # restart engine if stuck
                            try:
                                self.proc.kill()
                            except Exception:
                                pass
                            self._start()
                            return "e2e4"
                        continue
                    line = line.strip()
                    if line.startswith("info") and " pv " in line:
                        # collect pv move
                        try:
                            pv = line.split(" pv ", 1)[1].split()
                            if pv:
                                cands.append(pv[0])
                        except Exception:
                            pass
                    if line.startswith("bestmove"):
                        parts = line.split()
                        if len(parts) >= 2:
                            best = parts[1]
                        break
                if not best:
                    if cands:
                        best = cands[0]
                    else:
                        best = "e2e4"
                # optional randomness among top-2 (can be disabled)
                if len(cands) >= 2 and random.random() < 0.0:
                    return random.choice(cands[:2])
                return best
            except Exception as e:
                print("Engine error:", e, file=sys.stderr)
                try:
                    if self.proc:
                        self.proc.kill()
                except Exception:
                    pass
                self._start()
                return "e2e4"

    def shutdown(self):
        try:
            if self.proc:
                try:
                    self._write("quit")
                except Exception:
                    pass
                time.sleep(0.05)
                try:
                    self.proc.terminate()
                    self.proc.wait(timeout=1)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
        except Exception:
            pass

# instantiate (may be None if binary missing)
engine = PersistentEngine(SF_BIN)

def _cleanup():
    try:
        engine.shutdown()
    except Exception:
        pass

atexit.register(_cleanup)
signal.signal(signal.SIGINT, lambda s,f: (_cleanup(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (_cleanup(), sys.exit(0)))

# ----------------- Frontend HTML (uses chessboardjs + chess.js) -----------------
HTML = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Stockfish on Render</title>
  <script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
  <script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
  <style>body{font-family:Arial;background:#223; color:#fff; text-align:center} #board{width:420px;margin:10px auto}</style>
</head>
<body>
<h2>Stockfish on Render</h2>
<div id="board"></div>
<div style="margin-top:10px">
<button id="playWhite">Play White</button>
<button id="playBlack">Play Black</button>
<button id="reset">Reset</button>
</div>
<script>
var board, game = new Chess();
function aiMove(){
  if(game.game_over()) return;
  $.ajax({
    url: "/move",
    method: "POST",
    contentType: "application/json",
    data: JSON.stringify({fen: game.fen(), movetime: 300}),
    success: function(d){
      if(d.best_move){
        game.move(d.best_move, {sloppy:true});
        board.position(game.fen());
      }
    }
  });
}
function onDrop(s,t){
  var m = game.move({from:s,to:t,promotion:'q'});
  if(!m) return 'snapback';
  board.position(game.fen());
  aiMove();
}
$(function(){
  board = Chessboard('board', { draggable:true, position:'start', onDrop:onDrop });
  $('#playWhite').click(function(){ game.reset(); board.start(); });
  $('#playBlack').click(function(){ game.reset(); board.start(); aiMove(); });
  $('#reset').click(function(){ game.reset(); board.start(); });
});
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/move", methods=["POST"])
def move():
    data = request.get_json(force=True) or {}
    fen = data.get("fen")
    movetime = int(data.get("movetime", DEFAULT_MOVETIME))
    if not fen:
        return jsonify(error="no fen provided"), 400
    best = engine.get_move(fen, movetime_ms=movetime, multipv=1)
    return jsonify(best_move=best)

@app.route("/health")
def health():
    alive = bool(engine.proc and engine.proc.poll() is None)
    return jsonify(status="ok", engine_alive=alive)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run("0.0.0.0", port)
