// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_isa.py --shapes
//
// Typed decoded-IR schema used by the decoder's main storage path.
#pragma once

#include <cstdint>
#include <cstring>
#include <optional>
#include <memory>
#include <semu/decoded_base.hpp>
#ifdef NAN
#undef NAN
#endif

namespace semu::shape {

enum class OperandKind : std::uint8_t {
    kRegister,
    kUniformRegister,
    kPredicate,
    kUniformPredicate,
    kSImm,
    kUImm,
    kFImm16,
    kFImm32,
    kFImm64,
    kDesc,
    kSpecial,
};

struct OperandValue {
    std::uint8_t kind;   // OperandKind
    std::uint8_t flags;  // bit0 negate, bit1 absolute, bit2 pred_not
    union {
        std::uint64_t uimm64;  std::int64_t simm64;
        std::uint32_t uimm32;  std::int32_t simm32;
        float fimm32;          double dimm64;
        std::uint16_t uimm16;  std::uint8_t uimm8;
        std::int16_t simm16;   std::int8_t simm8;
        std::int32_t reg_idx;  std::int32_t ureg_idx;
        std::uint8_t pred_idx; std::uint64_t desc;
    } v;
};

// Reusable modifier enums (one per modifier FORMAT type).
enum class ABSONLY_ret : std::int32_t {
    kABS = 1,
};
enum class AIO : std::int32_t {
    kI = 0,
    kO = 1,
};
enum class AInteger : std::int32_t {
    k_32 = 0,
    k_64 = 1,
    k_96 = 2,
    k_128 = 3,
};
enum class ALLOnly : std::int32_t {
    kALL = 0,
};
enum class ANYONLY : std::int32_t {
    kANY = 1,
};
enum class AOFFI : std::int32_t {
    knoaoffi = 0,
    kAOFFI = 1,
    kUAOFFI = 2,
    kINVALID3 = 3,
};
enum class ARRIVEONLY : std::int32_t {
    kARRIVE = 10,
};
enum class ARRIVEONLY_syncs : std::int32_t {
    kARRIVE = 0,
};
enum class ASYNCONLY : std::int32_t {
    kASYNC = 0,
};
enum class ASYNCONLY_membar : std::int32_t {
    kASYNC = 1,
};
enum class ATOMCASSZ : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    kS32 = 1,
    k_64 = 2,
    kU64 = 2,
    kINVALID3 = 3,
    k_128 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class ATOMICFPOPS : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kMAX = 2,
    kINVALID3 = 3,
};
enum class ATOMICINTSIZES : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    kS32 = 1,
    k_64 = 2,
    kU64 = 2,
    kS64 = 3,
    k_128 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class AdMode : std::int32_t {
    kIA = 0,
    kIL = 1,
    kIS = 2,
    kISL = 3,
};
enum class AtomsOp : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kMAX = 2,
    kINC = 3,
    kDEC = 4,
    kAND = 5,
    kOR = 6,
    kXOR = 7,
    kEXCH = 8,
    kINVALID9 = 9,
};
enum class AtomsSPIN : std::int32_t {
    knoatomsspin = 0,
    kSPIN = 1,
};
enum class B3B0 : std::int32_t {
    kB0 = 0,
    kB1 = 1,
    kB2 = 2,
    kB3 = 3,
};
enum class BA : std::int32_t {
    knoba = 0,
    kBA = 1,
};
enum class BAROP : std::int32_t {
    kLEGACY = 0,
    kARVCNT = 1,
    kTRANSCNT = 2,
    kINVALID3 = 3,
};
enum class BASE : std::int32_t {
    kMAP = 0,
    kPATCH = 1,
    kPRIM = 2,
    kATTR = 3,
};
enum class BF16ONLY : std::int32_t {
    kBF16 = 4,
};
enum class BF16ONLY_f2fp : std::int32_t {
    kBF16 = 1,
};
enum class BF16ONLY_f2fp_ : std::int32_t {
    kBF16 = 9,
};
enum class BF16ONLY_frnd : std::int32_t {
    kBF16 = 36,
};
enum class BFONLY : std::int32_t {
    kBF = 0,
};
enum class BONLY : std::int32_t {
    kB = 1,
};
enum class BPT_PAUSE_DRAIN_PAUSE_QUIET : std::int32_t {
    kPAUSE = 2,
    kDRAIN = 5,
    kPAUSE_QUIET = 6,
};
enum class BPT_TRAP_INT : std::int32_t {
    kTRAP = 3,
    kINT = 4,
};
enum class BVal : std::int32_t {
    kBM = 0,
    kBF = 1,
};
enum class BYTE_MASK : std::int32_t {
    knobyte_mask = 0,
    kDST_G_BYTE_MASK = 1,
};
enum class BarArv : std::int32_t {
    kARV = 1,
};
enum class BarRED : std::int32_t {
    kRED = 2,
};
enum class BarSCAN : std::int32_t {
    kSCAN = 3,
};
enum class BarSYNCALL : std::int32_t {
    kSYNCALL = 4,
};
enum class BarSync : std::int32_t {
    kSYNC = 0,
};
enum class BarmdBAR : std::int32_t {
    kBAR = 0,
};
enum class BarmdRESULT : std::int32_t {
    kRESULT = 1,
};
enum class BarmdWARP : std::int32_t {
    kWARP = 2,
};
enum class Bop : std::int32_t {
    kAND = 0,
    kOR = 1,
    kXOR = 2,
    kINVALID3 = 3,
};
enum class CACHE_D_U : std::int32_t {
    kD = 0,
    kU = 1,
};
enum class CALL_DEPTH : std::int32_t {
    kINC = 0,
    kNOINC = 1,
};
enum class CAS : std::int32_t {
    kCAS = 0,
};
enum class CASONLY : std::int32_t {
    kCAS = 2,
};
enum class CASTONLY : std::int32_t {
    kCAST = 1,
};
enum class CCMP : std::int32_t {
    kF = 0,
    kCSM_TA = 1,
    kCSM_TR = 2,
    kCSM_MX = 3,
    kT = 4,
    kFCSM_TA = 5,
    kFCSM_TR = 6,
    kFCSM_MX = 7,
};
enum class CCTLONLY : std::int32_t {
    kCCTL = 0,
};
enum class CCTLTOp : std::int32_t {
    kIVTH = 1,
};
enum class CInteger_64 : std::int32_t {
    k_64 = 5,
};
enum class CL : std::int32_t {
    knocl = 0,
    kCL = 1,
};
enum class CLEAR : std::int32_t {
    knoclear = 0,
    kCLEAR = 1,
};
enum class CLEARONLY : std::int32_t {
    kCLEAR = 1,
};
enum class CLOSE : std::int32_t {
    kCLOSE = 1,
};
enum class COLLECTIVEONLY : std::int32_t {
    kCOLLECTIVE = 2,
};
enum class COLONLY : std::int32_t {
    kCOL = 1,
};
enum class COND : std::int32_t {
    knocond = 0,
    kU = 1,
    kDIV = 2,
    kCONV = 3,
};
enum class COND_DIV_CONV : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kDIV = 2,
    kCONV = 3,
};
enum class COND_DIV_CONV_jmp : std::int32_t {
    kDIV = 2,
    kCONV = 3,
};
enum class COND__DIV_CONV : std::int32_t {
    knocond__div_conv = 0,
    kDIV = 2,
    kCONV = 3,
};
enum class CONLY : std::int32_t {
    kC = 2,
};
enum class COP : std::int32_t {
    kEF = 0,
    kEN = 1,
    kEL = 2,
    kLU = 3,
    kEU = 4,
    kNA = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class COP2 : std::int32_t {
    kEFL2 = 0,
    kENL2 = 1,
    kELL2 = 2,
    kINVALID3 = 3,
};
enum class COP2_EFL2_ENL2_ELL2 : std::int32_t {
    kEFL2 = 0,
    kENL2 = 1,
    kELL2 = 2,
};
enum class COP_IVALL_IVALLP_WBALL_WBALLP : std::int32_t {
    kIVALL = 4,
    kIVALLP = 6,
    kWBALL = 7,
    kWBALLP = 8,
};
enum class COP_IVALL_WBALL : std::int32_t {
    kIVALL = 4,
    kWBALL = 7,
};
enum class COP_PF1_PF2_WB_IV_RS : std::int32_t {
    kPF1 = 0,
    kPF2 = 1,
    kWB = 2,
    kIV = 3,
    kRS = 5,
};
enum class COP_PF1_WB_IV_RS_PML2_DML2 : std::int32_t {
    kPF1 = 0,
    kDML2 = 10,
    kWB = 2,
    kIV = 3,
    kRS = 5,
    kPML2 = 9,
};
enum class COP_utmacctl : std::int32_t {
    kIV = 0,
    kPF = 1,
};
enum class CTAPOOLONLY : std::int32_t {
    kCTAPOOL = 1,
};
enum class CTA_DIM : std::int32_t {
    kX = 0,
    kY = 1,
    kZ = 2,
    kALL = 3,
};
enum class CUTONLY : std::int32_t {
    kCUT = 2,
};
enum class CWMode : std::int32_t {
    kC = 0,
    kW = 1,
};
enum class Cache : std::int32_t {
    kD = 0,
    kU = 1,
    kC = 2,
    kI = 3,
};
enum class ChkMode : std::int32_t {
    kDIVIDE = 0,
};
enum class Clamp1 : std::int32_t {
    kIGN = 0,
    kNEAR = 1,
    kTRAP = 2,
    kINVALID3 = 3,
};
enum class DC : std::int32_t {
    knodc = 0,
    kDC = 1,
};
enum class DEALLOCONLY : std::int32_t {
    kDEALLOC = 1,
};
enum class DEALLOCONLY_uvirtcount : std::int32_t {
    kDEALLOC = 0,
};
enum class DEFER_BLOCKINGONLY : std::int32_t {
    kDEFER_BLOCKING = 1,
};
enum class DEPTH : std::int32_t {
    knodepth = 0,
    kINC = 1,
    kDEC = 2,
    kINVALID3 = 3,
};
enum class DEPTH_cctl : std::int32_t {
    kSHALLOW = 0,
    kDEEP = 1,
};
enum class DIV : std::int32_t {
    knodiv = 0,
    kNDV = 1,
    kINVALID2 = 2,
    kDXY = 3,
};
enum class DIV__EXCLUSIVE : std::int32_t {
    knodiv__exclusive = 0,
    kEXCLUSIVE = 1,
};
enum class DOnly : std::int32_t {
    kD = 0,
};
enum class DSETP_FCMP : std::int32_t {
    kMIN = 0,
    kLT = 1,
    kEQU = 10,
    kLEU = 11,
    kGTU = 12,
    kNEU = 13,
    kGEU = 14,
    kMAX = 15,
    kEQ = 2,
    kLE = 3,
    kGT = 4,
    kNE = 5,
    kGE = 6,
    kNUM = 7,
    kNAN = 8,
    kLTU = 9,
};
enum class DST : std::int32_t {
    kG = 0,
    kS = 1,
};
enum class DSTFMT : std::int32_t {
    kF16 = 0,
    kBF16 = 1,
    kE3M4 = 10,
    kS2_6 = 11,
    kE8 = 12,
    kE0M3 = 2,
    kE2M1 = 3,
    kTF32 = 5,
    kE2M3 = 6,
    kE3M2 = 7,
    kE5M2 = 8,
    kE4M3 = 9,
};
enum class DSTFMT_E0M3_E2M1 : std::int32_t {
    kE0M3 = 2,
    kE2M1 = 3,
};
enum class DSTFMT_E2M3_E3M2_E5M2_E4M3_E3M4_E8 : std::int32_t {
    kE3M4 = 10,
    kE8 = 12,
    kE2M3 = 6,
    kE3M2 = 7,
    kE5M2 = 8,
    kE4M3 = 9,
};
enum class DSTFMT_F16_BF16 : std::int32_t {
    kF16 = 0,
    kBF16 = 1,
};
enum class DSTFMT_F16_F32_BF16 : std::int32_t {
    kF16 = 1,
    kF32 = 2,
    kBF16 = 4,
};
enum class DSTFMT_S2_U2 : std::int32_t {
    kU2 = 4,
    kS2 = 5,
};
enum class DSTFMT_S4_U4 : std::int32_t {
    kU4 = 6,
    kS4 = 7,
};
enum class DSTFMT_SRCFMT_F16F32_BF16F32 : std::int32_t {
    kF16_F32 = 17,
    kBF16_F32 = 20,
};
enum class DSTFMT_SRCFMT_F16F64_F32F64_BF16F64 : std::int32_t {
    kF16_F64 = 25,
    kF32_F64 = 26,
    kBF16_F64 = 28,
};
enum class DSTFMT_SRCFMT_F32F16_BF16F16_F16BF16_F32BF16 : std::int32_t {
    kF32_F16 = 10,
    kBF16_F16 = 12,
    kF16_BF16 = 33,
    kF32_BF16 = 34,
};
enum class DSTFMT_SRCFMT_F64F16_F64BF16 : std::int32_t {
    kF64_F16 = 11,
    kF64_BF16 = 35,
};
enum class DSTFMT_U64_S64 : std::int32_t {
    kU64 = 6,
    kS64 = 7,
};
enum class DSTFMT_U8_S8 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
};
enum class DSTFMT_U8_S8_U16_S16_U32_S32 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kU16 = 2,
    kS16 = 3,
    kU32 = 4,
    kS32 = 5,
};
enum class DSTFMT_i2i : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kU16 = 2,
    kS16 = 3,
};
enum class DSTFMT_uf2fp : std::int32_t {
    kBF16 = 0,
    kF16 = 1,
    kTF32 = 3,
    kE5M2 = 4,
    kE4M3 = 5,
};
enum class DUAL : std::int32_t {
    knodual = 0,
    kDUAL = 1,
};
enum class Dim1 : std::int32_t {
    k_1D = 0,
    k_1D_BUFFER = 1,
    k_1D_ARRAY = 2,
    k_2D = 3,
    k_2D_ARRAY = 4,
    k_3D = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class E : std::int32_t {
    knoe = 0,
    kE = 1,
};
enum class E8ONLY : std::int32_t {
    kE8 = 11,
};
enum class E8ONLY_mxqmma : std::int32_t {
    kE8 = 0,
};
enum class EONLY : std::int32_t {
    kE = 1,
};
enum class EONLY_ldgsts : std::int32_t {
    kE = 0,
};
enum class EXCHONLY : std::int32_t {
    kEXCH = 1,
};
enum class EXIT_MODE : std::int32_t {
    knoexit_mode = 0,
    kKEEPREFCOUNT = 1,
    kPREEMPTED = 2,
    kINVALID3 = 3,
};
enum class EXONLY : std::int32_t {
    kEX = 1,
};
enum class EXTRACT : std::int32_t {
    kH0 = 0,
    kH1 = 1,
};
enum class F16ONLY : std::int32_t {
    kF16 = 9,
};
enum class F16ONLY_f2fp : std::int32_t {
    kF16 = 0,
};
enum class F16ONLY_uf2fp : std::int32_t {
    kF16 = 3,
};
enum class F32ONLY : std::int32_t {
    kF32 = 18,
};
enum class F32ONLY_f2fp : std::int32_t {
    kF32 = 0,
};
enum class F32ONLY_hadd2 : std::int32_t {
    kF32 = 1,
};
enum class F32ONLY_i2fp : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kF32 = 2,
    kINVALID3 = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class F64_F32ONLY : std::int32_t {
    kF64_F32 = 19,
};
enum class F64ONLY : std::int32_t {
    kF64 = 27,
};
enum class FCMP : std::int32_t {
    kF = 0,
    kLT = 1,
    kEQU = 10,
    kLEU = 11,
    kGTU = 12,
    kNEU = 13,
    kGEU = 14,
    kT = 15,
    kEQ = 2,
    kLE = 3,
    kGT = 4,
    kNE = 5,
    kGE = 6,
    kNUM = 7,
    kNAN = 8,
    kLTU = 9,
};
enum class FILLCTRL : std::int32_t {
    knofillctrl = 0,
    kZFILL = 1,
};
enum class FINALONLY : std::int32_t {
    kFINAL = 0,
};
enum class FLUSHONLY : std::int32_t {
    kFLUSH = 2,
};
enum class FLUSHONLY_usetshmsz : std::int32_t {
    kFLUSH = 1,
};
enum class FMT : std::int32_t {
    kU32 = 0,
    kS32 = 1,
};
enum class FMT_64_DIST : std::int32_t {
    kU64 = 2,
    kS64 = 3,
};
enum class FMT_F16_BF16 : std::int32_t {
    kF16 = 1,
    kBF16 = 2,
};
enum class FMT_S32_U32 : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kS32 = 2,
    kU32 = 3,
};
enum class FMT_shf : std::int32_t {
    kS64 = 0,
    kU64 = 1,
    kS32 = 2,
    kU32 = 3,
};
enum class FMT_viadd : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    k_16x2 = 1,
    kU16x2 = 1,
    kS32 = 2,
    kS16x2 = 3,
    kU8x4 = 4,
    kS8x4 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class FMT_vimnmx : std::int32_t {
    kU32 = 0,
    kS32 = 1,
    kU16x2 = 2,
    kS16x2 = 3,
    kU8x4 = 4,
    kS8x4 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class FMZ : std::int32_t {
    knofmz = 0,
    kFMZ = 1,
    kFTZ = 2,
    kOOB = 3,
};
enum class FMZ_hfma2 : std::int32_t {
    knofmz_hfma2 = 0,
    kFMZ = 1,
    kFTZ = 2,
    kINVALID3 = 3,
};
enum class FTZ : std::int32_t {
    knoftz = 0,
    kFTZ = 1,
};
enum class Float16 : std::int32_t {
    kF16 = 1,
};
enum class Float32 : std::int32_t {
    kF32 = 2,
};
enum class Float64 : std::int32_t {
    kF64 = 3,
};
enum class FloatNo64 : std::int32_t {
    kF16 = 0,
    kF32 = 1,
};
enum class GONLY : std::int32_t {
    kG = 1,
};
enum class GPUONLY : std::int32_t {
    kGPU = 4,
};
enum class HILO : std::int32_t {
    kLO = 0,
    kHI = 1,
};
enum class HIONLY : std::int32_t {
    kHI = 2,
};
enum class HIONLY_lea : std::int32_t {
    kHI = 1,
};
enum class HSEL : std::int32_t {
    kH0 = 0,
    kH1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
};
enum class H_AND : std::int32_t {
    knoh_and = 0,
    kH_AND = 1,
};
enum class ICmpAll : std::int32_t {
    kF = 0,
    kLT = 1,
    kEQ = 2,
    kLE = 3,
    kGT = 4,
    kNE = 5,
    kGE = 6,
    kT = 7,
};
enum class IDEAction : std::int32_t {
    kEN = 0,
    kDI = 1,
};
enum class IDXOnly : std::int32_t {
    kIDX = 0,
};
enum class IGNORE_KILL : std::int32_t {
    knoignore_kill = 0,
    kIGNOREKILL = 1,
};
enum class INTOP_ADD_MIN_MAX_AND_OR_XOR : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kMAX = 2,
    kINVALID3 = 3,
    kINVALID4 = 4,
    kAND = 5,
    kOR = 6,
    kXOR = 7,
    kINVALID8 = 8,
    kINVALID9 = 9,
};
enum class IONLY : std::int32_t {
    kI = 3,
};
enum class ISAT : std::int32_t {
    knoisat = 0,
    kISAT = 1,
};
enum class ISBERD_SZ : std::int32_t {
    kU8 = 0,
    kU16 = 1,
    k_32 = 2,
    kINVALID3 = 3,
};
enum class ISBEWR_BASE : std::int32_t {
    kMAP = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kATTR = 3,
};
enum class ISWZA : std::int32_t {
    kH1_H0 = 0,
    kINVALID1 = 1,
    kH0_H0 = 2,
    kH1_H1 = 3,
};
enum class ISWZB : std::int32_t {
    kH1_H0 = 0,
    kF32 = 1,
    kH0_H0 = 2,
    kH1_H1 = 3,
    kH0_NH1 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class ISWZC : std::int32_t {
    kH0 = 0,
    kH1 = 1,
    kB0 = 2,
    kB1 = 3,
    kB2 = 4,
    kB3 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class IS_AONLY : std::int32_t {
    kIS_A = 1,
};
enum class IVALLONLY : std::int32_t {
    kIVALL = 4,
};
enum class IVALLONLY_cctlt : std::int32_t {
    kIVALL = 2,
};
enum class IVALLONLY_utmacctl : std::int32_t {
    kIVALL = 1,
};
enum class IVONLY : std::int32_t {
    kIV = 3,
};
enum class L2ONLY : std::int32_t {
    kL2 = 0,
};
enum class LC : std::int32_t {
    knolc = 0,
    kLC = 1,
    kULC = 2,
    kINVALID3 = 3,
};
enum class LDCONLY : std::int32_t {
    kLDC = 1,
};
enum class LDCUONLY : std::int32_t {
    kLDCU = 1,
};
enum class LDGMC_FP_OP : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kMAX = 2,
    kF32ADD = 3,
    kHPADD = 3,
};
enum class LDGMC_FP_SIZES : std::int32_t {
    kF16x2_RN = 0,
    kF16x4_RN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kF32_RN = 12,
    kF32x2_RN = 13,
    kF32x4_RN = 14,
    kF64_RN = 15,
    kINVALID16 = 16,
    kE5M2x4_RN = 17,
    kE5M2x8_RN = 18,
    kE5M2x16_RN = 19,
    kF16x8_RN = 2,
    kE4M3x4_RN = 20,
    kE4M3x8_RN = 21,
    kE4M3x16_RN = 22,
    kINVALID23 = 23,
    kINVALID24 = 24,
    kINVALID25 = 25,
    kINVALID26 = 26,
    kINVALID27 = 27,
    kINVALID28 = 28,
    kINVALID29 = 29,
    kBF16x2_RN = 3,
    kINVALID30 = 30,
    kINVALID31 = 31,
    kBF16x4_RN = 4,
    kBF16x8_RN = 5,
    kE3M4x4_RN = 6,
    kE3M4x8_RN = 7,
    kE3M4x16_RN = 8,
    kINVALID9 = 9,
};
enum class LDGSTSBARONLY : std::int32_t {
    kLDGSTSBAR = 0,
};
enum class LDONLY : std::int32_t {
    kLD = 1,
};
enum class LDONLY_syncs : std::int32_t {
    kLD = 0,
};
enum class LDSM_MODE : std::int32_t {
    kM88 = 0,
    kMT88 = 1,
    kM816 = 2,
    kM832 = 3,
    kMT1616 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class LDSM_NUM : std::int32_t {
    k_1 = 0,
    k_2 = 1,
    k_4 = 2,
    kINVALID3 = 3,
};
enum class LDSM_SZ : std::int32_t {
    k_16 = 0,
    kU4TO8 = 1,
    kS4TO8 = 2,
    kU2TO4 = 3,
    kS2TO4 = 4,
    kU4x16P64TO8 = 5,
    kU6x16P32TO8 = 6,
    k_8 = 7,
};
enum class LDSSIZE : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kU16 = 2,
    kS16 = 3,
    k_32 = 4,
    k_64 = 5,
    k_128 = 6,
};
enum class LEONLY : std::int32_t {
    kLE = 1,
};
enum class LOC : std::int32_t {
    kBYPASS = 0,
    kACCESS = 1,
};
enum class LODCTRL : std::int32_t {
    kFINE = 0,
    kCOARSE = 1,
};
enum class LODLC : std::int32_t {
    knolodlc = 0,
    kLZ = 1,
    kLB = 2,
    kLL = 3,
    kLC = 4,
    kLB_LC = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class LODLC_tex : std::int32_t {
    knolodlc_tex = 0,
    kLZ = 1,
    kLB_ULC = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kLB = 2,
    kLL = 3,
    kLC = 4,
    kLB_LC = 5,
    kULB = 6,
    kULL = 7,
    kULC = 8,
    kULB_LC = 9,
};
enum class LODLC_tld : std::int32_t {
    kLZ = 0,
    kLL = 1,
    kULL = 2,
    kINVALID3 = 3,
};
enum class LODOnly : std::int32_t {
    kLOD = 0,
};
enum class LOOnly : std::int32_t {
    kLO = 0,
};
enum class LOP : std::int32_t {
    kAND = 0,
    kOR = 1,
    kXOR = 2,
    kPASS_B = 3,
};
enum class LOP_POP : std::int32_t {
    kPOR = 0,
    kPAND = 1,
};
enum class LUTOnly : std::int32_t {
    kLUT = 0,
};
enum class MATCH_SZ : std::int32_t {
    kU32 = 0,
    kU64 = 1,
};
enum class MEMBAR_SEM : std::int32_t {
    kSC = 0,
    kALL = 1,
    knomembar_sem = 2,
    kMMIO = 3,
};
enum class MERGE_CONLY : std::int32_t {
    kMERGE_C = 1,
};
enum class MMAONLY : std::int32_t {
    kMMA = 1,
};
enum class MODE : std::int32_t {
    kPASS = 0,
    kCONSTANT = 1,
    kSTATE = 2,
    kINVALID3 = 3,
};
enum class MODE_2ALO_2AHI : std::int32_t {
    k_2A_LO = 1,
    k_2A_HI = 3,
};
enum class MODE_BAR_WARP : std::int32_t {
    kBAR = 0,
    kINVALID1 = 1,
    kWARP = 2,
    kINVALID3 = 3,
};
enum class MODE_FOOTPRINT : std::int32_t {
    kTEX = 0,
    kTXD = 1,
};
enum class MODE_IM2COL_W : std::int32_t {
    kINVALID0 = 0,
    kIM2COL = 1,
    kINVALID2 = 2,
    kW = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class MODE_TILED_GATHER4 : std::int32_t {
    kTILED = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    kGATHER4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class MODE_TILED_IM2COL_W_GATHER4 : std::int32_t {
    kTILED = 0,
    kIM2COL = 1,
    kINVALID2 = 2,
    kW = 3,
    kGATHER4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class MODE_ldtram : std::int32_t {
    kAB = 0,
    kC = 1,
};
enum class MODE_utmaredg : std::int32_t {
    kTILED = 0,
    kIM2COL = 1,
};
enum class MODE_utmastg : std::int32_t {
    kTILED = 0,
    kIM2COL = 1,
    kSCATTER4 = 2,
    kINVALID3 = 3,
};
enum class MOVM_MODE : std::int32_t {
    kMT88 = 0,
    kM832 = 1,
    kM864 = 2,
    kINVALID3 = 3,
};
enum class MOVM_SZ : std::int32_t {
    k_16 = 0,
    kU4TO8 = 1,
    kS4TO8 = 2,
    kU2TO4 = 3,
    kS2TO4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class MS : std::int32_t {
    knoms = 0,
    kMS = 1,
    kUMS = 2,
    kINVALID3 = 3,
};
enum class MSI_CENTER_CENTROID : std::int32_t {
    kCENTER = 0,
    kCENTROID = 1,
};
enum class MUFUOP_COS_SIN_EX2_LG2_RCP_RSQ_SQRT_TANH : std::int32_t {
    kCOS = 0,
    kSIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kEX2 = 2,
    kLG2 = 3,
    kRCP = 4,
    kRSQ = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
    kSQRT = 8,
    kTANH = 9,
};
enum class MUFU_OP : std::int32_t {
    kCOS = 0,
    kSIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kEX2 = 2,
    kLG2 = 3,
    kRCP = 4,
    kRSQ = 5,
    kRCP64H = 6,
    kRSQ64H = 7,
    kSQRT = 8,
    kTANH = 9,
};
enum class MULTICAST : std::int32_t {
    knomulticast = 0,
    kMULTICAST = 1,
};
enum class MULTICASTONLY : std::int32_t {
    kMULTICAST = 1,
};
enum class NAN : std::int32_t {
    knonan = 0,
    kNAN = 1,
};
enum class NODEP : std::int32_t {
    knonodep = 0,
    kNODEP = 1,
};
enum class NONCONFORMITY_FILL_BROADCAST : std::int32_t {
    kFILL = 1,
    kBROADCAST = 2,
};
enum class NONE : std::int32_t {
    knonone = 0,
};
enum class NOTTID0 : std::int32_t {
    knonottid0 = 0,
    kNOT_TID0 = 1,
};
enum class NO_ATEXIT : std::int32_t {
    knono_atexit = 0,
    kNO_ATEXIT = 1,
};
enum class NTZ : std::int32_t {
    knontz = 0,
    kNTZ = 1,
};
enum class OFFSETONLY : std::int32_t {
    kOFFSET = 2,
};
enum class OFMT : std::int32_t {
    kF16_V2 = 0,
    kF32 = 1,
    kBF16_V2 = 2,
    kINVALID3 = 3,
};
enum class OFMT_DIST : std::int32_t {
    kF16_V2 = 0,
    kBF16_V2 = 2,
};
enum class OFMT_F16_V2_BF16_V2 : std::int32_t {
    kF16_V2 = 0,
    kINVALID1 = 1,
    kBF16_V2 = 2,
    kINVALID3 = 3,
};
enum class ONEONLY : std::int32_t {
    kONE = 1,
};
enum class ONLY168128 : std::int32_t {
    k_168128 = 0,
};
enum class ONLY16832 : std::int32_t {
    k_16832 = 0,
};
enum class ONLY16864 : std::int32_t {
    k_16864 = 0,
};
enum class ONLY1CTA : std::int32_t {
    k_1CTA = 0,
    kINVALID1 = 1,
};
enum class ONLY1X : std::int32_t {
    k_1X = 0,
};
enum class ONLY24 : std::int32_t {
    k_24 = 2,
};
enum class ONLY256 : std::int32_t {
    k_256 = 1,
};
enum class ONLY256_ldcu : std::int32_t {
    k_256 = 0,
};
enum class ONLY28 : std::int32_t {
    k_28 = 3,
};
enum class ONLY32 : std::int32_t {
    k_32 = 0,
};
enum class ONLY4A : std::int32_t {
    k_4A = 0,
};
enum class ONLY64 : std::int32_t {
    k_64 = 1,
};
enum class ONLY64_atom : std::int32_t {
    k_64 = 2,
};
enum class ONLY64_syncs : std::int32_t {
    k_64 = 0,
};
enum class OONLY : std::int32_t {
    kO = 1,
};
enum class OPTIONAL_WARP : std::int32_t {
    knooptional_warp = 0,
    kWARP = 1,
};
enum class OPTOUT : std::int32_t {
    knooptout = 0,
    kOPTOUT = 1,
};
enum class OP_ADD_MIN_MAX_INC_DEC_AND_OR_XOR_EXCH_SAFEADD : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kMAX = 2,
    kINC = 3,
    kDEC = 4,
    kAND = 5,
    kOR = 6,
    kXOR = 7,
    kEXCH = 8,
    kSAFEADD = 9,
};
enum class ORDER : std::int32_t {
    knoorder = 0,
    kORDERED = 1,
};
enum class ORONLY : std::int32_t {
    kOR = 1,
};
enum class PACK_ABONLY : std::int32_t {
    kPACK_AB = 0,
};
enum class PACK_AB_MERGE_CONLY : std::int32_t {
    kPACK_AB_MERGE_C = 5,
};
enum class PACK_BONLY : std::int32_t {
    kPACK_B = 3,
};
enum class PARAMTYPE : std::int32_t {
    kA1TR = 0,
    kA1T0 = 1,
    kA0T1 = 2,
    kA0TR = 3,
    kA0TX = 4,
    kART0 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class PF2ONLY : std::int32_t {
    kPF2 = 1,
};
enum class PHASECHKONLY : std::int32_t {
    kPHASECHK = 1,
};
enum class PHYSONLY : std::int32_t {
    kPHYS = 2,
};
enum class PIXLD_MODE : std::int32_t {
    kMSCOUNT = 0,
    kCOVMASK = 1,
    kCENTROID_OFFSET = 2,
    kMY_INDEX = 3,
    kINNER_COVERAGE = 4,
};
enum class PLOP_OP_NOREG : std::int32_t {
    kAND = 32768,
    kXOR = 38400,
    kSEL = 51712,
    kOR = 65024,
};
enum class PMode : std::int32_t {
    kIDX = 0,
    kF4E = 1,
    kB4E = 2,
    kRC8 = 3,
    kECL = 4,
    kECR = 5,
    kRC16 = 6,
    kINVALID7 = 7,
};
enum class PONLY : std::int32_t {
    kP = 1,
};
enum class POPC_INCONLY : std::int32_t {
    kPOPC_INC = 11,
};
enum class PQUAD : std::int32_t {
    knopquad = 0,
    kPQUAD = 1,
};
enum class PRIVATE : std::int32_t {
    knoprivate = 0,
    kPRIVATE = 1,
};
enum class PSETP_BOP0 : std::int32_t {
    kAND = 0,
    kOR = 1,
    kXOR = 2,
};
enum class PSEUDO_OP : std::int32_t {
    k_1_M8128 = 0,
    k_2_M864 = 0,
    k_4_M832 = 0,
    k_8_M816 = 0,
    knopseudo_op = 0,
};
enum class PSEUDO_OPCODE : std::int32_t {
    kIADD = 0,
    kISCADD = 0,
    kMOV = 0,
    kSHL = 0,
    knopseudo_opcode = 0,
};
enum class QFAULTONLY : std::int32_t {
    kQFAULT = 1,
};
enum class QInteger : std::int32_t {
    k_32 = 0,
    k_64 = 1,
};
enum class QUERY_SPACE : std::int32_t {
    kG = 0,
    kL = 1,
    kS = 2,
    kD = 3,
};
enum class RAND : std::int32_t {
    knorand = 0,
    kRAND = 1,
};
enum class REDAS_SZ : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    kS32 = 1,
    k_64 = 2,
    kU64 = 2,
    kINVALID3 = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class REDSOP : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kMAX = 2,
    kINC = 3,
    kDEC = 4,
    kAND = 5,
    kOR = 6,
    kXOR = 7,
    kINVALID8 = 8,
    kINVALID9 = 9,
};
enum class REDSSIZE : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    kS32 = 1,
    k_64 = 2,
    kU64 = 2,
    kS64 = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class REDUX_OP : std::int32_t {
    kAND = 0,
    kOR = 1,
    kXOR = 2,
    kSUM = 3,
    kMIN = 4,
    kMAX = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class RELIABILITY_RELIABLE_RECONVERGENT : std::int32_t {
    kRELIABLE = 1,
    kRECONVERGENT = 2,
};
enum class RELIABLEONLY : std::int32_t {
    kRELIABLE = 1,
};
enum class RELONLY : std::int32_t {
    kREL = 0,
};
enum class RELU : std::int32_t {
    knorelu = 0,
    kRELU = 1,
};
enum class RELUONLY : std::int32_t {
    kRELU = 2,
};
enum class RETVAL_OLDSTATE_TMASK_RED : std::int32_t {
    kOLDSTATE = 0,
    kTMASK = 1,
    kRED = 2,
    kINVALID3 = 3,
};
enum class RET_ADDR : std::int32_t {
    kREL = 0,
    kABS = 1,
};
enum class RET_DEPTH : std::int32_t {
    kDEC = 0,
    kNODEC = 1,
};
enum class REUSE : std::int32_t {
    knoreuse = 0,
    kreuse = 1,
};
enum class RGBA : std::int32_t {
    kINVALID0 = 0,
    kR = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kRGBA = 15,
    kINVALID2 = 2,
    kRG = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
    kINVALID8 = 8,
    kINVALID9 = 9,
};
enum class RM16 : std::int32_t {
    knorm16 = 0,
    k_16_S_OR_RN = 1,
    kF16_RN = 1,
    k_16_U_OR_RZ = 2,
    kF16_RZ = 2,
    kINVALID3 = 3,
};
enum class RML2ONLY : std::int32_t {
    kRML2 = 11,
};
enum class RML2ONLY_ldg : std::int32_t {
    kRML2 = 3,
};
enum class RNDMODE_RN_RP_RZ : std::int32_t {
    kRN = 0,
    kRP = 2,
    kRZ = 3,
};
enum class RNDMODE_RN_RZ : std::int32_t {
    kRN = 0,
    kRZ = 3,
};
enum class RND_RN_RZ : std::int32_t {
    kRN = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kRZ = 3,
};
enum class RND_ROUND_TRUNC : std::int32_t {
    kROUND = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kTRUNC = 3,
};
enum class RNONLY : std::int32_t {
    kRN = 0,
};
enum class ROWONLY : std::int32_t {
    kROW = 0,
};
enum class Red : std::int32_t {
    kPOPC = 0,
    kAND = 1,
    kOR = 2,
    kINVALID3 = 3,
};
enum class RedOp : std::int32_t {
    kADD = 0,
    kMIN = 1,
    kMAX = 2,
    kINC = 3,
    kDEC = 4,
    kAND = 5,
    kOR = 6,
    kXOR = 7,
};
enum class Round1 : std::int32_t {
    kRN = 0,
    kRM = 1,
    kRP = 2,
    kRZ = 3,
};
enum class Round3 : std::int32_t {
    kROUND = 0,
    kFLOOR = 1,
    kCEIL = 2,
    kTRUNC = 3,
};
enum class S2_6ONLY : std::int32_t {
    kS2_6 = 11,
};
enum class S2_6ONLY_mxqmma : std::int32_t {
    kS2_6 = 0,
};
enum class S32ONLY : std::int32_t {
    kS32 = 5,
};
enum class S32ONLY_i2i : std::int32_t {
    kS32 = 0,
};
enum class S64ONLY : std::int32_t {
    kS64 = 7,
};
enum class SAT : std::int32_t {
    knosat = 0,
    kSAT = 1,
};
enum class SATFINITE : std::int32_t {
    knosatfinite = 0,
    kSATFINITE = 1,
};
enum class SATFINITEONLY : std::int32_t {
    kSATFINITE = 1,
};
enum class SATNARROW : std::int32_t {
    kSATFINITE = 0,
    kSATNARROW = 1,
};
enum class SATONLY : std::int32_t {
    kSAT = 0,
};
enum class SATRELU : std::int32_t {
    knosatrelu = 0,
    kSAT = 1,
    kSATRELU = 2,
    kINVALID3 = 3,
};
enum class SATRELU_RELU : std::int32_t {
    knosatrelu_relu = 0,
    kSAT = 1,
    kRELU = 2,
    kINVALID3 = 3,
};
enum class SATRELU_ui2ip : std::int32_t {
    knosatrelu_ui2ip = 0,
    kSAT = 1,
    kRELU = 2,
    kSATRELU = 2,
    kINVALID3 = 3,
};
enum class SCALEFMT : std::int32_t {
    kE8 = 0,
    kUE4M3 = 1,
};
enum class SCALEVECTORSZ : std::int32_t {
    k_4X = 0,
    k_2X = 1,
};
enum class SCO : std::int32_t {
    knosco = 0,
    kCTA = 1,
    kSM = 2,
    kVC = 3,
    kGPU = 4,
    kSYS = 5,
};
enum class SCO_CTA_SM_GPU_SYS_VC_CTAPARTIAL : std::int32_t {
    kCTA = 0,
    kSM = 1,
    kGPU = 2,
    kSYS = 3,
    kINVALID4 = 4,
    kVC = 5,
    kCTA_PARTIAL = 6,
    kINVALID7 = 7,
};
enum class SCRONLY : std::int32_t {
    kSCR = 1,
};
enum class SDIR : std::int32_t {
    kL = 0,
    kR = 1,
};
enum class SEM : std::int32_t {
    kCONSTANT = 0,
    kWEAK = 1,
    kSTRONG = 2,
    kMMIO = 3,
};
enum class SEM_ublkcp : std::int32_t {
    kWEAK = 1,
    kSTRONG = 2,
};
enum class SEQ : std::int32_t {
    knoseq = 0,
    kSEQUENCED = 1,
};
enum class SFONLY : std::int32_t {
    kSF = 0,
};
enum class SH : std::int32_t {
    knosh = 0,
    kSH = 1,
};
enum class SHALLOWONLY : std::int32_t {
    kSHALLOW = 0,
};
enum class SIGNONLY : std::int32_t {
    kSIGN = 0,
};
enum class SIZE : std::int32_t {
    kU32 = 0,
    kS32 = 1,
    kINVALID10 = 10,
    kINVALID11 = 11,
    kINVALID12 = 12,
    kINVALID13 = 13,
    kINVALID14 = 14,
    kINVALID15 = 15,
    kU64 = 2,
    kS64 = 3,
    kF16_RN = 4,
    kF32_RN = 5,
    kF32_FTZ_RN = 6,
    kF64_RN = 7,
    kBF16_RN = 8,
    kINVALID9 = 9,
};
enum class SIZE2 : std::int32_t {
    k_32 = 0,
    k_64 = 1,
    k_128 = 2,
    kINVALID3 = 3,
};
enum class SIZE_16816_16832 : std::int32_t {
    k_16816 = 0,
    k_16832 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
};
enum class SIZE_16816_16832_imma : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    k_16816 = 4,
    k_16832 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class SIZE_16832_16864 : std::int32_t {
    kINVALID0 = 0,
    k_16832 = 1,
    k_16864 = 2,
    kINVALID3 = 3,
};
enum class SIZE_16832_16864_imma : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    kINVALID4 = 4,
    k_16832 = 5,
    k_16864 = 6,
    kINVALID7 = 7,
};
enum class SIZE_1688_16816_16832 : std::int32_t {
    k_1688 = 0,
    k_16816 = 1,
    kINVALID2 = 2,
    k_16832 = 3,
};
enum class SIZE_1688_16816_1684 : std::int32_t {
    k_1688 = 0,
    k_16816 = 1,
    k_1684 = 2,
    kINVALID3 = 3,
};
enum class SIZE_DMMA : std::int32_t {
    k_884 = 0,
    k_8x8x4 = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
};
enum class SKEW : std::int32_t {
    knoskew = 0,
    kSKEW = 1,
};
enum class SMPOOLONLY : std::int32_t {
    kSMPOOL = 0,
};
enum class SONLY : std::int32_t {
    kS = 0,
};
enum class SONLY_ublkred : std::int32_t {
    kINVALID0 = 0,
    kS = 1,
};
enum class SP2 : std::int32_t {
    knosp2 = 0,
    kLTC64B = 1,
    kLTC128B = 2,
    kLTC256B = 3,
};
enum class SPFORMAT : std::int32_t {
    kTID = 0,
    kREGOFFSET = 1,
};
enum class SPILLONLY : std::int32_t {
    kSPILL = 1,
};
enum class SPONLY : std::int32_t {
    kSP = 1,
};
enum class SRCFMT : std::int32_t {
    kF16 = 0,
    kBF16 = 1,
    kTF32 = 2,
    kINVALID3 = 3,
};
enum class SRCFMT16A : std::int32_t {
    kU16 = 0,
    kS16 = 1,
};
enum class SRCFMTA : std::int32_t {
    kE2M1 = 0,
    kE0M3 = 1,
};
enum class SRCFMTA_U8_S8 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    kINVALID4 = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class SRCFMTA_qmma : std::int32_t {
    kE4M3 = 0,
    kE5M2 = 1,
    kE3M4 = 2,
    kE3M2 = 3,
    kE2M3 = 4,
    kE2M1 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class SRCFMT_E0M3_E2M1 : std::int32_t {
    kE0M3 = 4,
    kE2M1 = 5,
};
enum class SRCFMT_E5M2_E4M3 : std::int32_t {
    kE5M2 = 0,
    kE4M3 = 1,
};
enum class SRCFMT_E5M2_E4M3_E2M3_E3M2_E3M4 : std::int32_t {
    kE5M2 = 2,
    kE4M3 = 3,
    kE2M3 = 6,
    kE3M2 = 7,
    kE3M4 = 8,
};
enum class SRCFMT_E5M2_E4M3_E2M3_E3M2_E3M4_S2_6 : std::int32_t {
    kS2_6 = 10,
    kE5M2 = 2,
    kE4M3 = 3,
    kE2M3 = 6,
    kE3M2 = 7,
    kE3M4 = 8,
};
enum class SRCFMT_F16_BF16 : std::int32_t {
    kF16 = 1,
    kBF16 = 9,
};
enum class SRCFMT_U16_S16 : std::int32_t {
    kU16 = 2,
    kS16 = 3,
};
enum class SRCFMT_U32_S32 : std::int32_t {
    kU32 = 4,
    kS32 = 5,
};
enum class SRCFMT_U8_S8 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
};
enum class SRCFMT_i2fp : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    kU32 = 4,
    kS32 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class STRIDE : std::int32_t {
    kX1 = 0,
    kX4 = 1,
    kX8 = 2,
    kX16 = 3,
};
enum class STRONGONLY : std::int32_t {
    kSTRONG = 2,
};
enum class STSM_MODE : std::int32_t {
    kM88 = 0,
    kMT88 = 1,
    kMT168 = 2,
    kINVALID3 = 3,
};
enum class STSM_SZ : std::int32_t {
    k_16 = 0,
    k_8 = 1,
};
enum class SURFACESIZE : std::int32_t {
    k_32 = 0,
    kU32 = 0,
    kS32 = 1,
    k_64 = 2,
    kU64 = 2,
    kF32_FTZ_RN = 3,
    kF16x2_RN = 4,
    kS64 = 5,
    kSD32 = 6,
    kSD64 = 7,
};
enum class SX32ONLY : std::int32_t {
    kSX32 = 1,
};
enum class SYNCALL : std::int32_t {
    knosyncall = 0,
    kSYNCALL = 1,
};
enum class SYNCS_CCTL_OP : std::int32_t {
    kIV = 0,
    kWB = 1,
};
enum class SYNCS_CCTL_OP_ALL : std::int32_t {
    kIVALL = 0,
    kWBALL = 1,
};
enum class SYNCS_MOD : std::int32_t {
    knosyncs_mod = 0,
    kSYNCS = 1,
};
enum class SYSONLY : std::int32_t {
    kSYS = 5,
};
enum class SZ_0 : std::int32_t {
    kF16x2_RN = 0,
    kF16x4_RN = 1,
    kF32x2_FTZ_RN = 10,
    kF32x4_FTZ_RN = 11,
    kF32_RN = 12,
    kF32x2_RN = 13,
    kF32x4_RN = 14,
    kF64_RN = 15,
    kINVALID16 = 16,
    kINVALID17 = 17,
    kINVALID18 = 18,
    kINVALID19 = 19,
    kF16x8_RN = 2,
    kINVALID20 = 20,
    kINVALID21 = 21,
    kINVALID22 = 22,
    kINVALID23 = 23,
    kINVALID24 = 24,
    kINVALID25 = 25,
    kINVALID26 = 26,
    kINVALID27 = 27,
    kINVALID28 = 28,
    kINVALID29 = 29,
    kBF16x2_RN = 3,
    kINVALID30 = 30,
    kINVALID31 = 31,
    kBF16x4_RN = 4,
    kBF16x8_RN = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
    kINVALID8 = 8,
    kF32_FTZ_RN = 9,
};
enum class SZ_32_64_128 : std::int32_t {
    kINVALID0 = 0,
    kINVALID1 = 1,
    kINVALID2 = 2,
    kINVALID3 = 3,
    k_32 = 4,
    k_64 = 5,
    k_128 = 6,
    kINVALID7 = 7,
};
enum class SZ_U8_S8_U16_S16_32_64 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kU16 = 2,
    kS16 = 3,
    k_32 = 4,
    k_64 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class SZ_U8_S8_U16_S16_32_64_128 : std::int32_t {
    kU8 = 0,
    kS8 = 1,
    kU16 = 2,
    kS16 = 3,
    k_32 = 4,
    k_64 = 5,
    k_128 = 6,
    kINVALID7 = 7,
};
enum class Scale : std::int32_t {
    kINVALID0 = 0,
    kD8 = 1,
    kD4 = 2,
    kD2 = 3,
    knoscale = 4,
    kM2 = 5,
    kM4 = 6,
    kM8 = 7,
};
enum class Shflmd : std::int32_t {
    kIDX = 0,
    kUP = 1,
    kDOWN = 2,
    kBFLY = 3,
};
enum class TCNTONLY : std::int32_t {
    kTCNT = 0,
};
enum class TENSORDIM : std::int32_t {
    k_1D = 0,
    k_2D = 1,
    k_3D = 2,
    k_4D = 3,
    k_5D = 4,
    kINVALID5 = 5,
    kINVALID6 = 6,
    kINVALID7 = 7,
};
enum class TEXONLY : std::int32_t {
    kTEX = 0,
};
enum class TEXUNPACK : std::int32_t {
    knotexunpack = 0,
    kTEXUNPACK = 1,
    kHDRUNPACK = 2,
    kINVALID3 = 3,
};
enum class TF32ONLY : std::int32_t {
    kTF32 = 5,
};
enum class TF32ONLY_uf2fp : std::int32_t {
    kTF32 = 3,
};
enum class TOFF : std::int32_t {
    knotoff = 0,
    kAOFFI = 1,
    kPTP = 2,
    kUAOFFI = 3,
};
enum class TRANS64ONLY : std::int32_t {
    kTRANS64 = 0,
};
enum class TRY_ALLOCONLY : std::int32_t {
    kTRY_ALLOC = 2,
};
enum class TYPE_EMIT_THEN_CUT_EMIT : std::int32_t {
    kEMIT = 1,
    kEMIT_THEN_CUT = 3,
};
enum class TexComp : std::int32_t {
    kR = 0,
    kG = 1,
    kB = 2,
    kA = 3,
};
enum class U32ONLY : std::int32_t {
    kU32 = 0,
};
enum class U32ONLY_i2f : std::int32_t {
    kU32 = 4,
};
enum class U64ONLY : std::int32_t {
    kU64 = 6,
};
enum class UAI : std::int32_t {
    knouai = 0,
    kUAI = 1,
};
enum class UGETNEXTWORKID_CAST : std::int32_t {
    kSELFCAST = 0,
    kBROADCAST = 1,
};
enum class UNPACK_BONLY : std::int32_t {
    kUNPACK_B = 2,
};
enum class UNPACK_B_MERGE_CONLY : std::int32_t {
    kUNPACK_B_MERGE_C = 4,
};
enum class UONLY : std::int32_t {
    kU = 1,
};
enum class USEL : std::int32_t {
    kALL = 0,
    kANY = 1,
};
enum class VCONLY : std::int32_t {
    kVC = 5,
};
enum class VIEWONLY : std::int32_t {
    kVIEW = 0,
};
enum class VOP : std::int32_t {
    kINVALID0 = 0,
    kR = 1,
    kA = 2,
    kRA = 3,
};
enum class VoteOp : std::int32_t {
    kALL = 0,
    kANY = 1,
    kEQ = 2,
    kINVALID3 = 3,
};
enum class WAIT : std::int32_t {
    kONCE = 0,
    kTRYWAIT = 1,
};
enum class WATCH : std::int32_t {
    knowatch = 0,
    kWATCH = 1,
};
enum class WIDEONLY : std::int32_t {
    kWIDE = 1,
};
enum class XONLY : std::int32_t {
    kX = 1,
};
enum class XORSIGN : std::int32_t {
    knoxorsign = 0,
    kXORSIGN = 1,
};

// Derived decoded types: one per (mnemonic, operand-count).
// Operands are positional in the mnemonic's canonical role order;
// modifiers are typed enum members specific to each instruction.
struct DecodedMOV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV2>(*this);
    }
    OperandValue ops[2];
    ONLY64 size;
    SPILLONLY nonconformity;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedP2R4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedP2R4>(*this);
    }
    OperandValue ops[4];
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedR2P3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedR2P3>(*this);
    }
    OperandValue ops[3];
    B3B0 a_bsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSEL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSEL4>(*this);
    }
    OperandValue ops[4];
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSEL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSEL4>(*this);
    }
    OperandValue ops[4];
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMNMX4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMNMX4>(*this);
    }
    OperandValue ops[4];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMNMX5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMNMX5>(*this);
    }
    OperandValue ops[5];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    IS_AONLY is_A;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSET4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSET4>(*this);
    }
    OperandValue ops[4];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSET3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSET3>(*this);
    }
    OperandValue ops[3];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSETP5>(*this);
    }
    OperandValue ops[5];
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSETP3>(*this);
    }
    OperandValue ops[3];
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP6>(*this);
    }
    OperandValue ops[6];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP5>(*this);
    }
    OperandValue ops[5];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP4>(*this);
    }
    OperandValue ops[4];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP3>(*this);
    }
    OperandValue ops[3];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD36>(*this);
    }
    OperandValue ops[6];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD38 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD38>(*this);
    }
    OperandValue ops[8];
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISCADD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISCADD5>(*this);
    }
    OperandValue ops[5];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA6>(*this);
    }
    OperandValue ops[6];
    HIONLY_lea hilo;
    XONLY X;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA5>(*this);
    }
    OperandValue ops[5];
    HIONLY_lea hilo;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA7>(*this);
    }
    OperandValue ops[7];
    HIONLY_lea hilo;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP5>(*this);
    }
    OperandValue ops[5];
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP4>(*this);
    }
    OperandValue ops[4];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP37>(*this);
    }
    OperandValue ops[7];
    LUTOnly lut;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP36>(*this);
    }
    OperandValue ops[6];
    LUTOnly lut;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP35 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP35>(*this);
    }
    OperandValue ops[5];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIABS2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIABS2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPRMT4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPRMT4>(*this);
    }
    OperandValue ops[4];
    PMode pmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMNMX7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMNMX7>(*this);
    }
    OperandValue ops[7];
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMNMX6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMNMX6>(*this);
    }
    OperandValue ops[6];
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHF4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHF4>(*this);
    }
    OperandValue ops[4];
    SDIR dir;
    CWMode cw;
    FMT_shf fmt;
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHL3>(*this);
    }
    OperandValue ops[3];
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHR3>(*this);
    }
    OperandValue ops[3];
    CWMode cw;
    FMT_S32_U32 fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSGXT3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSGXT3>(*this);
    }
    OperandValue ops[3];
    CWMode cw;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMSK3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMSK3>(*this);
    }
    OperandValue ops[3];
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35>(*this);
    }
    OperandValue ops[5];
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    SIGNONLY sign_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37>(*this);
    }
    OperandValue ops[7];
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    SIGNONLY sign_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMUL3>(*this);
    }
    OperandValue ops[3];
    FMZ_hfma2 fmz;
    Scale scale;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFADD3>(*this);
    }
    OperandValue ops[3];
    FTZ ftz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFHADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFHADD3>(*this);
    }
    OperandValue ops[3];
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
    EXTRACT extract_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFFMA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFFMA4>(*this);
    }
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFHFMA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFHFMA4>(*this);
    }
    OperandValue ops[4];
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
    EXTRACT extract_a;
    EXTRACT extract_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD4>(*this);
    }
    OperandValue ops[4];
    LOOnly wide;
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5>(*this);
    }
    OperandValue ops[5];
    LOOnly wide;
    PSEUDO_OPCODE pseudo_opcode;
    FMT fmt;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL3>(*this);
    }
    OperandValue ops[3];
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD6>(*this);
    }
    OperandValue ops[6];
    WIDEONLY wide;
    FMT fmt;
    XONLY X;
    PSEUDO_OPCODE pseudo_opcode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL4>(*this);
    }
    OperandValue ops[4];
    WIDEONLY wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDP4>(*this);
    }
    OperandValue ops[4];
    MODE_2ALO_2AHI mode;
    SRCFMT16A SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDP4A4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDP4A4>(*this);
    }
    OperandValue ops[4];
    SRCFMT_U8_S8 SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDMUL3>(*this);
    }
    OperandValue ops[3];
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDADD3>(*this);
    }
    OperandValue ops[3];
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDSETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDSETP5>(*this);
    }
    OperandValue ops[5];
    DSETP_FCMP test;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDSETP3>(*this);
    }
    OperandValue ops[3];
    DSETP_FCMP test;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDFMA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDFMA4>(*this);
    }
    OperandValue ops[4];
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCLMAD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCLMAD4>(*this);
    }
    OperandValue ops[4];
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD23>(*this);
    }
    OperandValue ops[3];
    F32ONLY_hadd2 ofmt;
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA24>(*this);
    }
    OperandValue ops[4];
    OFMT ofmt;
    FMZ fmz;
    SAT satrelu;
    ISWZA iswzA;
    ISWZB iswzB;
    ISWZA iswzC;
    MMAONLY MMA;
    NONE iswzA_forced_H1_H0;
    NONE iswzB_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    ISWZB iswzC_as_B;
    ISWZA iswzB_as_C;
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzB_as_C_forced_H1_H0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA25 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA25>(*this);
    }
    OperandValue ops[5];
    MMAONLY MMA;
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    RELUONLY satrelu;
    NONE iswzA_forced_H1_H0;
    NONE iswzB_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    ISWZA iswzA;
    ISWZB iswzB;
    ISWZA iswzC;
    ISWZB iswzC_as_B;
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzB_as_C_forced_H1_H0;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMUL23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMUL23>(*this);
    }
    OperandValue ops[3];
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    SAT sat;
    ISWZA iswzA;
    ISWZA iswzB;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET24>(*this);
    }
    OperandValue ops[4];
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET23>(*this);
    }
    OperandValue ops[3];
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP25 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP25>(*this);
    }
    OperandValue ops[5];
    OFMT_F16_V2_BF16_V2 ofmt;
    FCMP cmp;
    H_AND h_and;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP24>(*this);
    }
    OperandValue ops[4];
    OFMT_F16_V2_BF16_V2 ofmt;
    FCMP cmp;
    H_AND h_and;
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD4>(*this);
    }
    OperandValue ops[4];
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD5>(*this);
    }
    OperandValue ops[5];
    ONLY64 size;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVIADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVIADD3>(*this);
    }
    OperandValue ops[3];
    FMT_viadd fmt;
    ISAT isat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMMA5>(*this);
    }
    OperandValue ops[5];
    SIZE_16816_16832_imma size;
    SRCFMTA_U8_S8 srcFmtA;
    SRCFMTA_U8_S8 srcFmtB;
    SAT SAT_;
    ROWONLY row_A;
    COLONLY col_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMMA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMMA7>(*this);
    }
    OperandValue ops[7];
    SPONLY sp;
    SPFORMAT spformat;
    SIZE_16832_16864_imma size;
    SRCFMTA_U8_S8 srcFmtA;
    SRCFMTA_U8_S8 srcFmtB;
    SAT SAT_;
    ROWONLY row_A;
    COLONLY col_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedI2I2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedI2I2>(*this);
    }
    OperandValue ops[2];
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
    SATONLY SAT;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedI2IP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedI2IP4>(*this);
    }
    OperandValue ops[4];
    DSTFMT_S4_U4 dstfmt;
    S32ONLY_i2i srcfmt;
    SATRELU satrelu;
    ONLY24 extract_limited;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOVM2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOVM2>(*this);
    }
    OperandValue ops[2];
    MOVM_SZ sz;
    MOVM_MODE mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA7>(*this);
    }
    OperandValue ops[7];
    SPONLY sp;
    SPFORMAT spformat;
    SIZE_1688_16816_16832 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA5>(*this);
    }
    OperandValue ops[5];
    SIZE_1688_16816_1684 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2FP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP2>(*this);
    }
    OperandValue ops[2];
    RELU relu;
    F16ONLY_f2fp dstfmt;
    SRCFMT_E0M3_E2M1 srcfmt;
    UNPACK_BONLY merge;
    RNONLY rndMode;
    B3B0 selB;
    EXTRACT extract_B;
    SATFINITE satfinite;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2FP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP3>(*this);
    }
    OperandValue ops[3];
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_F16_BF16 dstfmt;
    F32ONLY_f2fp srcfmt;
    PACK_ABONLY merge;
    RNDMODE_RN_RZ rndMode;
    EXTRACT extract;
    SATNARROW satnarrow;
    B3B0 selB;
    ISWZC iswzC;
    EXTRACT extract_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2FP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP4>(*this);
    }
    OperandValue ops[4];
    SATFINITEONLY satfinite;
    RELU relu;
    DSTFMT_E0M3_E2M1 dstfmt;
    F32ONLY_f2fp srcfmt;
    PACK_AB_MERGE_CONLY merge;
    RNONLY rndMode;
    EXTRACT extract;
    SATNARROW satnarrow;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDMMA5>(*this);
    }
    OperandValue ops[5];
    SIZE_DMMA size;
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMNMX24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMNMX24>(*this);
    }
    OperandValue ops[4];
    OFMT_F16_V2_BF16_V2 ofmt;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    ISWZA iswzA;
    ISWZA iswzB;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMNMX26 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMNMX26>(*this);
    }
    OperandValue ops[6];
    OFMT_F16_V2_BF16_V2 ofmt;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    IS_AONLY isA;
    ISWZA iswzA;
    ISWZA iswzB;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2IP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2IP4>(*this);
    }
    OperandValue ops[4];
    DSTFMT_U8_S8 dstfmt;
    F32ONLY_hadd2 srcfmt;
    RND_ROUND_TRUNC rnd;
    NTZ ntz;
    RELU relu;
    EXTRACT extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedI2FP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedI2FP2>(*this);
    }
    OperandValue ops[2];
    F32ONLY_i2fp dstfmt;
    SRCFMT_i2fp srcfmt;
    RND_RN_RZ rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVIMNMX4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVIMNMX4>(*this);
    }
    OperandValue ops[4];
    FMT_vimnmx fmt;
    RELU relu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQMMA5>(*this);
    }
    OperandValue ops[5];
    SIZE_16816_16832 size;
    FloatNo64 dstfmt;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
    ROWONLY row_A;
    COLONLY col_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQMMA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQMMA7>(*this);
    }
    OperandValue ops[7];
    SPONLY sp;
    SPFORMAT spformat;
    SIZE_16832_16864 size;
    FloatNo64 dstfmt;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
    ROWONLY row_A;
    COLONLY col_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedR2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedR2UR3>(*this);
    }
    OperandValue ops[3];
    ORONLY OR;
    NONCONFORMITY_FILL_BROADCAST nonconformity;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFLO3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFLO3>(*this);
    }
    OperandValue ops[3];
    FMT fmt;
    SH sh;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBREV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBREV2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFCHK3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFCHK3>(*this);
    }
    OperandValue ops[3];
    ChkMode mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2F2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2F2>(*this);
    }
    OperandValue ops[2];
    FTZ ftz;
    DSTFMT_SRCFMT_F16F32_BF16F32 dstfmt_srcfmt;
    Round1 rnd;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2I2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2I2>(*this);
    }
    OperandValue ops[2];
    FTZ ftz;
    DSTFMT_U8_S8_U16_S16_U32_S32 dstfmt;
    Float16 srcfmt;
    Round3 rnd;
    NTZ ntz;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedI2F2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedI2F2>(*this);
    }
    OperandValue ops[2];
    DSTFMT_F16_F32_BF16 dstfmt;
    SRCFMT_U16_S16 srcfmt;
    Round1 rnd;
    HSEL hsel;
    B3B0 bsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFRND2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFRND2>(*this);
    }
    OperandValue ops[2];
    FTZ ftz;
    BF16ONLY_frnd fmt;
    Round3 rnd;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMUFU2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMUFU2>(*this);
    }
    OperandValue ops[2];
    MUFU_OP mufuop;
    FMT_F16_BF16 fmt;
    HSEL extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPOPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPOPC2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedB2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedB2R2>(*this);
    }
    OperandValue ops[2];
    BarmdBAR mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedB2R1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedB2R1>(*this);
    }
    OperandValue ops[1];
    BarmdWARP mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBAR2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBAR2>(*this);
    }
    OperandValue ops[2];
    BarArv barmode;
    DEFER_BLOCKINGONLY defer_blocking;
    std::uint8_t subclass;  // generated semantic flags
    std::uint8_t barname;  // unsurfaced barrier-id field
};
struct DecodedBAR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBAR3>(*this);
    }
    OperandValue ops[3];
    BarRED barmode;
    Red op;
    DEFER_BLOCKINGONLY defer_blocking;
    std::uint8_t subclass;  // generated semantic flags
    std::uint8_t barname;  // unsurfaced barrier-id field
};
struct DecodedR2B2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedR2B2>(*this);
    }
    OperandValue ops[2];
    MODE_BAR_WARP mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSETCTAID1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSETCTAID1>(*this);
    }
    OperandValue ops[1];
    CTA_DIM dim;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedALD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedALD4>(*this);
    }
    OperandValue ops[4];
    AIO io;
    PHYSONLY p;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedALD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedALD5>(*this);
    }
    OperandValue ops[5];
    AIO io;
    AInteger sz;
    PONLY p;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAST4>(*this);
    }
    OperandValue ops[4];
    PHYSONLY p;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAST5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAST5>(*this);
    }
    OperandValue ops[5];
    AInteger sz;
    PONLY p;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOUT3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOUT3>(*this);
    }
    OperandValue ops[3];
    CUTONLY type;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOUT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOUT1>(*this);
    }
    OperandValue ops[1];
    FINALONLY type;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA4>(*this);
    }
    OperandValue ops[4];
    MODE ipaop;
    MSI_CENTER_CENTROID msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA5>(*this);
    }
    OperandValue ops[5];
    MODE ipaop;
    OFFSETONLY msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL0>(*this);
    }
    CONLY cache;
    LDCONLY ldc;
    IVALLONLY cop;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCALL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCALL3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t abs;
    CALL_DEPTH depth;
    std::uint8_t rel;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCALL2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCALL2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t rel;
    CALL_DEPTH depth;
    std::uint8_t abs;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC2>(*this);
    }
    OperandValue ops[2];
    DIV__EXCLUSIVE div;
    ALLOnly all;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC3>(*this);
    }
    OperandValue ops[3];
    COLLECTIVEONLY div;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEPC1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEPC1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRPCMOV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRPCMOV2>(*this);
    }
    OperandValue ops[2];
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2>(*this);
    }
    OperandValue ops[2];
    ONLY32 sz;
    CLEAR clear;
    PQUAD pquad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOTRAP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOTRAP2>(*this);
    }
    OperandValue ops[2];
    RAND rand;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOSLEEP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOSLEEP2>(*this);
    }
    OperandValue ops[2];
    RAND rand;
    OPTIONAL_WARP warp;
    SYNCS_MOD syncs;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTEX9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTEX9>(*this);
    }
    OperandValue ops[9];
    BONLY b;
    RM16 rm16;
    LODLC_tex lodlc;
    AOFFI aoffi;
    UAI uai;
    DC dc;
    COP cop;
    DIV div;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTMML6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTMML6>(*this);
    }
    OperandValue ops[6];
    BONLY b;
    LODOnly lod;
    DIV div;
    NODEP nodep;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTXQ5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTXQ5>(*this);
    }
    OperandValue ops[5];
    BONLY b;
    NODEP nodep;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG5>(*this);
    }
    OperandValue ops[5];
    E e;
    COP cop;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedST3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedST3>(*this);
    }
    OperandValue ops[3];
    E e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG3>(*this);
    }
    OperandValue ops[3];
    E e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ORDER order;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTL3>(*this);
    }
    OperandValue ops[3];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTS3>(*this);
    }
    OperandValue ops[3];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHFL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHFL5>(*this);
    }
    OperandValue ops[5];
    Shflmd shflmd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM6>(*this);
    }
    OperandValue ops[6];
    E e;
    AtomsOp op;
    COP cop;
    ATOMICINTSIZES sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM7>(*this);
    }
    OperandValue ops[7];
    E e;
    CAS cas;
    COP cop;
    ATOMCASSZ sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    AtomsSPIN spin;
    AtomsOp op;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS4>(*this);
    }
    OperandValue ops[4];
    AtomsOp op;
    ATOMCASSZ sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDS3>(*this);
    }
    OperandValue ops[3];
    REDSOP op;
    REDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS5>(*this);
    }
    OperandValue ops[5];
    CAS cas;
    ATOMCASSZ sz;
    STRIDE stride;
    AtomsSPIN spin;
    AtomsOp op;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLT0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLT0>(*this);
    }
    IVALLONLY_cctlt cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLT1>(*this);
    }
    OperandValue ops[1];
    CCTLTOp cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUATOM6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUATOM6>(*this);
    }
    OperandValue ops[6];
    DOnly d;
    BA ba;
    Dim1 dim;
    UAI uai;
    AtomsOp op;
    COP cop;
    SURFACESIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    Clamp1 clamp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSURED4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSURED4>(*this);
    }
    OperandValue ops[4];
    DOnly d;
    BA ba;
    Dim1 dim;
    UAI uai;
    RedOp op;
    COP cop;
    SURFACESIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    Clamp1 clamp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMATCH3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMATCH3>(*this);
    }
    OperandValue ops[3];
    ALLOnly op;
    MATCH_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMATCH2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMATCH2>(*this);
    }
    OperandValue ops[2];
    ANYONLY op;
    MATCH_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG5>(*this);
    }
    OperandValue ops[5];
    E e;
    ATOMICFPOPS op;
    COP cop;
    SZ_0 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS0>(*this);
    }
    FLUSHONLY op;
    CCTLONLY cctl_mode;
    SYNCS_CCTL_OP_ALL cctlop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMG6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG6>(*this);
    }
    OperandValue ops[6];
    E e;
    CAS cas;
    COP cop;
    ATOMCASSZ sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ATOMICFPOPS op;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC3>(*this);
    }
    OperandValue ops[3];
    E e;
    QUERY_SPACE space;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC4>(*this);
    }
    OperandValue ops[4];
    E e;
    QUERY_SPACE space;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedGETLMEMBASE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedGETLMEMBASE1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSETLMEMBASE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSETLMEMBASE1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDUX2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDUX2>(*this);
    }
    OperandValue ops[2];
    REDUX_OP op;
    FMT sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFENCE0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFENCE0>(*this);
    }
    VIEWONLY type;
    ASYNCONLY syncType;
    SONLY memType;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUOPEN0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUOPEN0>(*this);
    }
    DUAL dual;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUST4>(*this);
    }
    OperandValue ops[4];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUCLOSE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUCLOSE1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTULD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTULD5>(*this);
    }
    OperandValue ops[5];
    CLOSE close;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUGO0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUGO0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUCCTL0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUCCTL0>(*this);
    }
    IVALLONLY_utmacctl ivall;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFADD32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFADD32I3>(*this);
    }
    OperandValue ops[3];
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD24>(*this);
    }
    OperandValue ops[4];
    F32ONLY_hadd2 ofmt;
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD2_32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD2_32I4>(*this);
    }
    OperandValue ops[4];
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA26 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA26>(*this);
    }
    OperandValue ops[6];
    MMAONLY MMA;
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    RELUONLY satrelu;
    NONE iswzA_forced_H1_H0;
    NONE iswzC_as_B_forced_H1_H0;
    ISWZA iswzA;
    ISWZB iswzC_as_B;
    NONE iswzC_forced_H1_H0;
    ISWZA iswzC;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET25 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET25>(*this);
    }
    OperandValue ops[5];
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP26 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP26>(*this);
    }
    OperandValue ops[6];
    OFMT_F16_V2_BF16_V2 ofmt;
    FCMP cmp;
    H_AND h_and;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQMMA8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQMMA8>(*this);
    }
    OperandValue ops[8];
    SFONLY sf;
    ONLY16832 size;
    F32ONLY_f2fp dstfmt;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
    E8ONLY_mxqmma scalefmt;
    ONLY1X scaleVectorSz;
    REUSE reuse_src_h;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQMMA9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQMMA9>(*this);
    }
    OperandValue ops[9];
    SFONLY sf;
    SPONLY sp;
    SPFORMAT spformat;
    ONLY16864 size;
    F32ONLY_f2fp dstfmt;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
    E8ONLY_mxqmma scalefmt;
    ONLY1X scaleVectorSz;
    REUSE reuse_src_h;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMXQMMA8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMXQMMA8>(*this);
    }
    OperandValue ops[8];
    SFONLY sf;
    ONLY16832 size;
    F32ONLY_f2fp dstfmt;
    S2_6ONLY_mxqmma srcFmtA;
    S2_6ONLY_mxqmma srcFmtB;
    E8ONLY_mxqmma scalefmt;
    ONLY1X scaleVectorSz;
    REUSE reuse_src_h;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOMMA8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOMMA8>(*this);
    }
    OperandValue ops[8];
    SFONLY sf;
    ONLY16864 size;
    F32ONLY_f2fp dstfmt;
    SRCFMTA srcFmtA;
    SRCFMTA srcFmtB;
    SCALEFMT scalefmt;
    SCALEVECTORSZ scaleVectorSz;
    REUSE reuse_src_h;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOMMA9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOMMA9>(*this);
    }
    OperandValue ops[9];
    SFONLY sf;
    SPONLY sp;
    SPFORMAT spformat;
    ONLY168128 size;
    F32ONLY_f2fp dstfmt;
    SRCFMTA srcFmtA;
    SRCFMTA srcFmtB;
    SCALEFMT scalefmt;
    SCALEVECTORSZ scaleVectorSz;
    REUSE reuse_src_h;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV64IUR2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV64IUR2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCGAERRBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCGAERRBAR0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPMTRIG2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPMTRIG2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV32I3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedP2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedP2R2>(*this);
    }
    OperandValue ops[2];
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCS2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCS2R2>(*this);
    }
    OperandValue ops[2];
    QInteger sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE3>(*this);
    }
    OperandValue ops[3];
    VoteOp voteop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST1>(*this);
    }
    OperandValue ops[1];
    VOP vtgmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST4>(*this);
    }
    OperandValue ops[4];
    VOP vtgmode;
    CCMP ccmp;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST2>(*this);
    }
    OperandValue ops[2];
    VOP vtgmode;
    CCMP ccmp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG1>(*this);
    }
    OperandValue ops[1];
    VOP vtgmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG4>(*this);
    }
    OperandValue ops[4];
    VOP vtgmode;
    CCMP ccmp;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG2>(*this);
    }
    OperandValue ops[2];
    VOP vtgmode;
    CCMP ccmp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISCADD32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISCADD32I5>(*this);
    }
    OperandValue ops[5];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP32I5>(*this);
    }
    OperandValue ops[5];
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP32I4>(*this);
    }
    OperandValue ops[4];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP34 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP34>(*this);
    }
    OperandValue ops[4];
    PLOP_OP_NOREG lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPSETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPSETP5>(*this);
    }
    OperandValue ops[5];
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPSETP3>(*this);
    }
    OperandValue ops[3];
    PSETP_BOP0 bop0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMUL32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMUL32I3>(*this);
    }
    OperandValue ops[3];
    FMZ_hfma2 fmz;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSWZADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSWZADD4>(*this);
    }
    OperandValue ops[4];
    FTZ ftz;
    Round1 rnd;
    DIV div;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFFMA32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFFMA32I4>(*this);
    }
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL32I3>(*this);
    }
    OperandValue ops[3];
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL32I4>(*this);
    }
    OperandValue ops[4];
    WIDEONLY wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPREEXIT0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPREEXIT0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedACQBULK0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedACQBULK0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedELECT3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedELECT3>(*this);
    }
    OperandValue ops[3];
    IGNORE_KILL ignoreKill;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA2_32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA2_32I5>(*this);
    }
    OperandValue ops[5];
    FMZ fmz;
    ISWZA iswzA;
    ISWZA iswzC;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMUL24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMUL24>(*this);
    }
    OperandValue ops[4];
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMUL2_32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMUL2_32I4>(*this);
    }
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD32I4>(*this);
    }
    OperandValue ops[4];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD32I5>(*this);
    }
    OperandValue ops[5];
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDSM3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDSM3>(*this);
    }
    OperandValue ops[3];
    LDSM_SZ sz;
    LDSM_MODE mode;
    LDSM_NUM num;
    PSEUDO_OP pseudo_op;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMNMX25 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMNMX25>(*this);
    }
    OperandValue ops[5];
    OFMT_F16_V2_BF16_V2 ofmt;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMNMX27 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMNMX27>(*this);
    }
    OperandValue ops[7];
    OFMT_F16_V2_BF16_V2 ofmt;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    IS_AONLY isA;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTSM3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTSM3>(*this);
    }
    OperandValue ops[3];
    STSM_SZ sz;
    STSM_MODE mode;
    LDSM_NUM num;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIRTCOUNT2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIRTCOUNT2>(*this);
    }
    OperandValue ops[2];
    DEALLOCONLY_uvirtcount op;
    SMPOOLONLY pool;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedACQSHMINIT0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedACQSHMINIT0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUMOV3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUMOV3>(*this);
    }
    OperandValue ops[3];
    ONLY64_syncs size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTEU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTEU3>(*this);
    }
    OperandValue ops[3];
    VoteOp voteop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP35 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP35>(*this);
    }
    OperandValue ops[5];
    PLOP_OP_NOREG lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP36>(*this);
    }
    OperandValue ops[6];
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    SIGNONLY sign_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP38 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP38>(*this);
    }
    OperandValue ops[8];
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    SIGNONLY sign_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPSETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPSETP6>(*this);
    }
    OperandValue ops[6];
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPSETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPSETP4>(*this);
    }
    OperandValue ops[4];
    PSETP_BOP0 bop0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCS2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCS2UR3>(*this);
    }
    OperandValue ops[3];
    QInteger sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNOP0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNOP0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedS2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedS2R2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR3>(*this);
    }
    OperandValue ops[3];
    LEONLY le;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR0>(*this);
    }
    ALLOnly le;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedENDCOLLECTIVE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedENDCOLLECTIVE1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAL2P3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAL2P3>(*this);
    }
    OperandValue ops[3];
    AIO io;
    AInteger sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISBERD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISBERD3>(*this);
    }
    OperandValue ops[3];
    AIO io;
    BASE base;
    SKEW skew;
    ISBERD_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPIXLD2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPIXLD2>(*this);
    }
    OperandValue ops[2];
    PIXLD_MODE mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISBEWR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISBEWR3>(*this);
    }
    OperandValue ops[3];
    OONLY io;
    ISBEWR_BASE base;
    SKEW skew;
    ISBERD_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBSYNC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBSYNC2>(*this);
    }
    OperandValue ops[2];
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBREAK2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBREAK2>(*this);
    }
    OperandValue ops[2];
    RELIABLEONLY reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBSSY3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBSSY3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t rel;
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedYIELD1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedYIELD1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRA2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRA2>(*this);
    }
    OperandValue ops[2];
    DEPTH depth;
    COND__DIV_CONV cond;
    USEL usel;
    NOTTID0 nottid0;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC1>(*this);
    }
    OperandValue ops[1];
    ALLOnly all;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRX3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRX3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMP2>(*this);
    }
    OperandValue ops[2];
    DEPTH depth;
    COND__DIV_CONV cond;
    USEL usel;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMX3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMX3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedEXIT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedEXIT1>(*this);
    }
    OperandValue ops[1];
    EXIT_MODE mode;
    NO_ATEXIT no_atexit;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEPC2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRTT0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRTT0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRET3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRET3>(*this);
    }
    OperandValue ops[3];
    ABSONLY_ret addr;
    RET_DEPTH depth;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRET2>(*this);
    }
    OperandValue ops[2];
    RET_ADDR addr;
    RET_DEPTH depth;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDE1>(*this);
    }
    OperandValue ops[1];
    IDEAction action;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedKILL1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedKILL1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBPT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBPT1>(*this);
    }
    OperandValue ops[1];
    BPT_TRAP_INT bpt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOSLEEP1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOSLEEP1>(*this);
    }
    OperandValue ops[1];
    CLEARONLY clear;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLD4>(*this);
    }
    OperandValue ops[4];
    E e;
    COP cop;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDL3>(*this);
    }
    OperandValue ops[3];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDS3>(*this);
    }
    OperandValue ops[3];
    LDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDG3>(*this);
    }
    OperandValue ops[3];
    E e;
    RedOp op;
    COP cop;
    REDSSIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL2>(*this);
    }
    OperandValue ops[2];
    E e;
    Cache cache;
    COP_PF1_WB_IV_RS_PML2_DML2 cop;
    LDCONLY ldc;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL3>(*this);
    }
    OperandValue ops[3];
    E e;
    Cache cache;
    PF2ONLY cop;
    QFAULTONLY qfault;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLL0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLL0>(*this);
    }
    COP_IVALL_WBALL cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLL2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLL2>(*this);
    }
    OperandValue ops[2];
    COP_PF1_PF2_WB_IV_RS cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMEMBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMEMBAR0>(*this);
    }
    MEMBAR_SEM sem;
    SCO_CTA_SM_GPU_SYS_VC_CTAPARTIAL sco;
    ASYNCONLY_membar mmio;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSULD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSULD5>(*this);
    }
    OperandValue ops[5];
    PONLY p;
    Dim1 dim;
    UAI uai;
    COP cop;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    RGBA rgba;
    Clamp1 clamp;
    DOnly d;
    BA ba;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUST4>(*this);
    }
    OperandValue ops[4];
    PONLY p;
    Dim1 dim;
    UAI uai;
    COP cop;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    RGBA rgba;
    Clamp1 clamp;
    DOnly d;
    BA ba;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedERRBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedERRBAR0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGDEPBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGDEPBAR0>(*this);
    }
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUQUERY6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUQUERY6>(*this);
    }
    OperandValue ops[6];
    BA ba;
    Dim1 dim;
    UAI uai;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACMDFLUSH1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACMDFLUSH1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACCTL1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACCTL1>(*this);
    }
    OperandValue ops[1];
    IVALLONLY_utmacctl ivall;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedS2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedS2UR3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUMACROFUSE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUMACROFUSE1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBAR0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBAR0>(*this);
    }
    BarSYNCALL barmode;
    DEFER_BLOCKINGONLY defer_blocking;
    std::uint8_t subclass;  // generated semantic flags
    std::uint8_t barname;  // unsurfaced barrier-id field
};
struct DecodedCCTL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL4>(*this);
    }
    OperandValue ops[4];
    CONLY cache;
    LDCONLY ldc;
    IVONLY cop;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDC5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDC5>(*this);
    }
    OperandValue ops[5];
    SZ_U8_S8_U16_S16_32_64 sz;
    AdMode ad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIADD4>(*this);
    }
    OperandValue ops[4];
    FMT_viadd fmt;
    ISAT isat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIMNMX5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIMNMX5>(*this);
    }
    OperandValue ops[5];
    FMT_vimnmx fmt;
    RELU relu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIABS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIABS3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2I3>(*this);
    }
    OperandValue ops[3];
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
    SATONLY SAT;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2IP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2IP5>(*this);
    }
    OperandValue ops[5];
    DSTFMT_S4_U4 dstfmt;
    S32ONLY_i2i srcfmt;
    SATRELU_ui2ip satrelu;
    ONLY24 extract_limited;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFMNMX5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFMNMX5>(*this);
    }
    OperandValue ops[5];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFMNMX6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFMNMX6>(*this);
    }
    OperandValue ops[6];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    IS_AONLY is_A;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSEL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSEL5>(*this);
    }
    OperandValue ops[5];
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSET5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSET5>(*this);
    }
    OperandValue ops[5];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSET4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSET4>(*this);
    }
    OperandValue ops[4];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSETP6>(*this);
    }
    OperandValue ops[6];
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSETP4>(*this);
    }
    OperandValue ops[4];
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFADD4>(*this);
    }
    OperandValue ops[4];
    FTZ ftz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFHADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFHADD4>(*this);
    }
    OperandValue ops[4];
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
    EXTRACT extract_a;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFFMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFFMA5>(*this);
    }
    OperandValue ops[5];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFHFMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFHFMA5>(*this);
    }
    OperandValue ops[5];
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
    EXTRACT extract_a;
    EXTRACT extract_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFMUL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFMUL4>(*this);
    }
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    Scale scale;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2IP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2IP5>(*this);
    }
    OperandValue ops[5];
    DSTFMT_U8_S8 dstfmt;
    F32ONLY_hadd2 srcfmt;
    RND_ROUND_TRUNC rnd;
    NTZ ntz;
    RELU relu;
    EXTRACT extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2F3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2F3>(*this);
    }
    OperandValue ops[3];
    DSTFMT_F16_F32_BF16 dstfmt;
    SRCFMT_U16_S16 srcfmt;
    Round1 rnd;
    HSEL hsel;
    B3B0 bsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2F3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2F3>(*this);
    }
    OperandValue ops[3];
    FTZ ftz;
    DSTFMT_SRCFMT_F16F32_BF16F32 dstfmt_srcfmt;
    Round1 rnd;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2I3>(*this);
    }
    OperandValue ops[3];
    FTZ ftz;
    DSTFMT_U8_S8_U16_S16_U32_S32 dstfmt;
    Float16 srcfmt;
    Round3 rnd;
    NTZ ntz;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFRND3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFRND3>(*this);
    }
    OperandValue ops[3];
    FTZ ftz;
    BF16ONLY_frnd fmt;
    Round3 rnd;
    HSEL hsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2FP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2FP3>(*this);
    }
    OperandValue ops[3];
    F32ONLY_i2fp dstfmt;
    SRCFMT_i2fp srcfmt;
    RND_RN_RZ rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMNMX8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMNMX8>(*this);
    }
    OperandValue ops[8];
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMNMX7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMNMX7>(*this);
    }
    OperandValue ops[7];
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSEL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSEL5>(*this);
    }
    OperandValue ops[5];
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP6>(*this);
    }
    OperandValue ops[6];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP7>(*this);
    }
    OperandValue ops[7];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP4>(*this);
    }
    OperandValue ops[4];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP5>(*this);
    }
    OperandValue ops[5];
    ICmpAll icmp;
    FMT_64_DIST fmt;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD37>(*this);
    }
    OperandValue ops[7];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD39 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD39>(*this);
    }
    OperandValue ops[9];
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA7>(*this);
    }
    OperandValue ops[7];
    HIONLY_lea hilo;
    XONLY X;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA6>(*this);
    }
    OperandValue ops[6];
    HIONLY_lea hilo;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA8>(*this);
    }
    OperandValue ops[8];
    HIONLY_lea hilo;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP6>(*this);
    }
    OperandValue ops[6];
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP5>(*this);
    }
    OperandValue ops[5];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP38 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP38>(*this);
    }
    OperandValue ops[8];
    LUTOnly lut;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP37>(*this);
    }
    OperandValue ops[7];
    LUTOnly lut;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP36>(*this);
    }
    OperandValue ops[6];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPRMT5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPRMT5>(*this);
    }
    OperandValue ops[5];
    IDXOnly idx;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD3_647 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD3_647>(*this);
    }
    OperandValue ops[7];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD3_649 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD3_649>(*this);
    }
    OperandValue ops[9];
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHF5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHF5>(*this);
    }
    OperandValue ops[5];
    SDIR dir;
    CWMode cw;
    FMT_shf fmt;
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHL4>(*this);
    }
    OperandValue ops[4];
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHR4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHR4>(*this);
    }
    OperandValue ops[4];
    CWMode cw;
    FMT_S32_U32 fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSGXT4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSGXT4>(*this);
    }
    OperandValue ops[4];
    CWMode cw;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBMSK4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBMSK4>(*this);
    }
    OperandValue ops[4];
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD5>(*this);
    }
    OperandValue ops[5];
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD6>(*this);
    }
    OperandValue ops[6];
    LOOnly wide;
    FMT fmt;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD7>(*this);
    }
    OperandValue ops[7];
    WIDEONLY wide;
    FMT fmt;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP3>(*this);
    }
    OperandValue ops[3];
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    SRCFMT_E5M2_E4M3 srcfmt;
    UNPACK_BONLY merge;
    RNONLY rndMode;
    EXTRACT extract;
    SATFINITE satfinite;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP4>(*this);
    }
    OperandValue ops[4];
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    Float32 srcfmt;
    PACK_ABONLY merge;
    RNDMODE_RN_RZ rndMode;
    EXTRACT extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP5>(*this);
    }
    OperandValue ops[5];
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    Float32 srcfmt;
    PACK_AB_MERGE_CONLY merge;
    RNONLY rndMode;
    EXTRACT extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFLO4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFLO4>(*this);
    }
    OperandValue ops[4];
    FMT fmt;
    SH sh;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBREV3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBREV3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPOPC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPOPC3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU7>(*this);
    }
    OperandValue ops[7];
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU6>(*this);
    }
    OperandValue ops[6];
    ONLY256_ldcu sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDTRAM4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDTRAM4>(*this);
    }
    OperandValue ops[4];
    MODE_ldtram mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS6>(*this);
    }
    OperandValue ops[6];
    CASONLY emuop;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG4>(*this);
    }
    OperandValue ops[4];
    TENSORDIM dim;
    MODE_TILED_IM2COL_W_GATHER4 mode;
    MULTICAST multicast;
    ONLY1CTA cluster_sz;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG6>(*this);
    }
    OperandValue ops[6];
    TENSORDIM dim;
    MODE_TILED_IM2COL_W_GATHER4 mode;
    MULTICAST multicast;
    ONLY1CTA cluster_sz;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMASTG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMASTG3>(*this);
    }
    OperandValue ops[3];
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMASTG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMASTG5>(*this);
    }
    OperandValue ops[5];
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAREDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAREDG3>(*this);
    }
    OperandValue ops[3];
    TENSORDIM dim;
    MODE_utmaredg mode;
    RedOp op;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAREDG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAREDG5>(*this);
    }
    OperandValue ops[5];
    TENSORDIM dim;
    MODE_utmaredg mode;
    RedOp op;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAPF4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAPF4>(*this);
    }
    OperandValue ops[4];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_IM2COL_W mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAPF6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAPF6>(*this);
    }
    OperandValue ops[6];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_IM2COL_W mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKCP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKCP4>(*this);
    }
    OperandValue ops[4];
    DST dst;
    DST src;
    MULTICAST multicast;
    BYTE_MASK byte_mask;
    SP2 sp2;
    SEQ seq;
    SEM_ublkcp sem;
    SCO sco;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKCP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKCP6>(*this);
    }
    OperandValue ops[6];
    DST dst;
    DST src;
    MULTICAST multicast;
    BYTE_MASK byte_mask;
    SP2 sp2;
    SEQ seq;
    SEM_ublkcp sem;
    SCO sco;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKRED4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKRED4>(*this);
    }
    OperandValue ops[4];
    DST dst;
    SONLY_ublkred src;
    RedOp op;
    SIZE sz;
    SEM_ublkcp sem;
    SCO sco;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKRED6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKRED6>(*this);
    }
    OperandValue ops[6];
    DST dst;
    SONLY_ublkred src;
    RedOp op;
    SIZE sz;
    SEM_ublkcp sem;
    SCO sco;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKPF3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKPF3>(*this);
    }
    OperandValue ops[3];
    L2ONLY cache;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKPF5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKPF5>(*this);
    }
    OperandValue ops[5];
    L2ONLY cache;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARSET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARSET2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_SET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_SET2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETMAXREG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETMAXREG3>(*this);
    }
    OperandValue ops[3];
    TRY_ALLOCONLY mode;
    CTAPOOLONLY pool;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETMAXREG2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETMAXREG2>(*this);
    }
    OperandValue ops[2];
    DEALLOCONLY mode;
    CTAPOOLONLY pool;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETSHMSZ2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETSHMSZ2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUGETNEXTWORKID3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUGETNEXTWORKID3>(*this);
    }
    OperandValue ops[3];
    UGETNEXTWORKID_CAST cast;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUMEMSETS5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUMEMSETS5>(*this);
    }
    OperandValue ops[5];
    ONLY64 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEPC2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV4>(*this);
    }
    OperandValue ops[4];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA6>(*this);
    }
    OperandValue ops[6];
    MODE ipaop;
    OFFSETONLY msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRA3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRA3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    UONLY cond;
    USEL usel;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMP3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    UONLY cond;
    USEL usel;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS5>(*this);
    }
    OperandValue ops[5];
    PHASECHKONLY op;
    TRANS64ONLY bartype;
    WAIT wait;
    EXCHONLY emuop;
    ONLY64_syncs sz;
    RETVAL_OLDSTATE_TMASK_RED retval;
    OPTOUT optout;
    PARAMTYPE paramtype;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU8>(*this);
    }
    OperandValue ops[8];
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS4>(*this);
    }
    OperandValue ops[4];
    LDONLY cctl_mode;
    ONLY64_syncs sz;
    WATCH watch;
    TCNTONLY op;
    TRANS64ONLY bartype;
    BarRED retval;
    LDONLY_syncs emuop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG3>(*this);
    }
    OperandValue ops[3];
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONLY1CTA cluster_sz;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG5>(*this);
    }
    OperandValue ops[5];
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONLY1CTA cluster_sz;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAPF3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAPF3>(*this);
    }
    OperandValue ops[3];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAPF5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAPF5>(*this);
    }
    OperandValue ops[5];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARGET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARGET2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_GET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_GET2>(*this);
    }
    OperandValue ops[2];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedELECT2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedELECT2>(*this);
    }
    OperandValue ops[2];
    IGNORE_KILL ignoreKill;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDSM4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDSM4>(*this);
    }
    OperandValue ops[4];
    LDSM_SZ sz;
    LDSM_MODE mode;
    LDSM_NUM num;
    PSEUDO_OP pseudo_op;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTSM4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTSM4>(*this);
    }
    OperandValue ops[4];
    STSM_SZ sz;
    STSM_MODE mode;
    LDSM_NUM num;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUP2UR5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUP2UR5>(*this);
    }
    OperandValue ops[5];
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUP2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUP2UR3>(*this);
    }
    OperandValue ops[3];
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUR2UP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUR2UP4>(*this);
    }
    OperandValue ops[4];
    B3B0 ur2up_selA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP32I6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP32I6>(*this);
    }
    OperandValue ops[6];
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP32I5>(*this);
    }
    OperandValue ops[5];
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCLEA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCLEA6>(*this);
    }
    OperandValue ops[6];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRXU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRXU3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    COND cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMXU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMXU3>(*this);
    }
    OperandValue ops[3];
    DEPTH depth;
    COND cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG8>(*this);
    }
    OperandValue ops[8];
    EONLY e;
    COP cop;
    COP2_EFL2_ENL2_ELL2 cop2;
    SP2 sp2;
    ONLY256 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_bit75_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG7>(*this);
    }
    OperandValue ops[7];
    EONLY e;
    COP cop;
    RML2ONLY_ldg cop2;
    SP2 sp2;
    ONLY256 sz;
    STRONGONLY sem;
    GPUONLY sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_bit75_dist;
    ONLY64 input_reg_sz_64_bit75_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG7>(*this);
    }
    OperandValue ops[7];
    EONLY e;
    COP cop;
    COP2 cop2;
    ONLY256 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ORDER order;
    ONLY64 input_reg_sz_64_bit75_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG6>(*this);
    }
    OperandValue ops[6];
    EONLY e;
    COP cop;
    COP2 cop2;
    ONLY256 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ORDER order;
    U32ONLY input_reg_sz_32_bit75_dist;
    ONLY64 input_reg_sz_64_bit75_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLD6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLD6>(*this);
    }
    OperandValue ops[6];
    EONLY e;
    COP cop;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLD5>(*this);
    }
    OperandValue ops[5];
    E e;
    COP cop;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG6>(*this);
    }
    OperandValue ops[6];
    E e;
    COP cop;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDL5>(*this);
    }
    OperandValue ops[5];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDL4>(*this);
    }
    OperandValue ops[4];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDS4>(*this);
    }
    OperandValue ops[4];
    LDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedST5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedST5>(*this);
    }
    OperandValue ops[5];
    EONLY e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedST4>(*this);
    }
    OperandValue ops[4];
    E e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG5>(*this);
    }
    OperandValue ops[5];
    EONLY e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ORDER order;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG4>(*this);
    }
    OperandValue ops[4];
    E e;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ORDER order;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTL5>(*this);
    }
    OperandValue ops[5];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTL4>(*this);
    }
    OperandValue ops[4];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTS4>(*this);
    }
    OperandValue ops[4];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM8>(*this);
    }
    OperandValue ops[8];
    EONLY e;
    AtomsOp op;
    COP cop;
    ATOMICINTSIZES sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDS4>(*this);
    }
    OperandValue ops[4];
    REDSOP op;
    REDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDG4>(*this);
    }
    OperandValue ops[4];
    E e;
    RedOp op;
    COP cop;
    REDSSIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDG5>(*this);
    }
    OperandValue ops[5];
    EONLY e;
    RedOp op;
    COP cop;
    REDSSIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMG7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG7>(*this);
    }
    OperandValue ops[7];
    EONLY e;
    ATOMICFPOPS op;
    COP cop;
    SZ_0 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGMC4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGMC4>(*this);
    }
    OperandValue ops[4];
    EONLY e;
    INTOP_ADD_MIN_MAX_AND_OR_XOR intOp;
    REDSSIZE intSz;
    STRONGONLY sem;
    SYSONLY sco;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    LDGMC_FP_OP fpOp;
    LDGMC_FP_SIZES fpSz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGMC5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGMC5>(*this);
    }
    OperandValue ops[5];
    EONLY e;
    INTOP_ADD_MIN_MAX_AND_OR_XOR intOp;
    REDSSIZE intSz;
    STRONGONLY sem;
    SYSONLY sco;
    ONLY64 input_reg_sz_64_dist;
    LDGMC_FP_OP fpOp;
    LDGMC_FP_SIZES fpSz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC5>(*this);
    }
    OperandValue ops[5];
    E e;
    QUERY_SPACE space;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU5>(*this);
    }
    OperandValue ops[5];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU4>(*this);
    }
    OperandValue ops[4];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedARRIVES3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedARRIVES3>(*this);
    }
    OperandValue ops[3];
    LDGSTSBARONLY arrive;
    CInteger_64 sz;
    BAROP barop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS3>(*this);
    }
    OperandValue ops[3];
    CCTLONLY cctl_mode;
    SYNCS_CCTL_OP cctlop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACCTL2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACCTL2>(*this);
    }
    OperandValue ops[2];
    COP_utmacctl cop;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARARV1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARARV1>(*this);
    }
    OperandValue ops[1];
    SYNCALL syncall;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_ARV1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_ARV1>(*this);
    }
    OperandValue ops[1];
    SYNCALL syncall;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETSHMSZ1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETSHMSZ1>(*this);
    }
    OperandValue ops[1];
    FLUSHONLY_usetshmsz flush;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEPC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEPC3>(*this);
    }
    OperandValue ops[3];
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTEX8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTEX8>(*this);
    }
    OperandValue ops[8];
    BONLY b;
    RM16 rm16;
    LODLC_tex lodlc;
    AOFFI aoffi;
    UAI uai;
    DC dc;
    COP cop;
    DIV div;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTLD48 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTLD48>(*this);
    }
    OperandValue ops[8];
    TexComp comp;
    BONLY b;
    RM16 rm16;
    TOFF toff;
    UAI uai;
    DC dc;
    COP cop;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTLD8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTLD8>(*this);
    }
    OperandValue ops[8];
    BONLY b;
    RM16 rm16;
    LODLC_tld lodlc;
    AOFFI aoffi;
    UAI uai;
    COP cop;
    MS ms;
    CL cl;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTXD8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTXD8>(*this);
    }
    OperandValue ops[8];
    BONLY b;
    RM16 rm16;
    LC lc;
    AOFFI aoffi;
    UAI uai;
    COP cop;
    NODEP nodep;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFOOTPRINT6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFOOTPRINT6>(*this);
    }
    OperandValue ops[6];
    BONLY b;
    MODE_FOOTPRINT mode;
    LODCTRL lodctrl;
    LODLC lodlc;
    DIV div;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGSTS6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS6>(*this);
    }
    OperandValue ops[6];
    EONLY_ldgsts e;
    LOC loc;
    COP cop;
    SP2 sp2;
    SIZE2 sz;
    FILLCTRL fc;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    U32ONLY input_reg_sz_32_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGSTS8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS8>(*this);
    }
    OperandValue ops[8];
    EONLY_ldgsts e;
    LOC loc;
    COP cop;
    SP2 sp2;
    SIZE2 sz;
    FILLCTRL fc;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUQUERY7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUQUERY7>(*this);
    }
    OperandValue ops[7];
    BA ba;
    Dim1 dim;
    UAI uai;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTAS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTAS4>(*this);
    }
    OperandValue ops[4];
    SZ_32_64_128 sz;
    ONLY64 input_reg_sz_64_dist;
    U32ONLY input_reg_sz_32_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDAS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDAS4>(*this);
    }
    OperandValue ops[4];
    REDSOP op;
    REDAS_SZ sz;
    ONLY64 input_reg_sz_64_dist;
    U32ONLY input_reg_sz_32_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARWAIT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARWAIT1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_WAIT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_WAIT1>(*this);
    }
    OperandValue ops[1];
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA9>(*this);
    }
    OperandValue ops[9];
    SPONLY sp;
    SPFORMAT spformat;
    SIZE_1688_16816_16832 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTLD49 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTLD49>(*this);
    }
    OperandValue ops[9];
    SCRONLY scr;
    TexComp comp;
    RM16 rm16;
    TOFF toff;
    UAI uai;
    DC dc;
    COP cop;
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTLD9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTLD9>(*this);
    }
    OperandValue ops[9];
    SCRONLY scr;
    RM16 rm16;
    LODLC_tld lodlc;
    AOFFI aoffi;
    UAI uai;
    COP cop;
    MS ms;
    CL cl;
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTMML7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTMML7>(*this);
    }
    OperandValue ops[7];
    LODOnly lod;
    DIV div;
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTXD9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTXD9>(*this);
    }
    OperandValue ops[9];
    RM16 rm16;
    LC lc;
    AOFFI aoffi;
    UAI uai;
    COP cop;
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTXQ6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTXQ6>(*this);
    }
    OperandValue ops[6];
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFOOTPRINT7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFOOTPRINT7>(*this);
    }
    OperandValue ops[7];
    BONLY b;
    MODE_FOOTPRINT mode;
    LODCTRL lodctrl;
    LODLC lodlc;
    DIV div;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUATOM7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUATOM7>(*this);
    }
    OperandValue ops[7];
    DOnly d;
    BA ba;
    Dim1 dim;
    UAI uai;
    AtomsOp op;
    COP cop;
    SURFACESIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    Clamp1 clamp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSULD6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSULD6>(*this);
    }
    OperandValue ops[6];
    PONLY p;
    Dim1 dim;
    UAI uai;
    COP cop;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    RGBA rgba;
    Clamp1 clamp;
    DOnly d;
    BA ba;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUST5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUST5>(*this);
    }
    OperandValue ops[5];
    PONLY p;
    Dim1 dim;
    UAI uai;
    COP cop;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    RGBA rgba;
    Clamp1 clamp;
    DOnly d;
    BA ba;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSURED5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSURED5>(*this);
    }
    OperandValue ops[5];
    DOnly d;
    BA ba;
    Dim1 dim;
    UAI uai;
    RedOp op;
    COP cop;
    SURFACESIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    Clamp1 clamp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGSTS7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS7>(*this);
    }
    OperandValue ops[7];
    EONLY_ldgsts e;
    LOC loc;
    COP cop;
    SP2 sp2;
    SIZE2 sz;
    FILLCTRL fc;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};

