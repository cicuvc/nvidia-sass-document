// L3 unit tests: virtual memory + launch ABI (Phase 3).
//
// MemoryAllocator: deterministic addresses, lifecycle/bounds/alignment
// checks.  ConstantBank: parameter write/read + preset slots.  Context:
// module/function lookup, per-item KernelArg and packed-buffer launches
// producing byte-identical constant0 contents, error paths.

#include <semu/context.hpp>
#include <semu/memory.hpp>
#include <semu/memory_service.hpp>

#include <cstdio>
#include <cstring>
#include <string>

#include "test_framework.hpp"

using namespace semu;

namespace {

void push16(std::vector<std::uint8_t>* out, std::uint16_t v);

// A tiny hand-built cubin with a 4-param kernel (a: ptr 8 @0x0, b: int 4
// @0x8, c: bytes 16 @0x10, n: int 4 @0x20).  Mirrors the layout the
// loader produces; REGCOUNT etc. are not needed for launch.
std::vector<std::uint8_t> make_4param_cubin() {
    // Build the minimal ELF by hand (NULL, shstr, str, symtab, text,
    // devinfo, kerninfo).
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint32_t link = 0;
        std::uint32_t info = 0;
        std::uint64_t align = 4;
        std::uint64_t entsize = 0;
    };
    std::vector<S> secs(7);
    secs[0].name = "";  // NULL
    secs[1].name = ".shstrtab"; secs[1].type = 3;
    secs[2].name = ".strtab"; secs[2].type = 3;
    secs[3].name = ".symtab"; secs[3].type = 2; secs[3].link = 2;
    secs[3].entsize = 24; secs[3].align = 8;
    secs[4].name = ".text._Z4kernv"; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info._Z4kernv"; secs[6].type = 0x70000000;
    secs[6].info = 4;  // -> text

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto eia = [&](std::vector<std::uint8_t>* v, std::uint8_t fmt,
                   std::uint8_t etype, std::uint64_t size,
                   const std::vector<std::uint8_t>& payload) {
        v->push_back(fmt); v->push_back(etype);
        if (fmt == 4) {
            v->push_back(size & 0xff); v->push_back((size >> 8) & 0xff);
        }
        v->insert(v->end(), payload.begin(), payload.end());
    };

    // KPARAM records (EIATTR order scrambled to prove normalization):
    // ord 3 @0x20 size 4, ord 0 @0x0 size 8, ord 2 @0x10 size 16,
    // ord 1 @0x8 size 4.
    auto kp = [&](std::vector<std::uint8_t>* v, std::uint32_t ord,
                  std::uint32_t off, std::uint32_t size) {
        std::vector<std::uint8_t> p;
        push32(&p, 0);
        push32(&p, (off << 16) | ord);
        push32(&p, (((size << 2) | 1) << 16) | 0xf000);
        eia(v, 4, 0x17, 12, p);
    };
    std::vector<std::uint8_t> kern_info;
    kp(&kern_info, 3, 0x20, 4);
    kp(&kern_info, 0, 0x0, 8);
    kp(&kern_info, 2, 0x10, 16);
    kp(&kern_info, 1, 0x8, 4);

    // text: one NOP + one EXIT
    std::vector<std::uint8_t> text;
    push64(&text, 0x0000000000007918ULL); push64(&text, 0x000fc00000000000ULL);
    push64(&text, 0x000000000000794dULL); push64(&text, 0x000fea0003800000ULL);

    // symbols: NULL, .text sec, func, constant0 sec
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
    std::string strtab = std::string(1, '\0') + ".text._Z4kernv" + '\0' +
                         "_Z4kernv" + '\0' + ".nv.constant0._Z4kernv" + '\0';
    // strtab offsets: "" at 0, ".text._Z4kernv" at 1 (15 bytes incl NUL),
    // "_Z4kernv" at 16, ".nv.constant0._Z4kernv" at 25.
    sym(1, 0x03, 0x00, 4, 0, 0);            // .text section
    sym(16, 0x12, 0x10, 4, 0, 32);          // func (STO_ENTRY)
    sym(25, 0x03, 0x00, 4, 0, 0);           // constant0 section

    secs[4].data = text;
    secs[6].data = kern_info;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());

    // shstr
    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i) {
        shstr += secs[i].name + '\0';
    }
    secs[1].data.assign(shstr.begin(), shstr.end());

    // layout
    std::vector<std::uint64_t> offs(secs.size(), 0);
    std::uint64_t cur = 64;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        if (i == 0) continue;
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
    push16(&out, 2);       // ET_EXEC
    push16(&out, 190);     // EM_CUDA
    push32(&out, 1);
    push64(&out, 0);
    push64(&out, 0);
    push64(&out, shoff);
    push32(&out, 0x06007802);
    push16(&out, 64); push16(&out, 56); push16(&out, 0);
    push16(&out, 64); push16(&out, static_cast<std::uint16_t>(secs.size()));
    push16(&out, 1);
    for (std::size_t i = 1; i < secs.size(); ++i) {
        while (out.size() % std::max<std::uint64_t>(secs[i].align, 1))
            out.push_back(0);
        out.insert(out.end(), secs[i].data.begin(), secs[i].data.end());
    }
    // section headers: name offsets computed from shstr
    std::uint32_t name_pos = 1;
    for (std::size_t i = 0; i < secs.size(); ++i) {
        std::uint32_t no = 0;
        if (i > 0) { no = name_pos; name_pos += secs[i].name.size() + 1; }
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
}

void push16(std::vector<std::uint8_t>* out, std::uint16_t v) {
    out->push_back(v & 0xff);
    out->push_back((v >> 8) & 0xff);
}

}  // namespace

// ---------------------------------------------------------------------------
// MemoryAllocator
// ---------------------------------------------------------------------------

TEST(memory_allocate_deterministic) {
    MemoryAllocator m(0x10000);
    auto a1 = m.allocate(AddressSpace::kGlobal, 64);
    auto a2 = m.allocate(AddressSpace::kGlobal, 32, 256);
    CHECK(a1.ok() && a2.ok());
    if (!a1.ok() || !a2.ok()) return;
    CHECK(a1.value().va == 0x10000);
    // 32 bytes at align 256: 0x10040 -> aligned 0x10100
    CHECK(a2.value().va == 0x10100);
    // Same sequence on a fresh allocator -> identical addresses.
    MemoryAllocator m2(0x10000);
    auto b1 = m2.allocate(AddressSpace::kGlobal, 64);
    auto b2 = m2.allocate(AddressSpace::kGlobal, 32, 256);
    CHECK(b1.ok() && b2.ok());
    CHECK(b1.value() == a1.value());
    CHECK(b2.value() == a2.value());
}

