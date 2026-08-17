#!/usr/bin/env python3
"""Phase 8 LDGSTS oracle + profiler JSON schema compatibility test.

Two gates:

1. LDGSTS corpus vs Python reference (arch/l1tex/unified_model.py):
   - C++ base fields (SharedWf/ReadWf/WriteWf/OverlapWf/Tokens/TokenStats)
     must equal the Python `unified_model.simulate` field-by-field.
   - The pure architectural count fields (TWf/TagConf/TSetAcc/Sectors) must
     equal the hardware-measured corpus `meas` on every row (they are pure
     counting from per-lane offsets).
   - SharedConf/GlobalConf are definitional/approximate counters and are only
     checked for presence + confidence labels, never against `meas`.

2. Profiler JSON schema compatibility:
   - The CLI `run --l1tex --profile` emits a profiler report; it must parse as
     JSON, carry schema_version == "1.0", and contain every frozen field.
   - Re-running on the same cubin must be byte-for-byte deterministic.

Usage:
    profiler_report_test.py <semu> <semu_l1tex_cli> <arch_dir> [cubin_dir]
"""
import json
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"

ARCH = Path("/home/cicuvc/cs/projects/arch/l1tex")
ROOT = Path("/home/cicuvc/cs/projects/nvidia-sass-document")


