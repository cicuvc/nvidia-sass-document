#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <optional>
#include <span>
#include <string>
#include <vector>

#include <semu/cluster.hpp>
#include <semu/cubin.hpp>
#include <semu/memory.hpp>
#include <semu/status.hpp>

// FROZEN (SIM_PLAN Phase 10): this header holds the public launch ABI
// (Context / Module / Function / LaunchConfig / LaunchResult / KernelArg) and
// the backend contracts a future JIT plugs into:
//
//   - IBackend + BackendLaunchRequest        -> kBackendApiVersion
//   - IRuntimeServices                       -> kRuntimeServicesVersion
//   - IEventSink / BasicMemoryEvent / EventKind -> kEventStreamVersion
//
// (api.hpp).  Adding a real JIT backend must not require changing the cubin
// loader, this launch API, the memory model, the debugger or the profiler
// schema (Phase 10 exit criterion).  The async/TMA extension points are
// reserved below in a versioned, documentation-only section: they are NOT
// implemented yet and MUST NOT be added as new purely-virtual methods to
// IRuntimeServices itself (that would break every existing implementor).

// Runtime services: Context / Module / Function / LaunchConfig /
// LaunchResult and the IBackend interface (SIM_PLAN Phase 3).
//
// Phase 3 delivers the launch ABI: per-item KernelArg and packed parameter
// buffers are converted into constant0 contents exactly as the sm120 driver
// would (KPARAM ordinal/offset/size, param base 0x380, preset slots), and
// Context owns the virtual address space + constant banks.  Instruction
// execution is Phase 4 (IBackend); launching validates and prepares a
// launch, then hands it to the backend.

namespace semu {

// ---------------------------------------------------------------------------
// Kernel arguments
// ---------------------------------------------------------------------------

// One kernel argument.  The launch API accepts either a fully packed
// parameter buffer (see LaunchConfig::packed_params) or a per-item list of
// KernelArg; both must produce byte-identical constant0 contents.
struct KernelArg {
    enum class Kind : std::uint8_t {
        kPointer,   // DevicePtr, 8 bytes
        kInt,       // signed/unsigned scalar <= 8 bytes
        kFloat,     // IEEE-754 bit pattern <= 8 bytes
        kBytes,     // raw bytes (structs / tensormaps / arrays)
    };

    Kind kind = Kind::kInt;
    std::uint64_t value = 0;          // scalar payload (bit pattern)
    std::vector<std::uint8_t> payload;  // payload for kBytes
    std::string name;                 // optional, for diagnostics

    // Factories.
    static KernelArg pointer(DevicePtr p, std::string name = {});
    static KernelArg integer(std::uint64_t v, std::string name = {});
    static KernelArg floating(std::uint64_t bits, std::string name = {});
    static KernelArg raw(std::vector<std::uint8_t> b, std::string name = {});

    // Serialized byte width (0 for kBytes: bytes.size()).
    std::uint64_t width() const {
        if (kind == Kind::kBytes) return payload.size();
        return 8;  // scalars are stored 8 bytes, truncated on pack
    }
};

// ---------------------------------------------------------------------------
// Launch configuration
// ---------------------------------------------------------------------------

struct LaunchConfig {
    std::uint32_t grid_x = 1, grid_y = 1, grid_z = 1;
    std::uint32_t block_x = 1, block_y = 1, block_z = 1;
    // Static shared memory already declared in the cubin is auto-sized;
    // `extra_shared` adds dynamic shared (Phase 3 models the bytes, the
    // interpreter consumes it later).
    std::uint64_t extra_shared = 0;

