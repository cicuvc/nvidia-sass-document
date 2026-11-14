# TLD — sm120 (Blackwell (GB20x)) graphics instruction

<!-- notes-status -->
**Status:** active  
**Evidence:** sm75+sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-11-14  
**Probe:** `experiments/graphics_batch_t/vulkan_graphics.c`, `extract_pipeline_binary.py`, `gpucomp_spy.c`  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `sm120.json`

## Conclusion

Direct LOD texel fetch; subpassLoad lowers to a zero-LOD array-texture fetch.

## Graphics-observed semantics

`subpassLoad(input_color)` lowers to `TLD`, not `TEX`, `SULD`, or `LDG`:

```text
TLD.SCR.LZ.NODEP R2, R0, R6, R5, 0x1e, 0x0, ARRAY_2D
```

The input attachment is represented as an `ARRAY_2D` texture:

- `a[0x64]` supplies the attachment layer.
- `a[0x70]/a[0x74]` supply fragment X/Y.
- `.LZ` selects LOD zero.
- the result is written to `R0..R3`.

sm120 uses the same array fetch after descriptor unpacking:

```text
LDCU.HDRUNPACK UR4, c[0x1e][URZ]
TLD.SCR.LZ.NODEP R2, R0, R6, R5, UR4, ARRAY_2D
```

This path bypasses the sampler filtering used by `TEX`.

<!-- generated:isa-notes:begin -->
## Variants

| CLASS | opcode | operands (FORMAT-derived) |
|---|---|---|
| `tld_b_noConst_` | `0x1d67` | `[/b] /RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URe PARAMA_TLD:paramA *:wmsk` |
| `tld_b_urc_` | `0x1f67` | `[/b] /RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc :URe PARAMA_TLD:paramA *:wmsk` |
| `tld_scr_b_noConst_` | `0x1d67` | `[/scr] [/b] /RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URe PARAMA_TLD:paramA *:wmsk` |
| `tld_scr_b_urc_` | `0x1f67` | `[/scr] [/b] /RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra NonZeroRegister:Rb :URc :URe PARAMA_TLD:paramA *:wmsk` |
| `tld_scr_urc_` | `0x1f66` | `[/scr] /RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe @:tid8 PARAMA_TLD:paramA *:wmsk` |
| `tld_urc_` | `0x1f66` | `/RM16("norm16"):rm16 [/lodlc] /AOFFI("noaoffi"):aoffi /UAI("nouai"):uai /COP("EN"):cop /MS("noms"):ms /CL("nocl"):cl /NODEP("nonodep"):nodep :Pu :Rd2 :Rd NonZeroRegister:Ra :Rb :URc :URe @:tid8 PARAMA_TLD:paramA *:wmsk` |

## Properties

