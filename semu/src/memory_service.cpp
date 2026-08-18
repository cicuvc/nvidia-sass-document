// MemoryService — Phase 6 memory model (functional step 1).
//
// Functional semantics only: loads/stores/atomics resolve addresses, enforce
// width/alignment/bounds/space via the allocator, and convert errors into
// structured Faults.  Address arithmetic is CHECKED (a signed displacement or
// base+addr+offset never wraps silently), per-width natural alignment is
// enforced, and every access is bounds-validated with `off <= size &&
// len <= size - off`.  Memory is synchronous (op completes on issue), so a
// correct program's wait/DEPBAR observes all data; control-word dependencies
// are recorded for diagnostics but stale values from missing waits are not
// reproduced (per SIM_PLAN).

#include <semu/memory_service.hpp>

#include <algorithm>
#include <cstring>
#include <mutex>

namespace semu {

namespace {

// Checked `base + signed offset` (High-1): never wraps.  Returns false on
// overflow/underflow.
bool checked_add(std::uint64_t base, std::int64_t offset,
                 std::uint64_t* out) {
    if (offset >= 0) {
        const std::uint64_t d = static_cast<std::uint64_t>(offset);
        if (base > UINT64_MAX - d) return false;
        *out = base + d;
    } else {
        const std::uint64_t mag =
            static_cast<std::uint64_t>(-(offset + 1)) + 1;
        if (base < mag) return false;
        *out = base - mag;
    }
    return true;
}

// Natural alignment for a byte width (1/2/4/8/16).
std::uint64_t natural_alignment(std::uint64_t bytes) {
    if (bytes >= 16) return 16;
    if (bytes >= 8) return 8;
    if (bytes >= 4) return 4;
    if (bytes >= 2) return 2;
    return 1;
}

// True when `addr` is aligned to the width's natural alignment.
bool width_aligned(std::uint64_t addr, std::uint64_t bytes) {
    return (addr % natural_alignment(bytes)) == 0;
}

// Validate an atomic width: {1,2,4,8} supported; 16 (128-bit) is a
// structured error, never a truncated 64-bit RMW.
Status check_atomic_width(std::uint64_t width) {
    if (width != 1 && width != 2 && width != 4 && width != 8) {
        return Status::failure(
            Error(ErrorCode::kNotSupported,
                  "128-bit (width 16) atomic RMW is not supported"));
    }
    return Status::success();
}

// Decode `bytes` host bytes from a little-endian MemValue into a buffer.
void mem_value_to_bytes(const MemValue& v, std::uint64_t len,
                        std::uint8_t* dst) {
    std::uint64_t n = std::min<std::uint64_t>(len, 16);
    for (std::uint64_t i = 0; i < n; ++i) {
        dst[i] = static_cast<std::uint8_t>((v[i / 4] >> (8 * (i % 4))) & 0xff);
    }
}

// Atomic-operand variant: atomic widths are {1,2,4,8} (check_atomic_width),
// so clamp to 8 bytes — a 128-bit value can NEVER be written into an 8-byte
// operand buffer, and the explicit clamp lets -O3 prove the write stays in
// bounds (stringop-overflow).
void mem_value_to_bytes_atomic(const MemValue& v, std::uint64_t len,
                               std::uint8_t* dst) {
    std::uint64_t n = std::min<std::uint64_t>(len, 8);
    for (std::uint64_t i = 0; i < n; ++i) {
        dst[i] = static_cast<std::uint8_t>((v[i / 4] >> (8 * (i % 4))) & 0xff);
    }
}

// Load `len` little-endian bytes (1/2/4/8) from `src` into a uint64.
std::uint64_t load_le(const std::uint8_t* src, std::uint64_t len) {
    std::uint64_t v = 0;
    const std::uint64_t n = std::min<std::uint64_t>(len, 8);
    for (std::uint64_t i = 0; i < n; ++i) {
        v |= static_cast<std::uint64_t>(src[i]) << (8 * i);
    }
    return v;
}

// Store the low `len` little-endian bytes (1/2/4/8) of `v` into `dst`.
void store_le(std::uint8_t* dst, std::uint64_t v, std::uint64_t len) {
    const std::uint64_t n = std::min<std::uint64_t>(len, 8);
    for (std::uint64_t i = 0; i < n; ++i) {
        dst[i] = static_cast<std::uint8_t>((v >> (8 * i)) & 0xff);
    }
}

// Reinterpret a width-limited value as a SIGNED integer (S32/S64 atomics).
std::int64_t signed_le(std::uint64_t v, std::uint64_t len) {
    switch (len) {
        case 1: return static_cast<std::int8_t>(static_cast<std::uint8_t>(v));
        case 2: return static_cast<std::int16_t>(static_cast<std::uint16_t>(v));
        case 4: return static_cast<std::int32_t>(static_cast<std::uint32_t>(v));
        default: return static_cast<std::int64_t>(v);
    }
}

// Apply one atomic RMW (Blocker-4).  `a` = current memory value, `b` = the
// operand, `c` = the kCas compare operand.  Returns false when the (op,
// width) combination is not implemented — the caller must surface that as a
// structured error and MUST NOT downgrade to ADD (INC/DEC are U32-only,
// CAS requires the compare, unknown ops are rejected).
bool apply_atomic(AtomicOp op, std::uint64_t width, std::uint64_t a,
                  std::uint64_t b, std::uint64_t c, std::uint64_t* r) {
    switch (op) {
        case AtomicOp::kAdd: *r = a + b; return true;
        case AtomicOp::kMin: *r = std::min(a, b); return true;
        case AtomicOp::kMax: *r = std::max(a, b); return true;
        case AtomicOp::kAnd: *r = a & b; return true;
        case AtomicOp::kOr: *r = a | b; return true;
        case AtomicOp::kXor: *r = a ^ b; return true;
        case AtomicOp::kExch: *r = b; return true;
        case AtomicOp::kInc:
            // atom.inc.u32: (old >= bound) ? 0 : old + 1 (wraps to 0).
            if (width != 4) return false;
            *r = (a >= b) ? 0 : a + 1;
            return true;
        case AtomicOp::kDec:
            // atom.dec.u32: (old == 0 || old > bound) ? bound : old - 1.
            if (width != 4) return false;
            *r = (a == 0 || a > b) ? b : a - 1;
            return true;
        case AtomicOp::kCas:
            *r = (a == c) ? b : a;
            return true;
        case AtomicOp::kMinSigned:
        case AtomicOp::kMaxSigned: {
            const std::int64_t sa = signed_le(a, width);
            const std::int64_t sb = signed_le(b, width);
            const std::int64_t sr =
                op == AtomicOp::kMinSigned ? std::min(sa, sb)
                                           : std::max(sa, sb);
            *r = static_cast<std::uint64_t>(sr);
            return true;
        }
        default:
            return false;  // unknown / not implemented: never downgrade
    }
}

}  // namespace

MemWidthInfo mem_width_info(std::uint64_t sz_slot) {
    // SZ_U8_S8_U16_S16_32_64_128: 0..6 as in sm120.json.  Values >= 7 are
    // reserved/invalid and are rejected (Medium fix) rather than silently
    // decoded as 4 bytes.
    switch (sz_slot) {
        case 0: return {1, false, true};
        case 1: return {1, true, true};
        case 2: return {2, false, true};
        case 3: return {2, true, true};
        case 5: return {8, false, true};
        case 6: return {16, false, true};
        case 4: return {4, false, true};
        default: return {0, false, false};
    }
}

std::uint64_t ResolvedAddress::final_address() const {
    // Checked: base + signed offset (never wraps).
    std::uint64_t out = 0;
    if (!checked_add(base, offset, &out)) return 0;
    return out;
}

MemoryService::MemoryService(const std::vector<std::uint8_t>& params,
                             std::uint64_t /*global_size*/,
                             std::uint64_t /*shared_size*/)
    : params_(params) {
    // Constant bank: kernel params live at c[0x0][0x380..]; size the full
    // window so the param area + preset slots fit without overflow.
    constant_.resize(0x10000, 0);
    const std::uint64_t n =
        std::min<std::uint64_t>(params_.size(), constant_.size() - 0x380);
    if (n > 0) {
        std::memcpy(constant_.data() + 0x380, params_.data(), n);
    }
}

StatusOr<DevicePtr> MemoryService::setup_global(
    std::uint64_t size, const std::string& label) {
    std::lock_guard<std::mutex> lk(setup_mutex_);
    auto r = alloc_.allocate(AddressSpace::kGlobal, size, 16, label);
    if (r.failed()) return r;
    global_base_ = r.value();
    global_size_ = size;
    return r;
}

StatusOr<DevicePtr> MemoryService::register_cta_shared(std::uint64_t size,
                                                       std::uint64_t cta_id) {
    std::lock_guard<std::mutex> lk(setup_mutex_);
    auto r = alloc_.allocate(AddressSpace::kShared, size, 16,
                             "cta:" + std::to_string(cta_id));
    if (r.failed()) return r;
    SharedWindow w;
    auto alloc = alloc_.allocation_by_base(r.value());
    if (alloc.failed()) return r;
    w.id = alloc.value().id;
    w.base = r.value();
    w.size = size;
    while (shared_.size() <= cta_id) shared_.push_back({});
    shared_[cta_id] = w;
    return r;
}

StatusOr<DevicePtr> MemoryService::register_warp_local(
    std::uint64_t size, std::uint64_t cta_id, std::uint64_t warp_id) {
    // Local space is per-warp; owner domain is "warp:<cta>:<warp>".
    std::lock_guard<std::mutex> lk(setup_mutex_);
    return alloc_.allocate(
        AddressSpace::kLocal, size, 16,
        "warp:" + std::to_string(cta_id) + ":" + std::to_string(warp_id));
}

void MemoryService::set_global_backing(std::vector<std::uint8_t>* backing) {
    global_ = backing;
}

DevicePtr MemoryService::global_base() const { return global_base_; }

std::uint64_t MemoryService::global_size() const {
    // The host-visible backing (set via set_global_backing) is the buffer the
    // debugger/launcher reads; its size is the global window size.
    return global_ ? global_->size() : 0;
}

std::uint64_t MemoryService::constant_size() const {
    return constant_.size();
}

AllocationId MemoryService::global_allocation_id() const {
    if (global_base_.is_null()) return AllocationId{0};
    std::lock_guard<std::mutex> lk(setup_mutex_);
    auto a = alloc_.allocation_by_base(global_base_);
    return a.ok() ? a.value().id : AllocationId{0};
}

Status MemoryService::write_host(std::uint64_t off, const void* src,
                                 std::uint64_t len) {
    std::lock_guard<std::mutex> lk(global_mutex_);
    if (!global_ || off > global_->size() || len > global_->size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global buffer write out of bounds"));
    }
    std::memcpy(global_->data() + off, src, len);
    return Status::success();
}

Status MemoryService::read_host(std::uint64_t off, void* dst,
                                std::uint64_t len) {
    std::lock_guard<std::mutex> lk(global_mutex_);
    if (!global_ || off > global_->size() || len > global_->size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global buffer read out of bounds"));
    }
    std::memcpy(dst, global_->data() + off, len);
    return Status::success();
}

Status MemoryService::read_constant(std::uint64_t off, void* dst,
                                    std::uint64_t len) const {
    if (off > constant_.size() || len > constant_.size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "constant window read out of bounds"));
    }
    std::memcpy(dst, constant_.data() + off, len);
    return Status::success();
}

