// C++/Python oracle cross-check for the UnifiedV1 L1TEX estimator.
//
// Reads fixture JSONL from argv[1] (rows with `g`, `s`, `m`, optional `size`),
// runs the C++ estimator per row, and prints `shared_wf` (plus per-token
// decomposition) so a Python driver can compare field-by-field with
// unified_model.simulate.
//
// Output: one JSON object per line:
//   {"index":N,"SharedWf":I,"ReadWf":I,"WriteWf":I,"OverlapWf":I,
//    "Tokens":I,"TokenStats":[...]}
//
// Phase 8: `--ldgsts` prints the extended LDGSTS estimate instead:
//   {"SharedWf":..., ..., "TWf":I,"TagConf":I,"TSetAcc":I,"Sectors":I,
//    "SharedConf":I,"GlobalConf":I,"SharedWfConfidence":"...",...}

#include <semu/memory/l1tex_model.hpp>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

namespace {
std::vector<std::uint32_t> parse_int_array(const char* s) {
    std::vector<std::uint32_t> out;
    const char* p = s;
    while (*p) {
        if (*p == ',' || *p == '[' || *p == ']' || *p == ' ') {
            ++p;
            continue;
        }
        char* end = nullptr;
        const unsigned long v = std::strtoul(p, &end, 10);
        if (end == p) break;
        out.push_back(static_cast<std::uint32_t>(v));
        p = end;
    }
    return out;
}
}  // namespace

int main(int argc, char** argv) {
    bool ldgsts = false;
    int arg0 = 1;
    if (argc > 1 && std::strcmp(argv[1], "--ldgsts") == 0) {
        ldgsts = true;
        arg0 = 2;
    }
    if (argc < arg0 + 1) {
        std::fprintf(stderr, "usage: %s [--ldgsts] <goff,soff,mask[,size]>...\n",
                     argv[0]);
        return 2;
    }
    semu::l1tex::UnifiedV1Estimator est;
    // Arg format: "g=<g0,g1,...> s=<s0,...> m=<mask> [size=<N>]"
    std::vector<std::uint32_t> goff, soff;
    std::uint32_t mask = 0xffffffffu;
    int size = 4;
    for (int i = arg0; i < argc; ++i) {
        const std::string a = argv[i];
        if (a.rfind("g=", 0) == 0) goff = parse_int_array(a.c_str() + 2);
        else if (a.rfind("s=", 0) == 0) soff = parse_int_array(a.c_str() + 2);
        else if (a.rfind("m=", 0) == 0) mask = static_cast<std::uint32_t>(std::strtoul(a.c_str() + 2, nullptr, 10));
        else if (a.rfind("size=", 0) == 0) size = std::atoi(a.c_str() + 5);
    }
    if (goff.size() != 32 || soff.size() != 32) {
        std::fprintf(stderr, "need 32 goff + 32 soff\n");
        return 2;
    }
    if (ldgsts) {
        auto r = est.estimate_ldgsts(goff.data(), soff.data(), size, mask);
        std::printf("%s\n", r.to_json().c_str());
    } else {
        auto r = est.estimate(goff, soff, size, mask);
        std::printf("%s\n", r.to_json().c_str());
    }
    return 0;
}
