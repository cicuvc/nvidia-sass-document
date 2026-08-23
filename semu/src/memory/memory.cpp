// Virtual device memory implementation (SIM_PLAN Phase 3).
//
// MemoryAllocator: deterministic 64-bit virtual address space with
// monotonic, never-reused AllocationIds; structured lifecycle/bounds/
// alignment errors.  ConstantBank: the c[0x0][...] window the device-side
// reads kernel parameters and preset slots from (sm120 ABI).

#include <semu/memory/memory.hpp>

#include <algorithm>
#include <cstring>

namespace semu {

const char* to_string(AddressSpace as) {
    switch (as) {
        case AddressSpace::kGlobal: return "global";
        case AddressSpace::kConstant: return "constant";
        case AddressSpace::kShared: return "shared";
        case AddressSpace::kLocal: return "local";
    }
    return "?";
}

// ---------------------------------------------------------------------------
// MemoryAllocator
// ---------------------------------------------------------------------------

namespace {

// Align `value` up to `align` (align must be a power of two; 0 = no align).
bool is_pow2(std::uint64_t v) { return v != 0 && (v & (v - 1)) == 0; }

std::uint64_t align_up(std::uint64_t value, std::uint64_t align) {
    if (align <= 1) return value;
    return (value + align - 1) & ~(align - 1);
}

const Allocation* find_containing(const std::vector<Allocation>& allocs,
                                  std::uint64_t va) {
    // allocs is sorted by base address; find the last alloc with base <= va.
    std::size_t lo = 0, hi = allocs.size();
    while (lo < hi) {
        const std::size_t mid = (lo + hi) / 2;
        if (allocs[mid].base.va <= va) {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    if (lo == 0) return nullptr;
    const Allocation& a = allocs[lo - 1];
    if (a.alive && va < a.base.va + a.size) return &a;
    return nullptr;
}

}  // namespace

MemoryAllocator::MemoryAllocator(std::uint64_t base) : cursor_(base) {}

StatusOr<DevicePtr> MemoryAllocator::allocate(AddressSpace space,
                                              std::uint64_t size,
                                              std::uint64_t align) {
    return allocate(space, size, align, "context");
}

StatusOr<DevicePtr> MemoryAllocator::allocate(AddressSpace space,
                                              std::uint64_t size,
                                              std::uint64_t align,
                                              std::string owner) {
    if (size == 0) {
        return StatusOr<DevicePtr>::failure(Error::invalid_argument(
            "allocation of zero bytes"));
    }
    if (align != 0 && !is_pow2(align)) {
        return StatusOr<DevicePtr>::failure(Error::invalid_argument(
            "allocation alignment " + std::to_string(align) +
            " is not a power of two"));
    }
    // Align at least to 16 (SASS operand granularity).
    const std::uint64_t eff_align = std::max<std::uint64_t>(align, 16);
    const std::uint64_t start = align_up(cursor_, eff_align);
    if (start < cursor_ || size > UINT64_MAX - start) {
        return StatusOr<DevicePtr>::failure(Error::out_of_memory(
            "virtual address space exhausted"));
    }
    Allocation a;
    a.id = AllocationId{next_id_++};
    a.space = space;
    a.base = DevicePtr{start};
    a.size = size;
    a.align = eff_align;
    a.alive = true;
    a.owner = std::move(owner);
    a.data.assign(static_cast<std::size_t>(size), 0);
    allocs_.push_back(std::move(a));
    // Keep sorted by base (bases are strictly increasing anyway).
    cursor_ = start + size;
    return StatusOr<DevicePtr>::success(a.base);
}

Status MemoryAllocator::free(DevicePtr ptr) {
    const auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.base == ptr; });
    if (found == allocs_.end()) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "free of unknown device pointer 0x" +
                std::to_string(ptr.va),
            Error::invalid_argument("")));
    }
    if (!found->alive) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "double free of device allocation " +
                std::to_string(found->id.id),
            Error::invalid_argument("")));
    }
    found->alive = false;
    return Status::success();
}

Status MemoryAllocator::free(AllocationId id) {
    const auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.id == id; });
    if (found == allocs_.end()) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "free of unknown allocation id " + std::to_string(id.id),
            Error::invalid_argument("")));
    }
    return free(found->base);
}