Status MemoryService::write_constant(std::uint64_t off, const void* src,
                                     std::uint64_t len) {
    if (off > constant_.size() || len > constant_.size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "constant window write out of bounds"));
    }
    std::memcpy(constant_.data() + off, src, len);
    return Status::success();
}

DevicePtr MemoryService::cta_shared_base(std::uint64_t cta_id) const {
    if (cta_id < shared_.size()) return shared_[cta_id].base;
    return DevicePtr{0};
}

Status MemoryService::ldg(DevicePtr /*desc*/, std::uint64_t addr,
                          std::int64_t offset, MemWidthInfo w,
                          MemValue& out) {
    if (!w.valid) {
        return Status::failure(Error(ErrorCode::kInvalidArgument,
                                     "invalid load size slot"));
    }
    if (global_base_.is_null()) {
        // No global buffer (pure compute context): return zeros (matches the
        // pre-Phase-6 behavior where LDG was not executed).
        out = {};
        return Status::success();
    }
    // Checked base + addr + signed offset (never wraps).
    std::uint64_t base_addr = 0;
    if (!checked_add(global_base_.va, static_cast<std::int64_t>(addr),
                     &base_addr) ||
        !checked_add(base_addr, offset, &base_addr)) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global load address overflow"));
    }
    const std::uint64_t off = base_addr - global_base_.va;
    if (!width_aligned(off, w.bytes)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "global load misaligned for width"));
    }
    return read_global(base_addr, w, out);
}

