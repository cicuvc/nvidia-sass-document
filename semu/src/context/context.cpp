// Runtime services implementation (SIM_PLAN Phase 3).
//
// Context owns the virtual address space and per-kernel constant banks.
// Launch converts per-item KernelArgs (or a packed buffer) into the exact
// constant0 image the sm120 driver would produce: each parameter lands at
// param_base + KPARAM.offset with the KPARAM size, and preset slots
// (SLOT_DEFAULT_CDESC at 0x358) are initialized.

#include <semu/context/context.hpp>

#include <algorithm>
#include <atomic>
#include <cstring>

namespace semu {

// ---------------------------------------------------------------------------
// KernelArg factories
// ---------------------------------------------------------------------------

KernelArg KernelArg::pointer(DevicePtr p, std::string name) {
    KernelArg a;
    a.kind = Kind::kPointer;
    a.value = p.va;
    a.name = std::move(name);
    return a;
}

KernelArg KernelArg::integer(std::uint64_t v, std::string name) {
    KernelArg a;
    a.kind = Kind::kInt;
    a.value = v;
    a.name = std::move(name);
    return a;
}

KernelArg KernelArg::floating(std::uint64_t bits, std::string name) {
    KernelArg a;
    a.kind = Kind::kFloat;
    a.value = bits;
    a.name = std::move(name);
    return a;
}

KernelArg KernelArg::raw(std::vector<std::uint8_t> b, std::string name) {
    KernelArg a;
    a.kind = Kind::kBytes;
    a.payload = std::move(b);
    a.name = std::move(name);
    return a;
}

// ---------------------------------------------------------------------------
// RuntimeModule
// ---------------------------------------------------------------------------

StatusOr<RuntimeModule> RuntimeModule::load(std::vector<std::uint8_t> cubin,
                                            const std::string& source_name) {
    auto impl = semu::Module::load(std::move(cubin));
    if (impl.failed()) {
        return StatusOr<RuntimeModule>::failure(impl.take_error());
    }
    RuntimeModule m;
    m.source_name_ = source_name;
    m.impl_ = std::make_shared<semu::Module>(std::move(impl.value()));
    return StatusOr<RuntimeModule>::success(std::move(m));
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

namespace {

// Process-global nonce source (single instance shared by all Contexts).
NonceAllocator& context_nonce_source() {
    static NonceAllocator alloc;
    return alloc;
}

}  // namespace

StatusOr<Context> Context::create(std::shared_ptr<IBackend> backend) {
    Context ctx;
    ctx.backend_ = std::move(backend);
    // Context-unique nonce from a process-global monotonic counter: never
    // reused, so a token minted by another Context can never validate here.
    // The counter is claimed with a CAS loop and never wraps: at
    // UINT64_MAX the next allocation fails with kOutOfRange instead of
    // reusing a historical nonce or handing out 0 (codex round 3/4).
    auto nonce = context_nonce_source().claim();
    if (nonce.failed()) {
        return StatusOr<Context>::failure(nonce.take_error());
    }
    ctx.context_nonce_ = nonce.value();
    return StatusOr<Context>::success(std::move(ctx));
}

StatusOr<RuntimeModule> Context::load_module(
    std::vector<std::uint8_t> cubin, const std::string& source_name) {
    return RuntimeModule::load(std::move(cubin), source_name);
}

StatusOr<Function> Context::function(const RuntimeModule& module,
                                     const std::string& mangled_name) const {
    const Kernel* k = module.impl().find_kernel(mangled_name);
    if (!k) {
        return StatusOr<Function>::failure(Error::not_found(
            "kernel '" + mangled_name + "' not found in module '" +
            module.source_name() + "'"));
    }
    return StatusOr<Function>::success(
        Function(mangled_name, module.handle(), k));
}

ConstantBank* Context::bank_for(const std::string& mangled) {
    for (auto& [name, bank] : banks_) {
        if (name == mangled) return &bank;
    }
    banks_.emplace_back(mangled, ConstantBank{});
    return &banks_.back().second;
}

ConstantBank& Context::constant_bank(const Function& fn) {
    return *bank_for(fn.name());
}

const ConstantBank& Context::constant_bank(const Function& fn) const {
    for (const auto& [name, bank] : banks_) {
        if (name == fn.name()) return bank;
    }
    static const ConstantBank kEmpty{};
    return kEmpty;
}

// ---------------------------------------------------------------------------
// Parameter packing
// ---------------------------------------------------------------------------

namespace {

// Serialize one KernelArg into `out` (byte vector) with the target width.
// Scalars (int/float/pointer) pack to the parameter width by taking the
// low `width` bytes (natural C++ narrowing); kBytes must match the width
// exactly (an explicit-size arg never silently truncates).
Status pack_arg(const KernelArg& arg, std::uint64_t width,
                std::vector<std::uint8_t>* out) {
    std::vector<std::uint8_t> blob;
    switch (arg.kind) {
        case KernelArg::Kind::kPointer:
        case KernelArg::Kind::kInt:
        case KernelArg::Kind::kFloat:
            blob.resize(8, 0);
            for (std::size_t i = 0; i < 8; ++i) {
                blob[i] = static_cast<std::uint8_t>((arg.value >> (8 * i)) & 0xff);
            }
            // Truncate to the parameter width (low bytes) when narrower.
            blob.resize(static_cast<std::size_t>(width), 0);
            break;
        case KernelArg::Kind::kBytes:
            blob = arg.payload;
            if (blob.size() != width) {
                return Status::failure(Error::invalid_argument(
                    "argument '" + (arg.name.empty() ? "?" : arg.name) +
                    "' is " + std::to_string(blob.size()) +
                    " bytes wide but the kernel parameter is " +
                    std::to_string(width) + " bytes"));
            }
            break;
    }
    out->insert(out->end(), blob.begin(), blob.end());
    return Status::success();
}

// Validate pointer-typed args against the allocator (P3-GAP-02): the VA
// must fall inside a *live* allocation, in the *global* address space
// (the only space host launch API may pass), and may be an interior
// pointer.  Failures carry kernel/ordinal/VA/reason and happen before any
// backend call.
Status validate_pointer_arg(const MemoryAllocator& allocator,
                            const std::string& kernel,
                            std::uint32_t ordinal,
                            const KernelArg& arg) {
    const DevicePtr p{arg.value};
    auto r = allocator.resolve_range(p, 1);
    if (r.failed()) {
        return Status::failure(Error(
            r.take_error().code(),
            "kernel '" + kernel + "' parameter " + std::to_string(ordinal) +
                " ('" + (arg.name.empty() ? "?" : arg.name) +
                "'): device pointer 0x" + std::to_string(p.va) +
                " is not a valid live allocation",
            Error::invalid_argument("")));
    }
    if (r.value().alloc.space != AddressSpace::kGlobal) {
        return Status::failure(Error(
            ErrorCode::kBadAddress,
            "kernel '" + kernel + "' parameter " + std::to_string(ordinal) +
                " ('" + (arg.name.empty() ? "?" : arg.name) +
                "'): device pointer 0x" + std::to_string(p.va) +
                " targets " + to_string(r.value().alloc.space) +
                " allocation; host launch API may only pass global",
            Error::invalid_argument("")));
    }
    return Status::success();
}

// Lay out args by KPARAM ordinal into a packed buffer covering
// [0, max_offset+max_size).
StatusOr<std::vector<std::uint8_t>> pack_args_by_kparam(
    const MemoryAllocator& allocator, const std::string& kernel_name,
    const KernelMetadata& meta, const std::vector<KernelArg>& args) {
    std::vector<std::uint8_t> buf;
    std::uint64_t end = 0;
    if (args.size() != meta.params.size()) {
        return StatusOr<std::vector<std::uint8_t>>::failure(
            Error::invalid_argument(
                "argument count " + std::to_string(args.size()) +
                " does not match kernel parameter count " +
                std::to_string(meta.params.size())));
    }
    for (std::size_t i = 0; i < args.size(); ++i) {
        const KernelParam* p = meta.param_by_ordinal(
            static_cast<std::uint32_t>(i));
        if (!p) {
            // ABI hole: ordinals are not dense.  Locate the param matching
            // this arg position by ordinal order instead.
            if (i < meta.params.size() && meta.params[i].ordinal == i) {
                p = &meta.params[i];
            } else {
                return StatusOr<std::vector<std::uint8_t>>::failure(
                    Error::invalid_argument(
                        "kernel has a parameter ordinal hole at " +
                        std::to_string(i) + "; use packed buffer or "
                        "ordinal-matching args"));
            }
        }
        // P3-GAP-02: pointer-typed args go through allocator validation.
        if (args[i].kind == KernelArg::Kind::kPointer) {
            Status pst = validate_pointer_arg(
                allocator, kernel_name, p->ordinal, args[i]);
            if (pst.failed()) {
                return StatusOr<std::vector<std::uint8_t>>::failure(
                    pst.take_error());
            }
        }
        std::vector<std::uint8_t> blob;
        Status st = pack_arg(args[i], p->size, &blob);
        if (st.failed()) {
            return StatusOr<std::vector<std::uint8_t>>::failure(
                st.take_error());
        }
        if (buf.size() < p->offset + p->size) {
            buf.resize(p->offset + p->size, 0);
        }
        std::memcpy(buf.data() + p->offset, blob.data(),
                    static_cast<std::size_t>(p->size));
        end = std::max(end, static_cast<std::uint64_t>(p->offset + p->size));
    }
    return StatusOr<std::vector<std::uint8_t>>::success(std::move(buf));
}

}  // namespace

// Deterministic launch-time constant0 initialization (P3-GAP-09):
//   1. clear the whole bank;
//   2. seed the kernel's .nv.constant0.<name> initial image (if any);
//   3. write the ABI preset slots (SLOT_DEFAULT_CDESC);
//   4. write params (caller).
Status Context::prepare_bank(const Function& fn, ConstantBank* bank) {
    bank->clear();
    // Kernel constant0 initial image from the loader association.
    if (fn.kernel().constant0 && !fn.kernel().constant0->nobits) {
        const auto& mod = fn.module();
        if (mod) {
            auto view = mod->section_view(fn.kernel().constant0->section_index);
            if (!view.empty()) {
                std::vector<std::uint8_t> image(view.begin(), view.end());
                Status sst = bank->seed_from(image);
                if (sst.failed()) return sst;
            }
        }
    }
    // Preset slots (sm120 ABI).  SLOT_DEFAULT_CDESC: the driver plants a
    // global-address-space descriptor here; we store a canonical zero
    // placeholder (Phase 6 refines the real descriptor semantics).
    const std::uint64_t default_cdesc = 0;
    Status st = bank->write_slot(bank->layout().default_cdesc_offset,
                                 &default_cdesc, 8);
    if (st.failed()) return st;
    return Status::success();
}

StatusOr<LaunchResult> Context::launch(const Function& fn,
                                       const LaunchConfig& config,
                                       const std::vector<KernelArg>& args) {
    auto packed = pack_args_by_kparam(allocator_, fn.name(), fn.meta(), args);
    if (packed.failed()) {
        return StatusOr<LaunchResult>::failure(packed.take_error());
    }
    return launch(fn, config, packed.value(), ParamPackFormat::kKparamBlob);
}

StatusOr<LaunchResult> Context::launch(
    const Function& fn, const LaunchConfig& config,
    const std::vector<std::uint8_t>& packed, ParamPackFormat format) {
    const KernelMetadata& meta = fn.meta();

    // Full 64-bit launch generation overflow -> structured error, checked
    // BEFORE any shared allocation / domain reservation / active-state
    // modification (codex round 3): an exhausted Context never leaks
    // allocations or leaves stale active-launch state behind.
    if (launch_count_ == UINT64_MAX) {
        return StatusOr<LaunchResult>::failure(Error::out_of_range(
            "launch generation counter exhausted"));
    }

    // Validate the packed buffer against KPARAM layout: every parameter
    // must be fully covered by the buffer.
    std::uint64_t max_end = 0;
    for (const auto& p : meta.params) {
        const std::uint64_t end = static_cast<std::uint64_t>(p.offset) + p.size;
        if (format == ParamPackFormat::kKparamBlob && end > packed.size()) {
            return StatusOr<LaunchResult>::failure(Error::invalid_argument(
                "packed parameter buffer is " + std::to_string(packed.size()) +
                " bytes but parameter ordinal " +
                std::to_string(p.ordinal) + " needs " + std::to_string(end) +
                " bytes"));
        }
        max_end = std::max(max_end, end);
    }

    ConstantBank* bank = bank_for(fn.name());
    ConstantBankLayout layout = bank->layout();

    // Deterministic bank init: clear + kernel const0 seed + preset slots.
    Status st = prepare_bank(fn, bank);
    if (st.failed()) return StatusOr<LaunchResult>::failure(st.take_error());

    if (format == ParamPackFormat::kFullBankImage) {
        // Full image: params are at param_base + KPARAM.offset inside the
        // image; the image must cover [0, param_base + max_end).
        const std::uint64_t need = layout.param_base + max_end;
        if (packed.size() < need) {
            return StatusOr<LaunchResult>::failure(Error::invalid_argument(
                "constant bank image is " + std::to_string(packed.size()) +
                " bytes but needs " + std::to_string(need) +
                " to cover all parameters"));
        }
        st = bank->seed_from(packed);
        if (st.failed()) {
            return StatusOr<LaunchResult>::failure(st.take_error());
        }
        // Preset slots come from the image (caller-controlled); do not
        // overwrite them after seeding.
    } else {
        // KPARAM-relative blob: params at param_base + KPARAM.offset.
        // Guard the empty-params case (nullptr + len 0 is UB even with a
        // zero size).
        if (max_end > 0) {
            st = bank->write_param(0, packed.data(), max_end);
            if (st.failed()) {
                return StatusOr<LaunchResult>::failure(st.take_error());
            }
        }
    }

    // Static shared window: one allocation PER CTA (P3-GAP-07).  Overflow-
    // safe sum (P3-GAP-08) and overflow-checked grid dims.
    if (config.extra_shared > UINT64_MAX - meta.static_shared) {
        return StatusOr<LaunchResult>::failure(Error::out_of_range(
            "shared size overflow: static " +
            std::to_string(meta.static_shared) + " + extra " +
            std::to_string(config.extra_shared)));
    }
    const std::uint64_t shared_size = meta.static_shared + config.extra_shared;
    // Validate BOTH grid and block products before any shared allocation or
    // backend call (reviewer round 4).  Zero dimensions are rejected (CUDA
    // style); the sm120 block-thread hardware cap (1024) is enforced here
    // as capability validation, not silently accepted.
    if (config.grid_x == 0 || config.grid_y == 0 || config.grid_z == 0 ||
        config.block_x == 0 || config.block_y == 0 ||
        config.block_z == 0) {
        return StatusOr<LaunchResult>::failure(Error::invalid_argument(
            "launch dimensions must be non-zero "
            "(grid=(" + std::to_string(config.grid_x) + "," +
            std::to_string(config.grid_y) + "," +
            std::to_string(config.grid_z) + ") block=(" +
            std::to_string(config.block_x) + "," +
            std::to_string(config.block_y) + "," +
            std::to_string(config.block_z) + "))"));
    }
    auto grid = config.grid_threads();
    if (grid.failed()) {
        return StatusOr<LaunchResult>::failure(grid.take_error());
    }
    auto block = config.block_threads();
    if (block.failed()) {
        return StatusOr<LaunchResult>::failure(block.take_error());
    }
    // sm120 block-thread capability cap (1024 threads per block).
    if (block.value() > 1024) {
        return StatusOr<LaunchResult>::failure(Error::invalid_argument(
            "block thread count " + std::to_string(block.value()) +
            " exceeds the sm120 cap of 1024"));
    }
    const std::uint64_t nctas = grid.value();

    // Cluster topology (Phase 3.5): from the kernel's declared cluster
    // metadata + the launch grid.  A cluster launch with an invalid
    // topology fails before any allocation / backend call.
    auto topo = ClusterTopology::build(fn.meta().cluster_dims, config.grid_x,
                                       config.grid_y, config.grid_z);
    if (topo.failed()) {
        return StatusOr<LaunchResult>::failure(topo.take_error());
    }
    const ClusterTopology& topology = topo.value();

    // RAII launch-state guard (codex round 3): every exit path — success,
    // backend failure, early error after this point — clears the active
    // launch state and frees the CTA shared allocations exactly once.
    // The launch generation is reserved (incremented) here, after all
    // validation and before any mutable launch state is installed.
    struct LaunchGuard {
        Context* ctx;
        std::vector<DevicePtr> bases;
        ~LaunchGuard() {
            ctx->active_topology_ = ClusterTopology{};
            ctx->active_views_.clear();
            for (const auto& b : bases) {
                ctx->allocator_.free(b);
            }
        }
    } guard{this, {}};
    auto free_later = [&](DevicePtr b) { guard.bases.push_back(b); };

    // Context-local, overflow-checked CTA domain range reservation.  The
    // whole range is reserved before any allocation so a mid-launch failure
    // never reuses IDs (reviewer round 3).
    std::vector<CtaSharedView> shared_views;
    if (shared_size > 0) {
        if (nctas > UINT64_MAX - next_cta_domain_) {
            return StatusOr<LaunchResult>::failure(Error::out_of_range(
                "CTA domain id space exhausted"));
        }
        const std::uint64_t domain_base = next_cta_domain_;
        next_cta_domain_ += nctas;
        for (std::uint64_t c = 0; c < nctas; ++c) {
            const std::string owner =
                "cta:" + std::to_string(domain_base + c);
            auto alloc = allocator_.allocate(AddressSpace::kShared,
                                             shared_size, 1024, owner);
            if (alloc.failed()) {
                // Roll back the CTAs allocated so far (the reserved ID
                // range is not rewound: IDs are never reused).  The guard
                // frees them on scope exit.
                return StatusOr<LaunchResult>::failure(alloc.take_error());
            }
            free_later(alloc.value());
            CtaSharedView v;
            v.cta_linear_id = c;
            v.base = alloc.value();
            v.size = shared_size;
            v.domain = owner;
            shared_views.push_back(std::move(v));
        }
    }

    LaunchResult res;
    res.layout = layout;
    res.param_bank = bank->raw();
    res.kernel_name = fn.name();
    res.config = config;
    res.shared_views = shared_views;
    res.has_shared = !shared_views.empty();

    // Hand to the backend (Phase 4 implements execution; a null backend
    // still produces the prepared launch).  Bind the runtime services to
    // THIS Context instance at launch time (create() returns by value, so
    // an early bind would dangle after the move).  The CTA shared
    // allocations are reclaimed by the guard on BOTH success and failure
    // paths once the backend returns (P3-GAP-07 reclaim contract).  The
    // LaunchResult keeps only diagnostic metadata — no live pointers.
    if (backend_) {
        backend_->bind_runtime(this);
        BackendLaunchRequest req;
        req.kernel_name = fn.name();
        req.kernel = &fn.kernel();
        req.config = config;
        req.layout = layout;
        req.constant_bank = bank->raw();
        req.shared_views = shared_views;
        req.cluster = topology.enabled() ? &topology : nullptr;
        // Active-launch state (Phase 3.5): the translator + shared access
        // services read this while the backend runs.  The launch
        // generation is incremented here, after all validation.
        active_topology_ = topology;
        active_views_ = shared_views;
        ++launch_count_;
        event_stopped_ = false;
        Status bst = backend_->launch(req);
        if (bst.failed()) {
            return StatusOr<LaunchResult>::failure(bst.take_error());
        }
    }
    return StatusOr<LaunchResult>::success(std::move(res));
}

// ---------------------------------------------------------------------------
// Cluster DSMEM services (Phase 3.5)
// ---------------------------------------------------------------------------

namespace {

// Resolve the shared allocation for a grid-linear CTA from the active
// launch's views.
const CtaSharedView* view_for_cta(const std::vector<CtaSharedView>& views,
                                  std::uint64_t grid_cta) {
    for (const auto& v : views) {
        if (v.cta_linear_id == grid_cta) return &v;
    }
    return nullptr;
}

}  // namespace

StatusOr<TranslatedSharedAddress> Context::translate_shared(
    std::uint64_t source_cta, std::uint64_t logical_address,
    const DeviceAccess& access, SharedAccessMode mode) {
    // The active-launch views must be populated (backend call in flight).
    if (active_views_.empty() || launch_count_ == 0) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kIllegalState,
            "translate_shared called outside an active launch",
            Error::invalid_argument("")));
    }
    const std::uint64_t width = access.width;
    if (width == 0) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kInvalidArgument,
            "shared access width must be non-zero",
            Error::invalid_argument("")));
    }
    if (access.space != AddressSpace::kShared) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "shared translation requires AddressSpace::kShared",
            Error::invalid_argument("")));
    }
    // Alignment gate (reviewer round 1): the translation address must be
    // aligned to the required alignment, and the alignment must be a power
    // of two.
    if (access.alignment == 0 ||
        (access.alignment & (access.alignment - 1)) != 0) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kInvalidArgument,
            "shared access alignment " + std::to_string(access.alignment) +
                " is not a power of two",
            Error::invalid_argument("")));
    }
    if (logical_address % access.alignment != 0) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kAlignmentViolation,
            "shared access at 0x" + std::to_string(logical_address) +
                " misaligned for " + std::to_string(access.alignment) +
                "-byte alignment",
            Error::invalid_argument("")));
    }
    // Atomic width gate (Phase 3 contract): 1/2/4/8 only.
    if (access.kind == AccessKind::kAtomic && width != 1 && width != 2 &&
        width != 4 && width != 8) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kInvalidArgument,
            "atomic shared access width " + std::to_string(width) +
                " not in {1,2,4,8}",
            Error::invalid_argument("")));
    }
    const CtaSharedView* src = view_for_cta(active_views_, source_cta);
    if (!src) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "source CTA " + std::to_string(source_cta) +
                " has no shared window in this launch",
            Error::invalid_argument("")));
    }
    TranslatedSharedAddress out;
    // Mint the capability: full 64-bit Context nonce + full 64-bit launch
    // generation (codex review round 3 — no bit-width truncation).
    out.context_nonce = context_nonce_;
    out.launch_generation = launch_count_;
    out.source_cta = source_cta;
    out.mode = mode;
    out.width = width;
    out.alignment = access.alignment;
    out.space = access.space;
    out.kind = access.kind;

    if (mode == SharedAccessMode::kLocal) {
        // No rank bits; target == source.  Offset is the full logical
        // address (bounded by the window below).
        out.cluster_id = active_topology_.cluster_id(source_cta);
        out.target_rank = active_topology_.cta_rank(source_cta);
        out.target_cta = source_cta;
        out.logical_address = logical_address;
        const CtaSharedView* tgt = src;
        // Overflow-safe bounds (reviewer round 1): size - width must not
        // wrap when width > size.
        if (logical_address > tgt->size ||
            width > tgt->size - logical_address) {
            return StatusOr<TranslatedSharedAddress>::failure(Error(
                ErrorCode::kOob,
                "local shared access at 0x" +
                    std::to_string(logical_address) + " width " +
                    std::to_string(width) + " out of bounds of CTA " +
                    std::to_string(source_cta) + " window (" +
                    std::to_string(tgt->size) + " bytes)",
                Error::out_of_range("")));
        }
        out.allocation_offset = logical_address;
        auto off = tgt->base.add(logical_address);
        if (off.failed()) return StatusOr<TranslatedSharedAddress>::failure(
            off.take_error());
        out.address = off.value();
        auto alloc = allocator_.allocation_by_base(tgt->base);
        if (alloc.failed()) {
            return StatusOr<TranslatedSharedAddress>::failure(
                alloc.take_error());
        }
        out.allocation = alloc.value().id;
        return StatusOr<TranslatedSharedAddress>::success(std::move(out));
    }

    // kDistributed: DSMEM.  Cluster must be enabled.
    if (!active_topology_.enabled()) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "DSMEM access attempted but the kernel has no cluster metadata",
            Error::invalid_argument("")));
    }
    const std::uint64_t rank = logical_address >> 24;
    const std::uint64_t offset = logical_address & 0xFFFFFF;
    out.target_rank = rank;
    out.logical_address = logical_address;
    if (!active_topology_.valid_rank(rank)) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "DSMEM rank " + std::to_string(rank) + " out of range for "
            "cluster size " + std::to_string(active_topology_.cluster_size()),
            Error::invalid_argument("")));
    }
    // Source and target must share a cluster.
    const std::uint64_t src_cluster = active_topology_.cluster_id(source_cta);
    const std::uint64_t tgt_cta =
        active_topology_.grid_cta(src_cluster, rank);
    out.cluster_id = src_cluster;
    out.target_cta = tgt_cta;
    const CtaSharedView* tgt = view_for_cta(active_views_, tgt_cta);
    if (!tgt) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "DSMEM target CTA " + std::to_string(tgt_cta) +
                " has no shared window in this launch",
            Error::invalid_argument("")));
    }
    if (active_topology_.cluster_id(tgt_cta) != src_cluster) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kBadAddress,
            "DSMEM target CTA " + std::to_string(tgt_cta) + " is in "
            "cluster " + std::to_string(active_topology_.cluster_id(tgt_cta)) +
            " but source CTA " + std::to_string(source_cta) + " is in "
            "cluster " + std::to_string(src_cluster),
            Error::invalid_argument("")));
    }
    if (offset > tgt->size || width > tgt->size - offset) {
        return StatusOr<TranslatedSharedAddress>::failure(Error(
            ErrorCode::kOob,
            "DSMEM access offset 0x" + std::to_string(offset) + " width " +
                std::to_string(width) + " out of bounds of target CTA " +
                std::to_string(tgt_cta) + " window (" +
                std::to_string(tgt->size) + " bytes)",
            Error::out_of_range("")));
    }
    out.allocation_offset = offset;
    auto off = tgt->base.add(offset);
    if (off.failed()) return StatusOr<TranslatedSharedAddress>::failure(
        off.take_error());
    out.address = off.value();
    auto alloc = allocator_.allocation_by_base(tgt->base);
    if (alloc.failed()) {
        return StatusOr<TranslatedSharedAddress>::failure(alloc.take_error());
    }
    out.allocation = alloc.value().id;
    return StatusOr<TranslatedSharedAddress>::success(std::move(out));
}

