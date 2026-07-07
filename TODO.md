# SASS instruction documentation — TODO

Source: `ref_memo.txt` (sm_70..sm_90 opcode roster). Scope: **compute**; texture / surface / graphics and pseudo/lowered opcodes are excluded.

- **to document: 207**  |  excluded (tex/surf/gfx): 25  |  dropped pseudo/absent: 10 (INTRINSIC, QMMA_*×4, CREATEPOLICY, CVTA, UCVTA, MAPA, UMAPA)

Tags: `-> MNEM` = ref_memo entry maps to this canonical sm_90 SASS mnemonic (shape/width/uniform/extended variants share one instruction — docs may be consolidated). **LDCU** kept pending resolution (likely an LDC variant).


## Integer Arithmetic
- [x] **IMAD** (idx 1) — Integer multiply-add (32-bit)
- [x] **IMAD_WIDE** (idx 2) — Integer multiply-add, 32x32->64 result  `-> IMAD`
- [x] **IADD3** (idx 3) — Three-input integer add with carry
- [x] **BMSK** (idx 4) — Generate bitmask from position and width
- [x] **SGXT** (idx 5) — Sign-extend from specified bit position
- [x] **LOP3** (idx 6) — Three-input logic operation (arbitrary LUT)
- [x] **ISETP** (idx 7) — Integer compare and set predicate (32-bit; re-introduced at index 288 for sm_104 with 64-bit support)
- [x] **IABS** (idx 8) — Integer absolute value
- [x] **LEA** (idx 9) — Load effective address (shift-add)
- [x] **SHF** (idx 10) — Funnel shift (concatenate two regs, shift)
- [x] **IDP** (idx 33) — Integer dot product (4-element)
- [x] **IDE** (idx 34) — Integer dot expand
- [x] **IMNMX** (idx 37) — Integer min/max (32-bit only; re-introduced at indices 284–285 for sm_104 with 32/64-bit split)
- [x] **POPC** (idx 38) — Population count (count set bits)
- [X] **FLO** (idx 39) — Find leading one (bit scan)
- [X] **BREV** (idx 53) — Bit reverse

## FP32 Arithmetic
- [x] **FFMA** (idx 11) — FP32 fused multiply-add
- [x] **FADD** (idx 12) — FP32 add
- [x] **FMUL** (idx 13) — FP32 multiply
- [x] **FMNMX** (idx 14) — FP32 min/max (base encoding cat. 510; re-introduced at index 220 for sm_90 with extended operand modes)
- [x] **FSWZADD** (idx 15) — FP32 swizzle add (cross-lane partial reduction)
- [x] **FSET** (idx 16) — FP32 compare and set result register
- [x] **FSEL** (idx 17) — FP32 select (conditional move)
- [x] **FSETP** (idx 18) — FP32 compare and set predicate
- [x] **FCHK** (idx 40) — FP check for NaN/Inf/denorm
- [x] **MUFU** (idx 42) — Multi-function unit: RCP, RSQ, SIN, COS, EX2, LG2, RCP64H, RSQ64H

## FP64 Arithmetic
- [X] **DFMA** (idx 122) — FP64 fused multiply-add
- [x] **DADD** (idx 123) — FP64 add
- [x] **DMUL** (idx 124) — FP64 multiply
- [X] **DSETP** (idx 125) — FP64 compare and set predicate

## FP16 Packed Arithmetic
- [x] **HADD2** (idx 126) — Packed FP16x2 add
- [x] **HADD2_F32** (idx 127) — Packed FP16x2 add with FP32 accumulator  `-> HADD2`
- [x] **HFMA2** (idx 128) — Packed FP16x2 fused multiply-add
- [x] **HMUL2** (idx 129) — Packed FP16x2 multiply
- [x] **HSET2** (idx 130) — Packed FP16x2 compare and set
- [x] **HSETP2** (idx 131) — Packed FP16x2 compare and set predicate

## Type Conversion
- [x] **I2I** (idx 35) — Integer to integer conversion (width/sign change)
- [x] **I2IP** (idx 36) — Integer to integer, packed variant
- [X] **F2F** (idx 43) — Float to float conversion (precision change)
- [X] **F2F_X** (idx 44) — Float to float, extended (with carry chain)  `-> F2F`
- [x] **F2I** (idx 45) — Float to integer
- [X] **F2I_X** (idx 46) — Float to integer, extended  `-> F2I`
- [x] **I2F** (idx 47) — Integer to float
- [x] **I2F_X** (idx 48) — Integer to float, extended  `-> I2F`
- [x] **FRND** (idx 49) — FP round to integer (within FP format)
- [x] **FRND_X** (idx 50) — FP round, extended  `-> FRND`