Status MemoryService::read_global(std::uint64_t va, MemWidthInfo w,
                                  MemValue& out) {
    std::lock_guard<std::mutex> lk(global_mutex_);
    if (global_base_.is_null()) {
        out = {};
        return Status::success();
    }
    if (va < global_base_.va) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global load below buffer"));
    }
    const std::uint64_t off = va - global_base_.va;
    const std::uint64_t len = std::min<std::uint64_t>(w.bytes, 16);
    if (off > global_->size() || len > global_->size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global load out of bounds"));
    }
    std::uint8_t buf[16] = {0};
    std::memcpy(buf, global_->data() + off, len);
    ++reads_;
    out = {};
    if (len <= 4) {
        std::uint32_t raw = 0;
        std::memcpy(&raw, buf, len);
        if (w.sign_extend && len == 1) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int8_t>(raw)));
        } else if (w.sign_extend && len == 2) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int16_t>(raw)));
        } else {
            out[0] = raw;
        }
    } else if (len <= 8) {
        std::uint64_t raw = 0;
        std::memcpy(&raw, buf, len);
        out[0] = static_cast<std::uint32_t>(raw & 0xffffffffu);
        out[1] = static_cast<std::uint32_t>(raw >> 32);
    } else {  // 128-bit: all four words
        for (int i = 0; i < 4; ++i) {
            std::memcpy(&out[static_cast<std::size_t>(i)], buf + 4 * i, 4);
        }
    }
    return Status::success();
}

