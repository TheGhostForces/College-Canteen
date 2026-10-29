"""Backup wrapper regressions without Docker, network or production data."""

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_backup(tmp_path, *, fail=False):
    tools = tmp_path / "bin"
    tools.mkdir()
    docker = tools / "docker"
    docker.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"pg_restore --list"*) cat >/dev/null ;;\n'
        '  *"pg_dump"*) printf "test-archive"; [ "${FAIL_DUMP:-0}" = 0 ] ;;\n'
        "  *) exit 99 ;;\n"
        "esac\n"
    )
    docker.chmod(0o700)
    destination = tmp_path / "backups"
    env = {**os.environ, "PATH": f"{tools}:{os.environ['PATH']}", "FAIL_DUMP": "1" if fail else "0"}
    result = subprocess.run(
        ["bash", str(ROOT / "ops/backup.sh"), str(destination)], env=env, capture_output=True, text=True
    )
    return result, destination


def test_backup_publishes_complete_private_archive(tmp_path):
    result, destination = run_backup(tmp_path)
    assert result.returncode == 0, result.stderr
    archives = list(destination.glob("*.dump"))
    assert len(archives) == 1
    assert archives[0].read_bytes() == b"test-archive"
    assert archives[0].stat().st_mode & 0o077 == 0
    assert not list(destination.glob(".database.*"))


def test_failed_dump_is_not_published(tmp_path):
    result, destination = run_backup(tmp_path, fail=True)
    assert result.returncode != 0
    assert not list(destination.glob("*.dump"))
    assert not list(destination.glob(".database.*"))


def test_operations_scripts_have_valid_bash_syntax():
    for script in (ROOT / "ops").glob("*.sh"):
        result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