## Data Movement
- [x] **MOV** (idx 19) — Move register to register
- [x] **SEL** (idx 20) — Predicated select (ternary conditional)
- [x] **P2R** (idx 21) — Pack predicate registers into GPR
- [x] **R2P** (idx 22) — Unpack GPR bits into predicate registers
- [x] **PRMT** (idx 24) — Byte-level permute (4-byte shuffle)
- [x] **S2R** (idx 57) — Read special register to GPR
- [x] **CS2R_32** (idx 27) — Control/status register to GPR (32-bit)  `-> CS2R`
- [x] **CS2R_64** (idx 28) — Control/status register to GPR (64-bit)  `-> CS2R`

## Predicate Operations
- [x] **PLOP3** (idx 23) — Three-input predicate logic (arbitrary LUT)
- [x] **VOTE** (idx 26) — Warp-wide vote (ballot/any/all/unanimity)
- [X] **VABSDIFF** (idx 31) — Vector absolute difference
- [X] **VABSDIFF4** (idx 32) — Vector absolute difference, 4-way

## Memory — Load/Store
- [x] **LDC** (idx 89) — Load from constant memory bank c[bank][offset]
- [x] **LDS** (idx 94) — Load from shared memory
- [x] **STS** (idx 95) — Store to shared memory
- [x] **LDG** (idx 96) — Load from global memory
- [x] **STG** (idx 97) — Store to global memory
- [x] **LDL** (idx 98) — Load from local memory (per-thread stack)
- [x] **STL** (idx 99) — Store to local memory
- [x] **LD** (idx 100) — Load, generic address space (runtime-resolved; sibling of LDG, opcode differs by 1 bit)
- [x] **ST** (idx 101) — Store, generic address space (runtime-resolved; write-side sibling of LD, opcode 0x1985)

## Atomic and Reduction
- [x] **ATOM** (idx 102) — Atomic operation (generic address space)
- [x] **ATOMG** (idx 103) — Atomic operation (global memory)
- [x] **RED** (idx 104) — Reduction (shared memory, → ATOMS on sm_90)
- [x] **ATOMS** (idx 105) — Atomic operation (shared memory)

## Cache and Memory Control
- [x] **QSPC** (idx 106) — Query address space type
- [x] **CCTL_NO_SB** (idx 107) — Cache control, no scoreboard wait (= CCTL whole-cache noSrc `*ALL` forms; src_rel_sb pinned) `-> CCTL`
- [x] **CCTL** (idx 108) — Cache control (L1/L2 line prefetch/writeback/invalidate/discard + whole-cache *ALL)
- [x] **CCTLL** (idx 109) — Cache control, local memory (prefetch/writeback/invalidate; local-space sibling of CCTL)
- [x] **MEMBAR** (idx 111) — Memory barrier / fence (SC/ALL × CTA/GPU/SYS; ≥GPU co-emits ERRBAR+CGAERRBAR)

## Control Flow
- [x] **BRA** (idx 67) — Branch (relative)
- [x] **BRX** (idx 68) — Branch indirect (register target)
- [x] **JMP** (idx 69) — Jump (absolute)
- [x] **JMX** (idx 70) — Jump indirect  _(+ JMXU uniform variant; see notes/jmx.md)_
- [x] **CALL** (idx 71) — Function call
- [x] **RET** (idx 72) — Return from function
- [x] **BSSY** (idx 73) — Push convergence point onto branch sync stack
- [x] **BREAK** (idx 74) — Break out of convergence region
- [x] **EXIT** (idx 77) — Thread exit
- [x] **KILL** (idx 76) — Kill thread (discard fragment)
- [x] **BPT** (idx 75) — Breakpoint trap (debugger)
- [ ] **RTT** (idx 78) — Return to trap handler
- [x] **BSYNC** (idx 79) — Branch sync (pop convergence stack, reconverge)

