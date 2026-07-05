# SASS instruction documentation — TODO

Source: `ref_memo.txt` (sm_70..sm_90 opcode roster). Scope: **compute**; texture / surface / graphics and pseudo/lowered opcodes are excluded.

- **to document: 207**  |  excluded (tex/surf/gfx): 25  |  dropped pseudo/absent: 10 (INTRINSIC, QMMA_*×4, CREATEPOLICY, CVTA, UCVTA, MAPA, UMAPA)

Tags: `-> MNEM` = ref_memo entry maps to this canonical sm_90 SASS mnemonic (shape/width/uniform/extended variants share one instruction — docs may be consolidated). **LDCU** kept pending resolution (likely an LDC variant).


## Integer Arithmetic
- [x] **IMAD** (idx 1) — Integer multiply-add (32-bit)
- [x] **IMAD_WIDE** (idx 2) — Integer multiply-add, 32x32->64 result  `-> IMAD`
- [x] **IADD3** (idx 3) — Three-input integer add with carry
- [ ] **BMSK** (idx 4) — Generate bitmask from position and width
- [ ] **SGXT** (idx 5) — Sign-extend from specified bit position
- [x] **LOP3** (idx 6) — Three-input logic operation (arbitrary LUT)
- [ ] **ISETP** (idx 7) — Integer compare and set predicate (32-bit; re-introduced at index 288 for sm_104 with 64-bit support)
- [ ] **IABS** (idx 8) — Integer absolute value
- [x] **LEA** (idx 9) — Load effective address (shift-add)
- [x] **SHF** (idx 10) — Funnel shift (concatenate two regs, shift)
- [ ] **IDP** (idx 33) — Integer dot product (4-element)
- [ ] **IDE** (idx 34) — Integer dot expand
- [x] **IMNMX** (idx 37) — Integer min/max (32-bit only; re-introduced at indices 284–285 for sm_104 with 32/64-bit split)
- [ ] **POPC** (idx 38) — Population count (count set bits)
- [ ] **FLO** (idx 39) — Find leading one (bit scan)
- [ ] **BREV** (idx 53) — Bit reverse

## FP32 Arithmetic
- [x] **FFMA** (idx 11) — FP32 fused multiply-add
- [x] **FADD** (idx 12) — FP32 add
- [x] **FMUL** (idx 13) — FP32 multiply
- [x] **FMNMX** (idx 14) — FP32 min/max (base encoding cat. 510; re-introduced at index 220 for sm_90 with extended operand modes)
- [ ] **FSWZADD** (idx 15) — FP32 swizzle add (cross-lane partial reduction)
- [x] **FSET** (idx 16) — FP32 compare and set result register
- [ ] **FSEL** (idx 17) — FP32 select (conditional move)
- [x] **FSETP** (idx 18) — FP32 compare and set predicate
- [ ] **FCHK** (idx 40) — FP check for NaN/Inf/denorm
- [x] **MUFU** (idx 42) — Multi-function unit: RCP, RSQ, SIN, COS, EX2, LG2, RCP64H, RSQ64H

## FP64 Arithmetic
- [ ] **DFMA** (idx 122) — FP64 fused multiply-add
- [ ] **DADD** (idx 123) — FP64 add
- [ ] **DMUL** (idx 124) — FP64 multiply
- [ ] **DSETP** (idx 125) — FP64 compare and set predicate

## FP16 Packed Arithmetic
- [x] **HADD2** (idx 126) — Packed FP16x2 add
- [x] **HADD2_F32** (idx 127) — Packed FP16x2 add with FP32 accumulator  `-> HADD2`
- [x] **HFMA2** (idx 128) — Packed FP16x2 fused multiply-add
- [x] **HMUL2** (idx 129) — Packed FP16x2 multiply
- [x] **HSET2** (idx 130) — Packed FP16x2 compare and set
- [x] **HSETP2** (idx 131) — Packed FP16x2 compare and set predicate

