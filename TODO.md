# SASS instruction documentation — TODO

Source: `ref_memo.txt` (sm_70..sm_90 opcode roster). Scope: **compute**; texture / surface / graphics and pseudo/lowered opcodes are excluded.

- **to document: 207**  |  excluded (tex/surf/gfx): 25  |  dropped pseudo/absent: 10 (INTRINSIC, QMMA_*×4, CREATEPOLICY, CVTA, UCVTA, MAPA, UMAPA)

Tags: `-> MNEM` = ref_memo entry maps to this canonical sm_90 SASS mnemonic (shape/width/uniform/extended variants share one instruction — docs may be consolidated). **LDCU** kept pending resolution (likely an LDC variant).


## Integer / Vector
All `int_pipe` instructions, vector integer ops, bit/logic/predicate ops, warp vote, register data movement.
- [x] **IMAD** (idx 1) — Integer multiply-add (32-bit)
- [x] **IMAD_WIDE** (idx 2) — Integer multiply-add, 32x32->64 result  `-> IMAD`
- [x] **IADD3** (idx 3) — Three-input integer add/subtract
- [x] **BMSK** (idx 4) — Generate bitmask from position and width
- [x] **SGXT** (idx 5) — Sign/zero-extend from specified bit position
- [x] **LOP3** (idx 6) — Three-input logic operation (arbitrary 8-bit LUT)
- [x] **ISETP** (idx 7) — Integer compare and set predicate (32-bit; re-introduced at index 288 for sm_104 with 64-bit support)
- [x] **IABS** (idx 8) — Integer absolute value (32-bit)
- [x] **LEA** (idx 9) — Load effective address (shift-add: `Rd = Ra + (Rb << imm)`)
- [x] **SHF** (idx 10) — Funnel shift (concatenate two regs, shift; used for BFI/BFE lowering)
- [x] **IDP** (idx 33) — Integer dot product (4-element)
- [x] **IDE** (idx 34) — Integer dot expand (dot-product state-machine control)
- [x] **IMNMX** (idx 37) — Integer min/max (legacy; on sm_90 ptxas prefers VIMNMX)
- [x] **POPC** (idx 38) — Population count (count set bits)
- [X] **FLO** (idx 39) — Find leading one (bit scan; PFU on mio_pipe)
- [X] **BREV** (idx 53) — Bit reverse (PFU on mio_pipe)
- [x] **PRMT** (idx 24) — Byte-level permute (4-byte shuffle from 8-byte source pair)
- [x] **SEL** (idx 20) — Register conditional select (predicate-controlled: `Rd = Pp ? Ra : Rb`)
- [x] **FSEL** (idx 17) — FP32 conditional select with `[-]`/`[||]`/`.FTZ` modifiers on source operands
- [x] **P2R** (idx 21) — Pack predicate registers (P0–P6) into a GPR byte
- [x] **R2P** (idx 22) — Unpack GPR byte into predicate registers
- [x] **MOV** (idx 19) — Move register/immediate/constant to register (GPR-to-GPR + indexed register file forms)
- [x] **PLOP3** (idx 23) — Three-input predicate logic (arbitrary LUT; 0–3 register inputs + predicate inputs)
- [x] **VOTE** (idx 26) — Warp-wide vote / ballot (ALL/ANY/EQ; produces GPR mask + predicate)
- [x] **VIADD** (idx 247) — Vector integer add (`Ra + [-]Rb`; on fmalighter_pipe for scheduling balance)
- [X] **VIADDMNMX** (idx 248) — Vector integer add-then-min/max (fused add+clamp)
- [x] **VIMNMX** (idx 249) — Vector integer min/max with `.RELU` (sm_90 replacement for IMNMX)
- [x] **VIMNMX3** (idx 250) — Vector integer three-input min/max
- [X] **VABSDIFF** (idx 31) — Vector absolute difference (`|Ra − Rb| + Rc`; COUPLED_MATH)
- [X] **VABSDIFF4** (idx 32) — Vector absolute difference, 4-way (packed 4×8-bit `|Ra − Rb|`)
- [x] **GATHER** (idx 173) — Register sub-element gather (sparse-MMA metadata unpack)
- [x] **SCATTER** (idx 157) — Register sub-element permute (sparse-MMA metadata pack)