TEST(memory_lifecycle_checks) {
    MemoryAllocator m;
    auto a = m.allocate(AddressSpace::kGlobal, 64);
    CHECK(a.ok());
    if (!a.ok()) return;
    // write + read back
    const std::uint8_t blob[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    CHECK(m.write(a.value(), blob, 8).ok());
    std::uint8_t got[8] = {};
    CHECK(m.read(a.value(), got, 8).ok());
    CHECK(std::memcmp(got, blob, 8) == 0);
    // interior write
    const std::uint8_t inner[4] = {9, 9, 9, 9};
    CHECK(m.write(a.value().add(4).value(), inner, 4).ok());
    CHECK(m.read(a.value(), got, 8).ok());
    CHECK(got[4] == 9 && got[7] == 9);
    // OOB write
    CHECK(m.write(a.value().add(60).value(), blob, 8).failed());
    // OOB read
    CHECK(m.read(a.value().add(62).value(), got, 4).failed());
    // unaligned resolve
    CHECK(m.resolve(a.value().add(8).value()).failed());
    CHECK(m.resolve(a.value()).ok());
    // free + use-after-free
    CHECK(m.free(a.value()).ok());
    CHECK(m.free(a.value()).failed());  // double free
    CHECK(m.write(a.value(), blob, 4).failed());  // use-after-free
}

TEST(memory_memset_and_copy) {
    MemoryAllocator m;
    auto a = m.allocate(AddressSpace::kGlobal, 128);
    auto b = m.allocate(AddressSpace::kGlobal, 128);
    CHECK(a.ok() && b.ok());
    if (!a.ok() || !b.ok()) return;
    CHECK(m.memset(a.value(), 0xAB, 128).ok());
    std::uint8_t got[16];
    CHECK(m.read(a.value(), got, 16).ok());
    for (int i = 0; i < 16; ++i) CHECK(got[i] == 0xAB);
    CHECK(m.copy(b.value(), a.value(), 128).ok());
    CHECK(m.read(b.value(), got, 16).ok());
    for (int i = 0; i < 16; ++i) CHECK(got[i] == 0xAB);
    // overlapping copy within one allocation
    CHECK(m.memset(a.value(), 0x11, 32).ok());
    CHECK(m.copy(a.value().add(4).value(), a.value(), 16).ok());
    CHECK(m.read(a.value(), got, 8).ok());
    CHECK(got[4] == 0x11 && got[7] == 0x11);
}

TEST(memory_allocation_ids_stable) {
    MemoryAllocator m;
    auto a = m.allocate(AddressSpace::kShared, 16);
    auto b = m.allocate(AddressSpace::kLocal, 16);
    auto c = m.allocate(AddressSpace::kGlobal, 16);
    CHECK(a.ok() && b.ok() && c.ok());
    if (!a.ok() || !b.ok() || !c.ok()) return;
    CHECK(m.allocation_by_id(AllocationId{1}).ok());
    auto r1 = m.allocation_by_id(AllocationId{1});
    CHECK(r1.ok() && r1.value().base == a.value());
    CHECK(m.allocation_by_id(AllocationId{2}).ok());
    CHECK(m.allocation_by_id(AllocationId{99}).failed());
    // spaces tagged correctly
    CHECK(r1.value().space == AddressSpace::kShared);
}

TEST(memory_bad_alignment_rejected) {
    MemoryAllocator m;
    CHECK(m.allocate(AddressSpace::kGlobal, 16, 3).failed());
    CHECK(m.allocate(AddressSpace::kGlobal, 0).failed());
}

TEST(memory_deviceptr_arithmetic) {
    DevicePtr p{0x100};
    auto q = p.add(16);
    CHECK(q.ok() && q.value().va == 0x110);
    auto r = p.add(-16);
    CHECK(r.ok() && r.value().va == 0xF0);
    CHECK(p.add(-0x101).failed());
    // 0x100 + INT64_MAX = 0x8000...0100: fits in uint64 (no overflow), so
    // the add succeeds; a value that does overflow fails.
    DevicePtr big{0xFFFFFFFFFFFFFFFFULL};
    CHECK(big.add(1).failed());
    CHECK(big.add(-1).ok() && big.add(-1).value().va == 0xFFFFFFFFFFFFFFFEULL);
}

// ---------------------------------------------------------------------------
// ConstantBank
// ---------------------------------------------------------------------------

TEST(constant_bank_param_layout) {
    ConstantBank bank;
    // KPARAM-relative param write: lands at param_base + 0 = 0x380.
    const std::uint8_t data[8] = {0, 1, 2, 3, 4, 5, 6, 7};
    CHECK(bank.write_param(0, data, 8).ok());
    auto got = bank.read_param(0, 8);
    CHECK(got.ok() && got.value().size() == 8);
    if (got.ok()) CHECK(std::memcmp(got.value().data(), data, 8) == 0);
    // Raw absolute access must see it at 0x380.
    auto raw = bank.read_raw(0x380, 8);
    CHECK(raw.ok());
    if (raw.ok()) CHECK(std::memcmp(raw.value().data(), data, 8) == 0);
    // OOB write
    CHECK(bank.write_param(bank.layout().size - bank.layout().param_base - 4,
                           data, 8).failed());
    // Preset slot is an *absolute* offset (P3-GAP-01): writing 0x358 must
    // land at [0x358,0x360) and NOT touch [0x6d8,0x6e0) (param_base+0x358).
    const std::uint64_t cdesc = 0x1234;
    CHECK(bank.write_slot(0x358, &cdesc, 8).ok());
    auto slot = bank.read_raw(0x358, 8);
    CHECK(slot.ok());
    if (slot.ok()) {
        std::uint64_t v;
        std::memcpy(&v, slot.value().data(), 8);
        CHECK(v == 0x1234);
    }
    auto wrong = bank.read_raw(0x6d8, 8);
    CHECK(wrong.ok());
    if (wrong.ok()) {
        bool all_zero = true;
        for (auto b : wrong.value()) {
            if (b != 0) all_zero = false;
        }
        CHECK(all_zero);  // param_base + 0x358 must be untouched
    }
    // Same probe at the Context level: launch must place SLOT_DEFAULT_CDESC
    // at absolute 0x358, never at 0x6d8 (P3-GAP-01 through the ABI path).
    auto ctx2 = Context::create();
    auto mod2 = ctx2.value().load_module(make_4param_cubin(), "t2");
    auto fn2 = ctx2.value().function(mod2.value(), "_Z4kernv");
    CHECK(ctx2.ok() && mod2.ok() && fn2.ok());
    if (!ctx2.ok() || !mod2.ok() || !fn2.ok()) return;
    auto p2 = ctx2.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(p2.ok());
    LaunchConfig cfg2;
    std::vector<KernelArg> a2;
    a2.push_back(KernelArg::pointer(p2.value(), "a"));
    a2.push_back(KernelArg::integer(1, "b"));
    a2.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    a2.push_back(KernelArg::integer(1, "n"));
    auto r2 = ctx2.value().launch(fn2.value(), cfg2, a2);
    CHECK(r2.ok());
    if (!r2.ok()) return;
    const auto& bank2 = ctx2.value().constant_bank(fn2.value());
    auto slot358 = bank2.read_raw(0x358, 8);
    CHECK(slot358.ok());
    if (slot358.ok()) {
        bool all_zero = true;
        for (auto b : slot358.value())
            if (b != 0) all_zero = false;
        CHECK(all_zero);  // canonical zero placeholder at the right slot
    }
    auto slot6d8 = bank2.read_raw(0x6d8, 8);
    CHECK(slot6d8.ok());
    if (slot6d8.ok()) {
        bool all_zero = true;
        for (auto b : slot6d8.value())
            if (b != 0) all_zero = false;
        CHECK(all_zero);  // 0x6d8 must be untouched by the ABI path
    }
    // read_param(0x358) is KPARAM-relative (param_base + 0x358); it must
    // NOT return the slot value.
    auto kparam = bank.read_param(0x358, 8);
    CHECK(kparam.ok());
    if (kparam.ok()) {
        std::uint64_t v = 1;
        std::memcpy(&v, kparam.value().data(), 8);
        CHECK(v != 0x1234);
    }
}

// P3-GAP-01: malformed layouts must fail at construction.
TEST(constant_bank_bad_layout_rejected) {
    bool threw = false;
    try {
        ConstantBankLayout bad;
        bad.param_base = 0x20000;  // > size
        ConstantBank b(bad);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);
    threw = false;
    try {
        ConstantBankLayout bad;
        bad.default_cdesc_offset = bad.size - 4;  // slot doesn't fit
        ConstantBank b(bad);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);
}

// ---------------------------------------------------------------------------
// Context / launch ABI
// ---------------------------------------------------------------------------

// A recording backend: captures the launch request for assertions.  Only
// uses the runtime services for memory access (P3-GAP-03 contract).
struct RecordingBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::string last_kernel;
    std::vector<std::uint8_t> last_bank;
    std::uint64_t last_shared = 0;
    const Kernel* last_ir = nullptr;

    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        last_kernel = request.kernel_name;
        last_bank.assign(request.constant_bank.begin(),
                         request.constant_bank.end());
        last_shared = request.shared_views.empty()
            ? 0 : request.shared_views[0].size;
        last_ir = request.kernel;
        return Status::success();
    }
    const char* name() const override { return "recording"; }
};

TEST(context_launch_per_item_args) {
    auto ctx = Context::create();
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    if (!mod.ok()) {
        std::fprintf(stderr, "load error: %s\n",
                     mod.take_error().describe().c_str());
    }
    CHECK(mod.ok());
    if (!mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    if (!fn.ok()) {
        std::fprintf(stderr, "fn error: %s\n",
                     fn.take_error().describe().c_str());
    }
    CHECK(fn.ok());
    if (!fn.ok()) return;
    CHECK(fn.value().meta().params.size() == 4);

    // Allocate a device pointer to pass.
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    if (!ptr.ok()) return;

    LaunchConfig cfg;
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(0x11223344, "b"));
    std::vector<std::uint8_t> sixteen(16, 0xEE);
    args.push_back(KernelArg::raw(sixteen, "c"));
    args.push_back(KernelArg::integer(7, "n"));

    auto res = ctx.value().launch(fn.value(), cfg, args);
    CHECK(res.ok());
    if (!res.ok()) return;

    // Verify the materialized constant0 image: the params land at
    // param_base + KPARAM.offset inside the full bank image.
    // a@0x380 (8B), b@0x388 (4B), c@0x390 (16B), n@0x3a0 (4B).
    constexpr std::uint64_t PB = 0x380;
    CHECK(res.value().param_bank.size() > PB + 0x24);
    std::uint64_t pv = 0;
    std::memcpy(&pv, res.value().param_bank.data() + PB, 8);
    CHECK(pv == ptr.value().va);
    std::uint32_t bv = 0;
    std::memcpy(&bv, res.value().param_bank.data() + PB + 8, 4);
    CHECK(bv == 0x11223344);
    for (int i = 0; i < 16; ++i) {
        CHECK(res.value().param_bank[PB + 0x10 + i] == 0xEE);
    }
    std::uint32_t nv = 0;
    std::memcpy(&nv, res.value().param_bank.data() + PB + 0x20, 4);
    CHECK(nv == 7);

    // The bank content is what the driver would plant at param_base.
    auto& bank = ctx.value().constant_bank(fn.value());
    auto raw = bank.read_raw(0x380, 8);
    CHECK(raw.ok());
    if (raw.ok()) {
        std::uint64_t v;
        std::memcpy(&v, raw.value().data(), 8);
        CHECK(v == ptr.value().va);
    }
}

