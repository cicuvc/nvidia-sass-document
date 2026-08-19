#pragma once

// Frozen public API surface markers (SIM_PLAN Phase 10).
//
// Phase 10 freezes the *interface contracts* a future JIT backend plugs into:
//
//   - the IBackend contract (context.hpp / mock_backend.hpp)
//   - the decoded IR (decoder.hpp: DecodedInstruction / Operand / ScheduleWord /
//     slot_values; cubin.hpp: PredecodedWord / Kernel)
//   - the runtime services (context.hpp: IRuntimeServices)
//   - the event stream (context.hpp: IEventSink / BasicMemoryEvent;
//     memory_events.hpp: MemoryEvent; profiler.hpp: profiler schema)
//   - the fault ABI (fault.hpp: Fault / FaultKind; status.hpp: Status / Error /
//     ErrorCode)
//
// What is NOT frozen by Phase 10: instruction semantics still marked
// decode-only in the capability manifest (TMA family, sparse/rowcol/scale
// tensor variants, unsupported modifiers).  Closing those semantics never
// requires a breaking ABI change; the capability manifest is the tri-state
// source of truth for "can this variant execute".
//
// Each header below carries a freeze comment naming the version constant that
// covers it.  Bump the constant ONLY on a breaking change to the corresponding
// contract (a changed virtual-method signature, a removed field, a changed
// enum value).  Extensions that ADD new virtual methods MUST be added through
// a versioned extension interface (see the reserved async/TMA extension
// points in context.hpp) so existing implementors keep compiling.

namespace semu {

// IBackend + BackendLaunchRequest + Context::launch.  A JIT backend implements
// IBackend today with no changes to the loader, launch API, memory model,
// debugger or profiler schema (Phase 10 exit criterion).
inline constexpr int kBackendApiVersion = 1;

// decoded IR consumed by execution backends: DecodedInstruction, DecodeResult,
// Operand, ScheduleWord, PredecodedWord, Kernel.  A future JIT lowers exactly
// this IR; the interpretation of the flattened `slot_values` / `raw_fields`
// maps is stable.
// v2: DecodedInstruction's mnemonic / variant_class / pipe are now the
// generated isa::{Mnemonic,VariantClass,Pipe} enums instead of std::string.
inline constexpr int kDecodedIrVersion = 2;

// IRuntimeServices (memory / constant bank / event channel / cluster DSMEM).
// Async/TMA semantics are NOT frozen; their future completion/commit callbacks
// and mbarrier state queries are reserved as a versioned EXTENSION set (see
// context.hpp) so TMA can move decode-only -> functional without touching this
// ABI.
inline constexpr int kRuntimeServicesVersion = 1;

// Event stream: BasicMemoryEvent + IEventSink + EventKind (context.hpp) and
// the Phase 8 normalized MemoryEvent stream (memory_events.hpp).  The profiler
// JSON report schema is locked separately by profiler::kReportSchemaVersion.
inline constexpr int kEventStreamVersion = 1;

// Fault ABI: Fault + FaultKind + Error + Status + ErrorCode.  Phase 0 required
// later phases to enrich Fault context *fields* only, never to change the
// surface; kFaultAbiVersion locks that promise.
inline constexpr int kFaultAbiVersion = 1;

}  // namespace semu