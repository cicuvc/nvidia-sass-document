#!/usr/bin/env python3
# Driver: generate a per-thread word-index pattern, run the harness under ncu,
# parse the shared-memory conflict/wavefront metrics, print one row.
import subprocess, sys, os, csv, io, tempfile

PW = "c785ht8v"
HARNESS = os.path.join(os.path.dirname(__file__), "harness")
BIN = os.environ.get("HARNESS_BIN", HARNESS)
METRICS = ",".join([
    "l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_ld.sum",
    "l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_st.sum",
    "l1tex__data_pipe_lsu_wavefronts_mem_shared_op_ld.sum",
    "l1tex__data_pipe_lsu_wavefronts_mem_shared_op_st.sum",
    "smsp__inst_executed_op_shared_ld.sum",
    "smsp__inst_executed_op_shared_st.sum",
])
SHORT = {
    "l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_ld.sum": "ldC",
    "l1tex__data_bank_conflicts_pipe_lsu_mem_shared_op_st.sum": "stC",
    "l1tex__data_pipe_lsu_wavefronts_mem_shared_op_ld.sum": "ldW",
    "l1tex__data_pipe_lsu_wavefronts_mem_shared_op_st.sum": "stW",
    "smsp__inst_executed_op_shared_ld.sum": "ldI",
    "smsp__inst_executed_op_shared_st.sum": "stI",
}