## Type Conversion
- [ ] **I2I** (idx 35) — Integer to integer conversion (width/sign change)
- [ ] **I2IP** (idx 36) — Integer to integer, packed variant
- [ ] **F2F** (idx 43) — Float to float conversion (precision change)
- [ ] **F2F_X** (idx 44) — Float to float, extended (with carry chain)  `-> F2F`
- [ ] **F2I** (idx 45) — Float to integer
- [ ] **F2I_X** (idx 46) — Float to integer, extended  `-> F2I`
- [ ] **I2F** (idx 47) — Integer to float
- [ ] **I2F_X** (idx 48) — Integer to float, extended  `-> I2F`
- [ ] **FRND** (idx 49) — FP round to integer (within FP format)
- [ ] **FRND_X** (idx 50) — FP round, extended  `-> FRND`

## Data Movement
- [ ] **MOV** (idx 19) — Move register to register
- [ ] **SEL** (idx 20) — Predicated select (ternary conditional)
- [ ] **P2R** (idx 21) — Pack predicate registers into GPR
- [ ] **R2P** (idx 22) — Unpack GPR bits into predicate registers
- [ ] **PRMT** (idx 24) — Byte-level permute (4-byte shuffle)
- [ ] **S2R** (idx 57) — Read special register to GPR
- [ ] **CS2R_32** (idx 27) — Control/status register to GPR (32-bit)  `-> CS2R`
- [ ] **CS2R_64** (idx 28) — Control/status register to GPR (64-bit)  `-> CS2R`

## Predicate Operations
- [ ] **PLOP3** (idx 23) — Three-input predicate logic (arbitrary LUT)
- [ ] **VOTE** (idx 26) — Warp-wide vote (ballot/any/all/unanimity)
- [ ] **VABSDIFF** (idx 31) — Vector absolute difference
- [ ] **VABSDIFF4** (idx 32) — Vector absolute difference, 4-way

## Memory — Load/Store
- [ ] **LDC** (idx 89) — Load from constant memory bank c[bank][offset]
- [ ] **LDS** (idx 94) — Load from shared memory
- [ ] **STS** (idx 95) — Store to shared memory
- [ ] **LDG** (idx 96) — Load from global memory
- [ ] **STG** (idx 97) — Store to global memory
- [ ] **LDL** (idx 98) — Load from local memory (per-thread stack)
- [ ] **STL** (idx 99) — Store to local memory
- [ ] **LD** (idx 100) — Load, generic address space
- [ ] **ST** (idx 101) — Store, generic address space

## Atomic and Reduction
- [ ] **ATOM** (idx 102) — Atomic operation (generic address space)
- [ ] **ATOMG** (idx 103) — Atomic operation (global memory)
- [ ] **RED** (idx 104) — Reduction (global memory, fire-and-forget)
- [ ] **ATOMS** (idx 105) — Atomic operation (shared memory)

## Cache and Memory Control
- [ ] **QSPC** (idx 106) — Query address space type
- [ ] **CCTL_NO_SB** (idx 107) — Cache control, no scoreboard wait  `-> CCTL`
- [ ] **CCTL** (idx 108) — Cache control (invalidate/writeback/etc.)
- [ ] **CCTLL** (idx 109) — Cache control, L2 level
- [ ] **MEMBAR** (idx 111) — Memory barrier (fence)

## Control Flow
- [ ] **BRA** (idx 67) — Branch (relative)
- [ ] **BRX** (idx 68) — Branch indirect (register target)
- [ ] **JMP** (idx 69) — Jump (absolute)
- [ ] **JMX** (idx 70) — Jump indirect
- [ ] **CALL** (idx 71) — Function call
- [ ] **RET** (idx 72) — Return from function
- [ ] **BSSY** (idx 73) — Push convergence point onto branch sync stack
- [ ] **BREAK** (idx 74) — Break out of convergence region
- [ ] **EXIT** (idx 77) — Thread exit
- [ ] **KILL** (idx 76) — Kill thread (discard fragment)
- [ ] **BPT** (idx 75) — Breakpoint trap (debugger)
- [ ] **RTT** (idx 78) — Return to trap handler
- [ ] **BSYNC** (idx 79) — Branch sync (pop convergence stack, reconverge)

