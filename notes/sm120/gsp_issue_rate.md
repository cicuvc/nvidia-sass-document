# GB202 GSP issue-rate controls and the consumer tensor limit

<!-- notes-status -->
**Status:** active  
**Evidence:** sm120-silicon  
**Tier confidence:** high  
**Last verified:** 2026-10-26  
**Probe:** RTX 5090 (GB202, sm_120), driver 615.71.09, and supplied A100 /
RTX PRO 6000 timing comparison  
**Open items:** find a Blackwell-compatible authenticated payload path that
opens `FEAT_OVR_PLM`, then perform a controlled `FMLA32` full-rate A/B test  
**Audit:** `tools/notes_audit.py` · basis: explicit `Silicon:` header line

## Conclusion

Silicon: RTX 5090 (GB202, sm_120), driver 615.71.09, device ID `10de:2b85`,
VBIOS `98.02.2E.40.53`, 2026-10-26.

The consumer tensor reduction is an **issue/admission-rate limit**, not a
disabled arithmetic backend.  With the same GB202 silicon, an RTX PRO 6000
issues the tested `HMMA.16816.F32` at 8 clocks/instruction while the RTX 5090
takes 16.  `QMMA.16832.F32` shows the same 2x interval, while MXFP8
`QMMA.SF` remains full rate.  A100 also measures 8 clocks for the HMMA form.
The opcode-class selectivity rules out a generic tensor backend throughput
cut.

The controlling class is the table's old **FMLA32** selector, despite the
name having no visible relationship to tensor instructions.  The
`DMLA` entry is unrelated and unsupported on this SKU.  Ada evidence closes
the semantic loop: on an RTX 4070 Ti SUPER, stock `fmla32=1` changes to
`fmla32=0` after the four-PLM unlock and FP16/BF16-to-FP32 tensor issue rate
simultaneously doubles.  INT8, `dp4a`, and scalar FP32 do not change.

The public Ada implementation applies a hardware override, not an OTP fuse
rewrite:

| register | BAR0 offset | purpose |
|---|---:|---|
| `FEAT_OVR_PLM` | `0x00823804` | write permission for the feature-override block |
| `FEAT_READOUT_1` | `0x00823818` | nine effective 3-bit speed-select fields |
| `FEAT_OVR_SM_SPEED_SELECT` (`SS0`) | `0x0082381c` | eight 4-bit selectors, including FMLA32 |
| `FEAT_OVR_SM_SPEED_SELECT_1` (`SS1`) | `0x00823820` | ninth selector, attributed to IMLA4 |

Each `SS0` nibble has bit 3 as the override enable and bits 2:0 as the
speed-select value.  The Ada unlock writes `SS0=0x88888888` and `SS1=0x8`,
making every enabled selector request `0` (full rate).  Stock host writes are
ignored because `FEAT_OVR_PLM` initially permits writes only from the highest
privilege level (`0xffffff8f` low byte `0x8f`).  The published transaction
uses a signature-only V67 modification to the signed Ada booter, runs it on
SEC2, and makes the authenticated firmware change `FEAT_OVR_PLM` to
`0xffffffff`; only then can the host write `SS0/SS1`.

### How the Ada path opens the write permission

The Ada loader runs before the stock NVIDIA driver binds, after a full
power-off.  The transaction has two distinct privilege domains:

1. The host starts the board ROM's FWSEC-FRTS image on GSP, establishing the
   protected firmware reservation.
2. It starts the unchanged signed AD102 booter on SEC2.  During the signature
   copy, an unchecked DMA writes the crafted V67 signature payload over booter
   DMEM stack slots.  The payload preserves the expected canary and replaces
   the saved return address.
3. Returning through that slot enters existing instructions already present
   in the authenticated booter image.  This is a control-flow chain inside the
   signed Falcon code; no unsigned host code is executed in heavy-secure mode.
4. The selected gadgets perform protected writes to WPR_CFG (`0x001fa7cc`),
   FBPA (`0x009a0148`), WPR (`0x001fa7c4`), and FEAT_OVR_PLM (`0x00823804`).
   The first three are part of the published transaction; FEAT_OVR_PLM is the
   one required for subsequent host selector writes.  The payload then puts
   the marker `0x67b00001` in SEC2 mailbox 0 and halts.