StatusOr<Allocation> MemoryAllocator::resolve(DevicePtr ptr) const {
    const Allocation* a = find_containing(allocs_, ptr.va);
    if (!a || a->base != ptr) {
        return StatusOr<Allocation>::failure(Error(
            ErrorCode::kBadAddress,
            "device pointer 0x" + std::to_string(ptr.va) +
                " is not an allocation base",
            Error::invalid_argument("")));
    }
    return StatusOr<Allocation>::success(*a);
}

StatusOr<MemoryAllocator::ResolvedRange> MemoryAllocator::resolve_range(
    DevicePtr ptr, std::uint64_t len) const {
    const Allocation* a = find_containing(allocs_, ptr.va);
    if (!a) {
        return StatusOr<ResolvedRange>::failure(Error(
            ErrorCode::kBadAddress,
            "device pointer 0x" + std::to_string(ptr.va) +
                " does not fall inside any allocation",
            Error::invalid_argument("")));
    }
    if (!a->contains(ptr.va - a->base.va, len)) {
        return StatusOr<ResolvedRange>::failure(Error(
            ErrorCode::kOob,
            "access at 0x" + std::to_string(ptr.va) + " len " +
                std::to_string(len) + " out of bounds of allocation " +
                std::to_string(a->id.id) + " (" + to_string(a->space) +
                ", size " + std::to_string(a->size) + ")",
            Error::out_of_range("")));
    }
    return StatusOr<ResolvedRange>::success(
        ResolvedRange{*a, ptr.va - a->base.va});
}

StatusOr<Allocation> MemoryAllocator::allocation_by_base(
    DevicePtr base) const {
    const auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.base == base && a.alive; });
    if (found == allocs_.end()) {
        return StatusOr<Allocation>::failure(Error::not_found(
            "no live allocation at base 0x" + std::to_string(base.va)));
    }
    return StatusOr<Allocation>::success(*found);
}

