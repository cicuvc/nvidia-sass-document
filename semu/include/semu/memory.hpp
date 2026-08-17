#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <semu/status.hpp>

// Virtual device memory (SIM_PLAN Phase 3).
//
// The simulator models a stable 64-bit device address space with four
// address-space abstractions (global / constant / shared / local).  Every
// allocation gets:
//
//   - a monotonically increasing, never-reused AllocationId (events and race
//     reports key on this, never on host addresses);
//   - a deterministic virtual address (the same allocation sequence always
//     yields the same addresses, across hosts/runs);
//   - an address-space tag and a byte size with alignment.
//
// Host access (read/write/memset) goes through the allocator and performs
// lifecycle (use-after-free), bounds (OOB) and alignment checks; errors are
// structured Error values, never crashes.
//
// DevicePtr is a plain 64-bit virtual address; adding an offset yields a
// DevicePtr (overflow-checked).

namespace semu {

enum class AddressSpace : std::uint8_t {
    kGlobal = 0,    // context-bound; persists for the context lifetime
    kConstant = 1,  // context-bound; read-only from the device
    kShared = 2,    // CTA-bound; freed when the CTA ends
    kLocal = 3,     // thread-bound; per-warp local window
};

const char* to_string(AddressSpace as);

struct AllocationId {
    std::uint64_t id = 0;
    bool operator==(const AllocationId&) const = default;
};
constexpr AllocationId kNullAllocationId{0};

// Stable 64-bit device virtual address.  Arithmetic is overflow-checked.
struct DevicePtr {
    std::uint64_t va = 0;

    bool operator==(const DevicePtr&) const = default;
    bool is_null() const { return va == 0; }

    // Add an offset (returns error on overflow / negative past zero).
    // INT64_MIN-safe: magnitude computed without signed negation.
    StatusOr<DevicePtr> add(std::int64_t delta) const {
        if (delta >= 0) {
            if (va > UINT64_MAX - static_cast<std::uint64_t>(delta)) {
                return StatusOr<DevicePtr>::failure(Error::out_of_range(
                    "device pointer arithmetic overflow"));
            }
            return StatusOr<DevicePtr>::success(DevicePtr{
                va + static_cast<std::uint64_t>(delta)});
        }
        // |delta| for delta = INT64_MIN cannot be negated in int64; compute
        // in uint64 (two's complement magnitude is exact).
        const std::uint64_t mag =
            static_cast<std::uint64_t>(-(delta + 1)) + 1;
        if (va < mag) {
            return StatusOr<DevicePtr>::failure(Error::out_of_range(
                "device pointer arithmetic underflow"));
        }
        return StatusOr<DevicePtr>::success(DevicePtr{va - mag});
    }
};

// Host-visible view of one device allocation.  `data` owns the device bytes
// (the backing store); access is validated against the ranges and goes
// through the allocator.
struct Allocation {
    AllocationId id;
    AddressSpace space = AddressSpace::kGlobal;
    DevicePtr base;
    std::uint64_t size = 0;
    std::uint64_t align = 0;
    bool alive = true;
    std::string label;  // e.g. kernel name for shared/local, "" for global
    // Owner domain: "context" for global/constant, "cta:<n>" for shared,
    // "warp:<cta>:<w>" for local.  Used by P3-GAP-07 to isolate accesses
    // between domains and to reclaim allocations when a domain ends.
    std::string owner;
    std::vector<std::uint8_t> data;  // backing bytes (size bytes)