// Per-variant operand-role manifest (indexed by isa_data kVariants
// index).  pos = position in the derived type's ops[] array.
struct ShapeOpRole {
    const char* slot;   // FORMAT slot name (e.g. "Rd", "Rb")
    std::uint8_t pos;   // position in ops[]
    OperandKind kind;   // OperandKind
};
static_assert(sizeof(ShapeOpRole) <= 16);
static_assert(sizeof(OperandValue) <= 16);
struct ShapeManifest {
    std::uint16_t n_ops;             // number of operand roles
    const ShapeOpRole* ops;          // role list, or nullptr
};
inline const ShapeOpRole kShapeRoles_0[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "PixMaskU04", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_2[] = { { "Rd", 0, OperandKind::kRegister }, { "Pr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_3[] = { { "PR", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_4[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_5[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_6[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_7[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_8[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_9[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_10[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_11[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_12[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_13[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_14[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_15[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_16[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_17[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_18[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_19[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_20[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_21[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister }, { "Pp", 6, OperandKind::kPredicate }, { "Pq", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_22[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_23[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_24[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_25[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_26[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_27[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_28[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_29[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_30[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_31[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_32[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_33[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_34[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_35[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_36[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_37[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_38[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_39[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_40[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_41[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_42[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_43[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_44[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_45[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_46[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Rb", 2, OperandKind::kRegister }, { "Pr", 3, OperandKind::kPredicate }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_47[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Rb", 3, OperandKind::kRegister }, { "Pr", 4, OperandKind::kPredicate }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_48[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_49[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_50[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_51[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_52[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_53[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_54[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_55[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_56[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_57[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_58[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "GetPseudoOpRRR", 4, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_59[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_60[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_61[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_62[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_63[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_64[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_65[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_66[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_67[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_68[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_69[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_70[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_71[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_72[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_73[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_74[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_75[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_76[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_77[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_78[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_79[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_80[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_81[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_82[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_83[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_84[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_85[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_86[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_87[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_88[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_89[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_90[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_91[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_92[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_93[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_94[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_95[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_96[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_97[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_98[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_99[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_100[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_101[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_102[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_103[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_104[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_105[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_106[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "id", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_107[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_108[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_109[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_110[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_111[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_112[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_113[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_114[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_115[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "id", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_116[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_117[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_118[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_119[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_120[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_121[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_122[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_123[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_124[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_125[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_126[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_127[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_128[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_129[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_130[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_131[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_132[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_133[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_134[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_135[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_136[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_137[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_138[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_139[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_140[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_141[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_142[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "sparseId", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_143[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "sparseId", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_144[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_145[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_146[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_147[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_148[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_149[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_150[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_151[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_152[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_153[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_154[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_155[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_156[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_157[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_158[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_159[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_160[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_161[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_162[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_163[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_164[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_165[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_166[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_167[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_168[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_169[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_170[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_171[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_172[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_173[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_174[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_175[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_176[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_177[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_178[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_179[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_180[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_181[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_182[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_183[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_184[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_185[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_186[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_187[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_188[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_189[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_190[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_191[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_192[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_193[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_194[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_195[] = { { "Rd", 0, OperandKind::kRegister }, { "barname", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_196[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_197[] = { { "Rd", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_198[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_199[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_200[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_201[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_202[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_203[] = { { "Rb", 0, OperandKind::kRegister }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_204[] = { { "barname", 0, OperandKind::kUImm }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_205[] = { { "Ra", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_206[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_207[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_208[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_209[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_210[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_211[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_212[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_213[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_214[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_215[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_216[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_217[] = { { "Ra", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_218[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "attr", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_219[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "attr", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_222[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_223[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_224[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_225[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_226[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_227[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_228[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_229[] = { { "Rd", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_230[] = { { "RpcN", 0, OperandKind::kSpecial }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_231[] = { { "Rd", 0, OperandKind::kRegister }, { "RpcN", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_232[] = { { "Rd", 0, OperandKind::kRegister }, { "cbu_state", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_233[] = { { "cbu_state", 0, OperandKind::kSpecial }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_234[] = { { "atexit_pc", 0, OperandKind::kSpecial }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_235[] = { { "Pp", 0, OperandKind::kPredicate }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_236[] = { { "Pp", 0, OperandKind::kPredicate }, { "Rb", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_237[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_238[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_239[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "paramA", 4, OperandKind::kSpecial }, { "wmsk", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_240[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "query", 3, OperandKind::kSpecial }, { "wmsk", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_241[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Pnz", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_242[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Pnz", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_243[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_244[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_245[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_246[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_247[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_248[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_249[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_250[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_251[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_252[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_253[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_254[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_255[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_256[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_257[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_258[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_259[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_260[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_261[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_262[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_263[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_264[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_265[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_267[] = { { "Rb", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_268[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_269[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_270[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_271[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_272[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_273[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_274[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_275[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_276[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_278[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_279[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_280[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_281[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm }, { "Rb", 4, OperandKind::kRegister }, { "Rc", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_282[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_283[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_284[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_285[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_286[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_287[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_288[] = { { "Rd", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_289[] = { { "Ra", 0, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_290[] = { { "URd", 0, OperandKind::kUniformRegister }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_294[] = { { "ttuAddr", 0, OperandKind::kSpecial }, { "ImmU16", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_295[] = { { "Pu", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_296[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "ttuAddr", 3, OperandKind::kSpecial }, { "ImmU16", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_297[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "ttuAddr", 3, OperandKind::kSpecial }, { "ImmU16", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_300[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_301[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_302[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Sc", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_303[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Sc", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_304[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_305[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_306[] = { { "Rd", 0, OperandKind::kRegister }, { "Sa", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_307[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_308[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_309[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_310[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_311[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kSImm }, { "GetPseudoOpRRI", 4, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_312[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_313[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_314[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_315[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_316[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_317[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_318[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_319[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm16 }, { "Sc", 3, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_320[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_321[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_322[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm16 }, { "Sc1", 3, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_323[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm16 }, { "Sc1", 3, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_324[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_325[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_326[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_327[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_328[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_329[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_330[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_331[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_332[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_333[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm64 }, { "Sc1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_334[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_335[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_336[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_337[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm64 }, { "Sc1", 4, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_338[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_339[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_340[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_341[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_342[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_343[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_344[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_345[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_346[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_347[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "Rh", 6, OperandKind::kRegister }, { "URi", 7, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_348[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "Rh", 6, OperandKind::kRegister }, { "URi", 7, OperandKind::kUniformRegister }, { "sparseId", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_349[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "Rh", 6, OperandKind::kRegister }, { "URi", 7, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_350[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "Rh", 6, OperandKind::kRegister }, { "URi", 7, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_351[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "UPp", 4, OperandKind::kUniformPredicate }, { "Re", 5, OperandKind::kRegister }, { "Rh", 6, OperandKind::kRegister }, { "URi", 7, OperandKind::kUniformRegister }, { "sparseId", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_352[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_353[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_354[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_355[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_356[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_357[] = { { "Rb", 0, OperandKind::kRegister }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_358[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_359[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Sc", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_360[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_361[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_363[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_364[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_365[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_366[] = { { "Pp", 0, OperandKind::kPredicate }, { "imm", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_367[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm }, { "PixMaskU04", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_368[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm }, { "PixMaskU04", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_369[] = { { "Rd", 0, OperandKind::kRegister }, { "Pr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_370[] = { { "Rd", 0, OperandKind::kRegister }, { "Pr", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_371[] = { { "PR", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_372[] = { { "Rd", 0, OperandKind::kRegister }, { "SRa", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_373[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_374[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_375[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_376[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_377[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_378[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_379[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_380[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_381[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_382[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_383[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_384[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_385[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_386[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_387[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_388[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_389[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_390[] = { { "Sa", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_391[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Sa", 2, OperandKind::kUImm }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_392[] = { { "Pu", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_393[] = { { "Sa", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_394[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Sa", 2, OperandKind::kUImm }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_395[] = { { "Pu", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_396[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Rc", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_397[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Rc", 5, OperandKind::kRegister }, { "Pp", 6, OperandKind::kPredicate }, { "Pq", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_398[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_399[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_400[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_401[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_402[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_403[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_404[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_405[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_406[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_407[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_408[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_409[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_410[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_411[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_412[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_413[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_414[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_415[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_416[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_417[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_418[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_419[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kSImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_420[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_421[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_422[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_423[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_424[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_425[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Pq", 2, OperandKind::kPredicate }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_426[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Pq", 2, OperandKind::kPredicate }, { "UPr", 3, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_427[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Pq", 2, OperandKind::kPredicate }, { "Pr", 3, OperandKind::kPredicate }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_428[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Pq", 2, OperandKind::kPredicate }, { "UPr", 3, OperandKind::kUniformPredicate }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_429[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Pq", 3, OperandKind::kPredicate }, { "Pr", 4, OperandKind::kPredicate }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_430[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Pq", 3, OperandKind::kPredicate }, { "UPr", 4, OperandKind::kUniformPredicate }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_431[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Pq", 3, OperandKind::kPredicate }, { "Pr", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_432[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "Pq", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_433[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "Pq", 3, OperandKind::kPredicate }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_434[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_435[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_436[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "npCtrl", 3, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_437[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_438[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_439[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_440[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister }, { "GetPseudoOpRIR", 4, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_441[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_442[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_443[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_444[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_445[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_446[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_447[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_448[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_449[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_450[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_451[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_452[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_453[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_454[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_455[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_456[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_459[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_460[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_461[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_462[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_463[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_464[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_465[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_466[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm16 }, { "Sb1", 3, OperandKind::kFImm16 }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_467[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm16 }, { "Sb1", 3, OperandKind::kFImm16 }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_468[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_469[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_470[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm16 }, { "Sb1", 3, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_471[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm16 }, { "Sb1", 3, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_472[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_473[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_474[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_475[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_476[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_477[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kSImm }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_478[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_479[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_480[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_481[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_482[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_483[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_484[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_485[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_486[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_487[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_488[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_489[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_490[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_491[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_492[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_493[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_494[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_495[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_496[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_497[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_498[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_499[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_500[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_501[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_502[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_503[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_504[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm64 }, { "Sb1", 3, OperandKind::kFImm64 }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_505[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kFImm64 }, { "Sb1", 5, OperandKind::kFImm64 }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_506[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "Sb", 4, OperandKind::kFImm64 }, { "Sb1", 5, OperandKind::kFImm64 }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_507[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_508[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_509[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_510[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_511[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_512[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_513[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_515[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_516[] = { { "URd", 0, OperandKind::kUniformRegister }, { "UPu", 1, OperandKind::kUniformPredicate }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_517[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPp", 2, OperandKind::kUniformPredicate }, { "UPq", 3, OperandKind::kUniformPredicate }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_518[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPp", 2, OperandKind::kUniformPredicate }, { "UPq", 3, OperandKind::kUniformPredicate }, { "UPr", 4, OperandKind::kUniformPredicate }, { "uimm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_519[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "UPp", 3, OperandKind::kUniformPredicate }, { "UPq", 4, OperandKind::kUniformPredicate }, { "UPr", 5, OperandKind::kUniformPredicate }, { "uimm8", 6, OperandKind::kUImm }, { "vimm8", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_520[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "UPp", 3, OperandKind::kUniformPredicate }, { "UPq", 4, OperandKind::kUniformPredicate }, { "UPr", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_521[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPp", 2, OperandKind::kUniformPredicate }, { "UPq", 3, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_522[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "SRa", 2, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_523[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_524[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_525[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_526[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_527[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_528[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_529[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_530[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_531[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_532[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_533[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_534[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_535[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_536[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_537[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_538[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_539[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_540[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_541[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_542[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_543[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_544[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_545[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_546[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_547[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_548[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_549[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_550[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_551[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_552[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_553[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_554[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_555[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_556[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_557[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_558[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_559[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_560[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_561[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_562[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_563[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_564[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_565[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_566[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_567[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_568[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_570[] = { { "Rd", 0, OperandKind::kRegister }, { "SRa", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_571[] = { { "sbidx", 0, OperandKind::kSpecial }, { "cnt", 1, OperandKind::kUImm }, { "scoreboard_list", 2, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_572[] = { { "scoreboard_list", 0, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_574[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_575[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_576[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_577[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_578[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_579[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_580[] = { { "Sb", 0, OperandKind::kUImm }, { "Rc", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_581[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_582[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_583[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_584[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_585[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_586[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "attr", 3, OperandKind::kUImm }, { "Sb", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_587[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_588[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_589[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_590[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_591[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_592[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_593[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_594[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_595[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial }, { "Sa", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_596[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial }, { "Sa", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_597[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial }, { "Sa", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_598[] = { { "Pp", 0, OperandKind::kPredicate }, { "barReg", 1, OperandKind::kSpecial }, { "Sa", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_599[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_600[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_601[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_602[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_603[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_604[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_605[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_606[] = { { "Pp", 0, OperandKind::kPredicate }, { "sImm", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_607[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_608[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_609[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_610[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_611[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_612[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sa", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_613[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_614[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_615[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_616[] = { { "Rd", 0, OperandKind::kRegister }, { "sImm58", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_617[] = { { "Rd", 0, OperandKind::kRegister }, { "sImm58", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_619[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_620[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_621[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_622[] = { { "Pp", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_623[] = { { "Sb", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_624[] = { { "RpcN", 0, OperandKind::kSpecial }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_625[] = { { "Rpc", 0, OperandKind::kSpecial }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_626[] = { { "cbu_state", 0, OperandKind::kSpecial }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_627[] = { { "atexit_pc", 0, OperandKind::kSpecial }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_628[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_629[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_630[] = { { "Sb", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_631[] = { { "Sb", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_632[] = { { "Pp", 0, OperandKind::kPredicate }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_633[] = { { "Pp", 0, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_634[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Pnz", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_635[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm }, { "Pnz", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_636[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_637[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_638[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_639[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_640[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_641[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_642[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_644[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_645[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_646[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_647[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "sector_count", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_648[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_649[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_650[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_offset", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_651[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "sector_count", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_655[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_656[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_660[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_661[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_662[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_663[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_664[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kSImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_665[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_offset", 1, OperandKind::kUImm }, { "Rb", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_669[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "queryType", 3, OperandKind::kSpecial }, { "Rc", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_670[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_671[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_672[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_673[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "SRa", 2, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_674[] = { { "Sb", 0, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_675[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_676[] = { { "Rd", 0, OperandKind::kRegister }, { "Sb", 1, OperandKind::kFImm32 }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_677[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_678[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_679[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_680[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm }, { "Pp", 2, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_683[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_684[] = { { "Sb", 0, OperandKind::kUImm }, { "Sc", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_685[] = { { "Sa", 0, OperandKind::kSpecial }, { "Sa_bank", 1, OperandKind::kUImm }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_686[] = { { "Rd", 0, OperandKind::kRegister }, { "Sa", 1, OperandKind::kSpecial }, { "Sa_bank", 2, OperandKind::kUImm }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_687[] = { { "Rd", 0, OperandKind::kRegister }, { "Sa", 1, OperandKind::kSpecial }, { "Sa_bank", 2, OperandKind::kUImm }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_688[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_689[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Sc", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_690[] = { { "barReg", 0, OperandKind::kSpecial }, { "Ba", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_691[] = { { "barReg", 0, OperandKind::kSpecial }, { "cbu_state", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_692[] = { { "cbu_state", 0, OperandKind::kSpecial }, { "barReg", 1, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_693[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Sb", 3, OperandKind::kUImm }, { "Sc", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_694[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_695[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_696[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_697[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_698[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_699[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_700[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_701[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_702[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_703[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_704[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_705[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_706[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_707[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_708[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_709[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_710[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_711[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_712[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_713[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_714[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_715[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_716[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_717[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_718[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_719[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_720[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_721[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_722[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_723[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_724[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_725[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_726[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_727[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_728[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_729[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_730[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_731[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_732[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_733[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_734[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_735[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate }, { "UPq", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_736[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_737[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate }, { "UPq", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_738[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_739[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_740[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_741[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate }, { "UPr", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_742[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_743[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_744[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_745[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate }, { "UPr", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_746[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_747[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_748[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "URc", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_749[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "URc", 6, OperandKind::kUniformRegister }, { "UPp", 7, OperandKind::kUniformPredicate }, { "UPq", 8, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_750[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "scaleU5", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_751[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_752[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "scaleU5", 5, OperandKind::kUImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_753[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "scaleU5", 6, OperandKind::kUImm }, { "UPp", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_754[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_755[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "scaleU5", 5, OperandKind::kUImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_756[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_757[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_758[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "imm8", 6, OperandKind::kUImm }, { "UPp", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_759[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "imm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_760[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_761[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_762[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_763[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "URc", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_764[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "URc", 6, OperandKind::kUniformRegister }, { "UPp", 7, OperandKind::kUniformPredicate }, { "UPq", 8, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_765[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_766[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_767[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_768[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_769[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_770[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPp", 2, OperandKind::kUniformPredicate }, { "URb", 3, OperandKind::kUniformRegister }, { "UPr", 4, OperandKind::kUniformPredicate }, { "uimm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_771[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "UPp", 3, OperandKind::kUniformPredicate }, { "URb", 4, OperandKind::kUniformRegister }, { "UPr", 5, OperandKind::kUniformPredicate }, { "uimm8", 6, OperandKind::kUImm }, { "vimm8", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_772[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPp", 2, OperandKind::kUniformPredicate }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "uimm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_773[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "UPp", 3, OperandKind::kUniformPredicate }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "uimm8", 6, OperandKind::kUImm }, { "vimm8", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_774[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "uimm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_775[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "uimm8", 6, OperandKind::kUImm }, { "vimm8", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_776[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_777[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_778[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_779[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_780[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_781[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_782[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_783[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_784[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_785[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_786[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_787[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_788[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_789[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_790[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_791[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_792[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_793[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_794[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd2", 1, OperandKind::kUniformRegister }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sa_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_795[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd2", 1, OperandKind::kUniformRegister }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sa_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_796[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_797[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kSImm }, { "URb", 4, OperandKind::kUniformRegister }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_798[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_799[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_800[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_801[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_802[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_803[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_804[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_805[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_806[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_807[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_808[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_809[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_810[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_811[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_812[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_813[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_814[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_815[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_816[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_817[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_818[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_819[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_820[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "desc", 4, OperandKind::kDesc }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_821[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_822[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_823[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_824[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_825[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_826[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_827[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_828[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_829[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_830[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_831[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_832[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_833[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "URa_offset", 2, OperandKind::kSImm }, { "URb", 3, OperandKind::kUniformRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_834[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_835[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_836[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_837[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_838[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_839[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_840[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_841[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_842[] = { { "indexURd", 0, OperandKind::kSpecial }, { "URd", 1, OperandKind::kUniformRegister }, { "Rb", 2, OperandKind::kRegister }, { "PixMaskU04", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_843[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_844[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_845[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Sc", 5, OperandKind::kUImm }, { "scaleU5", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_846[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Sc", 5, OperandKind::kUImm }, { "scaleU5", 6, OperandKind::kUImm }, { "UPp", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_847[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_848[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sa", 2, OperandKind::kUImm }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_849[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_850[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kSImm }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_851[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_852[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Sc", 4, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_853[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_854[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Sc", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_855[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_856[] = { { "Rd", 0, OperandKind::kRegister }, { "srcAttr", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_857[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "URa", 1, OperandKind::kUniformRegister }, { "URa_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_858[] = { { "srcAttr", 0, OperandKind::kSpecial }, { "URa", 1, OperandKind::kUniformRegister }, { "URa_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_859[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "URa_offset", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_860[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "URa_offset", 4, OperandKind::kUImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_861[] = { { "URa", 0, OperandKind::kUniformRegister }, { "Sa_offset", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_862[] = { { "URa", 0, OperandKind::kUniformRegister }, { "Sa_offset", 1, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_863[] = { { "Pp", 0, OperandKind::kPredicate }, { "UPq", 1, OperandKind::kUniformPredicate }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_864[] = { { "Pp", 0, OperandKind::kPredicate }, { "UPq", 1, OperandKind::kUniformPredicate }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_865[] = { { "Pp", 0, OperandKind::kPredicate }, { "UPq", 1, OperandKind::kUniformPredicate }, { "Sa", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_866[] = { { "Pp", 0, OperandKind::kPredicate }, { "UPq", 1, OperandKind::kUniformPredicate }, { "Sa", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_867[] = { { "Rd", 0, OperandKind::kRegister }, { "Sa", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "Rb", 3, OperandKind::kRegister }, { "Sa_offset", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_868[] = { { "Rd", 0, OperandKind::kRegister }, { "Sa", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "Rb", 3, OperandKind::kRegister }, { "Sa_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_869[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_870[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd2", 1, OperandKind::kUniformRegister }, { "URd", 2, OperandKind::kUniformRegister }, { "Sa", 3, OperandKind::kSpecial }, { "URa", 4, OperandKind::kUniformRegister }, { "URb", 5, OperandKind::kUniformRegister }, { "Sa_offset", 6, OperandKind::kSImm }, { "word_mask", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_871[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_872[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kSImm }, { "URb", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_873[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_874[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_875[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_876[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_877[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_878[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_879[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_880[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "desc", 3, OperandKind::kDesc }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_881[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_882[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_883[] = { { "Sa", 0, OperandKind::kSpecial }, { "URa", 1, OperandKind::kUniformRegister }, { "Rb", 2, OperandKind::kRegister }, { "Sa_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_884[] = { { "Sa", 0, OperandKind::kSpecial }, { "URa", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Sa_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_885[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sa", 2, OperandKind::kSpecial }, { "Sa_bank", 3, OperandKind::kUImm }, { "URa", 4, OperandKind::kUniformRegister }, { "Sa_offset", 5, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_886[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_887[] = { { "Pu", 0, OperandKind::kPredicate }, { "URd", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_888[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_889[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_890[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_891[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_892[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_893[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_894[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_895[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_896[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_897[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_898[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_899[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kFImm32 }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_900[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_901[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_902[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_903[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kFImm32 }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_904[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_905[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_906[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_907[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_908[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_909[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_910[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_911[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_912[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_913[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_914[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_915[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_916[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_917[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_918[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_919[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_920[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_921[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_922[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm64 } };
inline const ShapeOpRole kShapeRoles_923[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm16 } };
inline const ShapeOpRole kShapeRoles_924[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_925[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_926[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_927[] = { { "indexURd", 0, OperandKind::kSpecial }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm }, { "PixMaskU04", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_928[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPR", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_929[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPR", 2, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_930[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPR", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_931[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "UPp", 6, OperandKind::kUniformPredicate }, { "UPq", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_932[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_933[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "UPp", 6, OperandKind::kUniformPredicate }, { "UPq", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_934[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URd", 3, OperandKind::kUniformRegister }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_935[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_936[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_937[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "UPp", 5, OperandKind::kUniformPredicate }, { "UPr", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_938[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_939[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_940[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_941[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "UPv", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "UPp", 5, OperandKind::kUniformPredicate }, { "UPr", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_942[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_943[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "UPr", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_944[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "URc", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_945[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "URc", 6, OperandKind::kUniformRegister }, { "UPp", 7, OperandKind::kUniformPredicate }, { "UPq", 8, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_946[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister }, { "scaleU5", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_947[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_948[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_949[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister }, { "scaleU5", 6, OperandKind::kUImm }, { "UPp", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_950[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_951[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "scaleU5", 5, OperandKind::kUImm }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_952[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_953[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_954[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_955[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_956[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister }, { "imm8", 6, OperandKind::kUImm }, { "UPp", 7, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_957[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "URc", 5, OperandKind::kUniformRegister }, { "imm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_958[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_959[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "URd", 2, OperandKind::kUniformRegister }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_960[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_961[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "URc", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_962[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "UPv", 3, OperandKind::kUniformPredicate }, { "URa", 4, OperandKind::kUniformRegister }, { "Sb", 5, OperandKind::kSImm }, { "URc", 6, OperandKind::kUniformRegister }, { "UPp", 7, OperandKind::kUniformPredicate }, { "UPq", 8, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_963[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_964[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_965[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_966[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_967[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_968[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_969[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kSImm }, { "URc", 4, OperandKind::kUniformRegister }, { "UPp", 5, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_970[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_971[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_972[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "URc", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_973[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kSImm }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_974[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_975[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_976[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_977[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_978[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sb", 3, OperandKind::kFImm32 }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_979[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_980[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_981[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_982[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kFImm32 } };
inline const ShapeOpRole kShapeRoles_983[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "Sb", 4, OperandKind::kUImm }, { "constSizeU05", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_984[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "Sb", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_985[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_986[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_987[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "srcAttr", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "URa_offset", 4, OperandKind::kUImm }, { "Sb", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_988[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_989[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_990[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_991[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_992[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_993[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "sImm", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_994[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "Sa", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_995[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister }, { "Sa", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_996[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_997[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_998[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "Sa_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_999[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1000[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "UR_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1001[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "UR_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1002[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "UR_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1003[] = { { "Pp", 0, OperandKind::kPredicate }, { "URa", 1, OperandKind::kUniformRegister }, { "UR_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1004[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "word_mask", 6, OperandKind::kUImm }, { "Pnz", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1005[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "word_mask", 6, OperandKind::kUImm }, { "Pnz", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1006[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1007[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1008[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1009[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1010[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1011[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "word_mask", 5, OperandKind::kUImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1012[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister }, { "Rb2", 5, OperandKind::kRegister }, { "word_mask", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1013[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rb2", 4, OperandKind::kRegister }, { "word_mask", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1014[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rb2", 4, OperandKind::kRegister }, { "word_mask", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1015[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister }, { "Rb2", 4, OperandKind::kRegister }, { "word_mask", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1016[] = { { "Rd", 0, OperandKind::kRegister }, { "memoryDescriptor", 1, OperandKind::kDesc }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1017[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Pnz", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1018[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Pnz", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1019[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Pnz", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1020[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1021[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1022[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1023[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1024[] = { { "Rd", 0, OperandKind::kRegister }, { "memoryDescriptor", 1, OperandKind::kDesc }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1025[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1026[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1027[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1028[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1029[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1030[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1031[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1032[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1033[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1034[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1035[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1036[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1037[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1038[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1039[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1040[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1041[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Rb", 6, OperandKind::kRegister }, { "wr_early", 7, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1042[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1043[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1044[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1045[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1046[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1047[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1048[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1049[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1050[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister }, { "wr_early", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1051[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Rb", 6, OperandKind::kRegister }, { "wr_early", 7, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1052[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1053[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1054[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1055[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Rb", 6, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1056[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1057[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1058[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1059[] = { { "Rd", 0, OperandKind::kRegister }, { "memoryDescriptor", 1, OperandKind::kDesc }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1060[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1061[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1062[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1063[] = { { "Rd", 0, OperandKind::kRegister }, { "memoryDescriptor", 1, OperandKind::kDesc }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1064[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1065[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1066[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1067[] = { { "memoryDescriptor", 0, OperandKind::kDesc }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1068[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm }, { "Rb", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1069[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1070[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1071[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1072[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Rb", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1073[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Rb", 6, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1074[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1075[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1076[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1077[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1078[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1079[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1080[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1081[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1082[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URb", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1083[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sa_offset", 3, OperandKind::kSImm }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1084[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "Sa_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1085[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1086[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1087[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URa_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1088[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1089[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URa", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1090[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1091[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1092[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPu", 1, OperandKind::kUniformPredicate }, { "Sb", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1093[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1094[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1095[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "Sb", 1, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1096[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "sImm58", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1097[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "sImm58", 2, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1098[] = { { "Sa", 0, OperandKind::kSpecial }, { "Sa_bank", 1, OperandKind::kUImm }, { "URa", 2, OperandKind::kUniformRegister }, { "Sa_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1099[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "Sa", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Sa_offset", 5, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1100[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1101[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "PixMaskU04", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1102[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1103[] = { { "Rd", 0, OperandKind::kRegister }, { "Pr", 1, OperandKind::kSpecial }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1104[] = { { "PR", 0, OperandKind::kSpecial }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1105[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1106[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1107[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1108[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1109[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1110[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1111[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1112[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1113[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1114[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1115[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1116[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1117[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate }, { "Pr", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1118[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1119[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pr", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1120[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1121[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Rc", 5, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1122[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Rc", 5, OperandKind::kRegister }, { "Pp", 6, OperandKind::kPredicate }, { "Pq", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1123[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1124[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1125[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1126[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1127[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "scaleU5", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1128[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "scaleU5", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1129[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "scaleU5", 4, OperandKind::kUImm }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1130[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1131[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1132[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm }, { "Pp", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1133[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "imm8", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1134[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1135[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1136[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1137[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1138[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1139[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1140[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate }, { "Pq", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1141[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1142[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1143[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1144[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1145[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1146[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1147[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "URb", 2, OperandKind::kUniformRegister }, { "Pr", 3, OperandKind::kPredicate }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1148[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "URb", 3, OperandKind::kUniformRegister }, { "Pr", 4, OperandKind::kPredicate }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1149[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pp", 1, OperandKind::kPredicate }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1150[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Pp", 2, OperandKind::kPredicate }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1151[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "uimm8", 4, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1152[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "uimm8", 5, OperandKind::kUImm }, { "vimm8", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1153[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1154[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1155[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1156[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1157[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1158[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1159[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1160[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1161[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1162[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1163[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1164[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1165[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1166[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1167[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1168[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1169[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1170[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1171[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1172[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Rc", 4, OperandKind::kRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1173[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1174[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1175[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1176[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1177[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1178[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1179[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1180[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1181[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1182[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1183[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1184[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1185[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1186[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1187[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1188[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1189[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1190[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1191[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1192[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1193[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1194[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1195[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1196[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1197[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1198[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1199[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1200[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1201[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1202[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1203[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1204[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1205[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1206[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1207[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1208[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister }, { "Rc", 2, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1209[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1210[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1211[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1212[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1213[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1214[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Pv", 2, OperandKind::kPredicate }, { "Ra", 3, OperandKind::kRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1215[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Rc", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1216[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1217[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1218[] = { { "Rd", 0, OperandKind::kRegister }, { "indexURb", 1, OperandKind::kSpecial }, { "URb", 2, OperandKind::kUniformRegister }, { "PixMaskU04", 3, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1219[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1220[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1221[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPR", 2, OperandKind::kSpecial }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1222[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "UPR", 1, OperandKind::kSpecial }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1223[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "URa", 2, OperandKind::kUniformRegister }, { "URb", 3, OperandKind::kUniformRegister }, { "UPp", 4, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1224[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd", 1, OperandKind::kUniformRegister }, { "UPu", 2, OperandKind::kUniformPredicate }, { "URa", 3, OperandKind::kUniformRegister }, { "URb", 4, OperandKind::kUniformRegister }, { "constSizeU05", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1225[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1226[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1227[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1228[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1229[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1230[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1231[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1232[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1233[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1234[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1235[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1236[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1237[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1238[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1239[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1240[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1241[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1242[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1243[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1244[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1245[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1246[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1247[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1248[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1249[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1250[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1251[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1252[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1253[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1254[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1255[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1256[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1257[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1258[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1259[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1260[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1261[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1262[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1263[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1264[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1265[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1266[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1267[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1268[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1269[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1270[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1271[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1272[] = { { "sbidx", 0, OperandKind::kSpecial }, { "URb", 1, OperandKind::kUniformRegister }, { "scoreboard_list", 2, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1273[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1274[] = { { "RpcN", 0, OperandKind::kSpecial }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1275[] = { { "Rpc", 0, OperandKind::kSpecial }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1276[] = { { "cbu_state", 0, OperandKind::kSpecial }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1277[] = { { "atexit_pc", 0, OperandKind::kSpecial }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1278[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1279[] = { { "Pp", 0, OperandKind::kPredicate }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1280[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1281[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1282[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1283[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1284[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1285[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1286[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URe", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial }, { "wmsk", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1287[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "paramA", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1288[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "paramA", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1289[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1290[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1291[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1292[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister }, { "sector_count", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1293[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1294[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1295[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URb", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1296[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister }, { "sector_count", 2, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1297[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1298[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1299[] = { { "URb", 0, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1300[] = { { "UPg", 0, OperandKind::kUniformPredicate }, { "URd2", 1, OperandKind::kUniformRegister }, { "URd", 2, OperandKind::kUniformRegister }, { "Sa", 3, OperandKind::kSpecial }, { "Sa_bank", 4, OperandKind::kUImm }, { "URa", 5, OperandKind::kUniformRegister }, { "Sa_offset", 6, OperandKind::kSImm }, { "word_mask", 7, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1301[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_URc", 1, OperandKind::kUniformRegister }, { "Rb_offset", 2, OperandKind::kSImm }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1302[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_URc", 1, OperandKind::kUniformRegister }, { "Rb_offset", 2, OperandKind::kSImm }, { "memoryDescriptor", 3, OperandKind::kDesc }, { "Ra_URd", 4, OperandKind::kUniformRegister }, { "Ra", 5, OperandKind::kRegister }, { "Ra_offset", 6, OperandKind::kSImm }, { "Pnz", 7, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1303[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_URc", 1, OperandKind::kUniformRegister }, { "Rb_offset", 2, OperandKind::kSImm }, { "Ra", 3, OperandKind::kRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1304[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "queryType", 3, OperandKind::kSpecial }, { "Rc", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1305[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1306[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1307[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1308[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1309[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1310[] = { { "Ra", 0, OperandKind::kRegister }, { "Ra_URc", 1, OperandKind::kUniformRegister }, { "Ra_offset", 2, OperandKind::kSImm }, { "Rb", 3, OperandKind::kRegister } };
inline const ShapeOpRole kShapeRoles_1311[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1312[] = { { "UPg", 0, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1313[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URb", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1314[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1315[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1316[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1317[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1318[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1319[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1320[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1321[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1322[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1323[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1324[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1325[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1326[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1327[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1328[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1329[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1330[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1331[] = { { "Rd", 0, OperandKind::kRegister }, { "Pu", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "Pp", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1332[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1333[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1334[] = { { "Pu", 0, OperandKind::kPredicate }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1335[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1336[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1337[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1338[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1339[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1340[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1341[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1342[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1343[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1344[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1345[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1346[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1347[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1348[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "Pp", 3, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1349[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1350[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1351[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1352[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "Pp", 4, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1353[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1354[] = { { "Pu", 0, OperandKind::kPredicate }, { "Pv", 1, OperandKind::kPredicate }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1355[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1356[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1357[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1358[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1359[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1360[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1361[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1362[] = { { "Rd", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1363[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Rb", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1364[] = { { "indexURd", 0, OperandKind::kSpecial }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "indexURc", 4, OperandKind::kSpecial }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate }, { "Re", 7, OperandKind::kRegister }, { "id", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1365[] = { { "indexURd", 0, OperandKind::kSpecial }, { "URd", 1, OperandKind::kUniformRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "indexURc", 4, OperandKind::kSpecial }, { "URc", 5, OperandKind::kUniformRegister }, { "UPp", 6, OperandKind::kUniformPredicate } };
inline const ShapeOpRole kShapeRoles_1366[] = { { "Rd", 0, OperandKind::kRegister }, { "URb", 1, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1367[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1368[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1369[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1370[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1371[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1372[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1373[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1374[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1375[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1376[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1377[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "paramA", 5, OperandKind::kSpecial }, { "wmsk", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1378[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "paramA", 5, OperandKind::kSpecial }, { "wmsk", 6, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1379[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1380[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister }, { "paramA", 7, OperandKind::kSpecial }, { "wmsk", 8, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1381[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "query", 3, OperandKind::kSpecial }, { "URc", 4, OperandKind::kUniformRegister }, { "wmsk", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1382[] = { { "Rd2", 0, OperandKind::kRegister }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "query", 3, OperandKind::kSpecial }, { "URc", 4, OperandKind::kUniformRegister }, { "wmsk", 5, OperandKind::kUImm } };
inline const ShapeOpRole kShapeRoles_1383[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1384[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1385[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1386[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd2", 1, OperandKind::kRegister }, { "Rd", 2, OperandKind::kRegister }, { "Ra", 3, OperandKind::kRegister }, { "Rb", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "paramA", 6, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1387[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1388[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1389[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1390[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1391[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1392[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "wr_early", 5, OperandKind::kSpecial } };
inline const ShapeOpRole kShapeRoles_1393[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1394[] = { { "Rd", 0, OperandKind::kRegister }, { "Ra", 1, OperandKind::kRegister }, { "Ra_URc", 2, OperandKind::kUniformRegister }, { "Ra_offset", 3, OperandKind::kSImm } };
inline const ShapeOpRole kShapeRoles_1395[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1396[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1397[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1398[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rb", 3, OperandKind::kRegister }, { "Rc", 4, OperandKind::kRegister }, { "URc", 5, OperandKind::kUniformRegister }, { "URe", 6, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1399[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1400[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1401[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1402[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "Rc", 3, OperandKind::kRegister }, { "URc", 4, OperandKind::kUniformRegister }, { "URe", 5, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1403[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1404[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1405[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1406[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1407[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "URc", 2, OperandKind::kUniformRegister }, { "URe", 3, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1408[] = { { "Ra", 0, OperandKind::kRegister }, { "Rb", 1, OperandKind::kRegister }, { "Rc", 2, OperandKind::kRegister }, { "URc", 3, OperandKind::kUniformRegister }, { "URe", 4, OperandKind::kUniformRegister } };
inline const ShapeOpRole kShapeRoles_1409[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_offset", 1, OperandKind::kSImm }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1410[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_offset", 1, OperandKind::kSImm }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1411[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_offset", 1, OperandKind::kSImm }, { "memoryDescriptor", 2, OperandKind::kDesc }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra", 4, OperandKind::kRegister }, { "Ra_offset", 5, OperandKind::kSImm }, { "Pnz", 6, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1412[] = { { "Rb", 0, OperandKind::kRegister }, { "Rb_offset", 1, OperandKind::kSImm }, { "Ra", 2, OperandKind::kRegister }, { "Ra_URc", 3, OperandKind::kUniformRegister }, { "Ra_offset", 4, OperandKind::kSImm }, { "Pnz", 5, OperandKind::kPredicate } };
inline const ShapeOpRole kShapeRoles_1413[] = { { "Pu", 0, OperandKind::kPredicate }, { "Rd", 1, OperandKind::kRegister }, { "Ra", 2, OperandKind::kRegister }, { "queryType", 3, OperandKind::kSpecial }, { "URc", 4, OperandKind::kUniformRegister }, { "URe", 5, OperandKind::kUniformRegister } };

inline const ShapeManifest kShapeManifests[] = {
    {2, kShapeRoles_0},
    {3, kShapeRoles_1},
    {4, kShapeRoles_2},
    {3, kShapeRoles_3},
    {4, kShapeRoles_4},
    {4, kShapeRoles_5},
    {4, kShapeRoles_6},
    {5, kShapeRoles_7},
    {4, kShapeRoles_8},
    {3, kShapeRoles_9},
    {5, kShapeRoles_10},
    {3, kShapeRoles_11},
    {6, kShapeRoles_12},
    {5, kShapeRoles_13},
    {4, kShapeRoles_14},
    {3, kShapeRoles_15},
    {6, kShapeRoles_16},
    {5, kShapeRoles_17},
    {4, kShapeRoles_18},
    {3, kShapeRoles_19},
    {6, kShapeRoles_20},
    {8, kShapeRoles_21},
    {5, kShapeRoles_22},
    {6, kShapeRoles_23},
    {5, kShapeRoles_24},
    {6, kShapeRoles_25},
    {7, kShapeRoles_26},
    {5, kShapeRoles_27},
    {6, kShapeRoles_28},
    {5, kShapeRoles_29},
    {4, kShapeRoles_30},
    {7, kShapeRoles_31},
    {6, kShapeRoles_32},
    {6, kShapeRoles_33},
    {5, kShapeRoles_34},
    {2, kShapeRoles_35},
    {4, kShapeRoles_36},
    {7, kShapeRoles_37},
    {6, kShapeRoles_38},
    {7, kShapeRoles_39},
    {6, kShapeRoles_40},
    {4, kShapeRoles_41},
    {3, kShapeRoles_42},
    {3, kShapeRoles_43},
    {3, kShapeRoles_44},
    {3, kShapeRoles_45},
    {5, kShapeRoles_46},
    {7, kShapeRoles_47},
    {5, kShapeRoles_48},
    {7, kShapeRoles_49},
    {5, kShapeRoles_50},
    {7, kShapeRoles_51},
    {3, kShapeRoles_52},
    {3, kShapeRoles_53},
    {3, kShapeRoles_54},
    {4, kShapeRoles_55},
    {4, kShapeRoles_56},
    {4, kShapeRoles_57},
    {5, kShapeRoles_58},
    {5, kShapeRoles_59},
    {5, kShapeRoles_60},
    {3, kShapeRoles_61},
    {5, kShapeRoles_62},
    {5, kShapeRoles_63},
    {6, kShapeRoles_64},
    {6, kShapeRoles_65},
    {4, kShapeRoles_66},
    {4, kShapeRoles_67},
    {4, kShapeRoles_68},
    {4, kShapeRoles_69},
    {5, kShapeRoles_70},
    {5, kShapeRoles_71},
    {6, kShapeRoles_72},
    {6, kShapeRoles_73},
    {3, kShapeRoles_74},
    {3, kShapeRoles_75},
    {5, kShapeRoles_76},
    {3, kShapeRoles_77},
    {4, kShapeRoles_78},
    {4, kShapeRoles_79},
    {3, kShapeRoles_80},
    {3, kShapeRoles_81},
    {3, kShapeRoles_82},
    {3, kShapeRoles_83},
    {4, kShapeRoles_84},
    {4, kShapeRoles_85},
    {4, kShapeRoles_86},
    {5, kShapeRoles_87},
    {5, kShapeRoles_88},
    {5, kShapeRoles_89},
    {3, kShapeRoles_90},
    {3, kShapeRoles_91},
    {4, kShapeRoles_92},
    {4, kShapeRoles_93},
    {3, kShapeRoles_94},
    {3, kShapeRoles_95},
    {5, kShapeRoles_96},
    {5, kShapeRoles_97},
    {4, kShapeRoles_98},
    {4, kShapeRoles_99},
    {4, kShapeRoles_100},
    {5, kShapeRoles_101},
    {4, kShapeRoles_102},
    {5, kShapeRoles_103},
    {3, kShapeRoles_104},
    {5, kShapeRoles_105},
    {7, kShapeRoles_106},
    {2, kShapeRoles_107},
    {4, kShapeRoles_108},
    {4, kShapeRoles_109},
    {4, kShapeRoles_110},
    {4, kShapeRoles_111},
    {4, kShapeRoles_112},
    {4, kShapeRoles_113},
    {2, kShapeRoles_114},
    {7, kShapeRoles_115},
    {5, kShapeRoles_116},
    {2, kShapeRoles_117},
    {2, kShapeRoles_118},
    {2, kShapeRoles_119},
    {3, kShapeRoles_120},
    {3, kShapeRoles_121},
    {3, kShapeRoles_122},
    {3, kShapeRoles_123},
    {3, kShapeRoles_124},
    {4, kShapeRoles_125},
    {4, kShapeRoles_126},
    {4, kShapeRoles_127},
    {3, kShapeRoles_128},
    {3, kShapeRoles_129},
    {2, kShapeRoles_130},
    {2, kShapeRoles_131},
    {5, kShapeRoles_132},
    {4, kShapeRoles_133},
    {4, kShapeRoles_134},
    {6, kShapeRoles_135},
    {6, kShapeRoles_136},
    {4, kShapeRoles_137},
    {2, kShapeRoles_138},
    {4, kShapeRoles_139},
    {5, kShapeRoles_140},
    {5, kShapeRoles_141},
    {7, kShapeRoles_142},
    {7, kShapeRoles_143},
    {3, kShapeRoles_144},
    {3, kShapeRoles_145},
    {3, kShapeRoles_146},
    {3, kShapeRoles_147},
    {3, kShapeRoles_148},
    {2, kShapeRoles_149},
    {3, kShapeRoles_150},
    {2, kShapeRoles_151},
    {2, kShapeRoles_152},
    {2, kShapeRoles_153},
    {2, kShapeRoles_154},
    {2, kShapeRoles_155},
    {2, kShapeRoles_156},
    {2, kShapeRoles_157},
    {2, kShapeRoles_158},
    {2, kShapeRoles_159},
    {2, kShapeRoles_160},
    {2, kShapeRoles_161},
    {2, kShapeRoles_162},
    {2, kShapeRoles_163},
    {2, kShapeRoles_164},
    {2, kShapeRoles_165},
    {2, kShapeRoles_166},
    {2, kShapeRoles_167},
    {2, kShapeRoles_168},
    {2, kShapeRoles_169},
    {2, kShapeRoles_170},
    {2, kShapeRoles_171},
    {2, kShapeRoles_172},
    {2, kShapeRoles_173},
    {2, kShapeRoles_174},
    {2, kShapeRoles_175},
    {2, kShapeRoles_176},
    {2, kShapeRoles_177},
    {2, kShapeRoles_178},
    {2, kShapeRoles_179},
    {2, kShapeRoles_180},
    {2, kShapeRoles_181},
    {2, kShapeRoles_182},
    {2, kShapeRoles_183},
    {2, kShapeRoles_184},
    {2, kShapeRoles_185},
    {2, kShapeRoles_186},
    {2, kShapeRoles_187},
    {2, kShapeRoles_188},
    {2, kShapeRoles_189},
    {2, kShapeRoles_190},
    {2, kShapeRoles_191},
    {2, kShapeRoles_192},
    {2, kShapeRoles_193},
    {2, kShapeRoles_194},
    {2, kShapeRoles_195},
    {2, kShapeRoles_196},
    {1, kShapeRoles_197},
    {2, kShapeRoles_198},
    {3, kShapeRoles_199},
    {3, kShapeRoles_200},
    {3, kShapeRoles_201},
    {2, kShapeRoles_202},
    {2, kShapeRoles_203},
    {2, kShapeRoles_204},
    {1, kShapeRoles_205},
    {4, kShapeRoles_206},
    {5, kShapeRoles_207},
    {5, kShapeRoles_208},
    {5, kShapeRoles_209},
    {4, kShapeRoles_210},
    {5, kShapeRoles_211},
    {5, kShapeRoles_212},
    {5, kShapeRoles_213},
    {3, kShapeRoles_214},
    {3, kShapeRoles_215},
    {3, kShapeRoles_216},
    {1, kShapeRoles_217},
    {4, kShapeRoles_218},
    {5, kShapeRoles_219},
    {0, nullptr},
    {0, nullptr},
    {3, kShapeRoles_222},
    {3, kShapeRoles_223},
    {3, kShapeRoles_224},
    {2, kShapeRoles_225},
    {2, kShapeRoles_226},
    {3, kShapeRoles_227},
    {3, kShapeRoles_228},
    {1, kShapeRoles_229},
    {2, kShapeRoles_230},
    {2, kShapeRoles_231},
    {2, kShapeRoles_232},
    {2, kShapeRoles_233},
    {2, kShapeRoles_234},
    {2, kShapeRoles_235},
    {2, kShapeRoles_236},
    {9, kShapeRoles_237},
    {9, kShapeRoles_238},
    {6, kShapeRoles_239},
    {5, kShapeRoles_240},
    {5, kShapeRoles_241},
    {5, kShapeRoles_242},
    {3, kShapeRoles_243},
    {3, kShapeRoles_244},
    {3, kShapeRoles_245},
    {3, kShapeRoles_246},
    {3, kShapeRoles_247},
    {3, kShapeRoles_248},
    {3, kShapeRoles_249},
    {3, kShapeRoles_250},
    {5, kShapeRoles_251},
    {6, kShapeRoles_252},
    {6, kShapeRoles_253},
    {7, kShapeRoles_254},
    {7, kShapeRoles_255},
    {7, kShapeRoles_256},
    {7, kShapeRoles_257},
    {4, kShapeRoles_258},
    {4, kShapeRoles_259},
    {3, kShapeRoles_260},
    {3, kShapeRoles_261},
    {5, kShapeRoles_262},
    {5, kShapeRoles_263},
    {5, kShapeRoles_264},
    {5, kShapeRoles_265},
    {0, nullptr},
    {1, kShapeRoles_267},
    {6, kShapeRoles_268},
    {6, kShapeRoles_269},
    {4, kShapeRoles_270},
    {3, kShapeRoles_271},
    {2, kShapeRoles_272},
    {6, kShapeRoles_273},
    {6, kShapeRoles_274},
    {5, kShapeRoles_275},
    {5, kShapeRoles_276},
    {0, nullptr},
    {5, kShapeRoles_278},
    {5, kShapeRoles_279},
    {6, kShapeRoles_280},
    {6, kShapeRoles_281},
    {3, kShapeRoles_282},
    {3, kShapeRoles_283},
    {3, kShapeRoles_284},
    {3, kShapeRoles_285},
    {4, kShapeRoles_286},
    {4, kShapeRoles_287},
    {1, kShapeRoles_288},
    {1, kShapeRoles_289},
    {2, kShapeRoles_290},
    {0, nullptr},
    {0, nullptr},
    {0, nullptr},
    {4, kShapeRoles_294},
    {1, kShapeRoles_295},
    {5, kShapeRoles_296},
    {5, kShapeRoles_297},
    {0, nullptr},
    {0, nullptr},
    {2, kShapeRoles_300},
    {4, kShapeRoles_301},
    {6, kShapeRoles_302},
    {7, kShapeRoles_303},
    {4, kShapeRoles_304},
    {4, kShapeRoles_305},
    {3, kShapeRoles_306},
    {3, kShapeRoles_307},
    {3, kShapeRoles_308},
    {4, kShapeRoles_309},
    {4, kShapeRoles_310},
    {5, kShapeRoles_311},
    {5, kShapeRoles_312},
    {5, kShapeRoles_313},
    {3, kShapeRoles_314},
    {5, kShapeRoles_315},
    {3, kShapeRoles_316},
    {4, kShapeRoles_317},
    {3, kShapeRoles_318},
    {4, kShapeRoles_319},
    {4, kShapeRoles_320},
    {4, kShapeRoles_321},
    {4, kShapeRoles_322},
    {4, kShapeRoles_323},
    {5, kShapeRoles_324},
    {5, kShapeRoles_325},
    {5, kShapeRoles_326},
    {6, kShapeRoles_327},
    {6, kShapeRoles_328},
    {6, kShapeRoles_329},
    {5, kShapeRoles_330},
    {5, kShapeRoles_331},
    {4, kShapeRoles_332},
    {4, kShapeRoles_333},
    {6, kShapeRoles_334},
    {6, kShapeRoles_335},
    {5, kShapeRoles_336},
    {5, kShapeRoles_337},
    {3, kShapeRoles_338},
    {3, kShapeRoles_339},
    {3, kShapeRoles_340},
    {4, kShapeRoles_341},
    {4, kShapeRoles_342},
    {4, kShapeRoles_343},
    {3, kShapeRoles_344},
    {3, kShapeRoles_345},
    {4, kShapeRoles_346},
    {8, kShapeRoles_347},
    {9, kShapeRoles_348},
    {8, kShapeRoles_349},
    {8, kShapeRoles_350},
    {9, kShapeRoles_351},
    {2, kShapeRoles_352},
    {3, kShapeRoles_353},
    {3, kShapeRoles_354},
    {3, kShapeRoles_355},
    {2, kShapeRoles_356},
    {2, kShapeRoles_357},
    {2, kShapeRoles_358},
    {5, kShapeRoles_359},
    {5, kShapeRoles_360},
    {5, kShapeRoles_361},
    {0, nullptr},
    {4, kShapeRoles_363},
    {3, kShapeRoles_364},
    {3, kShapeRoles_365},
    {2, kShapeRoles_366},
    {3, kShapeRoles_367},
    {3, kShapeRoles_368},
    {4, kShapeRoles_369},
    {2, kShapeRoles_370},
    {3, kShapeRoles_371},
    {2, kShapeRoles_372},
    {3, kShapeRoles_373},
    {4, kShapeRoles_374},
    {4, kShapeRoles_375},
    {4, kShapeRoles_376},
    {5, kShapeRoles_377},
    {4, kShapeRoles_378},
    {3, kShapeRoles_379},
    {5, kShapeRoles_380},
    {3, kShapeRoles_381},
    {6, kShapeRoles_382},
    {5, kShapeRoles_383},
    {4, kShapeRoles_384},
    {3, kShapeRoles_385},
    {6, kShapeRoles_386},
    {5, kShapeRoles_387},
    {4, kShapeRoles_388},
    {3, kShapeRoles_389},
    {1, kShapeRoles_390},
    {4, kShapeRoles_391},
    {2, kShapeRoles_392},
    {1, kShapeRoles_393},
    {4, kShapeRoles_394},
    {2, kShapeRoles_395},
    {6, kShapeRoles_396},
    {8, kShapeRoles_397},
    {5, kShapeRoles_398},
    {5, kShapeRoles_399},
    {6, kShapeRoles_400},
    {5, kShapeRoles_401},
    {6, kShapeRoles_402},
    {7, kShapeRoles_403},
    {5, kShapeRoles_404},
    {6, kShapeRoles_405},
    {5, kShapeRoles_406},
    {4, kShapeRoles_407},
    {6, kShapeRoles_408},
    {5, kShapeRoles_409},
    {7, kShapeRoles_410},
    {6, kShapeRoles_411},
    {5, kShapeRoles_412},
    {4, kShapeRoles_413},
    {2, kShapeRoles_414},
    {4, kShapeRoles_415},
    {7, kShapeRoles_416},
    {6, kShapeRoles_417},
    {7, kShapeRoles_418},
    {6, kShapeRoles_419},
    {4, kShapeRoles_420},
    {3, kShapeRoles_421},
    {3, kShapeRoles_422},
    {3, kShapeRoles_423},
    {3, kShapeRoles_424},
    {4, kShapeRoles_425},
    {4, kShapeRoles_426},
    {5, kShapeRoles_427},
    {5, kShapeRoles_428},
    {7, kShapeRoles_429},
    {7, kShapeRoles_430},
    {5, kShapeRoles_431},
    {3, kShapeRoles_432},
    {5, kShapeRoles_433},
    {3, kShapeRoles_434},
    {3, kShapeRoles_435},
    {4, kShapeRoles_436},
    {4, kShapeRoles_437},
    {4, kShapeRoles_438},
    {4, kShapeRoles_439},
    {5, kShapeRoles_440},
    {5, kShapeRoles_441},
    {5, kShapeRoles_442},
    {3, kShapeRoles_443},
    {3, kShapeRoles_444},
    {5, kShapeRoles_445},
    {5, kShapeRoles_446},
    {6, kShapeRoles_447},
    {6, kShapeRoles_448},
    {4, kShapeRoles_449},
    {4, kShapeRoles_450},
    {5, kShapeRoles_451},
    {5, kShapeRoles_452},
    {6, kShapeRoles_453},
    {6, kShapeRoles_454},
    {3, kShapeRoles_455},
    {4, kShapeRoles_456},
    {0, nullptr},
    {0, nullptr},
    {3, kShapeRoles_459},
    {5, kShapeRoles_460},
    {5, kShapeRoles_461},
    {5, kShapeRoles_462},
    {6, kShapeRoles_463},
    {6, kShapeRoles_464},
    {6, kShapeRoles_465},
    {5, kShapeRoles_466},
    {5, kShapeRoles_467},
    {4, kShapeRoles_468},
    {4, kShapeRoles_469},
    {4, kShapeRoles_470},
    {4, kShapeRoles_471},
    {4, kShapeRoles_472},
    {5, kShapeRoles_473},
    {4, kShapeRoles_474},
    {5, kShapeRoles_475},
    {4, kShapeRoles_476},
    {5, kShapeRoles_477},
    {3, kShapeRoles_478},
    {2, kShapeRoles_479},
    {4, kShapeRoles_480},
    {4, kShapeRoles_481},
    {4, kShapeRoles_482},
    {4, kShapeRoles_483},
    {4, kShapeRoles_484},
    {4, kShapeRoles_485},
    {3, kShapeRoles_486},
    {3, kShapeRoles_487},
    {2, kShapeRoles_488},
    {2, kShapeRoles_489},
    {2, kShapeRoles_490},
    {3, kShapeRoles_491},
    {3, kShapeRoles_492},
    {3, kShapeRoles_493},
    {3, kShapeRoles_494},
    {3, kShapeRoles_495},
    {4, kShapeRoles_496},
    {4, kShapeRoles_497},
    {4, kShapeRoles_498},
    {3, kShapeRoles_499},
    {3, kShapeRoles_500},
    {2, kShapeRoles_501},
    {2, kShapeRoles_502},
    {5, kShapeRoles_503},
    {5, kShapeRoles_504},
    {7, kShapeRoles_505},
    {7, kShapeRoles_506},
    {4, kShapeRoles_507},
    {3, kShapeRoles_508},
    {2, kShapeRoles_509},
    {2, kShapeRoles_510},
    {4, kShapeRoles_511},
    {2, kShapeRoles_512},
    {2, kShapeRoles_513},
    {0, nullptr},
    {3, kShapeRoles_515},
    {3, kShapeRoles_516},
    {5, kShapeRoles_517},
    {6, kShapeRoles_518},
    {8, kShapeRoles_519},
    {6, kShapeRoles_520},
    {4, kShapeRoles_521},
    {3, kShapeRoles_522},
    {3, kShapeRoles_523},
    {2, kShapeRoles_524},
    {3, kShapeRoles_525},
    {2, kShapeRoles_526},
    {2, kShapeRoles_527},
    {2, kShapeRoles_528},
    {2, kShapeRoles_529},
    {2, kShapeRoles_530},
    {2, kShapeRoles_531},
    {2, kShapeRoles_532},
    {2, kShapeRoles_533},
    {2, kShapeRoles_534},
    {2, kShapeRoles_535},
    {2, kShapeRoles_536},
    {2, kShapeRoles_537},
    {2, kShapeRoles_538},
    {2, kShapeRoles_539},
    {2, kShapeRoles_540},
    {2, kShapeRoles_541},
    {2, kShapeRoles_542},
    {2, kShapeRoles_543},
    {2, kShapeRoles_544},
    {2, kShapeRoles_545},
    {2, kShapeRoles_546},
    {2, kShapeRoles_547},
    {2, kShapeRoles_548},
    {2, kShapeRoles_549},
    {2, kShapeRoles_550},
    {2, kShapeRoles_551},
    {2, kShapeRoles_552},
    {2, kShapeRoles_553},
    {2, kShapeRoles_554},
    {2, kShapeRoles_555},
    {2, kShapeRoles_556},
    {2, kShapeRoles_557},
    {2, kShapeRoles_558},
    {2, kShapeRoles_559},
    {2, kShapeRoles_560},
    {2, kShapeRoles_561},
    {2, kShapeRoles_562},
    {2, kShapeRoles_563},
    {2, kShapeRoles_564},
    {2, kShapeRoles_565},
    {2, kShapeRoles_566},
    {2, kShapeRoles_567},
    {2, kShapeRoles_568},
    {0, nullptr},
    {2, kShapeRoles_570},
    {3, kShapeRoles_571},
    {1, kShapeRoles_572},
    {0, nullptr},
    {1, kShapeRoles_574},
    {2, kShapeRoles_575},
    {3, kShapeRoles_576},
    {3, kShapeRoles_577},
    {3, kShapeRoles_578},
    {2, kShapeRoles_579},
    {2, kShapeRoles_580},
    {3, kShapeRoles_581},
    {3, kShapeRoles_582},
    {3, kShapeRoles_583},
    {3, kShapeRoles_584},
    {2, kShapeRoles_585},
    {5, kShapeRoles_586},
    {3, kShapeRoles_587},
    {2, kShapeRoles_588},
    {2, kShapeRoles_589},
    {2, kShapeRoles_590},
    {2, kShapeRoles_591},
    {2, kShapeRoles_592},
    {2, kShapeRoles_593},
    {2, kShapeRoles_594},
    {3, kShapeRoles_595},
    {3, kShapeRoles_596},
    {3, kShapeRoles_597},
    {3, kShapeRoles_598},
    {1, kShapeRoles_599},
    {2, kShapeRoles_600},
    {2, kShapeRoles_601},
    {2, kShapeRoles_602},
    {2, kShapeRoles_603},
    {1, kShapeRoles_604},
    {2, kShapeRoles_605},
    {2, kShapeRoles_606},
    {3, kShapeRoles_607},
    {3, kShapeRoles_608},
    {2, kShapeRoles_609},
    {2, kShapeRoles_610},
    {2, kShapeRoles_611},
    {2, kShapeRoles_612},
    {3, kShapeRoles_613},
    {3, kShapeRoles_614},
    {1, kShapeRoles_615},
    {2, kShapeRoles_616},
    {2, kShapeRoles_617},
    {0, nullptr},
    {3, kShapeRoles_619},
    {3, kShapeRoles_620},
    {3, kShapeRoles_621},
    {2, kShapeRoles_622},
    {1, kShapeRoles_623},
    {2, kShapeRoles_624},
    {2, kShapeRoles_625},
    {2, kShapeRoles_626},
    {2, kShapeRoles_627},
    {2, kShapeRoles_628},
    {1, kShapeRoles_629},
    {1, kShapeRoles_630},
    {1, kShapeRoles_631},
    {2, kShapeRoles_632},
    {1, kShapeRoles_633},
    {4, kShapeRoles_634},
    {4, kShapeRoles_635},
    {3, kShapeRoles_636},
    {3, kShapeRoles_637},
    {3, kShapeRoles_638},
    {3, kShapeRoles_639},
    {5, kShapeRoles_640},
    {3, kShapeRoles_641},
    {3, kShapeRoles_642},
    {0, nullptr},
    {2, kShapeRoles_644},
    {2, kShapeRoles_645},
    {3, kShapeRoles_646},
    {3, kShapeRoles_647},
    {2, kShapeRoles_648},
    {2, kShapeRoles_649},
    {3, kShapeRoles_650},
    {3, kShapeRoles_651},
    {0, nullptr},
    {0, nullptr},
    {0, nullptr},
    {2, kShapeRoles_655},
    {2, kShapeRoles_656},
    {0, nullptr},
    {0, nullptr},
    {0, nullptr},
    {5, kShapeRoles_660},
    {5, kShapeRoles_661},
    {4, kShapeRoles_662},
    {4, kShapeRoles_663},
    {3, kShapeRoles_664},
    {3, kShapeRoles_665},
    {0, nullptr},
    {0, nullptr},
    {0, nullptr},
    {6, kShapeRoles_669},
    {1, kShapeRoles_670},
    {1, kShapeRoles_671},
    {1, kShapeRoles_672},
    {3, kShapeRoles_673},
    {1, kShapeRoles_674},
    {3, kShapeRoles_675},
    {3, kShapeRoles_676},
    {2, kShapeRoles_677},
    {3, kShapeRoles_678},
    {3, kShapeRoles_679},
    {3, kShapeRoles_680},
    {0, nullptr},
    {0, nullptr},
    {2, kShapeRoles_683},
    {2, kShapeRoles_684},
    {4, kShapeRoles_685},
    {5, kShapeRoles_686},
    {5, kShapeRoles_687},
    {3, kShapeRoles_688},
    {3, kShapeRoles_689},
    {2, kShapeRoles_690},
    {2, kShapeRoles_691},
    {2, kShapeRoles_692},
    {5, kShapeRoles_693},
    {3, kShapeRoles_694},
    {3, kShapeRoles_695},
    {4, kShapeRoles_696},
    {5, kShapeRoles_697},
    {3, kShapeRoles_698},
    {3, kShapeRoles_699},
    {5, kShapeRoles_700},
    {5, kShapeRoles_701},
    {5, kShapeRoles_702},
    {5, kShapeRoles_703},
    {6, kShapeRoles_704},
    {5, kShapeRoles_705},
    {5, kShapeRoles_706},
    {4, kShapeRoles_707},
    {6, kShapeRoles_708},
    {4, kShapeRoles_709},
    {4, kShapeRoles_710},
    {4, kShapeRoles_711},
    {5, kShapeRoles_712},
    {5, kShapeRoles_713},
    {4, kShapeRoles_714},
    {5, kShapeRoles_715},
    {3, kShapeRoles_716},
    {3, kShapeRoles_717},
    {3, kShapeRoles_718},
    {3, kShapeRoles_719},
    {3, kShapeRoles_720},
    {3, kShapeRoles_721},
    {3, kShapeRoles_722},
    {3, kShapeRoles_723},
    {3, kShapeRoles_724},
    {3, kShapeRoles_725},
    {3, kShapeRoles_726},
    {3, kShapeRoles_727},
    {3, kShapeRoles_728},
    {3, kShapeRoles_729},
    {3, kShapeRoles_730},
    {3, kShapeRoles_731},
    {3, kShapeRoles_732},
    {3, kShapeRoles_733},
    {3, kShapeRoles_734},
    {8, kShapeRoles_735},
    {7, kShapeRoles_736},
    {8, kShapeRoles_737},
    {7, kShapeRoles_738},
    {5, kShapeRoles_739},
    {6, kShapeRoles_740},
    {7, kShapeRoles_741},
    {4, kShapeRoles_742},
    {5, kShapeRoles_743},
    {6, kShapeRoles_744},
    {7, kShapeRoles_745},
    {4, kShapeRoles_746},
    {5, kShapeRoles_747},
    {7, kShapeRoles_748},
    {9, kShapeRoles_749},
    {7, kShapeRoles_750},
    {6, kShapeRoles_751},
    {7, kShapeRoles_752},
    {8, kShapeRoles_753},
    {6, kShapeRoles_754},
    {7, kShapeRoles_755},
    {6, kShapeRoles_756},
    {5, kShapeRoles_757},
    {8, kShapeRoles_758},
    {7, kShapeRoles_759},
    {7, kShapeRoles_760},
    {6, kShapeRoles_761},
    {5, kShapeRoles_762},
    {7, kShapeRoles_763},
    {9, kShapeRoles_764},
    {5, kShapeRoles_765},
    {4, kShapeRoles_766},
    {4, kShapeRoles_767},
    {4, kShapeRoles_768},
    {4, kShapeRoles_769},
    {6, kShapeRoles_770},
    {8, kShapeRoles_771},
    {6, kShapeRoles_772},
    {8, kShapeRoles_773},
    {6, kShapeRoles_774},
    {8, kShapeRoles_775},
    {5, kShapeRoles_776},
    {6, kShapeRoles_777},
    {6, kShapeRoles_778},
    {7, kShapeRoles_779},
    {6, kShapeRoles_780},
    {7, kShapeRoles_781},
    {3, kShapeRoles_782},
    {4, kShapeRoles_783},
    {4, kShapeRoles_784},
    {4, kShapeRoles_785},
    {5, kShapeRoles_786},
    {4, kShapeRoles_787},
    {4, kShapeRoles_788},
    {3, kShapeRoles_789},
    {3, kShapeRoles_790},
    {4, kShapeRoles_791},
    {3, kShapeRoles_792},
    {3, kShapeRoles_793},
    {7, kShapeRoles_794},
    {6, kShapeRoles_795},
    {4, kShapeRoles_796},
    {6, kShapeRoles_797},
    {4, kShapeRoles_798},
    {6, kShapeRoles_799},
    {4, kShapeRoles_800},
    {6, kShapeRoles_801},
    {3, kShapeRoles_802},
    {5, kShapeRoles_803},
    {3, kShapeRoles_804},
    {5, kShapeRoles_805},
    {3, kShapeRoles_806},
    {5, kShapeRoles_807},
    {3, kShapeRoles_808},
    {5, kShapeRoles_809},
    {4, kShapeRoles_810},
    {6, kShapeRoles_811},
    {4, kShapeRoles_812},
    {6, kShapeRoles_813},
    {4, kShapeRoles_814},
    {6, kShapeRoles_815},
    {6, kShapeRoles_816},
    {4, kShapeRoles_817},
    {4, kShapeRoles_818},
    {6, kShapeRoles_819},
    {6, kShapeRoles_820},
    {4, kShapeRoles_821},
    {3, kShapeRoles_822},
    {5, kShapeRoles_823},
    {3, kShapeRoles_824},
    {5, kShapeRoles_825},
    {2, kShapeRoles_826},
    {2, kShapeRoles_827},
    {3, kShapeRoles_828},
    {2, kShapeRoles_829},
    {2, kShapeRoles_830},
    {3, kShapeRoles_831},
    {3, kShapeRoles_832},
    {5, kShapeRoles_833},
    {2, kShapeRoles_834},
    {3, kShapeRoles_835},
    {3, kShapeRoles_836},
    {2, kShapeRoles_837},
    {2, kShapeRoles_838},
    {4, kShapeRoles_839},
    {5, kShapeRoles_840},
    {5, kShapeRoles_841},
    {4, kShapeRoles_842},
    {3, kShapeRoles_843},
    {5, kShapeRoles_844},
    {7, kShapeRoles_845},
    {8, kShapeRoles_846},
    {5, kShapeRoles_847},
    {4, kShapeRoles_848},
    {5, kShapeRoles_849},
    {6, kShapeRoles_850},
    {4, kShapeRoles_851},
    {5, kShapeRoles_852},
    {4, kShapeRoles_853},
    {4, kShapeRoles_854},
    {5, kShapeRoles_855},
    {5, kShapeRoles_856},
    {5, kShapeRoles_857},
    {5, kShapeRoles_858},
    {5, kShapeRoles_859},
    {6, kShapeRoles_860},
    {2, kShapeRoles_861},
    {2, kShapeRoles_862},
    {3, kShapeRoles_863},
    {3, kShapeRoles_864},
    {3, kShapeRoles_865},
    {3, kShapeRoles_866},
    {5, kShapeRoles_867},
    {5, kShapeRoles_868},
    {5, kShapeRoles_869},
    {8, kShapeRoles_870},
    {4, kShapeRoles_871},
    {5, kShapeRoles_872},
    {3, kShapeRoles_873},
    {5, kShapeRoles_874},
    {3, kShapeRoles_875},
    {5, kShapeRoles_876},
    {3, kShapeRoles_877},
    {5, kShapeRoles_878},
    {3, kShapeRoles_879},
    {5, kShapeRoles_880},
    {2, kShapeRoles_881},
    {2, kShapeRoles_882},
    {4, kShapeRoles_883},
    {4, kShapeRoles_884},
    {6, kShapeRoles_885},
    {3, kShapeRoles_886},
    {2, kShapeRoles_887},
    {4, kShapeRoles_888},
    {4, kShapeRoles_889},
    {4, kShapeRoles_890},
    {4, kShapeRoles_891},
    {5, kShapeRoles_892},
    {3, kShapeRoles_893},
    {3, kShapeRoles_894},
    {5, kShapeRoles_895},
    {5, kShapeRoles_896},
    {5, kShapeRoles_897},
    {5, kShapeRoles_898},
    {6, kShapeRoles_899},
    {5, kShapeRoles_900},
    {5, kShapeRoles_901},
    {4, kShapeRoles_902},
    {6, kShapeRoles_903},
    {4, kShapeRoles_904},
    {5, kShapeRoles_905},
    {4, kShapeRoles_906},
    {5, kShapeRoles_907},
    {3, kShapeRoles_908},
    {3, kShapeRoles_909},
    {3, kShapeRoles_910},
    {3, kShapeRoles_911},
    {3, kShapeRoles_912},
    {3, kShapeRoles_913},
    {3, kShapeRoles_914},
    {3, kShapeRoles_915},
    {3, kShapeRoles_916},
    {3, kShapeRoles_917},
    {3, kShapeRoles_918},
    {3, kShapeRoles_919},
    {3, kShapeRoles_920},
    {3, kShapeRoles_921},
    {3, kShapeRoles_922},
    {3, kShapeRoles_923},
    {3, kShapeRoles_924},
    {3, kShapeRoles_925},
    {3, kShapeRoles_926},
    {4, kShapeRoles_927},
    {5, kShapeRoles_928},
    {3, kShapeRoles_929},
    {4, kShapeRoles_930},
    {8, kShapeRoles_931},
    {7, kShapeRoles_932},
    {8, kShapeRoles_933},
    {7, kShapeRoles_934},
    {5, kShapeRoles_935},
    {6, kShapeRoles_936},
    {7, kShapeRoles_937},
    {4, kShapeRoles_938},
    {5, kShapeRoles_939},
    {6, kShapeRoles_940},
    {7, kShapeRoles_941},
    {4, kShapeRoles_942},
    {5, kShapeRoles_943},
    {7, kShapeRoles_944},
    {9, kShapeRoles_945},
    {7, kShapeRoles_946},
    {6, kShapeRoles_947},
    {7, kShapeRoles_948},
    {8, kShapeRoles_949},
    {6, kShapeRoles_950},
    {7, kShapeRoles_951},
    {6, kShapeRoles_952},
    {5, kShapeRoles_953},
    {7, kShapeRoles_954},
    {6, kShapeRoles_955},
    {8, kShapeRoles_956},
    {7, kShapeRoles_957},
    {6, kShapeRoles_958},
    {5, kShapeRoles_959},
    {5, kShapeRoles_960},
    {7, kShapeRoles_961},
    {9, kShapeRoles_962},
    {5, kShapeRoles_963},
    {4, kShapeRoles_964},
    {4, kShapeRoles_965},
    {4, kShapeRoles_966},
    {4, kShapeRoles_967},
    {5, kShapeRoles_968},
    {6, kShapeRoles_969},
    {6, kShapeRoles_970},
    {7, kShapeRoles_971},
    {6, kShapeRoles_972},
    {7, kShapeRoles_973},
    {3, kShapeRoles_974},
    {4, kShapeRoles_975},
    {4, kShapeRoles_976},
    {4, kShapeRoles_977},
    {5, kShapeRoles_978},
    {4, kShapeRoles_979},
    {4, kShapeRoles_980},
    {3, kShapeRoles_981},
    {3, kShapeRoles_982},
    {6, kShapeRoles_983},
    {4, kShapeRoles_984},
    {3, kShapeRoles_985},
    {3, kShapeRoles_986},
    {6, kShapeRoles_987},
    {3, kShapeRoles_988},
    {3, kShapeRoles_989},
    {3, kShapeRoles_990},
    {2, kShapeRoles_991},
    {3, kShapeRoles_992},
    {3, kShapeRoles_993},
    {3, kShapeRoles_994},
    {3, kShapeRoles_995},
    {3, kShapeRoles_996},
    {3, kShapeRoles_997},
    {3, kShapeRoles_998},
    {2, kShapeRoles_999},
    {3, kShapeRoles_1000},
    {3, kShapeRoles_1001},
    {3, kShapeRoles_1002},
    {3, kShapeRoles_1003},
    {8, kShapeRoles_1004},
    {8, kShapeRoles_1005},
    {7, kShapeRoles_1006},
    {7, kShapeRoles_1007},
    {7, kShapeRoles_1008},
    {7, kShapeRoles_1009},
    {7, kShapeRoles_1010},
    {7, kShapeRoles_1011},
    {7, kShapeRoles_1012},
    {6, kShapeRoles_1013},
    {6, kShapeRoles_1014},
    {6, kShapeRoles_1015},
    {6, kShapeRoles_1016},
    {5, kShapeRoles_1017},
    {5, kShapeRoles_1018},
    {5, kShapeRoles_1019},
    {7, kShapeRoles_1020},
    {6, kShapeRoles_1021},
    {6, kShapeRoles_1022},
    {6, kShapeRoles_1023},
    {5, kShapeRoles_1024},
    {4, kShapeRoles_1025},
    {4, kShapeRoles_1026},
    {5, kShapeRoles_1027},
    {4, kShapeRoles_1028},
    {4, kShapeRoles_1029},
    {4, kShapeRoles_1030},
    {5, kShapeRoles_1031},
    {4, kShapeRoles_1032},
    {4, kShapeRoles_1033},
    {4, kShapeRoles_1034},
    {5, kShapeRoles_1035},
    {4, kShapeRoles_1036},
    {4, kShapeRoles_1037},
    {7, kShapeRoles_1038},
    {7, kShapeRoles_1039},
    {7, kShapeRoles_1040},
    {8, kShapeRoles_1041},
    {5, kShapeRoles_1042},
    {4, kShapeRoles_1043},
    {4, kShapeRoles_1044},
    {4, kShapeRoles_1045},
    {4, kShapeRoles_1046},
    {5, kShapeRoles_1047},
    {7, kShapeRoles_1048},
    {7, kShapeRoles_1049},
    {7, kShapeRoles_1050},
    {8, kShapeRoles_1051},
    {6, kShapeRoles_1052},
    {6, kShapeRoles_1053},
    {6, kShapeRoles_1054},
    {7, kShapeRoles_1055},
    {4, kShapeRoles_1056},
    {4, kShapeRoles_1057},
    {4, kShapeRoles_1058},
    {5, kShapeRoles_1059},
    {4, kShapeRoles_1060},
    {4, kShapeRoles_1061},
    {4, kShapeRoles_1062},
    {5, kShapeRoles_1063},
    {4, kShapeRoles_1064},
    {4, kShapeRoles_1065},
    {4, kShapeRoles_1066},
    {5, kShapeRoles_1067},
    {5, kShapeRoles_1068},
    {4, kShapeRoles_1069},
    {6, kShapeRoles_1070},
    {6, kShapeRoles_1071},
    {6, kShapeRoles_1072},
    {7, kShapeRoles_1073},
    {4, kShapeRoles_1074},
    {4, kShapeRoles_1075},
    {4, kShapeRoles_1076},
    {4, kShapeRoles_1077},
    {4, kShapeRoles_1078},
    {4, kShapeRoles_1079},
    {5, kShapeRoles_1080},
    {5, kShapeRoles_1081},
    {5, kShapeRoles_1082},
    {5, kShapeRoles_1083},
    {4, kShapeRoles_1084},
    {3, kShapeRoles_1085},
    {3, kShapeRoles_1086},
    {4, kShapeRoles_1087},
    {2, kShapeRoles_1088},
    {2, kShapeRoles_1089},
    {1, kShapeRoles_1090},
    {1, kShapeRoles_1091},
    {3, kShapeRoles_1092},
    {2, kShapeRoles_1093},
    {1, kShapeRoles_1094},
    {2, kShapeRoles_1095},
    {3, kShapeRoles_1096},
    {3, kShapeRoles_1097},
    {4, kShapeRoles_1098},
    {6, kShapeRoles_1099},
    {2, kShapeRoles_1100},
    {3, kShapeRoles_1101},
    {2, kShapeRoles_1102},
    {4, kShapeRoles_1103},
    {3, kShapeRoles_1104},
    {4, kShapeRoles_1105},
    {4, kShapeRoles_1106},
    {4, kShapeRoles_1107},
    {5, kShapeRoles_1108},
    {4, kShapeRoles_1109},
    {3, kShapeRoles_1110},
    {5, kShapeRoles_1111},
    {3, kShapeRoles_1112},
    {6, kShapeRoles_1113},
    {5, kShapeRoles_1114},
    {4, kShapeRoles_1115},
    {3, kShapeRoles_1116},
    {6, kShapeRoles_1117},
    {5, kShapeRoles_1118},
    {4, kShapeRoles_1119},
    {3, kShapeRoles_1120},
    {6, kShapeRoles_1121},
    {8, kShapeRoles_1122},
    {5, kShapeRoles_1123},
    {6, kShapeRoles_1124},
    {5, kShapeRoles_1125},
    {6, kShapeRoles_1126},
    {7, kShapeRoles_1127},
    {5, kShapeRoles_1128},
    {6, kShapeRoles_1129},
    {5, kShapeRoles_1130},
    {4, kShapeRoles_1131},
    {7, kShapeRoles_1132},
    {6, kShapeRoles_1133},
    {6, kShapeRoles_1134},
    {5, kShapeRoles_1135},
    {2, kShapeRoles_1136},
    {4, kShapeRoles_1137},
    {7, kShapeRoles_1138},
    {6, kShapeRoles_1139},
    {7, kShapeRoles_1140},
    {6, kShapeRoles_1141},
    {4, kShapeRoles_1142},
    {3, kShapeRoles_1143},
    {3, kShapeRoles_1144},
    {3, kShapeRoles_1145},
    {3, kShapeRoles_1146},
    {5, kShapeRoles_1147},
    {7, kShapeRoles_1148},
    {5, kShapeRoles_1149},
    {7, kShapeRoles_1150},
    {5, kShapeRoles_1151},
    {7, kShapeRoles_1152},
    {3, kShapeRoles_1153},
    {4, kShapeRoles_1154},
    {4, kShapeRoles_1155},
    {4, kShapeRoles_1156},
    {4, kShapeRoles_1157},
    {5, kShapeRoles_1158},
    {5, kShapeRoles_1159},
    {3, kShapeRoles_1160},
    {5, kShapeRoles_1161},
    {5, kShapeRoles_1162},
    {6, kShapeRoles_1163},
    {6, kShapeRoles_1164},
    {4, kShapeRoles_1165},
    {4, kShapeRoles_1166},
    {4, kShapeRoles_1167},
    {4, kShapeRoles_1168},
    {5, kShapeRoles_1169},
    {5, kShapeRoles_1170},
    {6, kShapeRoles_1171},
    {6, kShapeRoles_1172},
    {3, kShapeRoles_1173},
    {4, kShapeRoles_1174},
    {4, kShapeRoles_1175},
    {4, kShapeRoles_1176},
    {4, kShapeRoles_1177},
    {4, kShapeRoles_1178},
    {5, kShapeRoles_1179},
    {5, kShapeRoles_1180},
    {5, kShapeRoles_1181},
    {3, kShapeRoles_1182},
    {3, kShapeRoles_1183},
    {4, kShapeRoles_1184},
    {5, kShapeRoles_1185},
    {4, kShapeRoles_1186},
    {5, kShapeRoles_1187},
    {3, kShapeRoles_1188},
    {2, kShapeRoles_1189},
    {4, kShapeRoles_1190},
    {4, kShapeRoles_1191},
    {4, kShapeRoles_1192},
    {4, kShapeRoles_1193},
    {4, kShapeRoles_1194},
    {4, kShapeRoles_1195},
    {2, kShapeRoles_1196},
    {2, kShapeRoles_1197},
    {2, kShapeRoles_1198},
    {3, kShapeRoles_1199},
    {3, kShapeRoles_1200},
    {3, kShapeRoles_1201},
    {3, kShapeRoles_1202},
    {3, kShapeRoles_1203},
    {4, kShapeRoles_1204},
    {4, kShapeRoles_1205},
    {4, kShapeRoles_1206},
    {3, kShapeRoles_1207},
    {3, kShapeRoles_1208},
    {2, kShapeRoles_1209},
    {2, kShapeRoles_1210},
    {4, kShapeRoles_1211},
    {4, kShapeRoles_1212},
    {6, kShapeRoles_1213},
    {6, kShapeRoles_1214},
    {4, kShapeRoles_1215},
    {2, kShapeRoles_1216},
    {4, kShapeRoles_1217},
    {4, kShapeRoles_1218},
    {3, kShapeRoles_1219},
    {3, kShapeRoles_1220},
    {5, kShapeRoles_1221},
    {4, kShapeRoles_1222},
    {5, kShapeRoles_1223},
    {6, kShapeRoles_1224},
    {3, kShapeRoles_1225},
    {2, kShapeRoles_1226},
    {3, kShapeRoles_1227},
    {2, kShapeRoles_1228},
    {2, kShapeRoles_1229},
    {2, kShapeRoles_1230},
    {2, kShapeRoles_1231},
    {2, kShapeRoles_1232},
    {2, kShapeRoles_1233},
    {2, kShapeRoles_1234},
    {2, kShapeRoles_1235},
    {2, kShapeRoles_1236},
    {2, kShapeRoles_1237},
    {2, kShapeRoles_1238},
    {2, kShapeRoles_1239},
    {2, kShapeRoles_1240},
    {2, kShapeRoles_1241},
    {2, kShapeRoles_1242},
    {2, kShapeRoles_1243},
    {2, kShapeRoles_1244},
    {2, kShapeRoles_1245},
    {2, kShapeRoles_1246},
    {2, kShapeRoles_1247},
    {2, kShapeRoles_1248},
    {2, kShapeRoles_1249},
    {2, kShapeRoles_1250},
    {2, kShapeRoles_1251},
    {2, kShapeRoles_1252},
    {2, kShapeRoles_1253},
    {2, kShapeRoles_1254},
    {2, kShapeRoles_1255},
    {2, kShapeRoles_1256},
    {2, kShapeRoles_1257},
    {2, kShapeRoles_1258},
    {2, kShapeRoles_1259},
    {2, kShapeRoles_1260},
    {2, kShapeRoles_1261},
    {2, kShapeRoles_1262},
    {2, kShapeRoles_1263},
    {2, kShapeRoles_1264},
    {2, kShapeRoles_1265},
    {2, kShapeRoles_1266},
    {2, kShapeRoles_1267},
    {2, kShapeRoles_1268},
    {2, kShapeRoles_1269},
    {2, kShapeRoles_1270},
    {2, kShapeRoles_1271},
    {3, kShapeRoles_1272},
    {3, kShapeRoles_1273},
    {2, kShapeRoles_1274},
    {2, kShapeRoles_1275},
    {2, kShapeRoles_1276},
    {2, kShapeRoles_1277},
    {2, kShapeRoles_1278},
    {2, kShapeRoles_1279},
    {8, kShapeRoles_1280},
    {8, kShapeRoles_1281},
    {8, kShapeRoles_1282},
    {8, kShapeRoles_1283},
    {8, kShapeRoles_1284},
    {8, kShapeRoles_1285},
    {8, kShapeRoles_1286},
    {6, kShapeRoles_1287},
    {6, kShapeRoles_1288},
    {2, kShapeRoles_1289},
    {2, kShapeRoles_1290},
    {3, kShapeRoles_1291},
    {3, kShapeRoles_1292},
    {2, kShapeRoles_1293},
    {2, kShapeRoles_1294},
    {3, kShapeRoles_1295},
    {3, kShapeRoles_1296},
    {2, kShapeRoles_1297},
    {2, kShapeRoles_1298},
    {1, kShapeRoles_1299},
    {8, kShapeRoles_1300},
    {6, kShapeRoles_1301},
    {8, kShapeRoles_1302},
    {6, kShapeRoles_1303},
    {7, kShapeRoles_1304},
    {4, kShapeRoles_1305},
    {4, kShapeRoles_1306},
    {4, kShapeRoles_1307},
    {4, kShapeRoles_1308},
    {4, kShapeRoles_1309},
    {4, kShapeRoles_1310},
    {1, kShapeRoles_1311},
    {1, kShapeRoles_1312},
    {4, kShapeRoles_1313},
    {4, kShapeRoles_1314},
    {4, kShapeRoles_1315},
    {3, kShapeRoles_1316},
    {3, kShapeRoles_1317},
    {4, kShapeRoles_1318},
    {4, kShapeRoles_1319},
    {4, kShapeRoles_1320},
    {4, kShapeRoles_1321},
    {5, kShapeRoles_1322},
    {5, kShapeRoles_1323},
    {5, kShapeRoles_1324},
    {5, kShapeRoles_1325},
    {6, kShapeRoles_1326},
    {6, kShapeRoles_1327},
    {5, kShapeRoles_1328},
    {5, kShapeRoles_1329},
    {6, kShapeRoles_1330},
    {6, kShapeRoles_1331},
    {3, kShapeRoles_1332},
    {5, kShapeRoles_1333},
    {3, kShapeRoles_1334},
    {4, kShapeRoles_1335},
    {4, kShapeRoles_1336},
    {3, kShapeRoles_1337},
    {3, kShapeRoles_1338},
    {3, kShapeRoles_1339},
    {3, kShapeRoles_1340},
    {4, kShapeRoles_1341},
    {4, kShapeRoles_1342},
    {4, kShapeRoles_1343},
    {5, kShapeRoles_1344},
    {5, kShapeRoles_1345},
    {5, kShapeRoles_1346},
    {4, kShapeRoles_1347},
    {4, kShapeRoles_1348},
    {3, kShapeRoles_1349},
    {3, kShapeRoles_1350},
    {5, kShapeRoles_1351},
    {5, kShapeRoles_1352},
    {4, kShapeRoles_1353},
    {4, kShapeRoles_1354},
    {3, kShapeRoles_1355},
    {3, kShapeRoles_1356},
    {3, kShapeRoles_1357},
    {4, kShapeRoles_1358},
    {4, kShapeRoles_1359},
    {4, kShapeRoles_1360},
    {3, kShapeRoles_1361},
    {3, kShapeRoles_1362},
    {4, kShapeRoles_1363},
    {9, kShapeRoles_1364},
    {7, kShapeRoles_1365},
    {2, kShapeRoles_1366},
    {9, kShapeRoles_1367},
    {9, kShapeRoles_1368},
    {9, kShapeRoles_1369},
    {9, kShapeRoles_1370},
    {9, kShapeRoles_1371},
    {9, kShapeRoles_1372},
    {9, kShapeRoles_1373},
    {9, kShapeRoles_1374},
    {9, kShapeRoles_1375},
    {9, kShapeRoles_1376},
    {7, kShapeRoles_1377},
    {7, kShapeRoles_1378},
    {9, kShapeRoles_1379},
    {9, kShapeRoles_1380},
    {6, kShapeRoles_1381},
    {6, kShapeRoles_1382},
    {7, kShapeRoles_1383},
    {7, kShapeRoles_1384},
    {7, kShapeRoles_1385},
    {7, kShapeRoles_1386},
    {6, kShapeRoles_1387},
    {6, kShapeRoles_1388},
    {6, kShapeRoles_1389},
    {6, kShapeRoles_1390},
    {6, kShapeRoles_1391},
    {6, kShapeRoles_1392},
    {4, kShapeRoles_1393},
    {4, kShapeRoles_1394},
    {6, kShapeRoles_1395},
    {7, kShapeRoles_1396},
    {6, kShapeRoles_1397},
    {7, kShapeRoles_1398},
    {5, kShapeRoles_1399},
    {6, kShapeRoles_1400},
    {5, kShapeRoles_1401},
    {6, kShapeRoles_1402},
    {4, kShapeRoles_1403},
    {5, kShapeRoles_1404},
    {4, kShapeRoles_1405},
    {5, kShapeRoles_1406},
    {4, kShapeRoles_1407},
    {5, kShapeRoles_1408},
    {6, kShapeRoles_1409},
    {6, kShapeRoles_1410},
    {7, kShapeRoles_1411},
    {6, kShapeRoles_1412},
    {6, kShapeRoles_1413},
};

}  // namespace semu::shape
