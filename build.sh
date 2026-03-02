#!/usr/bin/env bash
set -euo pipefail

echo "=== Update apt and install build deps ==="
apt-get update -y
apt-get install -y git build-essential clang lld make pkg-config

WORKDIR=/tmp/stockfish_build
rm -rf "$WORKDIR"
mkdir -p "$WORKDIR"
cd "$WORKDIR"

echo "=== Clone Stockfish ==="
git clone https://github.com/official-stockfish/Stockfish.git
cd Stockfish/src

echo "=== Build Stockfish (x86-64-bmi2) ==="
# primary: faster stable build. If you want PGO, replace make build with profile-build (slower).
make clean || true
# Use bmi2 target (good for modern Intel/APIs); if target VM lacks bmi2, change to x86-64-modern or x86-64
make build ARCH=x86-64-bmi2 COMP=clang -j$(nproc)

echo "=== Copy binary to project root ==="
cp ./stockfish /workspace/stockfish 2>/dev/null || cp ./stockfish /tmp/stockfish || true

# If Render uses a different working dir for build, also copy to repo root (attempt both)
echo "Done build. stockfish binary copied if build succeeded."
