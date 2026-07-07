# Tensor-core microarchitecture — dot-product vs systolic (SPECULATION)

**Status: SPECULATION / architectural inference.** Nothing here is provable from
the SASS/ISA dumps — the wgmma/mma ISA is dataflow-agnostic (tile shape, async
semantics, and the accumulator-collector behaviour do not expose whether the
multiply-add fabric is a systolic array or a dot-product/FMA tree). This records
a reasoned position and the indirect evidence, for future refinement.

## Question
Did Hopper's tensor core use a **systolic array**, or the pre-Hopper
**dot-product / 4-way-fused-FMA tree** (which fuses several low-precision
multiplies into one high-precision accumulate, eliminating per-multiply
renormalization — cheap because low-precision FP multiply is cheap)?

Premises taken as given (from external RE, not verified here):
- Pre-Hopper (Volta/Turing/Ampere, wmma/mma.sync) tensor cores are **not**
  systolic — 4-way-fused-FMA dot-product engines. Corroborated by 2:4 structured
  sparsity being natural in a dot-product engine (edge input selection).
- Blackwell allegedly **introduced a systolic array**, each PE taking two groups
  of 4 packed operands/cycle (reusing the 4-way-FMA as the PE), which also
  motivates explicit **Tensor Memory** to hold partial sums streamed out of the
  array.

## Position: Hopper is most likely NOT systolic
Hopper (4th-gen tensor core) reads as an Ampere-lineage dot-product/FMA-tree,
**widened to warpgroup scale and made asynchronous** (wgmma, TMA/mbarrier-fed),
not a datapath-paradigm change.

### Indirect evidence (from this repo's findings)
1. **Retained 2:4 structured sparsity.** The spec has sparse wgmma variants
   (`hgmma_sparse_Ra_URb_Rc_`, …). Structured sparsity is natural in a
   dot-product engine (2-of-4 input muxing), awkward in a rigid systolic
   dataflow. Hopper doing it the Ampere way ⇒ same datapath lineage. *(Suggestive,
   not exclusive: an array can mux at its edge.)*
2. **Small fixed per-instruction K (16 for fp16, 32 for fp8).** The reduction
   depth per wgmma is small and fixed; real accumulation is **explicit across
   instructions** (the K-loop + the internal accumulator collector we measured in
   `notes/wgmma.md`). That matches "compute a depth-16 dot product, add to
   accumulator" (FMA tree), not a deep systolic reduction pipeline.
3. **Per-subcore 16-row partitioning.** `notes/wgmma.md`: each of the 4 subcores
   has its own tensor unit computing 16 of the 64 rows — a widened per-subcore
   Ampere unit, not one SM-wide array.
4. **implicit-collector → explicit-TMEM world-jump to Blackwell.** `notes/wgmma.md`
   (Hopper keeps the accumulator inside the tensor core, register-named,
   drain-on-read) vs `notes/tcgen05_vs_wgmma.md` (Blackwell externalises it to
   addressable Tensor Memory). A systolic array streams partial sums out and
   needs explicit accumulate storage — so **if** Blackwell went systolic, TMEM is
   exactly the expected companion change. This makes Hopper's implicit
   read-C/compute-A·B/add/write-D semantics look like the older dot-product+
   accumulator model. *(Strongest circumstantial link, together with #1.)*
5. **NVIDIA's own generation framing.** Hopper = incremental 4th-gen over Ampere;
   Blackwell = 5th-gen with a new datapath (tcgen05, TMEM, single-thread issue).
   A paradigm shift to systolic fits Blackwell's positioning, not Hopper's.

### Caveats / what does NOT distinguish
- The internal-collector behaviour (`notes/wgmma.md`) is **equally consistent**
  with a systolic array holding partial sums — it is not a discriminator.
- 2:4 sparsity is implementable in a systolic array with edge muxes, so #1 is
  suggestive, not conclusive.
- The ISA cannot reveal the fabric; all of the above is inference + vendor
  positioning, not proof.

## Possible (likely inconclusive) probe
Microbenchmark single-wgmma dependent-chain **latency vs N** for
`m64n{8,16,…,256}k16` on the H800: a systolic array shows a fill/drain latency
roughly linear in the array dimension while steady-state throughput saturates.
Caveat: async issue + the GMMA-scoreboard-hidden completion would mask fill/drain,
and a wider N also costs more passes in a dot-product tree — so a latency-vs-N
slope would not cleanly separate the two hypotheses.

## Bottom line
Best guess: **Hopper = widened, asynchronous dot-product/4-way-FMA (Ampere
lineage); systolic array (if real) is a Blackwell introduction, with TMEM as its
partial-sum store.** Confidence: moderate, evidence-based but not provable from
SASS. The two mutually-reinforcing pillars are the retained 2:4 sparsity and the
implicit-collector→TMEM transition.

## Cross-refs
`notes/wgmma.md` (collector model, subcore partitioning, sparse variants),
`notes/hmma_pipeline.md` (latency), `notes/tcgen05_vs_wgmma.md` (TMEM).