## Synchronization and Warp
- [ ] **BMOV_B** (idx 54) — Barrier move (barrier register, B variant)  `-> BMOV`
- [ ] **BMOV_R** (idx 55) — Barrier move (barrier register, R variant)  `-> BMOV`
- [ ] **BMOV** (idx 56) — Barrier move
- [ ] **B2R** (idx 58) — Barrier register to GPR
- [ ] **R2B** (idx 59) — GPR to barrier register
- [ ] **BAR** (idx 61) — Named barrier synchronization
- [ ] **BAR_INDEXED** (idx 62) — Barrier, indexed variant  `-> BAR`
- [ ] **DEPBAR** (idx 66) — Dependency barrier (wait for scoreboard)
- [ ] **MATCH** (idx 80) — Warp match (find lanes with same value)
- [ ] **SHFL** (idx 119) — Warp shuffle (cross-lane data exchange)
- [ ] **WARPSYNC** (idx 120) — Warp-wide synchronization barrier
- [ ] **NANOSLEEP** (idx 81) — Thread sleep for specified nanoseconds
- [ ] **NANOTRAP** (idx 82) — Nano trap (lightweight trap)

## System and Miscellaneous
- [ ] **ERRBAR** (idx 0) — Error barrier (internal pseudo-instruction)
- [ ] **NOP** (idx 25) — No-operation
- [ ] **PMTRIG** (idx 29) — Performance monitor trigger
- [ ] **CSMTEST** (idx 30) — CSM (compute shader model) test
- [ ] **LEPC** (idx 60) — Load effective PC (get current instruction address)
- [ ] **SETCTAID** (idx 63) — Set CTA (thread block) ID
- [ ] **SETLMEMBASE** (idx 64) — Set local memory base address
- [ ] **GETLMEMBASE** (idx 65) — Get local memory base address
- [ ] **YIELD** (idx 121) — Yield execution (internal, scheduler hint)

## Tensor Core (Base)
- [ ] **HMMA_16** (idx 132) — FP16 matrix multiply-accumulate, 16-wide  `-> HMMA`
- [ ] **HMMA_32** (idx 133) — FP16 matrix multiply-accumulate, 32-wide  `-> HMMA`
- [ ] **IMMA** (idx 134) — Integer matrix multiply-accumulate

## Uniform Register Operations
- [ ] **UBREV** (idx 138) — Uniform bit reverse
- [ ] **UBMSK** (idx 139) — Uniform bitmask
- [ ] **UCLEA** (idx 140) — Uniform clear address
- [ ] **UISETP** (idx 141) — Uniform integer set-predicate
- [ ] **ULDC** (idx 142) — Uniform load constant
- [ ] **ULEA** (idx 143) — Uniform load effective address
- [ ] **UP2UR** (idx 144) — Uniform predicate to uniform register
- [ ] **ULOP3** (idx 145) — Uniform three-input logic
- [ ] **UPLOP3** (idx 146) — Uniform predicate three-input logic
- [ ] **USEL** (idx 147) — Uniform select
- [ ] **USGXT** (idx 148) — Uniform sign-extend
- [ ] **UFLO** (idx 149) — Uniform find leading one
- [x] **UIADD3** (idx 150) — Uniform three-input integer add
- [x] **UIMAD** (idx 151) — Uniform integer multiply-add
- [ ] **UMOV** (idx 152) — Uniform move
- [ ] **UPRMT** (idx 153) — Uniform byte permute
- [ ] **VOTEU** (idx 154) — Uniform vote
- [ ] **UPOPC** (idx 155) — Uniform population count
- [ ] **USHF** (idx 156) — Uniform funnel shift