// Revalidate a translation against the active launch (reviewer round 2):
// the capability token, the bound access descriptor, the allocation
// identity, the address/offset consistency, the logical-address
// re-derivation, the CTA / cluster / rank / mode fields and the window
// membership.  A forged, stale, cross-context or mis-typed translation is
// rejected before any memory access.
Status Context::validate_translation(const TranslatedSharedAddress& addr) {
    if (active_views_.empty() || launch_count_ == 0) {
        return Status::failure(Error(
            ErrorCode::kIllegalState,
            "shared access outside an active launch",
            Error::invalid_argument("")));
    }
    // 1. Capability: the full 64-bit nonce must be THIS Context's and the
    //    full 64-bit generation must be the current launch's (stale /
    //    cross-context / forged all rejected; no bit truncation).
    if (addr.context_nonce != context_nonce_ ||
        addr.launch_generation != launch_count_) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "stale or foreign capability (forged/cross-context)",
            Error::invalid_argument("")));
    }
    // 2. Mode must be a defined value.
    if (addr.mode != SharedAccessMode::kLocal &&
        addr.mode != SharedAccessMode::kDistributed) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "undefined SharedAccessMode value " +
                std::to_string(static_cast<int>(addr.mode)),
            Error::invalid_argument("")));
    }
    if (addr.width == 0 || addr.space != AddressSpace::kShared) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "translation width/space invalid",
            Error::invalid_argument("")));
    }
    // 3. The bound access descriptor must be consistent: alignment power of
    //    two and address aligned; kind is checked by the entry point
    //    (read=kLoad, write=kStore, atomic=kAtomic).
    if (addr.alignment == 0 ||
        (addr.alignment & (addr.alignment - 1)) != 0 ||
        addr.address.va % addr.alignment != 0) {
        return Status::failure(Error(
            ErrorCode::kAlignmentViolation,
            "translation alignment contract violated",
            Error::invalid_argument("")));
    }
    // 4. Logical-address re-derivation (reviewer round 2): the identity
    //    fields must be exactly what the logical address decodes to, so a
    //    forged logical_address cannot corrupt the event stream.
    if (addr.mode == SharedAccessMode::kDistributed) {
        if ((addr.logical_address >> 24) != addr.target_rank ||
            (addr.logical_address & 0xFFFFFF) != addr.allocation_offset) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "logical address does not decode to the translation's "
                "rank/offset (forged)",
                Error::invalid_argument("")));
        }
    } else {
        if (addr.logical_address != addr.allocation_offset) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "local logical address != allocation offset (forged)",
                Error::invalid_argument("")));
        }
        if (addr.target_cta != addr.source_cta) {
            return Status::failure(Error(
                ErrorCode::kBadAddress,
                "local translation must target its source CTA (forged)",
                Error::invalid_argument("")));
        }
    }
    // 5. The allocation must be one of this launch's shared windows.
    const CtaSharedView* owner = nullptr;
    for (const auto& v : active_views_) {
        if (v.cta_linear_id == addr.target_cta) {
            owner = &v;
            break;
        }
    }
    if (!owner) {
        return Status::failure(Error(
            ErrorCode::kBadAddress,
            "target CTA " + std::to_string(addr.target_cta) +
                " is not part of the active launch",
            Error::invalid_argument("")));
    }
    auto alloc = allocator_.allocation_by_base(owner->base);
    if (alloc.failed() || alloc.value().id != addr.allocation) {
        return Status::failure(Error(
            ErrorCode::kLifecycle,
            "translation allocation id mismatch (forged or stale)",
            Error::invalid_argument("")));
    }
    // 6. The address must equal base + allocation_offset.
    auto expected = owner->base.add(addr.allocation_offset);
    if (expected.failed() || expected.value() != addr.address) {
        return Status::failure(Error(
            ErrorCode::kBadAddress,
            "translation address/offset mismatch (forged)",
            Error::invalid_argument("")));
    }
    // 7. The identity fields must be consistent with the active topology.
    if (addr.cluster_id != active_topology_.cluster_id(addr.source_cta) ||
        addr.target_rank != active_topology_.cta_rank(addr.target_cta) ||
        active_topology_.grid_cta(addr.cluster_id, addr.target_rank) !=
            addr.target_cta) {
        return Status::failure(Error(
            ErrorCode::kBadAddress,
            "translation identity fields inconsistent with the active "
            "topology (forged)",
            Error::invalid_argument("")));
    }
    // 8. Bounds re-check with the final address.
    if (addr.allocation_offset > owner->size ||
        addr.width > owner->size - addr.allocation_offset) {
        return Status::failure(Error(
            ErrorCode::kOob,
            "translation range out of bounds of the target window",
            Error::out_of_range("")));
    }
    return Status::success();
}

