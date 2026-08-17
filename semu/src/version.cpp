#include <semu/version.hpp>

#include <cstdio>

namespace semu {

std::string semu_version_string() {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "%d.%d.%d", kVersionMajor, kVersionMinor,
                  kVersionPatch);
    return buf;
}

std::string build_cxx_compiler() {
#ifdef SEMU_CXX_COMPILER
    return SEMU_CXX_COMPILER;
#else
    return "unknown";
#endif
}

std::string build_mode() {
#ifdef SEMU_BUILD_TYPE
    return SEMU_BUILD_TYPE;
#else
    return "unknown";
#endif
}

bool sanitizers_enabled() {
#ifdef SEMU_SANITIZERS
    return SEMU_SANITIZERS;
#else
    return false;
#endif
}

bool gpu_differential_enabled() {
#ifdef SEMU_GPU_DIFFERENTIAL
    return SEMU_GPU_DIFFERENTIAL;
#else
    return false;
#endif
}

}  // namespace semu
