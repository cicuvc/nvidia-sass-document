# TEX — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Filtered sampled-texture fetch with implicit derivatives and sampler state.

## Graphics-observed semantics

`texture(sampler2D, uv)` lowers to `TEX`. Representative sm75 SASS:

```text
TEX.SCR.NODEP R2, R0, R4, R5, 0x1e, 0x0, 2D
```

`R4/R5` supply coordinates, `R0..R3` receive RGBA, `.SCR` indicates
screen-space sampling, and `.NODEP` controls the client dependency bit. The
immediate pair selects the texture/sampler descriptor.

Bindless sampled textures use the `.B` form:

```text
LDC R6, c[0x1e][R6]
TEX.SCR.B.NODEP R2, R0, R4, R6, 2D
```

Here `Rb=R6` is the dynamically loaded texture/sampler pointer. There is no
separate bindless mnemonic.

On sm120, the compiler first unpacks the descriptor:

```text
LDCU.TEXUNPACK UR4, c[0x1e][URZ]
TEX.SCR.DXY.NODEP R2, R0, R4, R5, UR4, 2D
```

`.DXY` marks the sm120 derivative model; `.B` remains the register-pointer
bindless form.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `tex_b_noConst_` | `0x1d61` | `[/b] /RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URe TEXPARAMA:paramA *:wmsk` |
| `tex_b_urc_` | `0x361` | `[/b] /RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc :URe TEXPARAMA:paramA *:wmsk` |
| `tex_scr_b_noConst_` | `0x1d61` | `[/scr] [/b] /RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URe TEXPARAMA:paramA *:wmsk` |
| `tex_scr_b_urc_` | `0x361` | `[/scr] [/b] /RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc :URe TEXPARAMA:paramA *:wmsk` |
| `tex_scr_urc_` | `0x1f60` | `[/scr] /RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe @:tid8 TEXPARAMA:paramA *:wmsk` |
| `tex_urc_` | `0x1f60` | `/RM16("norm16"):rm16 /LODLC_tex("nolodlc_tex"):lodlc /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /DC("nodc"):dc /COP("EN"):cop /DIV("nodiv"):div /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe @:tid8 TEXPARAMA:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32 + (((rm16==`RM16@norm16)) && ((wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"3") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"5") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"6") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"7") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"9") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"10") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"11") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"12") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"13") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"14") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"15")))*32` |
| `ILABEL_Ra_SIZE` | `32 + ((((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*96 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_2D)))*64 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)))*96 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)` |
| `ILABEL_Rb_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)` |
| `ILABEL_URc_SIZE` | `64` |
| `ILABEL_URe_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32 + ((((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((paramA==`TEXPARAMA@CUBE) || (paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*96 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_2D)))*64 + (((uai==`UAI@nouai)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)))*96 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((uai==`UAI@UAI)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@ULB.LC)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)` |
| `ISRC_B_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@nolodlc_tex) || (lodlc==`LODLC_tex@LZ) || (lodlc==`LODLC_tex@LC) || (lodlc==`LODLC_tex@ULB) || (lodlc==`LODLC_tex@ULL) || (lodlc==`LODLC_tex@ULC) || (lodlc==`LODLC_tex@ULB.LC)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((lodlc==`LODLC_tex@LB) || (lodlc==`LODLC_tex@LL) || (lodlc==`LODLC_tex@LB.LC) || (lodlc==`LODLC_tex@LB.ULC)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@nolodlc_tex)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULB)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_CUBE)) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"3D")) && ((lodlc==`LODLC_tex@ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@ULB.LC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_2D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@ARRAY_1D)) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"2D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((dc==`DC@nodc)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((dc==`DC@DC)) && ((paramA==`TEXPARAMA@"1D")) && ((lodlc==`LODLC_tex@LB.ULC)))*32)` |
| `ISRC_C_SIZE` | `64` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TEX_B_URc`, ``SIDL_NAMES@TEX_B_noConst`, ``SIDL_NAMES@TEX_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tex_b_noConst_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [60:60] | `scr` | 1 | 0 |
| [80:79] | `rm16` | 2 | `rm16` |
| [89:87]+[59:59] | `lodlc` | 4 | `lodlc` |
| [57:56] | `aoffi` | 2 | `aoffi` |
| [58:58] | `uai` | 1 | `uai` |
| [78:78] | `mode` | 1 | `dc` |
| [86:84] | `cop` | 3 | `cop` |
| [77:76] | `op` | 2 | `div` |
| [90:90] | `memdesc` | 1 | `nodep` |
| [83:81] | `Pu` | 3 | `Pu` |
| [71:64] | `Ra_URc` | 8 | `Rd2` |
| [23:16] | `Rd` | 8 | `Rd` |
| [31:24] | `Ra` | 8 | `Ra` |
| [39:32] | `Rb` | 8 | `Rb` |
| [55:48] | `URe` | 8 | `URe` |
| [63:61] | `paramA` | 3 | `paramA` |
| [75:72] | `wmsk` | 4 | `wmsk` |
| [121:116] | `req_bit_set` | 6 | `req_bit_set` |
| [115:113] | `src_rel_sb` | 3 | VarLatOperandEnc(src_rel_sb) |
| [112:110] | `dst_wr_sb` | 3 | VarLatOperandEnc(dst_wr_sb) |
| [103:102] | `pm_pred` | 2 | `pm_pred` |
| [124:122]+[109:105] | `opex` | 8 | TABLES_opex_0(batch_t,usched_info) |

## Legal-encoding conditions

| CLASS | error | message |
|---|---|---|
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_b_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D____DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE____DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D____DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D____DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE____DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D____DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D____) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D____DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE____) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE____DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D____) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D____DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D____) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D____DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D____) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D____DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D___AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D___UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D____) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D____DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC___DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI__DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE____DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE___UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D___AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D__UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LB_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULB_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULBLC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: CUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAYCUBE_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC___DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC__UAOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI__DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_AOFFI_DC) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LBULC_UAI_UAOFFI_DC) |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid div field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tex_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tex_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tex_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Uniform register URc is misaligned |
| `tex_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: .AOFFI/.UAOFFI are not supported with CUBE Map textures) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Depth comparison not valid with 3D textures) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tex_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAOFFI) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB cannot be used with UAI) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: All three of UAI/ULC and UAOFFI cannot be specified together) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL/ULB/ULC cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tex_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Descriptor contents beyond the operand behavior are not decoded here.
