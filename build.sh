#!/usr/bin/env bash
set -e

echo "📦 Install deps..."
pip install -r requirements.txt

apt update -y
apt install -y curl tar

echo "🧹 Clean old files..."
rm -rf sf.tar stockfish stockfish_dir

echo "⬇ Download Stockfish 16.1 AVX2..."
curl -L https://github.com/official-stockfish/Stockfish/releases/download/sf_16.1/stockfish-ubuntu-x86-64-avx2.tar -o sf.tar

echo "📂 Extract..."
tar -xf sf.tar

echo "🔁 Rename folder..."
mv stockfish stockfish_dir

echo "🔧 Move binary..."
mv stockfish_dir/stockfish-ubuntu-x86-64-avx2 ./engine

chmod +x engine

echo "✅ Test engine:"
./engine bench