Status MemoryAllocator::read_at(AllocationId id, std::uint64_t off,
                                void* dst, std::uint64_t len) {
    auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.id == id && a.alive; });
    if (found == allocs_.end()) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "allocation " + std::to_string(id.id) + " not live",
            Error::invalid_argument("")));
    }
    if (!found->contains(off, len)) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "read at offset 0x" + std::to_string(off) + " len " +
                std::to_string(len) + " out of bounds of allocation " +
                std::to_string(id.id) + " (size " +
                std::to_string(found->size) + ")",
            Error::out_of_range("")));
    }
    std::memcpy(dst, found->data.data() + off, static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::write_at(AllocationId id, std::uint64_t off,
                                 const void* src, std::uint64_t len) {
    auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.id == id && a.alive; });
    if (found == allocs_.end()) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "allocation " + std::to_string(id.id) + " not live",
            Error::invalid_argument("")));
    }
    if (!found->contains(off, len)) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "write at offset 0x" + std::to_string(off) + " len " +
                std::to_string(len) + " out of bounds of allocation " +
                std::to_string(id.id) + " (size " +
                std::to_string(found->size) + ")",
            Error::out_of_range("")));
    }
    std::memcpy(found->data.data() + off, src, static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::atomic_rmw(AllocationId id, std::uint64_t off,
                                    std::uint64_t width, AtomicOp op,
                                    const void* operand, void* old) {
    if (width != 1 && width != 2 && width != 4 && width != 8) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "atomic width " + std::to_string(width) + " not in {1,2,4,8}",
            Error::invalid_argument("")));
    }
    if (static_cast<std::uint8_t>(op) >=
        static_cast<std::uint8_t>(AtomicOp::kCount)) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "undefined atomic op " + std::to_string(static_cast<int>(op)),
            Error::invalid_argument("")));
    }
    // One critical section: resolve + read + compute + write (High 1).
    std::lock_guard<std::mutex> lock(*atomic_mutex_);
    auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.id == id && a.alive; });
    if (found == allocs_.end()) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "allocation " + std::to_string(id.id) + " not live",
            Error::invalid_argument("")));
    }
    if (!found->contains(off, width)) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "atomic at offset 0x" + std::to_string(off) + " width " +
                std::to_string(width) + " out of bounds of allocation " +
                std::to_string(id.id) + " (size " +
                std::to_string(found->size) + ")",
            Error::out_of_range("")));
    }
    std::uint8_t* mem = found->data.data() + off;
    std::uint64_t oldv = 0, val = 0, next = 0;
    std::memcpy(&oldv, mem, static_cast<std::size_t>(width));
    std::memcpy(&val, operand, static_cast<std::size_t>(width));
    // kCas has no compare operand on this low-level path (the interpreter's
    // MemoryService atomics handle CAS); reject it rather than downgrade.
    if (op == AtomicOp::kCas) {
        return Status::failure(Error(
            ErrorCode::kNotSupported,
            "CAS atomic on the allocator path requires a compare operand",
            Error::unimplemented("")));
    }
    // kInc / kDec are U32-only (SASS CONDITIONS), like MemoryService.
    if (op == AtomicOp::kInc || op == AtomicOp::kDec) {
        if (width != 4) {
            return Status::failure(Error(
                ErrorCode::kNotSupported,
                "atomic INC/DEC is only defined for U32",
                Error::unimplemented("")));
        }
        const std::uint32_t a = static_cast<std::uint32_t>(oldv);
        const std::uint32_t b = static_cast<std::uint32_t>(val);
        next = op == AtomicOp::kInc ? ((a >= b) ? 0u : a + 1u)
                                    : ((a == 0 || a > b) ? b : a - 1u);
        std::memcpy(mem, &next, static_cast<std::size_t>(width));
        if (old) std::memcpy(old, &oldv, static_cast<std::size_t>(width));
        return Status::success();
    }
    // Signed S32/S64 min/max (Blocker-4).
    if (op == AtomicOp::kMinSigned || op == AtomicOp::kMaxSigned) {
        std::int64_t a = 0, b = 0;
        switch (width) {
            case 1: a = static_cast<std::int8_t>(oldv);
                    b = static_cast<std::int8_t>(val); break;
            case 2: a = static_cast<std::int16_t>(oldv);
                    b = static_cast<std::int16_t>(val); break;
            case 4: a = static_cast<std::int32_t>(oldv);
                    b = static_cast<std::int32_t>(val); break;
            default: a = static_cast<std::int64_t>(oldv);
                     b = static_cast<std::int64_t>(val); break;
        }
        const std::int64_t r = op == AtomicOp::kMinSigned
                                   ? std::min(a, b) : std::max(a, b);
        next = static_cast<std::uint64_t>(r);
        std::memcpy(mem, &next, static_cast<std::size_t>(width));
        if (old) std::memcpy(old, &oldv, static_cast<std::size_t>(width));
        return Status::success();
    }
    switch (op) {
        case AtomicOp::kAdd: next = oldv + val; break;
        case AtomicOp::kMin: next = oldv < val ? oldv : val; break;
        case AtomicOp::kMax: next = oldv > val ? oldv : val; break;
        case AtomicOp::kAnd: next = oldv & val; break;
        case AtomicOp::kOr:  next = oldv | val; break;
        case AtomicOp::kXor: next = oldv ^ val; break;
        case AtomicOp::kExch: next = val; break;
        case AtomicOp::kInc:
        case AtomicOp::kDec:
        case AtomicOp::kCas:
        case AtomicOp::kMinSigned:
        case AtomicOp::kMaxSigned:
        case AtomicOp::kCount:
            return Status::failure(Error(
                ErrorCode::kNotSupported,
                "atomic op " + std::to_string(static_cast<int>(op)) +
                    " not supported on this path",
                Error::unimplemented("")));
    }
    if (old) std::memcpy(old, &oldv, static_cast<std::size_t>(width));
    std::memcpy(mem, &next, static_cast<std::size_t>(width));
    return Status::success();
}

Status MemoryAllocator::free_domain(const std::string& owner) {
    bool any = false;
    for (auto& a : allocs_) {
        if (a.alive && a.owner == owner) {
            a.alive = false;
            any = true;
        }
    }
    return any ? Status::success()
               : Status::failure(Error::not_found(
                     "no live allocations in domain '" + owner + "'"));
}