## Synchronization and Warp
- [x] **BMOV_B** (idx 54) — Branch-mask move (branch register, B variant)  `-> BMOV`
- [x] **BMOV_R** (idx 55) — Branch-mask move (branch register, R variant)  `-> BMOV`
- [x] **BMOV** (idx 56) — Barrier move
- [x] **B2R** (idx 58) — Barrier register to GPR
- [x] **R2B** (idx 59) — GPR to barrier register
- [x] **BAR** (idx 61) — Named barrier synchronization
- [x] **BAR_INDEXED** (idx 62) — Barrier, indexed variant  `-> BAR`
- [x] **DEPBAR** (idx 66) — Dependency barrier (wait for scoreboard)
- [x] **MATCH** (idx 80) — Warp match (find lanes with same value)
- [x] **SHFL** (idx 119) — Warp shuffle (cross-lane data exchange)
- [x] **WARPSYNC** (idx 120) — Warp-wide synchronization barrier
- [x] **NANOSLEEP** (idx 81) — Thread sleep for specified nanoseconds
- [x] **NANOTRAP** (idx 82) — Nano trap (lightweight trap)

## System and Miscellaneous
- [x] **ERRBAR** (idx 0) — Error barrier (GPU-scope; emitted with GPU/SYS fences)
- [X] **NOP** (idx 25) — No-operation
- [x] **PMTRIG** (idx 29) — Performance monitor trigger
- [x] **CSMTEST** (idx 30) — CSM (compute shader model) test
- [x] **LEPC** (idx 60) — Load effective PC (get current instruction address)
- [x] **SETCTAID** (idx 63) — Set CTA (thread block) ID
- [x] **SETLMEMBASE** (idx 64) — Set local memory base address
- [x] **GETLMEMBASE** (idx 65) — Get local memory base address
- [x] **YIELD** (idx 121) — Yield execution (internal, scheduler hint)

## Uniform Register Operations
- [x] **UBREV** (idx 138) — Uniform bit reverse
- [x] **UBMSK** (idx 139) — Uniform bitmask
- [x] **UCLEA** (idx 140) — Uniform clear address
- [x] **UISETP** (idx 141) — Uniform integer set-predicate
- [X] **ULDC** (idx 142) — Uniform load constant
- [x] **ULEA** (idx 143) — Uniform load effective address
- [x] **UP2UR** (idx 144) — Uniform predicate to uniform register
- [x] **ULOP3** (idx 145) — Uniform three-input logic
- [x] **UPLOP3** (idx 146) — Uniform predicate three-input logic
- [x] **USEL** (idx 147) — Uniform select
- [x] **USGXT** (idx 148) — Uniform sign-extend
- [x] **UFLO** (idx 149) — Uniform find leading one
- [x] **UIADD3** (idx 150) — Uniform three-input integer add
- [x] **UIMAD** (idx 151) — Uniform integer multiply-add
- [x] **UMOV** (idx 152) — Uniform move
- [x] **UPRMT** (idx 153) — Uniform byte permute
- [X] **VOTEU** (idx 154) — Uniform vote
- [X] **UPOPC** (idx 155) — Uniform population count
- [X] **USHF** (idx 156) — Uniform funnel shift

## Additional sm_73 Operations
- [x] **SCATTER** (idx 157) — Register sub-element byte/nibble permute (not a memory store; sparse/low-precision lane packing)
- [x] **GATHER** (idx 173) — Register sub-element gather (read-side sibling of SCATTER; sparse-MMA metadata) `[not previously listed]`
- [x] **S2UR** (idx 169) — Special register to uniform register (uniform-datapath sibling of S2R) `[not previously listed]`
- [ ] **F2FP** (idx 158) — Float to float, packed conversion
- [X] **HMMA_1688** (idx 159) — FP16 MMA, 16x8x8 shape  `-> HMMA`
- [X] **HMMA_16816** (idx 160) — FP16 MMA, 16x8x16 shape  `-> HMMA`
- [x] **BMMA** (idx 161) — Binary (1-bit) matrix multiply-accumulate
- [x] **BMMA_88128** (idx 176) — Binary MMA, 8x8x128 shape  `-> BMMA`
- [x] **BMMA_168128** (idx 177) — Binary MMA, 16x8x128 shape  `-> BMMA`
- [x] **BMMA_168256** (idx 178) — Binary MMA, 16x8x256 shape  `-> BMMA`
- [x] **CLMAD** (idx 179) — Carry-less multiply-add (GF(2) arithmetic)
- [x] **DMMA** (idx 180) — FP64 matrix multiply-accumulate (Ampere; encoding category 434; re-introduced at index 215 for Hopper with different TC path)
- [X] **HMMA_SP_1688** (idx 181) — FP16 sparse MMA, 16x8x8  `-> HMMA`
- [x] **HFMA2_MMA** (idx 182) — FP16 FMA2, MMA variant  `-> HFMA2`
- [x] **HMNMX2** (idx 183) — Packed FP16x2 min/max

