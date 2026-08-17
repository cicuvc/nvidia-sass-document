add_executable(semu main.cpp)
target_link_libraries(semu PRIVATE semu_core)
target_compile_options(semu PRIVATE ${SEMU_WARN_FLAGS})