StatusOr<Allocation> MemoryAllocator::allocation_by_id(
    AllocationId id) const {
    const auto found = std::find_if(
        allocs_.begin(), allocs_.end(),
        [&](const Allocation& a) { return a.id == id; });
    if (found == allocs_.end()) {
        return StatusOr<Allocation>::failure(Error::not_found(
            "allocation id " + std::to_string(id.id)));
    }
    return StatusOr<Allocation>::success(*found);
}

Status MemoryAllocator::write(DevicePtr ptr, const void* src,
                              std::uint64_t len) {
    auto r = resolve_range(ptr, len);
    if (r.failed()) return r.status();
    // Re-resolve to the live object so the write lands in the backing
    // store (ResolvedRange carries a value copy for inspection).
    Allocation* live = const_cast<Allocation*>(find_containing(allocs_, ptr.va));
    if (!live) return Status::failure(Error::internal("allocation vanished"));
    std::memcpy(live->data.data() + r.value().offset, src,
                static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::read(DevicePtr ptr, void* dst, std::uint64_t len) {
    auto r = resolve_range(ptr, len);
    if (r.failed()) return r.status();
    const Allocation* live = find_containing(allocs_, ptr.va);
    if (!live) return Status::failure(Error::internal("allocation vanished"));
    std::memcpy(dst, live->data.data() + r.value().offset,
                static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::memset(DevicePtr ptr, int value, std::uint64_t len) {
    auto r = resolve_range(ptr, len);
    if (r.failed()) return r.status();
    Allocation* live = const_cast<Allocation*>(find_containing(allocs_, ptr.va));
    if (!live) return Status::failure(Error::internal("allocation vanished"));
    std::memset(live->data.data() + r.value().offset, value,
                static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::copy(DevicePtr dst, DevicePtr src, std::uint64_t len) {
    auto rd = resolve_range(dst, len);
    if (rd.failed()) return rd.status();
    auto rs = resolve_range(src, len);
    if (rs.failed()) return rs.status();
    Allocation* dlive =
        const_cast<Allocation*>(find_containing(allocs_, dst.va));
    const Allocation* slive = find_containing(allocs_, src.va);
    if (!dlive || !slive) {
        return Status::failure(Error::internal("allocation vanished"));
    }
    std::memmove(dlive->data.data() + rd.value().offset,
                 slive->data.data() + rs.value().offset,
                 static_cast<std::size_t>(len));
    return Status::success();
}

// ---------------------------------------------------------------------------
// Typed device access (P3-GAP-06)
// ---------------------------------------------------------------------------

namespace {

// Resolve + validate a typed access: alignment, address-space match, then
// the underlying range/bounds/lifecycle checks.  Returns the live
// allocation and interior offset.
StatusOr<Allocation*> resolve_typed(
    std::vector<Allocation>& allocs, DevicePtr ptr, std::uint64_t len,
    const DeviceAccess& access, std::uint64_t* offset) {
    if (len != access.width) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kInvalidArgument,
            "typed access length " + std::to_string(len) +
                " != access width " + std::to_string(access.width),
            Error::invalid_argument("")));
    }
    // Alignment must be a power of two and the address aligned to it.
    if (access.alignment == 0 ||
        (access.alignment & (access.alignment - 1)) != 0) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kInvalidArgument,
            "access alignment " + std::to_string(access.alignment) +
                " is not a power of two",
            Error::invalid_argument("")));
    }
    if (ptr.va % access.alignment != 0) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kAlignmentViolation,
            "access at 0x" + std::to_string(ptr.va) + " misaligned for " +
                std::to_string(access.alignment) + "-byte alignment",
            Error::invalid_argument("")));
    }
    const Allocation* ca = find_containing(allocs, ptr.va);
    Allocation* a = const_cast<Allocation*>(ca);
    if (!a) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kBadAddress,
            "access at 0x" + std::to_string(ptr.va) +
                " does not fall inside any allocation",
            Error::invalid_argument("")));
    }
    if (a->space != access.space) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kBadAddress,
            "access at 0x" + std::to_string(ptr.va) + " targets " +
                to_string(a->space) + " allocation but access requested " +
                to_string(access.space),
            Error::invalid_argument("")));
    }
    // P3-GAP-07: shared/local access is isolated by owner domain.  The
    // caller's domain must match the allocation's owner exactly.
    if (a->space == AddressSpace::kShared || a->space == AddressSpace::kLocal) {
        const std::string spc = to_string(a->space);
        if (access.domain.empty()) {
            return StatusOr<Allocation*>::failure(Error(
                ErrorCode::kBadAddress,
                "access to " + spc + " allocation at 0x" +
                    std::to_string(ptr.va) + " (owner '" + a->owner +
                    "') requires a caller domain",
                Error::invalid_argument("")));
        }
        if (access.domain != a->owner) {
            return StatusOr<Allocation*>::failure(Error(
                ErrorCode::kBadAddress,
                "access at 0x" + std::to_string(ptr.va) + " by domain '" +
                    access.domain + "' rejected: allocation owned by '" +
                    a->owner + "'",
                Error::invalid_argument("")));
        }
    }
    if (!a->contains(ptr.va - a->base.va, len)) {
        return StatusOr<Allocation*>::failure(Error(
            ErrorCode::kOob,
            "access at 0x" + std::to_string(ptr.va) + " len " +
                std::to_string(len) + " out of bounds of allocation " +
                std::to_string(a->id.id) + " (" + to_string(a->space) +
                ", size " + std::to_string(a->size) + ")",
            Error::out_of_range("")));
    }
    *offset = ptr.va - a->base.va;
    return StatusOr<Allocation*>::success(const_cast<Allocation*>(a));
}

}  // namespace