| property | value(s) |
|---|---|
| `IDEST_SIZE` | `32 + (((rm16==`RM16@norm16)) && ((wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"3") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"5") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"6") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"7") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"9") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"10") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"11") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"12") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"13") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"14") || (wmsk==`WMSK_1_2_3_4_5_6_7_8_9_10_11_12_13_14_15@"15")))*32` |
| `ILABEL_Ra_SIZE` | `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)`, `32 + (((paramA==`PARAMA_TLD@"2D"))*32 + ((paramA==`PARAMA_TLD@"3D"))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_TLD@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_TLD@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)))*32)` |
| `ILABEL_Rb_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*64 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)` |
| `ILABEL_URc_SIZE` | `32` |
| `ILABEL_URe_SIZE` | `32` |
| `INSTRUCTION_TYPE` | `INST_TYPE_DECOUPLED_RD_WR_SCBD` |
| `ISRC_A_SIZE` | `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)`, `32 + (((paramA==`PARAMA_TLD@"2D"))*32 + ((paramA==`PARAMA_TLD@"3D"))*64 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_TLD@ARRAY_1D)))*32 + (((uai==`UAI@nouai)) && ((paramA==`PARAMA_TLD@ARRAY_2D)))*64 + (((uai==`UAI@UAI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)))*32)` |
| `ISRC_B_SIZE` | `32 + ((((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*32 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*32 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@noms) || (ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*64 + (((aoffi==`AOFFI@noaoffi) || (aoffi==`AOFFI@UAOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ) || (lodlc==`LODLC_tld@ULL)))*64 + (((aoffi==`AOFFI@AOFFI)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*96)`, `32 + ((((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LZ)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@LL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_2D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@ARRAY_1D)) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"2D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@AOFFI)) && ((paramA==`PARAMA_TLD@"1D")) && ((ms==`MS@MS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@nouai)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@noaoffi)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@noms)) && ((lodlc==`LODLC_tld@ULL)))*32 + (((uai==`UAI@UAI)) && ((aoffi==`AOFFI@UAOFFI)) && ((paramA==`PARAMA_TLD@"3D")) && ((ms==`MS@UMS)) && ((lodlc==`LODLC_tld@ULL)))*32)` |
| `ISRC_C_SIZE` | `32` |
| `ISRC_E_SIZE` | `32` |
| `MEM_SCBD` | `NONE` |
| `MEM_SCBD_TYPE` | `BARRIER_INST` |
| `MIN_WAIT_NEEDED` | `1` |
| `SIDL_NAME` | ``SIDL_NAMES@TLD_B_URc`, ``SIDL_NAMES@TLD_B_noConst`, ``SIDL_NAMES@TLD_URc` |
| `VALID_IN_SHADERS` | `ISHADER_ALL` |
| `VIRTUAL_QUEUE` | `$VQ_TEX` |

## Encoding

Bit map of the first layout (`tld_b_noConst_`); other classes differ
through the modifier fields enumerated in *Variants*:

| bits | field | width | source |
|---|---|---:|---|
| [14:12] | `Pg` | 3 | `Pg` |
| [15:15] | `Pg_not` | 1 | Pg@not |
| [91:91]+[11:0] | `opcode` | 13 | Opcode |
| [60:60] | `scr` | 1 | 0 |
| [80:79] | `rm16` | 2 | `rm16` |
| [88:87] | `lodlc` | 2 | `lodlc` |
| [57:56] | `aoffi` | 2 | `aoffi` |
| [58:58] | `uai` | 1 | `uai` |
| [86:84] | `cop` | 3 | `cop` |
| [78:77] | `ms` | 2 | `ms` |
| [76:76] | `memdesc` | 1 | `cl` |
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
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_MS) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI_MS) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI_MS) |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_b_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_MS) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI_MS) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI_MS) |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_MS) |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_noConst_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_scr_b_noConst_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Rb |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Rb can't be RZ) |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI__MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ_UAI_UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL___UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL__UAOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI__MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI__MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL___UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL__UAOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI__UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL_UAI_UAOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL___MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL__UAOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI__MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_MS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_AOFFI_UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL_UAI_UAOFFI_MS) |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_b_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_scr_b_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: Ra can't be RZ) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LZ+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LZ+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LZ+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_LL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_ULL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_ULL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI__) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI__UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 1D_ULL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI__) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI__UMS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_AOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_UAOFFI_) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_UAOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LZ+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LZ+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_LL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY1D_LL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 2D_LL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI__MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_AOFFI_) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_AOFFI_UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_LL+UAI_UAOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ARRAY2D_ULL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+_AOFFI_MS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: 3D_ULL+UAI_AOFFI_MS) |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_scr_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_scr_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid rm16 field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid lodlc field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid aoffi field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid cop field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid ms field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid paramA field value |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid wmsk field value |
| `tld_urc_` | `OOR_REG_ERROR` | Register Rd2 is out of range |
| `tld_urc_` | `OOR_REG_ERROR` | Register Rd is out of range |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Ra is out of range |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Disallowed register Ra |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Register Rb is out of range |
| `tld_urc_` | `OOR_REG_ERROR` | Uniform register URc is out of range |
| `tld_urc_` | `OOR_REG_ERROR` | Uniform register URe is out of range |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR` | Invalid combination of batch_t, usched_info |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS/UMS limitations) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: MS) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_MS) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: AOFFI_MS) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: LOD_AOFFI_MS) |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `OOR_REG_ERROR` | Register is out of range |
| `tld_urc_` | `MISALIGNED_REG_ERROR` | Register incorrectly aligned |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be used with UMS) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UMS cannot be specified when UAI and UAOFFI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: ULL cannot be specified when UAI and UAOFFI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when UMS and UAOFFI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when ULL and UAOFFI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when UMS and UAI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAOFFI cannot be specified when ULL and UAI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified when PARAM_A is 3D and UAOFFI are specified) |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination |
| `tld_urc_` | `ILLEGAL_INSTR_ENCODING_ERROR` | Invalid instruction combination (reason: UAI cannot be specified for non-array ParamA values) |

## Pipe

Pipe suffix(es) in this dump: `mio_pipe`.
<!-- generated:isa-notes:end -->

## Open questions

Other TLD modes such as shadow/compare variants were not isolated in this Vulkan probe.
