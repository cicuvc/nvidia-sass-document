#pragma once

#include <initializer_list>
#include <memory>
#include <optional>
#include <string>
#include <utility>
#include <vector>

#include <semu/core/version.hpp>

// Unified error model: ErrorCode, Error (value type with optional cause
// chain), Status (void-or-error), and Result<T> (value-or-error).
//
// This is the stable public error surface called out by SIM_PLAN Phase 0:
// every backend, the debugger and the profiler report failures through these
// types, and the Phase 0 exit criterion is that later phases do not need to
// change them.

namespace semu {

enum class ErrorCode : std::uint32_t {
    kNone = 0,
    // generic
    kInvalidArgument,
    kNotFound,
    kNotSupported,
    kUnimplemented,
    kIllegalState,
    kOutOfRange,
    kOutOfMemory,
    kIoError,
    kInternal,
    // module / cubin loading
    kBadCubin,            // malformed ELF64/cubin
    kUnknownMetadata,     // unrecognized but skippable EIATTR
    kUnsupportedMetadata, // unknown metadata that affects execution
    // virtual memory
    kBadAddress,
    kAlignmentViolation,
    kOob,                 // out-of-bounds within a device allocation
    kLifecycle,           // use-after-free / double-free / leak
    // decode
    kDecodeIllegal,       // illegal encoding (reserved/discriminator bits)
    kDecodeAmbiguous,     // not uniquely decodable
    kDecodeUnsupported,   // decode-only / not-yet-implemented instruction
    // execution
    kInstructionLimit,
    kNoProgress,
    kBarrierDeadlock,
    kFault,               // generic simulator fault
};

// Stable machine name for an error code (used in reports/JSON).
const char* to_string(ErrorCode code);

// Short human description.
const char* describe(ErrorCode code);

// Value-type error object.  Errors can chain causes (the root cause is the
// last element of the chain) and accumulate context frames as they propagate.
class Error {
public:
    Error() = default;
    Error(ErrorCode code, std::string message);
    Error(ErrorCode code, std::string message, Error cause);

    ErrorCode code() const { return code_; }
    const std::string& message() const { return message_; }
    bool ok() const { return code_ == ErrorCode::kNone; }

    bool has_cause() const { return cause_ != nullptr; }
    const Error& cause() const;  // requires has_cause()
    // [this, cause, cause-of-cause, ...]
    std::vector<const Error*> cause_chain() const;
    // message + context frames + full cause chain, one line each
    std::string describe() const;

    // Append a contextual frame ("while loading kernel 'foo'").  Context is
    // rendered in insertion order after the message.
    void push_context(std::string frame);
    const std::vector<std::string>& context() const { return context_; }
    std::string to_string() const;  // message + context (no chain)

    // Factories for the common generic codes.
    static Error invalid_argument(std::string message);
    static Error not_found(std::string message);
    static Error not_supported(std::string message);
    static Error unimplemented(std::string message);
    static Error illegal_state(std::string message);
    static Error out_of_range(std::string message);
    static Error out_of_memory(std::string message);
    static Error io_error(std::string message);
    static Error internal(std::string message);

private:
    ErrorCode code_ = ErrorCode::kNone;
    std::string message_;
    std::shared_ptr<Error> cause_;
    std::vector<std::string> context_;
};

// void-or-error.  Prefer over throwing for non-exceptional control flow.
class Status {
public:
    static Status success();
    static Status failure(Error error);

    bool ok() const { return !error_.has_value(); }
    bool failed() const { return error_.has_value(); }
    const Error& error() const;  // requires failed()
    Error take_error();          // requires failed()
    // Move-only convenience: attach a context frame to a failed status.
    Status with_context(std::string frame) &&;

private:
    Status() = default;
    std::optional<Error> error_;
};

// T-or-error.
template <typename T>
class Result {
public:
    static Result success(T value) {
        Result r;
        r.value_ = std::move(value);
        return r;
    }
    static Result failure(Error error) {
        Result r;
        r.error_ = std::move(error);
        return r;
    }

    bool ok() const { return value_.has_value(); }
    bool failed() const { return error_.has_value(); }
    T& value() { return *value_; }
    const T& value() const { return *value_; }
    Error take_error() { return std::move(*error_); }
    Status status() const {
        return failed() ? Status::failure(*error_) : Status::success();
    }

private:
    Result() = default;
    std::optional<T> value_;
    std::optional<Error> error_;
};

// Common alias used across the codebase.
template <typename T>
using StatusOr = Result<T>;

}  // namespace semu
