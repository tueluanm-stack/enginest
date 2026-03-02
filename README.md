# enginest
Engine Chess Pro
# Stockfish Web (Render)

Files:
- app.py : Flask server + frontend
- requirements.txt
- build.sh : build Stockfish during Render build
- Procfile
- render.yaml (optional)

Deploy:
1. Push repo to GitHub.
2. On Render: Create -> New Web Service -> Connect repo.
3. Set Environment: Python.
4. Build command: `bash build.sh`
5. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
6. Deploy. Visit URL after build completes.

Env variables (optional):
- THREADS (default 2)
- HASH (MB, default 128)
- MOVETIME (ms default 300)
- STOCKFISH_PATH (if you uploaded binary yourself)
