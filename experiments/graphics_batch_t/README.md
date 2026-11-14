# Graphics shader `batch_t` probe

This experiment compiles GLSL through the NVIDIA Vulkan driver and recovers the
driver-generated SASS from process memory. It does not use `ptxas` for the
shader SASS.

## Build and run (TITAN RTX / sm75)

```bash
glslc -fshader-stage=vertex -o probe.vert.spv probe.vert
glslc -fshader-stage=fragment -o probe.frag.spv probe.frag
VULKAN_HEADERS_INCLUDE=/path/to/Vulkan-Headers/include
gcc -O2 -I"$VULKAN_HEADERS_INCLUDE" -o vulkan_graphics \
  vulkan_graphics.c -lvulkan
gcc -shared -fPIC -O2 -o gpucomp_spy.so gpucomp_spy.c gpucomp_hooks.S -ldl

dump=/tmp/graphics-batch-t
mkdir -p "$dump"
SPY_GPUCOMP_LOG="$dump/calls.log" \
SPY_GPUCOMP_DUMP_DIR="$dump" \
PROBE_GPU_NAME="TITAN RTX" \
LD_PRELOAD="$PWD/gpucomp_spy.so" \
./vulkan_graphics "$PWD/probe.vert.spv" "$PWD/probe.frag.spv"
```

The harness uses `VK_KHR_pipeline_binary` and therefore requires
Vulkan-Headers new enough to contain that extension.

The preload interposes `nvGetCompilerInterface(GLVSPIRVC, ...)`, logs the
compiler-interface calls, and scans selected readable process mappings for
SASS candidates around `S2R`, `IPA`, `OUT`, `EXIT`, and known immediate values.
`extract_shader_sass.py` reconstructs a function from a candidate dump using a
signature instruction. `report_batch.py` separates true `batch_t` uses from
the overloaded `.reuse` uses.

## Direct compiled-pipeline capture

`PROBE_PIPELINE_BINARY_DIR=...` enables
`VK_KHR_pipeline_binary` and creates the pipeline with
`VK_PIPELINE_CREATE_2_CAPTURE_DATA_BIT_KHR`. NVIDIA returns a blob prefixed by
an uncompressed-size word and a zstd frame. After decompression, the container
starts with `NVDANVVMNVuc`, followed by shader metadata and the SASS stream.

`extract_pipeline_binary.py` decompresses the blob, finds complete
`...; EXIT` instruction runs, validates them with nvdisasm, and writes both raw
SASS and disassembly:

```bash
python3 extract_pipeline_binary.py pipeline_binary_0.bin \
  --arch SM75 --out-prefix vertex
```

`PROBE_VERTEX_ONLY=1` creates a valid graphics pipeline with only the vertex
stage and `rasterizerDiscardEnable=VK_TRUE`, so every recovered shader is a
vertex executable. `PROBE_VERTEX_INPUT=1` supplies three vertices with two
`vec4` attributes for the input-attribute test.

```bash
mkdir -p /tmp/vertex-binary
PROBE_GPU_NAME="TITAN RTX" PROBE_VERTEX_ONLY=1 PROBE_VERTEX_INPUT=1 \
PROBE_PIPELINE_BINARY_DIR=/tmp/vertex-binary \
  ./vulkan_graphics probe_vertex_attr.vert.spv probe_black.frag.spv

python3 extract_pipeline_binary.py \
  /tmp/vertex-binary/pipeline_binary_0.bin \
  --arch SM75 --out-prefix /tmp/vertex-binary/vertex
```

## sm75 result

The tested fragment shaders all place `batch_t=1` (`BATCH_START`) with
`stall=1, yield=1` on the first instruction of the shader:

| shader | first instruction |
|---|---|
| plain interpolation | `IPA.PASS R4, a[0x7c]` |
| flat input | `IPA.CONSTANT R0, a[0x80]` |
| centroid input | `IPA.PASS.CENTROID R4, a[0x7c]` |
| explicit `interpolateAt*` | `MOV R0, c[0x0][0x32d0]` |
| no interpolation | `IMAD.MOV.U32 R0, RZ, RZ, 0x3e800000` |

No second true batch marker was found after shader entry in the tested
discard, derivative, early-fragment-test, centroid, flat, or explicit
`interpolateAtCentroid/Sample/Offset` variants. Later nonzero `[124:122]`
values are operand `.reuse` hints and have `usched >= 16`.

A Vulkan compute shader compiled through the same driver had no
`BATCH_START`; only its actual `.reuse` modifiers were present.

No explicit `BATCH_END` (`batch_t=4`) appears in the recovered sm75 fragment
functions. The final instruction is a normal `EXIT` with `batch_t=0`; it is
not marked as an end-of-batch instruction. The sample therefore suggests that
the fragment batch is terminated implicitly at shader exit or by scheduler /
fixed-function state outside the SASS stream, rather than by a paired
instruction.

## IPA interpretation

`IPA` is the pixel-shader attribute interpolator. The spec exposes:

| name | bits / values | meaning |
|---|---|---|
| opcode | `0x326` | `IPA`, `mio_pipe`, virtual queue `VQ_IPA` |
| `ipaop` | `PASS=0, CONSTANT=1, STATE=2` | interpolation mode |
| `msi` | `CENTER=0, CENTROID=1` | sample location for one mode |
| `OFFSETONLY` | `OFFSET=2` | explicit offset mode |
| `attr` | immutable `a[...]`, 8-bit address scaled by 4 | rasterizer attribute-memory address |

The shader type condition is pixel-shader-only. The destination is a normal
32-bit GPR and the instruction has a variable-latency write scoreboard.

Observed lowering on sm75:

- `smooth in vec4` → four `IPA.PASS` component reads plus one
  `IPA.PASS a[0x7c]` perspective factor. The shader computes
  `MUFU.RCP` of that factor and multiplies all four components by it.
- Two `smooth in vec4` values share the single `a[0x7c]` perspective factor;
  eight component `IPA.PASS` instructions follow.
- `noperspective in vec4` → four `IPA.PASS` reads, with no `a[0x7c]`,
  `MUFU.RCP`, or component rescaling.
- `flat in vec4` → four `IPA.CONSTANT` reads.
- `centroid in vec4` → four `IPA.PASS.CENTROID` reads plus the perspective
  factor and reciprocal scaling.
- `interpolateAtOffset/Sample` → `IPA.PASS.OFFSET` with an extra register
  containing the evaluation offset.

This identifies `IPA` as the hardware read of a rasterizer-produced attribute
at a per-fragment barycentric/sample location. Perspective-correct versus
noperspective interpolation is expressed by whether the shader separately
reads the perspective factor and divides by it; it is not a distinct top-level
`IPA` mode in these dumps.

## Vertex shader SASS

The passthrough vertex shader

```glsl
layout(location = 0) in vec4 in_position;
layout(location = 1) in vec4 in_color;
layout(location = 0) out vec4 vcolor;

void main() {
    gl_Position = in_position;
    vcolor = in_color;
}
```

lowered to the following instruction structure on sm75:

```text
S2UR UR4, SR_WSCALEFACTOR_XY
ALD.128 R0, a[0x80]              ; location=0 input
S2UR UR5, SR_WSCALEFACTOR_Z
FMUL.FTZ R4, R3, UR4
FSETP...                         ; six clip/viewport bound comparisons
FMUL.FTZ R5, R3, UR5
CSMTEST.RA.F.AND ...
CSMTEST.A.FCSM_TR.AND P0, ...
@P0 EXIT                         ; early clip/guard-band rejection
ALD R4, a[0x90]                  ; location=1 input x
ALD R5, a[0x94]                  ; y
ALD R6, a[0x98]                  ; z
ALD R7, a[0x9c]                  ; w
AST.128 a[0x70], R0              ; gl_Position
AST a[0x80], R4                  ; varying location=0 x
AST a[0x84], R5                  ; y
AST a[0x88], R6                  ; z
AST a[0x8c], R7                  ; w
EXIT
```

Observed logical attribute addresses:

| value | address |
|---|---|
| `gl_VertexIndex` | `a[0x2fc]` |
| input `location=0` | `a[0x80]` |
| input `location=1` | `a[0x90]` |
| `gl_Position` output | `a[0x70]` |
| varying `location=0` output | `a[0x80]` |

Inputs therefore use the graphics-stage `ALD` attribute path, not CUDA-style
parameter loads or global loads. Outputs use `AST`; a compiler-selected vector
operation becomes `AST.128`, while a component-at-a-time source becomes four
scalar `AST` instructions.

The six `FSETP` comparisons scale `w` by `SR_WSCALEFACTOR_XY/Z` and compare the
result against positive and negative input X/Y/Z bounds. The two `CSMTEST`
instructions combine those predicate results into `P0`; `@P0 EXIT` performs an
early clip/guard-band rejection before the output attribute stores.

Unlike sm75 fragment shaders, the sm75 vertex shader has **no
`BATCH_START`**: all 25 instructions have `batch_t=0`. The nonzero
`[124:122]` values reported by `report_batch.py` are ordinary operand `.reuse`
uses. The same input-passthrough vertex shader on sm120/RTX 5090 has the same
`ALD`/`CSMTEST`/`AST` instruction structure and still has no `BATCH_START`;
only scheduling and stall/yield controls differ.