    // Overflow-checked product (P3-GAP-08 / reviewer round 3).
    StatusOr<std::uint64_t> grid_threads() const {
        const std::uint64_t x = grid_x, y = grid_y, z = grid_z;
        if (x != 0 && y > UINT64_MAX / x) {
            return StatusOr<std::uint64_t>::failure(Error::out_of_range(
                "grid dims overflow (grid_x*grid_y)"));
        }
        const std::uint64_t xy = x * y;
        if (xy != 0 && z > UINT64_MAX / xy) {
            return StatusOr<std::uint64_t>::failure(Error::out_of_range(
                "grid dims overflow (grid_x*grid_y*grid_z)"));
        }
        return StatusOr<std::uint64_t>::success(xy * z);
    }
    StatusOr<std::uint64_t> block_threads() const {
        const std::uint64_t x = block_x, y = block_y, z = block_z;
        if (x != 0 && y > UINT64_MAX / x) {
            return StatusOr<std::uint64_t>::failure(Error::out_of_range(
                "block dims overflow"));
        }
        const std::uint64_t xy = x * y;
        if (xy != 0 && z > UINT64_MAX / xy) {
            return StatusOr<std::uint64_t>::failure(Error::out_of_range(
                "block dims overflow"));
        }
        return StatusOr<std::uint64_t>::success(xy * z);
    }
};

// Per-CTA shared window view handed to backends (P3-GAP-07 multi-CTA):
// every CTA of the launch gets an explicit entry — backends must NOT derive
// addresses by arithmetic (the allocator re-aligns each allocation).
struct CtaSharedView {
    std::uint64_t cta_linear_id = 0;  // 0..grid_threads()-1
    DevicePtr base{};
    std::uint64_t size = 0;
    std::string domain;               // e.g. "cta:<id>"
};

// Result of a launch: the prepared state handed to the backend.  In Phase 3
// this is the parameter bank image + shared-window metadata.  NOTE: the CTA
// shared allocations are reclaimed when launch() returns (the backend runs
// synchronously), so the LaunchResult does NOT expose live/owning shared
// pointers — the diagnostic addresses in shared_views are dead by the time
// the caller sees the result (they identify which window each CTA had, for
// debugging, and must not be dereferenced).  Phase 4's asynchronous launch
// handle will own the windows instead.
struct LaunchResult {
    // Parameter bank: the exact constant0 image for the launch.
    ConstantBankLayout layout;
    std::vector<std::uint8_t> param_bank;
    std::string kernel_name;
    LaunchConfig config;
    // Diagnostic per-CTA shared metadata (domains + sizes).  These are
    // NOT live/owning pointers: the allocations are freed before launch()
    // returns; the addresses identify which window each CTA had and must
    // not be dereferenced.
    std::vector<CtaSharedView> shared_views;
    // True when the launch declared shared memory.
    bool has_shared = false;
};

// ---------------------------------------------------------------------------
// IBackend: the interface the interpreter uses to touch runtime services.
// All memory access goes through the runtime; backends never reach into
// private simulator state.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Runtime services: the controlled memory/launch surface handed to
// backends.  All device memory access from an interpreter/JIT must go
// through this interface — never reach into private simulator state.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Event / fault channel (SIM_PLAN "memory and event system"): the
// interpreter emits events through this interface.  This is the Phase 3
// *basic* event record (BasicMemoryEvent) — it carries the core access
// fields so the channel ABI is usable, but it is explicitly NOT the
// finalized SIM_PLAN normalized MemoryEvent (event/launch IDs, SM/CTA/warp,
// active lanes, per-lane byte ranges, cache/operator modifiers, atomic
// order/scope, L1/L2 parents land with the Phase 8 profiler).  The sink
// interface and emit protocol are stable; the record type will be extended,
// not replaced, in Phase 8.
//
// FROZEN (SIM_PLAN Phase 10, kEventStreamVersion in api.hpp): the Phase 8
// normalized stream lives in memory_events.hpp and the profiler schema is
// locked by profiler::kReportSchemaVersion.  The interpreter PRODUCES the
// stream; analyzers SUBSCRIBE; producing/consuming never feeds back into
// execution.
// ---------------------------------------------------------------------------

enum class EventKind : std::uint8_t {
    kMemoryAccess = 0,  // typed access (carries DeviceAccess + PC)
    kMemoryFault = 1,   // rejected access (error code + reason)
    kInstruction = 2,   // instruction executed (PC + mnemonic)
    kBarrier = 3,       // barrier arrival/leave
    kLaunch = 4,        // launch begin/end
    kFault = 5,         // simulator fault (FaultKind + report)
};

struct BasicMemoryEvent {
    EventKind kind = EventKind::kMemoryAccess;
    std::uint64_t pc = 0;            // kernel-relative PC
    DevicePtr address{};
    std::uint64_t width = 0;
    AddressSpace space = AddressSpace::kGlobal;
    AccessKind access_kind = AccessKind::kLoad;
    std::string domain;              // accessing domain (cta/warp)
    bool write = false;
    // Shared/DSMEM identity (Phase 3.5): populated for shared-space events.
    SharedAccessMode shared_mode = SharedAccessMode::kLocal;
    std::uint64_t source_cta = 0;    // grid-linear source CTA
    std::uint64_t cluster_id = 0;    // cluster-linear id (0 when disabled)
    std::uint64_t target_rank = 0;   // cluster-internal target rank
    std::uint64_t target_cta = 0;    // grid-linear target CTA
    std::uint64_t logical_address = 0;  // DSMEM logical address (rank<<24|off)
    AllocationId allocation;         // target shared allocation id
    std::uint64_t allocation_offset = 0;
    // For kMemoryFault / kFault:
    ErrorCode error = ErrorCode::kNone;
    std::string reason;
};

class IEventSink {
public:
    virtual ~IEventSink() = default;
    // Called by the runtime on every event; must not block or re-enter the
    // runtime.  Returns false to stop event delivery (e.g. debugger
    // breakpoint).
    virtual bool emit(const BasicMemoryEvent& event) = 0;
};

class IRuntimeServices {
public:
    virtual ~IRuntimeServices() = default;