def pattern(spec):
    """Return list of 32 word indices."""
    if spec == "id":
        return [t for t in range(32)]
    if spec == "bcast":
        return [0]*32
    if spec.startswith("stride:"):
        s = int(spec.split(":")[1]); return [t*s for t in range(32)]
    if spec.startswith("strideoff:"):    # (t*s + phase) style not needed; keep simple
        s = int(spec.split(":")[1]); return [t*s for t in range(32)]
    if spec == "multi_diffbank":     # 2 words, distinct banks, each read by 16 threads
        return [0 if t < 16 else 1 for t in range(32)]
    if spec == "multi_samebank":     # 2 words, SAME bank (0 & 32), each by 16 threads
        return [0 if t < 16 else 32 for t in range(32)]
    if spec == "pair_word_diffbank": # 16 words banks0..15, each read by 2 adjacent threads
        return [t // 2 for t in range(32)]
    if spec == "pair_word_samebank": # 16 words all bank0 (0,32,..,480), each by 2 threads
        return [(t // 2) * 32 for t in range(32)]
    if spec == "half_samebank_diffword":  # words 0 and 32 both bank0, 16 threads each (diff word)
        return [0 if t % 2 == 0 else 32 for t in range(32)]
    if spec == "share31_plus1":      # 31 threads -> word0, 1 thread -> word32 (same bank0)
        return [0]*31 + [32]
    if spec == "asym_max3":          # bank0:{0,32,64}=3distinct, bank1:{1,33}=2, rest distinct
        v = [t for t in range(32)]
        v[0], v[1], v[2] = 0, 32, 64
        v[3], v[4] = 1, 33
        return v
    # --- v2 patterns: value = BASE WORD (even); thread touches [base, base+1] ---
    if spec == "v2_consec":          # e[t]=t  -> fully consecutive 64 words
        return [2*t for t in range(32)]
    if spec == "v2_bcast":           # all threads read words 0,1
        return [0]*32
    if spec.startswith("v2_estride:"):  # element stride S -> base = 2*S*t
        s = int(spec.split(":")[1]); return [2*s*t for t in range(32)]
    if spec == "v2_pairmerge":       # threads t,t^1 share same 8B element (e=t>>1)
        return [2*(t>>1) for t in range(32)]
    if spec == "v2_pairmerge_bank":  # pairs share element, elements strided to same bank
        return [2*((t>>1)*16) for t in range(32)]   # e=(t>>1)*16 -> base=32*(t>>1)
    if spec == "v2_half_lo_hi":      # threads 0-15 -> elems 0..15, 16-31 -> same elems 0..15
        return [2*(t%16) for t in range(32)]
    if spec.startswith("v2_share:"):  # lane t and lane t^k share one 8B element; 16 elems, words 0..31
        k = int(spec.split(":")[1])
        seen = {}; nxt = 0; e = [0]*32
        for t in range(32):
            c = min(t, t ^ k)
            if c not in seen: seen[c] = nxt; nxt += 1
            e[t] = seen[c]
        return [2*x for x in e]
    if spec == "v2_quadshare":       # all 4 lanes of each quad share one element (8 elems, words 0..15)
        return [2*(t//4) for t in range(32)]
    if spec == "v2_octshare":        # all 8 lanes of each oct share one element (4 elems)
        return [2*(t//8) for t in range(32)]
    if spec == "v2_revpair":         # descending contiguous: lane L -> element 15-(L>>1)
        return [2*(15 - (t >> 1)) for t in range(32)]
    if spec == "v2_rotpair":         # ascending contiguous but rotated by 1 element (wraps)
        return [2*(((t >> 1) + 1) % 16) for t in range(32)]
    if spec == "v2_merge_plus_conf": # tid^1-mergeable structure + one genuine 2-way bank conflict
        b = [2*(t >> 1) for t in range(32)]   # pairmerge (would merge -> 1)
        b[30] = b[31] = 32                      # lanes 30,31 -> words32,33 (bank0/1); bank0={0,32} 2-way
        return b
    if spec == "v2_distinguish3":    # H0: 3-way in bank0/1; H1: broadcast 1 elem (banks16/17)
        # whole-warp max = 3 ; half-warp = passes(H0)+passes(H1) = 3+1 = 4
        b = [0]*32
        b[0], b[1], b[2] = 0, 32, 64                 # e=0,16,32 -> bank0 low, bank1 high (3-way)
        clean = [1,2,3,4,5,6,7,9,10,11,12,13,14]     # e values (skip 8 -> avoid bank16/17)
        for i, e in enumerate(clean): b[3+i] = 2*e
        for t in range(16, 32): b[t] = 16            # H1 all -> words 16,17
        return b
    if spec == "v2_distinguish4":    # H0: 4-way in bank0/1; H1: broadcast -> whole=4, half=5
        b = [0]*32
        b[0], b[1], b[2], b[3] = 0, 32, 64, 96       # 4-way bank0/1
        clean = [1,2,3,4,5,6,7,9,10,11]              # 10 lanes, avoid bank16/17 (skip e=8, and 16-mult)
        for i, e in enumerate(clean): b[4+i] = 2*e
        for t in range(16, 32): b[t] = 16
        return b
    if spec == "v2_asym_clean":      # H0 3-way bank0, H1 3-way bank0 too (symmetric) -> whole=6==half=6
        b = [0]*32
        b[0], b[1], b[2] = 0, 32, 64
        for i, e in enumerate([1,2,3,4,5,6,7,9,10,11,12,13,14]): b[3+i] = 2*e
        b[16], b[17], b[18] = 128, 160, 192          # H1 3-way in bank0 (words128,160,192)
        for i, e in enumerate([65,66,67,68,69,70,71,73,74,75,76,77,78]): b[19+i] = 2*e
        return b
    if spec in ("v2_bnd_in", "v2_bnd_cross"):
        # Same 2 distinct words in bank0; H1 is a broadcast (few banks, avoids bank0)
        # so whole!=half. _in: both hot words in H0 (lanes14,15) -> half=3, whole=2.
        # _cross: hot words straddle boundary (lane15 in H0, lane16 in H1) -> half=2, whole=2.
        b = [0]*32
        if spec == "v2_bnd_in":
            for L in range(14): b[L] = 2*(L+1)   # fillers e=1..14 -> banks 2..29
            b[14] = 0; b[15] = 32                 # 2-way bank0 inside H0
            for L in range(16, 32): b[L] = 16     # H1 broadcast -> banks 16,17
        else:  # cross
            for L in range(15): b[L] = 2*(L+1)   # fillers e=1..15 -> banks 2..31
            b[15] = 0                             # H0 bank0 word0
            b[16] = 32                            # H1 bank0 word32 (across boundary)
            for L in range(17, 32): b[L] = 16     # H1 broadcast -> bank16
        return b
    if spec.startswith("custom:"):
        vals = [int(x) for x in spec.split(":")[1].split(",")]
        assert len(vals) == 32, f"custom needs 32 vals, got {len(vals)}"
        return vals
    # --- v4 patterns: value = BASE WORD (mult of 4); thread touches [base..base+3] ---
    if spec == "v4_consec":          # e[t]=t -> 128 consecutive words
        return [4*t for t in range(32)]
    if spec == "v4_bcast":
        return [0]*32
    if spec.startswith("v4_estride:"):
        s = int(spec.split(":")[1]); return [4*s*t for t in range(32)]
    if spec == "v4_pairshare":       # lanes t,t^1 share one 16B element (÷2 blocks)
        return [4*(t>>1) for t in range(32)]
    if spec == "v4_quadshare":       # lanes in each quad share one element (÷4)
        return [4*(t>>2) for t in range(32)]
    if spec == "v4_octshare":        # lanes in each oct share one element (÷8)
        return [4*(t>>3) for t in range(32)]
    if spec.startswith("v4_share:"):  # lanes t,t^k share one element; 16 elems words 0..63 (4/lane pair)
        k = int(spec.split(":")[1])
        seen = {}; nxt = 0; e = [0]*32
        for t in range(32):
            c = min(t, t ^ k)
            if c not in seen: seen[c] = nxt; nxt += 1
            e[t] = seen[c]
        return [4*x for x in e]
    if spec == "v4_dist_q0":         # 2-way conflict inside Q0 (lanes0-7); rest broadcast-ish clean
        # quarter model: passes(Q0)=2, others 1 => 5 ; half model would give less
        b = [0]*32
        for L in range(8): b[L] = 4*(L+1)         # Q0 fillers e=1..8 -> banks spread
        b[0] = 0; b[1] = 128                        # two words in bank0 (word0, word128) inside Q0
        for L in range(8, 32): b[L] = 16            # Q1..Q3 broadcast one element (bank16..19)
        return b
    if spec in ("v4_bnd_in", "v4_bnd_cross"):
        # Two distinct words in bank0; other quarters broadcast to banks28-31 (avoid bank0).
        # _in: both hot words in Q0 (lanes6,7)   -> quarter=5, half=3, whole=2.
        # _cross: hot words straddle Q0|Q1 (7,8)  -> quarter=4, half=3, whole=2.
        b = [0]*32
        for L in range(24, 32): b[L] = 28            # Q3 broadcast -> banks28-31
        if spec == "v4_bnd_in":
            for L in range(6): b[L] = 4*(L+1)        # Q0 fillers e=1..6 -> banks4..27
            b[6] = 0; b[7] = 128                       # 2 distinct words in bank0, both in Q0
            for L in range(8, 24): b[L] = 28           # Q1,Q2 broadcast -> banks28-31
        else:  # cross
            for L in range(7): b[L] = 4*(L+1)        # Q0 fillers e=1..7 -> banks4..31
            b[7] = 0                                   # Q0 bank0 word0
            b[8] = 128                                 # Q1 bank0 word128 (across 7|8 boundary)
            for L in range(9, 24): b[L] = 28           # Q1(rest),Q2 broadcast -> banks28-31
        return b
    raise SystemExit("unknown pattern " + spec)

def run(mode, pat):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as tf:
        tf.write(" ".join(map(str, pat)))
        pf = tf.name
    cmd = ["sudo", "-S", "/usr/local/cuda/bin/ncu", "--csv", "--metrics", METRICS,
           "-c", "1", BIN, mode, pf]
    out = subprocess.run(cmd, input=PW+"\n", capture_output=True, text=True)
    os.unlink(pf)
    # parse CSV: find the header line with "Metric Name"
    txt = out.stdout
    vals = {}
    rdr = csv.reader(io.StringIO(txt))
    rows = [r for r in rdr if r]
    hdr = None; body = []
    for i, r in enumerate(rows):
        if "Metric Name" in r:
            hdr = r; body = rows[i+1:]; break
    if hdr is None:
        print("PARSE FAIL for", mode, pat, file=sys.stderr)
        print(txt[-800:], file=sys.stderr)
        return None
    mi = hdr.index("Metric Name"); vi = hdr.index("Metric Value")
    for r in body:
        if len(r) > max(mi, vi) and r[mi] in SHORT:
            vals[SHORT[r[mi]]] = r[vi]
    return vals

def analyze_v2(bases):
    """v2: lane touches words [b, b+1]. Return (whole_warp_passes, half_warp_passes)."""
    from collections import defaultdict
    words = [(b, b + 1) for b in bases]
    def passes(lanes):
        bw = defaultdict(set)
        for L in lanes:
            for w in words[L]:
                bw[w % 32].add(w)
        return max((len(s) for s in bw.values()), default=0)
    whole = passes(range(32))
    half = passes(range(0, 16)) + passes(range(16, 32))
    return whole, half

def analyze_v4(bases):
    """v4: lane touches words [b..b+3]. Return (whole, half, quarter) passes."""
    from collections import defaultdict
    words = [tuple(b + i for i in range(4)) for b in bases]
    def passes(lanes):
        bw = defaultdict(set)
        for L in lanes:
            for w in words[L]:
                bw[w % 32].add(w)
        return max((len(s) for s in bw.values()), default=0)
    whole = passes(range(32))
    half = sum(passes(range(h, h+16)) for h in (0, 16))
    quarter = sum(passes(range(q, q+8)) for q in (0, 8, 16, 24))
    return whole, half, quarter

def main():
    tests = sys.argv[1:] or ["id", "bcast", "stride:2", "stride:4", "stride:32", "stride:33"]
    is_v2 = "v2" in os.path.basename(BIN)
    is_v4 = "v4" in os.path.basename(BIN)
    hdr = f"{'pattern':<20} {'mode':<3} {'ldI':>4} {'ldW':>4} {'ldC':>4} {'stI':>4} {'stW':>4} {'stC':>4}"
    if is_v2: hdr += f"  {'pWhole':>6} {'pHalf':>6}"
    if is_v4: hdr += f"  {'pWhl':>4} {'pHlf':>4} {'pQtr':>4}"
    print(hdr)
    for spec in tests:
        pat = pattern(spec)
        pw = ph = pq = None
        if is_v2: pw, ph = analyze_v2(pat)
        if is_v4: pw, ph, pq = analyze_v4(pat)
        for mode in ("ld", "st"):
            v = run(mode, pat)
            if v is None: continue
            line = f"{spec:<20} {mode:<3} {v.get('ldI',''):>4} {v.get('ldW',''):>4} {v.get('ldC',''):>4} {v.get('stI',''):>4} {v.get('stW',''):>4} {v.get('stC',''):>4}"
            if is_v2: line += f"  {pw:>6} {ph:>6}"
            if is_v4: line += f"  {pw:>4} {ph:>4} {pq:>4}"
            print(line)

if __name__ == "__main__":
    main()
