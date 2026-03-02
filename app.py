#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template_string
import subprocess, threading, queue, time, os, sys, atexit, signal, random

app = Flask(__name__)

DEFAULT_STOCKFISH = os.environ.get("STOCKFISH_PATH", "./stockfish")
DEFAULT_THREADS = int(os.environ.get("THREADS", "2"))
DEFAULT_HASH = int(os.environ.get("HASH", "128"))
DEFAULT_MOVETIME = int(os.environ.get("MOVETIME", "300"))

def find_stockfish():
    candidates = [
        os.environ.get("STOCKFISH_PATH"),
        "./stockfish",
        "/opt/render/project/src/stockfish",
        "/usr/games/stockfish",
        "/usr/bin/stockfish",
        "/usr/local/bin/stockfish",
        "stockfish"
    ]
    for p in candidates:
        if not p:
            continue
        try:
            subprocess.run([p, "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1)
            return p
        except Exception:
            continue
    return None

SF_BIN = find_stockfish() or DEFAULT_STOCKFISH

class PersistentEngine:
    def __init__(self, path, threads=DEFAULT_THREADS, hash_mb=DEFAULT_HASH):
        self.path = path
        self.threads = threads
        self.hash_mb = hash_mb
        self.proc = None
        self._stdout_q = queue.Queue()
        self._reader_thread = None
        self._lock = threading.Lock()
        self._start_proc()

    def _start_proc(self):
        try:
            self.proc = subprocess.Popen([self.path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        except Exception as e:
            print("Failed to start engine:", e, file=sys.stderr)
            self.proc = None
            return
        self._stdout_q = queue.Queue()
        self._reader_thread = threading.Thread(target=self._stdout_reader, daemon=True)
        self._reader_thread.start()
        time.sleep(0.05)
        try:
            self._write("uci")
            self._write(f"setoption name Threads value {self.threads}")
            self._write(f"setoption name Hash value {self.hash_mb}")
            self._write("isready")
            self._drain_startup()
        except Exception:
            pass

    def _stdout_reader(self):
        if not self.proc or not self.proc.stdout:
            return
        try:
            for raw in self.proc.stdout:
                if raw is None:
                    break
                line = raw.rstrip("\n")
                try:
                    self._stdout_q.put_nowait(line)
                except queue.Full:
                    try:
                        _ = self._stdout_q.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        self._stdout_q.put_nowait(line)
                    except Exception:
                        pass
        except Exception:
            pass

    def _write(self, cmd):
        if not self.proc or self.proc.stdin.closed:
            raise RuntimeError("Engine not running")
        try:
            self.proc.stdin.write(cmd + "\n")
            self.proc.stdin.flush()
        except Exception as e:
            raise RuntimeError("Engine write failed: " + str(e))

    def _readline(self, timeout=1.0):
        try:
            return self._stdout_q.get(timeout=timeout)
        except queue.Empty:
            return None

    def _drain_startup(self, timeout_total=2.0):
        start = time.time()
        while time.time() - start < timeout_total:
            ln = self._readline(timeout=0.1)
            if ln is None:
                continue
            if ln.strip() == "readyok":
                break

    def restart(self):
        try:
            if self.proc:
                try:
                    self._write("quit")
                except Exception:
                    pass
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.05)
        self.proc = None
        self._start_proc()

    def is_alive(self):
        return bool(self.proc and self.proc.poll() is None)

    def set_options(self, threads=None, hash_mb=None):
        with self._lock:
            if threads is not None:
                self.threads = int(threads)
                try:
                    self._write(f"setoption name Threads value {self.threads}")
                except Exception:
                    pass
            if hash_mb is not None:
                self.hash_mb = int(hash_mb)
                try:
                    self._write(f"setoption name Hash value {self.hash_mb}")
                except Exception:
                    pass
            try:
                self._write("isready")
                self._drain_startup(timeout_total=1.0)
            except Exception:
                pass

    def get_move(self, fen, movetime_ms=None, multipv=1):
        if movetime_ms is None:
            movetime_ms = DEFAULT_MOVETIME
        if not self.is_alive():
            self.restart()
            if not self.is_alive():
                return {"error": "engine not available", "best_move": None}
        with self._lock:
            try:
                self._write(f"position fen {fen}")
                self._write(f"go movetime {int(movetime_ms)} multipv {int(multipv)}")
            except Exception as e:
                return {"error": f"write failed: {e}", "best_move": None}
            best_move = None
            candidates = []
            start = time.time()
            timeout_total = (movetime_ms / 1000.0) + 3.0
            while True:
                elapsed = time.time() - start
                if elapsed > timeout_total:
                    break
                ln = self._readline(timeout=0.5)
                if ln is None:
                    continue
                ln_str = ln.strip()
                if ln_str.startswith("info") and " pv " in ln_str:
                    try:
                        pv = ln_str.split(" pv ", 1)[1].split()
                        if pv:
                            candidates.append(pv[0])
                    except Exception:
                        pass
                if ln_str.startswith("bestmove"):
                    parts = ln_str.split()
                    if len(parts) >= 2:
                        best_move = parts[1]
                    break
            if not best_move:
                if candidates:
                    best_move = candidates[0]
                else:
                    best_move = None
            return {"error": None, "best_move": best_move}

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
                except Exception:
                    pass
                self.proc = None
        except Exception:
            pass

engine = PersistentEngine(SF_BIN, threads=DEFAULT_THREADS, hash_mb=DEFAULT_HASH)

def _cleanup():
    try:
        engine.shutdown()
    except Exception:
        pass

atexit.register(_cleanup)
signal.signal(signal.SIGINT, lambda s,f: (_cleanup(), sys.exit(0)))
signal.signal(signal.SIGTERM, lambda s,f: (_cleanup(), sys.exit(0)))

FRONT_HTML = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Stockfish Server</title>
<link rel="stylesheet" href="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.css">
<script src="https://code.jquery.com/jquery-3.5.1.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/chess.js/0.10.3/chess.min.js"></script>
<script src="https://unpkg.com/@chrisoakman/chessboardjs@1.0.0/dist/chessboard-1.0.0.min.js"></script>
<style>body{font-family:Arial;background:#223;color:#fff;text-align:center}#board{width:420px;margin:10px auto}</style>
</head>
<body>
<h2>Stockfish Server</h2>
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

@app.route("/", methods=["GET"])
def index():
    return render_template_string(FRONT_HTML)

@app.route("/health", methods=["GET"])
def health():
    alive = engine.is_alive()
    return jsonify(status="ok", engine_alive=alive, stockfish_path=SF_BIN, threads=engine.threads, hash=engine.hash_mb)

@app.route("/set_options", methods=["POST"])
def set_options():
    data = request.get_json(force=True) or {}
    t = data.get("threads")
    h = data.get("hash")
    try:
        engine.set_options(threads=t, hash_mb=h)
        return jsonify(status="ok", threads=engine.threads, hash=engine.hash_mb)
    except Exception as e:
        return jsonify(status="error", error=str(e)), 500

@app.route("/move", methods=["POST"])
def move_route():
    data = request.get_json(force=True) or {}
    fen = data.get("fen")
    movetime = data.get("movetime", DEFAULT_MOVETIME)
    if not fen:
        return jsonify(error="missing fen"), 400
    try:
        movetime = int(movetime)
    except Exception:
        movetime = DEFAULT_MOVETIME
    res = engine.get_move(fen, movetime_ms=movetime, multipv=1)
    if res.get("error"):
        return jsonify(status="error", error=res["error"]), 500
    return jsonify(status="ok", best_move=res["best_move"])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, threaded=True)
