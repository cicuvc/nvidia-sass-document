// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_isa.py --shapes
//
// Typed decoded-IR schema (design review; not yet wired into the
// decoder -- the existing DecodedInstruction is unchanged).
#pragma once

#include <cstdint>

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
struct DecodedMOV2 {
    OperandValue ops[2];
    SPILLONLY nonconformity;
    ONLY64 size;
};
struct DecodedMOV3 {
    OperandValue ops[3];
};
struct DecodedP2R4 {
    OperandValue ops[4];
    B3B0 insert;
};
struct DecodedR2P3 {
    OperandValue ops[3];
    B3B0 a_bsel;
};
struct DecodedSEL4 {
    OperandValue ops[4];
    ONLY64 size;
};
struct DecodedFSEL4 {
    OperandValue ops[4];
    FTZ ftz;
};
struct DecodedFMNMX4 {
    OperandValue ops[4];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
};
struct DecodedFMNMX5 {
    OperandValue ops[5];
    FTZ ftz;
    IS_AONLY is_A;
    NAN nan;
    XORSIGN xorsign;
};
struct DecodedFSET4 {
    OperandValue ops[4];
    BFONLY bf;
    Bop bop;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedFSET3 {
    OperandValue ops[3];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedFSETP5 {
    OperandValue ops[5];
    Bop bop;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedFSETP3 {
    OperandValue ops[3];
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedISETP6 {
    OperandValue ops[6];
    Bop bop;
    EXONLY ex;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedISETP5 {
    OperandValue ops[5];
    Bop bop;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedISETP4 {
    OperandValue ops[4];
    EXONLY ex;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedISETP3 {
    OperandValue ops[3];
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedIADD36 {
    OperandValue ops[6];
};
struct DecodedIADD38 {
    OperandValue ops[8];
    XONLY X;
};
struct DecodedISCADD5 {
    OperandValue ops[5];
};
struct DecodedLEA6 {
    OperandValue ops[6];
    XONLY X;
    HIONLY_lea hilo;
    SX32ONLY sx32;
};
struct DecodedLEA5 {
    OperandValue ops[5];
    HIONLY_lea hilo;
    SX32ONLY sx32;
};
struct DecodedLEA7 {
    OperandValue ops[7];
    XONLY X;
    HIONLY_lea hilo;
};
struct DecodedLOP5 {
    OperandValue ops[5];
    LOP lop;
    LOP_POP pop;
};
struct DecodedLOP4 {
    OperandValue ops[4];
    LOP lop;
};
struct DecodedLOP37 {
    OperandValue ops[7];
    LUTOnly lut;
    LOP_POP pop;
};
struct DecodedLOP36 {
    OperandValue ops[6];
    LOP lop;
    LUTOnly lut;
    LOP_POP pop;
};
struct DecodedLOP35 {
    OperandValue ops[5];
    LOP lop;
};
struct DecodedIABS2 {
    OperandValue ops[2];
};
struct DecodedPRMT4 {
    OperandValue ops[4];
    PMode pmode;
};
struct DecodedIMNMX7 {
    OperandValue ops[7];
    FMT_64_DIST fmt;
};
struct DecodedIMNMX6 {
    OperandValue ops[6];
    FMT_64_DIST fmt;
};
struct DecodedSHF4 {
    OperandValue ops[4];
    CWMode cw;
    SDIR dir;
    FMT_shf fmt;
    HILO hilo;
};
struct DecodedSHL3 {
    OperandValue ops[3];
    CWMode cw;
};
struct DecodedSHR3 {
    OperandValue ops[3];
    CWMode cw;
    FMT_S32_U32 fmt;
};
struct DecodedSGXT3 {
    OperandValue ops[3];
    CWMode cw;
    FMT fmt;
};
struct DecodedBMSK3 {
    OperandValue ops[3];
    CWMode cw;
};
struct DecodedPLOP35 {
    OperandValue ops[5];
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
};
struct DecodedPLOP37 {
    OperandValue ops[7];
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
};
struct DecodedFMUL3 {
    OperandValue ops[3];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    Scale scale;
};
struct DecodedFADD3 {
    OperandValue ops[3];
    FTZ ftz;
    Round1 rnd;
    SAT sat;
};
struct DecodedFHADD3 {
    OperandValue ops[3];
    EXTRACT extract_a;
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
};
struct DecodedFFMA4 {
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
};
struct DecodedFHFMA4 {
    OperandValue ops[4];
    EXTRACT extract_a;
    EXTRACT extract_b;
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
};
struct DecodedIMAD4 {
    OperandValue ops[4];
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    LOOnly wide;
};
struct DecodedIMAD5 {
    OperandValue ops[5];
    XONLY X;
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    LOOnly wide;
};
struct DecodedIMUL3 {
    OperandValue ops[3];
    FMT fmt;
    LOOnly wide;
};
struct DecodedIMAD6 {
    OperandValue ops[6];
    XONLY X;
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    WIDEONLY wide;
};
struct DecodedIMUL4 {
    OperandValue ops[4];
    FMT fmt;
    WIDEONLY wide;
};
struct DecodedIDP4 {
    OperandValue ops[4];
    SRCFMT16A SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
    MODE_2ALO_2AHI mode;
};
struct DecodedIDP4A4 {
    OperandValue ops[4];
    SRCFMT_U8_S8 SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
};
struct DecodedDMUL3 {
    OperandValue ops[3];
    Round1 rnd;
};
struct DecodedDADD3 {
    OperandValue ops[3];
    Round1 rnd;
};
struct DecodedDSETP5 {
    OperandValue ops[5];
    Bop bop;
    DSETP_FCMP test;
};
struct DecodedDSETP3 {
    OperandValue ops[3];
    DSETP_FCMP test;
};
struct DecodedDFMA4 {
    OperandValue ops[4];
    Round1 rnd;
};
struct DecodedCLMAD4 {
    OperandValue ops[4];
    HILO hilo;
};
struct DecodedHADD23 {
    OperandValue ops[3];
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    F32ONLY_hadd2 ofmt;
    SAT sat;
};
struct DecodedHFMA24 {
    OperandValue ops[4];
    MMAONLY MMA;
    FMZ fmz;
    ISWZA iswzA;
    NONE iswzA_forced_H1_H0;
    ISWZB iswzB;
    ISWZA iswzB_as_C;
    NONE iswzB_as_C_forced_H1_H0;
    NONE iswzB_forced_H1_H0;
    ISWZA iswzC;
    ISWZB iswzC_as_B;
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    OFMT ofmt;
    SAT satrelu;
};
struct DecodedHFMA25 {
    OperandValue ops[5];
    MMAONLY MMA;
    FMZ_hfma2 fmz;
    ISWZA iswzA;
    NONE iswzA_forced_H1_H0;
    ISWZB iswzB;
    ISWZA iswzB_as_C;
    NONE iswzB_as_C_forced_H1_H0;
    NONE iswzB_forced_H1_H0;
    ISWZA iswzC;
    ISWZB iswzC_as_B;
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    OFMT_F16_V2_BF16_V2 ofmt;
    RELUONLY satrelu;
};
struct DecodedHMUL23 {
    OperandValue ops[3];
    FMZ_hfma2 fmz;
    ISWZA iswzA;
    ISWZA iswzB;
    OFMT_F16_V2_BF16_V2 ofmt;
    SAT sat;
};
struct DecodedHSET24 {
    OperandValue ops[4];
    Bop bop;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedHSET23 {
    OperandValue ops[3];
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedHSETP25 {
    OperandValue ops[5];
    Bop bop;
    FCMP cmp;
    FTZ ftz;
    H_AND h_and;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedHSETP24 {
    OperandValue ops[4];
    FCMP cmp;
    FTZ ftz;
    H_AND h_and;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedIADD4 {
    OperandValue ops[4];
    ONLY64 size;
};
struct DecodedIADD5 {
    OperandValue ops[5];
    XONLY X;
    ONLY64 size;
};
struct DecodedVIADD3 {
    OperandValue ops[3];
    FMT_viadd fmt;
    ISAT isat;
};
struct DecodedIMMA5 {
    OperandValue ops[5];
    SAT SAT_;
    COLONLY col_B;
    ROWONLY row_A;
    SIZE_16816_16832_imma size;
    SRCFMTA_U8_S8 srcFmtA;
    SRCFMTA_U8_S8 srcFmtB;
};
struct DecodedIMMA7 {
    OperandValue ops[7];
    SAT SAT_;
    COLONLY col_B;
    ROWONLY row_A;
    SIZE_16832_16864_imma size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMTA_U8_S8 srcFmtA;
    SRCFMTA_U8_S8 srcFmtB;
};
struct DecodedI2I2 {
    OperandValue ops[2];
    SATONLY SAT;
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
};
struct DecodedI2IP4 {
    OperandValue ops[4];
    DSTFMT_S4_U4 dstfmt;
    ONLY24 extract_limited;
    SATRELU satrelu;
    S32ONLY_i2i srcfmt;
};
struct DecodedMOVM2 {
    OperandValue ops[2];
    MOVM_MODE mode;
    MOVM_SZ sz;
};
struct DecodedHMMA7 {
    OperandValue ops[7];
    FloatNo64 dstfmt;
    SIZE_1688_16816_16832 size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMT srcfmt;
};
struct DecodedHMMA5 {
    OperandValue ops[5];
    FloatNo64 dstfmt;
    SIZE_1688_16816_1684 size;
    SRCFMT srcfmt;
};
struct DecodedF2FP2 {
    OperandValue ops[2];
    F16ONLY_f2fp dstfmt;
    EXTRACT extract_B;
    UNPACK_BONLY merge;
    RELU relu;
    RNONLY rndMode;
    SATFINITE satfinite;
    B3B0 selB;
    SRCFMT_E0M3_E2M1 srcfmt;
};
struct DecodedF2FP3 {
    OperandValue ops[3];
    DSTFMT_F16_BF16 dstfmt;
    EXTRACT extract;
    EXTRACT extract_B;
    ISWZC iswzC;
    PACK_ABONLY merge;
    RELU relu;
    RNDMODE_RN_RZ rndMode;
    SATFINITE satfinite;
    SATNARROW satnarrow;
    B3B0 selB;
    F32ONLY_f2fp srcfmt;
};
struct DecodedF2FP4 {
    OperandValue ops[4];
    DSTFMT_E0M3_E2M1 dstfmt;
    EXTRACT extract;
    PACK_AB_MERGE_CONLY merge;
    RELU relu;
    RNONLY rndMode;
    SATFINITEONLY satfinite;
    SATNARROW satnarrow;
    F32ONLY_f2fp srcfmt;
};
struct DecodedDMMA5 {
    OperandValue ops[5];
    Round1 rnd;
    SIZE_DMMA size;
};
struct DecodedHMNMX24 {
    OperandValue ops[4];
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB;
    NAN nan;
    OFMT_F16_V2_BF16_V2 ofmt;
    XORSIGN xorsign;
};
struct DecodedHMNMX26 {
    OperandValue ops[6];
    FTZ ftz;
    IS_AONLY isA;
    ISWZA iswzA;
    ISWZA iswzB;
    NAN nan;
    OFMT_F16_V2_BF16_V2 ofmt;
    XORSIGN xorsign;
};
struct DecodedF2IP4 {
    OperandValue ops[4];
    DSTFMT_U8_S8 dstfmt;
    EXTRACT extract;
    NTZ ntz;
    RELU relu;
    RND_ROUND_TRUNC rnd;
    F32ONLY_hadd2 srcfmt;
};
struct DecodedI2FP2 {
    OperandValue ops[2];
    F32ONLY_i2fp dstfmt;
    RND_RN_RZ rnd;
    SRCFMT_i2fp srcfmt;
};
struct DecodedVIMNMX4 {
    OperandValue ops[4];
    FMT_vimnmx fmt;
    RELU relu;
};
struct DecodedQMMA5 {
    OperandValue ops[5];
    COLONLY col_B;
    FloatNo64 dstfmt;
    ROWONLY row_A;
    SIZE_16816_16832 size;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
};
struct DecodedQMMA7 {
    OperandValue ops[7];
    COLONLY col_B;
    FloatNo64 dstfmt;
    ROWONLY row_A;
    SIZE_16832_16864 size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
};
struct DecodedR2UR3 {
    OperandValue ops[3];
    ORONLY OR;
    NONCONFORMITY_FILL_BROADCAST nonconformity;
};
struct DecodedFLO3 {
    OperandValue ops[3];
    FMT fmt;
    SH sh;
};
struct DecodedBREV2 {
    OperandValue ops[2];
};
struct DecodedFCHK3 {
    OperandValue ops[3];
    ChkMode mode;
};
struct DecodedF2F2 {
    OperandValue ops[2];
    DSTFMT_SRCFMT_F16F32_BF16F32 dstfmt_srcfmt;
    FTZ ftz;
    HSEL hsel;
    Round1 rnd;
};
struct DecodedF2I2 {
    OperandValue ops[2];
    DSTFMT_U8_S8_U16_S16_U32_S32 dstfmt;
    FTZ ftz;
    HSEL hsel;
    NTZ ntz;
    Round3 rnd;
    Float16 srcfmt;
};
struct DecodedI2F2 {
    OperandValue ops[2];
    B3B0 bsel;
    DSTFMT_F16_F32_BF16 dstfmt;
    HSEL hsel;
    Round1 rnd;
    SRCFMT_U16_S16 srcfmt;
};
struct DecodedFRND2 {
    OperandValue ops[2];
    BF16ONLY_frnd fmt;
    FTZ ftz;
    HSEL hsel;
    Round3 rnd;
};
struct DecodedMUFU2 {
    OperandValue ops[2];
    HSEL extract;
    FMT_F16_BF16 fmt;
    MUFU_OP mufuop;
};
struct DecodedPOPC2 {
    OperandValue ops[2];
};
struct DecodedB2R2 {
    OperandValue ops[2];
    BarmdBAR mode;
};
struct DecodedB2R1 {
    OperandValue ops[1];
    BarmdWARP mode;
};
struct DecodedBAR2 {
    OperandValue ops[2];
    BarArv barmode;
    DEFER_BLOCKINGONLY defer_blocking;
};
struct DecodedBAR3 {
    OperandValue ops[3];
    BarRED barmode;
    DEFER_BLOCKINGONLY defer_blocking;
    Red op;
};
struct DecodedR2B2 {
    OperandValue ops[2];
    MODE_BAR_WARP mode;
};
struct DecodedSETCTAID1 {
    OperandValue ops[1];
    CTA_DIM dim;
};
struct DecodedALD4 {
    OperandValue ops[4];
    AIO io;
    PHYSONLY p;
    ONLY32 sz;
};
struct DecodedALD5 {
    OperandValue ops[5];
    AIO io;
    PONLY p;
    AInteger sz;
};
struct DecodedAST4 {
    OperandValue ops[4];
    PHYSONLY p;
    ONLY32 sz;
};
struct DecodedAST5 {
    OperandValue ops[5];
    PONLY p;
    AInteger sz;
};
struct DecodedOUT3 {
    OperandValue ops[3];
    CUTONLY type;
};
struct DecodedOUT1 {
    OperandValue ops[1];
    FINALONLY type;
};
struct DecodedIPA4 {
    OperandValue ops[4];
    MODE ipaop;
    MSI_CENTER_CENTROID msi;
};
struct DecodedIPA5 {
    OperandValue ops[5];
    MODE ipaop;
    OFFSETONLY msi;
};
struct DecodedCCTL0 {
    CONLY cache;
    IVALLONLY cop;
    SHALLOWONLY depth;
    LDCONLY ldc;
    LDCUONLY ldcu;
};
struct DecodedCALL3 {
    OperandValue ops[3];
    std::uint8_t abs;
    CALL_DEPTH depth;
    std::uint8_t rel;
    std::uint8_t rel_imm;
};
struct DecodedCALL2 {
    OperandValue ops[2];
    std::uint8_t abs;
    CALL_DEPTH depth;
    std::uint8_t rel;
    std::uint8_t rel_imm;
};
struct DecodedWARPSYNC2 {
    OperandValue ops[2];
    ALLOnly all;
    DIV__EXCLUSIVE div;
    std::uint8_t rel;
};
struct DecodedWARPSYNC3 {
    OperandValue ops[3];
    COLLECTIVEONLY div;
    std::uint8_t rel;
};
struct DecodedLEPC1 {
    OperandValue ops[1];
};
struct DecodedRPCMOV2 {
    OperandValue ops[2];
    ONLY32 sz;
};
struct DecodedBMOV2 {
    OperandValue ops[2];
    CLEAR clear;
    PQUAD pquad;
    ONLY32 sz;
};
struct DecodedNANOTRAP2 {
    OperandValue ops[2];
    RAND rand;
};
struct DecodedNANOSLEEP2 {
    OperandValue ops[2];
    RAND rand;
    SYNCS_MOD syncs;
    OPTIONAL_WARP warp;
};
struct DecodedTEX9 {
    OperandValue ops[9];
    AOFFI aoffi;
    BONLY b;
    COP cop;
    DC dc;
    DIV div;
    LODLC_tex lodlc;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    UAI uai;
};
struct DecodedTMML6 {
    OperandValue ops[6];
    BONLY b;
    DIV div;
    LODOnly lod;
    NODEP nodep;
};
struct DecodedTXQ5 {
    OperandValue ops[5];
    BONLY b;
    NODEP nodep;
};
struct DecodedLDG5 {
    OperandValue ops[5];
    COP cop;
    E e;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedST3 {
    OperandValue ops[3];
    COP cop;
    E e;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTG3 {
    OperandValue ops[3];
    COP cop;
    E e;
    ORDER order;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTL3 {
    OperandValue ops[3];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTS3 {
    OperandValue ops[3];
    STRIDE stride;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSHFL5 {
    OperandValue ops[5];
    Shflmd shflmd;
};
struct DecodedATOM6 {
    OperandValue ops[6];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    AtomsOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    ATOMICINTSIZES sz;
};
struct DecodedATOM7 {
    OperandValue ops[7];
    CAS cas;
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    AtomsOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    AtomsSPIN spin;
    ATOMCASSZ sz;
};
struct DecodedATOMS4 {
    OperandValue ops[4];
    AtomsOp op;
    STRIDE stride;
    ATOMCASSZ sz;
};
struct DecodedREDS3 {
    OperandValue ops[3];
    REDSOP op;
    STRIDE stride;
    REDSSIZE sz;
};
struct DecodedATOMS5 {
    OperandValue ops[5];
    CAS cas;
    AtomsOp op;
    AtomsSPIN spin;
    STRIDE stride;
    ATOMCASSZ sz;
};
struct DecodedCCTLT0 {
    IVALLONLY_cctlt cop;
};
struct DecodedCCTLT1 {
    OperandValue ops[1];
    CCTLTOp cop;
};
struct DecodedSUATOM6 {
    OperandValue ops[6];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    AtomsOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SURFACESIZE sz;
    UAI uai;
};
struct DecodedSURED4 {
    OperandValue ops[4];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    RedOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SURFACESIZE sz;
    UAI uai;
};
struct DecodedMATCH3 {
    OperandValue ops[3];
    ALLOnly op;
    MATCH_SZ sz;
};
struct DecodedMATCH2 {
    OperandValue ops[2];
    ANYONLY op;
    MATCH_SZ sz;
};
struct DecodedATOMG5 {
    OperandValue ops[5];
    COP cop;
    E e;
    ATOMICFPOPS op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_0 sz;
};
struct DecodedSYNCS0 {
    CCTLONLY cctl_mode;
    SYNCS_CCTL_OP_ALL cctlop;
    FLUSHONLY op;
};
struct DecodedATOMG6 {
    OperandValue ops[6];
    CAS cas;
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    ATOMICFPOPS op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    ATOMCASSZ sz;
};
struct DecodedQSPC3 {
    OperandValue ops[3];
    E e;
    QUERY_SPACE space;
};
struct DecodedQSPC4 {
    OperandValue ops[4];
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    QUERY_SPACE space;
};
struct DecodedGETLMEMBASE1 {
    OperandValue ops[1];
};
struct DecodedSETLMEMBASE1 {
    OperandValue ops[1];
};
struct DecodedREDUX2 {
    OperandValue ops[2];
    REDUX_OP op;
    FMT sz;
};
struct DecodedFENCE0 {
    SONLY memType;
    ASYNCONLY syncType;
    VIEWONLY type;
};
struct DecodedTTUOPEN0 {
    DUAL dual;
};
struct DecodedTTUST4 {
    OperandValue ops[4];
};
struct DecodedTTUCLOSE1 {
    OperandValue ops[1];
};
struct DecodedTTULD5 {
    OperandValue ops[5];
    CLOSE close;
};
struct DecodedTTUGO0 {
};
struct DecodedTTUCCTL0 {
    IVALLONLY_utmacctl ivall;
};
struct DecodedFADD32I3 {
    OperandValue ops[3];
    FTZ ftz;
};
struct DecodedHADD24 {
    OperandValue ops[4];
    FTZ ftz;
    ISWZA iswzA;
    F32ONLY_hadd2 ofmt;
    SAT sat;
};
struct DecodedHADD2_32I4 {
    OperandValue ops[4];
    FTZ ftz;
    ISWZA iswzA;
    SAT sat;
};
struct DecodedHFMA26 {
    OperandValue ops[6];
    MMAONLY MMA;
    FMZ_hfma2 fmz;
    ISWZA iswzA;
    NONE iswzA_forced_H1_H0;
    ISWZA iswzC;
    ISWZB iswzC_as_B;
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    OFMT_F16_V2_BF16_V2 ofmt;
    RELUONLY satrelu;
};
struct DecodedHSET25 {
    OperandValue ops[5];
    Bop bop;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedHSETP26 {
    OperandValue ops[6];
    Bop bop;
    FCMP cmp;
    FTZ ftz;
    H_AND h_and;
    ISWZA iswzA;
    OFMT_F16_V2_BF16_V2 ofmt;
};
struct DecodedQMMA8 {
    OperandValue ops[8];
    F32ONLY_f2fp dstfmt;
    REUSE reuse_src_h;
    ONLY1X scaleVectorSz;
    E8ONLY_mxqmma scalefmt;
    SFONLY sf;
    ONLY16832 size;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
};
struct DecodedQMMA9 {
    OperandValue ops[9];
    F32ONLY_f2fp dstfmt;
    REUSE reuse_src_h;
    ONLY1X scaleVectorSz;
    E8ONLY_mxqmma scalefmt;
    SFONLY sf;
    ONLY16864 size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMTA_qmma srcFmtA;
    SRCFMTA_qmma srcFmtB;
};
struct DecodedMXQMMA8 {
    OperandValue ops[8];
    F32ONLY_f2fp dstfmt;
    REUSE reuse_src_h;
    ONLY1X scaleVectorSz;
    E8ONLY_mxqmma scalefmt;
    SFONLY sf;
    ONLY16832 size;
    S2_6ONLY_mxqmma srcFmtA;
    S2_6ONLY_mxqmma srcFmtB;
};
struct DecodedOMMA8 {
    OperandValue ops[8];
    F32ONLY_f2fp dstfmt;
    REUSE reuse_src_h;
    SCALEVECTORSZ scaleVectorSz;
    SCALEFMT scalefmt;
    SFONLY sf;
    ONLY16864 size;
    SRCFMTA srcFmtA;
    SRCFMTA srcFmtB;
};
struct DecodedOMMA9 {
    OperandValue ops[9];
    F32ONLY_f2fp dstfmt;
    REUSE reuse_src_h;
    SCALEVECTORSZ scaleVectorSz;
    SCALEFMT scalefmt;
    SFONLY sf;
    ONLY168128 size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMTA srcFmtA;
    SRCFMTA srcFmtB;
};
struct DecodedMOV64IUR2 {
    OperandValue ops[2];
};
struct DecodedCGAERRBAR0 {
};
struct DecodedPMTRIG2 {
    OperandValue ops[2];
};
struct DecodedMOV32I3 {
    OperandValue ops[3];
};
struct DecodedP2R2 {
    OperandValue ops[2];
    B3B0 insert;
};
struct DecodedCS2R2 {
    OperandValue ops[2];
    QInteger sz;
};
struct DecodedVOTE3 {
    OperandValue ops[3];
    VoteOp voteop;
};
struct DecodedCSMTEST1 {
    OperandValue ops[1];
    VOP vtgmode;
};
struct DecodedCSMTEST4 {
    OperandValue ops[4];
    Bop bop;
    CCMP ccmp;
    VOP vtgmode;
};
struct DecodedCSMTEST2 {
    OperandValue ops[2];
    CCMP ccmp;
    VOP vtgmode;
};
struct DecodedVOTE_VTG1 {
    OperandValue ops[1];
    VOP vtgmode;
};
struct DecodedVOTE_VTG4 {
    OperandValue ops[4];
    Bop bop;
    CCMP ccmp;
    VOP vtgmode;
};
struct DecodedVOTE_VTG2 {
    OperandValue ops[2];
    CCMP ccmp;
    VOP vtgmode;
};
struct DecodedISCADD32I5 {
    OperandValue ops[5];
};
struct DecodedLOP32I5 {
    OperandValue ops[5];
    LOP lop;
    LOP_POP pop;
};
struct DecodedLOP32I4 {
    OperandValue ops[4];
    LOP lop;
};
struct DecodedPLOP34 {
    OperandValue ops[4];
    PLOP_OP_NOREG lop;
};
struct DecodedPSETP5 {
    OperandValue ops[5];
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
};
struct DecodedPSETP3 {
    OperandValue ops[3];
    PSETP_BOP0 bop0;
};
struct DecodedFMUL32I3 {
    OperandValue ops[3];
    FMZ_hfma2 fmz;
    SAT sat;
};
struct DecodedFSWZADD4 {
    OperandValue ops[4];
    DIV div;
    FTZ ftz;
    Round1 rnd;
};
struct DecodedFFMA32I4 {
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    SAT sat;
};
struct DecodedIMUL32I3 {
    OperandValue ops[3];
    FMT fmt;
    LOOnly wide;
};
struct DecodedIMUL32I4 {
    OperandValue ops[4];
    FMT fmt;
    WIDEONLY wide;
};
struct DecodedPREEXIT0 {
};
struct DecodedACQBULK0 {
};
struct DecodedELECT3 {
    OperandValue ops[3];
    IGNORE_KILL ignoreKill;
};
struct DecodedHFMA2_32I5 {
    OperandValue ops[5];
    FMZ fmz;
    ISWZA iswzA;
    ISWZA iswzC;
};
struct DecodedHMUL24 {
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    ISWZA iswzA;
    OFMT_F16_V2_BF16_V2 ofmt;
    SAT sat;
};
struct DecodedHMUL2_32I4 {
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    ISWZA iswzA;
    SAT sat;
};
struct DecodedIADD32I4 {
    OperandValue ops[4];
};
struct DecodedIADD32I5 {
    OperandValue ops[5];
    XONLY X;
};
struct DecodedLDSM3 {
    OperandValue ops[3];
    LDSM_MODE mode;
    LDSM_NUM num;
    PSEUDO_OP pseudo_op;
    LDSM_SZ sz;
};
struct DecodedHMNMX25 {
    OperandValue ops[5];
    FTZ ftz;
    ISWZA iswzA;
    NAN nan;
    OFMT_F16_V2_BF16_V2 ofmt;
    XORSIGN xorsign;
};
struct DecodedHMNMX27 {
    OperandValue ops[7];
    FTZ ftz;
    IS_AONLY isA;
    ISWZA iswzA;
    NAN nan;
    OFMT_F16_V2_BF16_V2 ofmt;
    XORSIGN xorsign;
};
struct DecodedSTSM3 {
    OperandValue ops[3];
    STSM_MODE mode;
    LDSM_NUM num;
    STSM_SZ sz;
};
struct DecodedUVIRTCOUNT2 {
    OperandValue ops[2];
    ONEONLY one;
    DEALLOCONLY_uvirtcount op;
    SMPOOLONLY pool;
};
struct DecodedACQSHMINIT0 {
};
struct DecodedUMOV3 {
    OperandValue ops[3];
    ONLY64_syncs size;
};
struct DecodedVOTEU3 {
    OperandValue ops[3];
    VoteOp voteop;
};
struct DecodedUPLOP35 {
    OperandValue ops[5];
    PLOP_OP_NOREG lop;
};
struct DecodedUPLOP36 {
    OperandValue ops[6];
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
};
struct DecodedUPLOP38 {
    OperandValue ops[8];
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
};
struct DecodedUPSETP6 {
    OperandValue ops[6];
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
};
struct DecodedUPSETP4 {
    OperandValue ops[4];
    PSETP_BOP0 bop0;
};
struct DecodedCS2UR3 {
    OperandValue ops[3];
    QInteger sz;
};
struct DecodedNOP0 {
};
struct DecodedS2R2 {
    OperandValue ops[2];
};
struct DecodedDEPBAR3 {
    OperandValue ops[3];
    LEONLY le;
};
struct DecodedDEPBAR1 {
    OperandValue ops[1];
};
struct DecodedDEPBAR0 {
    ALLOnly le;
};
struct DecodedENDCOLLECTIVE1 {
    OperandValue ops[1];
};
struct DecodedAL2P3 {
    OperandValue ops[3];
    AIO io;
    AInteger sz;
};
struct DecodedISBERD3 {
    OperandValue ops[3];
    BASE base;
    AIO io;
    SKEW skew;
    ISBERD_SZ sz;
};
struct DecodedPIXLD2 {
    OperandValue ops[2];
    PIXLD_MODE mode;
};
struct DecodedISBEWR3 {
    OperandValue ops[3];
    ISBEWR_BASE base;
    OONLY io;
    SKEW skew;
    ISBERD_SZ sz;
};
struct DecodedBSYNC2 {
    OperandValue ops[2];
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
};
struct DecodedBREAK2 {
    OperandValue ops[2];
    RELIABLEONLY reliability;
};
struct DecodedBSSY3 {
    OperandValue ops[3];
    std::uint8_t rel;
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
};
struct DecodedYIELD1 {
    OperandValue ops[1];
};
struct DecodedBRA2 {
    OperandValue ops[2];
    COND__DIV_CONV cond;
    DEPTH depth;
    NOTTID0 nottid0;
    std::uint8_t rel;
    USEL usel;
};
struct DecodedWARPSYNC1 {
    OperandValue ops[1];
    ALLOnly all;
};
struct DecodedBRX3 {
    OperandValue ops[3];
    DEPTH depth;
    std::uint8_t rel;
};
struct DecodedJMP2 {
    OperandValue ops[2];
    COND__DIV_CONV cond;
    DEPTH depth;
    std::uint8_t rel;
    USEL usel;
};
struct DecodedJMX3 {
    OperandValue ops[3];
    DEPTH depth;
    std::uint8_t rel;
};
struct DecodedEXIT1 {
    OperandValue ops[1];
    EXIT_MODE mode;
    NO_ATEXIT no_atexit;
};
struct DecodedLEPC2 {
    OperandValue ops[2];
    std::uint8_t rel;
};
struct DecodedRTT0 {
};
struct DecodedRET3 {
    OperandValue ops[3];
    ABSONLY_ret addr;
    RET_DEPTH depth;
    std::uint8_t rel_imm;
};
struct DecodedRET2 {
    OperandValue ops[2];
    RET_ADDR addr;
    RET_DEPTH depth;
};
struct DecodedIDE1 {
    OperandValue ops[1];
    IDEAction action;
};
struct DecodedKILL1 {
    OperandValue ops[1];
};
struct DecodedBPT1 {
    OperandValue ops[1];
    BPT_TRAP_INT bpt;
};
struct DecodedNANOSLEEP1 {
    OperandValue ops[1];
    CLEARONLY clear;
};
struct DecodedLD4 {
    OperandValue ops[4];
    COP cop;
    E e;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDL3 {
    OperandValue ops[3];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDS3 {
    OperandValue ops[3];
    STRIDE stride;
    LDSSIZE sz;
};
struct DecodedREDG3 {
    OperandValue ops[3];
    COP cop;
    E e;
    RedOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    REDSSIZE sz;
};
struct DecodedCCTL2 {
    OperandValue ops[2];
    Cache cache;
    COP_PF1_WB_IV_RS_PML2_DML2 cop;
    SHALLOWONLY depth;
    E e;
    LDCONLY ldc;
    LDCUONLY ldcu;
};
struct DecodedCCTL3 {
    OperandValue ops[3];
    Cache cache;
    PF2ONLY cop;
    E e;
    QFAULTONLY qfault;
};
struct DecodedCCTLL0 {
    COP_IVALL_WBALL cop;
};
struct DecodedCCTLL2 {
    OperandValue ops[2];
    COP_PF1_PF2_WB_IV_RS cop;
};
struct DecodedMEMBAR0 {
    ASYNCONLY_membar mmio;
    SCO_CTA_SM_GPU_SYS_VC_CTAPARTIAL sco;
    MEMBAR_SEM sem;
};
struct DecodedSULD5 {
    OperandValue ops[5];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    PONLY p;
    PRIVATE private_;
    RGBA rgba;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    UAI uai;
};
struct DecodedSUST4 {
    OperandValue ops[4];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    PONLY p;
    PRIVATE private_;
    RGBA rgba;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    UAI uai;
};
struct DecodedERRBAR0 {
};
struct DecodedLDGDEPBAR0 {
};
struct DecodedSUQUERY6 {
    OperandValue ops[6];
    BA ba;
    Dim1 dim;
    UAI uai;
};
struct DecodedUTMACMDFLUSH1 {
    OperandValue ops[1];
};
struct DecodedUTMACCTL1 {
    OperandValue ops[1];
    IVALLONLY_utmacctl ivall;
    ONEONLY one;
};
struct DecodedS2UR3 {
    OperandValue ops[3];
};
struct DecodedTTUMACROFUSE1 {
    OperandValue ops[1];
};
struct DecodedBAR0 {
    BarSYNCALL barmode;
    DEFER_BLOCKINGONLY defer_blocking;
};
struct DecodedCCTL4 {
    OperandValue ops[4];
    CONLY cache;
    IVONLY cop;
    SHALLOWONLY depth;
    LDCONLY ldc;
    LDCUONLY ldcu;
};
struct DecodedLDC5 {
    OperandValue ops[5];
    AdMode ad;
    SZ_U8_S8_U16_S16_32_64 sz;
};
struct DecodedUVIADD4 {
    OperandValue ops[4];
    FMT_viadd fmt;
    ISAT isat;
};
struct DecodedUVIMNMX5 {
    OperandValue ops[5];
    FMT_vimnmx fmt;
    RELU relu;
};
struct DecodedUIABS3 {
    OperandValue ops[3];
};
struct DecodedUI2I3 {
    OperandValue ops[3];
    SATONLY SAT;
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
};
struct DecodedUI2IP5 {
    OperandValue ops[5];
    DSTFMT_S4_U4 dstfmt;
    ONLY24 extract_limited;
    SATRELU_ui2ip satrelu;
    S32ONLY_i2i srcfmt;
};
struct DecodedUFMNMX5 {
    OperandValue ops[5];
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
};
struct DecodedUFMNMX6 {
    OperandValue ops[6];
    FTZ ftz;
    IS_AONLY is_A;
    NAN nan;
    XORSIGN xorsign;
};
struct DecodedUFSEL5 {
    OperandValue ops[5];
    FTZ ftz;
};
struct DecodedUFSET5 {
    OperandValue ops[5];
    BFONLY bf;
    Bop bop;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedUFSET4 {
    OperandValue ops[4];
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedUFSETP6 {
    OperandValue ops[6];
    Bop bop;
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedUFSETP4 {
    OperandValue ops[4];
    FCMP fcomp;
    FTZ ftz;
};
struct DecodedUFADD4 {
    OperandValue ops[4];
    FTZ ftz;
    Round1 rnd;
    SAT sat;
};
struct DecodedUFHADD4 {
    OperandValue ops[4];
    EXTRACT extract_a;
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
};
struct DecodedUFFMA5 {
    OperandValue ops[5];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
};
struct DecodedUFHFMA5 {
    OperandValue ops[5];
    EXTRACT extract_a;
    EXTRACT extract_b;
    DSTFMT_F16_BF16 mode16;
    Round1 rnd;
    SAT sat;
};
struct DecodedUFMUL4 {
    OperandValue ops[4];
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    Scale scale;
};
struct DecodedUF2IP5 {
    OperandValue ops[5];
    DSTFMT_U8_S8 dstfmt;
    EXTRACT extract;
    NTZ ntz;
    RELU relu;
    RND_ROUND_TRUNC rnd;
    F32ONLY_hadd2 srcfmt;
};
struct DecodedUI2F3 {
    OperandValue ops[3];
    B3B0 bsel;
    DSTFMT_F16_F32_BF16 dstfmt;
    HSEL hsel;
    Round1 rnd;
    SRCFMT_U16_S16 srcfmt;
};
struct DecodedUF2F3 {
    OperandValue ops[3];
    DSTFMT_SRCFMT_F16F32_BF16F32 dstfmt_srcfmt;
    FTZ ftz;
    HSEL hsel;
    Round1 rnd;
};
struct DecodedUF2I3 {
    OperandValue ops[3];
    DSTFMT_U8_S8_U16_S16_U32_S32 dstfmt;
    FTZ ftz;
    HSEL hsel;
    NTZ ntz;
    Round3 rnd;
    Float16 srcfmt;
};
struct DecodedUFRND3 {
    OperandValue ops[3];
    BF16ONLY_frnd fmt;
    FTZ ftz;
    HSEL hsel;
    Round3 rnd;
};
struct DecodedUI2FP3 {
    OperandValue ops[3];
    F32ONLY_i2fp dstfmt;
    RND_RN_RZ rnd;
    SRCFMT_i2fp srcfmt;
};
struct DecodedUIMNMX8 {
    OperandValue ops[8];
    FMT_64_DIST fmt;
};
struct DecodedUIMNMX7 {
    OperandValue ops[7];
    FMT_64_DIST fmt;
};
struct DecodedUSEL5 {
    OperandValue ops[5];
    ONLY64 size;
};
struct DecodedUISETP6 {
    OperandValue ops[6];
    Bop bop;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedUISETP7 {
    OperandValue ops[7];
    Bop bop;
    EXONLY ex;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedUISETP4 {
    OperandValue ops[4];
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedUISETP5 {
    OperandValue ops[5];
    EXONLY ex;
    FMT_64_DIST fmt;
    ICmpAll icmp;
};
struct DecodedUIADD37 {
    OperandValue ops[7];
};
struct DecodedUIADD39 {
    OperandValue ops[9];
    XONLY X;
};
struct DecodedULEA7 {
    OperandValue ops[7];
    XONLY X;
    HIONLY_lea hilo;
    SX32ONLY sx32;
};
struct DecodedULEA6 {
    OperandValue ops[6];
    HIONLY_lea hilo;
    SX32ONLY sx32;
};
struct DecodedULEA8 {
    OperandValue ops[8];
    XONLY X;
    HIONLY_lea hilo;
};
struct DecodedULOP6 {
    OperandValue ops[6];
    LOP lop;
    LOP_POP pop;
};
struct DecodedULOP5 {
    OperandValue ops[5];
    LOP lop;
};
struct DecodedULOP38 {
    OperandValue ops[8];
    LUTOnly lut;
    LOP_POP pop;
};
struct DecodedULOP37 {
    OperandValue ops[7];
    LOP lop;
    LUTOnly lut;
    LOP_POP pop;
};
struct DecodedULOP36 {
    OperandValue ops[6];
    LOP lop;
};
struct DecodedUPRMT5 {
    OperandValue ops[5];
    IDXOnly idx;
};
struct DecodedUIADD3_647 {
    OperandValue ops[7];
};
struct DecodedUIADD3_649 {
    OperandValue ops[9];
    XONLY X;
};
struct DecodedUSHF5 {
    OperandValue ops[5];
    CWMode cw;
    SDIR dir;
    FMT_shf fmt;
    HILO hilo;
};
struct DecodedUSHL4 {
    OperandValue ops[4];
    CWMode cw;
};
struct DecodedUSHR4 {
    OperandValue ops[4];
    CWMode cw;
    FMT_S32_U32 fmt;
};
struct DecodedUSGXT4 {
    OperandValue ops[4];
    CWMode cw;
    FMT fmt;
};
struct DecodedUBMSK4 {
    OperandValue ops[4];
    CWMode cw;
};
struct DecodedUIMAD5 {
    OperandValue ops[5];
    FMT fmt;
    LOOnly wide;
};
struct DecodedUIMAD6 {
    OperandValue ops[6];
    XONLY X;
    FMT fmt;
    LOOnly wide;
};
struct DecodedUIMAD7 {
    OperandValue ops[7];
    XONLY X;
    FMT fmt;
    WIDEONLY wide;
};
struct DecodedUF2FP3 {
    OperandValue ops[3];
    DSTFMT_uf2fp dstfmt;
    EXTRACT extract;
    UNPACK_BONLY merge;
    RELU relu;
    RNONLY rndMode;
    SATFINITE satfinite;
    SRCFMT_E5M2_E4M3 srcfmt;
};
struct DecodedUF2FP4 {
    OperandValue ops[4];
    DSTFMT_uf2fp dstfmt;
    EXTRACT extract;
    PACK_ABONLY merge;
    RELU relu;
    RNDMODE_RN_RZ rndMode;
    SATFINITE satfinite;
    Float32 srcfmt;
};
struct DecodedUF2FP5 {
    OperandValue ops[5];
    DSTFMT_uf2fp dstfmt;
    EXTRACT extract;
    PACK_AB_MERGE_CONLY merge;
    RELU relu;
    RNONLY rndMode;
    SATFINITE satfinite;
    Float32 srcfmt;
};
struct DecodedUFLO4 {
    OperandValue ops[4];
    FMT fmt;
    SH sh;
};
struct DecodedUBREV3 {
    OperandValue ops[3];
};
struct DecodedUPOPC3 {
    OperandValue ops[3];
};
struct DecodedLDCU7 {
    OperandValue ops[7];
    ONLY256_ldcu sz;
};
struct DecodedLDCU6 {
    OperandValue ops[6];
    ONLY256_ldcu sz;
    TEXUNPACK texunpack;
};
struct DecodedLDTRAM4 {
    OperandValue ops[4];
    MODE_ldtram mode;
};
struct DecodedSYNCS6 {
    OperandValue ops[6];
    CASONLY emuop;
    ONLY64_syncs sz;
};
struct DecodedUTMALDG4 {
    OperandValue ops[4];
    ONLY1CTA cluster_sz;
    TENSORDIM dim;
    MODE_TILED_IM2COL_W_GATHER4 mode;
    MULTICAST multicast;
    ONEONLY one;
};
struct DecodedUTMALDG6 {
    OperandValue ops[6];
    ONLY1CTA cluster_sz;
    TENSORDIM dim;
    MODE_TILED_IM2COL_W_GATHER4 mode;
    MULTICAST multicast;
    ONEONLY one;
};
struct DecodedUTMASTG3 {
    OperandValue ops[3];
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
};
struct DecodedUTMASTG5 {
    OperandValue ops[5];
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
};
struct DecodedUTMAREDG3 {
    OperandValue ops[3];
    TENSORDIM dim;
    MODE_utmaredg mode;
    ONEONLY one;
    RedOp op;
};
struct DecodedUTMAREDG5 {
    OperandValue ops[5];
    TENSORDIM dim;
    MODE_utmaredg mode;
    ONEONLY one;
    RedOp op;
};
struct DecodedUTMAPF4 {
    OperandValue ops[4];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_IM2COL_W mode;
    ONEONLY one;
};
struct DecodedUTMAPF6 {
    OperandValue ops[6];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_IM2COL_W mode;
    ONEONLY one;
};
struct DecodedUBLKCP4 {
    OperandValue ops[4];
    BYTE_MASK byte_mask;
    DST dst;
    MULTICAST multicast;
    ONEONLY one;
    SCO sco;
    SEM_ublkcp sem;
    SEQ seq;
    SP2 sp2;
    DST src;
};
struct DecodedUBLKCP6 {
    OperandValue ops[6];
    BYTE_MASK byte_mask;
    DST dst;
    MULTICAST multicast;
    ONEONLY one;
    SCO sco;
    SEM_ublkcp sem;
    SEQ seq;
    SP2 sp2;
    DST src;
};
struct DecodedUBLKRED4 {
    OperandValue ops[4];
    DST dst;
    ONEONLY one;
    RedOp op;
    SCO sco;
    SEM_ublkcp sem;
    SONLY_ublkred src;
    SIZE sz;
};
struct DecodedUBLKRED6 {
    OperandValue ops[6];
    DST dst;
    ONEONLY one;
    RedOp op;
    SCO sco;
    SEM_ublkcp sem;
    SONLY_ublkred src;
    SIZE sz;
};
struct DecodedUBLKPF3 {
    OperandValue ops[3];
    L2ONLY cache;
    ONEONLY one;
};
struct DecodedUBLKPF5 {
    OperandValue ops[5];
    L2ONLY cache;
    ONEONLY one;
};
struct DecodedUCGABARSET2 {
    OperandValue ops[2];
};
struct DecodedUCGABAR_SET2 {
    OperandValue ops[2];
};
struct DecodedUSETMAXREG3 {
    OperandValue ops[3];
    TRY_ALLOCONLY mode;
    CTAPOOLONLY pool;
};
struct DecodedUSETMAXREG2 {
    OperandValue ops[2];
    DEALLOCONLY mode;
    CTAPOOLONLY pool;
};
struct DecodedUSETSHMSZ2 {
    OperandValue ops[2];
};
struct DecodedUGETNEXTWORKID3 {
    OperandValue ops[3];
    UGETNEXTWORKID_CAST cast;
    ONEONLY one;
};
struct DecodedUMEMSETS5 {
    OperandValue ops[5];
    ONLY64 sz;
};
struct DecodedULEPC2 {
    OperandValue ops[2];
};
struct DecodedMOV4 {
    OperandValue ops[4];
};
struct DecodedIPA6 {
    OperandValue ops[6];
    MODE ipaop;
    OFFSETONLY msi;
};
struct DecodedBRA3 {
    OperandValue ops[3];
    UONLY cond;
    DEPTH depth;
    std::uint8_t rel;
    USEL usel;
};
struct DecodedJMP3 {
    OperandValue ops[3];
    UONLY cond;
    DEPTH depth;
    std::uint8_t rel;
    USEL usel;
};
struct DecodedSYNCS5 {
    OperandValue ops[5];
    TRANS64ONLY bartype;
    EXCHONLY emuop;
    PHASECHKONLY op;
    OPTOUT optout;
    PARAMTYPE paramtype;
    RETVAL_OLDSTATE_TMASK_RED retval;
    ONLY64_syncs sz;
    WAIT wait;
};
struct DecodedLDCU8 {
    OperandValue ops[8];
    ONLY256_ldcu sz;
};
struct DecodedSYNCS4 {
    OperandValue ops[4];
    TRANS64ONLY bartype;
    LDONLY cctl_mode;
    LDONLY_syncs emuop;
    TCNTONLY op;
    BarRED retval;
    ONLY64_syncs sz;
    WATCH watch;
};
struct DecodedUTMALDG3 {
    OperandValue ops[3];
    ONLY1CTA cluster_sz;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
};
struct DecodedUTMALDG5 {
    OperandValue ops[5];
    ONLY1CTA cluster_sz;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
};
struct DecodedUTMAPF3 {
    OperandValue ops[3];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
};
struct DecodedUTMAPF5 {
    OperandValue ops[5];
    L2ONLY cache;
    TENSORDIM dim;
    MODE_TILED_GATHER4 mode;
    ONEONLY one;
};
struct DecodedUCGABARGET2 {
    OperandValue ops[2];
};
struct DecodedUCGABAR_GET2 {
    OperandValue ops[2];
};
struct DecodedELECT2 {
    OperandValue ops[2];
    IGNORE_KILL ignoreKill;
};
struct DecodedLDSM4 {
    OperandValue ops[4];
    LDSM_MODE mode;
    LDSM_NUM num;
    PSEUDO_OP pseudo_op;
    LDSM_SZ sz;
};
struct DecodedSTSM4 {
    OperandValue ops[4];
    STSM_MODE mode;
    LDSM_NUM num;
    STSM_SZ sz;
};
struct DecodedUP2UR5 {
    OperandValue ops[5];
    B3B0 insert;
};
struct DecodedUP2UR3 {
    OperandValue ops[3];
    B3B0 insert;
};
struct DecodedUR2UP4 {
    OperandValue ops[4];
    B3B0 ur2up_selA;
};
struct DecodedULOP32I6 {
    OperandValue ops[6];
    LOP lop;
    LOP_POP pop;
};
struct DecodedULOP32I5 {
    OperandValue ops[5];
    LOP lop;
};
struct DecodedUCLEA6 {
    OperandValue ops[6];
};
struct DecodedBRXU3 {
    OperandValue ops[3];
    COND cond;
    DEPTH depth;
    std::uint8_t rel;
};
struct DecodedJMXU3 {
    OperandValue ops[3];
    COND cond;
    DEPTH depth;
    std::uint8_t rel;
};
struct DecodedLDG8 {
    OperandValue ops[8];
    COP cop;
    COP2_EFL2_ENL2_ELL2 cop2;
    EONLY e;
    ONLY64 input_reg_sz_64_bit75_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    ONLY256 sz;
};
struct DecodedLDG7 {
    OperandValue ops[7];
    COP cop;
    RML2ONLY_ldg cop2;
    EONLY e;
    U32ONLY input_reg_sz_32_bit75_dist;
    ONLY64 input_reg_sz_64_bit75_dist;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    GPUONLY sco;
    STRONGONLY sem;
    SP2 sp2;
    ONLY256 sz;
};
struct DecodedSTG7 {
    OperandValue ops[7];
    COP cop;
    COP2 cop2;
    EONLY e;
    ONLY64 input_reg_sz_64_bit75_dist;
    ORDER order;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    ONLY256 sz;
};
struct DecodedSTG6 {
    OperandValue ops[6];
    COP cop;
    COP2 cop2;
    EONLY e;
    U32ONLY input_reg_sz_32_bit75_dist;
    ONLY64 input_reg_sz_64_bit75_dist;
    ORDER order;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    ONLY256 sz;
};
struct DecodedLD6 {
    OperandValue ops[6];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLD5 {
    OperandValue ops[5];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDG6 {
    OperandValue ops[6];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDL5 {
    OperandValue ops[5];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDL4 {
    OperandValue ops[4];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedLDS4 {
    OperandValue ops[4];
    STRIDE stride;
    LDSSIZE sz;
};
struct DecodedST5 {
    OperandValue ops[5];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedST4 {
    OperandValue ops[4];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTG5 {
    OperandValue ops[5];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_dist;
    ORDER order;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTG4 {
    OperandValue ops[4];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    ORDER order;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTL5 {
    OperandValue ops[5];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTL4 {
    OperandValue ops[4];
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedSTS4 {
    OperandValue ops[4];
    STRIDE stride;
    SZ_U8_S8_U16_S16_32_64_128 sz;
};
struct DecodedATOM8 {
    OperandValue ops[8];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_100_dist;
    AtomsOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    ATOMICINTSIZES sz;
};
struct DecodedREDS4 {
    OperandValue ops[4];
    REDSOP op;
    STRIDE stride;
    REDSSIZE sz;
};
struct DecodedREDG4 {
    OperandValue ops[4];
    COP cop;
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    RedOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    REDSSIZE sz;
};
struct DecodedREDG5 {
    OperandValue ops[5];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_dist;
    RedOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    REDSSIZE sz;
};
struct DecodedATOMG7 {
    OperandValue ops[7];
    COP cop;
    EONLY e;
    ONLY64 input_reg_sz_64_100_dist;
    ATOMICFPOPS op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SZ_0 sz;
};
struct DecodedLDGMC4 {
    OperandValue ops[4];
    EONLY e;
    LDGMC_FP_OP fpOp;
    LDGMC_FP_SIZES fpSz;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    INTOP_ADD_MIN_MAX_AND_OR_XOR intOp;
    REDSSIZE intSz;
    SYSONLY sco;
    STRONGONLY sem;
};
struct DecodedLDGMC5 {
    OperandValue ops[5];
    EONLY e;
    LDGMC_FP_OP fpOp;
    LDGMC_FP_SIZES fpSz;
    ONLY64 input_reg_sz_64_dist;
    INTOP_ADD_MIN_MAX_AND_OR_XOR intOp;
    REDSSIZE intSz;
    SYSONLY sco;
    STRONGONLY sem;
};
struct DecodedQSPC5 {
    OperandValue ops[5];
    E e;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    QUERY_SPACE space;
};
struct DecodedLDCU5 {
    OperandValue ops[5];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
};
struct DecodedLDCU4 {
    OperandValue ops[4];
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
};
struct DecodedARRIVES3 {
    OperandValue ops[3];
    LDGSTSBARONLY arrive;
    BAROP barop;
    CInteger_64 sz;
};
struct DecodedSYNCS3 {
    OperandValue ops[3];
    CCTLONLY cctl_mode;
    SYNCS_CCTL_OP cctlop;
};
struct DecodedUTMACCTL2 {
    OperandValue ops[2];
    COP_utmacctl cop;
    ONEONLY one;
};
struct DecodedUCGABARARV1 {
    OperandValue ops[1];
    SYNCALL syncall;
};
struct DecodedUCGABAR_ARV1 {
    OperandValue ops[1];
    SYNCALL syncall;
};
struct DecodedUSETSHMSZ1 {
    OperandValue ops[1];
    FLUSHONLY_usetshmsz flush;
};
struct DecodedULEPC3 {
    OperandValue ops[3];
    std::uint8_t rel;
};
struct DecodedTEX8 {
    OperandValue ops[8];
    AOFFI aoffi;
    BONLY b;
    COP cop;
    DC dc;
    DIV div;
    LODLC_tex lodlc;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    UAI uai;
};
struct DecodedTLD48 {
    OperandValue ops[8];
    BONLY b;
    TexComp comp;
    COP cop;
    DC dc;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    TOFF toff;
    UAI uai;
};
struct DecodedTLD8 {
    OperandValue ops[8];
    AOFFI aoffi;
    BONLY b;
    CL cl;
    COP cop;
    LODLC_tld lodlc;
    MS ms;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    UAI uai;
};
struct DecodedTXD8 {
    OperandValue ops[8];
    AOFFI aoffi;
    BONLY b;
    COP cop;
    LC lc;
    NODEP nodep;
    RM16 rm16;
    UAI uai;
};
struct DecodedFOOTPRINT6 {
    OperandValue ops[6];
    BONLY b;
    DIV div;
    LODCTRL lodctrl;
    LODLC lodlc;
    MODE_FOOTPRINT mode;
    NODEP nodep;
    SCRONLY scr;
};
struct DecodedLDGSTS6 {
    OperandValue ops[6];
    COP cop;
    EONLY_ldgsts e;
    FILLCTRL fc;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    LOC loc;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SIZE2 sz;
};
struct DecodedLDGSTS8 {
    OperandValue ops[8];
    COP cop;
    EONLY_ldgsts e;
    FILLCTRL fc;
    ONLY64 input_reg_sz_64_dist;
    LOC loc;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SIZE2 sz;
};
struct DecodedSUQUERY7 {
    OperandValue ops[7];
    BA ba;
    Dim1 dim;
    UAI uai;
};
struct DecodedSTAS4 {
    OperandValue ops[4];
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    SZ_32_64_128 sz;
};
struct DecodedREDAS4 {
    OperandValue ops[4];
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    REDSOP op;
    REDAS_SZ sz;
};
struct DecodedUCGABARWAIT1 {
    OperandValue ops[1];
};
struct DecodedUCGABAR_WAIT1 {
    OperandValue ops[1];
};
struct DecodedHMMA9 {
    OperandValue ops[9];
    FloatNo64 dstfmt;
    SIZE_1688_16816_16832 size;
    SPONLY sp;
    SPFORMAT spformat;
    SRCFMT srcfmt;
};
struct DecodedTLD49 {
    OperandValue ops[9];
    BONLY b;
    TexComp comp;
    COP cop;
    DC dc;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    TOFF toff;
    UAI uai;
};
struct DecodedTLD9 {
    OperandValue ops[9];
    AOFFI aoffi;
    BONLY b;
    CL cl;
    COP cop;
    LODLC_tld lodlc;
    MS ms;
    NODEP nodep;
    RM16 rm16;
    SCRONLY scr;
    UAI uai;
};
struct DecodedTMML7 {
    OperandValue ops[7];
    BONLY b;
    DIV div;
    LODOnly lod;
    NODEP nodep;
};
struct DecodedTXD9 {
    OperandValue ops[9];
    AOFFI aoffi;
    BONLY b;
    COP cop;
    LC lc;
    NODEP nodep;
    RM16 rm16;
    UAI uai;
};
struct DecodedTXQ6 {
    OperandValue ops[6];
    BONLY b;
    NODEP nodep;
};
struct DecodedFOOTPRINT7 {
    OperandValue ops[7];
    BONLY b;
    DIV div;
    LODCTRL lodctrl;
    LODLC lodlc;
    MODE_FOOTPRINT mode;
    NODEP nodep;
    SCRONLY scr;
};
struct DecodedSUATOM7 {
    OperandValue ops[7];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    AtomsOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SURFACESIZE sz;
    UAI uai;
};
struct DecodedSULD6 {
    OperandValue ops[6];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    PONLY p;
    PRIVATE private_;
    RGBA rgba;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    UAI uai;
};
struct DecodedSUST5 {
    OperandValue ops[5];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    PONLY p;
    PRIVATE private_;
    RGBA rgba;
    SCO sco;
    SEM sem;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    UAI uai;
};
struct DecodedSURED5 {
    OperandValue ops[5];
    BA ba;
    Clamp1 clamp;
    COP cop;
    DOnly d;
    Dim1 dim;
    RedOp op;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SURFACESIZE sz;
    UAI uai;
};
struct DecodedLDGSTS7 {
    OperandValue ops[7];
    COP cop;
    EONLY_ldgsts e;
    FILLCTRL fc;
    ONLY64 input_reg_sz_64_dist;
    LOC loc;
    PRIVATE private_;
    SCO sco;
    SEM sem;
    SP2 sp2;
    SIZE2 sz;
};

}  // namespace semu::shape
