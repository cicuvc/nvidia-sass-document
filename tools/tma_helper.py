"""Bit-accurate forward construction of CUtensorMap descriptors.

The CUtensorMap is an opaque 128-byte object; its bit layout is not part of
the CUDA driver API.  This module reconstructs the layout empirically by
differentially probing ``cuTensorMapEncodeTiled`` / ``cuTensorMapEncodeIm2col``
on a real GPU (Hopper/Blackwell, CUDA 13) and verifying every field against
the driver output.  See ``notes/sm90/arch/cutensormap.md`` for the field
table and the probe evidence.

Reference (API semantics only, no bit layout):
https://docs.nvidia.com/cuda/cuda-driver-api/group__CUDA__TENSOR__MEMORY.html

The layout (all little-endian, 32-bit words w0..w31):

  tiled mode
  w0..w1    global address (64-bit)
  w2        flags (see below)
  w3..w7    globalStrides[i] / 16          (i = 0..rank-2, 32-bit each)
  w8..w12   globalDim[i] - 1               (32-bit each; w12 used by rank 5)
  w13       bits[15:0]  elementStrides[i]-1 packed 3 bits each, i = 0..4
            bits[23:16] reserved (0)
            bits[31:24] boxDim[0] - 1
  w14       bits[7:0]   boxDim[1] - 1
            bits[15:8]  boxDim[2] - 1
            bits[23:16] boxDim[3] - 1
            bits[31:24] boxDim[4] - 1
  w15       reserved (0)
  w16       tile size in bytes (see _transfer_size)
  w18       swizzle info: base 0x10; swizzle 1/2/3 -> +0x100/0x200/0x400;
            swizzle 4/5/6 -> +0x400
  all else  reserved (0)

  flags (w2):
  bits[3:0]   reserved (0)              (bit0 = 1 in im2col mode)
  bits[6:4]   tensorRank - 1
  bits[10:7]  element-type code (NOT the API enum; see DTYPE_CODE)
  bits[12:11] interleave (0/1/2)
  bits[14:13] min(swizzle, 3)
  bit  15     float-OOB-fill flag
  bit  16     TFLOAT32 flag (set together with type code 7 or 8)
  bits[18:17] L2 promotion (1..3)
  bits[20:19] max(swizzle - 3, 0)
  bit  21     "wide" flag: total elements >= 2^16 (non-interleaved), or
              interleaved tile bytes >= 2^16

  im2col mode (rank 3..5):
  w13 bits[31:24]  channelsPerPixel - 1
  w14              pixelBox corners, rank-dependent precision:
                     r3: lo[15:0], hi[31:16] (16-bit signed each)
                     r4: lo0[7:0] lo1[15:8] hi0[23:16] hi1[31:24] (8-bit signed)
                     r5: lo0[4:0] lo1[9:5] lo2[14:10]
                         hi0[20:16] hi1[25:21] hi2[30:26] (5-bit signed)
  w15              pixelsPerColumn - 1
  w16              channelsPerPixel * pixelsPerColumn * elementSize
"""

import ctypes
from ctypes import (
    Structure, POINTER, c_int, c_uint8, c_uint16, c_uint32, c_uint64,
    c_void_p, cast, sizeof, addressof, memmove,
)

# ---------------------------------------------------------------------------
# element-type code table (API enum -> hardware code)
#
# The 4-bit field at w2 bits[10:7] is NOT the CUtensorMapDataType enum value.
# Empirically (probed on CUDA 13 / sm_120 driver):
#   UINT8..FLOAT32 map 1:1 (codes 0..7), then the order changes:
#   FLOAT32_FTZ=8, FLOAT64=9, BFLOAT16=10, 16U4_ALIGN8B=11,
#   16U4_ALIGN16B=12, 16U6_ALIGN16B=13.
# TFLOAT32 / TFLOAT32_FTZ reuse codes 7 / 8 and additionally set w2 bit 16.
# ---------------------------------------------------------------------------
DTYPE_CODE = {
    0: (0, False),    # UINT8
    1: (1, False),    # UINT16
    2: (2, False),    # UINT32
    3: (3, False),    # INT32
    4: (4, False),    # UINT64
    5: (5, False),    # INT64
    6: (6, False),    # FLOAT16
    7: (7, False),    # FLOAT32
    8: (9, False),    # FLOAT64      (hardware code 9!)
    9: (10, False),   # BFLOAT16     (hardware code 10!)
    10: (8, False),   # FLOAT32_FTZ  (hardware code 8!)
    11: (7, True),    # TFLOAT32     (code 7 + bit16)
    12: (8, True),    # TFLOAT32_FTZ (code 8 + bit16)
    13: (11, False),  # 16U4_ALIGN8B
    14: (12, False),  # 16U4_ALIGN16B
    15: (13, False),  # 16U6_ALIGN16B
}

