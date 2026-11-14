#!/usr/bin/env python3
"""Generate sm75/sm120 notes for the graphics instructions researched locally."""

from __future__ import annotations

import pathlib

from isa_coverage import (
    ARCHES,
    BEGIN,
    END,
    by_mnemonic,
    load_db,
    render_conditions,
    render_encoding,
    render_properties,
    render_variants,
)


REPO = pathlib.Path(__file__).resolve().parent.parent
ARCHES_TO_WRITE = ("sm75", "sm120")

COMMON_PROBES = (
    "`experiments/graphics_batch_t/vulkan_graphics.c`, "
    "`extract_pipeline_binary.py`, `gpucomp_spy.c`"
)

NOTES = {
    "IPA": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Pixel-shader attribute interpolation read from rasterizer-produced attribute memory.",
        "body": """
## Graphics-observed semantics

`IPA` is the fragment-stage attribute interpolator. The compiled shader names
an attribute through the scaled `a[...]` address and receives one interpolated
component in a normal 32-bit GPR.

Observed Vulkan GLSL lowerings:

| source construct | sm75 lowering |
|---|---|
| `smooth in vec4` | four `IPA.PASS` reads plus `IPA.PASS a[0x7c]` perspective factor |
| perspective correction | `MUFU.RCP` of `a[0x7c]`, then component multiplies |
| `noperspective in vec4` | four `IPA.PASS` reads, with no perspective factor |
| `flat in vec4` | four `IPA.CONSTANT` reads |
| `centroid in vec4` | `IPA.PASS.CENTROID` |
| `interpolateAtOffset/Sample` | `IPA.PASS.OFFSET` with an evaluation offset |

The perspective divisor is explicit in the instruction stream. It is not a
separate top-level `IPA` mode. A shared smooth varying needs only one
`a[0x7c]` factor read.

In the tested fragment shaders, `BATCH_START` appears on the first shader
instruction, often the first `IPA` or a preceding constant move. No tested
fragment shader emitted a paired `BATCH_END`.

sm120 keeps the same source semantics and resource handling through uniform
registers where applicable. The generated variants below come from each
architecture's own ISA dump.
""",
        "open": "No direct test isolated every `IPA.STATE` use. Barycentric helper behavior is documented separately through `LDTRAM`.",
    },
    "ALD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Graphics attribute-space load used for vertex inputs and draw builtins.",
        "body": """
## Graphics-observed semantics

`ALD` loads from the graphics front-end attribute address space. Static
attributes use immediate `a[imm]`; dynamic arrays use a base plus register
offset.

Observed vertex mappings:

| source value | sm75 address |
|---|---|
| input `location=0` (`vec4`) | `a[0x80]` |
| input `location=1` (`vec4`) | `a[0x90]` |
| `gl_VertexIndex` | `a[0x2fc]` |
| raw instance ID | `a[0x2f8]` |

Representative lowering:

```text
ALD.128 R0, a[0x80]
ALD R4, a[0x90]
ALD R5, a[0x94]
ALD R6, a[0x98]
ALD R7, a[0x9c]
```

`ALD.128` consumes a naturally aligned four-register destination. Scalar
loads can gather individual components. Geometry/tessellation prologues can
feed an `ISBERD` result into the dynamic address form, for example
`ALD.128 ..., a[base], Roffset`.

This is not the CUDA parameter path (`LDC`) or the global-memory path (`LDG`).
It addresses the graphics stage's logical attribute storage.
""",
        "open": "The physical layout behind the logical `a[...]` address is not exposed as a raw pointer.",
    },
    "AST": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Graphics attribute-space store used for clip position, varyings, and stage outputs.",
        "body": """
## Graphics-observed semantics

`AST` writes graphics attribute storage used to carry stage outputs to the
next fixed-function stage.

Observed vertex output slots:

| output | sm75 SASS |
|---|---|
| `gl_Position` | `AST.128 a[0x70], R0` |
| varying `location=0` | `AST.128 a[0x80], R4` |
| `gl_Layer` | `AST a[0x64], R...` |
| `gl_ViewportIndex` | `AST a[0x68], R...` |
| `gl_PointSize` | `AST a[0x6c], R...` |

The compiler selects `AST.128` when four contiguous source registers are
available and scalar `AST` when components are produced separately. Vertex,
geometry and tessellation paths use the same logical attribute-store family.

`AST` does not write ordinary global memory. It supplies graphics-stage
records consumed by clipping, primitive assembly, rasterization, or
subsequent shader stages.
""",
        "open": "The post-shader transport between logical attributes and rasterizer physical slots remains opaque.",
    },
    "CSMTEST": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_vertex_attr.vert`, `probe_vertex_ssbo.vert`, `vulkan_graphics.c`",
        "conclusion": "Combines clip/guard-band predicates for a vertex-stage early-exit decision.",
        "body": """
## Graphics-observed semantics

A passthrough vertex shader uses `CSMTEST` after six clip-bound comparisons:

```text
FSETP...                         ; X/Y/Z against positive and negative bounds
FMUL.FTZ R5, R3, UR5             ; scale clip-space W
CSMTEST.RA.F.AND ...
CSMTEST.A.FCSM_TR.AND P0, ...
@P0 EXIT
```

`SR_WSCALEFACTOR_XY/Z` supplies viewport scale factors used before the bound
comparisons. The two `CSMTEST` operations combine the six predicates into the
final predicate consumed by the early `EXIT`.

The test is interleaved with setup stores but depends only on previously
generated predicates; it does not itself load a GLSL builtin. sm75 and sm120
use the same structural sequence with generation-specific scheduling controls.
""",
        "open": "Individual `RA`/`FCSM_TR` modifier semantics were not isolated beyond the combined clip-rejection sequence.",
    },
    "EXIT": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_const.frag`, `probe_atexit.frag`, `vulkan_graphics.c`, `gpucomp_spy.c`",
        "conclusion": "Operand-less shader termination with graphics output export performed by fixed-function state.",
        "body": """
## Graphics-observed semantics

Fragment color outputs are staged in GPRs and committed by an operand-less
`EXIT`:

```text
IMAD.MOV.U32 R0, RZ, RZ, 1.0
MOV           R1, 2.0
MOV           R2, 3.0
MOV           R3, 4.0
EXIT
```

There is no per-attachment store operand. Pipeline state selects attachment
indices, formats, blend equations, masks, and ROP behavior.

### Fragment epilogue search

Static pipeline-binary scans and live `/proc/<pid>/mem` scans found no SASS
epilogue after `EXIT`; the following slots were padding (`BRA 0x0; NOP`).
Replacing the normal EXIT control with `EXIT.NO_ATEXIT` did not change pixels,
and patching the post-EXIT slots to execute a store still did not affect the
result. `ATEXIT_PC` and `TRAP_RETURN_PC` both read zero in ordinary fragment
invocations.

This supports an implicit fixed-function export at `EXIT`, not a hidden SASS
continuation. If a continuation exists, it is not exposed through the tested
CBU registers and is not reached by fall-through.

### `gl_FragDepth`

A constant `gl_FragDepth` value can be folded into pipeline metadata with no
shader instruction. A dynamic value is computed into a compiler-selected GPR
and consumed by the late depth path after `EXIT`. One color output placed the
value in `R5`; two color outputs placed it in `R9`. Patching the producing
instruction from `R5` to `R4` left the old `R5` value to be exported, proving
the fixed-function path consumed that register.
""",
        "open": "The fixed-function continuation or state machine behind color/depth export is not represented as shader SASS.",
    },
    "SULD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Surface/image load; descriptor selection is separate from the X/Y coordinate operand.",
        "body": """
## Graphics-observed semantics

`imageLoad()` lowers to a surface load. A representative sm75 form is:

```text
SULD.P.2D.CTA.IGN R0, [R4], 0x1e, 0x0
```

- `Rd=R0`: destination quad.
- `Ra=R4`: integer X/Y coordinate pair.
- `0x1e, 0x0`: constant-bank location selecting the surface header.
- `.P`, `.2D`, `.CTA`, and `.IGN`: predicate, dimensionality,
  memory-scope/order controls in the emitted form.

The instruction does not contain a linear byte address. Bindless storage
images use a register descriptor instead:

```text
LDC R8, c[0x1e][R8]
SULD.P.2D.CTA.IGN R0, [R6], R8
```

The dynamic index is scaled and masked before `LDC`. In the tested image all
array entries referenced the same view, so all captured selectors were `9`.

sm120 loads the descriptor through `LDCU`, masks it to 20 bits, and can move it
to a uniform register with `R2UR`:

```text
LDCU UR4, c[0x1e][URZ]
SULD.P.2D.IGN R0, [R4], UR4
```

## Backing-address findings

CUDA external-memory interop proved that the backing allocation is ordinary
device memory. For a 64x64 RGBA8 optimal image, the CUDA-visible base plus a
recovered tiling bit permutation addressed every texel. The selector itself is
not a VA; conversion continues inside the hardware surface-header path.
""",
        "open": "The surface-header table base and selector-to-header lookup remain unresolved.",
    },
    "SUST": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Surface/image store with the same descriptor-selection model as SULD.",
        "body": """
## Graphics-observed semantics

`imageStore()` lowers to `SUST`, using the same coordinate and descriptor
inputs as the matching `SULD`:

```text
SUST.P.2D.CTA.IGN [R4], R8, 0x1e, 0x0
```

- `Ra=R4`: integer X/Y coordinate pair.
- `Rb=R8`: source component quad.
- immediate `0x1e, 0x0`: surface-header selector.

The bindless form replaces the immediate with a register selector:

```text
LDC R8, c[0x1e][R8]
SUST.P.2D.CTA.IGN [R6], R0, R8
```

sm120 likewise uses `LDCU`/`ULOP3` and an optional `R2UR` path for nonuniform
descriptor selection.

There is no generic `STG` in the shader. The texture/surface unit resolves the
selector, format, tiling and address calculation. CUDA interop confirmed that
the eventual backing allocation is device memory addressable through a CUDA
device pointer, with tiling applied by the surface path.
""",
        "open": "Selector-to-backing-allocation lookup remains driver/hardware-internal.",
    },
    "TEX": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Filtered sampled-texture fetch with implicit derivatives and sampler state.",
        "body": """
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
""",
        "open": "Descriptor contents beyond the operand behavior are not decoded here.",
    },
    "TLD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Direct LOD texel fetch; subpassLoad lowers to a zero-LOD array-texture fetch.",
        "body": """
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
""",
        "open": "Other TLD modes such as shadow/compare variants were not isolated in this Vulkan probe.",
    },
    "TXD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Gradient texture fetch consuming an explicit 2D X/Y gradient pair.",
        "body": """
## Graphics-observed semantics

`textureGrad()` lowers to `TXD`:

```text
TXD.NODEP R2, R0, R4, R8, 0x1e, 0x0, 2D
```

`Ra=R4` supplies coordinates and `Rb=R8..R11` supplies the 128-bit gradient
pair `{dX.xy, dY.xy}`. The shader first constructs this pair using the same
`SHFL.BFLY` + `FSWZADD` derivative sequence used by `dFdx/dFdy`.

Unlike `TEX`, `TXD` does not derive LOD from implicit screen derivatives.
sm120 uses the same gradient operand and adds `.DXY` to the derivative
combine instructions:

```text
TXD.NODEP R2, R0, R4, R8, UR4, 2D
```
""",
        "open": "",
    },
    "TMML": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": COMMON_PROBES,
        "conclusion": "Texture mip/lod query that returns LOD data without sampling a texel.",
        "body": """
## Graphics-observed semantics

`textureQueryLod()` lowers to two `TMML.LOD` operations:

```text
TMML.LOD.NODEP RZ, R6, R4, 0x1e, 0x0, 2D, 0x2
TMML.LOD.NODEP RZ, R7, R4, 0x1e, 0x0, 2D, 0x1
```

The trailing immediate selects which LOD result is produced. The compiler
converts the returned values to float and scales by `1/256` to match GLSL.
No texel fetch occurs.

sm120 uses the same two `TMML.LOD.DXY` operations with a uniform descriptor:

```text
TMML.LOD.DXY.NODEP RZ, R6, R4, UR4, 2D, 0x1
TMML.LOD.DXY.NODEP RZ, R0, R4, UR4, 2D, 0x2
```

Scheduling can reverse the two result-producing instructions; the trailing
selector identifies them.
""",
        "open": "The exact fixed-point scaling of every TMML result mode was not exhaustively enumerated.",
    },
    "FOOTPRINT": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_fragment_footprint*.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`",
        "conclusion": "Hardware texture-footprint query for implicit or explicit derivatives.",
        "body": """
## Graphics-observed semantics

`FOOTPRINT` computes the texel-group footprint of an equivalent filtered
texture access without returning sampled colors.

Primary modes:

| mode | meaning |
|---|---|
| `FOOTPRINT.TEX` | implicit screen-space derivatives |
| `FOOTPRINT.TXD` | explicit X/Y gradients |

LOD controls include `LB`, `LC`, `LL`, `LB.LC`, `LC.FDV`, and `LZ`.
`COARSE` requests coarse mip granularity; the default is fine.

Representative sm75 forms:

```text
FOOTPRINT.SCR.TEX.NODEP P0, R6, R4, R6, R4, 0x1e, 0x0, 2D
FOOTPRINT.SCR.TEX.LL.NODEP P0, R4, R6, R6, R4, 0x1e, 0x0, 2D
FOOTPRINT.TXD.NODEP P0, R8, R0, R4, R8, 0x1e, 0x0, 2D
```

The operation returns packed footprint data in two 64-bit destination pairs
and validity in `Pu`. The GLSL result exposes anchor, offset, a 64-bit mask of
8x8 texel groups, LOD, and granularity.

sm120 unpacks the descriptor into `UR4` and adds `.DXY` to implicit forms.
""",
        "open": "The full granularity-code table is supplied by the NV extension specification and was not independently enumerated.",
    },
    "PIXLD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_fragment_sample*.frag`, `probe_fragment_fullycovered.frag`, `vulkan_graphics.c`",
        "conclusion": "Pixel-shader load of sample and coverage state.",
        "body": """
## Graphics-observed semantics

`PIXLD` has no source operands and writes one 32-bit result plus optional
predicate.

Observed Vulkan GLSL mappings:

| source | SASS |
|---|---|
| `gl_SampleID` | `PIXLD.MY_INDEX R0` |
| `gl_SampleMaskIn[0]` | `PIXLD.MY_INDEX`, then `PIXLD.COVMASK` |
| `gl_FragFullyCoveredNV` | `PIXLD.INNER_COVERAGE R0` |

`gl_SamplePosition` also reads `MY_INDEX`, then performs `LDC.U8` from the
sample-position table in `c[0x0][0x32d0]`.

`gl_HelperInvocation` is not PIXLD; it lowers to `S2R SR_THREAD_KILL`.
`interpolateAtCentroid` uses `IPA.PASS.CENTROID`, and
`interpolateAtSample` combines `PIXLD.MY_INDEX` with `IPA.PASS.OFFSET`.

The same three observed PIXLD modes occur on sm75 and sm120. No tested
standard Vulkan GLSL construct emitted `MSCOUNT` or `CENTROID_OFFSET`.
""",
        "open": "`MSCOUNT` and `CENTROID_OFFSET` callers remain unidentified.",
    },
    "KILL": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_discard.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`",
        "conclusion": "Fragment discard control; suppresses the eventual fixed-function update.",
        "body": """
## Graphics-observed semantics

GLSL `discard` lowers to a predicated `KILL` before the final `EXIT`:

```text
@!P0 KILL
...
EXIT
```

`KILL` is separate from output writeback. The shader may still have staged
color/depth values, but a killed fragment is suppressed before the normal
fixed-function commit. Unlike color output, discard is explicit in SASS.
""",
        "open": "Early versus late discard timing across all depth/stencil state combinations was not exhaustively measured.",
    },
    "S2R": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "vertex/fragment builtin probes in `experiments/graphics_batch_t`, `gpucomp_spy.c` SR-pair patch",
        "conclusion": "Reads special register state; several graphics builtins map directly or through packed bitfields.",
        "body": """
## Graphics-observed semantics

Graphics builtins use three distinct sources: attribute loads, driver ABI
constants, and special registers. `S2R` covers the SR path.

Observed mappings:

| builtin / use | special register |
|---|---|
| `gl_SubgroupInvocationID` | `SR_LANEID` |
| subgroup equality masks | `SR_EQMASK` / `SR_GEMASK` / `SR_GTMASK` / `SR_LEMASK` / `SR_LTMASK` |
| `gl_WarpIDNV` | bitfield in `SR_VIRTID` |
| `gl_SMIDNV` | another bitfield in `SR_VIRTID` |
| `gl_SMCountNV` | bitfield in `SR_VIRTCFG` |
| `gl_HelperInvocation` | `SR_THREAD_KILL` |
| thread/block IDs | `SR_TID.*` / `SR_CTAID.*` |

Packed fields require shift/mask extraction:

```text
S2R R1, SR_VIRTID
SHF.R.U32.HI R6, RZ, 0x8, R1
SHF.R.U32.HI R7, RZ, 0x14, R1
SGXT.U32 R6, R6, 0x7
SGXT.U32 R7, R7, 0x9
```

The `SpecialRegisters` enum has no named surface-header-table or bindless
descriptor-table base. Candidate address-like registers were sampled in a
fragment S2R patch: direct-CBE address (21/22), circular-queue address (98/99),
and invocation/TTU metadata (29/133) all read zero. A positive control reading
`SR_LANEID`/`SR_TID.X` produced expected nonzero per-lane values.
""",
        "open": "Unnamed SR indices and stage-specific populating of address-like registers remain untested.",
    },
    "LDTRAM": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_fragment_barycentric.frag`, `vulkan_graphics.c`, `extract_pipeline_binary.py`",
        "conclusion": "Per-vertex/barycentric attribute load from triangle attribute storage.",
        "body": """
## Graphics-observed semantics

`LDTRAM` appears in fragment shaders using per-vertex barycentric input
attributes:

```glsl
layout(location = 0) pervertexEXT in vec4 colors[3];
```

Observed sm75 lowering:

```text
LDTRAM.AB R12, a[0x80]
LDTRAM.AB R14, a[0x84]
LDTRAM.AB R16, a[0x88]
LDTRAM.AB R18, a[0x8c]
LDTRAM.C  R1,  a[0x80]
LDTRAM.C  R5,  a[0x84]
LDTRAM.C  R7,  a[0x88]
LDTRAM.C  R8,  a[0x8c]
```

The modes match triangle vertex storage:

| mode | result |
|---|---|
| `AB` | 64-bit pair containing A and B vertex values |
| `C` | 32-bit C vertex value |

This differs from ordinary interpolation: `LDTRAM` exposes each triangle
vertex's attribute separately so the shader can combine them with explicit
barycentric weights.
""",
        "open": "No non-barycentric caller of LDTRAM was found in the tested Vulkan paths.",
    },
    "ISBERD": {
        "evidence": "sm75+sm120-silicon",
        "tier": "high",
        "probes": "`probe_dynamic.geom`, `probe.tesc`, `probe.tese`, `vulkan_graphics.c`",
        "conclusion": "Read of raw indexed shader-buffer entry values in geometry/tessellation stages.",
        "body": """
## Graphics-observed semantics

`ISBERD` reads a raw indexed shader-buffer entry from `[Ra]`. It is legal in
VS, GS, TS, and TI stages.

Geometry and tessellation prologues use the result as a dynamic offset for
attribute operations:

```text
ISBERD R3, [R1]
ALD.128 R4, a[0x70], R3
ALD.128 R8, a[0x80], R3
AST.128 a[0x70], R4
AST.128 a[0x80], R8
```

The same pattern selects input vertices and patch entries in TCS/TES.
`ISBERD` supplies the raw entry value; `ALD/AST` consume it as an attribute
address component. It is not a global-memory load.
""",
        "open": "The complete hardware layout of all ISBE bases (`MAP/PRIM/ATTR/PATCH`) is not decoded.",
    },
    "ISBEWR": {
        "evidence": "sm120-silicon",
        "tier": "high",
        "probes": "`probe.mesh`, `vulkan_graphics.c`, `extract_pipeline_binary.py`",
        "conclusion": "Write to indexed shader-buffer entries; observed directly in sm120 mesh output.",
        "body": """
## Graphics-observed semantics

`ISBEWR` writes `Rb` to raw indexed shader-buffer entry `[Ra]` and uses `.O`
for the output direction. The ISA permits VS, TS, and TI, but not GS.

An `EXT_mesh_shader` probe on sm120 emits:

```text
ISBEWR.O.32 [0x3], R0
ISBEWR.O.ATTR.SKEW.32 [RZ],  R1
ISBEWR.O.ATTR.SKEW.32 [0x80], R1
ISBEWR.O [0x4], RZ
ISBEWR.O [0x5], R4
ISBEWR.O [0x6], R5
```

`.ATTR` writes per-vertex output attributes such as `gl_Position` and user
varyings. Plain `.O` writes carry primitive/topology metadata. `SKEW` exposes
the packed/skewed entry layout.

The instruction has no normal destination register and does not write global
memory. It updates graphics-front-end indexed shader-buffer entries.
""",
        "open": "The sm75 mesh path is not available in local Vulkan; sm75 evidence covers the ISA/stage legality, not a mesh caller.",
    },
    "AL2P": {
        "evidence": "spec",
        "tier": "low",
        "probes": "`AL2P` ISA operand types plus negative tests across local VS/GS/TCS/TES/mesh probes",
        "conclusion": "Logical-to-physical attribute-address conversion; not observed in tested GLSL.",
        "body": """
## ISA-derived semantics

`AL2P` converts a logical attribute address to a physical attribute address:

```text
source:      LOGICAL_ATTR_ADDRESS
destination: PHYSICAL_ATTR_ADDRESS
```

Conceptually:

```text
Rphysical = translate_logical_attribute_address(
                Rlogical + offset)
```

The destination can feed a later dynamic `ALD`, `AST`, `IPA`, or related
attribute operation.

The ISA restricts `AL2P` to the geometry front-end stages:

```text
VS, GS, TS, TI
```

It is not legal in pixel shaders.

No real `AL2P` appeared in the tested static/dynamic VS, GS, TCS/TES, mesh, or
fragment probes. Ordinary static accesses use immediate `a[...]`; dynamic
arrays commonly use `ISBERD` plus `ALD/AST` with a register offset.

Likely callers are compiler-generated logical-to-physical remaps for dynamic,
aliased, packed, widened, or transformed attribute layouts.
""",
        "open": "Need a concrete GLSL/SPIR-V layout that forces AL2P before promoting this note above spec evidence.",
    },
}