Status MemoryService::lds(const std::vector<std::uint8_t>& shared,
                          std::uint64_t off, std::int64_t disp, MemWidthInfo w,
                          MemValue& out) {
    if (!w.valid) {
        return Status::failure(Error(ErrorCode::kInvalidArgument,
                                     "invalid shared load size slot"));
    }
    const std::uint64_t len = std::min<std::uint64_t>(w.bytes, 16);
    std::uint64_t abs_off = 0;
    if (!checked_add(off, disp, &abs_off)) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "shared load address underflow"));
    }
    if (abs_off > shared.size() || len > shared.size() - abs_off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "shared load out of bounds"));
    }
    if (!width_aligned(abs_off, w.bytes)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "shared load misaligned for width"));
    }
    std::uint8_t buf[16] = {0};
    std::memcpy(buf, shared.data() + abs_off, len);
    out = {};
    if (len <= 4) {
        std::uint32_t raw = 0;
        std::memcpy(&raw, buf, len);
        if (w.sign_extend && len == 1) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int8_t>(raw)));
        } else if (w.sign_extend && len == 2) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int16_t>(raw)));
        } else {
            out[0] = raw;
        }
    } else if (len <= 8) {
        std::uint64_t raw = 0;
        std::memcpy(&raw, buf, len);
        out[0] = static_cast<std::uint32_t>(raw & 0xffffffffu);
        out[1] = static_cast<std::uint32_t>(raw >> 32);
    } else {
        for (int i = 0; i < 4; ++i) {
            std::memcpy(&out[static_cast<std::size_t>(i)], buf + 4 * i, 4);
        }
    }
    return Status::success();
}