ELEM_BYTES = {
    0: 1, 1: 2, 2: 4, 3: 4, 4: 8, 5: 8, 6: 2, 7: 4, 8: 8, 9: 2,
    10: 4, 11: 4, 12: 4,
    13: 0.5, 14: 0.5, 15: 0.75,   # packed U4/U6 (w16 not stored, see below)
}


class Flags(Structure):
    _fields_ = [
        ("mode", c_uint32, 4),        # 0 = tiled, 1 = im2col
        ("dim", c_uint32, 3),         # tensorRank - 1
        ("type", c_uint32, 4),        # hardware code (DTYPE_CODE)
        ("interleave", c_uint32, 2),
        ("swizzle", c_uint32, 2),     # min(swizzle, 3)
        ("oob", c_uint32, 1),
        ("tf32", c_uint32, 1),        # TFLOAT32 flag
        ("l2c", c_uint32, 2),
        ("swizzle_hi", c_uint32, 2),  # max(swizzle - 3, 0)
        ("wide", c_uint32, 1),        # total elements / tile >= 2^16
        ("pad2", c_uint32, 10),
    ]


# The tiled and im2col descriptors share the same 128-byte envelope; only the
# meaning of w13/w14/w15/w16 differs between the two modes.
class TiledDesc(Structure):
    _fields_ = [
        ("memoryPtr", c_uint64),
        ("flags", Flags),
        ("gstride_div_16", c_uint32 * 5),
        ("gshape_sub_1", c_uint32 * 5),
        ("sstride_3bits", c_uint16),      # w13 bits[15:0]
        ("pad", c_uint8),                 # w13 bits[23:16]
        ("sshape_sub_1", c_uint8 * 5),    # w13 byte3 + w14 bytes 0..3
        ("pad1", c_uint32),               # w15 (im2col: pixelsPerColumn - 1)
        ("transferSize", c_uint32),       # w16
        ("pad2", c_uint32),               # w17 (reserved)
        ("swizzleInfo", c_uint32),        # w18 (0x10; sw 1/2/3 -> 0x100/0x200/0x400)
        ("zeros", c_uint8 * 52),          # w19..w31
    ]


def _read_array_as_list(ptr_or_seq, length, ctype):
    if hasattr(ptr_or_seq, "__getitem__") and not isinstance(
            ptr_or_seq, (int, c_void_p)):
        out = []
        for i in range(length):
            try:
                val = ptr_or_seq[i]
            except Exception:
                break
            if hasattr(val, "value"):
                val = val.value
            out.append(int(val))
        if len(out) == length:
            return out

    if isinstance(ptr_or_seq, (c_void_p, ctypes._SimpleCData)) or \
            hasattr(ptr_or_seq, "contents") or isinstance(ptr_or_seq, int):
        addr = None
        if isinstance(ptr_or_seq, int):
            addr = ptr_or_seq
        elif isinstance(ptr_or_seq, c_void_p):
            addr = int(ptr_or_seq.value) if ptr_or_seq.value is not None else 0
        elif hasattr(ptr_or_seq, "value") and isinstance(ptr_or_seq.value, int):
            addr = int(ptr_or_seq.value)
        else:
            try:
                addr = addressof(ptr_or_seq.contents)
            except Exception:
                addr = None
        if addr:
            arr_type = ctype * length
            try:
                arr = cast(c_void_p(addr), POINTER(arr_type)).contents
                return [int(arr[i]) for i in range(length)]
            except Exception:
                pass

    try:
        it = iter(ptr_or_seq)
        return [int(next(it)) for _ in range(length)]
    except Exception:
        raise TypeError("Unsupported array/pointer type for reading")


def _to_int_ptr_like(x):
    if x is None:
        return 0
    if isinstance(x, int):
        return x
    if isinstance(x, c_void_p):
        return int(x.value or 0)
    if hasattr(x, "value") and isinstance(x.value, int):
        return int(x.value)
    try:
        return addressof(x.contents)
    except Exception:
        raise TypeError("Unsupported pointer-like type for address conversion")