## Vertex SSBO indexed by gl_VertexIndex

`PROBE_VERTEX_SSBO=1` binds one std430 storage buffer at set 0, binding 0.
The probe shader uses `gl_VertexIndex` both as the SSBO read index and as the
index for a second write:

```glsl
uint index = uint(gl_VertexIndex);
vec4 position = data.values[index];
data.values[index + 3u] = position;
gl_Position = position;
vcolor = vec4(position.xyz, float(index));
```

On sm75 this lowers to:

```text
ALD R1, a[0x2fc]                          ; gl_VertexIndex
ULDC.64 UR6, c[0x1e][0x0]                ; 64-bit SSBO base
IMAD.SHL.U32 R0, R1, 0x10, RZ            ; index * sizeof(vec4)
LDG.E.128.STRONG.CTA R4, [R0.U32+UR6]    ; read values[index]
IADD3 R0, R0, 0x30, RZ                   ; (index + 3) * 16
STG.E.128.STRONG.CTA [R0.U32+UR6], R4    ; write values[index + 3]
... six FSETP / two CSMTEST ...
@P0 EXIT                                 ; clip/guard-band rejection
I2F.U32 R0, R1
AST.128 a[0x70], R4                      ; gl_Position
AST.128 a[0x80], R4                      ; varying location=0
EXIT
```

The SSBO itself is not a graphics-specific instruction path: after the driver
materializes the descriptor/base, it becomes ordinary `LDG`/`STG`. The
graphics-specific parts remain:

| instruction | role in this shader |
|---|---|
| `ALD R1, a[0x2fc]` | fetch `gl_VertexIndex` from graphics attribute space |
| `S2UR SR_WSCALEFACTOR_*` | obtain viewport scale factors |
| `CSMTEST` | combine clip-bound predicates and drive early `EXIT` |
| `AST.128 a[0x70]` | write `gl_Position` |
| `AST.128 a[0x80]` | write varying location 0 |

`c[0x1e][0x0]` is the driver ABI slot observed for this sole SSBO descriptor.
`UR6` is the recovered 64-bit base address; the address operand is
`R0.U32+UR6`, with `R0` containing the byte offset. No hidden
graphics-specific SSBO load/store opcode was found.

On sm120 the structure is unchanged, but `ULDC` is called `LDCU`, the memory
scope is `.STRONG.SM` instead of `.STRONG.CTA`, and several ALU spellings
change:

```text
LDCU.64 UR4, c[0x1e][URZ]
LDG.E.128.STRONG.SM R4, [R0.U32+UR4]
STG.E.128.STRONG.SM [R0.U32+UR4], R4
I2FP.F32.U32 R0, R1
AST.128 a[0x70], R4
AST.128 a[0x80], R4
```

Neither architecture sets `BATCH_START` for this vertex shader. Host readback
confirmed the stores: `ssbo[0..2]` were copied to `ssbo[3..5]`.

## Vertex builtin lowering: SR, ALD, or constants

Vulkan GLSL vertex builtins do not share one hardware source. The observed
sm75 mapping is:

| GLSL builtin | lowering |
|---|---|
| `gl_VertexIndex` | `ALD a[0x2fc]` |
| `gl_InstanceIndex` | `ALD a[0x2f8] + c[0x0][0x4]` |
| `gl_BaseVertexARB` | `c[0x0][0x0]` |
| `gl_BaseInstanceARB` | `c[0x0][0x4]` |
| `gl_DrawIDARB` | `c[0x0][0x8]` |
| `gl_DeviceIndex` | `c[0x0][0x10]` |
| `gl_ViewIndex` | `c[0x0][0x14]` |

Representative SASS:

```text
ALD R0, a[0x2f8]                    ; raw instance id
ALD R4, a[0x2fc]                    ; gl_VertexIndex
IMAD.MOV.U32 R6, RZ, RZ, c[0x0][0x0]   ; BaseVertex
IMAD.MOV.U32 R7, RZ, RZ, c[0x0][0x4]   ; BaseInstance
IMAD.MOV.U32 R8, RZ, RZ, c[0x0][0x8]   ; DrawID
IMAD.MOV.U32 R9, RZ, RZ, c[0x0][0x14]  ; ViewIndex
IMAD.MOV.U32 R12, RZ, RZ, c[0x0][0x10] ; DeviceIndex
IADD3 R5, R0, c[0x0][0x4], RZ           ; InstanceIndex =
                                         ; raw instance + BaseInstance
```

Thus the draw/index builtins are not fetched with `S2R`: vertex and raw
instance IDs use the graphics attribute path, while draw metadata is supplied
through the driver ABI constant bank. The few `CS2R ..., SRZ` instructions in
these shaders only materialize zero constants.

Subgroup and NVIDIA SM builtins use real special-register reads:

| GLSL builtin | lowering |
|---|---|
| `gl_SubgroupInvocationID` | `S2R SR_LANEID` |
| `gl_SubgroupEqMask` | `S2R SR_EQMASK` |
| `gl_SubgroupGeMask` | `S2R SR_GEMASK` |
| `gl_SubgroupGtMask` | `S2R SR_GTMASK` |
| `gl_SubgroupLeMask` | `S2R SR_LEMASK` |
| `gl_SubgroupLtMask` | `S2R SR_LTMASK` |
| `gl_WarpIDNV` | bitfield extracted from `S2R SR_VIRTID` |
| `gl_SMIDNV` | a different bitfield from `S2R SR_VIRTID` |
| `gl_SMCountNV` | bitfield extracted from `S2R SR_VIRTCFG` |

Representative SASS:

```text
S2R R8, SR_EQMASK
S2R R12, SR_GEMASK
S2R R16, SR_GTMASK
S2R R20, SR_LEMASK
S2R R24, SR_LTMASK

S2R R1, SR_VIRTID
SHF.R.U32.HI R6, RZ, 0x8, R1
SHF.R.U32.HI R7, RZ, 0x14, R1
SGXT.U32 R6, R6, 0x7
SGXT.U32 R7, R7, 0x9

S2R R2, SR_VIRTCFG
SHF.R.U32.HI R2, RZ, 0x14, R2
SGXT.U32 R13, R2, 0x9
```

`gl_SubgroupInvocationID` is exactly `SR_LANEID`. The subgroup ballot masks
have one dedicated SR each. In contrast, `gl_WarpIDNV` and `gl_SMIDNV` are
packed into `SR_VIRTID`, and `gl_SMCountNV` is packed into `SR_VIRTCFG`, so
the compiler emits `SHF` plus `SGXT` extraction.

Some subgroup/SM values are compile-time or device constants rather than
special-register reads:

| GLSL builtin | observed lowering |
|---|---|
| `gl_SubgroupSize` | immediate `32` |
| `gl_WarpsPerSMNV` | immediate `32` on sm75, `48` on sm120 |

The sm120 build uses the same sources: `ALD a[0x2fc]` for
`gl_VertexIndex`, `ALD a[0x2f8]` for raw instance ID, `c[0x0]` for draw
metadata, and the same `SR_LANEID`, mask, `SR_VIRTID`, and `SR_VIRTCFG`
family. Its subgroup-mask shader still contains the exact five mask reads:

```text
S2R SR_EQMASK
S2R SR_GEMASK
S2R SR_GTMASK
S2R SR_LEMASK
S2R SR_LTMASK
```

Vertex output builtins are a separate path: they use `AST`, not `ALD` or
`S2R`. The tested sm75 output slots are:

| GLSL output | SASS |
|---|---|
| `gl_Layer = 2` | `AST a[0x64], R5` |
| `gl_ViewportIndex = 3` | `AST a[0x68], R4` |
| `gl_PointSize = 3.5` | `AST a[0x6c], R4` |
| `gl_Position` | `AST.128 a[0x70], R0` |

The clip/guard-band `CSMTEST` sequence is interleaved with these setup stores,
but it only consumes the previously generated predicates; it does not generate
or load any GLSL builtin value.

## Fragment textures, images, and subpass inputs

The fragment probes use `gl_FragCoord.xy` as their coordinate source.
`IPA.PASS a[0x70]` and `a[0x74]` provide fragment X/Y. The three resource paths
then use distinct instruction families.

### `texture(sampler2D, uv)` -> `TEX`

The sm75 shader

```glsl
out_color = texture(input_texture,
                    gl_FragCoord.xy / vec2(64.0));
```

lowers to:

```text
IPA.PASS R4, a[0x70]                         ; FragCoord.x
IPA.PASS R5, a[0x74]                         ; FragCoord.y
FMUL.FTZ R4, R4, 0.015625                    ; / 64
FMUL.FTZ R5, R5, 0.015625
TEX.SCR.NODEP R2, R0, R4, R5, 0x1e, 0x0, 2D
EXIT
```

