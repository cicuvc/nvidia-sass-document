// Interpreter abstraction tests: IInterpreter surface + InterpreterRegistry
// (default availability, name lookup, registration/replacement).

#include <semu/decoder.hpp>
#include <semu/interpreter.hpp>

#include <cstdio>
#include <string>
#include <vector>

#include "test_framework.hpp"

using namespace semu;

namespace {

// A minimal alternative implementation used only to prove registry plumbing
// (it never executes anything).
class FakeInterpreter final : public IInterpreter {
public:
    explicit FakeInterpreter(const char* name) : name_(name) {}
    const char* name() const override { return name_; }
    bool handles(const DecodedInstruction&) const override { return false; }
    InterpreterResult run_result(const Kernel&, const LaunchEnv&,
                                 std::uint64_t, bool) const override {
        return InterpreterResult{};
    }
    InterpreterResult run_result(const Kernel&, const LaunchEnv&,
                                 const RunOptions&) const override {
        return InterpreterResult{};
    }
    std::optional<Fault> run(const Kernel&, const LaunchEnv&,
                             std::uint64_t, bool) const override {
        return std::nullopt;
    }
    std::optional<Fault> run(const Kernel&, const LaunchEnv&,
                             const RunOptions&) const override {
        return std::nullopt;
    }
    std::optional<Fault> run_shared(const Kernel&, const LaunchEnv&,
                                    std::vector<std::uint8_t>*, std::uint64_t) const override {
        return std::nullopt;
    }

private:
    const char* name_;
};

const FakeInterpreter kFakeA("fake-a");
const FakeInterpreter kFakeB("fake-b");
const IInterpreter* factory_a() { return &kFakeA; }
const IInterpreter* factory_b() { return &kFakeB; }

}  // namespace

TEST(registry_default_is_reference) {
    const IInterpreter* def = InterpreterRegistry::default_impl();
    CHECK(def != nullptr);
    CHECK(std::string(def->name()) == "reference-sm120");
    // The default must (like the static interpreter_handles) accept at least
    // a control-flow family so the mock backend can lower real kernels.
    // Verify through a real decode of a NOP word.
    const DecodeResult r =
        Decoder::instance().decode(/*mov_64__RR 0x0000000000007918*/ 0x0000000000007918ull,
                                   0x000fc00000000000ull);
    if (r.is_unique()) {
        // MOV is inside the interpreter's family boundary; a registry-level
        // consult must agree with the underlying implementation.
        CHECK(def->handles(r.instruction()) == interpreter_handles(r.instruction()));
    } else {
        // No assertion -- the exact opcode depends on the generated tables;
        // keep the smoke test non-fragile.
        std::printf("(note: mov_64__RR sample did not decode uniquely)\n");
    }
}

TEST(registry_lookup_and_replace) {
    // Unknown names resolve to nullptr (callers pick their own fallback).
    CHECK(InterpreterRegistry::find("no-such-interpreter") == nullptr);

    InterpreterRegistry::register_impl("fake-a", factory_a);
    const IInterpreter* f = InterpreterRegistry::find("fake-a");
    CHECK(f != nullptr);
    CHECK(std::string(f->name()) == "fake-a");
    // A registered impl is NOT the default; the reference stays default.
    CHECK(std::string(InterpreterRegistry::default_impl()->name()) ==
          "reference-sm120");

    // Replacement under the same name.
    InterpreterRegistry::register_impl("fake-a", factory_b);
    CHECK(std::string(InterpreterRegistry::find("fake-a")->name()) == "fake-b");

    // Registry listing contains both the replacement and a second entry.
    InterpreterRegistry::register_impl("fake-b", factory_b);
    const std::vector<std::string> names = InterpreterRegistry::names();
    bool has_a = false, has_b = false;
    for (const std::string& n : names) {
        if (n == "fake-a") has_a = true;
        if (n == "fake-b") has_b = true;
    }
    CHECK(has_a);
    CHECK(has_b);
}

int main(int argc, char** argv) {
    (void)argc;
    (void)argv;
    return semu_test::run_all("interpreter_registry");
}