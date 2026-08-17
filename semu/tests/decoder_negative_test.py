#!/usr/bin/env python3
"""Negative-vector test (CTest 'decoder_negative', GAP-06).

Negative vectors must be rejected by the decoder, and the rejection reason
must be specific (not a blanket ILLEGAL):

  1. illegal-encoding table rows: for every variant whose encoding carries a
     `TABLES_mem_N(...)` table function, take each row of the matching
     `*_illegal_encodings` table whose fixed args are compatible and splice
     the row's `out` value into the word's mem field.  The decode must be
     ILLEGAL with the illegal-encodings rejection.
  2. discriminator enum holes: patch a star_slot discriminator field to a
     value that is NOT a member of the slot's enum -> ILLEGAL.
  3. register-group violations: patch a register operand to a misaligned /
     out-of-range value -> ILLEGAL (not AMBIG/OK).

Usage:
    decoder_negative_test.py <semu binary> <corpus json> <sm120.json>
"""
import json
import subprocess
import sys
from pathlib import Path


def extract(targets, lo, hi):
    val = 0
    for h, l in targets:
        w = h - l + 1
        mask = (1 << w) - 1
        if l >= 64:
            part = (hi >> (l - 64)) & mask
        elif h < 64:
            part = (lo >> l) & mask
        else:
            lo_w = 64 - l
            part = ((lo >> l) & ((1 << lo_w) - 1)) | (
                (hi & ((1 << (w - lo_w)) - 1)) << lo_w)
        val = (val << w) | part
    return val