// Emit a shared/DSMEM access event from a trusted translation.  Events are
// emitted AFTER the memory commit (reviewer round 2 contract); once the
// sink requests a stop, subsequent events are suppressed.
void Context::emit_shared_event(const TranslatedSharedAddress& addr,
                                AccessKind kind, bool write,
                                std::uint64_t pc) {
    if (event_stopped_) return;
    BasicMemoryEvent ev;
    ev.kind = EventKind::kMemoryAccess;
    ev.pc = pc;
    ev.address = addr.address;
    ev.width = addr.width;
    ev.space = AddressSpace::kShared;
    ev.access_kind = kind;
    ev.shared_mode = addr.mode;
    ev.source_cta = addr.source_cta;
    ev.cluster_id = addr.cluster_id;
    ev.target_rank = addr.target_rank;
    ev.target_cta = addr.target_cta;
    ev.logical_address = addr.logical_address;
    ev.allocation = addr.allocation;
    ev.allocation_offset = addr.allocation_offset;
    ev.write = write;
    if (!emit_event(ev)) {
        event_stopped_ = true;  // sink breakpoint: stop further delivery
    }
}

Status Context::read_shared(const TranslatedSharedAddress& addr, void* dst) {
    Status st = validate_translation(addr);
    if (st.failed()) return st;
    // Blocker 2: the bound kind must be kLoad; a store/atomic translation
    // cannot be used for a read.
    if (addr.kind != AccessKind::kLoad) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "read_shared requires a kLoad translation (bound kind is " +
                std::to_string(static_cast<int>(addr.kind)) + ")",
            Error::invalid_argument("")));
    }
    Status r = allocator_.read_at(addr.allocation, addr.allocation_offset,
                                  dst, addr.width);
    if (r.failed()) return r;
    emit_shared_event(addr, AccessKind::kLoad, false, 0);
    return Status::success();
}

