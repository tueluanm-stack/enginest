#!/usr/bin/env bash

pip install -r requirements.txt

curl -L https://stockfishchess.org/files/stockfish_16.1_linux_x64_avx2.zip -o sf.zip

unzip sf.zip

chmod +x stockfish_16.1_linux_x64_avx2/stockfish

mv stockfish_16.1_linux_x64_avx2/stockfish stockfish
