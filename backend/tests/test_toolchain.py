"""
Tests for STEP 10: Toolchain and Execution Verification.

Verifies:
- Python 3 interpreter and version
- Python virtual environment (venv) creation and execution
- GCC compilation and execution (skipped gracefully if unavailable on host)
- G++ compilation and execution (skipped gracefully if unavailable on host)
- Make execution and clean (skipped gracefully if unavailable on host)
- Git repository status, branch, and log in temporary test repository
- Non-destructive operation guarantee (never modifies user repositories or global root)
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
import pytest


# 1. Python 3 Interpreter & Basic Execution
def test_python_interpreter_and_version():
    """Verify that Python 3 is available and executes correctly."""
    assert sys.version_info[0] == 3, f"Expected Python 3, got Python {sys.version_info[0]}"

    proc = subprocess.run(
        [sys.executable, "-c", 'print("Hello from Cloud IDE")'],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "Hello from Cloud IDE"


# 2. Python Virtual Environment (venv) Creation & Execution
def test_python_venv_creation_and_execution(tmp_path):
    """Verify that a Python virtual environment can be created and run scripts."""
    venv_dir = tmp_path / "test_venv"
    proc = subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, f"venv creation failed: {proc.stderr}"

    # Determine venv python binary path across platforms
    if os.name == "nt":
        venv_python = venv_dir / "Scripts" / "python.exe"
    else:
        venv_python = venv_dir / "bin" / "python"

    assert venv_python.exists(), f"Venv python binary not found at {venv_python}"

    test_script = tmp_path / "hello.py"
    test_script.write_text('print("Hello from Cloud IDE venv")\n')

    run_proc = subprocess.run(
        [str(venv_python), str(test_script)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run_proc.returncode == 0
    assert run_proc.stdout.strip() == "Hello from Cloud IDE venv"


# 3. GCC C Compilation & Execution (Graceful Skip if Missing)
def test_gcc_c_compilation_and_execution(tmp_path):
    """Verify GCC compiles and executes a minimal C program."""
    gcc_bin = shutil.which("gcc")
    if not gcc_bin:
        pytest.skip("GCC not available in current host environment")

    source_file = tmp_path / "hello.c"
    output_bin = tmp_path / ("hello.exe" if os.name == "nt" else "hello")

    source_file.write_text(
        '#include <stdio.h>\n'
        'int main(void) {\n'
        '    printf("Hello from C\\n");\n'
        '    return 0;\n'
        '}\n'
    )

    compile_proc = subprocess.run(
        [gcc_bin, str(source_file), "-o", str(output_bin)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert compile_proc.returncode == 0, f"GCC compilation failed: {compile_proc.stderr}"
    assert output_bin.exists(), "Compiled binary was not created"

    run_proc = subprocess.run(
        [str(output_bin)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run_proc.returncode == 0
    assert run_proc.stdout.strip() == "Hello from C"


# 4. G++ C++ Compilation & Execution (Graceful Skip if Missing)
def test_gpp_cpp_compilation_and_execution(tmp_path):
    """Verify G++ compiles and executes a minimal C++ program."""
    gpp_bin = shutil.which("g++")
    if not gpp_bin:
        pytest.skip("G++ not available in current host environment")

    source_file = tmp_path / "hello.cpp"
    output_bin = tmp_path / ("hello_cpp.exe" if os.name == "nt" else "hello_cpp")

    source_file.write_text(
        '#include <iostream>\n'
        'int main() {\n'
        '    std::cout << "Hello from C++" << std::endl;\n'
        '    return 0;\n'
        '}\n'
    )

    compile_proc = subprocess.run(
        [gpp_bin, str(source_file), "-o", str(output_bin)],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert compile_proc.returncode == 0, f"G++ compilation failed: {compile_proc.stderr}"
    assert output_bin.exists(), "Compiled C++ binary was not created"

    run_proc = subprocess.run(
        [str(output_bin)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run_proc.returncode == 0
    assert run_proc.stdout.strip() == "Hello from C++"


# 5. Make Build & Clean Test (Graceful Skip if Missing)
def test_make_build_and_clean(tmp_path):
    """Verify Make executes default build target and clean target."""
    make_bin = shutil.which("make") or shutil.which("mingw32-make")
    gcc_bin = shutil.which("gcc")
    if not make_bin or not gcc_bin:
        pytest.skip("Make or GCC not available in current host environment")

    c_file = tmp_path / "hello.c"
    c_file.write_text(
        '#include <stdio.h>\n'
        'int main(void) {\n'
        '    printf("Hello from C\\n");\n'
        '    return 0;\n'
        '}\n'
    )

    target_name = "hello_make"
    clean_cmd = "del /f /q" if (os.name == "nt" and not shutil.which("rm")) else "rm -f"
    makefile = tmp_path / "Makefile"
    makefile.write_text(
        f"all:\n"
        f"\tgcc hello.c -o {target_name}\n\n"
        f"clean:\n"
        f"\t{clean_cmd} {target_name} {target_name}.exe\n"
    )

    build_proc = subprocess.run(
        [make_bin],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert build_proc.returncode == 0, f"Make build failed: {build_proc.stderr}"

    built_bin = tmp_path / (f"{target_name}.exe" if os.name == "nt" else target_name)
    assert built_bin.exists(), "Make target binary was not produced"

    run_proc = subprocess.run(
        [str(built_bin)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert run_proc.returncode == 0
    assert run_proc.stdout.strip() == "Hello from C"

    # Test make clean
    clean_proc = subprocess.run(
        [make_bin, "clean"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert clean_proc.returncode == 0, f"Make clean failed: {clean_proc.stderr}"
    assert not built_bin.exists(), "Make clean did not remove target binary"


# 6. Git Local Operations in Temporary Test Repository
def test_git_local_repository_operations(tmp_path):
    """Verify git status, branch, and log in an ephemeral repository."""
    git_bin = shutil.which("git")
    if not git_bin:
        pytest.skip("Git not available in current host environment")

    repo_dir = tmp_path / "test_git_repo"
    repo_dir.mkdir()

    # 1. git init
    init_proc = subprocess.run(
        [git_bin, "init", "-b", "main"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert init_proc.returncode == 0

    # Configure local dummy identity
    subprocess.run([git_bin, "config", "user.email", "test@cloudide.local"], cwd=str(repo_dir), check=True)
    subprocess.run([git_bin, "config", "user.name", "CloudIDE Test"], cwd=str(repo_dir), check=True)

    # 2. git status (empty repo)
    status_proc = subprocess.run(
        [git_bin, "status", "--short"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert status_proc.returncode == 0

    # 3. Add and commit test file
    test_file = repo_dir / "README.md"
    test_file.write_text("# Cloud IDE Toolchain Verification\n")
    subprocess.run([git_bin, "add", "README.md"], cwd=str(repo_dir), check=True)

    commit_proc = subprocess.run(
        [git_bin, "commit", "-m", "Initial test commit"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert commit_proc.returncode == 0

    # 4. git branch
    branch_proc = subprocess.run(
        [git_bin, "branch", "--show-current"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert branch_proc.returncode == 0
    assert branch_proc.stdout.strip() == "main"

    # 5. git log -1
    log_proc = subprocess.run(
        [git_bin, "log", "-1", "--oneline"],
        cwd=str(repo_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert log_proc.returncode == 0
    assert "Initial test commit" in log_proc.stdout


# 7. Non-Destructive Guarantee
def test_non_destructive_guarantee():
    """Verify toolchain test scripts do not touch project or user directories."""
    toolchain_script = Path(__file__).resolve().parent.parent.parent / "scripts" / "toolchain_test.sh"
    assert toolchain_script.exists(), "scripts/toolchain_test.sh must exist"

    content = toolchain_script.read_text(encoding="utf-8")
    assert "/tmp/cloudide-toolchain-test" in content
    assert "trap cleanup" in content
    # Guarantee no hard resets or forced cleans on user repositories
    assert "git reset --hard" not in content
    assert "git clean -fd" not in content