// P3-GAP-06: the operation (read vs write) must be consistent with the
// access kind.  Atomic accesses must be 1/2/4/8 bytes on global/shared;
// text (instruction fetch) is a read-only global-space access.
Status check_kind_consistency(bool is_write, const DeviceAccess& access) {
    if (access.kind == AccessKind::kAtomic) {
        if (access.width != 1 && access.width != 2 && access.width != 4 &&
            access.width != 8) {
            return Status::failure(Error(
                ErrorCode::kInvalidArgument,
                "atomic access width " + std::to_string(access.width) +
                    " not in {1,2,4,8}",
                Error::invalid_argument("")));
        }
        if (access.space != AddressSpace::kGlobal &&
            access.space != AddressSpace::kShared) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "atomic access only valid in global/shared",
                Error::invalid_argument("")));
        }
        // Atomics both read and write; allow either entry point.
        return Status::success();
    }
    if (access.kind == AccessKind::kText) {
        if (is_write) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "text (instruction fetch) access is read-only",
                Error::invalid_argument("")));
        }
        if (access.space != AddressSpace::kGlobal) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "text access must target the global address space",
                Error::invalid_argument("")));
        }
        return Status::success();
    }
    // kLoad / kStore: operation must match the kind.
    if (access.kind == AccessKind::kLoad && is_write) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "write through a kLoad access is rejected",
            Error::invalid_argument("")));
    }
    if (access.kind == AccessKind::kStore && !is_write) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "read through a kStore access is rejected",
            Error::invalid_argument("")));
    }
    return Status::success();
}

Status MemoryAllocator::read_typed(DevicePtr ptr, void* dst, std::uint64_t len,
                                   const DeviceAccess& access) {
    Status kst = check_kind_consistency(/*is_write=*/false, access);
    if (kst.failed()) return kst;
    std::uint64_t off = 0;
    auto r = resolve_typed(allocs_, ptr, len, access, &off);
    if (r.failed()) return r.status();
    std::memcpy(dst, r.value()->data.data() + off,
                static_cast<std::size_t>(len));
    return Status::success();
}

Status MemoryAllocator::write_typed(DevicePtr ptr, const void* src,
                                    std::uint64_t len,
                                    const DeviceAccess& access) {
    Status kst = check_kind_consistency(/*is_write=*/true, access);
    if (kst.failed()) return kst;
    std::uint64_t off = 0;
    auto r = resolve_typed(allocs_, ptr, len, access, &off);
    if (r.failed()) return r.status();
    std::memcpy(r.value()->data.data() + off, src,
                static_cast<std::size_t>(len));
    return Status::success();
}

// ---------------------------------------------------------------------------
// ConstantBank
// ---------------------------------------------------------------------------

