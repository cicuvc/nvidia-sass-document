// L3.5 unit tests: cluster DSMEM address translation (Phase 3.5).
//
// Exercises ClusterTopology construction, the DSMEM logical-address rule
// (rank<<24 | offset), cross-CTA authorized access through the runtime
// services, negative matrices (disabled cluster / absent rank / cross
// cluster / OOB / local-vs-DSMEM distinction), and the identity fields of
// the translation.

#include <semu/cluster.hpp>
#include <semu/context.hpp>
#include <semu/memory.hpp>

#include <cstdio>
#include <cstring>
#include <string>
#include <thread>

#include "test_framework.hpp"

using namespace semu;

namespace {

void push16(std::vector<std::uint8_t>* out, std::uint16_t v);

// A 4-param kernel cubin with a declared (2,2,1) cluster.
// KPARAM: a(ptr)@0x0 size8, b(int)@0x8 size4, c(16B)@0x10, n(int)@0x20;
// .nv.shared._Z6clkernv NOBITS 0x400; cluster_dims (2,2,1) + EXPLICIT.
std::vector<std::uint8_t> make_cluster_cubin(
    std::array<std::uint32_t, 3> cluster = {2, 2, 1}) {
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint64_t size = 0;
        std::uint32_t link = 0;
        std::uint32_t info = 0;
        std::uint64_t align = 4;
        std::uint64_t entsize = 0;
    };
    std::vector<S> secs(8);
    secs[1].name = ".shstrtab"; secs[1].type = 3;
    secs[2].name = ".strtab"; secs[2].type = 3;
    secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
    secs[3].entsize = 24; secs[3].align = 8;
    secs[4].name = ".text._Z6clkernv"; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info._Z6clkernv"; secs[6].type = 0x70000000;
    secs[6].info = 4;
    secs[7].name = ".nv.shared._Z6clkernv"; secs[7].type = 8;  // NOBITS
    secs[7].flags = 2 | 0x40; secs[7].info = 4; secs[7].size = 0x400;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    std::vector<std::uint8_t> kern_info;
    auto kp = [&](std::uint32_t ord, std::uint32_t off, std::uint32_t sz) {
        kern_info.push_back(4); kern_info.push_back(0x17);
        kern_info.push_back(12); kern_info.push_back(0);
        push32(&kern_info, 0);
        push32(&kern_info, (off << 16) | ord);
        push32(&kern_info, (((sz << 2) | 1) << 16) | 0xf000);
    };
    kp(3, 0x20, 4);
    kp(0, 0x0, 8);
    kp(2, 0x10, 16);
    kp(1, 0x8, 4);
    // cluster dims (0x3d, fmt=4, 12B) + explicit cluster (0x3e, fmt=1).
    kern_info.push_back(4); kern_info.push_back(0x3d);
    kern_info.push_back(12); kern_info.push_back(0);
    push32(&kern_info, cluster[0]);
    push32(&kern_info, cluster[1]);
    push32(&kern_info, cluster[2]);
    kern_info.push_back(1); kern_info.push_back(0x3e);
    kern_info.push_back(0); kern_info.push_back(0);

    std::vector<std::uint8_t> text;
    push64(&text, 0x0000000000007918ULL);
    push64(&text, 0x000fc00000000000ULL);

    std::vector<std::uint8_t> symtab(24, 0);
    auto sym = [&](std::uint32_t name, std::uint8_t info, std::uint8_t other,
                   std::uint16_t shndx, std::uint64_t value,
                   std::uint64_t size) {
        std::vector<std::uint8_t> e;
        push32(&e, name); e.push_back(info); e.push_back(other);
        e.push_back(shndx & 0xff); e.push_back(shndx >> 8);
        push64(&e, value); push64(&e, size);
        symtab.insert(symtab.end(), e.begin(), e.end());
    };
    std::string strtab = std::string(1, '\0') + ".text._Z6clkernv" + '\0' +
                         "_Z6clkernv" + '\0' + ".nv.constant0._Z6clkernv" +
                         '\0' + ".nv.shared._Z6clkernv" + '\0';
    sym(1, 0x03, 0x00, 4, 0, 0);   // .text section
    sym(18, 0x12, 0x10, 4, 0, 16); // func
    sym(29, 0x03, 0x00, 4, 0, 0);  // constant0
    sym(54, 0x03, 0x00, 7, 0, 0);  // shared section

    secs[4].data = text;
    secs[6].data = kern_info;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());

    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i)
        shstr += secs[i].name + '\0';
    secs[1].data.assign(shstr.begin(), shstr.end());

    std::vector<std::uint64_t> offs(secs.size(), 0);
    std::uint64_t cur = 64;
    for (std::size_t i = 1; i < secs.size(); ++i) {
        const std::uint64_t al = std::max<std::uint64_t>(secs[i].align, 1);
        cur = (cur + al - 1) & ~(al - 1);
        offs[i] = cur;
        cur += secs[i].data.size();
    }
    const std::uint64_t shoff = cur;

    std::vector<std::uint8_t> out;
    const std::uint8_t ident[16] = {0x7f, 'E', 'L', 'F', 2, 1, 1, 0x41,
                                    0x08, 0, 0, 0, 0, 0, 0, 0};
    out.insert(out.end(), ident, ident + 16);
    push16(&out, 2);
    push16(&out, 190);
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    push16(&out, 64); push16(&out, 56); push16(&out, 0);
    push16(&out, 64);
    push16(&out, static_cast<std::uint16_t>(secs.size()));
    push16(&out, 1);
    for (std::size_t i = 1; i < secs.size(); ++i) {
        if (secs[i].type == 8) continue;
        while (out.size() % std::max<std::uint64_t>(secs[i].align, 1))
            out.push_back(0);
        out.insert(out.end(), secs[i].data.begin(), secs[i].data.end());
    }
    std::uint32_t name_pos = 1;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        std::uint32_t no = 0;
        if (i > 0) { no = name_pos; name_pos += secs[i].name.size() + 1; }
        push32(&out, no);
        push32(&out, secs[i].type);
        push64(&out, secs[i].flags);
        push64(&out, 0);
        push64(&out, (i == 0 || secs[i].type == 8) ? 0 : offs[i]);
        push64(&out, secs[i].type == 8 ? secs[i].size : secs[i].data.size());
        push32(&out, secs[i].link);
        push32(&out, secs[i].info);
        push64(&out, secs[i].align);
        push64(&out, secs[i].entsize);
    }
    return out;
}

void push16(std::vector<std::uint8_t>* out, std::uint16_t v) {
    out->push_back(v & 0xff);
    out->push_back((v >> 8) & 0xff);
}

// Standard shared-access descriptor for tests (width, aligned, shared).
DeviceAccess shared_access(std::uint64_t width,
                           AccessKind kind = AccessKind::kLoad) {
    DeviceAccess a;
    a.width = width;
    a.alignment = width;
    a.space = AddressSpace::kShared;
    a.kind = kind;
    return a;
}

}  // namespace

// ---------------------------------------------------------------------------
// ClusterTopology
// ---------------------------------------------------------------------------

