"""Tests 91-93: build/lint/import smoke tests."""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.smoke


# -- Test 91: npm run build — Next.js builds without errors ------------------

def test_nextjs_build():
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd="web",
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, f"npm run build failed:\n{result.stderr}"


# -- Test 92: Python package imports cleanly ---------------------------------

def test_python_import():
    result = subprocess.run(
        [sys.executable, "-c", "import video_to_essay"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"Import failed:\n{result.stderr}"


# -- Test 93: ruff check — no lint errors ------------------------------------

def test_ruff_check():
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"ruff check failed:\n{result.stdout}"