## FP32
FP32 arithmetic via `fmalighter_pipe`; min/max on `int_pipe`; transcendental on `mio_pipe`.
- [x] **FFMA** (idx 11) — FP32 fused multiply-add (`Rd = Ra * Rb + Rc`)
- [x] **FADD** (idx 12) — FP32 add
- [x] **FMUL** (idx 13) — FP32 multiply
- [x] **FMNMX** (idx 14) — FP32 min/max (on `int_pipe`, not fmalighter; .FTZ/.NAN/.XORSIGN modifiers; base encoding cat. 510; Hopper re-introduction at idx 220 with extended operand modes)
- [x] **FSWZADD** (idx 15) — FP32 swizzle-add (quad cross-lane partial reduction for derivatives; on fmalighter_pipe)
- [x] **FSET** (idx 16) — FP32 compare and set result register (`Rd = (Ra cmp Rb) ? 1 : 0`)
- [x] **FSETP** (idx 18) — FP32 compare and set predicate
- [x] **FCHK** (idx 40) — FP check for NaN/inf/denorm detection (MUFU-dispatch on mio_pipe)
- [x] **MUFU** (idx 42) — Multi-function unit on mio_pipe: COS, SIN, EX2, LG2, RCP, RSQ, SQRT, TANH, RCP64H, RSQ64H

## FP16
Packed half-precision FP16×2 arithmetic on `fp16_pipe`.
- [x] **HADD2** (idx 126) — Packed FP16×2 add
- [x] **HADD2_F32** (idx 127) — Packed FP16×2 add with FP32 accumulator  `-> HADD2`
- [x] **HFMA2** (idx 128) — Packed FP16×2 fused multiply-add
- [x] **HFMA2_MMA** (idx 182) — Packed FP16×2 FMA, MMA variant (on fma64lite_pipe)  `-> HFMA2`
- [x] **HMUL2** (idx 129) — Packed FP16×2 multiply
- [x] **HSET2** (idx 130) — Packed FP16×2 compare and set result register
- [x] **HSETP2** (idx 131) — Packed FP16×2 compare and set predicate
- [x] **HMNMX2** (idx 183) — Packed FP16×2 min/max (2-input; F16/BF16/E6M9 formats, swizzle selectors)
- [x] **VHMNMX** (idx 246) — Vector half min/max (3-input FP16×2 with per-element swizzle; fp16_pipe)

## FP64
Double-precision arithmetic on `fma64lite_pipe`.
- [X] **DFMA** (idx 122) — FP64 fused multiply-add
- [x] **DADD** (idx 123) — FP64 add
- [x] **DMUL** (idx 124) — FP64 multiply
- [X] **DSETP** (idx 125) — FP64 compare and set predicate
- [x] **CLMAD** (idx 179) — Carry-less multiply-add in GF(2) (polynomial arithmetic; `.LO`/`.HI` 64-bit halves; CRC/crypto — GPU analog of x86 PCLMULQDQ)

## Convert
Format conversion on `int_pipe` (modern I2FP/F2IP/I2I) and `mio_pipe` (legacy I2F/F2I/F2F/MUFU).
- [x] **I2I** (idx 35) — Integer to integer width/sign change (lowered to PRMT on sm_90 for narrow types)
- [x] **I2IP** (idx 36) — Integer to integer, packed variant (DL quantization)
- [X] **F2F** (idx 43) — Float to float format conversion (F32↔F16/BF16/etc.; MUFU on mio_pipe)
- [X] **F2F_X** (idx 44) — Float to float, extended (carry chain)  `-> F2F`
- [x] **F2I** (idx 45) — Float to integer (legacy MUFU on mio_pipe)
- [X] **F2I_X** (idx 46) — Float to integer, extended  `-> F2I`
- [x] **I2F** (idx 47) — Integer to float (legacy MUFU on mio_pipe)
- [x] **I2F_X** (idx 48) — Integer to float, extended  `-> I2F`
- [x] **FRND** (idx 49) — Float round to integer within FP format (MUFU on mio_pipe)
- [x] **FRND_X** (idx 50) — Float round, extended  `-> FRND`
- [x] **I2FP** (idx 197) — Integer to float (int_pipe modern replacement for I2F)
- [x] **F2IP** (idx 195) — Float to integer, packed 8-bit output (int_pipe modern replacement for F2I)
- [ ] **F2FP** (idx 158) — Float to float, packed conversion
- [x] **UF2FP** (idx 196) — Uniform float to float, packed conversion (on udp_pipe)

