#pragma once

#include <string>

#include <semu/core/api.hpp>

// Build-time version and configuration info for the semu simulator.
//
// Values come from CMake compile definitions (semu_buildinfo interface
// target) plus a couple of hard-coded ABI/stability markers.  This header is
// part of the stable public API: its accessors are expected to survive every
// phase.
//
// Interface-version markers (kBackendApiVersion / kDecodedIrVersion /
// kRuntimeServicesVersion / kEventStreamVersion / kFaultAbiVersion) are the
// Phase 10 freeze contract — see api.hpp.

namespace semu {

inline constexpr int kVersionMajor = 0;
inline constexpr int kVersionMinor = 1;
inline constexpr int kVersionPatch = 0;

// Error-model ABI version.  Bump only on a breaking change to Status/Error/
// Fault; SIM_PLAN Phase 0 exit requires later backends not to need one.
inline constexpr const char* kErrorModelVersion = "1";

// Capability-manifest schema version (see capability.hpp).
inline constexpr int kCapabilityManifestVersion = 1;

// Target architecture this build is generated for.
inline constexpr const char* kTargetArch = "sm120";

// Full version string "0.1.0".
std::string semu_version_string();

// CMake-provided build info (compile definitions, see CMakeLists.txt).
std::string build_cxx_compiler();
std::string build_mode();
bool sanitizers_enabled();
bool gpu_differential_enabled();

}  // namespace semu
