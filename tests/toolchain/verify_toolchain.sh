#!/bin/bash
set -e

echo "=== VERIFYING TOOLCHAINS ==="

echo "--- Python ---"
python3 --version
pip3 --version
python3 -m venv .test_venv
echo "Python venv creation: OK"
rm -rf .test_venv

echo "--- GCC / G++ / Make ---"
gcc --version | head -n 1
g++ --version | head -n 1
make --version | head -n 1

echo "--- Git ---"
git --version

echo "--- Compiling and executing test programs ---"
make all
make clean

echo "=== ALL TOOLCHAIN CHECKS PASSED SUCCESSFULLY ==="
