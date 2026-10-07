# sm_120 instruction notes — verification backlog

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** medium  
**Last verified:** unknown  
**Probe:** measured on an RTX 5090  
**Open items:** none  
**Audit:** `tools/notes_audit.py` · basis: hardware named next to a verification verb

## Conclusion

The 105 notes under [`notes/sm120/instr/`](instr/) are **generated** from
`sm120_instructions.txt` (`tools/sm120_notes_gen.py`). Their encodings are therefore
*claimed* by the ISA dump, not proven against a real cubin. This file holds the
program-wide work that would upgrade them from `Evidence: spec` — the per-instruction
notes deliberately do not repeat it 105 times.

Each item below is one piece of work covering **all** affected notes; tick it by doing the
work and recording the result in this file (and, for a tier change, in the note's status
block).

## V1 — decoder round-trip against real cuobjdump vectors

- [ ] For every mnemonic in `notes/sm120/instr/`, extract the opcode and field positions
      from `sm120.json` and decode real `cuobjdump -sass` output byte-exact.
- [ ] The sm_90-side recipe is `AGENTS.md` step 6; `tools/decode_*.py` has 109 worked
      examples and `tools/query_sm120.py layout <class>` prints the bit map to check
      against.
- [ ] Blocked by: nothing (the fixture cubins under `tests/` are committed).
- Affected: all 105 notes. On success, record per-note which decoder covers it.

## V2 — printed form versus the FORMAT-derived rendering

- [ ] The `operands` column of each note's *Variants* table is derived from `FORMAT`, with
      modifier slots marked `[/mod]` and operand types stripped. Confirm the exact
      cuobjdump spelling (modifier order, `.reuse` placement, `desc[UR]` composites) for
      each variant.
- [ ] Blocked by: a real sm_120 cubin per mnemonic; 41 mnemonics have **0** occurrences in
      the committed fixtures (see each note's *On-chip presence*) and need a kernel first.
- Affected: all 105 notes; the zero-presence ones need a new test kernel before this can
  even start.

## V3 — pipe and latency rows

- [ ] `sm120_latencies.txt` gives pipe *membership* only. The per-pipe true/output/anti
      tables have not been transcribed into the notes.
- [ ] Partly done outside this subtree: the measured latency matrices are
      [`alulite_latency.md`](alulite_latency.md), [`aluheavy_latency.md`](aluheavy_latency.md),
      [`fmalite_latency.md`](fmalite_latency.md), [`fmaheavy_latency.md`](fmaheavy_latency.md),
      [`fp16_latency.md`](fp16_latency.md), [`fp64_redirect_latency.md`](fp64_redirect_latency.md),
      and they are mirrored row-for-row into the matching instruction notes.
- [ ] Blocked by: nothing for the measured pipes; the unmeasured pipes need probes.

## V4 — mnemonics with no sm_120 measurement

- [ ] Each note's *sm_120 measurements* section says whether a measurement exists. The
      registry of what has been measured is
      [`measurements_index.md`](measurements_index.md).
- [ ] Blocked by: hardware sessions. Prioritise the mnemonics whose sm_90 behaviour was
      measured on an RTX 5090 but whose sm_120 form changed (the notes say so under
      *sm_90 relationship*).

## V5 — mnemonic-diff follow-up

- [ ] `tools/isa_diff_sm90_sm120.py` reports **20 sm_90-only** mnemonics
      (`BGMMA BMMA GATHER HFMA2.MMA HGMMA IGMMA QGMMA RED SCATTER ULDC VABSDIFF VABSDIFF4
      VHMNMX VIADDMNMX VIMNMX3 WARPGROUP WARPGROUPSET BITEXTRACT GENMETADATA SPMETADATA`)
      and **41 sm_120-only** ones. The 105 notes cover the compute subset; decide explicitly
      for each remaining mnemonic whether it is out of scope (texture/surface/data-mover)
      or a gap.
- [ ] Blocked by: a scope decision, not by hardware.

## What a tier upgrade requires

A note may move from `Evidence: spec` to `Evidence: sm120-silicon` only when a measurement
of *that* mnemonic exists and is linked (V1/V2/V4 above), because the status block is what
readers and `tools/notes_audit.py` trust. Editing the tier without a measurement is the
one change this structure exists to prevent.