`TEX` writes the sampled RGBA result into `R0..R3` (`Rd=R0`, `Rd2=R2`).
`0x1e, 0x0` is the texture/surface pointer slot in the driver ABI constant
bank for this pipeline. `.SCR` uses screen-space sampling, `.NODEP` disables
the client-provided dependency, and `2D` is the texture dimension.

### Bindless / nonuniform descriptor indexing

`PROBE_FRAGMENT_BINDLESS=1` creates eight combined-image-sampler descriptors
and enables the Vulkan features:

- `shaderSampledImageArrayDynamicIndexing`
- `shaderSampledImageArrayNonUniformIndexing`

The probe uses a per-fragment index:

```glsl
uint index = uint(gl_FragCoord.x) & 7u;
out_color = texture(textures[nonuniformEXT(index)],
                    gl_FragCoord.xy / vec2(64.0));
```

sm75 lowers this to:

```text
IPA.PASS R0, a[0x70]                  ; FragCoord.x
IPA.PASS R5, a[0x74]                  ; FragCoord.y
F2I.FTZ.U32.TRUNC.NTZ R1, R0          ; integer X
FMUL.FTZ R4, R0, 0.015625
FMUL.FTZ R5, R5, 0.015625
SHF.L.U32 R1, R1, 0x2, RZ             ; index * 4
LOP3.LUT R6, R1, 0x1c, RZ, 0xc0, !PT  ; (index & 7) * 4
LDC R6, c[0x1e][R6]                   ; dynamic TS pointer lookup
TEX.SCR.B.NODEP R2, R0, R4, R6, 2D
EXIT
```

This is the bindless mechanism:

1. Convert the per-lane descriptor index to an entry byte offset.
2. Dynamically index the driver descriptor/TS table in constant bank `0x1e`.
3. Load the selected TS pointer into general register `R6`.
4. Use the `TEX` `.B` form, where `Rb=R6` carries the TS pointer instead of
   encoding an immediate `bank,offset` operand.

There is no separate "bindless texture" mnemonic. It is a dynamic `LDC`
descriptor-table lookup feeding the register-pointer variant of `TEX`.

sm120 uses the same calculation and nearly identical code:

```text
SHF.L.U32 R1, R1, 0x2, RZ
LOP3.LUT R6, R1, 0x1c, RZ, 0xc0, !PT
LDC R6, c[0x1e][R6]
TEX.SCR.B.DXY.NODEP R2, R0, R4, R6, 2D
```

The only visible change is `.DXY` on the sm120 `TEX`. In this experiment all
eight descriptors referenced the same image, so the SASS demonstrates the
indexing mechanism; the lookup itself can select any valid descriptor-table
entry.

### `FOOTPRINT` / `GL_NV_shader_texture_footprint`

`FOOTPRINT` is the hardware implementation of the NV texture-footprint query.
It returns the texel-group footprint that an equivalent filtered texture
lookup would access, without sampling the texture.

The ISA has two primary modes:

| mode | meaning |
|---|---|
| `FOOTPRINT.TEX` | implicit coordinate derivatives, with optional explicit LOD controls |
| `FOOTPRINT.TXD` | explicit X/Y gradients |

Additional controls include:

- `LODLC`: `nolodlc`, `LB`, `LC`, `LL`, `LB.LC`, `LC.FDV`, and `LZ`.
- `LODCTRL`: fine or coarse mip level.
- `SCR`: screen-space coordinate handling.
- `NODEP`: explicit dependency control.

The probe enables `VK_NV_shader_image_footprint` and tests three GLSL forms.

Implicit derivatives:

```glsl
bool valid = textureFootprintNV(
    input_texture, uv, 4, false, footprint);
```

sm75:

```text
IPA.PASS R4, a[0x74]
IPA.PASS R7, a[0x70]
FMUL.FTZ R4, R4, 0.015625
FMUL.FTZ R7, R7, 0.015625
IMAD.MOV.U32 R6, RZ, RZ, 0x4
FOOTPRINT.SCR.TEX.NODEP P0, R6, R4, R6, R4, 0x1e, 0x0, 2D
```

Explicit LOD:

```glsl
textureFootprintLodNV(
    input_texture, uv, 3.0, 4, false, footprint);
```

```text
FOOTPRINT.SCR.TEX.LL.NODEP P0, R4, R6, R6, R4, 0x1e, 0x0, 2D
```

`LL` identifies the explicit-LOD form.

Explicit gradients:

```glsl
vec2 dx = dFdx(uv);
vec2 dy = dFdy(uv);
textureFootprintGradNV(
    input_texture, uv, dx, dy, 4, false, footprint);
```

```text
SHFL.BFLY ...                         ; construct dFdx/dFdy
FSWZADD R8,  R1,  R4, PNNPPNNP
FSWZADD R10, R10, R5, PNNPPNNP
FSWZADD R9,  R9,  R4, PNPNNPNP
FSWZADD R11, R0,  R5, PNPNNPNP
FOOTPRINT.TXD.NODEP P0, R8, R0, R4, R8, 0x1e, 0x0, 2D
```

This confirms `TXD` takes an explicit 128-bit gradient pair in `Rb`; the
compiler builds it using the same quad derivative sequence as ordinary
`textureGrad`.

The GLSL boolean selects fine versus coarse mip level. A query with `true`
emits:

```text
FOOTPRINT.SCR.TEX.COARSE.NODEP ...
```

while `false` uses the default fine form without a suffix.

The two 64-bit destination pairs (`Rd` and `Rd2`) return a packed 128-bit
footprint plus predicate validity `Pu`; both destinations must be 64-bit
aligned. The driver compiler extracts the GLSL structure fields with shifts
and masks. For example, the implicit-anchor probe emits:

```text
SHF.R.U32.HI R2, RZ, 0xc, R7
LOP3.LUT R0, R7, 0xfff, ...
LOP3.LUT R1, R6, 0xfff, ...
LOP3.LUT R2, R2, 0xf, ...
FSEL R3, RZ, 1, !P0
```

The public result is:

```glsl
struct gl_TextureFootprint2DNV {
    uvec2 anchor;       // origin of an 8x8 texel-group neighborhood
    uvec2 offset;       // split point when the footprint crosses an 8x8 set
    uvec2 mask;         // 64 bits, one per texel group
    uint  lod;
    uint  granularity;
};
```

For 2D textures, each granularity code selects a texel-group size such as
`2x2`, `4x4`, `8x4`, up to `256x256`; the mask identifies which groups in the
neighborhood the texture access would touch. The extension requires
`CLAMP_TO_EDGE` for defined results.

On sm120, the compiler first unpacks the sampler descriptor and adds `.DXY`:

```text
FOOTPRINT.SCR.TEX.DXY.NODEP P0, R6, R4, R6, R4, UR4, 2D
FOOTPRINT.SCR.TEX.LL.DXY.NODEP P0, R4, R6, R6, R4, UR4, 2D
FOOTPRINT.TXD.NODEP P0, R8, R0, R4, R8, UR4, 2D
```

The main practical use is multi-pass or virtual-texturing work: a cheap
visibility/geometry pass records the union of texture footprints, then the
expensive producer pass skips texels that no visible fragment would access.

## `PIXLD` / fragment sample and coverage state

`PIXLD` is a pixel-shader-only load of fragment sample/coverage state. It has
no source operands and returns one 32-bit register plus predicate `Pu`.

The ISA defines five modes:

| mode | value | meaning |
|---|---:|---|
| `MSCOUNT` | 0 | multisample count |
| `COVMASK` | 1 | coverage/sample mask |
| `CENTROID_OFFSET` | 2 | centroid offset |
| `MY_INDEX` | 3 | current sample index |
| `INNER_COVERAGE` | 4 | inner/full coverage state |

The observed Vulkan GLSL mappings are:

| GLSL builtin | SASS |
|---|---|
| `gl_SampleID` | `PIXLD.MY_INDEX R0` |
| `gl_SampleMaskIn[0]` | `PIXLD.MY_INDEX` then `PIXLD.COVMASK` |
| `gl_FragFullyCoveredNV` | `PIXLD.INNER_COVERAGE R0` |

Representative SASS:

```text
; gl_SampleID
PIXLD.MY_INDEX R0

; gl_SampleMaskIn[0]
PIXLD.MY_INDEX R0
PIXLD.COVMASK  R1

; gl_FragFullyCoveredNV
PIXLD.INNER_COVERAGE R0
```

`gl_FragFullyCoveredNV` was activated through
`GL_NV_conservative_raster_underestimation` and
`VK_EXT_conservative_rasterization` with
`VK_CONSERVATIVE_RASTERIZATION_MODE_UNDERESTIMATE_EXT`.

Other sample-related builtins use different paths:

- `gl_HelperInvocation` -> `S2R SR_THREAD_KILL`, not PIXLD.
- `gl_SamplePosition` -> `PIXLD.MY_INDEX`, followed by an `LDC.U8` lookup of
  the sample-position table in `c[0x0][0x32d0]`.
- `interpolateAtSample` -> `PIXLD.MY_INDEX` for the sample index, then
  `IPA.PASS.OFFSET`.
- `interpolateAtCentroid` -> `IPA.PASS.CENTROID`, not PIXLD.

