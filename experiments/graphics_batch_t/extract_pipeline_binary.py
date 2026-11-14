#!/usr/bin/env python3
"""Decompress a Vulkan pipeline binary and recover raw SASS functions."""

from __future__ import annotations

import argparse
import pathlib
import struct
import subprocess
import tempfile


ZSTD_MAGIC = bytes.fromhex("28b52ffd")
EXIT_LOW = 0x794D


def decompress_pipeline_binary(data: bytes) -> bytes:
    if data[4:8] != ZSTD_MAGIC:
        raise SystemExit("pipeline binary is not a size-prefixed zstd container")
    try:
        result = subprocess.run(
            ["zstd", "-d", "-c"],
            input=data[4:],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit("zstd executable not found") from None
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.stderr.decode("utf-8", "replace")) from None
    expected_size = struct.unpack_from("<I", data)[0]
    if len(result.stdout) != expected_size:
        raise SystemExit(
            f"zstd size mismatch: {len(result.stdout)} != {expected_size}"
        )
    return result.stdout


def disassemble(raw: bytes, arch: str) -> str | None:
    with tempfile.NamedTemporaryFile() as temp:
        temp.write(raw)
        temp.flush()
        result = subprocess.run(
            ["nvdisasm", "--binary", arch, "--print-instruction-encoding",
             temp.name],
            capture_output=True,
            text=True,
        )
    if result.returncode != 0 or "EXIT" not in result.stdout:
        return None
    return result.stdout


def extract_functions(raw: bytes, arch: str, window: int) -> list[tuple[int, bytes, str]]:
    exits = []
    for offset in range(0, len(raw) - 15):
        if struct.unpack_from("<Q", raw, offset)[0] == EXIT_LOW:
            exits.append(offset)

    functions = []
    for exit_offset in exits:
        end = exit_offset + 16
        first = max(0, end - window)
        first += (end - first) % 16
        for start in range(first, exit_offset + 1, 16):
            if (end - start) % 16:
                continue
            block = raw[start:end]
            text = disassemble(block, arch)
            if text is None:
                continue
            functions.append((start, block, text))
            break
    return functions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("pipeline_binary", type=pathlib.Path)
    parser.add_argument("--arch", default="SM75")
    parser.add_argument("--out-prefix", type=pathlib.Path)
    parser.add_argument("--window", type=int, default=8192)
    args = parser.parse_args()

    source = args.pipeline_binary.read_bytes()
    raw = decompress_pipeline_binary(source)
    out_prefix = args.out_prefix or args.pipeline_binary.with_suffix("")
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    (out_prefix.parent / f"{out_prefix.name}.raw").write_bytes(raw)

    functions = extract_functions(raw, args.arch, args.window)
    if not functions:
        raise SystemExit("no complete SASS function found")
    seen: set[bytes] = set()
    output_index = 0
    for start, block, text in functions:
        if block in seen:
            continue
        seen.add(block)
        raw_path = out_prefix.parent / (
            f"{out_prefix.name}.shader{output_index}.bin"
        )
        sass_path = out_prefix.parent / (
            f"{out_prefix.name}.shader{output_index}.sass"
        )
        raw_path.write_bytes(block)
        sass_path.write_text(text)
        print(
            f"shader[{output_index}]: raw_offset=0x{start:x} "
            f"bytes={len(block)} -> {sass_path}"
        )
        output_index += 1


if __name__ == "__main__":
    main()