## Uniform
All `udp_pipe` operations: uniform register arithmetic, uniform predicate logic, TMA, bulk copy, CGA barriers, warp-wide reduction, register-to-uniform bridging.
- [x] **UBREV** (idx 138) — Uniform bit reverse
- [x] **UBMSK** (idx 139) — Uniform bitmask
- [x] **UCLEA** (idx 140) — Uniform clear effective address (align to power-of-2 boundary)
- [x] **UISETP** (idx 141) — Uniform integer set-predicate
- [X] **ULDC** (idx 142) — Uniform load constant
- [x] **ULEA** (idx 143) — Uniform load effective address
- [x] **UP2UR** (idx 144) — Uniform predicate to uniform register
- [x] **ULOP3** (idx 145) — Uniform three-input logic (arbitrary LUT)
- [x] **UPLOP3** (idx 146) — Uniform predicate three-input logic
- [x] **USEL** (idx 147) — Uniform register conditional select
- [x] **USGXT** (idx 148) — Uniform sign-extend
- [x] **UFLO** (idx 149) — Uniform find leading one
- [x] **UIADD3** (idx 150) — Uniform three-input integer add
- [x] **UIMAD** (idx 151) — Uniform integer multiply-add
- [x] **UMOV** (idx 152) — Uniform register move
- [x] **UPRMT** (idx 153) — Uniform byte permute
- [X] **VOTEU** (idx 154) — Uniform warp vote / ballot (uniform-register results; `__activemask()`)
- [X] **UPOPC** (idx 155) — Uniform population count
- [X] **USHF** (idx 156) — Uniform funnel shift
- [x] **S2UR** (idx 169) — Special register to uniform register (udp sibling of S2R)
- [x] **R2UR_H** (idx 226) — Register to uniform register, high half  `-> R2UR`
- [x] **ULEPC** (idx 238) — Uniform load effective PC
- [x] **USETMAXREG** (idx 228) — Set maximum register count for dynamic partitioning  `-> USETMAXREG`
- [x] **USETSHMSZ** (idx 229) — Set shared memory size dynamically  `-> USETSHMSZ`