Status MemoryService::ldc(std::uint64_t bank, std::uint64_t off,
                          MemWidthInfo w, MemValue& out) {
    (void)bank;
    if (!w.valid) {
        return Status::failure(Error(ErrorCode::kInvalidArgument,
                                     "invalid constant load size slot"));
    }
    const std::uint64_t len = std::min<std::uint64_t>(w.bytes, 16);
    std::uint8_t buf[16] = {0};
    if (off > constant_.size() || len > constant_.size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "constant read out of bounds"));
    }
    if (!width_aligned(off, w.bytes)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "constant load misaligned for width"));
    }
    std::memcpy(buf, constant_.data() + off, len);
    out = {};
    if (len <= 4) {
        std::uint32_t raw = 0;
        std::memcpy(&raw, buf, len);
        if (w.sign_extend && len == 1) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int8_t>(raw)));
        } else if (w.sign_extend && len == 2) {
            out[0] = static_cast<std::uint32_t>(
                static_cast<std::int32_t>(static_cast<std::int16_t>(raw)));
        } else {
            out[0] = raw;
        }
    } else if (len <= 8) {
        std::uint64_t raw = 0;
        std::memcpy(&raw, buf, len);
        out[0] = static_cast<std::uint32_t>(raw & 0xffffffffu);
        out[1] = static_cast<std::uint32_t>(raw >> 32);
    } else {
        for (int i = 0; i < 4; ++i) {
            std::memcpy(&out[static_cast<std::size_t>(i)], buf + 4 * i, 4);
        }
    }
    return Status::success();
}

Status MemoryService::stg(DevicePtr /*desc*/, std::uint64_t addr,
                          std::int64_t offset, MemWidthInfo w,
                          const MemValue& in) {
    if (!w.valid) {
        return Status::failure(Error(ErrorCode::kInvalidArgument,
                                     "invalid store size slot"));
    }
    std::lock_guard<std::mutex> lk(global_mutex_);
    if (global_base_.is_null()) {
        // No global buffer: store is discarded (matches pre-Phase-6 compute
        // context; results are observed through GPR dumps instead).
        return Status::success();
    }
    std::uint64_t target = 0;
    if (!checked_add(global_base_.va, static_cast<std::int64_t>(addr),
                     &target) ||
        !checked_add(target, offset, &target)) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global store address overflow"));
    }
    const std::uint64_t off = target - global_base_.va;
    const std::uint64_t len = std::min<std::uint64_t>(w.bytes, 16);
    if (off > global_->size() || len > global_->size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global store out of bounds"));
    }
    if (!width_aligned(off, w.bytes)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "global store misaligned for width"));
    }
    std::uint8_t buf[16] = {0};
    mem_value_to_bytes(in, len, buf);
    std::memcpy(global_->data() + off, buf, len);
    ++writes_;
    return Status::success();
}

Status MemoryService::sts(std::vector<std::uint8_t>& shared, std::uint64_t off,
                          std::int64_t disp, MemWidthInfo w,
                          const MemValue& in) {
    if (!w.valid) {
        return Status::failure(Error(ErrorCode::kInvalidArgument,
                                     "invalid shared store size slot"));
    }
    const std::uint64_t len = std::min<std::uint64_t>(w.bytes, 16);
    std::uint64_t abs_off = 0;
    if (!checked_add(off, disp, &abs_off)) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "shared store address underflow"));
    }
    if (abs_off > shared.size() || len > shared.size() - abs_off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "shared store out of bounds"));
    }
    if (!width_aligned(abs_off, w.bytes)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "shared store misaligned for width"));
    }
    std::uint8_t buf[16] = {0};
    mem_value_to_bytes(in, len, buf);
    std::memcpy(shared.data() + abs_off, buf, len);
    return Status::success();
}

