add_executable(semu_test_core test_core.cpp)
target_link_libraries(semu_test_core PRIVATE semu_core)
target_compile_options(semu_test_core PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_decoder test_decoder.cpp)
target_link_libraries(semu_test_decoder PRIVATE semu_core)
target_compile_options(semu_test_decoder PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_cubin test_cubin.cpp)
target_link_libraries(semu_test_cubin PRIVATE semu_core)
target_compile_options(semu_test_cubin PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_memory test_memory.cpp)
target_link_libraries(semu_test_memory PRIVATE semu_core)
target_compile_options(semu_test_memory PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_cluster test_cluster.cpp)
target_link_libraries(semu_test_cluster PRIVATE semu_core)
target_compile_options(semu_test_cluster PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_interp test_interp.cpp)
target_link_libraries(semu_test_interp PRIVATE semu_core)
target_compile_options(semu_test_interp PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_interpreter_registry test_interpreter_registry.cpp)
target_link_libraries(semu_test_interpreter_registry PRIVATE semu_core)
target_compile_options(semu_test_interpreter_registry PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_fp test_fp.cpp)
target_link_libraries(semu_test_fp PRIVATE semu_core)
target_compile_options(semu_test_fp PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_l1tex test_l1tex.cpp)
target_link_libraries(semu_test_l1tex PRIVATE semu_core)
target_compile_options(semu_test_l1tex PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_shared_bank test_shared_bank.cpp)
target_link_libraries(semu_test_shared_bank PRIVATE semu_core)
target_compile_options(semu_test_shared_bank PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_global test_global.cpp)
target_link_libraries(semu_test_global PRIVATE semu_core)
target_compile_options(semu_test_global PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_profiler test_profiler.cpp)
target_link_libraries(semu_test_profiler PRIVATE semu_core)
target_compile_options(semu_test_profiler PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_subcore test_subcore.cpp)
target_link_libraries(semu_test_subcore PRIVATE semu_core)
target_compile_options(semu_test_subcore PRIVATE ${SEMU_WARN_FLAGS})
add_executable(semu_test_l2 test_l2.cpp)
target_link_libraries(semu_test_l2 PRIVATE semu_core)
target_compile_options(semu_test_l2 PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_race test_race.cpp)
target_link_libraries(semu_test_race PRIVATE semu_core)
target_compile_options(semu_test_race PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_debugger test_debugger.cpp)
target_link_libraries(semu_test_debugger PRIVATE semu_core)
target_compile_options(semu_test_debugger PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_tensor_map test_tensor_map.cpp)
target_link_libraries(semu_test_tensor_map PRIVATE semu_core)
target_compile_options(semu_test_tensor_map PRIVATE ${SEMU_WARN_FLAGS})

add_executable(semu_test_tensor test_tensor.cpp)
target_link_libraries(semu_test_tensor PRIVATE semu_core)
# tensor.cpp uses __int128 (GNU/Clang extension); relax pedantic here too.
target_compile_options(semu_test_tensor PRIVATE ${SEMU_WARN_FLAGS} -Wno-pedantic)

add_executable(semu_test_mbarrier test_mbarrier.cpp)
target_link_libraries(semu_test_mbarrier PRIVATE semu_core)
target_compile_options(semu_test_mbarrier PRIVATE ${SEMU_WARN_FLAGS})

# ---------------------------------------------------------------------------
# L0 unit tests (CPU only)
# ---------------------------------------------------------------------------
add_test(NAME core COMMAND semu_test_core)
add_test(NAME decoder COMMAND semu_test_decoder)
add_test(NAME cubin_loader COMMAND semu_test_cubin)
add_test(NAME memory COMMAND semu_test_memory)
add_test(NAME cluster COMMAND semu_test_cluster)
add_test(NAME interp COMMAND semu_test_interp)
add_test(NAME interpreter_registry COMMAND semu_test_interpreter_registry)
add_test(NAME fp COMMAND semu_test_fp)
add_test(NAME l1tex COMMAND semu_test_l1tex)
add_test(NAME shared_bank COMMAND semu_test_shared_bank)
add_test(NAME global COMMAND semu_test_global)
add_test(NAME profiler COMMAND semu_test_profiler)
add_test(NAME subcore COMMAND semu_test_subcore)
add_test(NAME l2 COMMAND semu_test_l2)
add_test(NAME race COMMAND semu_test_race)
add_test(NAME debugger COMMAND semu_test_debugger)
add_test(NAME tensor_map COMMAND semu_test_tensor_map)
add_test(NAME tensor COMMAND semu_test_tensor)
add_test(NAME mbarrier COMMAND semu_test_mbarrier)

