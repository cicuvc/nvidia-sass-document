#pragma once

// MemoryService — Phase 6 memory model for the SM120 interpreter.
//
// Layering (matching SIM_PLAN Phase 6): the service owns the virtual address
// map and provides SASS-level typed access (LDG/STG/LDS/STS/LDC/LDL + atomics)
// across the L1/L2/shared hierarchy.  Step 1 implements functional memory
// semantics with structured fault conversion; the L1/subcore serialization,
// L2 event layer and race detector are reserved interfaces here and built in
// later steps without changing the functional result.
//
// The service wraps MemoryAllocator (allocation + bounds + alignment + space
// + domain checks) and adds:
//   - width / sign-extension decoding for SASS loads (U8/S8/U16/S16/32/64/128)
//   - address computation for the common operand forms (register + offset,
//     immediate-offset, descriptor + register)
//   - checked address arithmetic (never an unchecked unsigned wrap of a
//     signed displacement or base + addr + offset)
//   - per-width natural alignment enforcement
//   - fault conversion: memory access errors become Interpreter Faults
//     (kIllegalMemoryAccess / kAlignmentFault / kLifecycleFault), never host
//     memory faults.
//
// Values: every load/store/atomic transfers a fixed 16-byte `MemValue` (four
// 32-bit words).  Only the low `width` bytes are meaningful for narrower
// accesses; 128-bit accesses use all four words.  Unimplemented 128-bit
// atomics fault with a structured error (never a truncated 64-bit RMW).

#include <array>
#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

#include <semu/cubin/cubin.hpp>
#include <semu/core/fault.hpp>
#include <semu/memory/memory.hpp>
#include <semu/core/status.hpp>

namespace semu {

// SASS load/store size (the `sz` slot on LDG/STG/LDS/STS/LDC/LDL/STL).
enum class MemWidth : std::uint8_t {
    kU8 = 0,   // 1 byte, zero-extended
    kS8 = 1,   // 1 byte, sign-extended
    kU16 = 2,  // 2 bytes, zero-extended
    kS16 = 3,  // 2 bytes, sign-extended
    k32 = 4,   // 4 bytes
    k64 = 5,   // 8 bytes
    k128 = 6,  // 16 bytes
};

// A fixed 16-byte value transferred by a memory access (four 32-bit words).
using MemValue = std::array<std::uint32_t, 4>;

// Decode the `sz` slot value into a width + sign info.  `valid` is false for
// reserved/invalid slot values (Medium: unknown sizes are rejected, never
// silently treated as 4 bytes).
struct MemWidthInfo {
    std::uint64_t bytes = 4;
    bool sign_extend = false;
    bool valid = true;
};
MemWidthInfo mem_width_info(std::uint64_t sz_slot);

// The resolved address form of a memory operand.
//   - descriptor + Ra + signed offset (LDG/STG/LDL/STL with Ra)
//   - shared: 32-bit shared offset (+ stride for vector ops)
//   - constant: bank + offset
struct ResolvedAddress {
    AddressSpace space = AddressSpace::kGlobal;
    std::uint64_t base = 0;          // global VA or shared byte offset
    std::int64_t offset = 0;         // instruction-provided offset
    std::uint64_t size = 0;          // access byte width
    // For shared memory: the shared VA (base+offset) as a DevicePtr into the
    // CTA shared allocation.  For global: the final VA.
    std::uint64_t final_address() const;
};

// One in-flight memory operation (logical scoreboard entry).
struct PendingMemOp {
    enum class Kind : std::uint8_t { kLoad, kStore, kAtomic, kAsync };
    Kind kind = Kind::kLoad;
    std::uint64_t group = 0;         // commit group id (cp.async / DEPBAR)
    std::uint64_t bytes = 0;
    std::string target;              // "global:0x..." / "shared:+0x.."
    bool completed = false;
};

// MemoryService: owns the device address map and the global/constant backing,
// plus per-CTA shared and per-warp local windows.  Thread-safe for the global
// path (future multi-worker); shared/local are CTA/warp-scoped.
class MemoryService {
public:
    // `params` are the packed kernel parameter bytes (constant0 [0x380, +cbank)).
    explicit MemoryService(const std::vector<std::uint8_t>& params,
                           std::uint64_t global_size = 1u << 20,
                           std::uint64_t shared_size = 48u << 10);

