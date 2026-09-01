# CUDA device `printf`: dynamic SASS call-chain trace

## Summary

A CUDA kernel containing `printf(...)` does **not** call a large formatter
that was linked into the kernel cubin.  In the tested CUDA 13.1 / NVIDIA
590.48.01 / RTX 5090 (`sm_120`) stack, the kernel cubin leaves `vprintf` as an
undefined symbol in `.rela.nv.constant4`.  The CUDA loader fills that constant
slot with the address of a driver-provided syscall trampoline.

The dynamically observed chain is:

```text
user kernel
  CALL.ABS.NOINC R2
    |
    v
syscall_trampoline_vprintf          0x0400 bytes
    |
    v
vprintf                             0x0180 bytes
    |
    v
vfprintf                            0x0180 bytes
    |
    v
vfprintf_internal                   0x4300 bytes (17,152 bytes)
    |
    `-- __cuda_sm20_rem_u64         0x0400 bytes
```

The first three functions are state-preserving/wrapper layers.  The large
implementation is `vfprintf_internal`, not the first address installed in the
user cubin.

This distinction matters to sassdbg M12: a loader-resolved CUDA system call is
an opaque external call edge, not a user device-function closure that should
automatically be copied per warp.

## Test environment

```text
GPU:       NVIDIA GeForce RTX 5090, compute capability 12.0
CUDA:      13.1
driver:    590.48.01
target:    sm_120
libcuda:   /usr/lib/x86_64-linux-gnu/libcuda.so.590.48.01
```

All absolute GPU virtual addresses below are examples from one process.  They
change between runs because the relevant modules are relocated.

## Static view of a minimal kernel

The probe kernel was structurally:

```cuda
__global__ void printf_target(unsigned long long *out) {
    printf("sassdbg printf target probe\n");
    out[0] = 0xBAD0BAD0BAD0BAD0ull;
}
```

`nvcc -arch=sm_120 -cubin` produced an undefined `vprintf` symbol and these
constant-bank relocations:

```text
.rela.nv.constant4:
    offset 0x0  type 2  -> $str
    offset 0x8  type 2  -> vprintf
```

The relevant kernel SASS was:

```sass
MOV R2, 0x8
...
LDC.64 {R2,R3}, c[0x4][R2]       // relocated vprintf target
...
LEPC {R20,R21}, return_pc
CALL.ABS.NOINC {R2,R3}
```

Thus the user cubin contains neither the device `printf` implementation nor a
direct text relocation on the `CALL`.  It contains a relocated function
pointer in constant bank 4.

The same standalone cubin cannot be loaded directly through the repository's
plain `cuModuleLoadData` path: the unresolved CUDA system function makes the
image invalid there (`CUDA_ERROR_INVALID_IMAGE`).  The ordinary CUDA runtime
fatbin-registration path supplies the system binding.

## Dynamic target capture

CUDA permits addresses of ordinary RDC device functions, but `printf` and
`vprintf` are compiler builtins with special overload/lowering rules.  Taking
their addresses directly did not yield a usable final executable.  The probe
therefore observed the already lowered `CALL` operand.

The executable was built with `-no-compress`, and the `sm_120` cubin embedded
in the host executable was located without changing its relocations.  Four
instructions around the generated call/marker sequence were replaced:

```text
original                         observation patch
-----------------------------    ----------------------------------------
CALL.ABS.NOINC {R2,R3}           NOP
LDC.64 {R2,R3}, #param(out)      LDC.64 {R4,R5}, #param(out)
MOV.64 {R4,R5}, marker           NOP
STG.E.64 [R2], {R4,R5}           STG.E.64 [R4], {R2,R3}
```

The CUDA runtime still performed the original `.nv.constant4` relocation.
The patched kernel merely wrote the resulting `R2:R3` value to `out` instead
of executing the call.

A second, ordinary CUDA kernel then copied 128-bit words from that GPU code VA
to a global-memory buffer.  Each absolute-immediate call in the copied code
was decoded and its callee was copied again in the **same CUDA context**.
Keeping the walk in one process is essential because the code VAs are
context/process-specific.

`tools/disasm.py` was connected by placing the captured raw words into a
temporary cubin text section.  It decoded the ordinary control flow and data
instructions.  Some system-state `BMOV` encodings (opcodes `0x355/0x356`) and
one `RET` form remain gaps in its solver; `cuobjdump` of the matching driver ELF
was used to name those instructions.

## Dynamically observed chain

One complete run reported:

```text
kernel CALL target:        0x7f56bb2b3a00
trampoline inner target:   0x7f56bb207400
vprintf inner target:      0x7f56bb206a00
vfprintf inner target:     0x7f56bb201100
```

These resolved as:

```text
0x7f56bb2b3a00  syscall_trampoline_vprintf
0x7f56bb207400  vprintf
0x7f56bb206a00  vfprintf
0x7f56bb201100  vfprintf_internal
```

The first target changed between processes (for example, another run produced
`0x7f43e32b3a00`), while its code and relative role remained identical.

## Layer 1: `syscall_trampoline_vprintf`

The loader resolves the user's undefined `vprintf` reference to the normal
stack-switching trampoline, not directly to the 384-byte `vprintf` wrapper and
not to `syscall_no_stack_switch_trampoline_vprintf`.

The trampoline is exactly 0x400 bytes including padding.  Its live body ends
with `RET` at offset `0x330`.  It saves the caller's local-stack and warp
control state at high local-memory offsets:

```sass
STL [RZ-0x23c], R1
STL [RZ-0x230], R2
BMOV.32 R2, MEXITED
STL [RZ-0x224], R2
BMOV.32 R2, OPT_STACK
STL [RZ-0x220], R2
BMOV.32 R2, THREAD_STATE_ENUM.0
...
BMOV.32 R2, THREAD_STATE_ENUM.4
...
BMOV.32 R2, MACTIVE
STL [RZ-0x228], R2
STL.64 [RZ-0x238], {R20,R21}
```

It then installs the syscall stack/state, constructs its own return address,
and calls the driver `vprintf` implementation:

```sass
MOV R1, 0xfffdc0
...
LEPC {R20,R21}
IADD R20, P0, R20, 0x50
IADD.X R21, R21, RZ, P0
LDL R2, [RZ-0x230]
CALL.ABS.NOINC <vprintf>
```

After the call it executes `WARPSYNC` with the saved active mask, restores
`THREAD_STATE_ENUM.0-4`, `OPT_STACK`, `MEXITED`, R20:R21 and R1, and returns to
the user kernel through the explicit R20:R21 return address.

The trampoline ELF contains:

```text
.rela.text.syscall_trampoline_vprintf:
    text+0x1a0  type 0x4b -> vprintf