## Additional sm_73 Operations
- [ ] **SCATTER** (idx 157) — Scatter write
- [ ] **F2FP** (idx 158) — Float to float, packed conversion
- [ ] **HMMA_1688** (idx 159) — FP16 MMA, 16x8x8 shape  `-> HMMA`
- [ ] **HMMA_16816** (idx 160) — FP16 MMA, 16x8x16 shape  `-> HMMA`
- [ ] **BMMA** (idx 161) — Binary (1-bit) matrix multiply-accumulate
- [ ] **R2UR** (idx 164) — GPR to uniform register
- [ ] **MOVM** (idx 165) — Move with mask
- [ ] **LDSM** (idx 166) — Load from shared memory to matrix register
- [ ] **LDTRAM** (idx 167) — Load from TRAM (transposed shared memory)
- [ ] **S2UR** (idx 169) — Special register to uniform register
- [ ] **BRXU** (idx 170) — Branch indirect, uniform target
- [ ] **GATHER** (idx 173) — Gather (multi-address load)
- [ ] **GENMETADATA** (idx 174) — Generate metadata (for sparse MMA)
- [ ] **SPMETADATA** (idx 175) — Sparse metadata
- [ ] **BMMA_88128** (idx 176) — Binary MMA, 8x8x128 shape  `-> BMMA`
- [ ] **BMMA_168128** (idx 177) — Binary MMA, 16x8x128 shape  `-> BMMA`
- [ ] **BMMA_168256** (idx 178) — Binary MMA, 16x8x256 shape  `-> BMMA`
- [ ] **CLMAD** (idx 179) — Carry-less multiply-add (GF(2) arithmetic)
- [ ] **DMMA** (idx 180) — FP64 matrix multiply-accumulate (Ampere; encoding category 434; re-introduced at index 215 for Hopper with different TC path)
- [ ] **HMMA_SP_1688** (idx 181) — FP16 sparse MMA, 16x8x8  `-> HMMA`
- [x] **HFMA2_MMA** (idx 182) — FP16 FMA2, MMA variant  `-> HFMA2`
- [ ] **HMNMX2** (idx 183) — Packed FP16x2 min/max
- [ ] **IMMA_88** (idx 184) — Integer MMA, 8x8 shape  `-> IMMA`
- [ ] **IMMA_SP_88** (idx 185) — Integer sparse MMA, 8x8  `-> IMMA`
- [ ] **IMMA_16816** (idx 186) — Integer MMA, 16x8x16  `-> IMMA`
- [ ] **IMMA_16832** (idx 187) — Integer MMA, 16x8x32  `-> IMMA`
- [ ] **IMMA_SP_16832** (idx 188) — Integer sparse MMA, 16x8x32  `-> IMMA`
- [ ] **ARRIVES** (idx 189) — Async barrier arrive signal
- [ ] **LDGDEPBAR** (idx 190) — Load-global dependency barrier
- [ ] **LDGSTS** (idx 191) — Load-global, store-to-shared (async copy)
- [ ] **REDUX** (idx 192) — Warp-wide reduction (uniform result)
- [ ] **F2IP** (idx 195) — Float to integer, packed
- [ ] **UF2FP** (idx 196) — Uniform float to float, packed
- [ ] **I2FP** (idx 197) — Integer to float, packed

## CGA Barriers and Synchronization
- [ ] **ACQBLK** (idx 207) — Acquire block (CTA resource acquisition)  `-> ACQBULK`
- [ ] **CGABAR_ARV** (idx 208) — CGA barrier arrive  `-> UCGABAR_ARV`
- [ ] **CGABAR_GET** (idx 209) — CGA barrier get (query state)  `-> UCGABAR_GET`
- [ ] **CGABAR_SET** (idx 210) — CGA barrier set  `-> UCGABAR_SET`
- [ ] **CGABAR_WAIT** (idx 211) — CGA barrier wait  `-> UCGABAR_WAIT`
- [ ] **CGAERRBAR** (idx 212) — CGA error barrier