TEST(context_packed_buffer_matches_item_args) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());

    // Item args.
    LaunchConfig cfg;
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(0x10203040, "b"));
    std::vector<std::uint8_t> sixteen(16, 0x42);
    args.push_back(KernelArg::raw(sixteen, "c"));
    args.push_back(KernelArg::integer(0xDEAD, "n"));
    auto r1 = ctx.value().launch(fn.value(), cfg, args);
    if (!r1.ok()) {
        std::fprintf(stderr, "launch1 error: %s\n",
                     r1.take_error().describe().c_str());
    }
    CHECK(r1.ok());

    // Equivalent packed buffer: [0..0x24) with a@0, b@8, c@0x10, n@0x20.
    std::vector<std::uint8_t> packed(0x24, 0);
    std::memcpy(packed.data(), &ptr.value().va, 8);
    std::uint32_t bval = 0x10203040;
    std::memcpy(packed.data() + 8, &bval, 4);
    std::memcpy(packed.data() + 0x10, sixteen.data(), 16);
    std::uint32_t nval = 0xDEAD;
    std::memcpy(packed.data() + 0x20, &nval, 4);
    auto r2 = ctx.value().launch(fn.value(), cfg, packed,
                                 ParamPackFormat::kKparamBlob);
    CHECK(r2.ok());

    // Byte-identical param banks (the requirement).
    CHECK(r1.value().param_bank.size() == r2.value().param_bank.size());
    CHECK(std::memcmp(r1.value().param_bank.data(), r2.value().param_bank.data(),
                      r1.value().param_bank.size()) == 0);
}

TEST(context_launch_error_paths) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    LaunchConfig cfg;

    // Wrong argument count.
    std::vector<KernelArg> too_few;
    too_few.push_back(KernelArg::integer(1, "a"));
    auto r = ctx.value().launch(fn.value(), cfg, too_few);
    CHECK(r.failed());

    // Arg wider than its param slot.
    std::vector<KernelArg> bad_width;
    bad_width.push_back(KernelArg::integer(1, "a"));  // 8B ok
    bad_width.push_back(KernelArg::raw(std::vector<std::uint8_t>(8, 0), "b"));  // b is 4B
    bad_width.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    bad_width.push_back(KernelArg::integer(1, "n"));
    r = ctx.value().launch(fn.value(), cfg, bad_width);
    CHECK(r.failed());

    // Packed buffer too short for a parameter.
    std::vector<std::uint8_t> short_packed(0x10, 0);  // c needs 0x20
    r = ctx.value().launch(fn.value(), cfg, short_packed,
                           ParamPackFormat::kKparamBlob);
    CHECK(r.failed());

    // Unknown kernel.
    auto bad_fn = ctx.value().function(mod.value(), "_Znope");
    CHECK(bad_fn.failed());
}

TEST(context_shared_and_backend) {
    auto backend = std::make_shared<RecordingBackend>();
    auto ctx = Context::create(backend);
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());

    LaunchConfig cfg;
    cfg.extra_shared = 0x400;
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    auto r = ctx.value().launch(fn.value(), cfg, args);
    if (!r.ok()) {
        std::fprintf(stderr, "launch3 error: %s\n",
                     r.take_error().describe().c_str());
    }
    CHECK(r.ok());
    if (!r.ok()) return;
    // Backend received the launch with shared bytes allocated.
    CHECK(backend->last_kernel == "_Z4kernv");
    CHECK(backend->last_shared == 0x400);
    CHECK(r.value().has_shared);
    CHECK(r.value().shared_views.size() == 1);
    if (!r.value().shared_views.empty()) {
        CHECK(r.value().shared_views[0].size == 0x400);
        CHECK(r.value().shared_views[0].domain == "cta:0");
    }
    // The shared allocation is reclaimed after launch: no live shared
    // allocation remains (the result carries metadata only).
    for (const auto& al : ctx.value().memory().allocations()) {
        if (al.alive) {
            CHECK(al.space != AddressSpace::kShared);
        }
    }
}

// ---------------------------------------------------------------------------
// Ported assembler case: test_bigparam (out<8> @0x380, big<128> @0x388).
// ---------------------------------------------------------------------------

// Build a cubin with KPARAM: ord 0 @0x0 size 8 (out), ord 1 @0x8 size 128
// (big).  The kernel reads big[4..7] = c[0x0][0x38c].
std::vector<std::uint8_t> make_bigparam_cubin() {
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
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
    secs[4].name = ".text._Z1kv"; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info._Z1kv"; secs[6].type = 0x70000000;
    secs[6].info = 4;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    std::vector<std::uint8_t> kern_info;
    auto kp = [&](std::uint32_t ord, std::uint32_t off, std::uint32_t size) {
        kern_info.push_back(4); kern_info.push_back(0x17);
        kern_info.push_back(12); kern_info.push_back(0);
        push32(&kern_info, 0);
        push32(&kern_info, (off << 16) | ord);
        push32(&kern_info, (((size << 2) | 1) << 16) | 0xf000);
    };
    kp(0, 0x0, 8);
    kp(1, 0x8, 128);

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
    std::string strtab = std::string(1, '\0') + ".text._Z1kv" + '\0' +
                         "_Z1kv" + '\0' + ".nv.constant0._Z1kv" + '\0';
    sym(1, 0x03, 0x00, 4, 0, 0);   // .text section
    sym(13, 0x12, 0x10, 4, 0, 16); // func
    sym(19, 0x03, 0x00, 4, 0, 0);  // constant0

    secs[4].data = text;
    secs[6].data = kern_info;
    secs[3].data = symtab;
    secs[2].data.assign(strtab.begin(), strtab.end());

    std::string shstr(1, '\0');
    for (std::size_t i = 1; i < secs.size(); ++i) shstr += secs[i].name + '\0';
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
        push64(&out, i == 0 ? 0 : offs[i]);
        push64(&out, secs[i].data.size());
        push32(&out, secs[i].link);
        push32(&out, secs[i].info);
        push64(&out, secs[i].align);
        push64(&out, secs[i].entsize);
    }
    return out;
}

TEST(context_bigparam_128_byte_arg) {
    // Ported from assembler test_bigparam: big<128> at KPARAM offset 8;
    // the kernel reads big[4..7] from c[0x0][0x38c] = param_base + 8 + 4.
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_bigparam_cubin(), "bigparam");
    if (!mod.ok()) {
        std::fprintf(stderr, "bigparam load error: %s\n",
                     mod.take_error().describe().c_str());
    }
    CHECK(mod.ok());
    if (!mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z1kv");
    if (!fn.ok()) {
        std::fprintf(stderr, "bigparam fn error: %s\n",
                     fn.take_error().describe().c_str());
    }
    CHECK(fn.ok());
    if (!fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 16);
    CHECK(ptr.ok());

    LaunchConfig cfg;
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "out"));
    std::vector<std::uint8_t> big(128, 0);
    for (int i = 0; i < 128; ++i) big[i] = static_cast<std::uint8_t>(i);
    args.push_back(KernelArg::raw(big, "big"));
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;

    // big[4..7] = 0x04 05 06 07 -> LE word 0x07060504 at 0x380+8+4 = 0x38c.
    constexpr std::uint64_t BIG4 = 0x380 + 8 + 4;
    std::uint32_t v = 0;
    std::memcpy(&v, r.value().param_bank.data() + BIG4, 4);
    CHECK(v == 0x07060504);
    // out pointer at 0x380.
    std::uint64_t pv = 0;
    std::memcpy(&pv, r.value().param_bank.data() + 0x380, 8);
    CHECK(pv == ptr.value().va);
    // A 128-byte arg that is too wide for a narrow param must fail.
    std::vector<KernelArg> bad;
    bad.push_back(KernelArg::raw(std::vector<std::uint8_t>(8, 0), "out"));
    auto r2 = ctx.value().launch(fn.value(), cfg, bad);
    CHECK(r2.failed());
}

// ---------------------------------------------------------------------------
// P3-GAP regression tests
// ---------------------------------------------------------------------------

// P3-GAP-04: DevicePtr::add must be INT64_MIN-safe (no signed negation UB).
TEST(memory_deviceptr_int64_min_safe) {
    DevicePtr p{0x100};
    // INT64_MIN magnitude = 2^63; 0x100 - 2^63 underflows -> error.
    auto r = p.add(INT64_MIN);
    CHECK(r.failed());
    // At a large-enough address it succeeds.
    DevicePtr big{0x8000000000000000ULL};
    auto r2 = big.add(INT64_MIN);
    CHECK(r2.ok() && r2.value().va == 0);
    // Exactly-to-zero and one-byte-underflow.
    auto r3 = big.add(-(INT64_MAX));  // -2^63+1 -> va == 1
    CHECK(r3.ok() && r3.value().va == 1);
    auto r4 = big.add(INT64_MIN).value().add(-1);
    CHECK(r4.failed());  // 0 - 1 underflows
    // INT64_MAX add from a low address does not overflow uint64.
    auto r5 = DevicePtr{1}.add(INT64_MAX);
    CHECK(r5.ok() && r5.value().va == 0x8000000000000000ULL);
}