5. The host verifies the marker, SEC2 HALT, and independent readbacks of the
   required permission words.  Only after `FEAT_OVR_PLM == 0xffffffff` does it
   write `SS0/SS1` and confirm `FEAT_READOUT_1 == 0`.
6. PCIe FLR resets transient WPR permissions; the FEAT override and selector
   values survive.  The stock driver then initializes the already-halted GPU.

`FEAT_OVR_PLM=0xffffff8f` encodes the permission gate in its low byte:

```text
bits[3:0] = 1111  all privilege levels may read
bits[7:4] = 1000  only the highest level (L3/heavy-secure) may write
```

Writing `0xffffffff` opens the remaining read/write/source-enable fields.  The
GB202 value `0xfffffb8f` has the same low permission byte but one source-enable
bit differs at bit 10; that difference has not yet been interpreted.

This mechanism is specific to the selected booter family.  The AD102 V67 chain
uses AD102 instruction addresses and geometry, so it cannot be used unchanged
on GB202 even though the resulting 5090 BAR register layout is now confirmed.

The local 5090 reports `FMLA32=3`, while the Ada stock card reports `1`.
A targeted BAR0 read confirms that this is not a stale RM value: the GB202
hardware readout field is `6`, versus Ada's `2`.  The old RM enum labels
code 3 as 1/8, but that label does not translate directly into the observed
16-versus-8-cycle interval; the selector may feed another generation-specific
mapping.  The A/B Ada result is stronger evidence of identity than the enum's
nominal ratio.

## Firmware evidence

Local images:

| file | size | relevant finding |
|---|---:|---|
| `/lib/firmware/nvidia/615.71.09/gsp_ga10x.bin` | 27,043,992 B | GSP RISC-V image, `.fwversion=615.71.09`; contains `RMOverrideSmSpeedSelect` and `RMOverrideSmSpeedSelect1` |
| `/lib/firmware/nvidia/615.71.09/ucodes_ga10x.bin` | 58,215,936 B | `NVUCODES` v1 container, 1,293 entries, fingerprint `0x2d38befecdb703a6` |

The GSP command dispatch table contains:

| command | parameter size | handler VA |
|---|---:|---:|
| `GR_GET_SM_ISSUE_RATE_MODIFIER_V2` (`0x2080123c`) | `0x7fc` | `0x14c546c` |
| `GR_GET_SM_ISSUE_THROTTLE_CTRL` (`0x2080123d`) | `0x7fc` | `0x144c60c` |

Thus both values below are generated by GSP, not synthesized by the host.
The GB202 handler image is signed/high-entropy and does not expose a
straightforward static MMIO-write sequence to the available tooling.  A
separate targeted BAR0 read nevertheless confirmed the inherited feature
cluster described below.

## Obtaining the GB202 SEC2/GSP-FMC image

Blackwell no longer exposes a `kgspGetBinArchiveBooterLoadUcode_GB202`
archive like the one used for Ada.  For GB202, SEC2 boots a **GSP-FMC**
image.  The normal non-CC GSP-RM path selects
`kgspGetBinArchiveGspRmFmcGfwProdSigned_GB202()` in
`kernel_sec2_gb20b.c`.

The matching 615.71.09 open-driver source is already installed locally:

| asset | generated source | original name | size |
|---|---|---|---:|
| production FMC image | `g_bindata_kgspGetBinArchiveGspRmFmcGfwProdSigned_GB202.c` | `g_gsp_gb20x_dyn_prd_gfw_image.bin` | 287,304 B |
| debug-signed FMC image | `g_bindata_kgspGetBinArchiveGspRmFmcGfwDebugSigned_GB202.c` | `g_gsp_gb20x_dyn_prd_gfw_prd_dbg_sign_image.bin` | 287,304 B |
| confidential-compute image | `g_bindata_kgspGetBinArchiveGspRmCcFmcGfwProdSigned_GB202.c` | `g_gsp_gb20x_dyn_spdm_prd_gfw_image.bin` | 257,096 B |

The first two `UCODE_IMAGE` blobs are byte-identical:

```text
sha256 5b74fefd42fc7b5f2e30c03e7558631d76899d9c6237ee9115c4e0829c63548b
```

Their `UCODE_HASH` blobs are also identical.  Only `UCODE_SIG` and
`UCODE_PKEY` differ.  In other words, the 615 debug-signed archive is the
exact same firmware image carrying debug signing material, not a separately
encrypted debug build.

The embedded C arrays can be reconstructed without compiling the driver:

```sh
python3 tools/extract_bindata_array.py \
  /usr/src/nvidia-615.71.09/src/nvidia/generated/g_bindata_kgspGetBinArchiveGspRmFmcGfwProdSigned_GB202.c \
  /tmp/gb20x-fmc-prod.bin \
  --array kgspBinArchiveGspRmFmcGfwProdSigned_GB202_BINDATA_LABEL_UCODE_IMAGE_data

python3 tools/extract_bindata_array.py \
  /usr/src/nvidia-615.71.09/src/nvidia/generated/g_bindata_kgspGetBinArchiveGspRmFmcGfwDebugSigned_GB202.c \
  /tmp/gb20x-fmc-debug-signed.bin \
  --array kgspBinArchiveGspRmFmcGfwDebugSigned_GB202_BINDATA_LABEL_UCODE_IMAGE_data
```

### Decryption attempt

The public debug test key has now been recovered from an earlier revision of
the `nvlight` firmware gist.  It is the all-zero AES-128-ECB known-answer key
from the Ada/CMP firmware work:

```text
25EFCDAB896745231032547698BADCFE
```

This is a published test key, not a production secret.  The independent
known-answer check is:

```text
AES-128-ECB(key, 00 * 16) = 717d1494eaca317ff106195258b38377  PASS
```

The current public gist labels the known plaintext as `FF * 16`; that label is
wrong.  Encrypting `00 * 16` produces the published marker, while encrypting
`FF * 16` produces `fd7e5b57768a309baabcc6903118c8f5`.

As a real-firmware control, extracting the AD102 `IMAGE_DBG` and decrypting
its `[0x100, 0x7e00)` code range with this key produces:

```text
code bytes   32256
code SHA256  7cdc788c0732c64d655349bda821e78a3ebb0155324a9f439cc1714ccd8a8a85
```

That is byte-for-byte the independently published AD102 debug listing, so the
key and the old BooterLoad AES mode are no longer in doubt.

The same key does not produce GB202 RISC-V code from the FMC image.  AES ECB,
CBC, CFB, OFB and CTR trials over the candidate code/data ranges remain at
approximately 7.999 bits/byte with no instruction stream, strings or
compressed-stream signature.  `zlib`, raw DEFLATE, gzip, bzip2, xz and zstd
also reject the results.  This is not a failure of the test key: key 37
belongs to the SEC2 Falcon image class, whereas the Blackwell FMC carries an
encrypted RISC-V monitor image.

### GB202 FMC and GspRmBoot layout

The 287,304-byte `GspRmFmcGfw` image is an assembly container, not an opaque
new cipher format.  Its 72-byte header is:

| offset | value | interpretation |
|---:|---:|---|
| `0x00` | `0x00480403` | `u16 0x0403`; `u16 0x0048` header size |
| `0x04` | `0x00046200` | bytes after the header |
| `0x0c` | `0x00037000` | first payload size |
| `0x14` | `0x0000e800` | second payload size |
| `0x18` | `0x00000104` | per-image control word; fields not yet decoded |
| `0x20` | `0x00002801` | per-image version/generation word |

For GB202 the regions are therefore:

```text
[0x00048, 0x37048)  payload A, 225,280 B
[0x37048, 0x45848)  payload B,  59,392 B
[0x45848, 0x46248)  manifest,    2,560 B
```

The separately published `GspRmBoot_GB202` image has a 92-byte
`RM_RISCV_UCODE_DESC`:

```text
version              6
manifestOffset       0x00000  manifestSize       0x00a00
monitorDataOffset    0x00a00  monitorDataSize    0x0e800
monitorCodeOffset    0x0f200  monitorCodeSize    0x37000
populated size       0x46200  (290,816-byte asset has 0xe00 zero tail)
```

Its pieces are byte-identical to the FMC container:

```text
FMC payload A == GspRmBoot monitorCode
FMC payload B == GspRmBoot monitorData
FMC manifest  == GspRmBoot manifest
```

Thus the FMC layer has already been unpacked; the remaining ciphertext is the
RISC-V monitor image itself.  This also explains the apparently random FMC
body: it is not an outer encryption layer with a new header, it is the
monitor data/code and their manifest reordered behind an FMC wrapper.