ConstantBank::ConstantBank(ConstantBankLayout layout) : layout_(layout) {
    // P3-GAP-01: layout invariants — param_base and preset slots must fit
    // within the bank.
    if (layout_.param_base > layout_.size) {
        throw std::invalid_argument(
            "ConstantBankLayout: param_base 0x" +
            std::to_string(layout_.param_base) + " > bank size 0x" +
            std::to_string(layout_.size));
    }
    if (layout_.default_cdesc_offset > layout_.size ||
        8 > layout_.size - layout_.default_cdesc_offset) {
        throw std::invalid_argument(
            "ConstantBankLayout: default_cdesc slot at 0x" +
            std::to_string(layout_.default_cdesc_offset) +
            " does not fit in bank size 0x" + std::to_string(layout_.size));
    }
    bank_.resize(layout_.size, 0);
}

Status ConstantBank::write_param(std::uint64_t off, const void* data,
                                 std::uint64_t len) {
    // KPARAM offsets are relative to the parameter base; the driver places
    // them at param_base + off inside the cbank window.
    if (off > layout_.size - layout_.param_base ||
        len > layout_.size - (layout_.param_base + off)) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "parameter write at 0x" + std::to_string(off) + " len " +
                std::to_string(len) + " past constant bank size " +
                std::to_string(layout_.size),
            Error::out_of_range("")));
    }
    const std::uint64_t dst = layout_.param_base + off;
    std::memcpy(bank_.data() + dst, data, static_cast<std::size_t>(len));
    return Status::success();
}

StatusOr<std::vector<std::uint8_t>> ConstantBank::read_param(
    std::uint64_t off, std::uint64_t len) const {
    if (off > layout_.size - layout_.param_base ||
        len > layout_.size - (layout_.param_base + off)) {
        return StatusOr<std::vector<std::uint8_t>>::failure(Error(
            ErrorCode::kOob,
            "parameter read at 0x" + std::to_string(off) + " len " +
                std::to_string(len) + " past constant bank size " +
                std::to_string(layout_.size),
            Error::out_of_range("")));
    }
    const std::uint64_t src = layout_.param_base + off;
    return StatusOr<std::vector<std::uint8_t>>::success(
        std::vector<std::uint8_t>(
            bank_.begin() + static_cast<std::ptrdiff_t>(src),
            bank_.begin() + static_cast<std::ptrdiff_t>(src + len)));
}

Status ConstantBank::write_slot(std::uint64_t offset, const void* data,
                                std::uint64_t len) {
    // P3-GAP-01: absolute bank offset (no param_base adjustment).
    if (!(offset <= layout_.size && len <= layout_.size - offset)) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "slot write at 0x" + std::to_string(offset) + " len " +
                std::to_string(len) + " past constant bank size " +
                std::to_string(layout_.size),
            Error::out_of_range("")));
    }
    std::memcpy(bank_.data() + offset, data, static_cast<std::size_t>(len));
    return Status::success();
}

void ConstantBank::clear() {
    std::fill(bank_.begin(), bank_.end(), 0);
}

Status ConstantBank::seed_from(const std::vector<std::uint8_t>& image) {
    if (image.size() > layout_.size) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "constant0 seed image " + std::to_string(image.size()) +
                " bytes larger than bank " + std::to_string(layout_.size),
            Error::out_of_range("")));
    }
    std::copy(image.begin(), image.end(), bank_.begin());
    return Status::success();
}

StatusOr<std::vector<std::uint8_t>> ConstantBank::read_raw(
    std::uint64_t off, std::uint64_t len) const {
    // Absolute bank access (no param_base adjustment).
    if (!(off <= layout_.size && len <= layout_.size - off)) {
        return StatusOr<std::vector<std::uint8_t>>::failure(Error(
            ErrorCode::kOob,
            "raw read at 0x" + std::to_string(off) + " len " +
                std::to_string(len) + " past constant bank size " +
                std::to_string(layout_.size),
            Error::out_of_range("")));
    }
    return StatusOr<std::vector<std::uint8_t>>::success(
        std::vector<std::uint8_t>(
            bank_.begin() + static_cast<std::ptrdiff_t>(off),
            bank_.begin() + static_cast<std::ptrdiff_t>(off + len)));
}

}  // namespace semu