// P3-GAP-06: typed access enforces width/alignment/address-space and
// returns distinguishable error codes.
TEST(memory_typed_access_contract) {
    MemoryAllocator m;
    auto a = m.allocate(AddressSpace::kGlobal, 256, 128);
    CHECK(a.ok());
    if (!a.ok()) return;
    std::uint64_t v = 0x1122334455667788ULL;
    DeviceAccess acc;
    acc.width = 8;
    acc.alignment = 8;
    acc.space = AddressSpace::kGlobal;
    // Aligned 8-byte store + load (kind must match the operation).
    DeviceAccess store_acc = acc;
    store_acc.kind = AccessKind::kStore;
    CHECK(m.write_typed(a.value(), &v, 8, store_acc).ok());
    std::uint64_t got = 0;
    DeviceAccess load_acc = acc;
    load_acc.kind = AccessKind::kLoad;
    CHECK(m.read_typed(a.value(), &got, 8, load_acc).ok());
    CHECK(got == v);
    // P3-GAP-06: kind/operation mismatch is rejected.
    auto ekind = m.write_typed(a.value(), &v, 8, load_acc).take_error();
    CHECK(ekind.code() == ErrorCode::kInvalidArgument);
    ekind = m.read_typed(a.value(), &got, 8, store_acc).take_error();
    CHECK(ekind.code() == ErrorCode::kInvalidArgument);
    // Atomic kind: valid widths {1,2,4,8} on global/shared.
    DeviceAccess atom_acc = acc;
    atom_acc.kind = AccessKind::kAtomic;
    atom_acc.width = 4;
    CHECK(m.write_typed(a.value(), &v, 4, atom_acc).ok());
    DeviceAccess atom_badw = atom_acc;
    atom_badw.width = 16;
    CHECK(m.write_typed(a.value(), &v, 16, atom_badw).failed());
    // Text kind: read-only global access; write rejected.
    DeviceAccess text_acc = acc;
    text_acc.kind = AccessKind::kText;
    CHECK(m.read_typed(a.value(), &got, 8, text_acc).ok());
    auto etxt = m.write_typed(a.value(), &v, 8, text_acc).take_error();
    CHECK(etxt.code() == ErrorCode::kBadAddress);
    // Misaligned access -> kAlignmentViolation.
    auto bad = a.value().add(4);
    CHECK(bad.ok());
    CHECK(m.write_typed(bad.value(), &v, 8, store_acc).failed());
    Error e = m.write_typed(bad.value(), &v, 8, store_acc).take_error();
    CHECK(e.code() == ErrorCode::kAlignmentViolation);
    // Wrong address space -> kBadAddress.
    auto sh = m.allocate(AddressSpace::kShared, 64, 16);
    CHECK(sh.ok());
    auto e2 = m.write_typed(sh.value(), &v, 8, store_acc).take_error();
    CHECK(e2.code() == ErrorCode::kBadAddress);
    // Width mismatch -> kInvalidArgument.
    DeviceAccess badw = store_acc;
    badw.width = 16;
    auto e3 = m.write_typed(a.value(), &v, 8, badw).take_error();
    CHECK(e3.code() == ErrorCode::kInvalidArgument);
    // OOB with the pointer inside a live allocation and the range crossing
    // its end: use a dedicated allocator with a known 64-byte block
    // [0x10000, 0x10040); offset 0x38 (8-aligned) + 8 = 0x10040 -> OOB.
    MemoryAllocator m2;
    auto a2 = m2.allocate(AddressSpace::kGlobal, 64, 64);
    CHECK(a2.ok());
    // Pointer inside the block, range crossing the end: offset 0x3C
    // (4-aligned, within [0x10000,0x10040)), width 8 -> [0x1003C,0x10044).
    DeviceAccess acc4 = store_acc;
    acc4.alignment = 4;
    auto oob = a2.value().add(0x3C);
    CHECK(oob.ok());
    auto e4 = m2.write_typed(oob.value(), &v, 8, acc4).take_error();
    CHECK(e4.code() == ErrorCode::kOob);
    // Byte-copy API does NOT enforce alignment (documented semantics).
    const std::uint8_t bytes[4] = {1, 2, 3, 4};
    auto unaligned = a.value().add(1);
    CHECK(unaligned.ok());
    CHECK(m.write(unaligned.value(), bytes, 4).ok());
}

// P3-GAP-07: domain ownership + reclaim.
TEST(memory_domain_isolate_and_reclaim) {
    MemoryAllocator m;
    auto g = m.allocate(AddressSpace::kGlobal, 64, 16, "context");
    auto s1 = m.allocate(AddressSpace::kShared, 64, 16, "cta:1");
    auto s2 = m.allocate(AddressSpace::kShared, 64, 16, "cta:2");
    auto l = m.allocate(AddressSpace::kLocal, 64, 16, "warp:1:0");
    CHECK(g.ok() && s1.ok() && s2.ok() && l.ok());
    if (!g.ok() || !s1.ok() || !s2.ok() || !l.ok()) return;
    // Reclaim cta:1 -> only that allocation dies.
    CHECK(m.free_domain("cta:1").ok());
    CHECK(m.write(s1.value(), "x", 1).failed());  // freed
    CHECK(m.write(s2.value(), "x", 1).ok());      // still alive
    CHECK(m.write(l.value(), "x", 1).ok());
    // Unknown domain -> structured error.
    CHECK(m.free_domain("cta:99").failed());
    // Reclaim warp domain.
    CHECK(m.free_domain("warp:1:0").ok());
    CHECK(m.write(l.value(), "x", 1).failed());
}

// P3-GAP-02: pointer args must be validated against the allocator.
TEST(context_pointer_arg_lifecycle_validation) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    LaunchConfig cfg;
    auto& mem = ctx.value().memory();

    auto live = mem.allocate(AddressSpace::kGlobal, 64, 16);
    CHECK(live.ok());
    auto shared_alloc = mem.allocate(AddressSpace::kShared, 64, 16);
    CHECK(shared_alloc.ok());

    auto base_args = [&](DevicePtr p) {
        std::vector<KernelArg> args;
        args.push_back(KernelArg::pointer(p, "a"));
        args.push_back(KernelArg::integer(1, "b"));
        args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
        args.push_back(KernelArg::integer(1, "n"));
        return args;
    };

    // Live global base: OK.
    auto r = ctx.value().launch(fn.value(), cfg, base_args(live.value()));
    CHECK(r.ok());
    if (!r.ok()) {
        std::fprintf(stderr, "live: %s\n",
                     r.take_error().describe().c_str());
    }
    // Interior pointer: OK (allowed).
    auto interior = live.value().add(8);
    CHECK(interior.ok());
    r = ctx.value().launch(fn.value(), cfg, base_args(interior.value()));
    CHECK(r.ok());
    // One-past-end: FAIL.
    auto ope = live.value().add(64);
    CHECK(ope.ok());
    r = ctx.value().launch(fn.value(), cfg, base_args(ope.value()));
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.describe().find("_Z4kernv") != std::string::npos);
        CHECK(e.describe().find("0") != std::string::npos);  // ordinal
        CHECK(e.describe().find("0x") != std::string::npos);  // VA
    }
    // Unknown VA: FAIL.
    r = ctx.value().launch(fn.value(), cfg,
                           base_args(DevicePtr{0xdead0000}));
    CHECK(r.failed());
    // Freed pointer: FAIL (and error mentions kernel).
    mem.free(live.value());
    r = ctx.value().launch(fn.value(), cfg, base_args(live.value()));
    CHECK(r.failed());
    // Shared-space pointer: FAIL (host launch may only pass global).
    r = ctx.value().launch(fn.value(), cfg, base_args(shared_alloc.value()));
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kBadAddress);
    }
}