TEST(cluster_topology_basic_mapping) {
    // 3D tiling (reviewer round 1): grid (4,2,1) tiled by cluster (2,2,1).
    // x-fast CTA ids: (x,y,z) -> z*gx*gy + y*gx + x.
    // Cluster 0 covers x in [0,2), y in [0,2): CTAs 0,1 (x 0,1 y 0) and
    // 4,5 (x 0,1 y 1).
    auto t = ClusterTopology::build(std::array<std::uint32_t, 3>{2, 2, 1},
                                    4, 2, 1);
    CHECK(t.ok());
    if (!t.ok()) return;
    const auto& topo = t.value();
    CHECK(topo.enabled());
    CHECK(topo.cluster_size() == 4);
    CHECK(topo.cluster_count() == 2);  // (4/2)*(2/2) = 2 clusters
    // Cluster membership: CTA 0,1,4,5 -> cluster 0; CTA 2,3,6,7 -> cluster 1.
    for (std::uint64_t c : {std::uint64_t{0}, std::uint64_t{1},
                            std::uint64_t{4}, std::uint64_t{5}}) {
        CHECK(topo.cluster_id(c) == 0);
    }
    for (std::uint64_t c : {std::uint64_t{2}, std::uint64_t{3},
                            std::uint64_t{6}, std::uint64_t{7}}) {
        CHECK(topo.cluster_id(c) == 1);
    }
    // Ranks within cluster 0: CTA0 rank0, CTA1 rank1, CTA4 rank2, CTA5 rank3
    // (rank = rz*cx*cy + ry*cx + rx with (x%cx, y%cy)).
    CHECK(topo.cta_rank(0) == 0);
    CHECK(topo.cta_rank(1) == 1);
    CHECK(topo.cta_rank(4) == 2);
    CHECK(topo.cta_rank(5) == 3);
    // Reverse mapping.
    CHECK(topo.grid_cta(0, 2) == 4);
    CHECK(topo.grid_cta(1, 0) == 2);
    // 3D: grid (4,4,2) with cluster (2,2,2): 2*2*1 = 4 clusters of 8.
    auto t3 = ClusterTopology::build(std::array<std::uint32_t, 3>{2, 2, 2},
                                     4, 4, 2);
    CHECK(t3.ok());
    if (!t3.ok()) return;
    const auto& topo3 = t3.value();
    CHECK(topo3.cluster_size() == 8);
    CHECK(topo3.cluster_count() == 4);
    // CTA (x=3,y=3,z=1) = id 1*16 + 3*4 + 3 = 31; in cluster (1,1,0) =
    // cluster id 3; rank = (1,1,1) = 1*4+1*2+1 = 7.
    CHECK(topo3.cluster_id(31) == 3);
    CHECK(topo3.cta_rank(31) == 7);
    CHECK(topo3.grid_cta(3, 7) == 31);
}

TEST(cluster_topology_legality) {
    // No cluster metadata -> disabled.
    auto t = ClusterTopology::build(std::nullopt, 4, 1, 1);
    CHECK(t.ok() && !t.value().enabled());
    // Zero cluster dim.
    auto z = ClusterTopology::build(std::array<std::uint32_t, 3>{0, 2, 1},
                                    4, 2, 1);
    CHECK(z.failed());
    // Product overflow (grid and cluster products checked internally).
    auto huge = ClusterTopology::build(
        std::array<std::uint32_t, 3>{0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF},
        0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF);
    CHECK(huge.failed());
    // Cap: 4x2x1 = 8 allowed; 4x4x1 = 16 rejected.
    auto ok8 = ClusterTopology::build(std::array<std::uint32_t, 3>{4, 2, 1},
                                      8, 2, 1);
    CHECK(ok8.ok() && ok8.value().cluster_size() == 8);
    auto over = ClusterTopology::build(std::array<std::uint32_t, 3>{4, 4, 1},
                                       16, 4, 1);
    CHECK(over.failed());
    // Per-axis divisibility (reviewer round 1): grid y < cluster y -> the
    // cluster cannot be formed.
    auto div = ClusterTopology::build(std::array<std::uint32_t, 3>{2, 2, 1},
                                      4, 1, 1);
    CHECK(div.failed());
    // Per-axis divisibility covers trailing partial clusters: grid x=5
    // with cluster x=2 leaves a partial column -> rejected.
    auto partial = ClusterTopology::build(
        std::array<std::uint32_t, 3>{2, 2, 1}, 5, 2, 1);
    CHECK(partial.failed());
}

// ---------------------------------------------------------------------------
// DSMEM translation through the runtime services
// ---------------------------------------------------------------------------

// A backend that performs DSMEM cross-CTA accesses through the services.
struct DsmemBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<TranslatedSharedAddress> translations;
    bool cross_cta_roundtrip_ok = false;
    std::string last_failure;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Source CTA 0 writes to rank 1 (DSMEM), then reads it back.
        // The capability binds one kind per translation (Blocker 2): mint
        // a kStore translation for the write and a kLoad one for the read.
        const std::uint64_t logical = (1ULL << 24) | 0x0;  // rank 1, off 0
        auto tr = services->translate_shared(0, logical,
                                             shared_access(8, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) {
            last_failure = tr.take_error().describe();
            return Status::failure(Error::internal(last_failure));
        }
        const TranslatedSharedAddress& t = tr.value();
        translations.push_back(t);
        std::uint64_t payload = 0x1234567890ABCDEFULL;
        if (services->write_shared(t, &payload).failed()) {
            last_failure = "write_shared failed";
            return Status::failure(Error::internal(last_failure));
        }
        auto trl = services->translate_shared(0, logical,
                                              shared_access(8, AccessKind::kLoad),
                                              SharedAccessMode::kDistributed);
        if (trl.failed()) {
            last_failure = trl.take_error().describe();
            return Status::failure(Error::internal(last_failure));
        }
        std::uint64_t back = 0;
        if (services->read_shared(trl.value(), &back).failed()) {
            last_failure = "read_shared failed";
            return Status::failure(Error::internal(last_failure));
        }
        cross_cta_roundtrip_ok = (back == payload);
        return Status::success();
    }
    const char* name() const override { return "dsmem"; }
};