    // Device memory (full lifecycle / bounds / address-space checks).
    virtual Status write(DevicePtr ptr, const void* src, std::uint64_t len) = 0;
    virtual Status read(DevicePtr ptr, void* dst, std::uint64_t len) = 0;
    virtual Status memset(DevicePtr ptr, int value, std::uint64_t len) = 0;
    virtual Status copy(DevicePtr dst, DevicePtr src, std::uint64_t len) = 0;
    virtual Status read_typed(DevicePtr ptr, void* dst, std::uint64_t len,
                              const DeviceAccess& access) = 0;
    virtual Status write_typed(DevicePtr ptr, const void* src,
                               std::uint64_t len,
                               const DeviceAccess& access) = 0;

    // Constant bank of the running kernel (read-only view of the launch
    // bank).  Returns empty span when the kernel has no bank.
    virtual std::span<const std::uint8_t> constant_bank(
        const std::string& kernel_name) const = 0;

    // Event channel (SIM_PLAN "memory and event system").  Returns false
    // when the sink asks to stop (debugger breakpoint).  Shared-access
    // events are emitted AFTER the memory commit; a sink stop does not
    // roll back the access — it suppresses subsequent events and is
    // observable via event_stopped().
    virtual bool emit_event(const BasicMemoryEvent& event) = 0;
    // Install/replace the event sink (nullptr detaches).
    virtual void set_event_sink(IEventSink* sink) = 0;
    // True once the sink returned false (breakpoint): further events are
    // suppressed.  Memory side effects already happened.
    virtual bool event_stopped() const = 0;

    // --- Cluster DSMEM (Phase 3.5) ---------------------------------------
    // Translate a shared logical address for `source_cta` under the given
    // mode.  kLocal: no rank bits, target == source.  kDistributed: rank =
    // address[31:24], offset = address[23:0]; the cluster must be enabled,
    // the rank must exist, and source/target must share a cluster.  The
    // result is the ONLY sanctioned way for a backend to reach a peer CTA's
    // shared window — backends must never decode (rank << 24) themselves.
    // `access` supplies width/alignment/space/kind; alignment and the
    // atomic width gate are validated here, before the address is handed
    // out (reviewer round 1).
    virtual StatusOr<TranslatedSharedAddress> translate_shared(
        std::uint64_t source_cta, std::uint64_t logical_address,
        const DeviceAccess& access, SharedAccessMode mode) = 0;