# ---------------------------------------------------------------------------
# CLI smoke tests: --version, invalid command line, empty / missing module,
# capability manifest.  A Python driver asserts exit codes AND output so the
# tests are robust regardless of CTest WILL_FAIL/regex semantics.
# ---------------------------------------------------------------------------
if(Python3_FOUND)
  add_test(NAME cli_smoke
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/cli_smoke_test.py
            $<TARGET_FILE:semu>
            ${CMAKE_CURRENT_SOURCE_DIR}/data/empty_module.bin)
else()
  add_test(NAME cli_version COMMAND semu --version)
  add_test(NAME cli_invalid_command COMMAND semu frobnicate)
  set_tests_properties(cli_invalid_command PROPERTIES WILL_FAIL TRUE)
  add_test(NAME cli_empty_module COMMAND semu load
    ${CMAKE_CURRENT_SOURCE_DIR}/data/empty_module.bin)
  set_tests_properties(cli_empty_module PROPERTIES WILL_FAIL TRUE)
  add_test(NAME cli_capability COMMAND semu capability)
endif()

# ---------------------------------------------------------------------------
# Manifest byte-identical regeneration gate (needs python3, dev-only).
# ---------------------------------------------------------------------------
if(Python3_FOUND)
  add_test(NAME manifest_regen
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/manifest_regen_test.py
            ${CMAKE_SOURCE_DIR}/../sm120.json
            ${CMAKE_CURRENT_SOURCE_DIR}/../generated)
endif()

