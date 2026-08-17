#pragma once

// Minimal header-only test framework (stdlib only, no external deps).  A test
// is a static function registered via TEST(name).  run_all() executes in
// registration order and returns the number of failures (0 = pass).

#include <cstdio>
#include <functional>
#include <sstream>
#include <string>
#include <vector>

namespace semu_test {

struct TestCase {
    std::string name;
    std::function<void()> fn;
};

inline std::vector<TestCase>& registry() {
    static std::vector<TestCase> r;
    return r;
}

struct Registrar {
    Registrar(std::string name, std::function<void()> fn) {
        registry().push_back({std::move(name), std::move(fn)});
    }
};

inline int& fail_count() {
    static int n = 0;
    return n;
}

#define TEST(name)                                                          \
    static void test_##name();                                              \
    static semu_test::Registrar reg_##name(#name, test_##name);             \
    static void test_##name()

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            ++semu_test::fail_count();                                       \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__,     \
                         #cond);                                             \
        }                                                                    \
    } while (0)

#define CHECK_EQ(a, b)                                                       \
    do {                                                                     \
        const auto& _semu_a = (a);                                           \
        const auto& _semu_b = (b);                                           \
        if (!(_semu_a == _semu_b)) {                                         \
            ++semu_test::fail_count();                                       \
            std::ostringstream _semu_os;                                     \
            _semu_os << "FAIL " << __FILE__ << ":" << __LINE__ << ": "       \
                     << #a << " == " << #b << " (got '" << _semu_a << "' vs '" \
                     << _semu_b << "')";                                     \
            std::fprintf(stderr, "%s\n", _semu_os.str().c_str());            \
        }                                                                    \
    } while (0)

inline int run_all(const char* suite) {
    int failures = 0;
    for (const auto& tc : registry()) {
        const int before = fail_count();
        std::fprintf(stdout, "[ RUN      ] %s/%s\n", suite, tc.name.c_str());
        tc.fn();
        if (fail_count() == before) {
            std::fprintf(stdout, "[       OK ] %s/%s\n", suite, tc.name.c_str());
        } else {
            ++failures;
            std::fprintf(stderr, "[  FAILED  ] %s/%s\n", suite, tc.name.c_str());
        }
    }
    return failures;
}

}  // namespace semu_test