TEST(dsmem_translation_and_cross_cta_roundtrip) {
    auto backend = std::make_shared<DsmemBackend>();
    auto ctx = Context::create(backend);
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    if (!mod.ok()) {
        std::fprintf(stderr, "cluster cubin load: %s\n",
                     mod.take_error().describe().c_str());
    }
    CHECK(mod.ok());
    if (!mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    if (!fn.ok()) {
        std::fprintf(stderr, "fn error: %s\n",
                     fn.take_error().describe().c_str());
    }
    CHECK(fn.ok());
    if (!fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    cfg.grid_y = 2;  // 8 CTAs = 2 clusters of (2,2,1)
    auto r = ctx.value().launch(fn.value(), cfg, args);
    if (!r.ok()) {
        std::fprintf(stderr, "launch: %s\n",
                     r.take_error().describe().c_str());
    }
    CHECK(r.ok());
    if (!r.ok()) return;
    if (!backend->cross_cta_roundtrip_ok) {
        std::fprintf(stderr, "backend failure: %s\n",
                     backend->last_failure.c_str());
    }
    CHECK(backend->cross_cta_roundtrip_ok);
    CHECK(!backend->translations.empty());
    if (backend->translations.empty()) return;
    const auto& t = backend->translations[0];
    // Identity fields: source 0, cluster 0, rank 1, target 1.
    CHECK(t.source_cta == 0);
    CHECK(t.cluster_id == 0);
    CHECK(t.target_rank == 1);
    CHECK(t.target_cta == 1);
    CHECK(t.logical_address == ((1ULL << 24) | 0x0));
    CHECK(t.allocation_offset == 0);
    CHECK(t.width == 8);
    CHECK(t.mode == SharedAccessMode::kDistributed);
    // The translated address is inside the launch's shared window but NOT
    // the source CTA's base (rank 1's window differs by an allocation).
    CHECK(t.address.va != 0);
}

// ---------------------------------------------------------------------------
// Negative matrix
// ---------------------------------------------------------------------------

struct DsmemNegativeProbe : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<std::string> observed_failures;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // rank 4 (out of range for cluster size 4).
        auto r1 = services->translate_shared(0, (4ULL << 24) | 0, shared_access(8), SharedAccessMode::kDistributed);
        if (r1.ok()) return Status::failure(Error::internal("rank4 ok?"));
        observed_failures.push_back(r1.take_error().describe());
        // offset past the window: rank 1, offset 0x400 (window is 0x400).
        auto r2 = services->translate_shared(0, (1ULL << 24) | 0x400, shared_access(8), SharedAccessMode::kDistributed);
        if (r2.ok()) return Status::failure(Error::internal("oob ok?"));
        observed_failures.push_back(r2.take_error().describe());
        // width crossing the window end: 8-aligned (alignment 8) so the
        // alignment gate passes and the OOB gate fires.
        DeviceAccess acc16 = shared_access(16);
        acc16.alignment = 8;
        auto r3 = services->translate_shared(0, (1ULL << 24) | 0x3F8, acc16,
                                             SharedAccessMode::kDistributed);
        if (r3.ok()) return Status::failure(Error::internal("width ok?"));
        observed_failures.push_back(r3.take_error().describe());
        return Status::success();
    }
    const char* name() const override { return "dsmemneg"; }
};

TEST(dsmem_negative_matrix) {
    auto backend = std::make_shared<DsmemNegativeProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->observed_failures.size() == 3);
    for (const auto& f : backend->observed_failures) {
        std::fprintf(stderr, "neg: %s\n", f.c_str());
        CHECK(f.find("out of range") != std::string::npos ||
              f.find("out of bounds") != std::string::npos);
    }
}

// DSMEM on a non-cluster kernel must fail.
struct DsmemNoClusterProbe : IBackend {
    IRuntimeServices* services = nullptr;
    bool failed_as_expected = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        auto r = services->translate_shared(0, (1ULL << 24) | 0, shared_access(8), SharedAccessMode::kDistributed);
        failed_as_expected = r.failed();
        return Status::success();
    }
    const char* name() const override { return "dsmemnocl"; }
};

TEST(dsmem_rejected_without_cluster) {
    // Reuse the plain 4-param cubin (no cluster metadata).
    auto backend = std::make_shared<DsmemNoClusterProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(
        []() {
            // Build the non-cluster cubin by stripping cluster EIATTR from
            // the cluster cubin: simplest is to reuse the test_memory
            // builder via a small inline copy — instead load the shared
            // 4-param cubin from the memory test file's builder path is
            // not accessible here, so construct via make_cluster_cubin
            // minus cluster attrs: rebuild with cluster dims {1,1,1} still
            // enables the cluster.  Use a kernel with NO .nv.info cluster
            // records: make a dedicated minimal cubin inline.
            struct S {
                std::string name;
                std::uint32_t type = 0;
                std::uint64_t flags = 0;
                std::vector<std::uint8_t> data;
                std::uint64_t size = 0;
                std::uint32_t link = 0;
                std::uint32_t info = 0;
                std::uint64_t align = 4;
                std::uint64_t entsize = 0;
            };
            std::vector<S> secs(7);
            secs[1].name = ".shstrtab"; secs[1].type = 3;
            secs[2].name = ".strtab"; secs[2].type = 3;
            secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
            secs[3].entsize = 24; secs[3].align = 8;
            secs[4].name = ".text._Z6clkernv"; secs[4].type = 1;
            secs[4].flags = 2 | 4; secs[4].align = 128;
            secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
            secs[6].name = ".nv.info._Z6clkernv"; secs[6].type = 0x70000000;
            secs[6].info = 4;
            auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
                for (int i = 0; i < 4; ++i)
                    v->push_back((x >> (8 * i)) & 0xff);
            };
            auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
                for (int i = 0; i < 8; ++i)
                    v->push_back((x >> (8 * i)) & 0xff);
            };
            std::vector<std::uint8_t> text;
            push64(&text, 0x0000000000007918ULL);
            push64(&text, 0x000fc00000000000ULL);
            std::vector<std::uint8_t> symtab(24, 0);
            auto sym = [&](std::uint32_t name, std::uint8_t info,
                           std::uint8_t other, std::uint16_t shndx,
                           std::uint64_t value, std::uint64_t size) {
                std::vector<std::uint8_t> e;
                push32(&e, name); e.push_back(info); e.push_back(other);
                e.push_back(shndx & 0xff); e.push_back(shndx >> 8);
                push64(&e, value); push64(&e, size);
                symtab.insert(symtab.end(), e.begin(), e.end());
            };
            std::string strtab = std::string(1, '\0') + ".text._Z6clkernv" +
                                 '\0' + "_Z6clkernv" + '\0' +
                                 ".nv.constant0._Z6clkernv" + '\0';
            sym(1, 0x03, 0x00, 4, 0, 0);
            sym(18, 0x12, 0x10, 4, 0, 16);
            sym(29, 0x03, 0x00, 4, 0, 0);
            secs[4].data = text;
            secs[3].data = symtab;
            secs[2].data.assign(strtab.begin(), strtab.end());
            std::string shstr(1, '\0');
            for (std::size_t i = 1; i < secs.size(); ++i)
                shstr += secs[i].name + '\0';
            secs[1].data.assign(shstr.begin(), shstr.end());
            std::vector<std::uint64_t> offs(secs.size(), 0);
            std::uint64_t cur = 64;
            for (std::size_t i = 1; i < secs.size(); ++i) {
                const std::uint64_t al =
                    std::max<std::uint64_t>(secs[i].align, 1);
                cur = (cur + al - 1) & ~(al - 1);
                offs[i] = cur;
                cur += secs[i].data.size();
            }
            std::vector<std::uint8_t> out;
            const std::uint8_t ident[16] = {0x7f, 'E', 'L', 'F', 2, 1, 1,
                                            0x41, 0x08, 0, 0, 0, 0, 0, 0, 0};
            out.insert(out.end(), ident, ident + 16);
            push16(&out, 2);
            push16(&out, 190);
            push32(&out, 1);
            push64(&out, 0);
            push64(&out, 0);
            push64(&out, cur);
            push32(&out, 0x06007802);
            push16(&out, 64); push16(&out, 56); push16(&out, 0);
            push16(&out, 64);
            push16(&out, static_cast<std::uint16_t>(secs.size()));
            push16(&out, 1);
            for (std::size_t i = 1; i < secs.size(); ++i) {
                while (out.size() %
                       std::max<std::uint64_t>(secs[i].align, 1))
                    out.push_back(0);
                out.insert(out.end(), secs[i].data.begin(),
                           secs[i].data.end());
            }
            std::uint32_t name_pos = 1;
            for (std::size_t i = 0; i < secs.size(); ++i) {
                std::uint32_t no = 0;
                if (i > 0) {
                    no = name_pos;
                    name_pos += secs[i].name.size() + 1;
                }
                push32(&out, no);
                push32(&out, secs[i].type);
                push64(&out, secs[i].flags);
                push64(&out, 0);
                push64(&out, i == 0 ? 0 : offs[i]);
                push64(&out, secs[i].data.size());
                push32(&out, secs[i].link);
                push32(&out, secs[i].info);
                push64(&out, secs[i].align);
                push64(&out, secs[i].entsize);
            }
            return out;
        }(),
        "nocl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto r = ctx.value().launch(fn.value(), LaunchConfig{},
                                std::vector<KernelArg>{});
    if (!r.ok()) {
        std::fprintf(stderr, "nocl launch: %s\n",
                     r.take_error().describe().c_str());
    }
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->failed_as_expected);
}