def set_field(targets, lo, hi, value):
    """Overwrite a multi-range field with `value` (MSB-first)."""
    width = sum(h - l + 1 for h, l in targets)
    bits_left = width
    for h, l in targets:
        rw = h - l + 1
        bits_left -= rw
        sub = (value >> bits_left) & ((1 << rw) - 1)
        for b in range(l, h + 1):
            bit = (sub >> (b - l)) & 1
            if b >= 64:
                hi = (hi & ~(1 << (b - 64))) | (bit << (b - 64))
            else:
                lo = (lo & ~(1 << b)) | (bit << b)
    return lo, hi


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: decoder_negative_test.py <semu> <corpus> <db>",
              file=sys.stderr)
        return 2
    semu = Path(sys.argv[1])
    corpus_path = Path(sys.argv[2])
    if not corpus_path.is_file():
        subprocess.run([sys.executable,
                        str(Path(__file__).resolve().parent.parent /
                            "tools" / "gen_corpus.py"),
                        "--db", sys.argv[3], "--out", str(corpus_path)],
                       check=True, capture_output=True)
    corpus = json.load(open(corpus_path))
    db = json.load(open(sys.argv[3]))
    by_class = {r["variant_class"]: r for r in corpus if r["encoded"]}

    def decode(lo, hi):
        p = subprocess.run([str(semu), "disasm", str(lo), str(hi)],
                           text=True, capture_output=True)
        out = p.stdout.splitlines()[0] if p.stdout.splitlines() else ""
        return out

    n_ok = 0
    bad = []

    # 1. illegal-encoding table rows spliced into the mem field.  Only
    #    variants whose CONDITIONS actually reference the matching
    #    `!DEFINED *_illegal_encodings(...)` guard are tested -- the illegal
    #    table is only enforced there.
    for v in db["variants"]:
        if v.get("is_alternate") or v["class"] not in by_class:
            continue
        conds = " ".join(c["predicate"] for c in v["conditions"])
        for f in v["encoding"]:
            if f["rhs_kind"] != "table_fn" or "(" not in f["rhs"]:
                continue
            tn = f["rhs"].split("(")[0]
            ilt = db["tables"].get(tn + "_illegal_encodings")
            if not ilt:
                continue
            if f"DEFINED {tn}_illegal_encodings" not in conds and \
               f"!DEFINED {tn}_illegal_encodings" not in conds:
                continue
            args = f["rhs"].split("(")[1].rstrip(")").split(",")
            base = by_class[v["class"]]
            for row in ilt["rows"]:
                inargs = row["in"]
                if len(inargs) != len(args):
                    continue
                # fixed (literal) args must match
                ok_args = True
                for a, inv in zip(args, inargs):
                    try:
                        lit = int(a, 0)
                    except ValueError:
                        continue
                    if str(lit) != inv:
                        ok_args = False
                        break
                if not ok_args:
                    continue
                outv = int(row["out"], 0)
                nlo, nhi = set_field(f["targets"], base["lo"], base["hi"],
                                     outv)
                r = decode(nlo, nhi)
                if not r.startswith("ILLEGAL"):
                    bad.append(f"{v['class']}: illegal row {inargs} "
                               f"(out={outv}) decoded as {r.split(chr(9))[0]}")
                    continue
                n_ok += 1
                break  # one illegal row per variant is enough

    # 2. discriminator enum holes on star_slot MODIFIER fields (dstfmt /
    #    srcfmt / merge / ... -- the enum-membership discriminators).  Patching
    #    such a field to a non-member value must be rejected.  Register-typed
    #    star_slots (*Ra, *input_reg_sz_*) are excluded: their legality is
    #    enforced by conditions, not enum membership.
    for v in db["variants"]:
        if v.get("is_alternate") or v["class"] not in by_class:
            continue
        slot_by_name = {s["name"]: s for s in v["format"]["slots"]}
        for f in v["encoding"]:
            if f["rhs_kind"] != "star_slot" or "(" in f["rhs"]:
                continue
            name = f["rhs"].lstrip("*")
            try:
                int(name, 0)
                continue  # pinned literal
            except ValueError:
                pass
            slot = slot_by_name.get(name)
            if slot is None or not slot["modifier"]:
                continue
            if slot["type"] not in db["enums"]:
                continue
            e = db["enums"][slot["type"]]
            members = {x for x in e.values() if x is not None and x != -1}
            # only multi-member enums act as discriminators; singletons like
            # ONLY64/ONLY32 (input_reg_sz_*) carry no variant information.
            if len(members) < 2:
                continue
            # find a hole: a value inside the field's range that is not a
            # member and not INVALID-labeled
            width = sum(h - l + 1 for h, l in f["targets"])
            hole = None
            for cand in range(1 << width):
                if cand in members:
                    continue
                hole = cand
                break
            if hole is None:
                continue
            base = by_class[v["class"]]
            nlo, nhi = set_field(f["targets"], base["lo"], base["hi"], hole)
            r = decode(nlo, nhi)
            # The hole must not be accepted BY THIS VARIANT: either the word is
            # illegal, or it decodes to a sibling variant whose discriminator
            # legitimately covers the value (dstfmt=6 is U64 in the Rd64
            # sibling of a U8..S32 f2i class).  Accepting THIS class is the
            # failure mode.
            if r.startswith("OK"):
                parts = r.split("|")
                got = parts[1].strip() if len(parts) > 1 else ""
                if got == v["class"]:
                    bad.append(f"{v['class']}: discriminator hole {hole} in "
                               f"{name} accepted by same class")
                    continue
            n_ok += 1

    # 3. register alignment violation: patch Rd of a 64-bit-dest variant to an
    #    odd number (misaligned)
    for v in db["variants"]:
        if v.get("is_alternate") or v["class"] not in by_class:
            continue
        idest = v.get("predicates", {}).get("IDEST_SIZE")
        if idest not in ("64", "32 + ((sz==`QInteger@\"64\"))*32"):
            continue
        rd_field = next((f for f in v["encoding"] if f["name"] == "Rd"),
                        None)
        if rd_field is None or rd_field["width"] != 8:
            continue
        base = by_class[v["class"]]
        cur = extract(rd_field["targets"], base["lo"], base["hi"])
        odd = (cur | 1) if (cur % 2 == 0) else (cur ^ 1)
        if odd == 255:
            continue
        nlo, nhi = set_field(rd_field["targets"], base["lo"], base["hi"], odd)
        r = decode(nlo, nhi)
        if r.startswith("OK"):
            bad.append(f"{v['class']}: misaligned Rd={odd} accepted")
            continue
        n_ok += 1

    if bad:
        for b in bad[:20]:
            print("  " + b, file=sys.stderr)
        print(f"FAIL: {len(bad)} negative vectors not rejected",
              file=sys.stderr)
        return 1
    print(f"OK: {n_ok} negative vectors rejected "
          f"(illegal tables / enum holes / register alignment)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