In a 4-sample, sample-shaded pipeline, `gl_SampleMaskIn` still emitted
`MY_INDEX` before `COVMASK`. No standard Vulkan GLSL construct tested here
emitted `PIXLD.MSCOUNT` or `PIXLD.CENTROID_OFFSET`; those may be compiler/
driver-internal paths or OpenGL-specific paths.

sm75 and sm120 produce the same `PIXLD.MY_INDEX`, `.COVMASK`, and
`.INNER_COVERAGE` forms.

## `ISBERD` and `ISBEWR`

These are raw **indexed shader-buffer entry** read/write operations:

- `ISBERD`: read a raw ISBE value from `[Ra]`.
- `ISBEWR`: write `Rb` to raw ISBE `[Ra]`, with `.O` output direction.

The ISA exposes:

| field | values |
|---|---|
| size | `U8`, `U16`, `32` |
| base | `MAP`, `PRIM`, `ATTR`, `PATCH` |
| mode | `noskew`, `SKEW` |

Shader-stage constraints explain the observed lowering:

| instruction | allowed stages |
|---|---|
| `ISBERD` | VS, GS, TS, TI |
| `ISBEWR` | VS, TS, TI; not GS |

### Geometry/tessellation entry reads

The geometry shader's compiler-generated prologue reads per-primitive entry
indices with `ISBERD`, then uses them as dynamic offsets for `ALD`/`AST`:

```text
ISBERD R3, [R1]
ALD.128 R4, a[0x70], R3
ALD.128 R8, a[0x80], R3
AST.128 a[0x70], R4
AST.128 a[0x80], R8
```

The same pattern appears in the tessellation-control/evaluation pipeline,
where multiple `ISBERD` results select the three input vertices and patch
entries. `ISBERD` therefore supplies the raw indexed entry value; the
surrounding `ALD/AST` operations consume it as an attribute address.

The ordinary vertex shader, vertex transform-feedback outputs, geometry output
path (`OUT.EMIT`), and TCS/TES user outputs in these probes did not emit
`ISBEWR`.

### Mesh output entry writes

An `EXT_mesh_shader` probe on sm120 emits `ISBEWR` directly for mesh output
attributes and primitive metadata:

```text
ISBEWR.O.32 [0x3], R0
ISBEWR.O.ATTR.SKEW.32 [RZ],  R1
ISBEWR.O.ATTR.SKEW.32 [0x80], R1
ISBEWR.O.ATTR.SKEW.32 [0x100], RZ
ISBEWR.O.ATTR.SKEW.32 [0x180], R2
...
ISBEWR.O [0x4], RZ
ISBEWR.O [0x5], R4
ISBEWR.O [0x6], R5
```

The `.ATTR` writes correspond to mesh per-vertex output attributes, including
`gl_Position` and user varyings. The plain `.O` writes to `[0x4]`, `[0x5]`,
and `[0x6]` carry mesh primitive/topology metadata such as primitive count,
indices, and emitted output state.

The mesh SASS also uses `SKEW` mode, exposing the packed/skewed entry layout
instead of the default linear layout. `ISBEWR` does not write ordinary global
memory and does not produce a destination register; it directly updates the
graphics front-end's indexed shader-buffer entries.

### Summary

```text
VS/GS/TS/TI  ISBERD -> raw entry value -> ALD/AST dynamic address
mesh output  ISBEWR.O[.ATTR][.SKEW] -> per-vertex attributes / primitive metadata
```

The observed implementation is consistent with `ISBE` meaning the graphics
front-end's indexed shader-buffer entry store, not a generic global/shared
memory buffer.

## `AL2P`

`AL2P` is not a generic pointer-conversion instruction. Its ISA operand types
are:

```text
source:      LOGICAL_ATTR_ADDRESS
destination: PHYSICAL_ATTR_ADDRESS
```

The conceptual operation is:

```text
AL2P Rphysical, Rlogical, offset
Rphysical = translate_logical_attribute_address(
                Rlogical + offset)
```

It is only legal in the geometry front-end stages:

```text
VS, GS, TS, TI
```

It is not legal in the pixel shader. The destination is a 32-bit physical
attribute address that can subsequently feed the dynamic-address form of
`ALD`, `AST`, `IPA`, or related attribute operations.

The ordinary probes do not require an explicit `AL2P`:

- Static attributes are encoded directly as `ALD a[imm]` / `AST a[imm]`.
- Dynamic geometry input arrays lower to `ISBERD` followed by
  `ALD a[base], Roffset`.
- TCS/TES per-vertex/patch access similarly uses `ISBERD` plus dynamic
  `ALD/AST`.

The compiler can fold the logical→physical mapping into those address forms
when the logical slot is known at compile time. `AL2P` should therefore be
expected primarily in compiler-generated VTG prologues or uncommon input
layouts where a logical attribute number must be converted at runtime, for
example:

- dynamically selected vertex/geometry/tessellation input attributes;
- aliased or remapped attribute locations/components;
- packed, widened, or otherwise transformed attribute layouts where the
  shader-visible location differs from the hardware physical slot;
- cases that need to materialize and reuse one physical attribute address for
  multiple `ALD`/`AST` operations.

No real `AL2P` appeared in the tested static/dynamic VS, GS, TCS/TES, mesh, or
fragment probes. This suggests ordinary GLSL attribute access usually avoids
the instruction rather than that `AL2P` is pixel-shader state.

## `TXD` and `TMML`

These are related texture-pipeline operations:

- `TXD` performs a filtered texture lookup using explicit X/Y gradients.
- `TMML` computes the LOD values used by `textureQueryLod`, without fetching
  a texel.

### `textureGrad()` -> `TXD`

The probe:

```glsl
vec2 dx = dFdx(uv);
vec2 dy = dFdy(uv);
out_color = textureGrad(input_texture, uv, dx, dy);
```

sm75 lowers to:

```text
IPA.PASS R4, a[0x70]
IPA.PASS R5, a[0x74]
SHFL.BFLY PT, R1,  R4, 0x1, 0x1c03
SHFL.BFLY PT, R10, R5, 0x1, 0x1c03
SHFL.BFLY PT, R9,  R4, 0x2, 0x1c03
SHFL.BFLY PT, R0,  R5, 0x2, 0x1c03
FSWZADD R8,  R1,  R4, PNNPPNNP
FSWZADD R10, R10, R5, PNNPPNNP
FSWZADD R9,  R9,  R4, PNPNNPNP
FSWZADD R11, R0,  R5, PNPNNPNP
TXD.NODEP R2, R0, R4, R8, 0x1e, 0x0, 2D
```

`TXD` consumes:

- `Ra=R4`: 2D texture coordinates.
- `Rb=R8`: 128-bit gradient pair `{dX.xy, dY.xy}` in `R8..R11`.
- `Rd=R0` / `Rd2=R2`: the RGBA result register quads.
- `0x1e, 0x0`: texture/sampler pointer.

The GLSL `dFdx/dFdy` calls were explicit here, so the compiler materializes
their quad derivative network before issuing `TXD`. Unlike ordinary `TEX`,
`TXD` does not derive its LOD from implicit screen-space derivatives.

sm120 is equivalent with `.DXY` on derivative combines and a UR descriptor:

```text
FSWZADD.DXY ...
TXD.NODEP R2, R0, R4, R8, UR4, 2D
```

### `textureQueryLod()` -> `TMML`

The probe:

```glsl
vec2 lod = textureQueryLod(input_texture, uv);
out_color = vec4(lod, 0.0, 1.0);
```

sm75 emits two `TMML.LOD` operations:

```text
TMML.LOD.NODEP RZ, R6, R4, 0x1e, 0x0, 2D, 0x2
TMML.LOD.NODEP RZ, R7, R4, 0x1e, 0x0, 2D, 0x1
I2F.U32 R0, R6
I2F.S16 R1, R7
FMUL.FTZ R0, R0, 0.00390625
FMUL.FTZ R1, R1, 0.00390625
```

`TMML` is therefore the mip-level query primitive:

- `.LOD` is the LOD-only mode.
- `Ra=R4` supplies texture coordinates.
- `Rd=R6/R7` receives integer/fixed-point LOD data.
- The trailing immediate selects which query result is produced.
- The compiler converts the integer results with `I2F` and scales by
  `1/256` to match GLSL's floating `textureQueryLod` result.

No texture sample is returned by `TMML`; the final fragment color contains
only the two queried LOD values.

sm120 keeps the same operation:

```text
TMML.LOD.DXY.NODEP RZ, R6, R4, UR4, 2D, 0x1
TMML.LOD.DXY.NODEP RZ, R0, R4, UR4, 2D, 0x2
```

The two instructions may be scheduled in the opposite order from sm75; the
trailing selector and destination mapping identify each result.

### `imageLoad/imageStore` -> `SULD`/`SUST`

```glsl
ivec2 coord = ivec2(gl_FragCoord.xy);
vec4 value = imageLoad(storage_image, coord);
imageStore(storage_image, coord, value + vec4(0.25));
out_color = value;
```