## Memory
Load/store/atomic/reduction/cache-control/warp-cross-lane
- [x] **LDC** (idx 89) — Load from constant memory c[bank][offset]
- [x] **LDS** (idx 94) — Load from shared memory
- [x] **STS** (idx 95) — Store to shared memory
- [x] **LDG** (idx 96) — Load from global memory
- [x] **STG** (idx 97) — Store to global memory
- [x] **LDL** (idx 98) — Load from local memory (per-thread stack / `.local`)
- [x] **STL** (idx 99) — Store to local memory
- [x] **LD** (idx 100) — Load, generic address space (runtime-resolved)
- [x] **ST** (idx 101) — Store, generic address space (runtime-resolved)
- [x] **LDGSTS** (idx 191) — Load-global, store-to-shared (async copy; `cp.async`)
- [x] **ATOM** (idx 102) — Atomic operation (generic address space)
- [x] **ATOMG** (idx 103) — Atomic operation (global memory)
- [x] **RED** (idx 104) — Reduction on shared memory (fire-and-forget; dead on sm_90 — ptxas emits ATOMS instead)
- [x] **ATOMS** (idx 105) — Atomic operation (shared memory)
- [x] **REDAS** (idx 227) — Reduce-async to distributed shared memory (`red.async.shared::cluster`)
- [ ] **QSPC** (idx 106) — Query address space type
- [x] **CCTL** (idx 108) — Cache control (L1/L2 line prefetch/writeback/invalidate/discard + whole-cache *ALL)
- [x] **CCTL_NO_SB** (idx 107) — Cache control, no scoreboard wait (= CCTL whole-cache noSrc forms)  `-> CCTL`
- [x] **CCTLL** (idx 109) — Cache control, local memory (local-space sibling of CCTL)
- [x] **MEMBAR** (idx 111) — Memory ordering fence (SC/ALL × CTA/GPU/SYS)
- [x] **FENCE_G** (idx 218) — Fence, global scope (FENCE.VIEW.ASYNC.G)  `-> FENCE`
- [x] **FENCE_S** (idx 219) — Fence, shared/CTA scope (FENCE.VIEW.ASYNC.S)  `-> FENCE`
- [x] **STAS** (idx 230) — Store-async to distributed shared memory (`st.async.shared::cluster`)
- [x] **STSM** (idx 231) — Store to shared memory, matrix layout
- [x] **UBLKCP** (idx 234) — Uniform block copy (non-tensor `cp.async.bulk`)
- [x] **UBLKRED** (idx 235) — Uniform block reduction (non-tensor `cp.reduce.async.bulk`)
- [x] **UBLKPF** (idx 236) — Uniform block prefetch (non-tensor `cp.async.bulk.prefetch` → L2)
- [x] **UTMALDG** (idx 242) — TMA tensor load (descriptor-based async global→shared)
- [x] **UTMASTG** (idx 245) — TMA tensor store (shared→global) `[ref_memo typo: "UTMALST"]`
- [x] **UTMAPF** (idx 243) — TMA tensor prefetch (global→L2)
- [x] **UTMAREDG** (idx 244) — TMA tensor reduction store (shared→global, atomic reduce)  `[ref_memo: UTMREDG]`
- [x] **UTMACMDFLUSH** (idx 241) — TMA command flush / bulk-async-group commit (`cp.async.bulk.commit_group`)
- [x] **UTMACCTL** (idx 240) — TMA descriptor cache control (invalidate/prefetch)
- [x] **ERRBAR** (idx 0) — Error barrier (GPU-scope; emitted alongside GPU/SYS fences; mio_pipe)
- [x] **CGAERRBAR** (idx 212) — CGA error barrier (cluster-scope; mio_pipe)


## Tensor
Matrix multiply-accumulate: warp-level MMA (`fp16_pipe`/`int_pipe`/`fma64lite_pipe`) and warpgroup GMMA (`mio_pipe` MIO_SLOW).
- [x] **HMMA_16** (idx 132) — FP16 warp MMA, 16-wide  `-> HMMA`
- [x] **HMMA_32** (idx 133) — FP16 warp MMA, 32-wide  `-> HMMA`
- [X] **HMMA_1688** (idx 159) — FP16 warp MMA, 16×8×8  `-> HMMA`
- [X] **HMMA_16816** (idx 160) — FP16 warp MMA, 16×8×16  `-> HMMA`
- [X] **HMMA_SP_1688** (idx 181) — FP16 sparse warp MMA, 16×8×8  `-> HMMA`
- [x] **IMMA** (idx 134) — Integer warp MMA
- [x] **IMMA_88** (idx 184) — Integer warp MMA, 8×8  `-> IMMA`
- [x] **IMMA_SP_88** (idx 185) — Integer sparse warp MMA, 8×8  `-> IMMA`
- [x] **IMMA_16816** (idx 186) — Integer warp MMA, 16×8×16  `-> IMMA`
- [x] **IMMA_16832** (idx 187) — Integer warp MMA, 16×8×32  `-> IMMA`
- [x] **IMMA_SP_16832** (idx 188) — Integer sparse warp MMA, 16×8×32  `-> IMMA`
- [x] **BMMA** (idx 161) — Binary (1-bit) warp MMA
- [x] **BMMA_88128** (idx 176) — Binary warp MMA, 8×8×128  `-> BMMA`
- [x] **BMMA_168128** (idx 177) — Binary warp MMA, 16×8×128  `-> BMMA`
- [x] **BMMA_168256** (idx 178) — Binary warp MMA, 16×8×256  `-> BMMA`
- [x] **DMMA** (idx 180) — FP64 warp MMA (Ampere; encoding category 434; `fma64lite_pipe`)
- [x] **DMMA** (idx 215) — FP64 warp MMA (Hopper re-introduction; encoding category 515, warpgroup-aware TC path; same opcode as CVTA 0xD6/0xD7)
- [x] **GMMA** (idx 221) — Group (warpgroup) MMA  `-> HGMMA/IGMMA/BGMMA/QGMMA`