Status MemoryService::atom_global(std::uint64_t addr, std::uint64_t width,
                                  AtomicOp op, const MemValue& operands,
                                  MemValue& old, const MemValue* cmp) {
    std::lock_guard<std::mutex> lk(global_mutex_);
    if (global_base_.is_null()) {
        return Status::failure(
            Error(ErrorCode::kBadAddress, "no global memory for atomic"));
    }
    Status ws = check_atomic_width(width);
    if (ws.failed()) return ws;
    const std::uint64_t off = addr;  // addr is already relative to global base
    if (off > global_->size() || width > global_->size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "global atomic out of bounds"));
    }
    if (!width_aligned(off, width)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "global atomic misaligned for width"));
    }
    std::uint8_t cur[8] = {0};
    std::uint8_t opr_buf[8] = {0};
    std::uint8_t cmp_buf[8] = {0};
    std::memcpy(&cur, global_->data() + off, width);
    mem_value_to_bytes_atomic(operands, width, opr_buf);
    if (cmp) mem_value_to_bytes_atomic(*cmp, width, cmp_buf);
    old = {};
    // `old` is the PRE-operation value: capture before the RMW applies.
    std::memcpy(&old[0], cur, width <= 4 ? width : 4);
    if (width > 4) std::memcpy(&old[1], cur + 4, width - 4);

    std::uint64_t r = 0;
    if (!apply_atomic(op, width, load_le(cur, width),
                      load_le(opr_buf, width), load_le(cmp_buf, width), &r)) {
        return Status::failure(
            Error(ErrorCode::kNotSupported,
                  "atomic op " + std::to_string(static_cast<int>(op)) +
                      " at width " + std::to_string(width) +
                      " is not implemented"));
    }
    store_le(cur, r, width);
    std::memcpy(global_->data() + off, cur, width);
    ++reads_;
    ++writes_;
    return Status::success();
}

Status MemoryService::atom_shared(std::vector<std::uint8_t>& shared,
                                  std::uint64_t off, std::uint64_t width,
                                  AtomicOp op, const MemValue& operands,
                                  MemValue& old, const MemValue* cmp) {
    Status ws = check_atomic_width(width);
    if (ws.failed()) return ws;
    if (off > shared.size() || width > shared.size() - off) {
        return Status::failure(Error(ErrorCode::kOob,
                                     "shared atomic out of bounds"));
    }
    if (!width_aligned(off, width)) {
        return Status::failure(Error(ErrorCode::kAlignmentViolation,
                                     "shared atomic misaligned for width"));
    }
    std::uint8_t cur[8] = {0};
    std::uint8_t opr_buf[8] = {0};
    std::uint8_t cmp_buf[8] = {0};
    std::memcpy(&cur, shared.data() + off, width);
    mem_value_to_bytes_atomic(operands, width, opr_buf);
    if (cmp) mem_value_to_bytes_atomic(*cmp, width, cmp_buf);
    old = {};
    // `old` is the PRE-operation value: capture before the RMW applies.
    std::memcpy(&old[0], cur, width <= 4 ? width : 4);
    if (width > 4) std::memcpy(&old[1], cur + 4, width - 4);

    std::uint64_t r = 0;
    if (!apply_atomic(op, width, load_le(cur, width),
                      load_le(opr_buf, width), load_le(cmp_buf, width), &r)) {
        return Status::failure(
            Error(ErrorCode::kNotSupported,
                  "atomic op " + std::to_string(static_cast<int>(op)) +
                      " at width " + std::to_string(width) +
                      " is not implemented"));
    }
    store_le(cur, r, width);
    std::memcpy(shared.data() + off, cur, width);
    return Status::success();
}

void MemoryService::membar() {}
void MemoryService::fence() {}

void MemoryService::commit_group() { groups_.emplace_back(); }
void MemoryService::drain() { groups_.clear(); }
std::size_t MemoryService::pending_ops(std::uint64_t group) const {
    if (group >= groups_.size()) return 0;
    std::size_t n = 0;
    for (const auto& op : groups_[group]) {
        if (!op.completed) ++n;
    }
    return n;
}

Fault memory_error_to_fault(const Error& e, std::uint64_t pc,
                            std::uint32_t warp) {
    switch (e.code()) {
        case ErrorCode::kAlignmentViolation:
            return Fault(FaultKind::kAlignmentFault, e.message())
                .set_pc(pc)
                .set_warp(warp);
        case ErrorCode::kLifecycle:
            return Fault(FaultKind::kLifecycleFault, e.message())
                .set_pc(pc)
                .set_warp(warp);
        case ErrorCode::kNotSupported:
        case ErrorCode::kUnimplemented:
        case ErrorCode::kInvalidArgument:
            return Fault(FaultKind::kIllegalMemoryAccess, e.message())
                .set_pc(pc)
                .set_warp(warp);
        default:
            return Fault(FaultKind::kIllegalMemoryAccess, e.message())
                .set_pc(pc)
                .set_warp(warp);
    }
}

}  // namespace semu