The 595.71.05 and 610.43.02 driver sources have different debug and production
FMC/monitor ciphertexts.  At 615.71.09, however, the debug-signed and
production FMC assets become byte-identical; only the detached signature and
public key change.  A 615 "debug" extraction therefore cannot reveal a
separately debug-encrypted RISC-V monitor.  Moving to an older debug asset
confirms the layout and manifest marker (`0x42` plus `0x55` production or
`0xAA` debug), but still does not supply the monitor-image content key.

The same check was run specifically on 595.71.05.  Its `GspRmBoot_GB202`
descriptor is identical to 615's v6 descriptor, and its FMC payload A/B and
manifest equal the 595 debug `monitorCode`, `monitorData` and `manifest`
byte-for-byte.  The 595 debug manifest has its first `0x180` bytes zeroed and
the `42 ... AA` marker at `0x300`; monitor data and code remain 7.997 and
7.999 bits/byte respectively.  key37 ECB/CBC/CFB/OFB/CTR and an XTS sanity
sweep did not expose code, and no common compressed-stream signature appeared.
The 580.173.02 and 590.48.01 debug images were also checked for a possible
older plaintext/debug-key variant; all retain opaque monitor sections.

These are not the right inputs:

- `gsp_ga10x.bin` is the generic GSP-RISCV/RM image, not the SEC2 FMC.
- `ucodes_ga10x.bin` is the broader NVUCODES container for GR and other
  engines, not this SEC2 boot stage.
- the 503,808-byte `ConcatenatedFMC_GB202` image is the CC/SPDM profile.

## GB202 BAR0 confirmation

A one-shot read-only module built from
[`gb202_reg_peek.c`](../../../launchprobe/tools/gb202_reg_peek/gb202_reg_peek.c)
checked exactly five known Ada offsets after validating PCI ID `10de:2b85` and
BAR0.  It performed no scan, write, reset, firmware load, or PCI-config
change, and was unloaded immediately.

| BAR0 offset | register | GB202 value |
|---:|---|---:|
| `0x00823804` | `FEAT_OVR_PLM` | `0xfffffb8f` |
| `0x00823814` | `FEAT_READOUT_0` | `0x00000233` |
| `0x00823818` | `FEAT_READOUT_1` | `0x00c36180` |
| `0x0082381c` | `FEAT_OVR_SM_SPEED_SELECT` (`SS0`) | `0x73766047` |
| `0x00823820` | `FEAT_OVR_SM_SPEED_SELECT_1` (`SS1`) | `0x00077005` |

The readout low 27 bits decode as

```text
FEAT_READOUT_1 = 0x00c36180
low 27 bits    = 0x00c36180
nine 3-bit fields = 0 0 6 0 6 6 0 6 0
```

The four nonzero fields align exactly with the four nonzero RM results:

| readout field | RM class | RM code | readout code |
|---:|---|---:|---:|
| 2 | FMLA32 | 3 | 6 |
| 4 | IMLA1 | 3 | 6 |
| 5 | IMLA2 | 3 | 6 |
| 7 | IMLA4 | 3 | 6 |

Ada supplies the cross-check for the encoding: its stock nonzero fields
`2, 5, 7` contain `2`, while the Ada RM getter reports `FMLA32/IMLA2/IMLA4 =
1`.  For these fields the effective readout is therefore `2 * RM selector`.
This proves that GB202's `FMLA32=3` reaches the hardware as field value `6`.

Every `SS0` nibble-enable bit and `SS1[3]` are clear (`SS0` nibbles
`7 4 0 6 6 7 3 7`; `SS1` low nibble `5`).  The 5090 is therefore using its
fused/default selectors, not an active software override.  The
`FEAT_OVR_PLM` low byte remains `0x8f`, preserving the same highest-level-only
write permission seen on Ada.

## Actual RTX 5090 values

`gr_rate_preload.c` below queries both the legacy command (`0x20801230`) and V2.
The legacy response confirms that the numeric values use the documented
speed-select scale.

| V2 index | class | data | decoded speed |
|---:|---|---:|---|
| `0x00` | FMLA16 | 0 | full |
| `0x02` | FMLA32 | 3 | 1/8 |
| `0x03` | FFMA | 0 | full |
| `0x04` | IMLA0 | 0 | full |
| `0x05` | IMLA1 | 3 | 1/8 |
| `0x06` | IMLA2 | 3 | 1/8 |
| `0x07` | IMLA3 | 0 | full |
| `0x08` | IMLA4 | 3 | 1/8 |