lowers to:

```text
IPA.PASS R4, a[0x70]
IPA.PASS R5, a[0x74]
F2I.FTZ.TRUNC.NTZ R4, R4
F2I.FTZ.TRUNC.NTZ R5, R5
SULD.P.2D.CTA.IGN R0, [R4], 0x1e, 0x0
FADD.FTZ R8..R11, R0..R3, 0.25
SUST.P.2D.CTA.IGN [R4], R8, 0x1e, 0x0
EXIT
```

This is not a generic `LDG/STG` path. Storage images use the surface
load/store instructions `SULD` and `SUST`:

- `.P` exposes a predicate result.
- `.2D` is the surface dimensionality.
- `.CTA` / `.IGN` are memory-scope/order modifiers in the emitted sm75 form.
- `[R4]` is the integer X/Y coordinate pair.
- `R0..R3` is the loaded/stored RGBA vector.
- `0x1e, 0x0` again selects the resource pointer in the constant bank.

#### Intercepting the `SULD/SUST` operands

The surface instructions do not carry a linear byte address. For the emitted
2-D image operation:

```text
SULD.P.2D.CTA.IGN R0, [R4], 0x1e, 0x0
SUST.P.2D.CTA.IGN [R4], R8, 0x1e, 0x0
```

the visible inputs are:

- `[R4]`: the integer X/Y coordinate pair in `R4/R5`.
- `0x1e, 0x0`: constant bank `0x1e`, offset `0`, selecting the surface
  header/slot. It is not a raw virtual address.

Two runtime SASS patch modes now capture these inputs.

`SPY_CAPTURE_SULD_COORD=1` replaces `SULD` and `SUST` with:

```text
MOV R0, R4
MOV R1, R5
```

and preserves the `EXIT` writeback. With a `R32G32B32A32_UINT` color target,
pixel `(x,y)` reads back as `(x,y,0,0)`. The captured pixel-0 value is
`0,0,0,0`; pixel 1 is `1,0,0,0`, and so on.

The replacement MOVs must still wait scoreboard SB0:

```text
MOV R0, R4;[7:7:{0}:5:1]
MOV R1, R5;[7:7:{0}:5:1]
```

Without that wait, the output contained the original floating-point
`gl_FragCoord` values (`0x3f000000`, etc.) instead of the post-`F2I` integer
coordinates. This is another variable-latency forwarding case: the original
`SULD` wait is attached to the coordinate values as well as its result.

`SPY_CAPTURE_SULD_DESC=1` replaces both surface instructions with:

```text
LDC.64 R0, c[0x1e][0]
LDC.64 R2, c[0x1e][8]
EXIT                       ; req={SB0}
```

The output is the first 16 bytes of the selected surface header entry. This
experiment reads:

```text
00000009 00000000 00000000 00000000
```

Thus `c[0x1e][0]` currently contains the 64-bit value `9`, apparently a
surface header/index selector rather than a 64-bit memory address. Scanning
`c[0x1e][0x10]`, `[0x20]`, `[0x30]`, and `[0x40]` returned zero, so the actual
backing address is not stored directly in this constant window. The next step
is to locate the header table entry identified by this selector.

Both `SULD` and `SUST` encode the same `(bank=0x1e, offset=0)` selector in the
tested shader, so they resolve the same surface header.

#### Bindless storage images

Storage images support descriptor-indexed bindless access. The test shader
uses:

```glsl
#extension GL_EXT_nonuniform_qualifier : require
layout(set = 0, binding = 1, rgba8) uniform image2D storage_images[8];

uint index = uint(gl_FragCoord.x) & 7u;
vec4 value = imageLoad(
    storage_images[nonuniformEXT(index)], coord);
imageStore(
    storage_images[nonuniformEXT(index)], coord, value);
```

TITAN RTX exposes the required
`shaderStorageImageArrayDynamicIndexing` and
`shaderStorageImageArrayNonUniformIndexing` features. On sm75, the dynamic
surface selection appears in `R8`:

```text
F2I.FTZ.U32.TRUNC.NTZ R0, R4
SHF.L.U32 R0, R0, 0x2, RZ
LOP3.LUT R8, R0, 0x1c, RZ, 0xe2, !PT
LDC R8, c[0x1e][R8]
SULD.P.2D.CTA.IGN R0, [R6], R8
SUST.P.2D.CTA.IGN [R6], R0, R8
```

`R8` is the dynamically loaded 32-bit surface header selector. Unlike the
sampled-texture `.B` path, `SULD/SUST` directly accept this register operand,
so no fixed `(0x1e, 0x0)` immediate is used after the index selection.

sm120 keeps the same mechanism but unpacks the selected descriptor into a
uniform register:

```text
LDC R7, c[0x1e][R7]
LOP3.LUT R8, R7, 0xfffff, RZ, 0xc0, !PT
R2UR P1, UR4, R8
SULD.P.2D.IGN R12, [R4], UR4
...
SUST.P.2D.IGN [R4], R0, UR4
```

The surrounding sm120 `R2UR`/predicate loop handles divergent/nonuniform
descriptor selection when different lanes choose different image array
elements. Thus image bindless access is real on both generations, but it is
implemented as a dynamically selected surface header, not as a dynamic array
of raw 64-bit memory addresses.

Patching the sm75 bindless `SULD` to `MOV R0, R8` captures the selected surface
header index. In the current experiment all eight descriptor slots point to the
same `VkImageView`; all pixels therefore read selector `9`, independent of the
array index:

```text
rt0.nonzero[0..7] = 00000009 00000000 00000000 00000000
```

This confirms that the descriptor-array index first selects a value from
`c[0x1e]`, while the resulting 20-bit selector identifies the underlying
surface resource. A distinct-image control is still needed to show whether
different resources receive different selectors.

Relevant inputs:

- `PROBE_FRAGMENT_IMAGE_BINDLESS=1` enables the eight-element descriptor array.
- `probe_fragment_image_bindless.frag` performs nonuniform `imageLoad` and
  `imageStore`.

#### Special-register candidates

The `SpecialRegisters` enum in the sm90 ISA dump was searched for
`SURF/TEX/HEADER/TABLE/DESC/BASE/PTR/ADDRESS/INDEX`. There is no named
special register exposing a texture/surface header-table base or a bindless
descriptor-table base.

The only address-like names are:

| SR index | name | assessment |
|---:|---|---|
| 21/22 | `SR_DIRECTCBEWRITEADDRESSLOW/HIGH` | real low/high address pair, but semantically a direct CBE write target; not a descriptor-table base |
| 84/85 | `SR_ESR_PC`/`SR_ESR_PC_HI` | exception return PC; trap-only in user mode |
| 98/99 | `SR_CIRCULARQUEUEENTRYADDRESSLOW/HIGH` | circular command-queue entry address; unrelated to image surfaces |
| 138 | `SR_CgaLinearMemorySlot` | CGA linear-memory slot metadata, not a surface lookup pointer |

Other plausibly graphics-related fields are metadata rather than pointers:
`SR_INVOCATION_INFO` (29), `SR_MULTIPASSSHADERINFO` (45),
`SR_TTU_TICKET_INFO` (133), `SR_WARPGROUP_INFO` (134), and
`SR_WARPGROUPID` (135).

`SPY_CAPTURE_SR_PAIR=1 SPY_SR_LO=<n> SPY_SR_HI=<n>` reads a pair of SRs from
the patched fragment and writes their 32-bit values to the color target. On
TITAN RTX:

| SR pair | fragment readback |
|---|---|
| 21/22 direct-CBE address | `0 / 0` |
| 98/99 circular-queue address | `0 / 0` |
| 29/133 invocation/TTU metadata | `0 / 0` |

A positive control reading `SR_LANEID` (0) and `SR_TID.X` (33) produced the
expected per-lane nonzero sequence, so the patch path was working. These
candidate registers are not populated in the tested fragment invocation.

### CUDA external-memory access to an optimal image

`vulkan_cuda_interop.c` bypasses staging and exports the actual dedicated
Vulkan image allocation with
`VK_KHR_external_memory_fd`/`VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT`.
CUDA imports the same fd with `cudaImportExternalMemory` and maps it through
`cudaExternalMemoryGetMappedBuffer`.

Build and run:

```bash
gcc -O2 -I"$VULKAN_HEADERS/include" -I/usr/local/cuda/include \
  -o vulkan_cuda_interop vulkan_cuda_interop.c \
  -L/usr/local/cuda/lib64 -Wl,-rpath,/usr/local/cuda/lib64 \
  -lvulkan -lcudart
PROBE_GPU_NAME="TITAN RTX" ./vulkan_cuda_interop
```

For the tested 64x64 `R8G8B8A8_UNORM` optimal-tiled image:

```text
Vulkan image memory: size=16384 alignment=1024
external image features=0x6       ; EXPORTABLE | IMPORTABLE
vkMapMemory: VK_ERROR_MEMORY_MAP_FAILED (-5)
CUDA pointer: cudaMemoryTypeDevice
```

The CUDA device pointer therefore reaches the real backing allocation even
though the host cannot map the Vulkan device memory.