    // Authorized shared access through a translation.  The launch
    // generation token and every identity field are revalidated; a forged
    // or stale translation is rejected before any memory is touched.
    // `dst`/`src` must be `addr.width` bytes.
    virtual Status read_shared(const TranslatedSharedAddress& addr,
                               void* dst) = 0;
    virtual Status write_shared(const TranslatedSharedAddress& addr,
                                const void* src) = 0;

    // DSMEM read-modify-write atomic on a translation.  `op` selects the
    // RMW operation; 1/2/4/8-byte widths only (the Phase 3 atomic gate).
    // `value` holds the operand (low bytes used); the pre-RMW value is
    // returned in `old` (may be null).  Emits an atomic event.
    virtual Status atomic_shared(const TranslatedSharedAddress& addr,
                                 AtomicOp op, const void* value,
                                 void* old) = 0;

    // Read-only cluster topology of the running launch (empty when the
    // kernel has no cluster metadata).
    virtual const ClusterTopology& shared_topology() const = 0;
};

// ---------------------------------------------------------------------------
// Phase 10 reserved async / TMA extension points (VERSIONED, documentation
// only — NOT implemented, NOT part of kRuntimeServicesVersion surface yet).
//
// The forward declaration below turns the pure-comment reservation into a
// real (compile-time) part of the frozen header surface: backends and tests
// can reference the `IRuntimeServicesV2` type (e.g. a capability query /
// safe_downcast check) even though no implementation exists yet.  The
// concrete ABI lands in a future phase and MUST be declared here, never as
// new purely-virtual methods on IRuntimeServices itself (that would break
// every existing implementor).
struct IRuntimeServicesV2;
//
// When a future phase moves TMA from decode-only to functional it MUST add
// these as members of a NEW versioned extension interface (e.g.
// `IRuntimeServicesV2 : IRuntimeServices` or a standalone
// `IAsyncRuntimeServices` the Context opts into via a cast/query), so the
// frozen kRuntimeServicesVersion=1 ABI above stays source- and
// binary-compatible for existing backends (mock backend, tests, interpreters).
//
// The current interpreter's async/TMA state is fully synchronous: cp.async
// (LDGSTS) copies land immediately, TMA tile transfers are expanded
// synchronously, and mbarrier phase flips are computed logically.  The
// reserved shapes below are what a timing-aware / GPU-completion-observable
// semantics would publish; their exact signatures are NOT frozen yet.
//
//   // Completion/commit callbacks — an async transfer completing reports its
//   // identity + byte count so the runtime can mirror commit accounting.
//   //   void set_async_completion_sink(AsyncCompletionSink* sink);
//   //   struct AsyncCompletion { std::uint64_t group; std::uint64_t bytes;
//   //                            std::uint64_t pc; std::string kind; };
//   //   class AsyncCompletionSink {
//   //       virtual ~AsyncCompletionSink() = default;
//   //       virtual void on_commit(const AsyncCompletion& c) = 0;
//   //       virtual void on_error(const AsyncCompletion& c,
//   //                             const Error& e) = 0;
//   //   };
//
//   // mbarrier state query — read the logical phase/arrive/expected/tx state
//   // of an mbarrier at a shared byte offset (the interpreter's current
//   // synchronous model already computes this internally; a JIT/TMA engine
//   // would need the query to NOT carry a functional copy of the state).
//   //   struct MbarrierSnapshot {
//   //       std::uint32_t phase; std::uint32_t arrive; std::uint32_t expected;
//   //       std::int64_t tx; bool locked; bool corrupted;
//   //   };
//   //   StatusOr<MbarrierSnapshot> query_mbarrier(std::uint64_t cta_id,
//   //                                             std::uint32_t shared_off);
//
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// IBackend: the interface the interpreter uses to run launches.  Backends
// are bound to a Context (and its runtime services) at creation; they must
// not bypass them.
//
// FROZEN (kBackendApiVersion in api.hpp): a future JIT backend implements
// exactly this surface.  The interpreter is the reference backend; the mock
// backend (mock_backend.hpp) exercises the contract for the JIT follow-up.
// ---------------------------------------------------------------------------

// Everything a backend needs to run one launch, handed as an immutable
// bundle (P3-GAP-03): the pre-decoded IR, launch config, the full
// materialized constant0 bank, and the shared window.
struct BackendLaunchRequest {
    std::string kernel_name;
    const Kernel* kernel = nullptr;     // pre-decoded IR (module-owned)
    LaunchConfig config;
    ConstantBankLayout layout;
    // Full constant0 bank image (params + preset slots + kernel seed).
    std::span<const std::uint8_t> constant_bank;
    // One entry per CTA (empty when the kernel declares no shared).
    std::span<const CtaSharedView> shared_views;
    // Read-only cluster topology (enabled only for cluster kernels); the
    // backend must use translate_shared, never re-derive ranks.
    const ClusterTopology* cluster = nullptr;
};

class IBackend {
public:
    virtual ~IBackend() = default;