Status Context::write_shared(const TranslatedSharedAddress& addr,
                             const void* src) {
    Status st = validate_translation(addr);
    if (st.failed()) return st;
    if (addr.kind != AccessKind::kStore) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "write_shared requires a kStore translation (bound kind is " +
                std::to_string(static_cast<int>(addr.kind)) + ")",
            Error::invalid_argument("")));
    }
    Status r = allocator_.write_at(addr.allocation, addr.allocation_offset,
                                   src, addr.width);
    if (r.failed()) return r;
    emit_shared_event(addr, AccessKind::kStore, true, 0);
    return Status::success();
}

Status Context::atomic_shared(const TranslatedSharedAddress& addr,
                              AtomicOp op, const void* value, void* old) {
    Status st = validate_translation(addr);
    if (st.failed()) return st;
    if (addr.kind != AccessKind::kAtomic) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "atomic_shared requires a kAtomic translation (bound kind is " +
                std::to_string(static_cast<int>(addr.kind)) + ")",
            Error::invalid_argument("")));
    }
    if (static_cast<std::uint8_t>(op) >=
        static_cast<std::uint8_t>(AtomicOp::kCount)) {
        return Status::failure(Error(
            ErrorCode::kInvalidArgument,
            "undefined AtomicOp value " + std::to_string(static_cast<int>(op)),
            Error::invalid_argument("")));
    }
    // True atomic RMW inside the allocator's critical section (High 1).
    Status r = allocator_.atomic_rmw(addr.allocation, addr.allocation_offset,
                                     addr.width, op, value, old);
    if (r.failed()) return r;
    emit_shared_event(addr, AccessKind::kAtomic, true, 0);
    return Status::success();
}