Writing a unique marker into each logical texel through Vulkan and reading the
raw allocation through CUDA recovered all 4096 texels. For `(x,y)`, let:

```text
tx = x & 3
ty = y & 3

word =
    tx
  | (ty << 2)
  | (((x >> 2) & 1) << 4)
  | (((y >> 2) & 1) << 5)
  | (((x >> 3) & 1) << 6)
  | (((y >> 3) & 1) << 7)
  | (((y >> 4) & 1) << 8)
  | (((y >> 5) & 1) << 9)
  | (((x >> 4) & 1) << 10)
  | (((x >> 5) & 1) << 11)

byte_offset = word * 4
```

This is a pure bit permutation of the X/Y coordinate bits for the tested
64x64 RGBA8 surface. The formula matched all `4096/4096` CUDA-observed texel
positions on both TITAN RTX (sm75) and RTX 5090 (sm120).

The first 4x4 microtile is linear:

```text
(0,0)..(3,3) -> raw 0x000..0x03c
```

The next X microtile starts at raw `0x40`, then the layout interleaves larger
X/Y coordinate bits according to the formula above.

Bidirectional verification also succeeded:

```text
CUDA wrote 0xdeadbeef at raw+0xe4 for texel(5,6);
Vulkan read 0xdeadbeef
```

Thus the CUDA device pointer is a valid base for raw `LDG/STG` access to the
same Vulkan image allocation. Converting an image coordinate to a raw address
still requires applying the surface format and tiling permutation:

```text
raw_address = image_base + tiled_byte_offset(x, y)
```

For the bindless selector chain, this supplies the missing final stage:

```text
bindless index
  -> c[0x1e][index]
  -> surface header
  -> allocation base VA
  + tiled offset
```

### `subpassLoad(input_attachment)` -> `TLD ARRAY_2D`

The two-subpass render pass makes attachment 0 a color target in subpass 0 and
an input attachment in subpass 1. The fragment shader:

```glsl
layout(input_attachment_index = 0, set = 0, binding = 2)
uniform subpassInput input_color;
out_color = subpassLoad(input_color);
```

lowers to:

```text
IPA.PASS R5, a[0x74]                 ; FragCoord.y
IPA.PASS R4, a[0x70]                 ; FragCoord.x
IPA.CONSTANT R6, a[0x64]             ; input attachment layer
F2I.FTZ.TRUNC.NTZ R5, R5
IMNMX.U32 R6, R6, 0xffff, PT
F2I.FTZ.TRUNC.NTZ R7, R4
TLD.SCR.LZ.NODEP R2, R0, R6, R5, 0x1e, 0x0, ARRAY_2D
EXIT
```

`subpassLoad` therefore lowers to a direct, LOD-zero texel fetch (`TLD`), not
to `TEX`, `SULD`, `LDG`, or any special "read input attachment" mnemonic.
The input attachment is represented as an `ARRAY_2D` texture; `a[0x64]`
supplies the layer, and `a[0x70]/a[0x74]` supply X/Y. The result is again in
`R0..R3` for implicit writeback at `EXIT`.

### sm120 descriptor unpacking

The instruction families are the same on sm120, but the resource descriptor is
first expanded into a uniform register:

```text
; texture
LDCU.TEXUNPACK UR4, c[0x1e][URZ]
TEX.SCR.DXY.NODEP R2, R0, R4, R5, UR4, 2D

; image
LDCU UR4, c[0x1e][URZ]
ULOP3.LUT UR4, UR4, 0xfffff, URZ, 0xc0, !UPT
SULD.P.2D.IGN R0, [R4], UR4
SUST.P.2D.IGN [R4], R8, UR4

; subpassLoad
LDCU.HDRUNPACK UR4, c[0x1e][URZ]
TLD.SCR.LZ.NODEP R2, R0, R6, R5, UR4, ARRAY_2D
```

Summary of the three paths:

| GLSL operation | sm75 | sm120 |
|---|---|---|
| `texture` | `TEX` with immediate TS pointer | `LDCU.TEXUNPACK` + `TEX` |
| bindless `texture` | dynamic `LDC` + `TEX ... .B` | dynamic `LDC` + `TEX ... .B` |
| `imageLoad/imageStore` | `SULD`/`SUST` with immediate TS pointer | `LDCU` + mask + `SULD`/`SUST` |
| `subpassLoad` | `TLD ... ARRAY_2D` | `LDCU.HDRUNPACK` + `TLD ... ARRAY_2D` |

All three source RGBA from the resource result registers and write the final
fragment color through the normal implicit `EXIT` path.

## Non-interpolated fragment inputs and `LDTRAM`

Several distinct GLSL constructs are non-interpolated, but they do not all use
the same hardware path.

| GLSL input | observed sm75 lowering |
|---|---|
| ordinary `flat in vec4` | four `IPA.CONSTANT` reads |
| `gl_PrimitiveID` | `IPA.CONSTANT a[0x60]` |
| `gl_FrontFacing` | `IPA.CONSTANT a[0x3fc]` |
| dynamically indexed array of four `flat in` values | jump table plus `IPA.CONSTANT` |
| `pervertexEXT/NV in vec4 colors[3]` | `LDTRAM.AB` plus `LDTRAM.C` |

`flat` is therefore still an interpolator/attribute input: `IPA.CONSTANT`
fetches one constant attribute value, normally selected by the provoking
vertex semantics. It is not a generic memory load.

The barycentric extension is the observed `LDTRAM` trigger. The probe declares:

```glsl
layout(location = 0) pervertexEXT in vec4 colors[3];
vec3 bary = gl_BaryCoordEXT;
out_color = bary.x * colors[0] +
            bary.y * colors[1] +
            bary.z * colors[2];
```

On sm75 this lowers to:

```text
IPA.PASS R2,  a[0x7c]             ; perspective/barycentric factor
IPA.PASS R9,  a[0x3b8]
IPA.PASS R3,  a[0x3b4]
IPA.PASS R11, a[0x3bc]

LDTRAM.AB R12, a[0x80]            ; vertices A/B, x component
LDTRAM.AB R14, a[0x84]            ; A/B, y
LDTRAM.AB R16, a[0x88]            ; A/B, z
LDTRAM.AB R18, a[0x8c]            ; A/B, w
LDTRAM.C  R1,  a[0x80]            ; vertex C, x
LDTRAM.C  R5,  a[0x84]            ; vertex C, y
LDTRAM.C  R7,  a[0x88]            ; vertex C, z
LDTRAM.C  R8,  a[0x8c]            ; vertex C, w
```

`LDTRAM` mode meaning matches the observed triangle storage:

- `LDTRAM.AB` (`mode=0`) returns a 64-bit pair containing the A and B vertex
  values for one attribute component.
- `LDTRAM.C` (`mode=1`) returns the 32-bit C vertex value.

The shader then applies the barycentric coordinates with `FMUL`/`FFMA` itself.
This is genuinely raw per-vertex attribute access, not hardware interpolation.
The same sequence appears on sm120.

The practical GLSL cases for `LDTRAM` are therefore programs using
`GL_EXT_fragment_shader_barycentric` / `GL_NV_fragment_shader_barycentric`:
per-vertex debug colors, barycentric wireframe/no-perspective interpolation,
and custom interpolation of raw vertex attributes. Ordinary `flat` inputs,
dynamic arrays of `flat` inputs, `gl_PrimitiveID`, and `gl_FrontFacing` did not
produce it in these probes.

## Screen-space derivatives: `dFdx` / `dFdy`

The derivative probe consumes a smooth interpolated varying:

```glsl
vec2 dx = dFdx(vcolor.xy);
vec2 dy = dFdy(vcolor.zw);
out_color = vec4(dx, dy);
```

On sm75, the fragment result values are first perspective-corrected:

```text
IPA.PASS R2, a[0x7c]              ; shared perspective factor
IPA.PASS R1, a[0x80]
IPA.PASS R3, a[0x88]
IPA.PASS R5, a[0x84]
IPA.PASS R7, a[0x8c]
MUFU.RCP R2, R2
FMUL.FTZ.RZ R4, R2, R1
FMUL.FTZ.RZ R6, R2, R3
FMUL.FTZ.RZ R5, R2, R5
FMUL.FTZ.RZ R7, R2, R7
```

The derivative itself is a two-step pixel-quad operation. First each lane
fetches a neighbor with a butterfly shuffle:

```text
SHFL.BFLY PT, R1,  R4, 0x1, 0x1c03  ; XOR lane 1
SHFL.BFLY PT, R3,  R6, 0x2, 0x1c03  ; XOR lane 2
SHFL.BFLY PT, R8,  R5, 0x1, 0x1c03  ; XOR lane 1
SHFL.BFLY PT, R10, R7, 0x2, 0x1c03  ; XOR lane 2
```

Then `FSWZADD` performs the signed quad combination:

```text
FSWZADD R0, R1,  R4, PNNPPNNP        ; dFdx(vcolor.x)
FSWZADD R2, R3,  R6, PNPNNPNP        ; dFdy(vcolor.y)
FSWZADD R1, R8,  R5, PNNPPNNP        ; dFdx(vcolor.z)
FSWZADD R3, R10, R7, PNPNNPNP        ; dFdy(vcolor.w)
EXIT
```