    // Bind the backend to a Context's runtime services.  Called once by
    // Context::create before any launch; backends must use `services` for
    // every device access.
    virtual void bind_runtime(IRuntimeServices* services) = 0;

    // Run one launch.  The request's views are valid for the duration of
    // the call only; a backend that retains them must copy the data.
    virtual Status launch(const BackendLaunchRequest& request) = 0;

    // Backend capability string (for `semu --version` / inspection).
    virtual const char* name() const = 0;
};

// ---------------------------------------------------------------------------
// Context / Module / Function
// ---------------------------------------------------------------------------

class Context;

// Handle to a loaded cubin (owning the parsed Module + per-kernel metadata).
class RuntimeModule {
public:
    // Load a cubin byte image (strict mode; executable).
    static StatusOr<RuntimeModule> load(std::vector<std::uint8_t> cubin,
                                 const std::string& source_name = {});

    const std::string& source_name() const { return source_name_; }
    const semu::Module& impl() const { return *impl_; }
    const std::vector<Kernel>& kernels() const { return impl_->kernels(); }

    // Handle to the underlying module image (Functions keep this alive).
    std::shared_ptr<const semu::Module> handle() const { return impl_; }

private:
    RuntimeModule() = default;
    std::string source_name_;
    std::shared_ptr<const semu::Module> impl_;
};

// Handle to one kernel function inside a Module.
class Function {
public:
    Function(Function&&) = default;
    Function& operator=(Function&&) = default;
    Function(const Function&) = delete;
    Function& operator=(const Function&) = delete;

    const std::string& name() const { return name_; }
    const Kernel& kernel() const { return *kernel_; }
    // Parameter metadata (ordinal-sorted).
    const KernelMetadata& meta() const { return kernel_->meta; }
    // The module image this function lives in (kept alive by the handle).
    std::shared_ptr<const semu::Module> module() const { return module_; }

private:
    friend class Context;
    Function(std::string name, std::shared_ptr<const semu::Module> module,
             const Kernel* kernel)
        : name_(std::move(name)), module_(std::move(module)),
          kernel_(kernel) {}
    std::string name_;
    std::shared_ptr<const semu::Module> module_;  // keeps IR alive
    const Kernel* kernel_ = nullptr;
};

// The runtime context: address space, constant banks, loaded modules.
// Parameter buffer format for the packed-launch entry point (P3-GAP-05):
// a KPARAM-relative blob (params only, offsets within [0, max_end)) or a
// full constant0 bank image (params at param_base + KPARAM.offset).
enum class ParamPackFormat : std::uint8_t {
    kKparamBlob = 0,   // params only, KPARAM-relative offsets
    kFullBankImage = 1,  // full constant0 image (params + presets)
};

// ---------------------------------------------------------------------------
// Context-unique nonce allocation (codex round 4): a monotonic, never-
// reused counter claimed with a CAS loop.  At UINT64_MAX the next claim
// fails with kOutOfRange; 0 and UINT64_MAX are never handed out.  The class
// is standalone so exhaustion / race behavior is directly testable.
// ---------------------------------------------------------------------------
class NonceAllocator {
public:
    explicit NonceAllocator(std::uint64_t start = 1) : next_(start) {}

