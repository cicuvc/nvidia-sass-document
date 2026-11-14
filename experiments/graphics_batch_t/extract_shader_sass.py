#!/usr/bin/env python3
"""Recover one shader function from driver-memory candidate dumps."""

from __future__ import annotations

import argparse
import hashlib
import pathlib
import subprocess
import tempfile


EXIT_LOW = bytes.fromhex("4d79000000000000")


def disassemble(raw: pathlib.Path, arch: str) -> str | None:
    result = subprocess.run(
        ["nvdisasm", "--binary", arch, str(raw)],
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dump_dir", type=pathlib.Path)
    parser.add_argument("--arch", default="SM75")
    parser.add_argument("--signature", required=True,
                        help="Hex bytes that occur inside the shader's SASS")
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--include-s2r", action="store_true")
    args = parser.parse_args()

    signature = bytes.fromhex(args.signature)
    best: tuple[int, bytes, str] | None = None
    seen: set[str] = set()
    files = sorted(args.dump_dir.glob("shader_*.bin"))
    if args.include_s2r:
        files += sorted(args.dump_dir.glob("s2r_*.bin"))
    with tempfile.TemporaryDirectory(prefix="extract-sass-") as td:
        temp_raw = pathlib.Path(td) / "slice.bin"
        for path in files:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest in seen:
                continue
            seen.add(digest)
            sig = data.find(signature)
            if sig < 0:
                continue

            exits = []
            pos = sig
            while True:
                pos = data.find(EXIT_LOW, pos)
                if pos < 0 or pos - sig > 8192:
                    break
                if pos % 16 == 0:
                    exits.append(pos)
                pos += 1
            if not exits:
                continue

            low_start = max(0, (sig - 1024) & ~15)
            for exit_off in exits:
                for start in range(low_start, sig + 1, 16):
                    end = exit_off + 16
                    raw = data[start:end]
                    temp_raw.write_bytes(raw)
                    text = disassemble(temp_raw, args.arch)
                    if text is None or "EXIT" not in text:
                        continue
                    score = text.count("IPA.PASS")
                    if best is None or score > best[0]:
                        best = (score, raw, text)
                    if score >= 5:
                        break
                if best is not None and best[0] >= 5:
                    break
            if best is not None and best[0] >= 5:
                break

    if best is None:
        raise SystemExit("no candidate shader function found")

    _, raw, text = best
    args.out.write_bytes(raw)
    args.out.with_suffix(".sass").write_text(text)
    print(f"wrote {len(raw)} bytes to {args.out}")
    print(f"disassembly: {args.out.with_suffix('.sass')}")


if __name__ == "__main__":
    main()