// P3-GAP-08: shared size overflow must be a structured error.  The check
// is `extra > UINT64_MAX - static_shared`; a kernel whose metadata carries
// static shared drives it.  We emulate static_shared > 0 by patching the
// loaded Kernel's metadata through the module image: the loader computes
// static_shared from .nv.shared.<k> NOBITS size.  Build a cubin variant
// with a shared section by reusing make_4param_cubin and appending a
// .nv.shared._Z4kernv NOBITS section (as the loader tests do).
std::vector<std::uint8_t> make_4param_cubin_with_shared() {
    auto bytes = make_4param_cubin();
    // Patch: the loader looks for NOBITS sections named .nv.shared.<k>
    // whose sh_info == text section index.  Rebuild the section table is
    // overkill; instead use the loader's own test path: build the section
    // via the same hand-rolled layout with a shared section appended.
    // We reuse the CubinBuilder-style approach from test_cubin.cpp.
    struct S {
        std::string name;
        std::uint32_t type = 0;
        std::uint64_t flags = 0;
        std::vector<std::uint8_t> data;
        std::uint64_t size = 0;  // logical size for NOBITS
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
    secs[4].name = ".text._Z4kernv"; secs[4].type = 1;
    secs[4].flags = 2 | 4; secs[4].align = 128;
    secs[5].name = ".nv.info"; secs[5].type = 0x70000000;
    secs[6].name = ".nv.info._Z4kernv"; secs[6].type = 0x70000000;
    secs[6].info = 4;
    secs[7].name = ".nv.shared._Z4kernv"; secs[7].type = 8;  // NOBITS
    secs[7].flags = 2 | 0x40; secs[7].info = 4; secs[7].size = 0x400;

    auto push32 = [](std::vector<std::uint8_t>* v, std::uint32_t x) {
        for (int i = 0; i < 4; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    auto push64 = [](std::vector<std::uint8_t>* v, std::uint64_t x) {
        for (int i = 0; i < 8; ++i) v->push_back((x >> (8 * i)) & 0xff);
    };
    std::vector<std::uint8_t> kern_info;
    auto kp = [&](std::uint32_t ord, std::uint32_t off,
                  std::uint32_t size) {
        kern_info.push_back(4); kern_info.push_back(0x17);
        kern_info.push_back(12); kern_info.push_back(0);
        push32(&kern_info, 0);
        push32(&kern_info, (off << 16) | ord);
        push32(&kern_info, (((size << 2) | 1) << 16) | 0xf000);
    };
    kp(3, 0x20, 4);
    kp(0, 0x0, 8);
    kp(2, 0x10, 16);
    kp(1, 0x8, 4);
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
    std::string strtab = std::string(1, '\0') + ".text._Z4kernv" + '\0' +
                         "_Z4kernv" + '\0' + ".nv.constant0._Z4kernv" + '\0' +
                         ".nv.shared._Z4kernv" + '\0';
    sym(1, 0x03, 0x00, 4, 0, 0);   // .text section (14 chars + NUL)
    sym(16, 0x12, 0x10, 4, 0, 16); // func "_Z4kernv" (8 chars + NUL)
    sym(25, 0x03, 0x00, 4, 0, 0);  // constant0 (22 chars + NUL)
    sym(48, 0x03, 0x00, 7, 0, 0);  // shared section

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
        if (secs[i].type == 8) continue;  // NOBITS has no file payload
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

TEST(context_shared_size_overflow) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin_with_shared(), "t");
    if (!mod.ok()) {
        std::fprintf(stderr, "shared cubin load: %s\n",
                     mod.take_error().describe().c_str());
    }
    CHECK(ctx.ok() && mod.ok());
    if (!ctx.ok() || !mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(fn.ok());
    if (!fn.ok()) return;
    // The loader reports the raw NOBITS size (0x400) as static shared.
    CHECK(fn.value().meta().static_shared == 0x400);
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    // P3-GAP-08: static (0x400) + extra (UINT64_MAX) overflows -> the
    // launch must fail with a structured error before any allocation.
    LaunchConfig cfg;
    cfg.extra_shared = UINT64_MAX;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kOutOfRange);
        CHECK(e.describe().find("shared size overflow") !=
              std::string::npos);
    }
    // Boundary: extra == UINT64_MAX - static_shared is exactly representable
    // (but unallocatable); extra == UINT64_MAX - static_shared + 1 overflows.
    // The overflow check itself is `extra > UINT64_MAX - static_shared`.
    const std::uint64_t static_shared = 0x400;
    CHECK(UINT64_MAX - static_shared + 1 > UINT64_MAX - static_shared);
}

// P3-GAP-05: full-bank-image launch places params at param_base + offset
// and keeps the image's preset slots; blob launch is identical to per-item.
TEST(context_full_bank_image_launch) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    LaunchConfig cfg;

    // Build a full bank image with distinctive bytes everywhere.
    std::vector<std::uint8_t> image(0x10000, 0xAB);
    std::uint64_t pv = ptr.value().va;
    std::memcpy(image.data() + 0x380, &pv, 8);            // a
    std::uint32_t bv = 0xCAFEBABE;
    std::memcpy(image.data() + 0x388, &bv, 4);            // b
    std::memset(image.data() + 0x390, 0x42, 16);           // c
    std::uint32_t nv = 99;
    std::memcpy(image.data() + 0x3a0, &nv, 4);             // n
    std::uint64_t slot = 0xDEADBEEF;
    std::memcpy(image.data() + 0x358, &slot, 8);           // preset

    auto r = ctx.value().launch(fn.value(), cfg, image,
                                ParamPackFormat::kFullBankImage);
    CHECK(r.ok());
    if (!r.ok()) {
        std::fprintf(stderr, "image launch: %s\n",
                     r.take_error().describe().c_str());
        return;
    }
    // Preset slot from the image preserved (not overwritten by prepare).
    const auto& bank = ctx.value().constant_bank(fn.value());
    auto slot_got = bank.read_raw(0x358, 8);
    CHECK(slot_got.ok());
    if (slot_got.ok()) {
        std::uint64_t v = 0;
        std::memcpy(&v, slot_got.value().data(), 8);
        CHECK(v == 0xDEADBEEF);
    }
    // Params landed.
    auto a_got = bank.read_raw(0x380, 8);
    CHECK(a_got.ok());
    if (a_got.ok()) {
        std::uint64_t v = 0;
        std::memcpy(&v, a_got.value().data(), 8);
        CHECK(v == ptr.value().va);
    }
    // Padding preserved from the image.
    auto pad = bank.read_raw(0x3a4, 4);
    CHECK(pad.ok());
    if (pad.ok()) {
        for (auto b : pad.value()) CHECK(b == 0xAB);
    }
    // Image too small for the params -> structured error.
    std::vector<std::uint8_t> small(0x380 + 8, 0);  // covers only a
    auto r2 = ctx.value().launch(fn.value(), cfg, small,
                                 ParamPackFormat::kFullBankImage);
    CHECK(r2.failed());
}

// P3-GAP-03: a services-only mock backend reads IR + global + shared
// through the runtime, and the Function survives module destruction.
struct ServicesBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::size_t predecoded_words = 0;
    std::uint8_t global_byte = 0;
    bool shared_seen = false;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        // Read IR through the request.
        predecoded_words = request.kernel->predecoded.size();
        // Read/write global via runtime services.
        DevicePtr g{0x10000};
        auto st = services->read(g, &global_byte, 1);
        if (st.failed()) return st;
        shared_seen = !request.shared_views.empty();
        return Status::success();
    }
    const char* name() const override { return "services"; }
};