# ---------------------------------------------------------------------------
# Phase 1 verification gates (need python3 + sm120.json; CPU-only).
# ---------------------------------------------------------------------------
if(Python3_FOUND AND EXISTS ${CMAKE_SOURCE_DIR}/../sm120.json)
  # ISA table + corpus generators are deterministic and match committed inputs.
  add_test(NAME isa_regen
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/isa_regen_test.py
            ${CMAKE_SOURCE_DIR}/../sm120.json
            ${CMAKE_CURRENT_SOURCE_DIR}/../generated)

  # Corpus encode -> decode -> encode bit-exact round-trip; every encoded
  # variant must decode uniquely through the CLI.  The corpus is generated
  # on the fly when not present.
  set(SEMU_CORPUS ${CMAKE_BINARY_DIR}/semu_corpus.json)
  add_test(NAME decoder_roundtrip
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/decoder_roundtrip_test.py
            $<TARGET_FILE:semu>
            ${SEMU_CORPUS}
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # High-overlap opcodes (F2FP/F2I/BAR/CCTL/PLOP3/PSETP/...) decode uniquely;
  # reserved-bit flips must not silently match another variant.
  add_test(NAME decoder_ambig
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/decoder_ambig_test.py
            $<TARGET_FILE:semu>
            ${SEMU_CORPUS}
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # Condition evaluator coverage (GAP-04): every legality condition must be
  # fully parseable by the (Python reference) evaluator over the corpus.
  add_test(NAME cond_differential
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/cond_differential_test.py
            ${SEMU_CORPUS}
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # Compile-time hardening equivalence (kConds -> C++ thunks): the EMITTED
  # C++ expressions (gen_isa.CondEmitter) must evaluate identically to the
  # reference string evaluator (sass_cond) on randomized slot maps.
  add_test(NAME cond_compile_equiv
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/cond_compile_equiv_test.py
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # Generated operand-width metadata equivalence (gen_isa.SizeEmitter ->
  # per-variant width methods) vs the reference evaluator on random words.
  add_test(NAME size_compile_equiv
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/size_compile_equiv_test.py
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # Real cuobjdump vector differential (GAP-05): words extracted from sm120
  # cubins via cuobjdump -sass must decode uniquely with matching
  # mnemonic + registers.
  add_test(NAME decoder_cuobjdump
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/decoder_cuobjdump_test.py
            $<TARGET_FILE:semu>
            ${CMAKE_CURRENT_SOURCE_DIR}/data/cuobj_vectors_sm120.json)

  # Negative vectors (GAP-06): illegal-encoding table rows, discriminator
  # enum holes and register-alignment violations must be rejected.
  add_test(NAME decoder_negative
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/decoder_negative_test.py
            $<TARGET_FILE:semu>
            ${SEMU_CORPUS}
            ${CMAKE_SOURCE_DIR}/../sm120.json)

  # Fixture reproducibility (GAP-11): the committed cuobjdump fixture must be
  # rebuildable from repo content (committed cubins + regen sources).  Skips
  # when nvcc/cuobjdump are unavailable.
  add_test(NAME cuobj_regen
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/cuobj_regen_test.py)

  # Mutation test (GAP-10): the structured cuobjdump gate must reject every
  # tamper class (register/modifier/branch-target/extra-operand).
  add_test(NAME decoder_cuobjdump_tamper
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/decoder_cuobjdump_tamper_test.py
            $<TARGET_FILE:semu>)

  # Phase 2 loader gates: real cubins (assembler + nvcc when available)
  # cross-checked against readelf/cuobjdump, plus error-path coverage.
  add_test(NAME cubin_load
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/cubin_load_test.py
            $<TARGET_FILE:semu>)

  # Phase 5 compute semantics acceptance: random-operand fuzz of the
  # interpreter against an independent host reference oracle (no GPU) plus a
  # mutation gate (a tampered semu result must be detected).  The GPU
  # differential is run separately (tools/diff_phase5.py / --gpu) because it
  # needs a live sm_120 device.
  add_test(NAME fuzz_phase5
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/fuzz_phase5_test.py
            $<TARGET_FILE:semu>
            ${CMAKE_SOURCE_DIR}/../tools/fuzz_phase5.py)

  # Phase 9 tensor differential gate: C++ tensor-core interpreter == the
  # Python reference model (tools/hmma_model.py) bit-for-bit, driven through
  # `semu run` on hand-assembled HMMA/QMMA/OMMA kernels.  CPU-only (the GPU
  # differential is run separately via tools/tensor_gpu_differential.py).
  add_test(NAME tensor_differential
    COMMAND ${Python3_EXECUTABLE}
            ${CMAKE_SOURCE_DIR}/../tools/tensor_differential_test.py
            $<TARGET_FILE:semu>)
endif()

# Phase 5.5: fast-interpreter microbenchmark.  Built but NOT registered as a
# CTest gate (timing thresholds are only enforced on a dedicated stable
# machine; CI just requires it builds and produces valid JSON).
add_executable(semu_bench_fast_interp bench_fast_interp.cpp)
target_link_libraries(semu_bench_fast_interp PRIVATE semu_core)
target_compile_options(semu_bench_fast_interp PRIVATE ${SEMU_WARN_FLAGS})

# Phase 10: interpreter throughput benchmark + hotspot probe.  Built but NOT
# a CTest gate (no hard SLA; results are recorded to benchmarks/record.json).
add_executable(semu_bench_interp_throughput bench_interp_throughput.cpp)
target_link_libraries(semu_bench_interp_throughput PRIVATE semu_core)
target_compile_options(semu_bench_interp_throughput PRIVATE ${SEMU_WARN_FLAGS})

# ---------------------------------------------------------------------------
# Phase 10: public-API compile tests.  Every public header must be
# self-contained (compiles standalone with -Werror); the aggregate test also
# RUNS smoke checks over the frozen API surface (api.hpp contracts).
# ---------------------------------------------------------------------------

# Per-header standalone object compile: catches a header that only compiles
# because another include leaked its dependencies.
function(semu_header_object_check _name _header)
  set(_src "${CMAKE_CURRENT_BINARY_DIR}/hdr_check_${_name}.cpp")
  file(WRITE "${_src}" "#include <semu/${_header}>\n"
                       "int main() { return 0; }\n")
  add_library(hdr_check_${_name} OBJECT "${_src}")
  target_include_directories(hdr_check_${_name} PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/../include
    ${CMAKE_CURRENT_SOURCE_DIR}/../generated)
  target_compile_options(hdr_check_${_name} PRIVATE ${SEMU_WARN_FLAGS})
endfunction()

set(SEMU_PUBLIC_HEADERS
  core/api.hpp core/capability.hpp core/fault.hpp core/hb_clock.hpp
  core/status.hpp core/version.hpp core/word.hpp
  context/context.hpp context/mock_backend.hpp
  exec/cluster.hpp exec/debugger.hpp exec/execution.hpp
  exec/subcore_scheduler.hpp
  memory/global_model.hpp memory/l1tex_model.hpp memory/l2_events.hpp
  memory/memory.hpp memory/memory_events.hpp memory/memory_service.hpp
  memory/race_detector.hpp memory/shared_bank.hpp
  tensor/mbarrier.hpp tensor/tensor.hpp tensor/tensor_map.hpp
  fp/fast_fp.hpp fp/fp.hpp
  profiler/profiler.hpp
  decoder/decoder.hpp decoder/decoded_access.hpp decoder/decoded_base.hpp
  decoder/shape_in.hpp
  cubin/cubin.hpp
  interpreter/interpreter.hpp)
foreach(_h IN LISTS SEMU_PUBLIC_HEADERS)
  string(REPLACE ".hpp" "" _base "${_h}")
  string(REPLACE "/" "_" _base "${_base}")
  string(REPLACE "." "_" _base "${_base}")
  semu_header_object_check("${_base}" "${_h}")
endforeach()

add_executable(semu_test_api_compile compile_api_test.cpp)
target_link_libraries(semu_test_api_compile PRIVATE semu_core)
target_compile_options(semu_test_api_compile PRIVATE ${SEMU_WARN_FLAGS})
add_test(NAME api_compile COMMAND semu_test_api_compile)

# L1TEX estimator oracle cross-check CLI (Phase 6 Step 2B).
add_executable(semu_l1tex_cli ${CMAKE_SOURCE_DIR}/tools/l1tex_cli.cpp)
target_link_libraries(semu_l1tex_cli PRIVATE semu_core)
target_compile_options(semu_l1tex_cli PRIVATE ${SEMU_WARN_FLAGS})
if(Python3_FOUND)
  # C++ UnifiedV1Estimator must match the Python oracle field-by-field on all
  # frozen fixtures (affine/near/token exact; random C++==Python).  The
  # arch/l1tex reference tree is a dev dependency; the default points at the
  # repo's reference checkout so the oracle gate (840/365/216/520) always
  # compares real execution.  Override with -DL1TEX_ARCH_DIR=<path>.
  set(L1TEX_ARCH_DIR "" CACHE PATH "Path to the arch/l1tex reference tree")
  if(NOT L1TEX_ARCH_DIR)
    set(_candidate /home/cicuvc/cs/projects/arch/l1tex)
    if(EXISTS ${_candidate}/unified_model.py)
      set(L1TEX_ARCH_DIR ${_candidate})
    endif()
  endif()
  if(L1TEX_ARCH_DIR AND EXISTS ${L1TEX_ARCH_DIR}/unified_model.py)
    add_test(NAME l1tex_oracle
      COMMAND ${Python3_EXECUTABLE}
              ${CMAKE_SOURCE_DIR}/../tools/l1tex_oracle_check.py
              $<TARGET_FILE:semu_l1tex_cli>
              ${L1TEX_ARCH_DIR})
  endif()

  # Phase 8: profiler gates — LDGSTS corpus field-for-field vs the Python
  # unified reference (base fields hard, pure-count fields == hardware meas)
  # plus the frozen profiler JSON schema compatibility test.
  if(L1TEX_ARCH_DIR AND EXISTS ${L1TEX_ARCH_DIR}/unified_model.py)
    add_test(NAME profiler_report
      COMMAND ${Python3_EXECUTABLE}
              ${CMAKE_SOURCE_DIR}/../tools/profiler_report_test.py
              $<TARGET_FILE:semu>
              $<TARGET_FILE:semu_l1tex_cli>
              ${L1TEX_ARCH_DIR}
              ${CMAKE_BINARY_DIR})
  endif()
endif()

add_executable(semu_test_mock_backend test_mock_backend.cpp)
target_link_libraries(semu_test_mock_backend PRIVATE semu_core)
target_compile_options(semu_test_mock_backend PRIVATE ${SEMU_WARN_FLAGS})
add_test(NAME mock_backend COMMAND semu_test_mock_backend)
