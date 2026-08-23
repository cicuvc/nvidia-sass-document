add_library(semu_core STATIC
  core/status.cpp
  core/fault.cpp
  core/word.cpp
  core/capability.cpp
  core/version.cpp
  memory/memory.cpp
  context/context.cpp
  exec/cluster.cpp
  interpreter/baseline/sm120/core.cpp
  interpreter/baseline/sm120/control_flow.cpp
  interpreter/baseline/sm120/fp_vector.cpp
  interpreter/baseline/sm120/int_vector.cpp
  interpreter/baseline/sm120/memory.cpp
  interpreter/baseline/sm120/scalar.cpp
  interpreter/baseline/sm120/tensor.cpp
  interpreter/baseline/sm120/tma.cpp
  exec/debugger.cpp
  tensor/tensor_map.cpp
  tensor/tensor.cpp
  tensor/mbarrier.cpp
  fp/fp.cpp
  fp/fast_fp.cpp
  memory/memory_service.cpp
  context/mock_backend.cpp
  memory/l1tex_model.cpp
  memory/shared_bank.cpp
  memory/global_model.cpp
  profiler/profiler.cpp
  exec/subcore_scheduler.cpp
  memory/l2_events.cpp
  core/hb_clock.cpp
  memory/race_detector.cpp
  decoder/expr.cpp
  decoder/decoder.cpp
  decoder/render.cpp
  cubin/loader.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/../generated/capability_data.cpp
  ${CMAKE_CURRENT_SOURCE_DIR}/../generated/isa_data.cpp
)

# Generated ISA tables: the compile-time condition thunks are emitted with
# constant-foldable `a || b` operands (e.g. an enum/param literal folding to a
# constant).  Clang's -Wconstant-logical-operand is -Werror here; silence it
# for this generated file only (it is not hand-authored).
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  set_source_files_properties(
    ${CMAKE_CURRENT_SOURCE_DIR}/../generated/isa_data.cpp
    PROPERTIES COMPILE_OPTIONS
              "-Wno-constant-logical-operand;-Wno-overlength-strings")
endif()
target_include_directories(semu_core PUBLIC
  ${CMAKE_CURRENT_SOURCE_DIR}/../include
  ${CMAKE_CURRENT_SOURCE_DIR}/../generated
)
target_link_libraries(semu_core PUBLIC semu_buildinfo)
target_compile_options(semu_core PRIVATE ${SEMU_WARN_FLAGS})

# fp.cpp computes FP results under a dynamic fenv rounding mode; this flag
# (with `#pragma STDC FENV_ACCESS ON`) is the compile contract that stops the
# optimizer from folding/reassociating the rounding-mode-dependent arithmetic.
if(CMAKE_CXX_COMPILER_ID MATCHES "GNU|Clang")
  set_source_files_properties(fp.cpp PROPERTIES
    COMPILE_OPTIONS "-frounding-math")
  # tensor.cpp uses __int128 for the FDA/GDFS fixed-point accumulators (the
  # worst-case OMMA scale alignment needs >64 bits); __int128 is a GNU/Clang
  # extension so -Wpedantic is relaxed for this translation unit only.
  set_source_files_properties(tensor.cpp PROPERTIES
    COMPILE_OPTIONS "-Wno-pedantic")
endif()