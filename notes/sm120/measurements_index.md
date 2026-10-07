# sm_120 measurements — where the numbers are

**Architecture:** RTX 5090 / GB202 (sm_120) unless a row says otherwise.  Compiled by
`tools/sm120_measurements_index.py`; this is an **index**, not a copy — each row points
at the note that produced the number.  Duplicating measurements is what made the notes
ambiguous to begin with, so read the source note before quoting a figure.

Notes carrying sm_120 silicon evidence: **212**.
The per-instruction sm_120 notes link back here; see also
[`notes/sm120/index.md`](index.md) for the architecture notes.

<!-- generated:measurements-index:begin -->
## Per-instruction measurements

| instruction | sm_120 note | where the numbers live |
|---|---|---|
| `ACQBULK` | - | [`sm90/instr/acqbulk.md`](../sm90/instr/acqbulk.md) |
| `ACQSHMINIT` | `instr/acqshminit.md` | [`sm100/instr/acqshminit.md`](../sm100/instr/acqshminit.md) |
| `ARRIVES` | - | [`sm90/instr/arrives.md`](../sm90/instr/arrives.md) |
| `ATOM` | - | [`sm90/instr/atom.md`](../sm90/instr/atom.md) |
| `ATOMG` | - | [`sm90/instr/atomg.md`](../sm90/instr/atomg.md) |
| `ATOMS` | `instr/atoms.md` | [`sm90/instr/atoms.md`](../sm90/instr/atoms.md) |
| `B2R` | - | [`sm90/instr/b2r.md`](../sm90/instr/b2r.md) |
| `BGMMA` | - | [`sm90/instr/bgmma.md`](../sm90/instr/bgmma.md) |
| `BMMA` | - | [`sm90/instr/bmma.md`](../sm90/instr/bmma.md) |
| `BMOV` | `instr/bmov.md` | [`sm90/instr/bmov.md`](../sm90/instr/bmov.md) |
| `BMSK` | `instr/bmsk.md` | [`sm90/instr/bmsk.md`](../sm90/instr/bmsk.md) |
| `BPT` | - | [`sm90/instr/bpt.md`](../sm90/instr/bpt.md) |
| `BRA` | - | [`sm90/instr/bra.md`](../sm90/instr/bra.md) |
| `BREAK` | `instr/break.md` | [`sm90/instr/break.md`](../sm90/instr/break.md) |
| `BREV` | `instr/brev.md` | [`sm90/instr/brev.md`](../sm90/instr/brev.md) |
| `BRX` | - | [`sm90/instr/brx.md`](../sm90/instr/brx.md) |
| `BRXU` | - | [`sm90/instr/brxu.md`](../sm90/instr/brxu.md) |
| `BSSY` | `instr/bssy.md` | [`sm90/instr/bssy.md`](../sm90/instr/bssy.md) |
| `BSYNC` | `instr/bsync.md` | [`sm90/instr/bsync.md`](../sm90/instr/bsync.md) |
| `CALL` | `instr/call.md` | [`sm90/instr/call.md`](../sm90/instr/call.md) |
| `CCTL` | `instr/cctl.md` | [`sm90/instr/cctl.md`](../sm90/instr/cctl.md) |
| `CCTLL` | - | [`sm90/instr/cctll.md`](../sm90/instr/cctll.md) |
| `CGAERRBAR` | - | [`sm90/instr/cgaerrbar.md`](../sm90/instr/cgaerrbar.md) |
| `CLMAD` | `instr/clmad.md` | [`sm90/instr/clmad.md`](../sm90/instr/clmad.md) |
| `CS2R` | - | [`sm90/instr/cs2r.md`](../sm90/instr/cs2r.md) |
| `DADD` | `instr/dadd.md` | [`sm90/instr/dadd.md`](../sm90/instr/dadd.md) |
| `DEPBAR` | - | [`sm90/instr/depbar.md`](../sm90/instr/depbar.md) |
| `DMMA` | - | [`sm90/instr/dmma.md`](../sm90/instr/dmma.md) |
| `DMUL` | `instr/dmul.md` | [`sm90/instr/dmul.md`](../sm90/instr/dmul.md) |
| `DSETP` | `instr/dsetp.md` | [`sm90/instr/dsetp.md`](../sm90/instr/dsetp.md) |
| `ELECT` | - | [`sm90/instr/elect.md`](../sm90/instr/elect.md) |
| `ENDCOLLECTIVE` | - | [`sm90/instr/endcollective.md`](../sm90/instr/endcollective.md) |
| `ERRBAR` | - | [`sm90/instr/errbar.md`](../sm90/instr/errbar.md) |
| `EXIT` | - | [`sm90/instr/exit.md`](../sm90/instr/exit.md) |
| `F2F` | `instr/f2f.md` | [`sm90/instr/f2f.md`](../sm90/instr/f2f.md) |
| `F2FP` | `instr/f2fp.md` | [`sm90/instr/f2fp.md`](../sm90/instr/f2fp.md) |
| `F2I` | `instr/f2i.md` | [`sm90/instr/f2i.md`](../sm90/instr/f2i.md) |
| `F2IP` | `instr/f2ip.md` | [`sm90/instr/f2ip.md`](../sm90/instr/f2ip.md) |
| `FADD` | `instr/fadd.md` | [`sm90/instr/fadd.md`](../sm90/instr/fadd.md) |
| `FCHK` | `instr/fchk.md` | [`sm90/instr/fchk.md`](../sm90/instr/fchk.md) |
| `FENCE` | - | [`sm90/instr/fence.md`](../sm90/instr/fence.md) |
| `FFMA` | `instr/ffma.md` | [`sm90/instr/ffma.md`](../sm90/instr/ffma.md) |
| `FLO` | `instr/flo.md` | [`sm90/instr/flo.md`](../sm90/instr/flo.md) |
| `FMNMX` | `instr/fmnmx.md` | [`sm90/instr/fmnmx.md`](../sm90/instr/fmnmx.md) |
| `FMUL` | `instr/fmul.md` | [`sm90/instr/fmul.md`](../sm90/instr/fmul.md) |
| `FRND` | `instr/frnd.md` | [`sm90/instr/frnd.md`](../sm90/instr/frnd.md) |
| `FSEL` | `instr/fsel.md` | [`sm90/instr/fsel.md`](../sm90/instr/fsel.md) |
| `FSET` | `instr/fset.md` | [`sm90/instr/fset.md`](../sm90/instr/fset.md) |
| `FSETP` | `instr/fsetp.md` | [`sm90/instr/fsetp.md`](../sm90/instr/fsetp.md) |
| `FSWZADD` | - | [`sm90/instr/fswzadd.md`](../sm90/instr/fswzadd.md) |
| `GATHER` | - | [`sm90/instr/gather.md`](../sm90/instr/gather.md) |
| `GETLMEMBASE` | `instr/getlmembase.md` | [`sm120/instr/getlmembase.md`](../sm120/instr/getlmembase.md) |
| `HADD2` | `instr/hadd2.md` | [`sm90/instr/hadd2.md`](../sm90/instr/hadd2.md) |
| `HFMA2` | `instr/hfma2.md` | [`sm90/instr/hfma2.md`](../sm90/instr/hfma2.md) |
| `HGMMA` | - | [`sm90/instr/hgmma.md`](../sm90/instr/hgmma.md) |
| `HMMA` | - | [`sm90/instr/hmma.md`](../sm90/instr/hmma.md) |
| `HMNMX2` | `instr/hmnmx2.md` | [`sm90/instr/hmnmx2.md`](../sm90/instr/hmnmx2.md) |
| `HMUL2` | `instr/hmul2.md` | [`sm90/instr/hmul2.md`](../sm90/instr/hmul2.md) |
| `HSET2` | `instr/hset2.md` | [`sm90/instr/hset2.md`](../sm90/instr/hset2.md) |
| `HSETP2` | `instr/hsetp2.md` | [`sm90/instr/hsetp2.md`](../sm90/instr/hsetp2.md) |
| `I2F` | `instr/i2f.md` | [`sm90/instr/i2f.md`](../sm90/instr/i2f.md) |
| `I2FP` | `instr/i2fp.md` | [`sm90/instr/i2fp.md`](../sm90/instr/i2fp.md) |
| `I2I` | `instr/i2i.md` | [`sm90/instr/i2i.md`](../sm90/instr/i2i.md) |
| `I2IP` | `instr/i2ip.md` | [`sm90/instr/i2ip.md`](../sm90/instr/i2ip.md) |
| `IABS` | `instr/iabs.md` | [`sm90/instr/iabs.md`](../sm90/instr/iabs.md) |
| `IADD3` | `instr/iadd3.md` | [`sm90/instr/iadd3.md`](../sm90/instr/iadd3.md) |
| `IDE` | - | [`sm90/instr/ide.md`](../sm90/instr/ide.md) |
| `IDP` | `instr/idp.md` | [`sm90/instr/idp.md`](../sm90/instr/idp.md) |
| `IGMMA` | - | [`sm90/instr/igmma.md`](../sm90/instr/igmma.md) |
| `IMAD` | `instr/imad.md` | [`sm90/instr/imad.md`](../sm90/instr/imad.md) |
| `IMMA` | - | [`sm90/instr/imma.md`](../sm90/instr/imma.md) |
| `IMNMX` | `instr/imnmx.md` | [`sm90/instr/imnmx.md`](../sm90/instr/imnmx.md) |
| `ISETP` | `instr/isetp.md` | [`sm90/instr/isetp.md`](../sm90/instr/isetp.md) |
| `JMP` | `instr/jmp.md` | [`sm90/instr/jmp.md`](../sm90/instr/jmp.md) |
| `JMX` | - | [`sm90/instr/jmx.md`](../sm90/instr/jmx.md) |
| `JMXU` | - | [`sm90/instr/jmxu.md`](../sm90/instr/jmxu.md) |
| `KILL` | - | [`sm90/instr/kill.md`](../sm90/instr/kill.md) |
| `LD` | - | [`sm90/instr/ld.md`](../sm90/instr/ld.md) |
| `LDG` | `instr/ldg.md` | [`sm90/instr/ldg.md`](../sm90/instr/ldg.md) |
| `LDGSTS` | - | [`sm90/instr/ldgsts.md`](../sm90/instr/ldgsts.md) |
| `LDL` | - | [`sm90/instr/ldl.md`](../sm90/instr/ldl.md) |
| `LDS` | - | [`sm90/instr/lds.md`](../sm90/instr/lds.md) |
| `LDSM` | - | [`sm90/instr/ldsm.md`](../sm90/instr/ldsm.md) |
| `LEA` | `instr/lea.md` | [`sm90/instr/lea.md`](../sm90/instr/lea.md) |
| `LEPC` | - | [`sm90/instr/lepc.md`](../sm90/instr/lepc.md) |
| `LOP3` | `instr/lop3.md` | [`sm90/instr/lop3.md`](../sm90/instr/lop3.md) |
| `MATCH` | - | [`sm90/instr/match.md`](../sm90/instr/match.md) |
| `MEMBAR` | - | [`sm90/instr/membar.md`](../sm90/instr/membar.md) |
| `MOV` | `instr/mov.md` | [`sm90/instr/mov.md`](../sm90/instr/mov.md) |
| `MOVM` | - | [`sm90/instr/movm.md`](../sm90/instr/movm.md) |
| `MUFU` | `instr/mufu.md` | [`sm90/instr/mufu.md`](../sm90/instr/mufu.md) |
| `NANOSLEEP` | `instr/nanosleep.md` | [`sm90/instr/nanosleep.md`](../sm90/instr/nanosleep.md) |
| `NANOTRAP` | `instr/nanotrap.md` | [`sm90/instr/nanotrap.md`](../sm90/instr/nanotrap.md) |
| `NOP` | - | [`sm90/instr/nop.md`](../sm90/instr/nop.md) |
| `P2R` | `instr/p2r.md` | [`sm90/instr/p2r.md`](../sm90/instr/p2r.md) |
| `PLOP3` | `instr/plop3.md` | [`sm90/instr/plop3.md`](../sm90/instr/plop3.md) |
| `PMTRIG` | - | [`sm90/instr/pmtrig.md`](../sm90/instr/pmtrig.md) |
| `POPC` | `instr/popc.md` | [`sm90/instr/popc.md`](../sm90/instr/popc.md) |
| `PREEXIT` | - | [`sm90/instr/preexit.md`](../sm90/instr/preexit.md) |
| `PRMT` | `instr/prmt.md` | [`sm90/instr/prmt.md`](../sm90/instr/prmt.md) |
| `QSPC` | - | [`sm90/instr/qspc.md`](../sm90/instr/qspc.md) |
| `R2B` | - | [`sm90/instr/r2b.md`](../sm90/instr/r2b.md) |
| `R2P` | `instr/r2p.md` | [`sm90/instr/r2p.md`](../sm90/instr/r2p.md) |
| `R2UR` | - | [`sm90/instr/r2ur.md`](../sm90/instr/r2ur.md) |
| `RED` | - | [`sm90/instr/red.md`](../sm90/instr/red.md) |
| `REDAS` | - | [`sm90/instr/redas.md`](../sm90/instr/redas.md) |
| `REDUX` | - | [`sm90/instr/redux.md`](../sm90/instr/redux.md) |
| `RET` | - | [`sm90/instr/ret.md`](../sm90/instr/ret.md) |
| `S2R` | - | [`sm90/instr/s2r.md`](../sm90/instr/s2r.md) |
| `S2UR` | - | [`sm90/instr/s2ur.md`](../sm90/instr/s2ur.md) |
| `SCATTER` | - | [`sm90/instr/scatter.md`](../sm90/instr/scatter.md) |
| `SEL` | `instr/sel.md` | [`sm90/instr/sel.md`](../sm90/instr/sel.md) |
| `SETCTAID` | - | [`sm90/instr/setctaid.md`](../sm90/instr/setctaid.md) |
| `SETLMEMBASE` | `instr/setlmembase.md` | [`sm120/instr/setlmembase.md`](../sm120/instr/setlmembase.md) |
| `SETMAXREG` | - | [`sm90/instr/setmaxreg.md`](../sm90/instr/setmaxreg.md) |
| `SGXT` | `instr/sgxt.md` | [`sm90/instr/sgxt.md`](../sm90/instr/sgxt.md) |
| `SHF` | `instr/shf.md` | [`sm90/instr/shf.md`](../sm90/instr/shf.md) |
| `SHFL` | - | [`sm90/instr/shfl.md`](../sm90/instr/shfl.md) |
| `ST` | - | [`sm90/instr/st.md`](../sm90/instr/st.md) |
| `STAS` | - | [`sm90/instr/stas.md`](../sm90/instr/stas.md) |
| `STG` | `instr/stg.md` | [`sm90/instr/stg.md`](../sm90/instr/stg.md) |
| `STL` | - | [`sm90/instr/stl.md`](../sm90/instr/stl.md) |
| `STSM` | - | [`sm90/instr/stsm.md`](../sm90/instr/stsm.md) |
| `SYNCS` | `instr/syncs.md` | [`sm90/instr/syncs.md`](../sm90/instr/syncs.md) |
| `UBLKCP` | `instr/ublkcp.md` | [`sm90/instr/ublkcp.md`](../sm90/instr/ublkcp.md) |
| `UBLKPF` | - | [`sm90/instr/ublkpf.md`](../sm90/instr/ublkpf.md) |
| `UBLKRED` | `instr/ublkred.md` | [`sm90/instr/ublkred.md`](../sm90/instr/ublkred.md) |
| `UBMSK` | - | [`sm90/instr/ubmsk.md`](../sm90/instr/ubmsk.md) |
| `UBREV` | - | [`sm90/instr/ubrev.md`](../sm90/instr/ubrev.md) |
| `UCGABAR_ARV` | - | [`sm90/instr/ucgabar_arv.md`](../sm90/instr/ucgabar_arv.md) |
| `UCGABAR_GET` | - | [`sm90/instr/ucgabar_get.md`](../sm90/instr/ucgabar_get.md) |
| `UCGABAR_SET` | - | [`sm90/instr/ucgabar_set.md`](../sm90/instr/ucgabar_set.md) |
| `UF2FP` | - | [`sm90/instr/uf2fp.md`](../sm90/instr/uf2fp.md) |
| `UFLO` | - | [`sm90/instr/uflo.md`](../sm90/instr/uflo.md) |
| `UIADD3` | - | [`sm90/instr/uiadd3.md`](../sm90/instr/uiadd3.md) |
| `UIMAD` | `instr/uimad.md` | [`sm90/instr/uimad.md`](../sm90/instr/uimad.md) |
| `UISETP` | - | [`sm90/instr/uisetp.md`](../sm90/instr/uisetp.md) |
| `ULDC` | - | [`sm90/instr/uldc.md`](../sm90/instr/uldc.md) |
| `ULEA` | - | [`sm90/instr/ulea.md`](../sm90/instr/ulea.md) |
| `ULEPC` | - | [`sm90/instr/ulepc.md`](../sm90/instr/ulepc.md) |
| `ULOP3` | - | [`sm90/instr/ulop3.md`](../sm90/instr/ulop3.md) |
| `UMOV` | `instr/umov.md` | [`sm90/instr/umov.md`](../sm90/instr/umov.md) |
| `UP2UR` | - | [`sm90/instr/up2ur.md`](../sm90/instr/up2ur.md) |
| `UPLOP3` | - | [`sm90/instr/uplop3.md`](../sm90/instr/uplop3.md) |
| `UPOPC` | - | [`sm90/instr/upopc.md`](../sm90/instr/upopc.md) |
| `UPRMT` | - | [`sm90/instr/uprmt.md`](../sm90/instr/uprmt.md) |
| `USEL` | `instr/usel.md` | [`sm90/instr/usel.md`](../sm90/instr/usel.md) |
| `USETSHMSZ` | - | [`sm90/instr/usetshmsz.md`](../sm90/instr/usetshmsz.md) |
| `USGXT` | - | [`sm90/instr/usgxt.md`](../sm90/instr/usgxt.md) |
| `USHF` | - | [`sm90/instr/ushf.md`](../sm90/instr/ushf.md) |
| `UTMACCTL` | `instr/utmacctl.md` | [`sm90/instr/utmacctl.md`](../sm90/instr/utmacctl.md) |
| `UTMACMDFLUSH` | - | [`sm90/instr/utmacmdflush.md`](../sm90/instr/utmacmdflush.md) |
| `UTMALDG` | - | [`sm90/instr/utmaldg.md`](../sm90/instr/utmaldg.md) |
| `UTMAPF` | - | [`sm90/instr/utmapf.md`](../sm90/instr/utmapf.md) |
| `UTMAREDG` | - | [`sm90/instr/utmaredg.md`](../sm90/instr/utmaredg.md) |
| `UTMASTG` | - | [`sm90/instr/utmastg.md`](../sm90/instr/utmastg.md) |
| `VABSDIFF` | - | [`sm90/instr/vabsdiff.md`](../sm90/instr/vabsdiff.md) |
| `VHMNMX` | - | [`sm90/instr/vhmnmx.md`](../sm90/instr/vhmnmx.md) |
| `VIADD` | `instr/viadd.md` | [`sm90/instr/viadd.md`](../sm90/instr/viadd.md) |
| `VIADDMNMX` | - | [`sm90/instr/viaddmnmx.md`](../sm90/instr/viaddmnmx.md) |
| `VIMNMX` | `instr/vimnmx.md` | [`sm90/instr/vimnmx.md`](../sm90/instr/vimnmx.md) |
| `VOTE` | - | [`sm90/instr/vote.md`](../sm90/instr/vote.md) |
| `VOTEU` | - | [`sm90/instr/voteu.md`](../sm90/instr/voteu.md) |
| `WARPSYNC` | - | [`sm90/instr/warpsync.md`](../sm90/instr/warpsync.md) |