The legacy response is exactly
`imla0=0, fmla16=0, dp=0, fmla32=3, ffma=0, imla1=3, imla2=3, imla3=0,
imla4=3`.

Every V2 index is also queried individually.  `DP` (`0x01`), `FP16` (`0x09`),
`FP32` (`0x0a`), `DFMA` (`0x0b`), `DMLA` (`0x0c`), `CTRL0` (`0x0d`), and
`CTRL1` (`0x0e`) return `NV_ERR_INVALID_ARGUMENT` (`0x1f`) on this SKU.  The
throttle table contains one entry: `MASK=0`; no `CREDIT` entry is returned.

`FMLA32=3` is the active candidate control for the RTX 5090's 2x
FP32-accumulating HMMA/QMMA interval.  `QMMA.SF` bypasses it, which is
consistent with an opcode-class issuance override rather than a disabled
tensor backend.

## Reproduction

The preload probe watches a normal CUDA process create its
`NV20_SUBDEVICE_0`, then issues the read-only RM controls on that live object:

```sh
cd launchprobe
make gr_rate_preload.so
LD_PRELOAD=./gr_rate_preload.so CUDA_VISIBLE_DEVICES=0 ./target/ctxprobe
```

It is read-only with respect to GPU configuration and does not require root
when run this way.  Sample output on the local 5090:

```text
SM issue-rate modifiers: 8 entries
  [00] index=0x00 FMLA16  data=0x0 full
  [01] index=0x02 FMLA32  data=0x3 1/8
  [02] index=0x03 FFMA    data=0x0 full
  [03] index=0x04 IMLA0   data=0x0 full
  [04] index=0x05 IMLA1   data=0x3 1/8
  [05] index=0x06 IMLA2   data=0x3 1/8
  [06] index=0x07 IMLA3   data=0x0 full
  [07] index=0x08 IMLA4   data=0x3 1/8
  index=0x0c DMLA unsupported status=0x1f
```

The BAR0 probe is deliberately fixed to the five offsets above:

```sh
cd launchprobe/tools/gb202_reg_peek
make
sudo insmod ./gb202_reg_peek.ko target=0000:01:00.0
sudo dmesg | tail
sudo rmmod gb202_reg_peek
```

Do not extend this into an address scan.  The successful run was performed
with the NVIDIA driver bound and an active CUDA workload; telemetry and the
workload were unchanged afterward.  One successful power-on does not make
arbitrary BAR0 ranges safe to probe.

## External reference

The Ada implementation is
[JustAResearcher/gpu-unlock-ada](https://github.com/JustAResearcher/gpu-unlock-ada),
reviewed at commit `4e7fefcc4923f9e083d5324dc75a7d2f906af77f`.  Relevant files:

- `docs/How Ampere was unlocked.md`: selector and PLM encoding;
- `kernel/gpu_unlock/unlock_610.c`: `SS0/SS1` application and readback;
- `rtx4090-register-report.md`: signed-firmware transaction and register map;
- `tools/read_sm_rates.py`: read-only RM getter cross-check.

The public debug-key provenance and FMC/RISC-V layout cross-checks are also
recorded in the [CMP 170HX firmware notes](https://github.com/Consensus-Protocol/cmp170hx/blob/main/docs/unlock/falcon-and-booter.md),
the [nvlight firmware gist](https://gist.github.com/nvlight/fc7479629b0ace094873e58ba7d75eb2),
and the GB202 inventory discussion in
[phiraml/gpu-unlock-blackwell#1](https://github.com/phiraml/gpu-unlock-blackwell/issues/1).

## Remaining route

The Ada payload is tied to AD102-family booters and production images.  The
GB202 feature-cluster offsets are confirmed, but its signed booter geometry
and payload chain are not established by the Ada work and must not be assumed
portable.  The useful next steps are:

1. identify the encryption/key derivation for the encrypted `GspRmBoot`
   monitor image, or obtain a runtime plaintext dump; the outer FMC geometry
   no longer needs investigation;
2. determine whether that monitor exposes a permission-opening path analogous
   to the SEC2 Falcon booter; do not apply the Ada V67 payload to GB202;
3. once that is proven, change the `FMLA32` nibble from selector 3 to selector
   0 and re-run the existing HMMA/QMMA/QMMA.SF issue-rate controls;
4. compare a same-driver RTX PRO 6000 register/RM readback to separate the
   selector value from any additional GB202 generation mapping.