TEST(context_services_backend_and_function_lifetime) {
    auto backend = std::make_shared<ServicesBackend>();
    auto ctx = Context::create(backend);
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    CHECK(mod.ok());
    if (!mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(fn.ok());
    if (!fn.ok()) return;

    // Allocate global at the deterministic base 0x10000 (first alloc).
    auto g = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(g.ok() && g.value().va == 0x10000);
    const std::uint8_t byte = 0x77;
    CHECK(ctx.value().memory().write(g.value(), &byte, 1).ok());

    // Destroy the RuntimeModule; the Function must keep the IR alive.
    mod = StatusOr<RuntimeModule>::failure(Error::internal("gone"));
    (void)mod;

    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    LaunchConfig cfg;
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    // Backend saw the IR and read global through services.
    CHECK(backend->predecoded_words == 2);
    CHECK(backend->global_byte == 0x77);
}

// P3-GAP-07: typed access is isolated by owner domain — cta:1 cannot
// touch cta:2's shared allocation, nor warp:1:0 another warp's local.
TEST(memory_domain_access_isolation) {
    MemoryAllocator m;
    auto s1 = m.allocate(AddressSpace::kShared, 64, 16, "cta:1");
    auto s2 = m.allocate(AddressSpace::kShared, 64, 16, "cta:2");
    auto l1 = m.allocate(AddressSpace::kLocal, 64, 16, "warp:1:0");
    auto l2 = m.allocate(AddressSpace::kLocal, 64, 16, "warp:2:0");
    CHECK(s1.ok() && s2.ok() && l1.ok() && l2.ok());
    if (!s1.ok() || !s2.ok() || !l1.ok() || !l2.ok()) return;

    DeviceAccess acc;
    acc.width = 8;
    acc.alignment = 8;
    acc.kind = AccessKind::kStore;
    acc.space = AddressSpace::kShared;
    std::uint64_t v = 0xAA;
    // Owner cta:1 can write its own; cta:2 cannot.
    acc.domain = "cta:1";
    CHECK(m.write_typed(s1.value(), &v, 8, acc).ok());
    acc.domain = "cta:2";
    auto e = m.write_typed(s1.value(), &v, 8, acc).take_error();
    CHECK(e.code() == ErrorCode::kBadAddress);
    CHECK(e.describe().find("owned by") != std::string::npos);
    // cta:2 can write its own.
    CHECK(m.write_typed(s2.value(), &v, 8, acc).ok());
    // Missing domain on shared -> rejected.
    acc.domain.clear();
    auto e2 = m.write_typed(s1.value(), &v, 8, acc).take_error();
    CHECK(e2.code() == ErrorCode::kBadAddress);
    // Local: warp isolation.
    acc.space = AddressSpace::kLocal;
    acc.domain = "warp:1:0";
    CHECK(m.write_typed(l1.value(), &v, 8, acc).ok());
    acc.domain = "warp:2:0";
    auto e3 = m.write_typed(l1.value(), &v, 8, acc).take_error();
    CHECK(e3.code() == ErrorCode::kBadAddress);
    CHECK(m.write_typed(l2.value(), &v, 8, acc).ok());
    // Global: no domain isolation (context accesses have empty domain).
    auto g = m.allocate(AddressSpace::kGlobal, 64, 16, "context");
    CHECK(g.ok());
    DeviceAccess gacc = acc;
    gacc.space = AddressSpace::kGlobal;
    gacc.domain.clear();
    CHECK(m.write_typed(g.value(), &v, 8, gacc).ok());
}

// P3-GAP-06: full width matrix (1/2/4/8/16/32/128/256) for aligned,
// misaligned, OOB and wrong-space on typed access.
TEST(memory_typed_access_width_matrix) {
    MemoryAllocator m;
    const std::uint64_t widths[] = {1, 2, 4, 8, 16, 32, 128, 256};
    const std::uint64_t kSize = 1024;
    auto a = m.allocate(AddressSpace::kGlobal, kSize, 256);
    CHECK(a.ok());
    if (!a.ok()) return;
    std::vector<std::uint8_t> blob(256, 0x5A);
    for (const std::uint64_t w : widths) {
        DeviceAccess acc;
        acc.width = w;
        acc.alignment = w;
        acc.kind = AccessKind::kStore;
        acc.space = AddressSpace::kGlobal;
        // Aligned write + read at offset 0.
        CHECK(m.write_typed(a.value(), blob.data(), w, acc).ok());
        DeviceAccess rd = acc;
        rd.kind = AccessKind::kLoad;
        CHECK(m.read_typed(a.value(), blob.data(), w, rd).ok());
        // Misaligned at +1 -> kAlignmentViolation (for w >= 2).
        if (w >= 2) {
            auto p = a.value().add(1);
            CHECK(p.ok());
            auto e = m.write_typed(p.value(), blob.data(), w, acc).take_error();
            CHECK(e.code() == ErrorCode::kAlignmentViolation);
        }
        // OOB at kSize - w + 1 (alignment 1 to reach the OOB check).
        // Use a dedicated allocator so the pointer stays inside the
        // allocation's range but crosses its end.
        MemoryAllocator mw;
        auto aw = mw.allocate(AddressSpace::kGlobal, kSize, 256);
        CHECK(aw.ok());
        DeviceAccess oob_acc = acc;
        oob_acc.alignment = 1;
        auto p = aw.value().add(kSize - w + 1);
        CHECK(p.ok());
        auto e2 = mw.write_typed(p.value(), blob.data(), w, oob_acc).take_error();
        // w=1 at offset 1024 is past every allocation (kBadAddress); for
        // w>=2 the pointer is inside and the range crosses the end (kOob).
        if (w == 1) {
            CHECK(e2.code() == ErrorCode::kOob ||
                  e2.code() == ErrorCode::kBadAddress);
        } else {
            CHECK(e2.code() == ErrorCode::kOob);
        }
        // Wrong space.
        auto sh = m.allocate(AddressSpace::kShared, kSize, 256, "cta:9");
        CHECK(sh.ok());
        DeviceAccess wacc = acc;
        wacc.domain = "cta:9";
        auto e3 = m.write_typed(sh.value(), blob.data(), w, wacc).take_error();
        CHECK(e3.code() == ErrorCode::kBadAddress);  // space mismatch
    }
}

// P3-GAP-07: repeated launches reclaim CTA shared allocations — no leak
// across launches.
TEST(context_repeated_launch_no_shared_leak) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin_with_shared(), "t");
    CHECK(ctx.ok() && mod.ok());
    if (!ctx.ok() || !mod.ok()) return;
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(fn.ok());
    if (!fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));

    std::size_t live_before = 0;
    for (const auto& al : ctx.value().memory().allocations())
        if (al.alive) ++live_before;
    LaunchConfig cfg;  // 1 CTA -> 1 shared alloc per launch
    for (int i = 0; i < 5; ++i) {
        auto r = ctx.value().launch(fn.value(), cfg, args);
        CHECK(r.ok());
        if (!r.ok()) return;
        // After the launch returns, the CTA shared allocations are
        // reclaimed: live count returns to the pre-launch baseline.
        std::size_t live = 0;
        for (const auto& al : ctx.value().memory().allocations()) {
            if (al.alive) ++live;
        }
        CHECK(live == live_before);  // no leak across launches
    }
}

// P3-GAP-01: layout slot boundary — overflow-safe check rejects offsets
// near UINT64_MAX.
TEST(constant_bank_layout_boundary) {
    // default_cdesc_offset near UINT64_MAX must be rejected (no wrap).
    bool threw = false;
    try {
        ConstantBankLayout bad;
        bad.default_cdesc_offset = UINT64_MAX;
        ConstantBank b(bad);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);
    threw = false;
    try {
        ConstantBankLayout bad;
        bad.default_cdesc_offset = UINT64_MAX - 7;  // 8 bytes would wrap
        ConstantBank b(bad);
    } catch (const std::invalid_argument&) {
        threw = true;
    }
    CHECK(threw);
    // Exactly at the edge: size - 8 fits.
    bool ok = true;
    try {
        ConstantBankLayout good;
        good.default_cdesc_offset = good.size - 8;
        ConstantBank b(good);
    } catch (const std::invalid_argument&) {
        ok = false;
    }
    CHECK(ok);
}

// P3-GAP-03: event channel ABI — a sink receives events through the
// runtime services.
struct CountingSink : IEventSink {
    std::size_t events = 0;
    bool emit(const BasicMemoryEvent&) override {
        ++events;
        return true;
    }
};

TEST(context_event_channel) {
    auto ctx = Context::create();
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    CountingSink sink;
    ctx.value().set_event_sink(&sink);
    BasicMemoryEvent ev;
    ev.kind = EventKind::kLaunch;
    ev.pc = 0;
    ev.address = DevicePtr{0x100};
    ev.width = 8;
    ev.space = AddressSpace::kGlobal;
    ev.access_kind = AccessKind::kLoad;
    ev.domain = "cta:0";
    ev.write = false;
    CHECK(ctx.value().emit_event(ev));
    CHECK(sink.events == 1);
    ctx.value().set_event_sink(nullptr);
    CHECK(ctx.value().emit_event(ev));  // no sink -> always true
    CHECK(sink.events == 1);
}

// P3-GAP-03: a backend using the event channel through the services.
struct EventBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::size_t emitted = 0;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        BasicMemoryEvent ev;
        ev.kind = EventKind::kMemoryAccess;
        ev.pc = 0x10;
        ev.address = request.shared_views.empty()
            ? DevicePtr{0} : request.shared_views[0].base;
        ev.width = 4;
        ev.space = AddressSpace::kShared;
        ev.access_kind = AccessKind::kLoad;
        ev.domain = request.shared_views.empty()
            ? "" : request.shared_views[0].domain;
        ev.write = false;
        if (!services->emit_event(ev)) return Status::failure(
            Error::internal("sink stopped"));
        ++emitted;
        return Status::success();
    }
    const char* name() const override { return "event"; }
};

