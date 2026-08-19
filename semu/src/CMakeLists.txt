add_library(semu_core STATIC
  status.cpp
  fault.cpp
  word.cpp
  capability.cpp
  version.cpp
  memory.cpp
  context.cpp
  cluster.cpp
  interpreter.cpp
  debugger.cpp
  tensor_map.cpp
  tensor.cpp
  mbarrier.cpp
  fp.cpp
  fast_fp.cpp
  memory.cpp
  memory_service.cpp
  mock_backend.cpp
  l1tex_model.cpp
  shared_bank.cpp
  global_model.cpp
  profiler.cpp
  subcore_scheduler.cpp
  l2_events.cpp
  hb_clock.cpp
  race_detector.cpp
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
