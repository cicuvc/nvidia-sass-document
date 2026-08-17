cmake_minimum_required(VERSION 3.20)
project(semu VERSION 0.1.0 LANGUAGES CXX)

# ---------------------------------------------------------------------------
# SM120 SASS behavior simulator (SIM_PLAN).  Core library has no CUDA
# runtime/driver dependency; everything is CPU-only by default.
# ---------------------------------------------------------------------------

option(SEMU_BUILD_CLI "Build the semu command-line tool" ON)
option(SEMU_BUILD_TESTS "Build semu tests (CTest)" ON)
option(SEMU_ENABLE_SANITIZERS
       "Build with AddressSanitizer + UndefinedBehaviorSanitizer" OFF)
option(SEMU_ENABLE_TSAN
       "Build with ThreadSanitizer (concurrency gates; not combinable
with ASan)" OFF)
option(SEMU_ENABLE_GPU_DIFFERENTIAL
       "Reserve optional GPU differential hooks (no effect before Phase 3)"
       OFF)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Debug CACHE STRING "Build type" FORCE)
endif()

set(SEMU_WARN_FLAGS "")
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  set(SEMU_WARN_FLAGS -Wall -Wextra -Wpedantic)
endif()

# Treat warnings as errors for the core library, CLI and tests.  Phase 0/1
# acceptance requires a warning-free build (GAP-08).
option(SEMU_WERROR "Treat compiler warnings as errors" ON)
if(SEMU_WERROR AND CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  list(APPEND SEMU_WARN_FLAGS -Werror)
  message(STATUS "semu: warnings are errors (SEMU_WERROR=ON)")
endif()

if(SEMU_ENABLE_SANITIZERS)
  add_compile_options(-fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
  message(STATUS "semu: sanitizers (ASan+UBSan) enabled")
endif()
if(SEMU_ENABLE_TSAN)
  add_compile_options(-fsanitize=thread -fno-omit-frame-pointer)
  add_link_options(-fsanitize=thread)
  message(STATUS "semu: ThreadSanitizer enabled")
endif()

if(SEMU_ENABLE_GPU_DIFFERENTIAL)
  message(STATUS "semu: GPU differential hooks reserved (require a CUDA "
                 "environment; no-op before Phase 3)")
endif()

# ---------------------------------------------------------------------------
# Build-info compile definitions shared by all targets.
# ---------------------------------------------------------------------------
add_library(semu_buildinfo INTERFACE)
target_compile_definitions(semu_buildinfo INTERFACE
  SEMU_VERSION_MAJOR=${PROJECT_VERSION_MAJOR}
  SEMU_VERSION_MINOR=${PROJECT_VERSION_MINOR}
  SEMU_VERSION_PATCH=${PROJECT_VERSION_PATCH}
  SEMU_BUILD_TYPE="$<CONFIG>"
  SEMU_CXX_COMPILER="$<CXX_COMPILER_ID>-${CMAKE_CXX_COMPILER_VERSION}"
  SEMU_SANITIZERS=$<BOOL:${SEMU_ENABLE_SANITIZERS}>
  SEMU_GPU_DIFFERENTIAL=$<BOOL:${SEMU_ENABLE_GPU_DIFFERENTIAL}>
)

# ---------------------------------------------------------------------------
# Generated build inputs.  Regenerate (byte-identical) with:
#   python3 semu/tools/gen_capability.py
# Phase 1 adds semu/tools/gen_isa.py -> generated/isa_data.{hpp,cpp}.
# ---------------------------------------------------------------------------
find_package(Python3 COMPONENTS Interpreter QUIET)
if(Python3_FOUND)
  add_custom_target(regenerate-capability
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/tools/gen_capability.py
            --db ${CMAKE_CURRENT_SOURCE_DIR}/../sm120.json
    COMMENT "Regenerate capability manifest build inputs")
endif()

add_subdirectory(src)
if(SEMU_BUILD_CLI)
  add_subdirectory(cli)
endif()
if(SEMU_BUILD_TESTS)
  enable_testing()
  add_subdirectory(tests)
endif()