## Tensor Core (Base)
- [x] **HMMA_16** (idx 132) — FP16 matrix multiply-accumulate, 16-wide  `-> HMMA`
- [x] **HMMA_32** (idx 133) — FP16 matrix multiply-accumulate, 32-wide  `-> HMMA`
- [x] **IMMA** (idx 134) — Integer matrix multiply-accumulate
- [x] **IMMA_88** (idx 184) — Integer MMA, 8x8 shape  `-> IMMA`
- [x] **IMMA_SP_88** (idx 185) — Integer sparse MMA, 8x8  `-> IMMA`
- [x] **IMMA_16816** (idx 186) — Integer MMA, 16x8x16  `-> IMMA`
- [x] **IMMA_16832** (idx 187) — Integer MMA, 16x8x32  `-> IMMA`
- [x] **IMMA_SP_16832** (idx 188) — Integer sparse MMA, 16x8x32  `-> IMMA`
- [x] **ARRIVES** (idx 189) — Async barrier arrive signal
- [x] **LDGDEPBAR** (idx 190) — Load-global dependency barrier
- [x] **LDGSTS** (idx 191) — Load-global, store-to-shared (async copy, `cp.async`)
- [x] **REDUX** (idx 192) — Warp-wide reduction (uniform result)
- [x] **F2IP** (idx 195) — Float to integer, packed
- [x] **UF2FP** (idx 196) — Uniform float to float, packed
- [x] **I2FP** (idx 197) — Integer to float, packed

## CGA Barriers and Synchronization
- [x] **ACQBLK** (idx 207) — Acquire block (CTA resource acquisition)  `-> ACQBULK`
- [x] **CGABAR_ARV** (idx 208) — CGA barrier arrive  `-> UCGABAR_ARV`
- [x] **CGABAR_GET** (idx 209) — CGA barrier get (query state)  `-> UCGABAR_GET`
- [x] **CGABAR_SET** (idx 210) — CGA barrier set  `-> UCGABAR_SET`
- [X] **CGABAR_WAIT** (idx 211) — CGA barrier wait  `-> UCGABAR_WAIT`
- [x] **CGAERRBAR** (idx 212) — CGA error barrier

## Collective and Election
- [x] **DMMA** (idx 215) — FP64 matrix multiply-accumulate (Hopper re-introduction; encoding category 515 vs 434 for index 180; uses warpgroup-aware tensor core path, shared dispatch with CVTA at case 0xD6/0xD7 in sub_6575D0)
- [x] **ELECT** (idx 216) — Elect a leader lane in warp
- [x] **ENDCOLLECTIVE** (idx 217) — End collective operation scope

## Fences
- [x] **FENCE_G** (idx 218) — Fence, global scope (FENCE.VIEW.ASYNC.G; async-proxy view fence) `-> FENCE`
- [x] **FENCE_S** (idx 219) — Fence, shared/CTA scope (FENCE.VIEW.ASYNC.S) `-> FENCE`

## GMMA (Group Matrix Multiply-Accumulate)
- [x] **GMMA** (idx 221) — Group (warpgroup) matrix multiply-accumulate  `-> HGMMA/IGMMA/BGMMA/QGMMA`

## Memory Extensions
- [X] **LDCU** (idx 222) — Load constant, uniform (warp-coherent constant load)  `-> LDC variant? (unresolved)`
- [x] **LEPC** (idx 223) — Load effective PC (sm_90 variant)
- [x] **PREEXIT** (idx 225) — Pre-exit (griddepcontrol.launch_dependents / PDL)
- [x] **R2UR_H** (idx 226) — Register to uniform register, high half  `-> R2UR`
- [x] **REDAS** (idx 227) — Reduce-async to distributed shared memory (`red.async.shared::cluster`)

## Configuration
- [x] **SETMAXREG** (idx 228) — Set maximum register count for dynamic partitioning  `-> USETMAXREG`
- [x] **SETSMEMSIZE** (idx 229) — Set shared memory size dynamically  `-> USETSHMSZ`
- [x] **STAS** (idx 230) — Store-async to distributed shared memory (`st.async.shared::cluster`)
- [x] **STSM** (idx 231) — Store to shared memory, matrix layout

## Synchronization Extensions
- [x] **SYNCS_BASIC** (idx 232) — Sync scope, basic  `-> SYNCS`
- [x] **SYNCS_LD_UNIFM** (idx 233) — Sync scope with uniform load  `-> SYNCS`

