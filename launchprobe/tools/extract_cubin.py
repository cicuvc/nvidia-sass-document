#!/usr/bin/env python3
"""extract_cubin.py <file.cubin> <kernel_name> <out.bin>

Pure-stdlib ELF64 section extraction (.text.<kernel_name> -> out.bin),
plus REG count via cuobjdump --dump-resource-usage (written to stderr
and to <out.bin>.meta as "regcount=N entry=0x...").
"""
import re
import struct
import subprocess
import sys

CUOBJDUMP = "/usr/local/cuda/bin/cuobjdump"


def read_elf_sections(path):
    d = open(path, "rb").read()
    assert d[:4] == b"\x7fELF" and d[4] == 2, "need ELF64"
    (e_shoff,) = struct.unpack_from("<Q", d, 0x28)
    (e_shentsize,) = struct.unpack_from("<H", d, 0x3A)
    (e_shnum,) = struct.unpack_from("<H", d, 0x3C)
    (e_shstrndx,) = struct.unpack_from("<H", d, 0x3E)
    secs = []
    for i in range(e_shnum):
        off = e_shoff + i * e_shentsize
        name, stype, flags, addr, soff, size = struct.unpack_from("<IIQQQQ", d, off)
        secs.append((name, stype, flags, addr, soff, size))
    strbase = secs[e_shstrndx][4]

    def sname(n):
        end = d.index(b"\0", strbase + n)
        return d[strbase + n:end].decode()
    return d, [(sname(n), t, f, a, o, s) for n, t, f, a, o, s in secs]


def main():
    cubin, kernel, outbin = sys.argv[1], sys.argv[2], sys.argv[3]
    d, secs = read_elf_sections(cubin)
    text = None
    symtab = strtab = None
    for name, t, f, a, o, s in secs:
        if name == f".text.{kernel}":
            text = d[o:o + s]
        if name == ".symtab":
            symtab = (o, s)
        if name == ".strtab":
            strtab = (o, s)
    if text is None:
        print("sections:", [n for n, *_ in secs], file=sys.stderr)
        sys.exit(f"no .text.{kernel}")

    entry = 0
    if symtab and strtab:
        soff, ssize = symtab
        for i in range(0, ssize, 24):
            st_name, st_info, st_other, st_shndx, st_value, st_size = \
                struct.unpack_from("<IBBHQQ", d, soff + i)
            end = d.index(b"\0", strtab[0] + st_name)
            nm = d[strtab[0] + st_name:end].decode()
            if nm == kernel and st_shndx != 0:
                entry = st_value
                break
    if entry:
        print(f"[extract] entry offset {entry:#x} within .text", file=sys.stderr)
        text = text[entry:]

    open(outbin, "wb").write(text)

    reg = 0
    try:
        ru = subprocess.run([CUOBJDUMP, "--dump-resource-usage", cubin],
                            capture_output=True, text=True, timeout=60).stdout
        m = re.search(rf"Function {re.escape(kernel)}:.*?REG:(\d+)", ru, re.S)
        if not m:
            m = re.search(r"REG:(\d+)", ru)
        if m:
            reg = int(m.group(1))
    except Exception as e:
        print(f"[extract] resource-usage failed: {e}", file=sys.stderr)
    print(f"[extract] {len(text)} bytes code, regcount={reg}", file=sys.stderr)
    open(outbin + ".meta", "w").write(f"regcount={reg}\nentry=0x0\n")


if __name__ == "__main__":
    main()