    // Byte range check [off, off+len) within this allocation.
    bool contains(std::uint64_t off, std::uint64_t len) const {
        return off <= size && len <= size - off;
    }
};

// Typed device access descriptor (P3-GAP-06): the interpreter's loads and
// stores specify width / required alignment / address space / access kind.
// The allocator enforces the alignment and address-space contract and
// returns distinct error codes (kAlignmentViolation / kOob / kLifecycle /
// kBadAddress) that the debugger/profiler/race detector can consume.
enum class AccessKind : std::uint8_t {
    kLoad = 0,
    kStore = 1,
    kAtomic = 2,
    kText = 3,  // instruction fetch (text section)
};

// RMW atomic operations supported by the atomic path.  kMin / kMax compare
// as UNSIGNED little-endian values of the access width; kMinSigned /
// kMaxSigned compare as SIGNED values (SASS S32/S64 atom variants, Blocker-4).
// kInc/kDec are the U32-only wrap-to-bound increments; kCas is compare-and-
// swap (needs a separate compare operand).  Any other op is rejected by the
// atomic path (never silently downgraded to ADD).
enum class AtomicOp : std::uint8_t {
    kAdd = 0,
    kMin = 1,      // unsigned min
    kMax = 2,      // unsigned max
    kAnd = 3,
    kOr = 4,
    kXor = 5,
    kExch = 6,
    kInc = 7,      // atom.inc: (old >= bound) ? 0 : old + 1  (U32 only)
    kDec = 8,      // atom.dec: (old == 0 || old > bound) ? bound : old - 1
    kCas = 9,      // compare-and-swap (compare operand passed separately)
    kMinSigned = 10,
    kMaxSigned = 11,
    kCount,        // sentinel: number of defined ops
};

struct DeviceAccess {
    std::uint64_t width = 1;          // 1/2/4/8/16/32/128/256 bytes
    std::uint64_t alignment = 1;      // required address alignment
    AddressSpace space = AddressSpace::kGlobal;
    AccessKind kind = AccessKind::kLoad;
    // Accessing domain (P3-GAP-07): who is performing the access.
    //   global/constant: "context" (or any domain; no isolation applied)
    //   shared: "cta:<id>"
    //   local: "warp:<cta>:<warp>"
    // Empty = no domain check (host/context accesses).
    std::string domain;
};

// The virtual address map + host access for one Context.  Owns the backing
// bytes; DevicePtr values are only meaningful through this allocator.
class MemoryAllocator {
public:
    explicit MemoryAllocator(std::uint64_t base = kDefaultBase);

    // --- allocation ------------------------------------------------------
    // Allocate `size` bytes in `space` with `align` (power of two).
    // Returns the base DevicePtr.  Fails on overflow, alignment misuse or
    // address-space exhaustion.
    StatusOr<DevicePtr> allocate(AddressSpace space, std::uint64_t size,
                                 std::uint64_t align = 16);

    // Free an allocation.  Double-free / unknown pointer -> kLifecycle.
    Status free(DevicePtr ptr);
    Status free(AllocationId id);

    // --- lookup ----------------------------------------------------------
    // Find the allocation covering the exact DevicePtr (fails if it falls
    // in the middle of nothing, or the pointer is not a base).
    StatusOr<Allocation> resolve(DevicePtr ptr) const;
    // Find the allocation containing [ptr, ptr+len) (for access checks).
    // `ptr` may be interior; returns the allocation + the interior offset.
    struct ResolvedRange {
        Allocation alloc;
        std::uint64_t offset = 0;  // interior byte offset within alloc
    };
    StatusOr<ResolvedRange> resolve_range(DevicePtr ptr,
                                          std::uint64_t len) const;
    StatusOr<Allocation> allocation_by_id(AllocationId id) const;
    // Lookup a live allocation by its exact base address.
    StatusOr<Allocation> allocation_by_base(DevicePtr base) const;
    // Direct read/write into a live allocation's backing store by id +
    // interior offset (avoids value-copy aliasing; bounds-checked).
    Status read_at(AllocationId id, std::uint64_t off, void* dst,
                   std::uint64_t len);
    Status write_at(AllocationId id, std::uint64_t off, const void* src,
                    std::uint64_t len);

    // True atomic read-modify-write (High 1): resolve, read, compute and
    // write happen inside one critical section, so concurrent CPU workers
    // (future multi-core backends) never lose updates.  `width` must be in
    // {1,2,4,8}; the pre-RMW value is returned in `old` (may be null).
    // The op is applied as an UNSIGNED value of `width` bytes.
    Status atomic_rmw(AllocationId id, std::uint64_t off, std::uint64_t width,
                      AtomicOp op, const void* operand, void* old);

    // --- host access -----------------------------------------------------
    // Write host bytes into device memory at [ptr, ptr+len).
    Status write(DevicePtr ptr, const void* src, std::uint64_t len);
    // Read device bytes into host buffer at [ptr, ptr+len).
    Status read(DevicePtr ptr, void* dst, std::uint64_t len);
    // Fill [ptr, ptr+len) with `value` (byte-wise).
    Status memset(DevicePtr ptr, int value, std::uint64_t len);
    // Copy len bytes from src device range to dst device range.
    Status copy(DevicePtr dst, DevicePtr src, std::uint64_t len);

