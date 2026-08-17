#!/usr/bin/env python3
"""CLI smoke test (CTest 'cli_smoke').

Runs the semu binary and asserts exit codes and output for the Phase 0 CLI
contract: --version, capability manifest, invalid command line, and empty /
missing module handling.  Exits 0 on success, 1 on any assertion failure.

Also hosts the Phase 7 round-3 CLI help golden gate: driving the `debug` REPL
must not advertise `--lane` as a memory-scope option, while the
breakpoint/watchpoint conditions help must keep the `--lane 0xMASK` lane mask.

Usage: cli_smoke_test.py <semu binary> <empty module fixture>
"""
import pathlib
import subprocess
import sys


def run(binary, *args, input_text=None):
    return subprocess.run([str(binary), *map(str, args)], text=True,
                          capture_output=True, input=input_text)


def debug_help_golden(binary) -> int:
    """Phase 7 round-3 re-review golden gate.

    MemoryScope has no lane dimension (local is a per-warp window), so the
    user-visible debug help must not list `--lane N` as a `mem` scope option;
    the breakpoint/watchpoint conditions line must still document the lane
    mask (`--lane 0xMASK`).
    """
    import tempfile

    repo = pathlib.Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(repo))
    try:
        from assembler import assemble  # noqa: PLC0415
    except Exception as e:  # noqa: BLE001
        print(f"  FAIL  debug_help_golden: assembler import: {e}")
        return 1
    src = """
#fn k_add(a<8>, b<8>, c<8>, n<4>) {
  LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[0:7:{}:1:0]
  LDC.64 {R2,R3}, #param(a);[1:7:{}:1:0]
  LDC.64 {R4,R5}, #param(b);[2:7:{}:1:0]
  LDC.64 {R6,R7}, #param(c);[3:7:{}:1:0]
  LDC.32 R8, #param(n);[4:7:{}:1:0]
  LDG.E.64 {R10,R11}, desc[{UR4,UR5}][{R2,R3}+0x0];[0:1:{0,1}:1:0]
  LDG.E.64 {R12,R13}, desc[{UR4,UR5}][{R4,R5}+0x0];[1:1:{0,1}:1:0]
  FADD R14, R10, R12;[2:7:{}:1:0]
  FADD R15, R11, R13;[3:7:{}:1:0]
  STG.E.64 desc[{UR4,UR5}][{R6,R7}+0x0], {R14,R15};[4:1:{0,1}:1:0]
  EXIT;[7:7:{}:5:0]
}
"""
    with tempfile.TemporaryDirectory() as td:
        cubin = pathlib.Path(td) / "dbg_help.cubin"
        try:
            cubin.write_bytes(assemble(src, kernel_name="k_add",
                                       check_deps=False))
        except Exception as e:  # noqa: BLE001
            print(f"  FAIL  debug_help_golden: assemble: {e}")
            return 1
        p = run(binary, "debug", str(cubin), "_Z5k_add", "1", "1",
                input_text="help\nmem\nq\n")
        if p.returncode != 0:
            print(f"  FAIL  debug_help_golden: debug REPL rc={p.returncode} "
                  f"(want 0)")
            print(f"       stderr={p.stderr[:300]!r}")
            return 1
        out, err = p.stdout, p.stderr
        mem_help = "\n".join(l for l in out.splitlines()
                             if l.strip().startswith("mem "))
        conds_help = "\n".join(l for l in out.splitlines()
                               if "conds:" in l)
        results = [
            ("mem scope help has no --lane",
             "--lane" not in mem_help, mem_help),
            ("mem usage (stderr) has no --lane", "--lane" not in err, err),
            ("conds help keeps lane mask", "--lane 0xMASK" in conds_help,
             conds_help),
            ("--lane appears only on the conds line",
             sum("--lane" in l for l in out.splitlines()) == 1,
             out.splitlines()[-6:]),
        ]
        failures = 0
        for name, ok, detail in results:
            print(("  ok  " if ok else "FAIL  ") + name)
            if not ok:
                failures += 1
                print(f"       {detail!r}")
        return 1 if failures else 0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: cli_smoke_test.py <semu binary> <empty module>",
              file=sys.stderr)
        return 2
    binary = pathlib.Path(sys.argv[1])
    empty = pathlib.Path(sys.argv[2])
    failures = 0

    def check(name, r, expect_code, *needles, stream="out"):
        nonlocal failures
        text = r.stdout if stream == "out" else r.stderr
        ok = r.returncode == expect_code and all(n in text for n in needles)
        print(("  ok  " if ok else "FAIL  ") + name)
        if not ok:
            failures += 1
            print(f"       rc={r.returncode} (want {expect_code})")
            print(f"       stdout={r.stdout[:200]!r}")
            print(f"       stderr={r.stderr[:200]!r}")

    print("cli: --version")
    check("version", run(binary, "--version"), 0,
          "semu 0.1.0", "error model: 1", "capability manifest: 1")

    print("cli: capability manifest")
    r = run(binary, "capability")
    check("summary", r, 0, "semu capability manifest v1", "1414 variants")
    check("full", run(binary, "capability", "--full"), 0, "decode-only")

    print("cli: invalid command line")
    check("unknown command", run(binary, "frobnicate"), 2,
          "unknown command", stream="err")
    check("no args", run(binary), 2, "usage: semu", stream="err")
    check("bad capability option", run(binary, "capability", "--nope"), 2,
          "unknown capability option", stream="err")

    print("cli: module argument validation")
    check("missing module", run(binary, "load", "/nonexistent/x.cubin"), 1,
          "cannot open module", stream="err")
    check("empty module", run(binary, "load", empty), 1,
          "empty module", "caused by", stream="err")
    check("missing arg", run(binary, "load"), 2, "'load' requires", stream="err")

    print("cli: debug REPL help golden (Phase 7 round 3)")
    failures += debug_help_golden(binary)

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