## Control Flow
Branch/jump/call/return/convergence/PDL/election on `cbu_pipe`.
- [x] **BRA** (idx 67) — Branch (relative)
- [x] **BRX** (idx 68) — Branch indirect (register target)
- [x] **JMP** (idx 69) — Jump (absolute)
- [x] **JMX** (idx 70) — Jump indirect  _(+ JMXU uniform variant)_
- [x] **CALL** (idx 71) — Function call
- [x] **RET** (idx 72) — Return from function
- [x] **BSSY** (idx 73) — Branch set sync (push convergence barrier `Bi` onto sync stack)
- [x] **BSYNC** (idx 79) — Branch sync (wait + pop convergence stack, reconverge)
- [x] **BREAK** (idx 74) — Peel lanes from convergence region
- [x] **BMOV** (idx 56) — CBU convergence-barrier state/register read/write (B0–B15, lane masks, trap PCs; `cbu_pipe`)
- [x] **BMOV_B** (idx 54) — CBU barrier register read form  `-> BMOV`
- [x] **BMOV_R** (idx 55) — CBU state write, register-source form  `-> BMOV`
- [x] **EXIT** (idx 77) — Thread exit
- [x] **BPT** (idx 75) — Breakpoint trap (debugger)
- [ ] **RTT** (idx 78) — Return to trap handler
- [x] **YIELD** (idx 121) — Warp scheduler yield hint


## Synchronization
- [x] **WARPGROUP** (idx 251) — Warpgroup MMA fence/wait (syncs warp-level work with warpgroup tensor ops; mio_pipe)
- [x] **B2R** (idx 58) — Barrier register to GPR (named `bar.sync` state read)
- [x] **R2B** (idx 59) — GPR to barrier register
- [x] **BAR** (idx 61) — Named barrier synchronization (`bar.sync`)
- [x] **BAR_INDEXED** (idx 62) — Barrier, indexed variant  `-> BAR`
- [x] **DEPBAR** (idx 66) — Dependency barrier (counted scoreboard wait; on `fe_pipe`)
- [x] **SYNCS_BASIC** (idx 232) — Sync scope, basic (mbarrier operations + uniform atomics)  `-> SYNCS`
- [x] **SYNCS_LD_UNIFM** (idx 233) — Sync scope with uniform load  `-> SYNCS`
- [x] **ELECT** (idx 216) — Elect leader lane in warp (URa or predicate candidate mask; `cg::invoke_one` primitive)
- [x] **ENDCOLLECTIVE** (idx 217) — Close warp collective region (bracket for `WARPSYNC.COLLECTIVE`)
- [x] **WARPSYNC** (idx 120) — Warp-lane reconvergence (`__syncwarp`; .ALL/.COLLECTIVE/.EXCLUSIVE modes)
- [x] **PREEXIT** (idx 225) — Grid-dependent launch producer signal (`griddepcontrol.launch_dependents`)
- [x] **ACQBLK** (idx 207) — Grid-dependent launch consumer acquire (`griddepcontrol.wait`)  `-> ACQBULK`
- [x] **ARRIVES** (idx 189) — Async mbarrier arrive signal (LDGSTS completion signaling)
- [x] **SHFL** (idx 119) — Warp shuffle (cross-lane data exchange; IDX/UP/DOWN/BFLY modes)
- [x] **MATCH** (idx 80) — Warp match (find lanes sharing a value; MIO_FAST_OPS)
- [x] **LDGDEPBAR** (idx 190) — Async copy group commit (`cp.async.bulk.commit_group`)
- [x] **UCGABAR_ARV** (idx 208) — CGA cluster barrier arrive  `-> UCGABAR_ARV`
- [X] **UCGABAR_WAIT** (idx 211) — CGA cluster barrier wait  `-> UCGABAR_WAIT`
- [ ] **UCGABAR_GET** (idx 209) — CGA barrier query state  `-> UCGABAR_GET`
- [ ] **UCGABAR_SET** (idx 210) — CGA barrier set  `-> UCGABAR_SET`
- [x] **REDUX** (idx 192) — Warp-wide reduction to uniform register (ADD/MIN/MAX/AND/OR/XOR; udp_pipe, `VQ_REDUX`)

