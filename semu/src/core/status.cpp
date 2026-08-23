#include <semu/core/status.hpp>

#include <cstdio>

namespace semu {

const char* to_string(ErrorCode code) {
    switch (code) {
        case ErrorCode::kNone: return "kNone";
        case ErrorCode::kInvalidArgument: return "kInvalidArgument";
        case ErrorCode::kNotFound: return "kNotFound";
        case ErrorCode::kNotSupported: return "kNotSupported";
        case ErrorCode::kUnimplemented: return "kUnimplemented";
        case ErrorCode::kIllegalState: return "kIllegalState";
        case ErrorCode::kOutOfRange: return "kOutOfRange";
        case ErrorCode::kOutOfMemory: return "kOutOfMemory";
        case ErrorCode::kIoError: return "kIoError";
        case ErrorCode::kInternal: return "kInternal";
        case ErrorCode::kBadCubin: return "kBadCubin";
        case ErrorCode::kUnknownMetadata: return "kUnknownMetadata";
        case ErrorCode::kUnsupportedMetadata: return "kUnsupportedMetadata";
        case ErrorCode::kBadAddress: return "kBadAddress";
        case ErrorCode::kAlignmentViolation: return "kAlignmentViolation";
        case ErrorCode::kOob: return "kOob";
        case ErrorCode::kLifecycle: return "kLifecycle";
        case ErrorCode::kDecodeIllegal: return "kDecodeIllegal";
        case ErrorCode::kDecodeAmbiguous: return "kDecodeAmbiguous";
        case ErrorCode::kDecodeUnsupported: return "kDecodeUnsupported";
        case ErrorCode::kInstructionLimit: return "kInstructionLimit";
        case ErrorCode::kNoProgress: return "kNoProgress";
        case ErrorCode::kBarrierDeadlock: return "kBarrierDeadlock";
        case ErrorCode::kFault: return "kFault";
    }
    return "kUnknown";
}

const char* describe(ErrorCode code) {
    switch (code) {
        case ErrorCode::kNone: return "no error";
        case ErrorCode::kInvalidArgument: return "invalid argument";
        case ErrorCode::kNotFound: return "not found";
        case ErrorCode::kNotSupported: return "not supported";
        case ErrorCode::kUnimplemented: return "unimplemented";
        case ErrorCode::kIllegalState: return "illegal state";
        case ErrorCode::kOutOfRange: return "out of range";
        case ErrorCode::kOutOfMemory: return "out of memory";
        case ErrorCode::kIoError: return "i/o error";
        case ErrorCode::kInternal: return "internal error";
        case ErrorCode::kBadCubin: return "malformed cubin";
        case ErrorCode::kUnknownMetadata: return "unknown cubin metadata";
        case ErrorCode::kUnsupportedMetadata:
            return "unsupported execution-affecting metadata";
        case ErrorCode::kBadAddress: return "bad device address";
        case ErrorCode::kAlignmentViolation: return "misaligned device access";
        case ErrorCode::kOob: return "out-of-bounds device access";
        case ErrorCode::kLifecycle: return "device allocation lifecycle error";
        case ErrorCode::kDecodeIllegal: return "illegal instruction encoding";
        case ErrorCode::kDecodeAmbiguous: return "ambiguous instruction decode";
        case ErrorCode::kDecodeUnsupported: return "unsupported instruction";
        case ErrorCode::kInstructionLimit: return "dynamic instruction limit";
        case ErrorCode::kNoProgress: return "no scheduler progress";
        case ErrorCode::kBarrierDeadlock: return "barrier deadlock";
        case ErrorCode::kFault: return "simulator fault";
    }
    return "unknown error";
}

Error::Error(ErrorCode code, std::string message)
    : code_(code), message_(std::move(message)) {}

Error::Error(ErrorCode code, std::string message, Error cause)
    : code_(code),
      message_(std::move(message)),
      cause_(std::make_shared<Error>(std::move(cause))) {}

const Error& Error::cause() const { return *cause_; }

std::vector<const Error*> Error::cause_chain() const {
    std::vector<const Error*> chain;
    const Error* cur = this;
    while (cur != nullptr) {
        chain.push_back(cur);
        cur = cur->has_cause() ? &cur->cause() : nullptr;
    }
    return chain;
}

void Error::push_context(std::string frame) {
    context_.push_back(std::move(frame));
}

std::string Error::to_string() const {
    std::string out = message_;
    for (const auto& frame : context_) {
        out += "; ";
        out += frame;
    }
    return out;
}

std::string Error::describe() const {
    std::string out = to_string();
    const auto chain = cause_chain();
    if (chain.size() > 1) {
        out += "  (caused by: ";
        for (std::size_t i = 1; i < chain.size(); ++i) {
            if (i > 1) out += " -> ";
            out += chain[i]->message_;
        }
        out += ")";
    }
    return out;
}

Error Error::invalid_argument(std::string message) {
    return Error(ErrorCode::kInvalidArgument, std::move(message));
}
Error Error::not_found(std::string message) {
    return Error(ErrorCode::kNotFound, std::move(message));
}
Error Error::not_supported(std::string message) {
    return Error(ErrorCode::kNotSupported, std::move(message));
}
Error Error::unimplemented(std::string message) {
    return Error(ErrorCode::kUnimplemented, std::move(message));
}
Error Error::illegal_state(std::string message) {
    return Error(ErrorCode::kIllegalState, std::move(message));
}
Error Error::out_of_range(std::string message) {
    return Error(ErrorCode::kOutOfRange, std::move(message));
}
Error Error::out_of_memory(std::string message) {
    return Error(ErrorCode::kOutOfMemory, std::move(message));
}
Error Error::io_error(std::string message) {
    return Error(ErrorCode::kIoError, std::move(message));
}
Error Error::internal(std::string message) {
    return Error(ErrorCode::kInternal, std::move(message));
}

Status Status::success() { return Status(); }

Status Status::failure(Error error) {
    Status s;
    s.error_ = std::move(error);
    return s;
}

const Error& Status::error() const { return *error_; }

Error Status::take_error() { return std::move(*error_); }

Status Status::with_context(std::string frame) && {
    if (failed()) error_->push_context(std::move(frame));
    return std::move(*this);
}

}  // namespace semu
