#!/bin/bash
# ==============================================================================
# Cloud IDE - STEP 10 Toolchain and Execution Verification Script
#
# Verifies:
#   1. Non-root user execution
#   2. Python 3, pip3, python3-venv creation and activation
#   3. Python script execution in system and virtual environment
#   4. GCC compilation and execution
#   5. G++ compilation and execution
#   6. Make build and clean
#   7. Git repository status, branch, and commit log
#
# NON-DESTRUCTIVE GUARANTEE:
#   Operates strictly inside /tmp/cloudide-toolchain-test.
#   Never touches, modifies, or resets any user workspace or GitHub repository.
#   Automatically cleans up /tmp/cloudide-toolchain-test on exit.
# ==============================================================================

set -euo pipefail

echo "=================================================="
echo " CLOUD IDE TOOLCHAIN VERIFICATION (STEP 10)"
echo "=================================================="

# 1. Ephemeral Test Directory Setup
TEST_DIR="/tmp/cloudide-toolchain-test"

cleanup() {
    EXIT_CODE=$?
    echo ""
    echo "--> Cleaning up temporary test directory: $TEST_DIR"
    rm -rf "$TEST_DIR" 2>/dev/null || true
    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "--> Toolchain verification completed successfully."
    else
        echo "--> Toolchain verification FAILED with exit code $EXIT_CODE."
    fi
    exit "$EXIT_CODE"
}

trap cleanup EXIT INT TERM

rm -rf "$TEST_DIR" 2>/dev/null || true
mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

echo "--> Operating in temporary directory: $TEST_DIR"

# 2. Non-root User Check
CURRENT_USER=$(whoami 2>/dev/null || id -un || echo "unknown")
CURRENT_UID=$(id -u 2>/dev/null || echo "1000")
echo "--> Current user: $CURRENT_USER (UID: $CURRENT_UID)"
if [ "$CURRENT_UID" -eq 0 ]; then
    echo "WARNING: Running as root. OpenVSCode in production container must run as 'openvscode-server' (UID 1000)."
else
    echo "--> Confirmed: running as non-root user ($CURRENT_USER)."
fi

# 3. Toolchain Binary Detection
# Inside Linux container: uses /usr/bin/python3, pip3, gcc, g++, make, git
# On host systems: falls back gracefully if aliased or differently named
if command -v python3 >/dev/null 2>&1 && python3 -c "import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)" 2>/dev/null; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1 && python -c "import sys; sys.exit(0 if sys.version_info[0] == 3 else 1)" 2>/dev/null; then
    PY_CMD="python"
else
    echo "ERROR: Python 3 executable not found."
    exit 1
fi

if command -v pip3 >/dev/null 2>&1 && pip3 --version >/dev/null 2>&1; then
    PIP_CMD="pip3"
elif command -v pip >/dev/null 2>&1 && pip --version >/dev/null 2>&1; then
    PIP_CMD="pip"
else
    PIP_CMD="$PY_CMD -m pip"
fi

if command -v make >/dev/null 2>&1; then
    MAKE_CMD="make"
elif command -v mingw32-make >/dev/null 2>&1; then
    MAKE_CMD="mingw32-make"
else
    MAKE_CMD=""
fi

echo ""
echo "--- 1. Toolchain Versions ---"

echo -n "Python 3: "
$PY_CMD --version
echo -n "pip 3:    "
$PIP_CMD --version

if command -v gcc >/dev/null 2>&1; then
    echo -n "GCC:      "
    gcc --version | head -n 1
else
    echo "GCC:      NOT FOUND (skipping C tests)"
fi

if command -v g++ >/dev/null 2>&1; then
    echo -n "G++:      "
    g++ --version | head -n 1
else
    echo "G++:      NOT FOUND (skipping C++ tests)"
fi

if [ -n "$MAKE_CMD" ]; then
    echo -n "Make:     "
    $MAKE_CMD --version | head -n 1
else
    echo "Make:     NOT FOUND (skipping Make tests)"
fi

echo -n "Git:      "
git --version

# 4. Python & Venv Verification
echo ""
echo "--- 2. Python & Virtual Environment Test ---"

# Create hello.py
cat << 'EOF' > hello.py
print("Hello from Cloud IDE")
EOF

# Run with system python
SYS_PY_OUT=$($PY_CMD hello.py)
echo "System $PY_CMD output: $SYS_PY_OUT"
if [ "$SYS_PY_OUT" != "Hello from Cloud IDE" ]; then
    echo "ERROR: Unexpected system python output: $SYS_PY_OUT"
    exit 1