// Local shared access never interprets rank bits: a local access with a
// high-bit-set offset is still local (offset = full address) and fails as
// OOB rather than silently becoming a DSMEM access.
struct LocalNoRankProbe : IBackend {
    IRuntimeServices* services = nullptr;
    bool rank_bits_ignored = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Local mode with a high-bit-set logical address on a 0x400 window.
        auto r = services->translate_shared(0, (1ULL << 24) | 0x10, shared_access(8), SharedAccessMode::kLocal);
        // Must be OOB (offset 0x10000010 > 0x400 window), NOT a DSMEM
        // translation to rank 1.
        rank_bits_ignored = r.failed();
        return Status::success();
    }
    const char* name() const override { return "localnorank"; }
};

TEST(dsmem_local_mode_ignores_rank_bits) {
    auto backend = std::make_shared<LocalNoRankProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->rank_bits_ignored);
}

// ---------------------------------------------------------------------------
// Translation boundary golden: rank 0 DSMEM == cluster rank 0, NOT source.
// ---------------------------------------------------------------------------

struct DsmemRank0Probe : IBackend {
    IRuntimeServices* services = nullptr;
    bool rank0_is_cluster_rank0 = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Source CTA 2 (x=2,y=0 -> cluster (1,0) = cluster id 1, rank 0).
        // DSMEM rank 0 targets the source cluster's rank-0 CTA, which for
        // cluster 1 is grid CTA 2 (x=2,y=0) — NOT CTA 0.  The identity must
        // reflect the source cluster, never an implicit self/global-0.
        auto r = services->translate_shared(2, (0ULL << 24) | 0x20, shared_access(4), SharedAccessMode::kDistributed);
        if (r.failed()) return Status::failure(Error::internal(
            r.take_error().describe()));
        // Source CTA 2 is in cluster 1; its cluster rank is 0 (x=2,y=0
        // with cluster dims (2,2,1): rx=0, ry=0 -> rank 0).
        rank0_is_cluster_rank0 = (r.value().cluster_id == 1 &&
                                  r.value().source_cta == 2 &&
                                  r.value().target_rank == 0 &&
                                  r.value().target_cta == 2 &&
                                  r.value().allocation_offset == 0x20);
        return Status::success();
    }
    const char* name() const override { return "dsmemrank0"; }
};

TEST(dsmem_rank0_is_cluster_rank0) {
    auto backend = std::make_shared<DsmemRank0Probe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->rank0_is_cluster_rank0);
}

// ---------------------------------------------------------------------------
// Event identity + DSMEM atomic widths
// ---------------------------------------------------------------------------

// The backend emits a shared event after a DSMEM access; the event must
// carry the full translation identity (mode/source/target/rank/logical/
// allocation id + offset).
struct DsmemEventBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<BasicMemoryEvent> events;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        auto tr = services->translate_shared(0, (1ULL << 24) | 0x20, shared_access(4, AccessKind::kStore), SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        const auto& t = tr.value();
        BasicMemoryEvent ev;
        ev.kind = EventKind::kMemoryAccess;
        ev.pc = 0x30;
        ev.address = t.address;
        ev.width = t.width;
        ev.space = AddressSpace::kShared;
        ev.access_kind = AccessKind::kStore;
        ev.shared_mode = SharedAccessMode::kDistributed;
        ev.source_cta = t.source_cta;
        ev.cluster_id = t.cluster_id;
        ev.target_rank = t.target_rank;
        ev.target_cta = t.target_cta;
        ev.logical_address = t.logical_address;
        ev.allocation = t.allocation;
        ev.allocation_offset = t.allocation_offset;
        ev.write = true;
        services->emit_event(ev);
        events.push_back(ev);
        return Status::success();
    }
    const char* name() const override { return "dsmemev"; }
};

TEST(dsmem_event_identity_golden) {
    auto backend = std::make_shared<DsmemEventBackend>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->events.size() == 1);
    if (backend->events.empty()) return;
    const auto& ev = backend->events[0];
    CHECK(ev.shared_mode == SharedAccessMode::kDistributed);
    CHECK(ev.source_cta == 0);
    CHECK(ev.cluster_id == 0);
    CHECK(ev.target_rank == 1);
    CHECK(ev.target_cta == 1);
    CHECK(ev.logical_address == ((1ULL << 24) | 0x20));
    CHECK(ev.allocation_offset == 0x20);
    CHECK(ev.width == 4);
    CHECK(ev.write);
    CHECK(ev.allocation.id != 0);  // stable allocation identity, not host ptr
}

// DSMEM atomic: legal widths 1/2/4/8 through the typed translation; the
// write_shared path is the authorized channel (AccessKind::kAtomic flows
// through the same translation, width/alignment gated by Phase 3 rules).
struct DsmemAtomicProbe : IBackend {
    IRuntimeServices* services = nullptr;
    std::size_t ok_widths = 0;
    bool bad_width_rejected = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        for (const std::uint64_t w : {std::uint64_t{1}, std::uint64_t{2},
                                      std::uint64_t{4}, std::uint64_t{8}}) {
            auto tr = services->translate_shared(
                0, (1ULL << 24) | 0x40, shared_access(w, AccessKind::kAtomic),
                SharedAccessMode::kDistributed);
            if (tr.failed()) return Status::failure(Error::internal(
                tr.take_error().describe()));
            std::uint64_t payload = 0xAB;
            auto st = services->atomic_shared(tr.value(), AtomicOp::kAdd,
                                              &payload, nullptr);
            if (st.failed()) return Status::failure(Error::internal(
                st.take_error().describe()));
            ++ok_widths;
        }
        // 16-byte DSMEM is not a legal atomic width: the translation still
        // succeeds (translation is width-agnostic), but the Phase 3 atomic
        // width gate rejects it at the typed layer.  Here we verify the
        // translation refuses an out-of-window width.
        auto tr16 = services->translate_shared(0, (1ULL << 24) | 0x3F8, shared_access(16), SharedAccessMode::kDistributed);
        bad_width_rejected = tr16.failed();
        return Status::success();
    }
    const char* name() const override { return "dsmematom"; }
};

TEST(dsmem_atomic_widths_and_oob) {
    auto backend = std::make_shared<DsmemAtomicProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->ok_widths == 4);
    CHECK(backend->bad_width_rejected);
}

// ---------------------------------------------------------------------------
// Reviewer round 1: forged-translation rejection (Blocker 2)
// ---------------------------------------------------------------------------