## Measurements recorded under `notes/other`

| note | evidence | open items | what it holds |
|---|---|---:|---|
| `CUBIN_STRUCTURE.md` | sm90+sm120-silicon | 0 | - |
| `DEVICE_PRINT.md` | sm120-silicon | 0 | Test environment |
| `sm100/instr/acqshminit.md` | sm120-silicon | 1 | - |

## Measurements recorded under `notes/sm120`

| note | evidence | open items | what it holds |
|---|---|---:|---|
| `sm120/adu_topology.md` | sm120-silicon | 0 | Probe entry points |
| `sm120/aluheavy_latency.md` | sm120-silicon | 0 | GPR result matrix; Predicate result matrix |
| `sm120/alulite_latency.md` | sm120-silicon | 0 | Method |
| `sm120/arch/local_memory_backing_va.md` | sm120-silicon | 1 | Result; Concrete values from the probe |
| `sm120/arch/shared_memory_allocator.md` | sm120-silicon | 0 | Result; Measurement discipline |
| `sm120/cbu_topology.md` | sm120-silicon | 0 | Probe entry points |
| `sm120/encoding-addressing.md` | sm120-silicon | 1 | - |
| `sm120/fixed_admission_depth.md` | sm120-silicon | 0 | Mixed-leaf matrix |
| `sm120/fixed_pipeline_forwarding_latency_zh.md` | sm120-silicon | 0 | 6.1 普通 32-bit result |
| `sm120/fixed_pipeline_issue_to_use_zh.md` | sm120-silicon | 0 | - |
| `sm120/fixed_pipeline_latency_handoff_zh.md` | sm120-silicon | 0 | - |
| `sm120/fmaheavy_latency.md` | sm120-silicon | 0 | Ordinary 32-bit result |
| `sm120/fmalite_latency.md` | sm120-silicon | 0 | Scalar FP16/BF16 result has two observable representations |
| `sm120/fp16_latency.md` | sm120-silicon | 0 | - |
| `sm120/fp64_redirect_latency.md` | sm120-silicon | 0 | Cross-check: LSU and XU admission on GB202 (same burst metho |
| `sm120/gb202_compute_pipelines.md` | sm120-silicon | 0 | Effective bandwidth of the fixed-result bypass; Corrected scalar short-burst depth probe (2026-09-21) |
| `sm120/icache_topology.md` | sm120-silicon | 0 | Probe construction; Tag identity: GPU-VMM alias experiment |
| `sm120/indexed_rf_topology.md` | sm120-silicon | 0 | - |
| `sm120/instr/getlmembase.md` | sm120-silicon | 0 | Boundaries of the result |
| `sm120/instr/setlmembase.md` | sm120-silicon | 0 | Correction to the earlier probe |
| `sm120/l2_slice_probe.md` | sm120-silicon | 0 | Why it fails (the finding); Incidental finding worth keeping |
| `sm120/mio_lsu_xu_topology.md` | sm120-silicon | 0 | A late collector can consume a fixed-pipe result before RF c |
| `sm120/rf_writeback_conflict.md` | sm120-silicon | 0 | Sustained issue/backpressure result; Decisive same-bank result |
| `sm120/scalar_math_pipe_catalog.md` | sm120-silicon | 0 | Scope and method |
| `sm120/subcore_compute_conflict.md` | sm120-silicon | 0 | Preliminary naked-run matrix; Tensor operand and result connection to the RF |
| `sm120/udp_urf_topology.md` | sm120-silicon | 0 | - |
| `sm120/yield_dispatch_cost.md` | sm120-silicon | 0 | - |

## Measurements recorded under `notes/sm90`

| note | evidence | open items | what it holds |
|---|---|---:|---|
| `sm90/arch/async_proxy.md` | sm120-silicon | 1 | - |
| `sm90/arch/cache_descriptor.md` | sm120-silicon | 1 | - |
| `sm90/arch/cbu_state.md` | sm120-silicon | 0 | - |
| `sm90/arch/cubin_elf.md` | sm120-silicon | 0 | - |
| `sm90/arch/cutensormap.md` | sm120-silicon | 1 | - |
| `sm90/arch/div.md` | sm120-silicon | 0 | - |
| `sm90/arch/encoding_classification.md` | sm120-silicon | 0 | - |
| `sm90/arch/hmma_fda_model.md` | sm120-silicon | 1 | - |
| `sm90/arch/hmma_pipeline.md` | sm120-silicon | 1 | - |
| `sm90/arch/ldc_admode.md` | sm120-silicon | 1 | - |
| `sm90/arch/lsu_mio_structure.md` | sm120-silicon | 1 | - |
| `sm90/arch/memory_order_cta.md` | sm120-silicon | 1 | Result table — global (L1); Structural probe — store-own / load-peer, forwarding exclude; atom (global .add) — order × scope matrix |
| `sm90/arch/pipe_forward_survey.md` | sm120-silicon | 1 | Measured matrix (27 edges, all deterministic; spec = sm120 T |
| `sm90/arch/pipe_forwarding.md` | sm120-silicon | 1 | Method — value-based stale/fresh boundary sweep; GPR-domain: int_pipe / fmalighter_pipe (same method); cbu_pipe: int→cbu via NANOSLEEP (same method, timing-observe |
| `sm90/arch/ptx_memory_model_to_sass.md` | sm90+sm120-silicon | 0 | - |
| `sm90/arch/scoreboards.md` | sm120-silicon | 1 | - |
| `sm90/arch/shared_bank_conflicts.md` | sm120-silicon | 1 | Key result: STS same-address does NOT conflict; 4.6 Structured sweep tables (all exact vs model) |
| `sm90/arch/sm_memory_microarch_synthesis.md` | sm120-silicon | 0 | - |
| `sm90/arch/subcore_scheduler.md` | sm120-silicon | 1 | Method — per-warp yield asymmetry; Reproduce |
| `sm90/arch/tcgen05_vs_wgmma.md` | sm120-silicon | 0 | - |
| `sm90/arch/tma_mbarrier.md` | sm120-silicon | 1 | - |
| `sm90/instr/acqbulk.md` | sm120-silicon | 1 | - |
| `sm90/instr/arrives.md` | sm120-silicon | 1 | - |
| `sm90/instr/atom.md` | sm90+sm120-silicon | 0 | - |
| `sm90/instr/atomg.md` | sm120-silicon | 0 | - |
| `sm90/instr/atoms.md` | sm120-silicon | 1 | - |
| `sm90/instr/b2r.md` | sm120-silicon | 1 | - |
| `sm90/instr/bgmma.md` | sm120-silicon | 0 | - |
| `sm90/instr/bmma.md` | sm120-silicon | 0 | Matrix size (`size`) — 2-bit at [76:75] |
| `sm90/instr/bmov.md` | sm120-silicon | 1 | - |
| `sm90/instr/bmsk.md` | sm120-silicon | 0 | - |
| `sm90/instr/bpt.md` | sm120-silicon | 0 | - |
| `sm90/instr/bra.md` | sm90+sm120-silicon | 1 | - |
| `sm90/instr/break.md` | sm120-silicon | 1 | - |
| `sm90/instr/brev.md` | sm120-silicon | 0 | - |
| `sm90/instr/brx.md` | sm120-silicon | 1 | - |
| `sm90/instr/brxu.md` | sm120-silicon | 1 | - |
| `sm90/instr/bssy.md` | sm120-silicon | 1 | - |
| `sm90/instr/bsync.md` | sm120-silicon | 1 | - |
| `sm90/instr/call.md` | sm90+sm120-silicon | 1 | - |
| `sm90/instr/cctl.md` | sm120-silicon | 2 | - |
| `sm90/instr/cctll.md` | sm120-silicon | 1 | - |
| `sm90/instr/cgaerrbar.md` | sm120-silicon | 1 | - |
| `sm90/instr/clmad.md` | sm120-silicon | 1 | - |
| `sm90/instr/cs2r.md` | sm120-silicon | 1 | - |
| `sm90/instr/dadd.md` | sm120-silicon | 1 | - |
| `sm90/instr/depbar.md` | sm120-silicon | 1 | DEPBAR.LE immediate sweep: threshold == number of in-flight  |
| `sm90/instr/dmma.md` | sm120-silicon | 1 | Matrix size (`size`) — 2-bit at [77:76], enum `SIZE_DMMA` |
| `sm90/instr/dmul.md` | sm120-silicon | 1 | - |
| `sm90/instr/dsetp.md` | sm120-silicon | 0 | DSETP_FCMP (test) — 4-bit |
| `sm90/instr/elect.md` | sm120-silicon | 1 | - |
| `sm90/instr/endcollective.md` | sm120-silicon | 1 | - |
| `sm90/instr/errbar.md` | sm120-silicon | 1 | - |
| `sm90/instr/exit.md` | sm120-silicon | 1 | - |
| `sm90/instr/f2f.md` | sm120-silicon | 0 | - |
| `sm90/instr/f2fp.md` | sm120-silicon | 1 | - |
| `sm90/instr/f2i.md` | sm120-silicon | 1 | - |
| `sm90/instr/f2ip.md` | sm120-silicon | 0 | - |
| `sm90/instr/fadd.md` | sm120-silicon | 1 | - |
| `sm90/instr/fchk.md` | sm120-silicon | 0 | - |
| `sm90/instr/fence.md` | sm120-silicon | 1 | Verified encodings (`tests/membar_test.cu` + probe, sm_90a,  |
| `sm90/instr/ffma.md` | sm120-silicon | 1 | - |
| `sm90/instr/flo.md` | sm120-silicon | 0 | - |
| `sm90/instr/fmnmx.md` | sm120-silicon | 1 | - |
| `sm90/instr/fmul.md` | sm120-silicon | 1 | - |
| `sm90/instr/frnd.md` | sm120-silicon | 1 | - |
| `sm90/instr/fsel.md` | sm120-silicon | 0 | - |
| `sm90/instr/fset.md` | sm120-silicon | 1 | - |
| `sm90/instr/fsetp.md` | sm120-silicon | 1 | - |
| `sm90/instr/fswzadd.md` | sm120-silicon | 1 | - |
| `sm90/instr/gather.md` | sm120-silicon | 1 | - |
| `sm90/instr/hadd2.md` | sm120-silicon | 1 | - |
| `sm90/instr/hfma2.md` | sm120-silicon | 1 | - |
| `sm90/instr/hgmma.md` | sm120-silicon | 1 | Matrix size; Matrix descriptor format |
| `sm90/instr/hmma.md` | sm120-silicon | 1 | Matrix size (`size`) — bits [78,75] |
| `sm90/instr/hmnmx2.md` | sm120-silicon | 0 | - |
| `sm90/instr/hmul2.md` | sm120-silicon | 1 | - |
| `sm90/instr/hset2.md` | sm120-silicon | 1 | - |
| `sm90/instr/hsetp2.md` | sm120-silicon | 1 | - |
| `sm90/instr/i2f.md` | sm120-silicon | 0 | - |
| `sm90/instr/i2fp.md` | sm120-silicon | 0 | - |
| `sm90/instr/i2i.md` | sm120-silicon | 0 | - |
| `sm90/instr/i2ip.md` | sm120-silicon | 0 | - |
| `sm90/instr/iabs.md` | sm120-silicon | 1 | - |
| `sm90/instr/iadd3.md` | sm120-silicon | 1 | - |
| `sm90/instr/ide.md` | sm120-silicon | 0 | - |
| `sm90/instr/idp.md` | sm120-silicon | 0 | - |
| `sm90/instr/igmma.md` | sm120-silicon | 0 | Matrix size (`size`) — 7-bit at [59:53] |
| `sm90/instr/imad.md` | sm120-silicon | 1 | Operand form matrix |
| `sm90/instr/imma.md` | sm120-silicon | 1 | Matrix size (`size`) — 3-bit at [86:85,75] |
| `sm90/instr/imnmx.md` | sm120-silicon | 1 | - |
| `sm90/instr/isetp.md` | sm120-silicon | 0 | - |
| `sm90/instr/jmp.md` | sm90+sm120-silicon | 1 | Empirical modifier probe |
| `sm90/instr/jmx.md` | sm120-silicon | 1 | - |
| `sm90/instr/jmxu.md` | sm120-silicon | 1 | - |
| `sm90/instr/kill.md` | sm120-silicon | 0 | - |
| `sm90/instr/ld.md` | sm120-silicon | 1 | - |
| `sm90/instr/ldg.md` | sm120-silicon | 1 | - |
| `sm90/instr/ldgsts.md` | sm120-silicon | 1 | - |
| `sm90/instr/ldl.md` | sm120-silicon | 0 | - |
| `sm90/instr/lds.md` | sm120-silicon | 1 | - |
| `sm90/instr/ldsm.md` | sm120-silicon | 1 | - |
| `sm90/instr/lea.md` | sm120-silicon | 0 | - |
| `sm90/instr/lepc.md` | sm120-silicon | 1 | - |
| `sm90/instr/lop3.md` | sm120-silicon | 0 | - |
| `sm90/instr/match.md` | sm120-silicon | 1 | - |
| `sm90/instr/membar.md` | sm120-silicon | 1 | - |
| `sm90/instr/mov.md` | sm120-silicon | 0 | - |
| `sm90/instr/movm.md` | sm120-silicon | 1 | Matrix mode (`mode`) — bits [79:78], enum `MOVM_MODE` |
| `sm90/instr/mufu.md` | sm120-silicon | 1 | COS/SIN turn convention (major finding) |
| `sm90/instr/nanosleep.md` | sm120-silicon | 1 | - |
| `sm90/instr/nanotrap.md` | sm120-silicon | 0 | Verified behavior (SM120, single-warp probe, 2026-08); Verified: TRAP_RETURN_PC write-protection blocks the "set-TR |
| `sm90/instr/nop.md` | sm120-silicon | 0 | - |
| `sm90/instr/p2r.md` | sm120-silicon | 1 | - |
| `sm90/instr/plop3.md` | sm120-silicon | 0 | - |
| `sm90/instr/pmtrig.md` | sm90+sm120-silicon | 1 | - |
| `sm90/instr/popc.md` | sm120-silicon | 0 | - |
| `sm90/instr/preexit.md` | sm120-silicon | 1 | - |
| `sm90/instr/prmt.md` | sm120-silicon | 0 | - |
| `sm90/instr/qspc.md` | sm120-silicon | 1 | - |
| `sm90/instr/r2b.md` | sm120-silicon | 1 | - |
| `sm90/instr/r2p.md` | sm120-silicon | 1 | - |
| `sm90/instr/r2ur.md` | sm120-silicon | 1 | - |
| `sm90/instr/red.md` | sm120-silicon | 0 | - |
| `sm90/instr/redas.md` | sm120-silicon | 1 | - |
| `sm90/instr/redux.md` | sm120-silicon | 1 | - |
| `sm90/instr/ret.md` | sm120-silicon | 1 | - |
| `sm90/instr/s2r.md` | sm120-silicon | 1 | - |
| `sm90/instr/s2ur.md` | sm120-silicon | 1 | - |
| `sm90/instr/scatter.md` | sm120-silicon | 1 | - |
| `sm90/instr/sel.md` | sm120-silicon | 0 | - |
| `sm90/instr/setctaid.md` | sm120-silicon | 1 | - |
| `sm90/instr/setmaxreg.md` | sm120-silicon | 1 | - |
| `sm90/instr/sgxt.md` | sm120-silicon | 1 | - |
| `sm90/instr/shf.md` | sm120-silicon | 1 | - |
| `sm90/instr/shfl.md` | sm120-silicon | 1 | - |
| `sm90/instr/st.md` | sm120-silicon | 1 | - |
| `sm90/instr/stas.md` | sm120-silicon | 1 | - |
| `sm90/instr/stg.md` | sm120-silicon | 1 | - |
| `sm90/instr/stl.md` | sm120-silicon | 0 | - |
| `sm90/instr/stsm.md` | sm120-silicon | 1 | Matrix layout mode (`mode`) — bit [78], enum `STSM_MODE` |
| `sm90/instr/syncs.md` | sm120-silicon | 1 | - |
| `sm90/instr/ublkcp.md` | sm120-silicon | 1 | - |
| `sm90/instr/ublkpf.md` | sm120-silicon | 1 | - |
| `sm90/instr/ublkred.md` | sm120-silicon | 1 | - |
| `sm90/instr/ubmsk.md` | sm120-silicon | 0 | - |
| `sm90/instr/ubrev.md` | sm120-silicon | 0 | - |
| `sm90/instr/ucgabar_arv.md` | sm120-silicon | 1 | - |
| `sm90/instr/ucgabar_get.md` | sm120-silicon | 1 | - |
| `sm90/instr/ucgabar_set.md` | sm120-silicon | 1 | - |
| `sm90/instr/uf2fp.md` | sm120-silicon | 0 | - |
| `sm90/instr/uflo.md` | sm120-silicon | 1 | - |
| `sm90/instr/uiadd3.md` | sm120-silicon | 0 | - |
| `sm90/instr/uimad.md` | sm120-silicon | 0 | - |
| `sm90/instr/uisetp.md` | sm120-silicon | 1 | - |
| `sm90/instr/uldc.md` | sm120-silicon | 1 | From libcublas + test kernels (sm_90, CUDA 13.1) |
| `sm90/instr/ulea.md` | sm120-silicon | 1 | - |
| `sm90/instr/ulepc.md` | sm120-silicon | 1 | - |
| `sm90/instr/ulop3.md` | sm120-silicon | 1 | - |
| `sm90/instr/umov.md` | sm120-silicon | 0 | - |
| `sm90/instr/up2ur.md` | sm90+sm120-silicon | 1 | - |
| `sm90/instr/uplop3.md` | sm120-silicon | 1 | - |
| `sm90/instr/upopc.md` | sm120-silicon | 0 | - |
| `sm90/instr/uprmt.md` | sm120-silicon | 1 | - |
| `sm90/instr/usel.md` | sm120-silicon | 0 | - |
| `sm90/instr/usetshmsz.md` | sm120-silicon | 1 | - |
| `sm90/instr/usgxt.md` | sm120-silicon | 0 | - |
| `sm90/instr/ushf.md` | sm120-silicon | 0 | - |
| `sm90/instr/utmacctl.md` | sm120-silicon | 1 | - |
| `sm90/instr/utmacmdflush.md` | sm120-silicon | 1 | Verified encodings (multiple test cubins, sm_90a, CUDA 13.1) |
| `sm90/instr/utmaldg.md` | sm120-silicon | 1 | - |
| `sm90/instr/utmapf.md` | sm120-silicon | 1 | - |
| `sm90/instr/utmaredg.md` | sm120-silicon | 1 | - |
| `sm90/instr/utmastg.md` | sm120-silicon | 1 | - |
| `sm90/instr/vabsdiff.md` | sm120-silicon | 0 | - |
| `sm90/instr/vhmnmx.md` | sm120-silicon | 0 | - |
| `sm90/instr/viadd.md` | sm120-silicon | 0 | - |
| `sm90/instr/viaddmnmx.md` | sm120-silicon | 0 | - |
| `sm90/instr/vimnmx.md` | sm120-silicon | 0 | - |
| `sm90/instr/vote.md` | sm120-silicon | 1 | - |
| `sm90/instr/voteu.md` | sm90+sm120-silicon | 1 | - |
| `sm90/instr/warpsync.md` | sm120-silicon | 1 | - |

<!-- generated:measurements-index:end -->
