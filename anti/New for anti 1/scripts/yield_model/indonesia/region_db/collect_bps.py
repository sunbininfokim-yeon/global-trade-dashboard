"""Download immutable BPS source publications listed in the local manifest."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone

from .manifest import BY_ID, PUBLICATIONS


HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
METADATA = os.path.join(HERE, "data", "download_metadata.json")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(publication, refresh=False):
    crop_dir = os.path.join(RAW, publication["crop"])
    os.makedirs(crop_dir, exist_ok=True)
    path = os.path.join(crop_dir, publication["id"] + ".pdf")
    if not os.path.exists(path) or refresh:
        request = urllib.request.Request(
            publication["download_url"],
            headers={"User-Agent": "Mozilla/5.0 BPS province panel audit"},
        )
        temporary = path + ".part"
        try:
            with urllib.request.urlopen(request, timeout=300) as response, open(
                    temporary, "wb") as handle:
                handle.write(response.read())
        except (urllib.error.URLError, TimeoutError):
            curl = shutil.which("curl")
            if not curl:
                raise
            subprocess.run([
                curl, "--http1.1", "--location", "--fail", "--silent",
                "--show-error", "--retry", "4", "--retry-all-errors",
                "--user-agent", "Mozilla/5.0 BPS province panel audit",
                "--output", temporary, publication["download_url"],
            ], check=True)
        if not open(temporary, "rb").read(4).startswith(b"%PDF"):
            raise RuntimeError(publication["id"] + ": response is not a PDF")
        os.replace(temporary, path)
    return {
        "id": publication["id"], "path": path,
        "bytes": os.path.getsize(path), "sha256": sha256(path),
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "page_url": publication["page_url"],
    }


def main():
    args = list(sys.argv[1:])
    refresh = "--refresh" in args
    args = [arg for arg in args if arg != "--refresh"]
    selected = [BY_ID[arg] for arg in args] if args else PUBLICATIONS
    records = []
    for publication in selected:
        print("[bps:download] " + publication["id"], flush=True)
        records.append(download(publication, refresh=refresh))
    os.makedirs(os.path.dirname(METADATA), exist_ok=True)
    with open(METADATA, "w", encoding="utf-8") as handle:
        json.dump(records, handle, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