```

The dynamically captured instruction at `+0x1a0` encoded the second target
`0x7f56bb207400`.

## Layers 2 and 3: `vprintf` and `vfprintf`

Both functions are small wrappers padded to 0x180 bytes.

`vprintf` rearranges the incoming format/argument-list registers, saves its
return pair, and calls `vfprintf`:

```sass
IADD3 R1, R1, -0x8, RZ
MOV R9, R7
MOV R8, R6
STL [R1+0x4], R21
STL [R1], R20
MOV R6, R4
MOV R7, R5
CS2R R4, SRZ
MOV R20, <relocated return lo>
MOV R21, <relocated return hi>
CALL.ABS.NOINC <vfprintf>
...
RET.ABS.NODEC {R20,R21}, 0x0
```

`vfprintf` is an even thinner frame/return wrapper around
`vfprintf_internal`.

The dynamic images matched the driver ELF byte-for-byte except at loader
relocation sites:

```text
vprintf:   differences only at 0x80, 0x90, 0xa0
vfprintf:  differences only at 0x30, 0x40, 0x50
```

The first two words in each set materialize an absolute return VA; the third
is the absolute call target.

## Layer 4: `vfprintf_internal`

`vfprintf_internal` is 0x4300 bytes (1,072 encoded instruction slots,
including tail padding).  Its live return is near offset `0x41f0`.  It allocates
a 0xb8-byte local frame and contains the substantive device-side printf
implementation.

Observed behavior includes:

- byte-wise scanning of the format string (`LD.E.U8`);
- explicit comparisons with ASCII `0x25` (`'%'`);
- narrow- and wide-character paths (`LD.E.U8` and `LD.E.U16`);
- parsing/construction using `PRMT`, shifts, predicates and many CFG arms;
- warp-cooperative work with `VOTE`, `VOTEU`, `FLO`, `SHFL`, `WARPSYNC` and
  collective `WARPSYNC` forms;
- 64-bit global atomic allocation (`ATOM.E.ADD.64.STRONG.GPU`);
- shared/global atomic spin-update paths (`ATOMS.CAST.SPIN.64`);
- system-visible publication with `MEMBAR.SC.SYS`;
- byte copies into the selected output record;
- ring-buffer arithmetic, including a call to `__cuda_sm20_rem_u64`.

The driver ELF names the relevant constant-bank-1 objects:

```text
c[1][0x20]  printfBuffer       (u64)
c[1][0x28]  printfGlobalPtr    (u64)
c[1][0x30]  printfHostGlobalPtr (u64)
c[1][0x38]  printfBufLen       (u32)
```

This shows that device printf is not a blind two-pointer enqueue.  The GPU
code parses enough of the format to determine and encode the argument/record
layout, coordinates participating lanes, reserves buffer space atomically and
publishes records into driver-managed storage.  This experiment did not trace
the later host-side drain/rendering path, so it does not by itself assign every
formatting responsibility between GPU and host.

The only dynamic/static differences across the entire 17,152-byte image were:

```text
0x2030  relocation type 0x38 -> vfprintf_internal + 0x2070
0x2040  relocation type 0x39 -> vfprintf_internal + 0x2070
0x2060  relocation type 0x4b -> __cuda_sm20_rem_u64
```

Every other 128-bit word matched the `sm_120` image embedded in the driver.

## Driver packaging

The driver contains at least two relevant `sm_120` CUDA ELFs:

1. A normal device-runtime ELF containing `vprintf`, `vfprintf`,
   `vfprintf_internal`, their constant-bank objects, and arithmetic helpers.
2. A separate syscall-trampoline ELF containing fixed-size normal and
   no-stack-switch trampolines for `vprintf`, `malloc`, `free`, device-launch
   operations and many other CUDA system calls.

For driver 590.48.01 the two blobs were found inside `libcuda.so` by scanning
for embedded ELF headers and selecting CUDA `sm_120` flags.  Their host-file
offsets are driver-build-specific and must not be treated as ABI.

The ordinary `libcudadevrt.a` `sm_120` image did **not** define `vprintf`; it
also left CUDA syscall symbols undefined.  Therefore the final binding is a
driver/runtime service, not merely static linkage of `libcudadevrt.a` into the
user cubin.

## Consequences for sassdbg M12

### 1. Split local call closure from external runtime edges

M12's “copy reachable device functions per warp” should mean functions that
belong to the user's resolvable link unit.  It should not recursively absorb
driver system functions merely because a runtime target is reachable.

Suggested edge classification:

```text
INTERNAL_DIRECT
    target symbol/range belongs to the user module closure; copy and relocate