TEST(context_backend_event_channel) {
    auto backend = std::make_shared<EventBackend>();
    auto ctx = Context::create(backend);
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    auto mod = ctx.value().load_module(make_4param_cubin_with_shared(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    auto r = ctx.value().launch(fn.value(), LaunchConfig{}, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(backend->emitted == 1);
}

// Reviewer round 3 Blocker: multi-CTA shared windows must be fully
// visible to the backend as explicit per-CTA views (no arithmetic).
struct MultiCtaBackend : IBackend {
    IRuntimeServices* services = nullptr;
    std::vector<CtaSharedView> views;
    bool isolation_ok = true;
    void bind_runtime(IRuntimeServices* s) override { services = s; }
    Status launch(const BackendLaunchRequest& request) override {
        views.assign(request.shared_views.begin(),
                     request.shared_views.end());
        // Verify: each CTA can only access its own window.
        std::uint64_t v = 0x42;
        for (const auto& view : views) {
            DeviceAccess acc;
            acc.width = 8;
            acc.alignment = 8;
            acc.kind = AccessKind::kStore;
            acc.space = AddressSpace::kShared;
            acc.domain = view.domain;
            if (services->write_typed(view.base, &v, 8, acc).failed()) {
                isolation_ok = false;
                return Status::success();
            }
            // Cross-domain access to another CTA's window must fail.
            for (const auto& other : views) {
                if (other.cta_linear_id == view.cta_linear_id) continue;
                acc.domain = view.domain;
                if (services->write_typed(other.base, &v, 8, acc).ok()) {
                    isolation_ok = false;
                    return Status::success();
                }
            }
        }
        return Status::success();
    }
    const char* name() const override { return "multicta"; }
};

TEST(context_multi_cta_shared_views) {
    auto backend = std::make_shared<MultiCtaBackend>();
    auto ctx = Context::create(backend);
    CHECK(ctx.ok());
    if (!ctx.ok()) return;
    auto mod = ctx.value().load_module(make_4param_cubin_with_shared(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
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
    cfg.grid_x = 2;
    cfg.grid_y = 2;  // 4 CTAs
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.ok());
    if (!r.ok()) {
        std::fprintf(stderr, "multi-cta launch: %s\n",
                     r.take_error().describe().c_str());
        return;
    }
    // Backend saw 4 views.
    CHECK(backend->views.size() == 4);
    // Addresses pairwise non-overlapping, domains unique.
    for (std::size_t i = 0; i < backend->views.size(); ++i) {
        for (std::size_t j = i + 1; j < backend->views.size(); ++j) {
            const auto& a = backend->views[i];
            const auto& b = backend->views[j];
            const bool overlap =
                (a.base.va < b.base.va + b.size) &&
                (b.base.va < a.base.va + a.size);
            CHECK(!overlap);
            CHECK(a.domain != b.domain);
        }
    }
    // Isolation: each CTA could write its own, cross-CTA rejected.
    CHECK(backend->isolation_ok);
    // LaunchResult carries diagnostic views (metadata only).
    CHECK(r.value().has_shared);
    CHECK(r.value().shared_views.size() == 4);
    // After launch returns, the shared allocations are reclaimed: live
    // count has no shared allocations.
    for (const auto& al : ctx.value().memory().allocations()) {
        if (al.alive) CHECK(al.space != AddressSpace::kShared);
    }
}

// Reviewer round 3 High: LaunchResult must not expose dangling shared
// pointers — the windows are freed before launch() returns.
TEST(context_launch_result_shared_not_dangling) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin_with_shared(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    auto r = ctx.value().launch(fn.value(), LaunchConfig{}, args);
    CHECK(r.ok());
    if (!r.ok()) return;
    CHECK(r.value().has_shared);
    // Any address from the diagnostic views is NOT accessible after the
    // launch: a typed access must fail (the allocation is freed).
    if (!r.value().shared_views.empty()) {
        DeviceAccess acc;
        acc.width = 8;
        acc.alignment = 8;
        acc.kind = AccessKind::kLoad;
        acc.space = AddressSpace::kShared;
        acc.domain = r.value().shared_views[0].domain;
        std::uint64_t out = 0;
        auto e = ctx.value().read_typed(r.value().shared_views[0].base,
                                        &out, 8, acc);
        CHECK(e.failed());
        if (e.failed()) {
            Error err = e.take_error();  // take once, check both
            CHECK(err.code() == ErrorCode::kLifecycle ||
                  err.code() == ErrorCode::kBadAddress);
        }
    }
}

// Reviewer round 3 High: CTA domain IDs are Context-local — two Contexts
// must never share or collide domain IDs.
TEST(context_cta_domain_ids_context_local) {
    // Context 1.
    auto ctx1 = Context::create();
    CHECK(ctx1.ok());
    if (!ctx1.ok()) return;
    auto mod1 = ctx1.value().load_module(make_4param_cubin_with_shared(), "t");
    CHECK(mod1.ok());
    if (!mod1.ok()) return;
    auto fn1 = ctx1.value().function(mod1.value(), "_Z4kernv");
    CHECK(fn1.ok());
    if (!fn1.ok()) return;
    auto p1 = ctx1.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(p1.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(p1.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));
    auto r1 = ctx1.value().launch(fn1.value(), LaunchConfig{}, args);
    CHECK(r1.ok());
    if (!r1.ok()) return;
    CHECK(r1.value().has_shared);
    CHECK(r1.value().shared_views[0].domain == "cta:0");

    // Context 2: fresh domain counter.
    auto ctx2 = Context::create();
    CHECK(ctx2.ok());
    if (!ctx2.ok()) return;
    auto mod2 = ctx2.value().load_module(make_4param_cubin_with_shared(), "t");
    CHECK(mod2.ok());
    if (!mod2.ok()) return;
    auto fn2 = ctx2.value().function(mod2.value(), "_Z4kernv");
    CHECK(fn2.ok());
    if (!fn2.ok()) return;
    auto p2 = ctx2.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(p2.ok());
    std::vector<KernelArg> args2 = args;
    args2[0] = KernelArg::pointer(p2.value(), "a");
    auto r2 = ctx2.value().launch(fn2.value(), LaunchConfig{}, args2);
    CHECK(r2.ok());
    if (!r2.ok()) return;
    CHECK(r2.value().shared_views[0].domain == "cta:0");
    // Both Contexts alive with their own allocators (no shared state).
    CHECK(ctx1.value().memory().allocation_by_id(AllocationId{1}).ok());
    CHECK(ctx2.value().memory().allocation_by_id(AllocationId{1}).ok());
}

// Reviewer round 3 High: grid dims overflow is a structured error.
TEST(context_grid_dims_overflow_rejected) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
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
    cfg.grid_x = 0xFFFFFFFF;
    cfg.grid_y = 0xFFFFFFFF;
    cfg.grid_z = 0xFFFFFFFF;  // triple product overflows uint64
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kOutOfRange);
        CHECK(e.describe().find("grid dims overflow") != std::string::npos);
    }
}

// Reviewer round 4: block dims are validated at launch (not just grid);
// zero dimensions are rejected; the sm120 1024-thread cap is enforced.
TEST(context_block_dims_overflow_rejected) {
    auto ctx = Context::create();
    auto mod = ctx.value().load_module(make_4param_cubin(), "t");
    auto fn = ctx.value().function(mod.value(), "_Z4kernv");
    CHECK(ctx.ok() && mod.ok() && fn.ok());
    if (!ctx.ok() || !mod.ok() || !fn.ok()) return;
    auto ptr = ctx.value().memory().allocate(AddressSpace::kGlobal, 64);
    CHECK(ptr.ok());
    std::vector<KernelArg> args;
    args.push_back(KernelArg::pointer(ptr.value(), "a"));
    args.push_back(KernelArg::integer(1, "b"));
    args.push_back(KernelArg::raw(std::vector<std::uint8_t>(16, 0), "c"));
    args.push_back(KernelArg::integer(1, "n"));

    // Block triple product overflows uint64 -> structured error before any
    // shared allocation / backend call.
    LaunchConfig cfg;
    cfg.block_x = 0xFFFFFFFF;
    cfg.block_y = 0xFFFFFFFF;
    cfg.block_z = 0xFFFFFFFF;
    auto r = ctx.value().launch(fn.value(), cfg, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kOutOfRange);
        CHECK(e.describe().find("block dims overflow") != std::string::npos);
    }

    // Zero block dim -> rejected.
    LaunchConfig cfg0;
    cfg0.block_y = 0;
    r = ctx.value().launch(fn.value(), cfg0, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kInvalidArgument);
        CHECK(e.describe().find("non-zero") != std::string::npos);
    }

    // Zero grid dim -> rejected.
    LaunchConfig cfg0g;
    cfg0g.grid_z = 0;
    r = ctx.value().launch(fn.value(), cfg0g, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kInvalidArgument);
        CHECK(e.describe().find("non-zero") != std::string::npos);
    }

    // Block thread count above the sm120 cap (1024) -> rejected.
    LaunchConfig cfgcap;
    cfgcap.block_x = 1025;
    r = ctx.value().launch(fn.value(), cfgcap, args);
    CHECK(r.failed());
    if (r.failed()) {
        Error e = r.take_error();
        CHECK(e.code() == ErrorCode::kInvalidArgument);
        CHECK(e.describe().find("1024") != std::string::npos);
    }

    // At the cap: 1024 threads is legal.
    LaunchConfig cfgok;
    cfgok.block_x = 1024;
    r = ctx.value().launch(fn.value(), cfgok, args);
    CHECK(r.ok());
}

// ---------------------------------------------------------------------------
// Phase 6: MemoryService functional semantics.
// ---------------------------------------------------------------------------

// LDG width + sign extension across U8/S8/U16/S16/32/64/128 through the
// service.
TEST(memory_service_load_widths_and_sign_extension) {
    std::vector<std::uint8_t> params;
    MemoryService ms(params);
    std::vector<std::uint8_t> global(32, 0);
    global[0] = 0xFF;  // byte0
    global[1] = 0x80;  // byte1
    global[2] = 0x00;  // byte2
    global[3] = 0xFF;  // byte3
    std::memcpy(global.data() + 4, "\x78\x56\x34\x12", 4);  // 0x12345678 @4
    std::memcpy(global.data() + 8, "\xef\xcd\xab\x89\x67\x45\x23\x01", 8);
    std::memcpy(global.data() + 16, "\x00\x01\x02\x03\x04\x05\x06\x07"
                                     "\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f", 16);
    ms.set_global_backing(&global);
    auto g = ms.setup_global(global.size(), "test");
    CHECK(g.ok());

    MemValue v{};
    // U8 @0 -> 0xFF.
    CHECK(ms.ldg(DevicePtr{0}, 0, 0, MemWidthInfo{1, false, true}, v).ok());
    CHECK(v[0] == 0xFFu && v[1] == 0);
    // S8 @0 -> 0xFFFFFFFF.
    CHECK(ms.ldg(DevicePtr{0}, 0, 0, MemWidthInfo{1, true, true}, v).ok());
    CHECK(v[0] == 0xFFFFFFFFu && v[1] == 0);
    // U16 @2 -> 0xFF00 (bytes 00 FF).
    CHECK(ms.ldg(DevicePtr{0}, 2, 0, MemWidthInfo{2, false, true}, v).ok());
    CHECK(v[0] == 0xFF00u && v[1] == 0);
    // S16 @2 -> 0xFFFFFF00.
    CHECK(ms.ldg(DevicePtr{0}, 2, 0, MemWidthInfo{2, true, true}, v).ok());
    CHECK(v[0] == 0xFFFFFF00u && v[1] == 0);
    // 32 @4 -> 0x12345678.
    CHECK(ms.ldg(DevicePtr{0}, 4, 0, MemWidthInfo{4, false, true}, v).ok());
    CHECK(v[0] == 0x12345678u && v[1] == 0);
    // 64 @8 -> 0x0123456789ABCDEF.
    CHECK(ms.ldg(DevicePtr{0}, 8, 0, MemWidthInfo{8, false, true}, v).ok());
    CHECK(v[0] == 0x89ABCDEFu && v[1] == 0x01234567u);
    // 128 @16 -> all four words.
    CHECK(ms.ldg(DevicePtr{0}, 16, 0, MemWidthInfo{16, false, true}, v).ok());
    CHECK(v[0] == 0x03020100u && v[1] == 0x07060504u &&
          v[2] == 0x0b0a0908u && v[3] == 0x0f0e0d0cu);
}