def _as_desc(tmaDesc):
    if isinstance(tmaDesc, int):
        return cast(c_void_p(tmaDesc), POINTER(TiledDesc))
    try:
        return cast(tmaDesc, POINTER(TiledDesc))
    except Exception:
        try:
            return cast(c_void_p(_to_int_ptr_like(tmaDesc)),
                        POINTER(TiledDesc))
        except Exception:
            return None


def _build_flags(dtype, rank, interleave, swizzle, l2c, oob, im2col=False):
    if dtype not in DTYPE_CODE:
        raise ValueError(f"unknown CUtensorMapDataType {dtype}")
    code, tf32 = DTYPE_CODE[dtype]
    if rank < 1 or rank > 5:
        raise ValueError("rank must be 1..5")
    f = Flags()
    f.mode = 1 if im2col else 0
    f.dim = rank - 1
    f.type = code
    f.interleave = int(interleave) & 0x3
    f.swizzle = min(int(swizzle), 3)
    f.oob = int(oob) & 0x1
    f.tf32 = 1 if tf32 else 0
    f.l2c = int(l2c) & 0x3
    f.swizzle_hi = max(int(swizzle) - 3, 0)
    return f


def _transfer_size_tiled(dtype, box, elem, interleave):
    """Tile byte count stored at w16 (empirical).

    Non-interleaved: elementSize * prod(floor(box[i] / elemStride[i])).
    Interleaved 16B/32B: prod(box[i]) * (16 or 32).
    Packed U4/U6 dtypes (13..15): the driver stores 0.
    """
    if dtype in (13, 14, 15):
        return 0
    if interleave == 0:
        n = 1
        for b, e in zip(box, elem):
            n *= b // e
        return int(ELEM_BYTES[dtype] * n)
    ilb = 16 if interleave == 1 else 32
    n = 1
    for b in box:
        n *= b
    return int(n * ilb)


def _wide_tiled(dtype, dims, box, elem, interleave):
    if interleave == 0:
        tot = 1
        for d in dims:
            tot *= d
        return 1 if tot >= 65536 else 0
    return 1 if _transfer_size_tiled(dtype, box, elem, interleave) >= 65536 \
        else 0


def cuTensorMapEncodeTiled(tmaDesc, dtype, rank, gaddr, gshape, gstride,
                           sshape, sstride, interleave=0, swizzle=0,
                           l2c=0, oob=0):
    """Fill a 128-byte CUtensorMap (tiled mode) in-place.

    sshape  = boxDim (u32 array, rank entries)
    sstride = elementStrides (u32 array, rank entries)
    Returns 0 on success, -1 on error.  Mirrors cuTensorMapEncodeTiled.
    """
    try:
        desc_ptr = _as_desc(tmaDesc)
        if desc_ptr is None:
            return -1
        desc = desc_ptr.contents
        ctypes.memset(addressof(desc), 0, sizeof(TiledDesc))

        dims = _read_array_as_list(gshape, rank, c_uint64)
        strides = _read_array_as_list(gstride, max(0, rank - 1), c_uint64)
        box = _read_array_as_list(sshape, rank, c_uint32)
        elem = _read_array_as_list(sstride, rank, c_uint32)
        if len(dims) != rank or len(box) != rank or len(elem) != rank:
            return -1
        if len(strides) != max(0, rank - 1):
            return -1
        for v in box + elem:
            if int(v) <= 0:
                return -1
        for s in strides:
            if int(s) & 0xF:
                return -1

        desc.memoryPtr = _to_int_ptr_like(gaddr)
        desc.flags = _build_flags(dtype, rank, interleave, swizzle, l2c, oob)

        for i in range(rank):
            desc.gshape_sub_1[i] = c_uint32(int(dims[i]) - 1)
            desc.sshape_sub_1[i] = c_uint8(int(box[i]) - 1)
        for i in range(max(0, rank - 1)):
            desc.gstride_div_16[i] = c_uint32(int(strides[i]) >> 4)

        packed = 0
        for i in range(rank):
            packed |= ((int(elem[i]) - 1) & 0x7) << (3 * i)
        desc.sstride_3bits = c_uint16(packed & 0xFFFF)

        desc.flags.wide = _wide_tiled(
            dtype, dims, box, elem, int(interleave))
        desc.transferSize = c_uint32(_transfer_size_tiled(
            dtype, box, elem, int(interleave)))
        sw = int(swizzle)
        desc.swizzleInfo = c_uint32(
            0x10 if sw == 0 else (1 << (7 + min(sw, 3))))

        memmove(addressof(desc_ptr.contents), addressof(desc),
                sizeof(TiledDesc))
        return 0
    except Exception:
        return -1