def run_cpp(cli, g, s, size, mask, ldgsts=False):
    gs = ",".join(str(x) for x in g)
    ss = ",".join(str(x) for x in s)
    args = ["--ldgsts"] if ldgsts else []
    p = subprocess.run([str(cli)] + args + [f"g={gs}", f"s={ss}",
                        f"m={mask}", f"size={size}"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        return None
    return json.loads(p.stdout)


def base_match(cpp, py):
    if cpp["SharedWf"] != py["SharedWf"]: return "SharedWf"
    if cpp["ReadWf"] != py["ReadWf"]: return "ReadWf"
    if cpp["WriteWf"] != py["WriteWf"]: return "WriteWf"
    if cpp["OverlapWf"] != py["OverlapWf"]: return "OverlapWf"
    if cpp["Tokens"] != py["Tokens"]: return "Tokens"
    cs, ps = cpp["TokenStats"], py["TokenStats"]
    if len(cs) != len(ps): return "TokenStats.len"
    for a, b in zip(cs, ps):
        for k in ("Token", "Lanes", "ReadWf", "WriteWf", "OverlapWf", "SharedWf"):
            if a[k] != b[k]:
                return f"TokenStats.{k}"
    return None


def gate_ldgsts_corpus(cli, arch_dir):
    sys.path.insert(0, str(arch_dir))
    from unified_model import simulate  # noqa: E402

    hard_total = hard_exact = 0
    count_total = 0
    count_exact = {k: 0 for k in ("TWf", "TagConf", "TSetAcc", "Sectors")}
    conf_checked = 0
    for f in ("data4_ldgsts_warmldg.jsonl",
              "data8_ldgsts_warmldg.jsonl",
              "data16_ldgsts_warmldg.jsonl"):
        size_hint = 4 if f.startswith("data4") else 8 if f.startswith("data8") else 16
        rows = [json.loads(l) for l in (arch_dir / f).open()]
        for row in rows:
            size = row.get("size", size_hint)
            py = simulate(row["g"], row["s"], size, row["m"])
            cpp = run_cpp(cli, row["g"], row["s"], size, row["m"], ldgsts=False)
            if cpp is None:
                return False, f"{f}: C++ run failed"
            hard_total += 1
            if base_match(cpp, py) is None:
                hard_exact += 1

            cpp = run_cpp(cli, row["g"], row["s"], size, row["m"], ldgsts=True)
            if cpp is None:
                return False, f"{f}: C++ --ldgsts run failed"
            meas = row["meas"]
            count_total += 1
            for k in count_exact:
                if meas.get(k) == cpp.get(k):
                    count_exact[k] += 1
            # Confidence labels must degrade only in the declared direction:
            # never "unsupported" on a default-policy row, never "exact" for
            # the definitional conflict counters.
            assert cpp.get("SharedWfConfidence") in ("exact-empirical", "approximate")
            assert cpp.get("CountConfidence") == "exact-empirical"
            assert cpp.get("ConflictConfidence") == "approximate"
            conf_checked += 1

    print(f"LDGSTS corpus: base C++==Python {hard_exact}/{hard_total}")
    print(f"  pure counts == hardware meas: TWf {count_exact['TWf']}/{count_total}, "
          f"TagConf {count_exact['TagConf']}/{count_total}, "
          f"TSetAcc {count_exact['TSetAcc']}/{count_total}, "
          f"Sectors {count_exact['Sectors']}/{count_total}")
    print(f"  confidence-label checks passed on {conf_checked} rows")
    if hard_exact != hard_total:
        return False, f"base mismatch: {hard_exact}/{hard_total}"
    if any(v != count_total for v in count_exact.values()):
        return False, f"pure-count mismatch: {count_exact}/{count_total}"
    return True, ""


def build_stg_cubin(out, assembler_src):
    """Build a small STG kernel cubin with the repo assembler."""
    sys.path.insert(0, str(ROOT))
    try:
        from assembler import assemble
    except ImportError:
        raise SystemExit("repo assembler not importable")
    cubin = assemble(assembler_src, kernel_name="ksty", check_deps=False)
    out.write_bytes(cubin)


# Medium-1 (codex review): the schema gate no longer checks a bare
# pc/mnemonic/space/events subset.  A full canonical schema golden
# (tools/profiler_schema_v1.0.json) is loaded and every REQUIRED field is
# validated for presence + type + enum value; unknown extra fields are
# tolerated (forward-compatibility policy).  A missing required field or a
# wrong enum always fails.
TYPE_MAP = {"string": str, "integer": int, "array": list, "object": dict}


def _check_spec(value, spec, path, defs):
    t = spec.get("type")
    if t not in TYPE_MAP:
        return f"{path}: unknown schema type {t!r}"
    if not isinstance(value, TYPE_MAP[t]):
        return f"{path}: bad type {type(value).__name__} (want {t})"
    enum = spec.get("enum")
    if enum is not None and value not in enum:
        return f"{path}: bad enum value {value!r} (want one of {enum})"
    if t == "array":
        items = spec.get("items")
        if items is not None:
            for i, v in enumerate(value):
                if isinstance(items, str):
                    err = _check_def(v, items, f"{path}[{i}]", defs)
                else:
                    err = _check_spec(v, items, f"{path}[{i}]", defs)
                if err:
                    return err
    return None


def _check_def(value, defname, path, defs):
    if defname not in defs:
        return f"{path}: unknown schema def {defname!r}"
    spec = defs[defname]
    for k, subspec in spec.items():
        if k not in value:
            return f"{path}.{k}: missing required field"
        err = _check_spec(value[k], subspec, f"{path}.{k}", defs)
        if err:
            return err
    return None


def load_canonical_schema(path):
    data = json.loads(Path(path).read_text())
    assert data["meta"]["schema_version"] == SCHEMA_VERSION
    return data["required"], data["defs"]


def validate_schema(obj, required, defs):
    """Presence + type + enum for every REQUIRED field; unknown extra fields
    are ignored (forward compatibility)."""
    for k, spec in required.items():
        if k not in obj:
            return f"missing required field {k}"
        err = _check_spec(obj[k], spec, k, defs)
        if err:
            return err
    return None


def gate_schema(semu, tmpdir):
    STG_SRC = """#fn ksty(ptr<8>, val<4>) {
    #pragma SHARED(0x4000)
    LDCU.64 {UR4,UR5}, #spec_const(SLOT_DEFAULT_CDESC);[3:7:{}:1:0]
    LDC.64 {R6,R7}, #param(ptr);[3:7:{}:1:0]
    S2R R0, SR_TID.X;[4:7:{}:5:1]
    MOV32I R3, 4;[1:7:{}:1:0]
    IMAD R4, R0, R3, RZ;[2:7:{1}:1:0]
    STG.E desc[{UR4,UR5}][{R6,R7}], R0;[0:1:{0,1}:1:0]
    EXIT;[7:7:{}:5:0]
}"""
    cubin = tmpdir / "ksty.cubin"
    build_stg_cubin(cubin, STG_SRC)

    def run():
        p = subprocess.run(
            [str(semu), "run", "--l1tex", "--profile",
             str(cubin), "_Z4ksty", "1", "32"],
            capture_output=True, text=True)
        if p.returncode != 0:
            return None, p.stderr
        i = p.stdout.find("{")
        return json.loads(p.stdout[i:]), p.stdout

    required, defs = load_canonical_schema(ROOT / "tools" / "profiler_schema_v1.0.json")

    obj, raw = run()
    if obj is None:
        return False, "cli run failed"
    prof = obj.get("profiler")
    if prof is None:
        return False, "profiler block missing (need --l1tex)"
    err = validate_schema(prof, required, defs)
    if err:
        return False, f"schema: {err}"

    # Medium-1 forward-compatibility policy: an unknown EXTRA field must NOT
    # break an older validator (producers may add fields), while deleting a
    # REQUIRED field must fail loudly.
    import copy
    augmented = copy.deepcopy(prof)
    augmented["future_field_9x"] = {"probe": 1}
    if validate_schema(augmented, required, defs) is not None:
        return False, "schema: unknown extra field must be tolerated"
    for drop in ("aggregate", "l2", "simulated_sm_count"):
        broken = copy.deepcopy(prof)
        broken.pop(drop, None)
        if validate_schema(broken, required, defs) is None:
            return False, f"schema: missing required field {drop} must fail"

    # Deterministic: same input -> byte-identical report block.
    _, raw1 = run()
    _, raw2 = run()
    if raw1 != raw2:
        return False, "report not deterministic"
    return True, ""


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        return 2
    semu = Path(sys.argv[1])
    cli = Path(sys.argv[2])
    arch_dir = Path(sys.argv[3])
    tmpdir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("/tmp/opencode")

    ok, err = gate_ldgsts_corpus(cli, arch_dir)
    if not ok:
        print("LDGSTS corpus gate FAILED:", err)
        return 1
    ok, err = gate_schema(semu, tmpdir)
    if not ok:
        print("profiler schema gate FAILED:", err)
        return 1
    print("profiler schema (v" + SCHEMA_VERSION + ") compatibility OK; "
          "report deterministic")
    return 0


if __name__ == "__main__":
    sys.exit(main())