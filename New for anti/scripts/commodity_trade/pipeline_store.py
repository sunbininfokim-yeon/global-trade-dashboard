"""Atomic JSON persistence and advisory single-writer lock (macOS/Linux)."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile


def read_json(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.' + path.name, delete=False) as f:
            tmp = Path(f.name)
            json.dump(data, f, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()


@contextmanager
def single_writer(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