// A backend that builds forged TranslatedSharedAddresses and verifies each
// is rejected before touching memory.
struct ForgeProbe : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<bool> rejected;
    bool genuine_ok = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // A genuine translation to mutate.
        auto tr = services->translate_shared(0, (1ULL << 24) | 0x10,
                                             shared_access(8, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        TranslatedSharedAddress good = tr.value();

        // 1. address changed to a forged global allocation.
        auto g = [&]() {
            // Allocate global through the (byte) services.
            // (No allocation API on services; use a fixed non-shared VA.)
            return DevicePtr{0x10000};
        }();
        TranslatedSharedAddress f1 = good;
        f1.address = g;
        rejected.push_back(services->write_shared(f1, "x").failed());

        // 2. allocation id changed to a different allocation.
        TranslatedSharedAddress f2 = good;
        f2.allocation = AllocationId{999};
        rejected.push_back(services->write_shared(f2, "x").failed());

        // 3. address/offset inconsistent.
        TranslatedSharedAddress f3 = good;
        f3.allocation_offset = good.allocation_offset + 8;
        rejected.push_back(services->write_shared(f3, "x").failed());

        // 4. target rank / target CTA modified.
        TranslatedSharedAddress f4 = good;
        f4.target_rank = 3;
        f4.target_cta = good.target_cta + 1;
        rejected.push_back(services->write_shared(f4, "x").failed());

        // 5. stale generation (previous launch's counter value).
        TranslatedSharedAddress f5 = good;
        f5.launch_generation = good.launch_generation - 1;
        rejected.push_back(services->write_shared(f5, "x").failed());

        // 5b. foreign nonce (different Context).
        TranslatedSharedAddress f5b = good;
        f5b.context_nonce = good.context_nonce + 1;
        rejected.push_back(services->write_shared(f5b, "x").failed());

        // 6. mode flipped (forged DSMEM from a local translation).
        TranslatedSharedAddress f6 = good;
        f6.mode = SharedAccessMode::kLocal;
        rejected.push_back(services->write_shared(f6, "x").failed());

        // Sanity: the genuine translation still works (recorded as a
        // separate flag, not part of the rejection vector).
        std::uint64_t payload = 0x7777;
        genuine_ok = services->write_shared(good, &payload).ok();
        return Status::success();
    }
    const char* name() const override { return "forge"; }
};

TEST(dsmem_forged_translation_rejected) {
    auto backend = std::make_shared<ForgeProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    // All 7 forgeries rejected + genuine accepted.
    CHECK(backend->rejected.size() == 7);
    for (std::size_t i = 0; i < backend->rejected.size(); ++i) {
        CHECK(backend->rejected[i]);
    }
    CHECK(backend->genuine_ok);
}

// Cross-context: a translation from Context A used on Context B must be
// rejected (different launch generation AND different active launch).
struct CrossContextProbe : IBackend {
    IRuntimeServices* services = nullptr;
    TranslatedSharedAddress stolen;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        auto tr = services->translate_shared(0, (1ULL << 24) | 0,
                                             shared_access(4),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        stolen = tr.value();
        return Status::success();
    }
    const char* name() const override { return "crossctx"; }
};

TEST(dsmem_cross_context_translation_rejected) {
    // Context A: steal a translation.
    auto backend_a = std::make_shared<CrossContextProbe>();
    auto ctx_a = Context::create(backend_a);
    auto mod_a = ctx_a.value().load_module(make_cluster_cubin(), "cl");
    auto fn_a = ctx_a.value().function(mod_a.value(), "_Z6clkernv");
    CHECK(ctx_a.ok() && mod_a.ok() && fn_a.ok());
    if (!ctx_a.ok() || !mod_a.ok() || !fn_a.ok()) return;
    auto pa = ctx_a.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(pa.ok());
    std::vector<KernelArg> args_a;
    args_a.push_back(KernelArg::pointer(pa.value(), "a"));
    args_a.push_back(KernelArg::integer(1, "b"));
    args_a.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args_a.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto ra = ctx_a.value().launch(fn_a.value(), cfg, args_a);
    CHECK(ra.ok());
    if (!ra.ok()) return;

    // Context B: replay the stolen translation (fresh generation).
    auto backend_b = std::make_shared<CrossContextProbe>();
    auto ctx_b = Context::create(backend_b);
    auto mod_b = ctx_b.value().load_module(make_cluster_cubin(), "cl");
    auto fn_b = ctx_b.value().function(mod_b.value(), "_Z6clkernv");
    CHECK(ctx_b.ok() && mod_b.ok() && fn_b.ok());
    if (!ctx_b.ok() || !mod_b.ok() || !fn_b.ok()) return;
    auto pb = ctx_b.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(pb.ok());
    std::vector<KernelArg> args_b;
    args_b.push_back(KernelArg::pointer(pb.value(), "a"));
    args_b.push_back(KernelArg::integer(1, "b"));
    args_b.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args_b.push_back(KernelArg::integer(1, "n"));
    auto rb = ctx_b.value().launch(fn_b.value(), cfg, args_b);
    CHECK(rb.ok());
    if (!rb.ok()) return;
    // The stolen translation's generation is 1; Context B's is also 1 —
    // but the allocation id differs (fresh allocator), so revalidation
    // must reject it.
    auto replay = ctx_b.value().write_shared(backend_a->stolen, "x");
    CHECK(replay.failed());
}

// ---------------------------------------------------------------------------
// Reviewer round 1: true DSMEM atomic RMW + auto events (High 3/7)
// ---------------------------------------------------------------------------

struct DsmemAtomicBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<BasicMemoryEvent> events;
    bool add_ok = false, exch_ok = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Seed rank 1 offset 0 with 0x10 via a normal store.
        auto tr = services->translate_shared(0, (1ULL << 24) | 0x0,
                                             shared_access(4, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        std::uint32_t seed = 0x10;
        auto st = services->write_shared(tr.value(), &seed);
        if (st.failed()) return Status::failure(Error::internal(
            st.take_error().describe()));
        // Atomic add 0x20: old must be 0x10, final 0x30.
        auto tr2 = services->translate_shared(0, (1ULL << 24) | 0x0,
                                              shared_access(4, AccessKind::kAtomic),
                                              SharedAccessMode::kDistributed);
        if (tr2.failed()) return Status::failure(Error::internal(
            tr2.take_error().describe()));
        std::uint32_t addv = 0x20, oldv = 0;
        st = services->atomic_shared(tr2.value(), AtomicOp::kAdd, &addv, &oldv);
        if (st.failed()) return Status::failure(Error::internal(
            st.take_error().describe()));
        add_ok = (oldv == 0x10);
        // Read back: must be 0x30.
        auto tr3 = services->translate_shared(0, (1ULL << 24) | 0x0,
                                              shared_access(4, AccessKind::kLoad),
                                              SharedAccessMode::kDistributed);
        if (tr3.failed()) return Status::failure(Error::internal(
            tr3.take_error().describe()));
        std::uint32_t back = 0;
        st = services->read_shared(tr3.value(), &back);
        if (st.failed()) return Status::failure(Error::internal(
            st.take_error().describe()));
        add_ok = add_ok && (back == 0x30);
        // Atomic exchange: old 0x30, new 0x99.
        std::uint32_t xv = 0x99, xold = 0;
        st = services->atomic_shared(tr2.value(), AtomicOp::kExch, &xv, &xold);
        if (st.failed()) return Status::failure(Error::internal(
            st.take_error().describe()));
        exch_ok = (xold == 0x30);
        return Status::success();
    }
    const char* name() const override { return "dsmematom2"; }
};

