#!/usr/bin/env python3
"""Verify or unpack the curated tcgen05 primary evidence (stdlib only)."""

import argparse
import gzip
import hashlib
import json
from pathlib import Path


DATA = Path(__file__).resolve().parents[1] / "notes/sm100/arch/data"


def local_path(root, name):
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError(f"Path outside evidence directory: {name}")
    return path


def check(raw, expected_size, expected_hash, name):
    if len(raw) != expected_size or hashlib.sha256(raw).hexdigest() != expected_hash:
        raise ValueError(f"Evidence checksum mismatch: {name}")


def process(root, unpack=False):
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["format_version"] != 1:
        raise ValueError("Unsupported manifest version")
    restored = 0
    for record in manifest["files"]:
        path = local_path(root, record["path"])
        original = local_path(root, record["original_path"])
        packed = path.read_bytes()
        check(packed, record["bytes"], record["sha256"], path)
        encoding = record["encoding"]
        if encoding not in ("gzip", "identity"):
            raise ValueError(f"Unsupported encoding: {encoding}")
        raw = gzip.decompress(packed) if encoding == "gzip" else packed
        check(raw, record["original_bytes"], record["original_sha256"], original)
        if unpack and encoding == "gzip":
            if original.exists():
                check(original.read_bytes(), len(raw), record["original_sha256"], original)
            else:
                original.parent.mkdir(parents=True, exist_ok=True)
                with original.open("xb") as stream:
                    stream.write(raw)
                restored += 1
    print(f"Verified {len(manifest['files'])} evidence files; restored {restored} originals.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "unpack"))
    args = parser.parse_args()
    process(DATA, unpack=args.command == "unpack")


if __name__ == "__main__":
    main()
