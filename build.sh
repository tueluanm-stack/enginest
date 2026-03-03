#!/usr/bin/env bash
set -e

echo "📦 Install Python deps..."
pip install -r requirements.txt

echo "📦 Install tools..."
apt update -y
apt install -y curl tar

echo "⬇ Download Stockfish 16.1 AVX2..."
curl -L https://github.com/official-stockfish/Stockfish/releases/download/sf_16.1/stockfish-ubuntu-x86-64-avx2.tar -o sf.tar

echo "📂 Extract..."
tar -xf sf.tar

echo "🔧 Set permission..."
chmod +x stockfish/stockfish-ubuntu-x86-64-avx2

echo "📦 Move binary to root..."
mv stockfish/stockfish-ubuntu-x86-64-avx2 ./stockfish_bin

echo "🔁 Rename..."
mv stockfish_bin stockfish

echo "✅ Test:"
./stockfish bench