TEST(dsmem_true_atomic_rmw) {
    auto backend = std::make_shared<DsmemAtomicBackend>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->add_ok);
    CHECK(backend->exch_ok);
}

// A sink that records events emitted by the runtime's shared access path
// (High 7: events are automatic, not backend-assembled).
struct EventCollector : IEventSink {
    std::vector<BasicMemoryEvent> events;
    bool emit(const BasicMemoryEvent& ev) override {
        events.push_back(ev);
        return true;
    }
};

TEST(dsmem_auto_events_from_shared_access) {
    auto backend = std::make_shared<DsmemAtomicBackend>();
    auto collector = std::make_shared<EventCollector>();
    auto ctx = Context::create(backend);
    ctx.value().set_event_sink(collector.get());
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    // The backend did: 1 store + 1 atomic + 1 load + 1 atomic = 4 shared
    // accesses; each must have emitted an automatic event.
    CHECK(collector->events.size() == 4);
    std::size_t atomics = 0, stores = 0, loads = 0;
    bool dsmem_identity = true;
    for (const auto& ev : collector->events) {
        if (ev.access_kind == AccessKind::kAtomic) ++atomics;
        if (ev.access_kind == AccessKind::kStore) ++stores;
        if (ev.access_kind == AccessKind::kLoad) ++loads;
        // Every event must carry the DSMEM identity.
        if (ev.shared_mode != SharedAccessMode::kDistributed ||
            ev.source_cta != 0 || ev.target_rank != 1 ||
            ev.target_cta != 1 || ev.cluster_id != 0) {
            dsmem_identity = false;
        }
    }
    CHECK(atomics == 2 && stores == 1 && loads == 1);
    CHECK(dsmem_identity);
}

// ---------------------------------------------------------------------------
// Reviewer round 2 regressions
// ---------------------------------------------------------------------------

// Blocker 1: a translation minted by Context A replayed on Context B
// DURING B's backend launch must be rejected — the capability token
// embeds a Context-unique nonce, so identical allocation sequences still
// cannot cross contexts.
struct ReplayProbe : IBackend {
    IRuntimeServices* services = nullptr;
    TranslatedSharedAddress foreign;
    bool foreign_rejected = false;
    bool own_ok = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Mint our own (must work) then replay the foreign one.
        auto own = services->translate_shared(0, (1ULL << 24) | 0,
                                              shared_access(4, AccessKind::kStore),
                                              SharedAccessMode::kDistributed);
        if (own.failed()) return Status::failure(Error::internal(
            own.take_error().describe()));
        std::uint32_t v = 1;
        own_ok = services->write_shared(own.value(), &v).ok();
        // Replay Context A's translation (same allocation ids/VAs because
        // the allocator is deterministic; only the nonce differs).
        foreign_rejected = services->write_shared(foreign, &v).failed();
        return Status::success();
    }
    const char* name() const override { return "replay"; }
};