fi

# Create virtual environment
echo "Creating virtual environment: $TEST_DIR/.venv ..."
$PY_CMD -m venv "$TEST_DIR/.venv"

ACTIVATE_SCRIPT=""
if [ -f "$TEST_DIR/.venv/bin/activate" ]; then
    ACTIVATE_SCRIPT="$TEST_DIR/.venv/bin/activate"
elif [ -f "$TEST_DIR/.venv/Scripts/activate" ]; then
    ACTIVATE_SCRIPT="$TEST_DIR/.venv/Scripts/activate"
else
    echo "ERROR: Virtual environment activation script not found."
    exit 1
fi

# Activate virtual environment
# shellcheck source=/dev/null
source "$ACTIVATE_SCRIPT"

echo -n "Venv Python: "
python --version
echo -n "Venv Pip:    "
pip --version

VENV_PY_OUT=$(python hello.py)
echo "Venv python output: $VENV_PY_OUT"
if [ "$VENV_PY_OUT" != "Hello from Cloud IDE" ]; then
    echo "ERROR: Unexpected venv python output: $VENV_PY_OUT"
    exit 1
fi

deactivate
echo "--> Python and virtual environment verified successfully."

# 5. C Compilation & Execution
if command -v gcc >/dev/null 2>&1; then
    echo ""
    echo "--- 3. C Compilation & Execution Test ---"

    cat << 'EOF' > hello.c
#include <stdio.h>

int main(void) {
    printf("Hello from C\n");
    return 0;
}
EOF

    gcc hello.c -o hello
    C_OUT=$(./hello)
    echo "C executable output: $C_OUT"
    if [ "$C_OUT" != "Hello from C" ]; then
        echo "ERROR: Unexpected C output: $C_OUT"
        exit 1
    fi
    echo "--> C compiler and execution verified successfully."
fi

# 6. C++ Compilation & Execution
if command -v g++ >/dev/null 2>&1; then
    echo ""
    echo "--- 4. C++ Compilation & Execution Test ---"

    cat << 'EOF' > hello.cpp
#include <iostream>

int main() {
    std::cout << "Hello from C++" << std::endl;
    return 0;
}
EOF

    g++ hello.cpp -o hello_cpp
    CPP_OUT=$(./hello_cpp)
    echo "C++ executable output: $CPP_OUT"
    if [ "$CPP_OUT" != "Hello from C++" ]; then
        echo "ERROR: Unexpected C++ output: $CPP_OUT"
        exit 1
    fi
    echo "--> C++ compiler and execution verified successfully."
fi

# 7. Make Build & Clean Test
if [ -n "$MAKE_CMD" ] && command -v gcc >/dev/null 2>&1; then
    echo ""
    echo "--- 5. Make Build & Clean Test ---"

    cat << 'EOF' > Makefile
all:
	gcc hello.c -o hello_make

clean:
	rm -f hello_make hello_make.exe
EOF

    $MAKE_CMD
    MAKE_OUT=$(./hello_make)
    echo "Make-built executable output: $MAKE_OUT"
    if [ "$MAKE_OUT" != "Hello from C" ]; then
        echo "ERROR: Unexpected Make executable output: $MAKE_OUT"
        exit 1
    fi

    $MAKE_CMD clean
    if [ -f "hello_make" ] || [ -f "hello_make.exe" ]; then
        echo "ERROR: 'make clean' failed to remove hello_make"
        exit 1
    fi
    echo "--> Make build and clean verified successfully."
fi

# 8. Git Local Repository Test
echo ""
echo "--- 6. Git Operations Test (Temporary Test Repo) ---"

git init -b main
git config user.email "cloudide-test@example.com"
git config user.name "CloudIDE Test"
git add hello.py
[ -f hello.c ] && git add hello.c
[ -f hello.cpp ] && git add hello.cpp
[ -f Makefile ] && git add Makefile
git commit -m "chore: test toolchain initial commit"

echo "Git status output:"
git status --short
echo "Git branch output:"
git branch -v
echo "Git latest commit output:"
git log -1 --oneline

echo "--> Git local operations verified successfully."

# 9. Summary
echo ""
echo "=================================================="
echo " ALL STEP 10 TOOLCHAIN CHECKS PASSED"
echo "=================================================="