    // --- typed device access (P3-GAP-06) ----------------------------------
    // Instruction-level access: enforces `access.alignment` and
    // `access.space`, returns kAlignmentViolation / kOob / kLifecycle /
    // kBadAddress.  `len` must equal `access.width`.
    Status read_typed(DevicePtr ptr, void* dst, std::uint64_t len,
                      const DeviceAccess& access);
    Status write_typed(DevicePtr ptr, const void* src, std::uint64_t len,
                       const DeviceAccess& access);

    // --- domain isolation (P3-GAP-07) -------------------------------------
    // Allocate with an explicit owner domain (e.g. "cta:3", "warp:1:0").
    StatusOr<DevicePtr> allocate(AddressSpace space, std::uint64_t size,
                                 std::uint64_t align,
                                 std::string owner);
    // Reclaim every allocation in `owner`'s domain (CTA/warp teardown).
    Status free_domain(const std::string& owner);

    // Deterministic address bookkeeping (inspection / debugger).
    const std::vector<Allocation>& allocations() const { return allocs_; }
    std::uint64_t next_id() const { return next_id_; }
    std::uint64_t cursor() const { return cursor_; }

private:
    static constexpr std::uint64_t kDefaultBase = 0x10000;
    // Allocations ordered by base address.
    std::vector<Allocation> allocs_;
    std::uint64_t next_id_ = 1;
    std::uint64_t cursor_ = kDefaultBase;
    // Serializes atomic_rmw critical sections (High 1).  Heap-allocated so
    // the allocator stays movable.
    mutable std::unique_ptr<std::mutex> atomic_mutex_{
        std::make_unique<std::mutex>()};
};

// ---------------------------------------------------------------------------
// Constant bank (constant0): the c[0x0][...] window the device-side code
// reads kernel parameters and preset slots from (sm120 ABI).
// ---------------------------------------------------------------------------

// sm120 ABI constant-bank offsets (verified on RTX 5090, CUDA 13.1):
//   parameter base:  c[0x0][0x380] (assembler arch.param_base)
//   default global cache descriptor: c[0x0][0x358]
//   (see assembler/arch.py; sm90 uses 0x210 / 0x208.)
struct ConstantBankLayout {
    std::uint64_t param_base = 0x380;
    std::uint64_t default_cdesc_offset = 0x358;
    std::uint64_t size = 0x10000;  // full cbank window modeled
};

class ConstantBank {
public:
    // Validates layout invariants: param_base <= size, and every preset
    // slot (default_cdesc_offset) fits within the bank.  Malformed layouts
    // are a hard error at construction.
    explicit ConstantBank(ConstantBankLayout layout = {});

    // Kernel-parameter write: place `data` at layout.param_base + off
    // (KPARAM-relative).  Bounds-checked against the bank size.
    Status write_param(std::uint64_t off, const void* data,
                       std::uint64_t len);
    StatusOr<std::vector<std::uint8_t>> read_param(
        std::uint64_t off, std::uint64_t len) const;

    // Preset-slot write at an *absolute* bank offset (e.g. 0x358 for
    // SLOT_DEFAULT_CDESC).  Does NOT add param_base.
    Status write_slot(std::uint64_t offset, const void* data,
                      std::uint64_t len);

    // Raw absolute bank access (for the interpreter later).  Does NOT add
    // param_base.
    StatusOr<std::vector<std::uint8_t>> read_raw(
        std::uint64_t off, std::uint64_t len) const;
    // Clear the whole bank (deterministic launch initialization).
    void clear();
    // Seed the bank with the kernel's .nv.constant0.<name> initial image
    // (loaded by the cubin loader); bytes beyond the image stay 0.
    Status seed_from(const std::vector<std::uint8_t>& image);

    const std::vector<std::uint8_t>& raw() const { return bank_; }
    const ConstantBankLayout& layout() const { return layout_; }

private:
    ConstantBankLayout layout_;
    std::vector<std::uint8_t> bank_;
};

}  // namespace semu