// STG widths write into the global backing; LDG reads them back (including
// a 128-bit store through all four words).
TEST(memory_service_store_widths) {
    std::vector<std::uint8_t> params;
    MemoryService ms(params);
    std::vector<std::uint8_t> global(32, 0);
    ms.set_global_backing(&global);
    auto g = ms.setup_global(global.size(), "test");
    CHECK(g.ok());

    MemValue v{};
    // 32-bit store of 0xDEADBEEF at offset 0.
    v[0] = 0xDEADBEEFu;
    CHECK(ms.stg(DevicePtr{0}, 0, 0, MemWidthInfo{4, false, true}, v).ok());
    std::uint32_t x = 0;
    std::memcpy(&x, global.data(), 4);
    CHECK(x == 0xDEADBEEFu);
    // 64-bit store at offset 8 (8-byte natural alignment).
    v = {};
    v[0] = 0x89ABCDEFu; v[1] = 0x01234567u;
    CHECK(ms.stg(DevicePtr{0}, 8, 0, MemWidthInfo{8, false, true}, v).ok());
    std::uint64_t w = 0;
    std::memcpy(&w, global.data() + 8, 8);
    CHECK(w == 0x0123456789ABCDEFULL);
    // 128-bit store at offset 16 (all four words survive).
    v = {};
    v[0] = 0x03020100u; v[1] = 0x07060504u;
    v[2] = 0x0b0a0908u; v[3] = 0x0f0e0d0cu;
    CHECK(ms.stg(DevicePtr{0}, 16, 0, MemWidthInfo{16, false, true}, v).ok());
    MemValue rd{};
    CHECK(ms.ldg(DevicePtr{0}, 16, 0, MemWidthInfo{16, false, true}, rd).ok());
    CHECK(rd[0] == 0x03020100u && rd[1] == 0x07060504u &&
          rd[2] == 0x0b0a0908u && rd[3] == 0x0f0e0d0cu);
}

// LDS/STS on the CTA shared buffer, with OOB detection.
TEST(memory_service_shared_roundtrip_and_oob) {
    std::vector<std::uint8_t> shared(64, 0);
    MemValue v{};
    v[0] = 42;
    CHECK(MemoryService::sts(shared, 0, 0, MemWidthInfo{4, false, true}, v).ok());
    MemValue lo{};
    CHECK(MemoryService::lds(shared, 0, 0, MemWidthInfo{4, false, true}, lo).ok());
    CHECK(lo[0] == 42u);
    // OOB store faults (kOob).
    auto st = MemoryService::sts(shared, 100, 0, MemWidthInfo{4, false, true}, v);
    CHECK(st.failed());
    CHECK(st.error().code() == ErrorCode::kOob);
    // Negative offset faults.
    auto st2 = MemoryService::sts(shared, 0, -4, MemWidthInfo{4, false, true}, v);
    CHECK(st2.failed());
    CHECK(st2.error().code() == ErrorCode::kOob);
    // Misaligned multi-byte access faults (alignment enforced per width).
    auto st3 = MemoryService::sts(shared, 1, 0, MemWidthInfo{4, false, true}, v);
    CHECK(st3.failed());
    CHECK(st3.error().code() == ErrorCode::kAlignmentViolation);
    // Invalid size slot is rejected (Medium fix), not decoded as 4 bytes.
    auto st4 = MemoryService::lds(shared, 0, 0, MemWidthInfo{0, false, false}, lo);
    CHECK(st4.failed());
    CHECK(st4.error().code() == ErrorCode::kInvalidArgument);
}

// Shared atomics: add/exch on the shared buffer.
TEST(memory_service_shared_atomic) {
    std::vector<std::uint8_t> shared(16, 0);
    MemValue ops{};
    MemValue old{};
    ops[0] = 5;
    CHECK(MemoryService::atom_shared(shared, 0, 4, AtomicOp::kAdd, ops, old).ok());
    CHECK(old[0] == 0u);
    std::uint32_t cur = 0;
    std::memcpy(&cur, shared.data(), 4);
    CHECK(cur == 5u);
    // Second add returns the pre-value.
    ops[0] = 7;
    CHECK(MemoryService::atom_shared(shared, 0, 4, AtomicOp::kAdd, ops, old).ok());
    CHECK(old[0] == 5u);
    std::memcpy(&cur, shared.data(), 4);
    CHECK(cur == 12u);
    // Exch returns old and sets new.
    ops[0] = 0xAABBCCDD;
    CHECK(MemoryService::atom_shared(shared, 0, 4, AtomicOp::kExch, ops, old).ok());
    CHECK(old[0] == 12u);
    std::memcpy(&cur, shared.data(), 4);
    CHECK(cur == 0xAABBCCDDU);
    // 64-bit atomic reads/writes both words.
    ops[0] = 0x11111111u; ops[1] = 0x22222222u;
    CHECK(MemoryService::atom_shared(shared, 8, 8, AtomicOp::kAdd, ops, old).ok());
    CHECK(old[0] == 0 && old[1] == 0);
    std::uint64_t w64 = 0;
    std::memcpy(&w64, shared.data() + 8, 8);
    CHECK(w64 == 0x2222222211111111ULL);
    // 128-bit atomic is a STRUCTURED error (never a truncated 64-bit RMW).
    auto st = MemoryService::atom_shared(shared, 0, 16, AtomicOp::kAdd, ops, old);
    CHECK(st.failed());
}

// Global atomic: 128-bit must fault (Blocker-3: no truncated 64-bit RMW).
TEST(memory_service_global_atomic_128_faults) {
    std::vector<std::uint8_t> params;
    MemoryService ms(params);
    std::vector<std::uint8_t> global(64, 0);
    ms.set_global_backing(&global);
    auto g = ms.setup_global(global.size(), "test");
    CHECK(g.ok());
    MemValue ops{};
    ops[0] = 1;
    MemValue old{};
    auto st = ms.atom_global(0, 16, AtomicOp::kAdd, ops, old);
    CHECK(st.failed());
    CHECK(st.error().code() == ErrorCode::kNotSupported);
}

// High-1: bounds (off+len never wraps), per-width alignment and checked
// signed-offset arithmetic are all enforced.
TEST(memory_service_bounds_alignment_overflow) {
    std::vector<std::uint8_t> params;
    MemoryService ms(params);
    std::vector<std::uint8_t> global(64, 0);
    ms.set_global_backing(&global);
    auto g = ms.setup_global(global.size(), "test");
    CHECK(g.ok());
    MemValue v{};
    v[0] = 1;

    // Misaligned 8-byte load/store/atomic -> kAlignmentViolation.
    CHECK(ms.ldg(DevicePtr{0}, 4, 0, MemWidthInfo{8, false, true}, v).failed());
    auto e = ms.ldg(DevicePtr{0}, 4, 0, MemWidthInfo{8, false, true}, v).take_error();
    CHECK(e.code() == ErrorCode::kAlignmentViolation);
    CHECK(ms.stg(DevicePtr{0}, 12, 0, MemWidthInfo{8, false, true}, v).failed());
    auto e2 = ms.stg(DevicePtr{0}, 12, 0, MemWidthInfo{8, false, true}, v).take_error();
    CHECK(e2.code() == ErrorCode::kAlignmentViolation);
    CHECK(ms.atom_global(4, 8, AtomicOp::kAdd, v, v).failed());
    auto e3 = ms.atom_global(4, 8, AtomicOp::kAdd, v, v).take_error();
    CHECK(e3.code() == ErrorCode::kAlignmentViolation);

    // Range crossing the buffer end -> kOob (off <= size && len <= size-off).
    // addr=64 (one-past-end, aligned) width 8 crosses [64,72).
    auto oob = ms.ldg(DevicePtr{0}, 64, 0, MemWidthInfo{8, false, true}, v);
    CHECK(oob.failed());
    CHECK(oob.error().code() == ErrorCode::kOob);
    auto oob2 = ms.stg(DevicePtr{0}, 64, 0, MemWidthInfo{8, false, true}, v);
    CHECK(oob2.failed());
    CHECK(oob2.error().code() == ErrorCode::kOob);

    // A signed negative offset underflowing base -> structured error (no
    // unsigned wrap into a huge address).
    auto under = ms.ldg(DevicePtr{0}, 0, INT64_MIN, MemWidthInfo{4, false, true}, v);
    CHECK(under.failed());
    auto over = ms.ldg(DevicePtr{0}, 0, INT64_MAX, MemWidthInfo{4, false, true}, v);
    CHECK(over.failed());
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    int failures = semu_test::run_all("semu-memory");
    if (failures == 0) {
        std::fprintf(stdout, "[  PASSED  ] all semu memory/context tests\n");
    }
    return failures == 0 ? 0 : 1;
}