## Uniform Block Operations
- [x] **UBLKCP** (idx 234) — Uniform block copy
- [x] **UBLKRED** (idx 235) — Uniform block reduction (non-tensor cp.reduce.async.bulk)
- [x] **UBLKPF** (idx 236) — Uniform block prefetch (non-tensor cp.async.bulk.prefetch → L2)
- [x] **ULEPC** (idx 238) — Uniform load effective PC
- [x] **UTMACCTL** (idx 240) — TMA cache control (tensor-map descriptor invalidate/prefetch)
- [x] **UTMACMDFLUSH** (idx 241) — TMA command flush / bulk-async-group commit (`cp.async.bulk.commit_group`)
- [x] **UTMALDG** (idx 242) — TMA load global
- [x] **UTMAPF** (idx 243) — TMA tensor prefetch (global→L2)
- [x] **UTMAREDG** (idx 244) — TMA tensor reduction store (shared→global, atomic reduce)  `[ref_memo: UTMREDG]`
- [x] **UTMASTG** (idx 245) — TMA tensor store (shared→global) `[TODO ref_memo typo: "UTMALST" is not a real mnemonic]`

## Vector Min/Max Extensions
- [x] **VHMNMX** (idx 246) — Vector half min/max (FP16x2)
- [x] **VIADD** (idx 247) — Vector integer add
- [X] **VIADDMNMX** (idx 248) — Vector integer add with min/max
- [x] **VIMNMX** (idx 249) — Vector integer min/max
- [x] **VIMNMX3** (idx 250) — Vector integer three-input min/max
- [x] **WARPGROUP** (idx 251) — Warpgroup collective operation

---
## Excluded (texture / surface / graphics)
- ~~IPA~~ (idx 41) — Interpolate pixel attribute (fragment shader)  · _fragment-shader attribute interp_
- ~~AL2P~~ (idx 51) — Attribute location to patch offset  · _Graphics Pipeline_
- ~~AL2P_INDEXED~~ (idx 52) — Attribute to patch, indexed variant  · _Graphics Pipeline_
- ~~TEX~~ (idx 83) — Texture fetch (filtered sample)  · _Texture Operations_
- ~~TLD~~ (idx 84) — Texture load (unfiltered, integer coords)  · _Texture Operations_
- ~~TLD4~~ (idx 85) — Texture gather (fetch 4 texels for bilinear)  · _Texture Operations_
- ~~TMML~~ (idx 86) — Query texture mip-map level  · _Texture Operations_
- ~~TXD~~ (idx 87) — Texture fetch with explicit derivatives  · _Texture Operations_
- ~~TXQ~~ (idx 88) — Texture query (dimensions, levels, format)  · _Texture Operations_
- ~~ALD~~ (idx 90) — Attribute load (vertex/fragment attributes)  · _vertex/fragment attribute load_
- ~~AST~~ (idx 91) — Attribute store  · _attribute store_
- ~~OUT~~ (idx 92) — Tessellation output emit  · _Graphics Pipeline_
- ~~OUT_FINAL~~ (idx 93) — Tessellation output emit (final, cut primitive)  · _Graphics Pipeline_
- ~~CCTLT~~ (idx 110) — Cache control, texture cache  · _texture cache control_
- ~~SULD~~ (idx 112) — Surface load  · _Surface Operations_
- ~~SUST~~ (idx 113) — Surface store  · _Surface Operations_
- ~~SUATOM~~ (idx 114) — Surface atomic  · _Surface Operations_
- ~~SURED~~ (idx 115) — Surface reduction  · _Surface Operations_
- ~~PIXLD~~ (idx 116) — Pixel information load (coverage, sample mask)  · _Graphics Pipeline_
- ~~ISBERD~~ (idx 117) — Indexed set buffer for read (bindless)  · _Graphics Pipeline_
- ~~ISBEWR~~ (idx 118) — Indexed set buffer for write (bindless)  · _Graphics Pipeline_
- ~~TTUCCTL~~ (idx 162) — Tensor texture unit cache control  · _tensor-texture-unit_
- ~~TTUMACRO~~ (idx 163) — Tensor texture unit macro  · _tensor-texture-unit_
- ~~FOOTPRINT~~ (idx 168) — Texture footprint query  · _texture footprint_
- ~~SUQUERY~~ (idx 198) — Surface query (dimensions, format)  · _surface query_