def render_note(arch: str, mnemonic: str, variants: list[dict],
                metadata: dict) -> str:
    display = ARCHES[arch][3]
    pipe_names = sorted({v.get("pipe_suffix", "?") for v in variants})
    pipes = ", ".join(f"`{p}`" for p in pipe_names)
    evidence = metadata.get(f"evidence_{arch}", metadata["evidence"])
    timestamp = "2026-11-14"
    status = "active"
    return f"""# {mnemonic} — {arch} ({display}) graphics instruction

<!-- notes-status -->
**Status:** {status}  
**Evidence:** {evidence}  
**Tier confidence:** {metadata['tier']}  
**Last verified:** {timestamp}  
**Probe:** {metadata['probes']}  
**Open items:** see below  
**Audit:** `tools/notes_audit.py` · handwritten graphics semantics + ISA fields from `{ARCHES[arch][0]}`

## Conclusion

{metadata['conclusion']}

{metadata['body'].strip()}

{BEGIN}
## Variants

{render_variants(variants)}

## Properties

{render_properties(variants)}

## Encoding

Bit map of the first layout (`{variants[0]['class']}`); other classes differ
through the modifier fields enumerated in *Variants*:

{render_encoding(variants[0])}

## Legal-encoding conditions

{render_conditions(variants)}

## Pipe

Pipe suffix(es) in this dump: {pipes}.
{END}

## Open questions

{metadata['open'] or "No instruction-specific open item from the local graphics probes."}
"""


def main() -> None:
    for arch in ARCHES_TO_WRITE:
        db = load_db(arch)
        grouped = by_mnemonic(db)
        out_dir = REPO / "notes" / arch / "instr"
        out_dir.mkdir(parents=True, exist_ok=True)
        for mnemonic, metadata in NOTES.items():
            variants = grouped.get(mnemonic)
            if not variants:
                raise SystemExit(f"{arch}: missing {mnemonic}")
            path = out_dir / f"{mnemonic.lower()}.md"
            path.write_text(
                render_note(arch, mnemonic, variants, metadata),
                encoding="utf-8",
            )
            print(f"wrote {path.relative_to(REPO)} ({len(variants)} variants)")


if __name__ == "__main__":
    main()