TEST(dsmem_cross_context_replay_during_launch) {
    // Minting probe: mints a translation during its launch and hands it
    // back for replay.
    struct MintProbe : IBackend {
        IRuntimeServices* services = nullptr;
        TranslatedSharedAddress captured;
        bool minted = false;
        void bind_runtime(IRuntimeServices* s) override { services = s; }
        Status launch(const BackendLaunchRequest& request) override {
            (void)request;
            auto tr = services->translate_shared(
                0, (1ULL << 24) | 0, shared_access(4, AccessKind::kStore),
                SharedAccessMode::kDistributed);
            if (tr.failed()) return Status::failure(Error::internal(
                tr.take_error().describe()));
            captured = tr.value();
            minted = true;
            return Status::success();
        }
        const char* name() const override { return "mint"; }
    };

    // Context A: identical deterministic allocation sequence.
    auto backend_a = std::make_shared<MintProbe>();
    auto ctx_a = Context::create(backend_a);
    auto mod_a = ctx_a.value().load_module(make_cluster_cubin(), "cl");
    auto fn_a = ctx_a.value().function(mod_a.value(), "_Z6clkernv");
    CHECK(ctx_a.ok() && mod_a.ok() && fn_a.ok());
    if (!ctx_a.ok() || !mod_a.ok() || !fn_a.ok()) return;
    auto pa = ctx_a.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(pa.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(pa.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto ra = ctx_a.value().launch(fn_a.value(), cfg, args);
    CHECK(ra.ok());
    if (!ra.ok()) return;
    CHECK(backend_a->minted);

    // Context B: same sequence (same allocation ids / VAs / topology), but
    // replaying A's translation during B's launch must be rejected — the
    // token embeds A's nonce.
    auto backend_b = std::make_shared<ReplayProbe>();
    backend_b->foreign = backend_a->captured;
    auto ctx_b = Context::create(backend_b);
    auto mod_b = ctx_b.value().load_module(make_cluster_cubin(), "cl");
    auto fn_b = ctx_b.value().function(mod_b.value(), "_Z6clkernv");
    CHECK(ctx_b.ok() && mod_b.ok() && fn_b.ok());
    if (!ctx_b.ok() || !mod_b.ok() || !fn_b.ok()) return;
    auto pb = ctx_b.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(pb.ok());
    std::vector<KernelArg> args_b = args;
    args_b[0] = KernelArg::pointer(pb.value(), "a");
    auto rb = ctx_b.value().launch(fn_b.value(), cfg, args_b);
    CHECK(rb.ok());
    if (!rb.ok()) return;
    CHECK(backend_b->own_ok);
    CHECK(backend_b->foreign_rejected);
}

// Blocker 2: kind-cross-reuse — a translation minted for one operation
// cannot be used for another.
struct KindCrossProbe : IBackend {
    IRuntimeServices* services = nullptr;
    bool load_on_write_rejected = false;
    bool store_on_read_rejected = false;
    bool load_on_atomic_rejected = false;
    bool atomic_on_write_rejected = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        const std::uint64_t logical = (1ULL << 24) | 0x0;
        // kLoad translation used for write.
        auto tl = services->translate_shared(0, logical,
                                             shared_access(4, AccessKind::kLoad),
                                             SharedAccessMode::kDistributed);
        if (tl.failed()) return Status::failure(Error::internal(
            tl.take_error().describe()));
        std::uint32_t v = 1;
        load_on_write_rejected = services->write_shared(tl.value(), &v).failed();
        // kStore translation used for read.
        auto ts = services->translate_shared(0, logical,
                                             shared_access(4, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (ts.failed()) return Status::failure(Error::internal(
            ts.take_error().describe()));
        std::uint32_t out = 0;
        store_on_read_rejected = services->read_shared(ts.value(), &out).failed();
        // kLoad translation used for atomic.
        load_on_atomic_rejected = services->atomic_shared(
            tl.value(), AtomicOp::kAdd, &v, nullptr).failed();
        // kAtomic translation used for plain write.
        auto ta = services->translate_shared(0, logical,
                                             shared_access(4, AccessKind::kAtomic),
                                             SharedAccessMode::kDistributed);
        if (ta.failed()) return Status::failure(Error::internal(
            ta.take_error().describe()));
        atomic_on_write_rejected = services->write_shared(ta.value(), &v).failed();
        return Status::success();
    }
    const char* name() const override { return "kindcross"; }
};

TEST(dsmem_kind_cross_reuse_rejected) {
    auto backend = std::make_shared<KindCrossProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->load_on_write_rejected);
    CHECK(backend->store_on_read_rejected);
    CHECK(backend->load_on_atomic_rejected);
    CHECK(backend->atomic_on_write_rejected);
}

// High 2: invalid enum values are rejected (mode + atomic op).
struct BadEnumProbe : IBackend {
    IRuntimeServices* services = nullptr;
    bool bad_mode_rejected = false;
    bool bad_op_rejected = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        auto tr = services->translate_shared(0, (1ULL << 24) | 0,
                                             shared_access(4, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        TranslatedSharedAddress t = tr.value();
        // Undefined mode value.
        t.mode = static_cast<SharedAccessMode>(0x42);
        std::uint32_t v = 1;
        bad_mode_rejected = services->write_shared(t, &v).failed();
        // Undefined atomic op value.
        t = tr.value();
        t.kind = AccessKind::kAtomic;
        bad_op_rejected = services->atomic_shared(
            t, static_cast<AtomicOp>(0x77), &v, nullptr).failed();
        return Status::success();
    }
    const char* name() const override { return "badenum"; }
};

TEST(dsmem_invalid_enums_rejected) {
    auto backend = std::make_shared<BadEnumProbe>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->bad_mode_rejected);
    CHECK(backend->bad_op_rejected);
}

// High 3: event-stop semantics — a sink returning false suppresses
// subsequent events; memory is committed (post-commit events).
struct StopSink : IEventSink {
    std::size_t emits = 0;
    std::size_t stop_after = 2;
    bool emit(const BasicMemoryEvent&) override {
        ++emits;
        return emits <= stop_after;
    }
};

TEST(dsmem_event_stop_semantics) {
    auto backend = std::make_shared<DsmemAtomicBackend>();
    auto sink = std::make_shared<StopSink>();
    auto ctx = Context::create(backend);
    ctx.value().set_event_sink(sink.get());
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    // The backend did 4 accesses; the sink returns false on its 3rd emit.
    // The runtime calls emit per committed access until the sink stops:
    // 3 calls (2 accepted + 1 stop signal), the 4th access is suppressed.
    // Memory is still committed (add/exch results OK).
    CHECK(sink->emits == 3);
    CHECK(backend->add_ok);
    CHECK(backend->exch_ok);
    CHECK(ctx.value().event_stopped());
}

// High 1: true atomicity — N threads × M atomic adds on the same word must
// sum exactly (no lost updates).
TEST(dsmem_atomic_rmw_multithreaded) {
    MemoryAllocator m;
    auto a = m.allocate(AddressSpace::kShared, 64, 16, "cta:0");
    CHECK(a.ok());
    if (!a.ok()) return;
    auto alloc = m.allocation_by_base(a.value());
    CHECK(alloc.ok());
    if (!alloc.ok()) return;
    const AllocationId aid = alloc.value().id;
    std::uint32_t zero = 0;
    CHECK(m.write_at(aid, 0, &zero, 4).ok());

    constexpr int kThreads = 8;
    constexpr int kAdds = 500;
    std::vector<std::thread> workers;
    for (int t = 0; t < kThreads; ++t) {
        workers.emplace_back([&]() {
            for (int i = 0; i < kAdds; ++i) {
                std::uint32_t one = 1;
                auto st = m.atomic_rmw(aid, 0, 4, AtomicOp::kAdd, &one,
                                       nullptr);
                CHECK(st.ok());
            }
        });
    }
    for (auto& w : workers) w.join();

    std::uint32_t final = 0;
    CHECK(m.read_at(aid, 0, &final, 4).ok());
    // Exactly kThreads * kAdds — no lost updates.
    CHECK(final == kThreads * kAdds);
}

// ---------------------------------------------------------------------------
// Codex review round 3: capability token width + overflow boundaries
// ---------------------------------------------------------------------------

// A probe that mints a translation DURING its launch and immediately uses
// it (the only valid window for shared access), recording both the minted
// identity and whether the access succeeded.
struct MintForBoundary : IBackend {
    IRuntimeServices* services = nullptr;
    TranslatedSharedAddress minted;
    bool minted_ok = false;
    bool access_ok = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        auto tr = services->translate_shared(0, (1ULL << 24) | 0,
                                             shared_access(4, AccessKind::kStore),
                                             SharedAccessMode::kDistributed);
        if (tr.failed()) return Status::failure(Error::internal(
            tr.take_error().describe()));
        minted = tr.value();
        minted_ok = true;
        // Use the minted translation inside the launch: with the full-width
        // nonce this must succeed (defect 1 would reject it).
        std::uint32_t v = 0x42;
        access_ok = services->write_shared(tr.value(), &v).ok();
        return Status::success();
    }
    const char* name() const override { return "mintbound"; }
};

// Nonce >= 2^32 must not truncate: a Context with a large nonce mints and
// validates its own translations (defect 1 regression).
TEST(dsmem_token_full_width_nonce) {
    for (const std::uint64_t nonce : {std::uint64_t{0xFFFFFFFF},
                                      std::uint64_t{0x100000000}}) {
        auto backend = std::make_shared<MintForBoundary>();
        auto ctx = Context::create(backend);
        ctx.value().debug_set_counters(nonce, 1);
        auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
        auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
        CHECK(ctx.ok() && mod.ok() && fn.ok());
        if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
        auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
        CHECK(ptr.ok());
        std::vector<KernelArg> args;
        args.push_back(KernelArg::pointer(ptr.value(), "a"));
        args.push_back(KernelArg::integer(1, "b"));
        args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
        args.push_back(KernelArg::integer(1, "n"));
        LaunchConfig cfg;
        cfg.grid_x = 4;
        cfg.grid_y = 2;
        auto r = ctx.value().launch(fn.value(), cfg, args);
        CHECK(r.ok());
        if (!r.ok()) return;
        CHECK(backend->minted_ok);
        // The minted translation must carry the full nonce (no truncation).
        CHECK(backend->minted.context_nonce == nonce);
        // generation = injected (1) + the launch's increment = 2.
        CHECK(backend->minted.launch_generation == 2);
        // And it must validate for its own Context during the launch
        // (defect 1: the old truncated token compared against the full
        // nonce would have rejected its own minted translation).
        CHECK(backend->access_ok);
    }
}

// Generation near UINT64_MAX: minting at the max generation is legal, but
// the next launch must fail with a structured overflow error (never wrap,
// so a stale translation cannot re-validate after the counter moves).
TEST(dsmem_generation_overflow_is_error) {
    // A Context whose generation is already at UINT64_MAX-1: one launch
    // brings it to UINT64_MAX (mint legal), the next must overflow.
    auto backend = std::make_shared<MintForBoundary>();
    auto ctx = Context::create(backend);
    ctx.value().debug_set_counters(1, UINT64_MAX - 1);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    // First launch: generation UINT64_MAX-1 -> UINT64_MAX (legal); the
    // minted translation must validate within that launch.
    auto r1 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r1.ok());
    if (!r1.ok()) return;
    CHECK(ctx.value().debug_generation() == UINT64_MAX);
    CHECK(backend->access_ok);
    // Second launch: incrementing UINT64_MAX overflows -> structured error.
    auto r2 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r2.failed());
    if (r2.failed()) {
        Error e = r2.take_error();
        CHECK(e.code() == ErrorCode::kOutOfRange);
        CHECK(e.describe().find("launch generation") != std::string::npos);
    }
}