- XOR-1 selects the horizontal quad neighbor for X derivatives.
- XOR-2 selects the vertical quad neighbor for Y derivatives.
- `PNNPPNNP` is the X derivative sign pattern.
- `PNPNNPNP` is the Y derivative sign pattern.
- The alternating `P/N` signs produce the per-lane finite difference
  orientation inside the 2x2 pixel quad.

There is no standalone `DFDX`/`DFDY` mnemonic in these dumps. The operation is
implemented as pixel-quad shuffles followed by `FSWZADD`.

`fwidth` was also tested separately. It reuses the same X/Y quad differences
and then combines their absolute values:

```text
FSWZADD R0, R1, R4, PNNPPNNP
FSWZADD R3, R3, R4, PNPNNPNP
FSWZADD R1, R6, R5, PNNPPNNP
FSWZADD R6, R8, R5, PNPNNPNP
FADD.FTZ R0, |R0|, |R3|
FADD.FTZ R1, |R1|, |R6|
```

Thus:

```text
fwidth(x) = abs(dFdx(x)) + abs(dFdy(x))
```

and there is no additional derivative primitive.

sm120 has the same sequence, with the derivative mode made explicit in the
mnemonic:

```text
SHFL.BFLY ... 0x1 / 0x2
FSWZADD.DXY R0, R1,  R4, PNNPPNNP
FSWZADD.DXY R2, R3,  R6, PNPNNPNP
FSWZADD.DXY R1, R8,  R5, PNNPPNNP
FSWZADD.DXY R3, R10, R7, PNPNNPNP
```

### Fragment lane-to-pixel ordering inferred from the shuffle pattern

The `SHFL.BFLY` operands directly identify the two fragment-quad axes:

- `lane XOR 1` selects the horizontal neighbor used by `dFdx`.
- `lane XOR 2` selects the vertical neighbor used by `dFdy`.

Therefore lane bit 0 is the X parity and lane bit 1 is the Y parity inside a
2x2 quad. The `PNNPPNNP` X pattern is:

```text
lane0: PN  = +neighbor - current   (neighbor is X+1)
lane1: NP  = -neighbor + current   (neighbor is X-1)
lane2: PN
lane3: NP
```

The Y pattern is analogous:

```text
lane0/1: PN = +neighbor - current  (neighbor is Y+1)
lane2/3: NP = -neighbor + current  (neighbor is Y-1)
```

Thus the sign pattern compensates for which XOR neighbor each lane sees and
makes the final derivative consistently positive along screen X/Y.

The complete warp layout was verified by outputting
`(gl_SubgroupInvocationID, gl_WarpIDNV, gl_SMIDNV)` to an integer attachment
and reading back a pixel grid. One fragment warp covers a 4x8 pixel rectangle:

```text
y=0:   0   1 | 16  17
y=1:   2   3 | 18  19
y=2:   4   5 | 20  21
y=3:   6   7 | 22  23
y=4:   8   9 | 24  25
y=5:  10  11 | 26  27
y=6:  12  13 | 28  29
y=7:  14  15 | 30  31
         x=0..3
```

For warp-local pixel coordinates `qx` (0..3) and `qy` (0..7):

```text
lane = 16 * (qx >> 1) + 2 * qy + (qx & 1)
```

Equivalently:

```text
lane bit 0  = qx & 1
lane bits 1..3 = qy
lane bit 4  = qx >> 1
```

The four pixels of each 2x2 quad are therefore:

```text
(qx=0,qy=0) -> lane base + 0    ; top-left
(qx=1,qy=0) -> lane base + 1    ; top-right
(qx=0,qy=1) -> lane base + 2    ; bottom-left
(qx=1,qy=1) -> lane base + 3    ; bottom-right
```

Quad index advances vertically first within the left 2-column half, then
continues in the right 2-column half. This 4x8 mapping and the
`XOR1/XOR2 + FSWZADD` relationship were identical on sm75 and sm120.

## Fragment color writeback

The recovered fragment SASS contains no `STG`, `ST`, or other framebuffer-store
instruction. Color values are staged in output registers and `EXIT` is then
issued with no operands. A constant `out vec4` shader lowers to:

```text
IMAD.MOV.U32 R0, RZ, RZ, 0.25
MOV           R2, 0.75
IMAD.MOV.U32 R1, RZ, RZ, 0.5
MOV           R3, 1.0
EXIT
```

The final `R0..R3` contents are the RGBA result. The instruction stream does not
encode the color attachment index, component mask, blend state, or ROP write.
Those are pipeline/fixed-function state. `EXIT` itself has no destination or
store operand; its at-exit behavior is configured through a separate
`ATEXIT_PC`/CBU state, so this experiment cannot yet distinguish a direct
hardware export at `EXIT` from a fragment-stage at-exit handler performing it.

`discard` is separate from output writeback: the discard test lowers to
`@!P0 KILL` before the final `EXIT`, suppressing the eventual fragment update.

With a real two-attachment render pass (`PROBE_COLOR_TARGETS=2`), two shader
outputs map to consecutive GPR quads:

| shader output | component | register |
|---|---|---|
| `location=0` | r/g/b/a | `R0/R1/R2/R3` |
| `location=1` | r/g/b/a | `R4/R5/R6/R7` |

Both outputs are fully populated before a single operand-less `EXIT`; there is
still no per-attachment store/export instruction in SASS.

## `gl_FragDepth` writeback

`PROBE_DEPTH_OUTPUT=1` adds a `D32_SFLOAT` depth attachment with depth test and
write enabled (`compareOp=ALWAYS`) and reads the depth image back after the
draw. Without a depth attachment, the driver removes a `gl_FragDepth`
assignment entirely. With the attachment enabled, a constant assignment:

```glsl
gl_FragDepth = 0.25;
```

still lowers to just the four color moves followed by `EXIT`:

```text
IMAD.MOV.U32 R0, RZ, RZ, 0x3f800000
MOV           R2, 0x40400000
IMAD.MOV.U32 R1, RZ, RZ, 0x40000000
MOV           R3, 0x40800000
EXIT
```

The D32 output reads back exactly `0x3e800000`. The same `0x3e800000` appears
in the pipeline-binary metadata, so the constant depth was folded into
fixed-function output state rather than emitted as a shader instruction.

Making depth depend on fragment state forces a real value:

```glsl
gl_FragDepth = 0.25 + gl_FragCoord.x * (1.0 / 1024.0);
```

For one color output, the fragment function becomes:

```text
IPA.PASS R5, a[0x70]
MOV      R2, 0x3a800000
...
FFMA.FTZ R5, R5, R2, 0.25
...
EXIT
```

The depth readback is `0.250488281` (`0x3e804000`). R5 is the fragment depth
output value: `gl_FragCoord.x` is loaded there first and `FFMA` overwrites it
with the final depth.

The consumed register was confirmed dynamically by patching the instruction's
destination from R5 to R4. With the depth clear set to `0.75`, the readback
changed to `0.5` (the unmodified `gl_FragCoord.x` in R5), proving that the
fixed-function path still consumed R5. Two shader copies were patched.

With two color outputs (`R0..R7`), the compiler places the dynamic depth value
in `R9`; the same function then ends with `FFMA.FTZ R9, R9, R2, 0.25; EXIT`.
Thus the depth value is staged in an ordinary GPR selected by the compiler,
not written through a dedicated store instruction. No `STG`, depth-test, or
depth-write instruction exists in the shader: the pipeline metadata identifies
the staged value, and the late fragment-test/ROP fixed-function stages perform
the compare and write after the operand-less `EXIT`.

## Blend operations

`vulkan_graphics.c` accepts `PROBE_BLEND=...` and configures a real
`VkPipelineColorBlendAttachmentState`. The blend probe uses:

```text
source = (0.25, 0.50, 0.75, 0.50)
clear/destination = (0.10, 0.20, 0.30, 0.40)
format = R8G8B8A8_UNORM
```

The ordinary blend modes produced the expected fixed-point results:

| mode | state | RGBA8 readback |
|---|---|---|
| `alpha` | src-alpha, one-minus-src-alpha | `44 89 133 178` |
| `add` | one, one, saturated | `89 178 255 229` |
| `sub` | subtract, clamped | `39 76 115 25` |
| `rsub` | reverse subtract, clamped | `0 0 0 0` |
| `min` | MIN | `25 51 76 102` |
| `max` | MAX | `64 127 191 127` |
| `srccolor` | SRC_COLOR, ONE_MINUS_SRC_COLOR | `35 89 162 127` |
| `dstcolor` | DST_COLOR, ONE_MINUS_DST_COLOR | `29 66 110 127` |
| `saturate` | SRC_ALPHA_SATURATE, ONE_MINUS_SRC_ALPHA | `44 89 133 127` |