const ClusterTopology& Context::shared_topology() const {
    return active_topology_;
}

// ---------------------------------------------------------------------------
// IRuntimeServices (Context)
// ---------------------------------------------------------------------------

Status Context::write(DevicePtr ptr, const void* src, std::uint64_t len) {
    return allocator_.write(ptr, src, len);
}
Status Context::read(DevicePtr ptr, void* dst, std::uint64_t len) {
    return allocator_.read(ptr, dst, len);
}
Status Context::memset(DevicePtr ptr, int value, std::uint64_t len) {
    return allocator_.memset(ptr, value, len);
}
Status Context::copy(DevicePtr dst, DevicePtr src, std::uint64_t len) {
    return allocator_.copy(dst, src, len);
}
Status Context::read_typed(DevicePtr ptr, void* dst, std::uint64_t len,
                           const DeviceAccess& access) {
    return allocator_.read_typed(ptr, dst, len, access);
}
Status Context::write_typed(DevicePtr ptr, const void* src, std::uint64_t len,
                            const DeviceAccess& access) {
    return allocator_.write_typed(ptr, src, len, access);
}
std::span<const std::uint8_t> Context::constant_bank(
    const std::string& kernel_name) const {
    for (const auto& [name, bank] : banks_) {
        if (name == kernel_name) return bank.raw();
    }
    return {};
}

bool Context::emit_event(const BasicMemoryEvent& event) {
    if (!event_sink_) return true;
    return event_sink_->emit(event);
}

}  // namespace semu