// A translation minted at generation N must be rejected when replayed
// during the NEXT launch's backend callback (generation N+1), while a
// freshly minted translation at N+1 works (codex round 3: real replay).
struct GenerationReplayProbe : IBackend {
    IRuntimeServices* services = nullptr;
    TranslatedSharedAddress previous;   // minted at the previous launch
    std::optional<ErrorCode> previous_error;  // code of the replay failure
    bool fresh_ok = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        (void)request;
        // Replay the translation minted at the previous launch generation.
        std::uint32_t v = 0x11;
        Status r = services->write_shared(previous, &v);
        if (r.ok()) {
            previous_error = std::nullopt;
        } else {
            previous_error = r.take_error().code();
        }
        // Mint + use a fresh translation at the current generation.
        auto fresh = services->translate_shared(0, (1ULL << 24) | 0x4,
                                                shared_access(4, AccessKind::kStore),
                                                SharedAccessMode::kDistributed);
        if (fresh.failed()) return Status::failure(Error::internal(
            fresh.take_error().describe()));
        fresh_ok = services->write_shared(fresh.value(), &v).ok();
        return Status::success();
    }
    const char* name() const override { return "genreplay"; }
};

TEST(dsmem_previous_generation_translation_invalid_after_next_launch) {
    // Same-context generation-advance replay: launch 1 (MintForBoundary)
    // mints a generation-1 translation; launch 2 on the SAME Context with a
    // replay backend replays it during the backend callback.  The
    // generation advanced to 2, so the gen1 replay must be rejected with
    // kLifecycle while a fresh gen2 translation works.
    auto backend1 = std::make_shared<MintForBoundary>();
    auto ctx = Context::create(backend1);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;
    auto r1 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r1.ok());
    if (!r1.ok()) return;
    const TranslatedSharedAddress gen1 = backend1->minted;
    CHECK(gen1.launch_generation == 1);

    // Launch 2 on the SAME Context with a replay backend.
    auto backend2 = std::make_shared<GenerationReplayProbe>();
    backend2->previous = gen1;
    ctx.value().debug_set_backend(backend2);
    auto r2 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r2.ok());
    if (!r2.ok()) return;
    // The gen1 replay inside the gen2 backend callback must be rejected,
    // and the fresh gen2 translation must succeed.
    // The replay must fail specifically with kLifecycle (stale/foreign
    // capability), not any incidental error.
    CHECK(backend2->previous_error.has_value());
    if (backend2->previous_error.has_value()) {
        CHECK(*backend2->previous_error == ErrorCode::kLifecycle);
    }
    CHECK(backend2->fresh_ok);
}

// High-1 regression: an overflow launch leaves NO leaked shared allocations
// and NO active-launch state, and the backend is never invoked.
struct CountingBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::size_t launches = 0;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest&) override {
        ++launches;
        return Status::success();
    }
    const char* name() const override { return "counting"; }
};

TEST(dsmem_generation_overflow_no_leak_no_active_state) {
    auto backend = std::make_shared<CountingBackend>();
    auto ctx = Context::create(backend);
    ctx.value().debug_set_counters(7, UINT64_MAX - 1);
    auto mod = ctx.value().load_module(make_cluster_cubin(), "cl");
    auto fn = ctx.value().function(mod.value(), "_Z6clkernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    LaunchConfig cfg;
    cfg.grid_x = 4;
    cfg.grid_y = 2;

    // Baseline live shared allocations before the overflow launch.
    std::size_t live_shared_before = 0;
    for (const auto& al : ctx.value().memory().allocations()) {
        if (al.alive && al.space == AddressSpace::kShared) ++live_shared_before;
    }
    // Launch 1: gen UINT64_MAX-1 -> UINT64_MAX (legal).
    auto r1 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r1.ok());
    if (!r1.ok()) return;
    CHECK(backend->launches == 1);
    // Launch 2: overflow -> error BEFORE any allocation/backend call.
    auto r2 = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r2.failed());
    if (r2.failed()) {
        Error e = r2.take_error();
        CHECK(e.code() == ErrorCode::kOutOfRange);
        CHECK(e.describe().find("launch generation") != std::string::npos);
    }
    // No leaked shared allocations (overflow path allocated nothing).
    std::size_t live_shared_after = 0;
    for (const auto& al : ctx.value().memory().allocations()) {
        if (al.alive && al.space == AddressSpace::kShared) ++live_shared_after;
    }
    CHECK(live_shared_after == live_shared_before);
    // Backend never invoked for the overflow launch.
    CHECK(backend->launches == 1);
    // shared_topology() reports a disabled (non-active) topology.
    CHECK(!ctx.value().shared_topology().enabled());
    // translate_shared after the overflow -> kIllegalState (no active state).
    auto tr = ctx.value().translate_shared(0, (1ULL << 24) | 0,
                                           shared_access(4, AccessKind::kStore),
                                           SharedAccessMode::kDistributed);
    CHECK(tr.failed());
    if (tr.failed()) {
        Error e = tr.take_error();
        CHECK(e.code() == ErrorCode::kIllegalState);
    }
}

// High-2 regression: the nonce allocator must never wrap or hand out 0.
// Exercises the real claim() path at the exhaustion boundary and a
// multithreaded race on the last available nonce (codex round 4).
TEST(context_nonce_exhaustion_is_error) {
    // 1. UINT64_MAX-1 claims successfully; the next claim returns
    //    kOutOfRange; UINT64_MAX and 0 are never handed out.
    {
        NonceAllocator alloc;
        alloc.debug_set(UINT64_MAX - 1);
        auto a = alloc.claim();
        CHECK(a.ok());
        if (a.ok()) CHECK(a.value() == UINT64_MAX - 1);
        // UINT64_MAX itself is never handed out.
        CHECK(alloc.debug_value() == UINT64_MAX);
        auto b = alloc.claim();
        CHECK(b.failed());
        if (b.failed()) {
            Error e = b.take_error();
            CHECK(e.code() == ErrorCode::kOutOfRange);
            CHECK(e.describe().find("nonce") != std::string::npos);
        }
    }
    // 2. Never hands out 0 (starts at 1).
    {
        NonceAllocator alloc;
        auto c0 = alloc.claim();
        CHECK(c0.ok());
        if (c0.ok()) {
            CHECK(c0.value() != 0);
            CHECK(c0.value() == 1);
        }
    }
    // 3. Multithreaded race on the last available nonce: exactly one of
    //    N threads succeeds; the rest get kOutOfRange.
    {
        constexpr int kThreads = 16;
        NonceAllocator alloc;
        alloc.debug_set(UINT64_MAX - 1);  // only one claim left
        std::atomic<int> successes{0};
        std::atomic<int> out_of_range{0};
        std::vector<std::thread> workers;
        for (int i = 0; i < kThreads; ++i) {
            workers.emplace_back([&]() {
                auto r = alloc.claim();
                if (r.ok()) {
                    ++successes;
                } else {
                    Error e = r.take_error();
                    if (e.code() == ErrorCode::kOutOfRange) ++out_of_range;
                    else {
                        std::fprintf(stderr,
                                     "nonce race unexpected error: %s\n",
                                     e.describe().c_str());
                    }
                }
            });
        }
        for (auto& w : workers) w.join();
        CHECK(successes == 1);
        CHECK(out_of_range == kThreads - 1);
    }
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-cluster");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu cluster DSMEM tests\n");
    }
    return failures == 0 ? 0 : 1;
}
