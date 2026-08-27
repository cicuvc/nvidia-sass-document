add_executable(semu main.cpp)
target_link_libraries(semu PRIVATE semu_core)
target_compile_options(semu PRIVATE ${SEMU_WARN_FLAGS})

# Test/diagnostic probe tools (decode-json etc.) -- kept out of the
# user-facing `semu` command surface.
add_executable(semu_probe probe.cpp)
target_link_libraries(semu_probe PRIVATE semu_core)
target_compile_options(semu_probe PRIVATE ${SEMU_WARN_FLAGS})