    // --- address spaces -----------------------------------------------------
    // Register the launch's global buffer (allocated in the device map).
    // `label` is for diagnostics.  Returns the base DevicePtr.
    StatusOr<DevicePtr> setup_global(std::uint64_t size,
                                     const std::string& label = "global");
    // Allocate the CTA shared window (called once per CTA at setup).
    StatusOr<DevicePtr> register_cta_shared(std::uint64_t size,
                                            std::uint64_t cta_id);
    // Allocate the per-warp local window (local space is per-warp).
    StatusOr<DevicePtr> register_warp_local(std::uint64_t size,
                                            std::uint64_t cta_id,
                                            std::uint64_t warp_id);
    // Global buffer base (the launch-provided device pointer).
    DevicePtr global_base() const;
    // Global buffer byte size (0 when no global buffer was set up).  Used by
    // the debugger to bounds-check host-visible reads before any copy.
    std::uint64_t global_size() const;
    // Constant window byte size (0x10000).  Used by the debugger to
    // bounds-check constant reads before any copy.
    std::uint64_t constant_size() const;
    // The global buffer's allocation id (real allocator id; used by the race
    // detector's global shadow domain + generation tracking).
    AllocationId global_allocation_id() const;
    // Write host bytes into the global buffer at `off` (used to seed the
    // device backing from the launch's host memory).
    Status write_host(std::uint64_t off, const void* src, std::uint64_t len);
    // Read host-visible bytes out of the global buffer (for result checks).
    Status read_host(std::uint64_t off, void* dst, std::uint64_t len);
    // Constant bank (constant0 window, 0x10000 bytes with params at 0x380).
    // Phase 7 debugger view+modify; bounds-checked against the window.
    Status read_constant(std::uint64_t off, void* dst, std::uint64_t len) const;
    Status write_constant(std::uint64_t off, const void* src,
                          std::uint64_t len);
    // Reference the caller-owned global backing (stores become visible to the
    // launcher after the run).
    void set_global_backing(std::vector<std::uint8_t>* backing);
    // CTA shared window base VA (for SASS shared addressing).
    DevicePtr cta_shared_base(std::uint64_t cta_id) const;

    // --- SASS loads ---------------------------------------------------------
    // LDG: descriptor + Ra(64) + signed offset -> global.  `out` receives the
    // sign/zero-extended register value (width from `w`), up to 4 words.
    Status ldg(DevicePtr desc, std::uint64_t addr, std::int64_t offset,
               MemWidthInfo w, MemValue& out);
    // LDS: shared offset (+stride) reads from the CTA shared buffer.
    static Status lds(const std::vector<std::uint8_t>& shared,
                      std::uint64_t off, std::int64_t disp, MemWidthInfo w,
                      MemValue& out);
    // LDC: constant bank + offset.
    Status ldc(std::uint64_t bank, std::uint64_t off, MemWidthInfo w,
               MemValue& out);

    // --- SASS stores --------------------------------------------------------
    Status stg(DevicePtr desc, std::uint64_t addr, std::int64_t offset,
               MemWidthInfo w, const MemValue& in);
    // STS writes into the CTA shared buffer.
    static Status sts(std::vector<std::uint8_t>& shared, std::uint64_t off,
                      std::int64_t disp, MemWidthInfo w, const MemValue& in);

    // --- atomics ------------------------------------------------------------
    // Global atomic RMW (returns the pre-operation value in `old`).  Widths
    // {1,2,4,8} are supported; width 16 (128-bit atomic) is a structured
    // error (never a truncated 64-bit RMW).  `cmp` is the compare operand for
    // kCas (compare-and-swap); it is ignored for every other op.
    Status atom_global(std::uint64_t addr, std::uint64_t width, AtomicOp op,
                       const MemValue& operands, MemValue& old,
                       const MemValue* cmp = nullptr);
    // Shared atomic RMW on the CTA shared buffer (widths {1,2,4,8}; 16 ->
    // structured error).  `cmp` carries the kCas compare operand.
    static Status atom_shared(std::vector<std::uint8_t>& shared,
                              std::uint64_t off, std::uint64_t width,
                              AtomicOp op, const MemValue& operands,
                              MemValue& old, const MemValue* cmp = nullptr);

    // --- fences / barriers (logical; no-op in functional step 1) -------------
    void membar();  // ordering barrier: functional no-op (single-writer model)
    void fence();   // fence: functional no-op

    // --- pending ops (logical scoreboard) -----------------------------------
    // Record an in-flight op so DEPBAR/wait in a correct program can observe
    // completion.  Step 1 completes ops immediately (memory is synchronous)
    // but keeps the count for group-based DEPBAR.
    void commit_group();                       // cp.async.commit_group
    void drain();                              // wait_all / DEPBAR.LE ,0
    std::uint64_t pending_groups() const { return groups_.size(); }
    std::size_t pending_ops(std::uint64_t group) const;

    // --- diagnostics ----------------------------------------------------------
    std::uint64_t total_global_reads() const { return reads_; }
    std::uint64_t total_global_writes() const { return writes_; }

private:
    Status read_global(std::uint64_t va, MemWidthInfo w, MemValue& out);
    MemoryAllocator alloc_;
    std::vector<std::uint8_t> params_;
    // Host-visible global backing (owned by the caller; MemoryService
    // references it so stores are visible to the launcher after the run).
    std::vector<std::uint8_t>* global_ = nullptr;
    std::uint64_t global_size_ = 0;
    std::vector<std::uint8_t> constant_;
    DevicePtr global_base_ = DevicePtr{0};
    // Serializes global read/write/atomic (Step 2 parallel workers).
    mutable std::mutex global_mutex_;
    // Serializes allocation bookkeeping (register_cta_shared / warp_local /
    // setup_global) across parallel worker constructors.
    mutable std::mutex setup_mutex_;
    // Per-CTA shared windows (cta_id -> allocation id + base + bytes).
    struct SharedWindow {
        AllocationId id;
        DevicePtr base;
        std::uint64_t size = 0;
    };
    std::vector<SharedWindow> shared_;
    // Pending op groups (logical scoreboard).
    std::vector<std::vector<PendingMemOp>> groups_;
    std::uint64_t reads_ = 0;
    std::uint64_t writes_ = 0;
};

// Convert a memory access Error into a Fault with the right kind.
Fault memory_error_to_fault(const Error& e, std::uint64_t pc,
                            std::uint32_t warp);

}  // namespace semu
