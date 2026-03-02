#!/usr/bin/env bash

pip install -r requirements.txt

curl -L https://github.com/official-stockfish/Stockfish/releases/latest/download/stockfish-ubuntu-x86-64.tar -o sf.tar
tar -xf sf.tar
chmod +x stockfish-ubuntu-x86-64
mv stockfish-ubuntu-x86-64 stockfish