## Collective and Election
- [ ] **DMMA** (idx 215) — FP64 matrix multiply-accumulate (Hopper re-introduction; encoding category 515 vs 434 for index 180; uses warpgroup-aware tensor core path, shared dispatch with CVTA at case 0xD6/0xD7 in sub_6575D0)
- [ ] **ELECT** (idx 216) — Elect a leader lane in warp
- [ ] **ENDCOLLECTIVE** (idx 217) — End collective operation scope

## Fences
- [ ] **FENCE_G** (idx 218) — Fence, global scope  `-> FENCE`
- [ ] **FENCE_S** (idx 219) — Fence, shared/CTA scope  `-> FENCE`
- [ ] **FMNMX** (idx 220) — FP32 min/max (Hopper re-introduction; encoding category 534 vs 510 for index 14; adds 5-entry operand sub-mode table via dword_2026FC0 for extended rounding/precision modes not in base encoding)

## GMMA (Group Matrix Multiply-Accumulate)
- [ ] **GMMA** (idx 221) — Group (warpgroup) matrix multiply-accumulate  `-> HGMMA/IGMMA/BGMMA/QGMMA`

## Memory Extensions
- [ ] **LDCU** (idx 222) — Load constant, uniform (warp-coherent constant load)  `-> LDC variant? (unresolved)`
- [ ] **LEPC** (idx 223) — Load effective PC (sm_90 variant)
- [ ] **PREEXIT** (idx 225) — Pre-exit (cleanup before thread exit)
- [ ] **R2UR_H** (idx 226) — Register to uniform register, high half  `-> R2UR`
- [ ] **REDAS** (idx 227) — Reduction, async (fire-and-forget with arrive)

## Configuration
- [ ] **SETMAXREG** (idx 228) — Set maximum register count for dynamic partitioning  `-> USETMAXREG`
- [ ] **SETSMEMSIZE** (idx 229) — Set shared memory size dynamically  `-> USETSHMSZ`
- [ ] **STAS** (idx 230) — Store async (to shared, with barrier)
- [ ] **STSM** (idx 231) — Store to shared memory, matrix layout

## Synchronization Extensions
- [ ] **SYNCS_BASIC** (idx 232) — Sync scope, basic  `-> SYNCS`
- [ ] **SYNCS_LD_UNIFM** (idx 233) — Sync scope with uniform load  `-> SYNCS`

## Uniform Block Operations
- [ ] **UBLKCP** (idx 234) — Uniform block copy
- [ ] **UBLKRED** (idx 235) — Uniform block reduction
- [ ] **UBLKPF** (idx 236) — Uniform block prefetch
- [ ] **ULEPC** (idx 238) — Uniform load effective PC
- [ ] **UTMACCTL** (idx 240) — TMA cache control
- [ ] **UTMACMDFLUSH** (idx 241) — TMA command flush
- [ ] **UTMALDG** (idx 242) — TMA load global
- [ ] **UTMAPF** (idx 243) — TMA prefetch
- [ ] **UTMREDG** (idx 244) — TMA reduction global  `-> UTMAREDG`
- [ ] **UTMALST** (idx 245) — TMA load/store  `-> UTMASTG(?)`

## Vector Min/Max Extensions
- [ ] **VHMNMX** (idx 246) — Vector half min/max (FP16x2)
- [ ] **VIADD** (idx 247) — Vector integer add
- [ ] **VIADDMNMX** (idx 248) — Vector integer add with min/max
- [ ] **VIMNMX** (idx 249) — Vector integer min/max
- [ ] **VIMNMX3** (idx 250) — Vector integer three-input min/max
- [ ] **WARPGROUP** (idx 251) — Warpgroup collective operation

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