## Misc
System and special-purpose instructions not fitting the above categories.
- [X] **NOP** (idx 25) — No-operation (dispatched on `fe_pipe` as padding)
- [x] **CS2R_32** (idx 27) — Control/code state register to GPR (32-bit)  `-> CS2R`
- [x] **CS2R_64** (idx 28) — Control/code state register to GPR (64-bit)  `-> CS2R`
- [x] **S2R** (idx 57) — Read special register (SR_TID, SR_CLOCKLO, etc.) to GPR
- [x] **LEPC** (idx 60) — Load effective PC (get current instruction address; `int_pipe`)
- [x] **LEPC** (idx 223) — Load effective PC (sm_90 variant)
- [x] **SETCTAID** (idx 63) — Set CTA ID hardware state (driver/ABI setup; mio_pipe)
- [x] **SETLMEMBASE** (idx 64) — Set local memory base address
- [x] **GETLMEMBASE** (idx 65) — Get local memory base address
- [X] **LDCU** (idx 222) — Load constant, uniform (warp-coherent constant load; unresolved — likely LDC variant)
- [x] **PMTRIG** (idx 29) — Performance monitor trigger
- [x] **CSMTEST** (idx 30) — CSM (compute shader model) test
- [x] **NANOSLEEP** (idx 81) — Thread sleep for specified nanoseconds (cbu_pipe)
- [x] **NANOTRAP** (idx 82) — Nano trap, lightweight trap (cbu_pipe)

---
## Excluded (texture / surface / graphics)
- ~~KILL~~ (idx 76) — Kill thread (pixel shader discard)
- ~~IPA~~ (idx 41) — Interpolate pixel attribute (fragment shader)  · _fragment-shader attribute interp_
- ~~AL2P~~ (idx 51) — Attribute location to patch offset  · _graphics_
- ~~AL2P_INDEXED~~ (idx 52) — Attribute to patch, indexed variant  · _graphics_
- ~~TEX~~ (idx 83) — Texture fetch (filtered sample)  · _texture_
- ~~TLD~~ (idx 84) — Texture load (unfiltered, integer coords)  · _texture_
- ~~TLD4~~ (idx 85) — Texture gather (fetch 4 texels)  · _texture_
- ~~TMML~~ (idx 86) — Query texture mip-map level  · _texture_
- ~~TXD~~ (idx 87) — Texture fetch with explicit derivatives  · _texture_
- ~~TXQ~~ (idx 88) — Texture query (dimensions, levels, format)  · _texture_
- ~~ALD~~ (idx 90) — Attribute load  · _vertex/fragment attribute load_
- ~~AST~~ (idx 91) — Attribute store  · _attribute store_
- ~~OUT~~ (idx 92) — Tessellation output emit  · _graphics_
- ~~OUT_FINAL~~ (idx 93) — Tessellation output emit (final, cut primitive)  · _graphics_
- ~~CCTLT~~ (idx 110) — Cache control, texture cache  · _texture cache_
- ~~SULD~~ (idx 112) — Surface load  · _surface_
- ~~SUST~~ (idx 113) — Surface store  · _surface_
- ~~SUATOM~~ (idx 114) — Surface atomic  · _surface_
- ~~SURED~~ (idx 115) — Surface reduction  · _surface_
- ~~PIXLD~~ (idx 116) — Pixel information load  · _graphics_
- ~~ISBERD~~ (idx 117) — Indexed set buffer for read (bindless)  · _graphics_
- ~~ISBEWR~~ (idx 118) — Indexed set buffer for write (bindless)  · _graphics_
- ~~TTUCCTL~~ (idx 162) — Tensor texture unit cache control  · _tensor-texture-unit_
- ~~TTUMACRO~~ (idx 163) — Tensor texture unit macro  · _tensor-texture-unit_
- ~~FOOTPRINT~~ (idx 168) — Texture footprint query  · _texture_
- ~~SUQUERY~~ (idx 198) — Surface query  · _surface_