def cuTensorMapEncodeIm2col(tmaDesc, dtype, rank, gaddr, gshape, gstride,
                            pixelLo, pixelHi, cpp, ppc, sstride,
                            interleave=0, swizzle=0, l2c=0, oob=0):
    """Fill a 128-byte CUtensorMap (im2col mode) in-place.

    pixelLo / pixelHi = pixelBox lower/upper corners, rank-2 signed ints each
    ({W} for r3, {H,W} for r4, {D,H,W} for r5).  cpp = channelsPerPixel,
    ppc = pixelsPerColumn, sstride = elementStrides (rank entries).
    """
    try:
        desc_ptr = _as_desc(tmaDesc)
        if desc_ptr is None:
            return -1
        desc = desc_ptr.contents
        ctypes.memset(addressof(desc), 0, sizeof(TiledDesc))
        if rank < 3 or rank > 5:
            return -1

        dims = _read_array_as_list(gshape, rank, c_uint64)
        strides = _read_array_as_list(gstride, rank - 1, c_uint64)
        lo = _read_array_as_list(pixelLo, rank - 2, c_int)
        hi = _read_array_as_list(pixelHi, rank - 2, c_int)
        elem = _read_array_as_list(sstride, rank, c_uint32)
        if len(dims) != rank or len(strides) != rank - 1 or \
                len(lo) != rank - 2 or len(hi) != rank - 2 or \
                len(elem) != rank:
            return -1
        for s in strides:
            if int(s) & 0xF:
                return -1
        if not (1 <= int(cpp) <= 256) or not (1 <= int(ppc) <= 1024):
            return -1

        desc.memoryPtr = _to_int_ptr_like(gaddr)
        desc.flags = _build_flags(dtype, rank, interleave, swizzle, l2c, oob,
                                  im2col=True)

        for i in range(rank):
            desc.gshape_sub_1[i] = c_uint32(int(dims[i]) - 1)
        for i in range(rank - 1):
            desc.gstride_div_16[i] = c_uint32(int(strides[i]) >> 4)

        packed = 0
        for i in range(rank):
            packed |= ((int(elem[i]) - 1) & 0x7) << (3 * i)
        desc.sstride_3bits = c_uint16(packed & 0xFFFF)
        desc.sshape_sub_1[0] = c_uint8(int(cpp) - 1)   # w13 byte3

        # pixelBox corners in w14, rank-dependent signed precision
        corner = 0
        n = rank - 2
        if rank == 3:
            corner = (int(lo[0]) & 0xFFFF) | ((int(hi[0]) & 0xFFFF) << 16)
        elif rank == 4:
            for i in range(2):
                corner |= (int(lo[i]) & 0xFF) << (8 * i)
                corner |= (int(hi[i]) & 0xFF) << (16 + 8 * i)
        else:  # rank 5, 5-bit signed fields
            for i in range(3):
                corner |= (int(lo[i]) & 0x1F) << (5 * i)
                corner |= (int(hi[i]) & 0x1F) << (16 + 5 * i)
        desc.sshape_sub_1[1] = c_uint8(corner & 0xFF)
        desc.sshape_sub_1[2] = c_uint8((corner >> 8) & 0xFF)
        desc.sshape_sub_1[3] = c_uint8((corner >> 16) & 0xFF)
        desc.sshape_sub_1[4] = c_uint8((corner >> 24) & 0xFF)

        tot = 1
        for d in dims:
            tot *= int(d)
        desc.flags.wide = 1 if tot >= 65536 else 0
        desc.transferSize = c_uint32(int(cpp) * int(ppc) *
                                     ELEM_BYTES[dtype])
        desc.pad1 = c_uint32(int(ppc) - 1)
        sw = int(swizzle)
        desc.swizzleInfo = c_uint32(
            0x10 if sw == 0 else (1 << (7 + min(sw, 3))))

        memmove(addressof(desc_ptr.contents), addressof(desc),
                sizeof(TiledDesc))
        return 0
    except Exception:
        return -1