    // Claim the next nonce.  Fails kOutOfRange at exhaustion; never
    // returns 0 or a reused value.  Thread-safe.
    StatusOr<std::uint64_t> claim() {
        for (;;) {
            const std::uint64_t cur = next_.load(std::memory_order_relaxed);
            if (cur == UINT64_MAX) {
                return StatusOr<std::uint64_t>::failure(Error::out_of_range(
                    "context nonce space exhausted"));
            }
            std::uint64_t expected = cur;
            if (next_.compare_exchange_weak(
                    expected, cur + 1, std::memory_order_relaxed,
                    std::memory_order_relaxed)) {
                return StatusOr<std::uint64_t>::success(cur);
            }
        }
    }

    // TEST-ONLY: force the next value to be handed out (boundary tests).
    void debug_set(std::uint64_t value) {
        next_.store(value, std::memory_order_relaxed);
    }
    std::uint64_t debug_value() const {
        return next_.load(std::memory_order_relaxed);
    }

private:
    std::atomic<std::uint64_t> next_;
};

class Context : public IRuntimeServices {
public:
    static StatusOr<Context> create(
        std::shared_ptr<IBackend> backend = {});

    // --- modules / functions ---------------------------------------------
    StatusOr<RuntimeModule> load_module(std::vector<std::uint8_t> cubin,
                                 const std::string& source_name = {});
    // Find a kernel by mangled name.  The returned Function keeps the
    // module image alive (safe to destroy/move the RuntimeModule after).
    StatusOr<Function> function(const RuntimeModule& module,
                                const std::string& mangled_name) const;

    // --- launch -----------------------------------------------------------
    // Launch with per-item KernelArgs.  Packing follows the kernel's
    // KPARAM metadata (ordinal/offset/size); wrong argument count or
    // width is an error.  Pointer-typed args are validated against the
    // allocator (live global allocation; interior pointers allowed).
    StatusOr<LaunchResult> launch(const Function& fn,
                                  const LaunchConfig& config,
                                  const std::vector<KernelArg>& args);

    // Launch with a packed parameter buffer in an explicit format.
    StatusOr<LaunchResult> launch(const Function& fn,
                                  const LaunchConfig& config,
                                  const std::vector<std::uint8_t>& packed,
                                  ParamPackFormat format);

    // --- runtime services (IBackend-facing) ------------------------------
    Status write(DevicePtr ptr, const void* src, std::uint64_t len) override;
    Status read(DevicePtr ptr, void* dst, std::uint64_t len) override;
    Status memset(DevicePtr ptr, int value, std::uint64_t len) override;
    Status copy(DevicePtr dst, DevicePtr src, std::uint64_t len) override;
    Status read_typed(DevicePtr ptr, void* dst, std::uint64_t len,
                      const DeviceAccess& access) override;
    Status write_typed(DevicePtr ptr, const void* src, std::uint64_t len,
                       const DeviceAccess& access) override;
    std::span<const std::uint8_t> constant_bank(
        const std::string& kernel_name) const override;
    bool emit_event(const BasicMemoryEvent& event) override;
    void set_event_sink(IEventSink* sink) override { event_sink_ = sink; }
    bool event_stopped() const override { return event_stopped_; }
    StatusOr<TranslatedSharedAddress> translate_shared(
        std::uint64_t source_cta, std::uint64_t logical_address,
        const DeviceAccess& access, SharedAccessMode mode) override;
    Status read_shared(const TranslatedSharedAddress& addr,
                       void* dst) override;
    Status write_shared(const TranslatedSharedAddress& addr,
                        const void* src) override;
    Status atomic_shared(const TranslatedSharedAddress& addr, AtomicOp op,
                         const void* value, void* old) override;
    const ClusterTopology& shared_topology() const override;