EXTERNAL_RUNTIME
    loader-resolved target outside the user module; preserve as an opaque call

INDIRECT_UNKNOWN
    runtime target cannot be proven internal or supported; fail closed or
    allow continue-only behavior
```

### 2. Preserve the original loader binding

For printf, the private kernel should retain the relocated `c[4]` load and
call the original syscall trampoline.  A required M12 probe is to verify that
heap-resident private code still observes the original module's relocated
constant-bank-4 value.  If it does, no driver code needs to be copied.

The user kernel's preceding `LEPC` should naturally construct a return address
inside the warp-private image.  The syscall trampoline already preserves the
incoming R20:R21, constructs its own inner return address, then finally returns
through the saved pair.  This ABI is structurally compatible with returning to
a private heap copy.

### 3. Step over external calls; do not patch system code

The safe default for an `EXTERNAL_RUNTIME` call is source-level step-over:

1. stop at the private call site;
2. arm the private return continuation;
3. execute the loader-resolved external target unchanged;
4. stop when it returns to the private continuation.

Stepping into `syscall_trampoline_vprintf` would require debugger ownership of
driver code, its module-specific `c[1]`, private globals and special syscall
state.  M12 should not mutate or clone that code by default.

### 4. Do not infer closure from a symbol name alone

The undefined symbol is named `vprintf`, but its user-module function pointer
resolves to `syscall_trampoline_vprintf`.  Consequently, symbol identity alone
does not describe the runtime first instruction.  Closure analysis needs both
static symbol/relocation classification and runtime address-range ownership.

### 5. Keep fail-closed relocation rules

This case uses a data/constant relocation to obtain an external function
pointer, followed by a register-target absolute call.  Supporting direct text
relocations alone is insufficient.  Conversely, copying the full system
closure would accidentally import module-specific constants and state.

The initial M12 implementation should therefore support this pattern as an
opaque external call only after the constant-bank and private-return probes
pass; otherwise it should reject the image with a precise diagnostic.