For MRT, `PROBE_COLOR_TARGETS=2 PROBE_BLEND=mixed_mrt` assigns alpha blending
to RT0 and additive blending to RT1. The two-output shader's second source is
`(0.60, 0.30, 0.20, 0.70)`. Readback was:

```text
rt0.pixel0.unorm = 44 89 133 178
rt1.pixel0.unorm = 178 127 127 255
```

This demonstrates that each attachment has independent color-pipeline state.
The two output quads remain `R0..R3` and `R4..R7`; there is no blend-specific
instruction between them and `EXIT`.

TITAN RTX advertises both `maxColorAttachments=8` and
`maxFragmentOutputAttachments=8`. `probe_mrt8.frag` was also run through a real
eight-attachment render pass; all eight targets were exported and read back
successfully:

```text
rt0.pixel0.unorm = 32 64 96 255
rt1.pixel0.unorm = 255 223 191 255
rt2.pixel0.unorm = 64 127 191 255
rt3.pixel0.unorm = 191 127 64 255
rt4.pixel0.unorm = 51 102 153 255
rt5.pixel0.unorm = 153 102 51 255
rt6.pixel0.unorm = 76 153 229 255
rt7.pixel0.unorm = 229 153 76 255
```

This is the hardware/driver-supported maximum. A deliberately invalid
nine-attachment run, made only by raising the harness limit, reached
`vkQueueWaitIdle` with `VK_ERROR_DEVICE_LOST` (`-4`); the supported MRT count is
therefore eight.

### Mixed-component MRT outputs

`PROBE_MIXED_OUTPUTS=1` uses `probe_mixed_outputs.frag` with eight attachments
whose formats and output component counts vary:

| location | Vulkan format | GLSL output | live registers |
|---|---|---|---|
| 0 | `R32G32B32A32_SFLOAT` | `vec4` | `R0..R3` |
| 1 | `R32G32_SFLOAT` | `vec2` | `R4..R5` |
| 2 | `R32_SFLOAT` | `float` | `R8` |
| 3 | `R32G32B32A32_SFLOAT` | `vec4` | `R12..R15` |
| 4 | `R32G32_SFLOAT` | `vec2` | `R16..R17` |
| 5 | `R32_SFLOAT` | `float` | `R20` |
| 6 | `R32G32B32A32_SFLOAT` | `vec4` | `R24..R27` |
| 7 | `R32G32_SFLOAT` | `vec2` | `R28..R29` |

The sm75 driver does not pack component values tightly. Every fragment output
`location=N` owns the fixed four-GPR window `R(4N)..R(4N+3)`; components not
present in that location's output type are simply not written. The recovered
fragment SASS contains assignments such as:

```text
IMAD.MOV.U32 R0,  RZ, RZ, 0x3f800000  ; location 0 x
MOV           R1,  0x40000000         ; location 0 y
IMAD.MOV.U32 R2,  RZ, RZ, 0x40400000  ; location 0 z
MOV           R3,  0x40800000         ; location 0 w
IMAD.MOV.U32 R4,  RZ, RZ, 0x40a00000  ; location 1 x
MOV           R5,  0x40c00000         ; location 1 y
IMAD.MOV.U32 R8,  RZ, RZ, 0x40e00000  ; location 2 x
IMAD.MOV.U32 R12, RZ, RZ, 0x41000000  ; location 3 x
...
IMAD.MOV.U32 R16, RZ, RZ, 0x41400000  ; location 4 x
IMAD.MOV.U32 R20, RZ, RZ, 0x41600000  ; location 5 x
IMAD.MOV.U32 R24, RZ, RZ, 0x41700000  ; location 6 x
IMAD.MOV.U32 R28, RZ, RZ, 0x41980000  ; location 7 x
EXIT
```

All eight attachments read back the expected values. Thus the lack of
per-attachment instructions remains true: `EXIT` is still operand-less, while
the fragment-output ABI reserves one four-register window per logical location.

The TITAN RTX exposes `VK_EXT_blend_operation_advanced`. The probe also tested
these advanced operations with unpremultiplied source/destination and
uncorrelated overlap:

| advanced blend op | RGBA8 readback |
|---|---|
| `MULTIPLY_EXT` | `36 76 120 178` |
| `SCREEN_EXT` | `58 112 163 178` |
| `OVERLAY_EXT` | `38 83 136 178` |
| `COLORDODGE_EXT` | `44 98 176 178` |
| `COLORBURN_EXT` | `34 69 108 178` |
| `SOFTLIGHT_EXT` | `38 83 134 178` |
| `DIFFERENCE_EXT` | `46 91 136 178` |
| `EXCLUSION_EXT` | `56 105 147 178` |
| `HSL_HUE_EXT` | `42 83 125 178` |
| `HSL_SATURATION_EXT` | `34 85 135 178` |
| `HSL_COLOR_EXT` | `34 85 136 178` |
| `HSL_LUMINOSITY_EXT` | `61 103 145 178` |

For the one-output shader, the recovered fragment function was identical
across all nine ordinary modes and all twelve advanced modes. A representative
constant-color shader was still:

```text
IMAD.MOV.U32 R0, RZ, RZ, 0.25  ; BATCH_START
MOV           R2, 0.75
IMAD.MOV.U32 R1, RZ, RZ, 0.5
MOV           R3, 0.5
EXIT
```

The 80-byte encoding had one SHA-256 prefix, `a15340db24304e48`, in every
one-output run, including the entry control word `0x040fc200078e00ff`
(`batch_t=1`, `stall=1`, `yield=1`). Blend equations, factors, write masks,
attachment indices, and advanced-op selection therefore live entirely in
fixed-function color-pipeline/ROP state, not in fragment SASS.

The MRT shader has four additional constant moves for `R4..R7`, but follows
the same pattern: one `BATCH_START` on the first move, seven further ordinary
moves, and an operand-less `EXIT`.

## Patching BMOV reads into fragment SASS

The graphics compiler's SASS is present in writable anonymous memory before the
pipeline is submitted. The `SPY_PATCH_ATEXIT=1` preload mode replaces two
color-constant writes with:

```text
BMOV.32 R0, ATEXIT_PC.LO  ; wr=SB5, stall=8, yield=0
BMOV.32 R1, ATEXIT_PC.HI  ; wr=SB5, stall=8, yield=0
EXIT                      ; req={SB5}
```

Both BMOVs claim the same write scoreboard; EXIT waits that scoreboard before
implicit color export. The attachment is `R32G32B32A32_UINT`, so the two words
can be read back without float conversion.

For sm75, all 4096 rendered pixels read `ATEXIT_PC = 0`. A positive control
that patches the same two instructions to `BMOV R0/R1, MACTIVE` reads back
`0xffffffff, 0xffffffff` and leaves the other two components unchanged. This
validates both BMOV completion and the EXIT scoreboard wait. The positive
control also passed with stall values 0, 1, 4, and 8 and with `yield=1`;
therefore the scoreboard wait, rather than the stall count, is what makes the
read safe in this construction.

Replacing the two BMOV selectors with `TRAP_RETURN_PC.LO/HI` also reads zero in
all 4096 pixels. Thus both candidate continuation PCs are readable in an
ordinary fragment invocation, but neither is populated by this pipeline.

## Brute-searching for a fragment epilogue

The fragment pipeline binary was scanned both statically and in the live
process after a draw. The constant-color fragment ends with:

```text
EXIT
BRA 0x0
NOP
NOP
```

The `BRA 0x0; NOP; NOP` sequence is a function-end sentinel/padding, not an
epilogue. In the pipeline binary, metadata begins immediately after it.

A live process scan found two copies of the exact 80-byte fragment function:

```text
anonymous process heap
/dev/nvidiactl mapping
```

The scan validated aligned 16-byte instructions individually, grouped
consecutive valid instructions, and inspected up to 64 KiB after each `EXIT`.
No common fragment epilogue block followed either copy. The next valid code
blocks in the mappings were unrelated vertex/helper functions.

Runtime checks:

1. Replacing the normal EXIT control with `EXIT.NO_ATEXIT` produced the same
   4096-pixel result:

   ```text
   11111111 22222222 33333333 44444444
   ```

2. Replacing the bytes after `EXIT` with:

   ```text
   MOV R0, 0xAAAAAAAA
   EXIT
   ```

   also left the result unchanged. Therefore normal `EXIT` does not
   fall-through to the following bytes.

Combined with the earlier zero `ATEXIT_PC` and `TRAP_RETURN_PC` reads, this
shows no evidence for a per-shader SASS epilogue in the ordinary fragment
color path. The observed behavior is most consistent with an implicit
fixed-function export at `EXIT`; if a hidden continuation exists, its PC is
not exposed through `ATEXIT_PC`, not stored next to the shader function, and
is not reached by ordinary fall-through.

The generic brute-force method is still useful:

1. Patch/instrument the shader with a unique immediate signature.
2. Pause after draw and scan `/proc/<pid>/mem`.
3. Find all aligned copies of the function.
4. Validate every aligned 16-byte word independently with nvdisasm.
5. Group consecutive valid instructions and inspect all runs after `EXIT`.
6. Confirm candidate control flow dynamically with no-at-exit/fall-through
   patches.