    // --- memory services (interpreter-facing) ----------------------------
    MemoryAllocator& memory() { return allocator_; }
    const MemoryAllocator& memory() const { return allocator_; }
    // Per-kernel constant bank (the bank the launch writes params into).
    ConstantBank& constant_bank(const Function& fn);
    const ConstantBank& constant_bank(const Function& fn) const;

    // Backend (may be null in Phase 3; launch still prepares state).
    std::shared_ptr<IBackend> backend() const { return backend_; }

    // --- test hooks (codex review round 3) -------------------------------
    // TEST-ONLY: force the Context nonce / launch generation counters for
    // boundary tests.  Production code never uses these; they exist so the
    // token width and overflow paths can be probed deterministically
    // without 2^32 launches.
    void debug_set_counters(std::uint64_t nonce, std::uint64_t gen) {
        context_nonce_ = nonce;
        launch_count_ = gen;
    }
    std::uint64_t debug_nonce() const { return context_nonce_; }
    std::uint64_t debug_generation() const { return launch_count_; }
    // TEST-ONLY: swap the backend (allows re-launching the same Context
    // with a replay probe for generation-advance tests).
    void debug_set_backend(std::shared_ptr<IBackend> b) {
        backend_ = std::move(b);
    }

private:
    Context() = default;

    MemoryAllocator allocator_;
    // Banks keyed by mangled kernel name (each kernel gets its own
    // constant0 window as the driver would).
    std::vector<std::pair<std::string, ConstantBank>> banks_;
    std::shared_ptr<IBackend> backend_;
    IEventSink* event_sink_ = nullptr;
    // Context-local monotonic CTA domain counter (reviewer round 3): not a
    // global static, so multiple Contexts never share/race domain IDs.
    std::uint64_t next_cta_domain_ = 0;
    // Active-launch state (Phase 3.5): the cluster topology + per-CTA
    // shared views of the launch currently executing in the backend.  Only
    // valid during the synchronous backend_->launch call.
    ClusterTopology active_topology_;
    std::vector<CtaSharedView> active_views_;
    // Unforgeable authorization (reviewer round 2 + codex round 3): a
    // Context-unique nonce (drawn from a process-global monotonic counter
    // at create(), never reused) and a full 64-bit per-launch generation
    // that overflows to a structured error instead of wrapping.  Tokens
    // minted by another Context or by an earlier launch of this Context
    // are rejected even when allocation IDs / VAs / topology match exactly.
    std::uint64_t context_nonce_ = 0;
    std::uint64_t launch_count_ = 0;
    // Set when the event sink requested a stop; subsequent events are
    // suppressed (memory is already committed when events are emitted).
    bool event_stopped_ = false;

    ConstantBank* bank_for(const std::string& mangled);
    // Deterministic launch-time bank initialization (P3-GAP-09):
    // clear -> kernel .nv.constant0 seed -> ABI preset slots -> params.
    Status prepare_bank(const Function& fn, ConstantBank* bank);
    // Revalidate a translation against the active launch (token +
    // identity); forged/stale translations are rejected.
    Status validate_translation(const TranslatedSharedAddress& addr);
    // Emit a shared/DSMEM access event from a trusted translation.
    void emit_shared_event(const TranslatedSharedAddress& addr,
                           AccessKind kind, bool write, std::uint64_t pc);
};

}  // namespace semu
