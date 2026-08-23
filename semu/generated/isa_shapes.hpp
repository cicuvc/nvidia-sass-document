// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_isa.py --shapes
//
// Typed decoded-IR schema used by the decoder's main storage path.
#pragma once

#include <cstdint>
#include <cstring>
#include <optional>
#include <memory>
#include <semu/decoder/decoded_base.hpp>
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

// Derived decoded types: one per (mnemonic, operand-count); the
// polyvalent groups declared in shapes_poly_config.py emit one
// Decoded<Mnemonic><N>_<k> per kind-collapsed role signature, so
// every struct's ops[] positions are unambiguous.  Operands are
// positional role order; modifiers are typed enum members.
// Every operand is ONE NAMED OperandValue FIELD (no ops[] array):
// each position has a stable field name across the group's
// variants (kind-only families {Rb,Sb,URb} etc. collapse to a
// single field; the OperandValue kind carries register / uniform
// / immediate at runtime).
struct DecodedMOV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    ONLY64 size;
    SPILLONLY nonconformity;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    OperandValue PixMaskU04;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedP2R4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedP2R4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pr;
    OperandValue Ra;
    OperandValue b;
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedR2P3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedR2P3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue PR;
    OperandValue Ra;
    OperandValue b;
    B3B0 a_bsel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSEL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSEL4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSEL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSEL4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMNMX4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMNMX4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMNMX5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMNMX5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSETP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSETP3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    OperandValue Pr;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pr;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISETP3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD36>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD38 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD38>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue Pp;
    OperandValue Pq;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISCADD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISCADD5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue scaleU5;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    OperandValue scaleU5;
    HIONLY_lea hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue scaleU5;
    OperandValue Pp;
    HIONLY_lea hilo;
    XONLY X;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue scaleU5;
    HIONLY_lea hilo;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEA7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEA7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    OperandValue scaleU5;
    OperandValue Pp;
    HIONLY_lea hilo;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP37>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue imm8;
    OperandValue Pp;
    LUTOnly lut;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP36_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP36_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue Pp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP36_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP36_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue imm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP35 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP35>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIABS2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIABS2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPRMT4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPRMT4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    PMode pmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMNMX7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMNMX7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    OperandValue Pq;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMNMX6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMNMX6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHF4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHF4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    SDIR dir;
    CWMode cw;
    FMT_shf fmt;
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHL3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHL3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Sa;
    OperandValue Rb;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHL3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHL3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    CWMode cw;
    FMT_S32_U32 fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSGXT3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSGXT3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    CWMode cw;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMSK3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMSK3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue Pr;
    OperandValue uimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue UPr;
    OperandValue uimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue b;
    OperandValue Pr;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue b;
    OperandValue Rc;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP35_4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP35_4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue Pr;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue UPr;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue b;
    OperandValue Pr;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue b;
    OperandValue Rc;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP37_4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP37_4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMUL3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
    FTZ ftz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFHADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFHADD3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFHFMA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFHFMA4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    LOOnly wide;
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    WIDEONLY wide;
    FMT fmt;
    PSEUDO_OPCODE pseudo_opcode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Rc;
    OperandValue GetPseudoOpRIR;
    LOOnly wide;
    PSEUDO_OPCODE pseudo_opcode;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Sc;
    OperandValue GetPseudoOpRRI;
    LOOnly wide;
    PSEUDO_OPCODE pseudo_opcode;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue GetPseudoOpRRR;
    LOOnly wide;
    PSEUDO_OPCODE pseudo_opcode;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD5_4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD5_4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    OperandValue Pp;
    LOOnly wide;
    FMT fmt;
    XONLY X;
    PSEUDO_OPCODE pseudo_opcode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMAD6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMAD6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    WIDEONLY wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    MODE_2ALO_2AHI mode;
    SRCFMT16A SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDP4A4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDP4A4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
    SRCFMT_U8_S8 SrcAFmt;
    SRCFMT_U8_S8 SrcBFmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDMUL3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDMUL3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDADD3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDSETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDSETP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue c;
    OperandValue Pp;
    DSETP_FCMP test;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDSETP3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue c;
    DSETP_FCMP test;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDFMA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDFMA4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCLMAD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCLMAD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD23>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
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
struct DecodedHFMA25_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA25_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    OperandValue Rc;
    OFMT ofmt;
    FMZ fmz;
    SAT satrelu;
    ISWZA iswzA;
    ISWZA iswzC;
    MMAONLY MMA;
    NONE iswzA_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA25_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA25_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    OperandValue Pp;
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
    NONE iswzC_as_B_forced_H1_H0;
    NONE iswzB_as_C_forced_H1_H0;
    ISWZB iswzC_as_B;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA25_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA25_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Sc;
    OperandValue Sc1;
    OFMT ofmt;
    FMZ fmz;
    SAT satrelu;
    ISWZA iswzA;
    ISWZB iswzC_as_B;
    MMAONLY MMA;
    NONE iswzA_forced_H1_H0;
    NONE iswzC_as_B_forced_H1_H0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMUL23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMUL23>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    SAT sat;
    ISWZA iswzA;
    ISWZA iswzB;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET24_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET24_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
    OperandValue Pp;
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET24_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET24_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET23 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET23>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
    OFMT_F16_V2_BF16_V2 ofmt;
    BVal bval;
    FCMP cmp;
    FTZ ftz;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP25_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP25_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue c;
    OperandValue Pp;
    OFMT_F16_V2_BF16_V2 ofmt;
    FCMP cmp;
    H_AND h_and;
    FTZ ftz;
    Bop bop;
    ISWZA iswzA;
    ISWZA iswzB_as_C;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP25_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP25_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    OFMT_F16_V2_BF16_V2 ofmt;
    FCMP cmp;
    H_AND h_and;
    FTZ ftz;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSETP24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSETP24>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    ONLY64 size;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVIADD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVIADD3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    FMT_viadd fmt;
    ISAT isat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMMA5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue id;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
    SATONLY SAT;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedI2IP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedI2IP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Rc;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    MOVM_SZ sz;
    MOVM_MODE mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA7_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA7_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue id;
    SPONLY sp;
    SPFORMAT spformat;
    SIZE_1688_16816_16832 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA7_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA7_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue indexURd;
    OperandValue URd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue indexURc;
    OperandValue URc;
    OperandValue UPp;
    SIZE_1688_16816_1684 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    SIZE_1688_16816_1684 size;
    FloatNo64 dstfmt;
    SRCFMT srcfmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2FP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
struct DecodedF2FP3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_F16_BF16 dstfmt;
    F32ONLY_f2fp srcfmt;
    PACK_ABONLY merge;
    RNDMODE_RN_RZ rndMode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2FP3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2FP3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    OperandValue c;
    SATFINITEONLY satfinite;
    RELU relu;
    DSTFMT_E0M3_E2M1 dstfmt;
    SRCFMT_F16_BF16 srcfmt;
    UNPACK_B_MERGE_CONLY merge;
    RNONLY rndMode;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    SIZE_DMMA size;
    Round1 rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMNMX24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMNMX24>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    F32ONLY_i2fp dstfmt;
    SRCFMT_i2fp srcfmt;
    RND_RN_RZ rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVIMNMX4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVIMNMX4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue Pp;
    FMT_vimnmx fmt;
    RELU relu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQMMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQMMA5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue sparseId;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue URd;
    OperandValue Ra;
    ORONLY OR;
    NONCONFORMITY_FILL_BROADCAST nonconformity;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFLO3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFLO3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue b;
    FMT fmt;
    SH sh;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBREV2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBREV2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFCHK3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFCHK3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue b;
    ChkMode mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedF2F2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedF2F2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    MUFU_OP mufuop;
    FMT_F16_BF16 fmt;
    HSEL extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPOPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPOPC2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedB2R2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedB2R2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    BarmdRESULT mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedB2R2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedB2R2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue barname;
    BarmdBAR mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedB2R1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedB2R1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    BarmdWARP mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBAR2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBAR2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue b;
    OperandValue c;
    BarArv barmode;
    DEFER_BLOCKINGONLY defer_blocking;
    std::uint8_t subclass;  // generated semantic flags
    std::uint8_t barname;  // unsurfaced barrier-id field
};
struct DecodedBAR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBAR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue b;
    OperandValue c;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue barname;
    OperandValue Rb;
    MODE_BAR_WARP mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSETCTAID1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSETCTAID1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    CTA_DIM dim;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedALD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedALD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue srcAttr;
    OperandValue Ra;
    OperandValue Rb;
    AIO io;
    PHYSONLY p;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedALD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedALD5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue srcAttr;
    OperandValue a;
    OperandValue off;
    OperandValue Rb;
    AIO io;
    AInteger sz;
    PONLY p;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAST4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue srcAttr;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    PHYSONLY p;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAST5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAST5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue srcAttr;
    OperandValue a;
    OperandValue off;
    OperandValue Rb;
    OperandValue Rc;
    AInteger sz;
    PONLY p;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOUT3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOUT3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    CUTONLY type;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedOUT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedOUT1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    FINALONLY type;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue srcAttr;
    OperandValue attr;
    MODE ipaop;
    MSI_CENTER_CENTROID msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue srcAttr;
    OperandValue URa;
    OperandValue URa_offset;
    MODE ipaop;
    MSI_CENTER_CENTROID msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue srcAttr;
    OperandValue attr;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue a;
    OperandValue off;
    std::uint8_t abs;
    CALL_DEPTH depth;
    std::uint8_t rel;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCALL2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCALL2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Sa;
    std::uint8_t abs;
    CALL_DEPTH depth;
    std::uint8_t rel;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCALL2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCALL2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue a;
    std::uint8_t rel;
    CALL_DEPTH depth;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Ra;
    DIV__EXCLUSIVE div;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue sImm;
    COLLECTIVEONLY div;
    ALLOnly all;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedWARPSYNC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedWARPSYNC3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Ra;
    OperandValue sImm;
    COLLECTIVEONLY div;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEPC1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEPC1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRPCMOV2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRPCMOV2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue RpcN;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRPCMOV2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRPCMOV2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rpc;
    OperandValue b;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRPCMOV2_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRPCMOV2_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue RpcN;
    OperandValue b;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue cbu_state;
    ONLY32 sz;
    CLEAR clear;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue atexit_pc;
    OperandValue b;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue barReg;
    OperandValue Ba;
    ONLY32 sz;
    CLEARONLY clear;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue barReg;
    OperandValue cbu_state;
    ONLY32 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue cbu_state;
    OperandValue b;
    ONLY32 sz;
    PQUAD pquad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBMOV2_5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBMOV2_5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue cbu_state;
    OperandValue barReg;
    ONLY32 sz;
    PQUAD pquad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOTRAP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOTRAP2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue b;
    RAND rand;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOSLEEP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOSLEEP2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue b;
    RAND rand;
    OPTIONAL_WARP warp;
    SYNCS_MOD syncs;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTEX9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTEX9>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue query;
    OperandValue wmsk;
    BONLY b;
    NODEP nodep;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTS3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSHFL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSHFL5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue b;
    OperandValue c;
    Shflmd shflmd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue wr_early;
    EONLY e;
    ARRIVEONLY op;
    COP cop;
    ONLY64_atom sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue wr_early;
    E e;
    AtomsOp op;
    COP cop;
    ATOMICINTSIZES sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM7_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM7_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue wr_early;
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
struct DecodedATOM7_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM7_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue wr_early;
    E e;
    CAS cas;
    COP cop;
    ATOMCASSZ sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    AtomsSPIN spin;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    ARRIVEONLY op;
    ONLY64_atom sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    AtomsOp op;
    ATOMCASSZ sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDS3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    REDSOP op;
    REDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rc;
    CASTONLY cas;
    AtomsSPIN spin;
    ATOMCASSZ sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    AtomsOp op;
    ATOMCASSZ sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMS5_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMS5_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rc;
    CAS cas;
    ATOMCASSZ sz;
    STRIDE stride;
    AtomsSPIN spin;
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
    // Named operand fields (one per role position).
    OperandValue b;
    CCTLTOp cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSUATOM6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSUATOM6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue c;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Rb;
    OperandValue c;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    ALLOnly op;
    MATCH_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMATCH2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMATCH2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    ANYONLY op;
    MATCH_SZ sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
struct DecodedATOMG6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    E e;
    ATOMICFPOPS op;
    COP cop;
    SZ_0 sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_100_dist;
    ONLY64 input_reg_sz_64_100_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOMG6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOMG6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rc;
    E e;
    CAS cas;
    COP cop;
    ATOMCASSZ sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_offset;
    E e;
    QUERY_SPACE space;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    E e;
    QUERY_SPACE space;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    E e;
    QUERY_SPACE space;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    E e;
    QUERY_SPACE space;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedQSPC4_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedQSPC4_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSETLMEMBASE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSETLMEMBASE1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDUX2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDUX2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue URd;
    OperandValue Ra;
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
    // Named operand fields (one per role position).
    OperandValue ttuAddr;
    OperandValue ImmU16;
    OperandValue Rb;
    OperandValue Rc;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUCLOSE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUCLOSE1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTULD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTULD5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue ttuAddr;
    OperandValue ImmU16;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sc;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD24_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD24_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sc;
    F32ONLY_hadd2 ofmt;
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD24_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD24_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    OFMT_DIST ofmt;
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHADD2_32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHADD2_32I4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    FTZ ftz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA26_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA26_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    OperandValue Rc;
    OperandValue Pp;
    MMAONLY MMA;
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    RELUONLY satrelu;
    NONE iswzA_forced_H1_H0;
    NONE iswzC_forced_H1_H0;
    ISWZA iswzA;
    ISWZA iswzC;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA26_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA26_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Sc;
    OperandValue Sc1;
    OperandValue Pp;
    MMAONLY MMA;
    OFMT_F16_V2_BF16_V2 ofmt;
    FMZ_hfma2 fmz;
    RELUONLY satrelu;
    NONE iswzA_forced_H1_H0;
    NONE iswzC_as_B_forced_H1_H0;
    ISWZA iswzA;
    ISWZB iswzC_as_B;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHSET25 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHSET25>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue Sc;
    OperandValue Sc1;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue Rh;
    OperandValue URi;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue Rh;
    OperandValue URi;
    OperandValue sparseId;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue Rh;
    OperandValue URi;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue Rh;
    OperandValue URi;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue Rh;
    OperandValue URi;
    OperandValue sparseId;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV32I3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Sb;
    OperandValue PixMaskU04;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedP2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedP2R2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pr;
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCS2R2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCS2R2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue SRa;
    QInteger sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Pp;
    VoteOp voteop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sa;
    VOP vtgmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Sa;
    OperandValue Pp;
    VOP vtgmode;
    CCMP ccmp;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCSMTEST2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCSMTEST2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Sa;
    VOP vtgmode;
    CCMP ccmp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sa;
    VOP vtgmode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Sa;
    OperandValue Pp;
    VOP vtgmode;
    CCMP ccmp;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTE_VTG2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTE_VTG2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Sa;
    VOP vtgmode;
    CCMP ccmp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISCADD32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISCADD32I5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue scaleU5;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP32I5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Pp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLOP32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLOP32I4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP34_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP34_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue Pr;
    PLOP_OP_NOREG lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPLOP34_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPLOP34_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue UPr;
    PLOP_OP_NOREG lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPSETP5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPSETP5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue Pr;
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPSETP5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPSETP5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Pp;
    OperandValue Pq;
    OperandValue UPr;
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedPSETP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedPSETP3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Pp;
    OperandValue Pq;
    PSETP_BOP0 bop0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFMUL32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFMUL32I3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    FMZ_hfma2 fmz;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFSWZADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFSWZADD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rc;
    OperandValue npCtrl;
    FTZ ftz;
    Round1 rnd;
    DIV div;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFFMA32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFFMA32I4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Rc;
    FMZ_hfma2 fmz;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL32I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL32I3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIMUL32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIMUL32I4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Sb;
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
struct DecodedELECT3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedELECT3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue URd;
    OperandValue Pp;
    IGNORE_KILL ignoreKill;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedELECT3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedELECT3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue URd;
    OperandValue URa;
    IGNORE_KILL ignoreKill;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHFMA2_32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHFMA2_32I5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    OperandValue Rc;
    FMZ fmz;
    ISWZA iswzA;
    ISWZA iswzC;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMUL24 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMUL24>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    FMZ_hfma2 fmz;
    SAT sat;
    ISWZA iswzA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD32I4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD32I4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Sb;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIADD32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIADD32I5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Pp;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDSM3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDSM3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue Pv;
    OperandValue Ra;
    OperandValue Sb;
    OperandValue Sb1;
    OperandValue Pp;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    STSM_SZ sz;
    STSM_MODE mode;
    LDSM_NUM num;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIRTCOUNT2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIRTCOUNT2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue Sa;
    DEALLOCONLY_uvirtcount op;
    SMPOOLONLY pool;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIRTCOUNT2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIRTCOUNT2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    ONLY64_syncs size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedVOTEU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedVOTEU3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue URd;
    OperandValue UPu;
    OperandValue Pp;
    VoteOp voteop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP35 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP35>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPp;
    OperandValue UPq;
    OperandValue UPr;
    PLOP_OP_NOREG lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP36_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP36_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPp;
    OperandValue UPq;
    OperandValue UPr;
    OperandValue uimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP36_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP36_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPp;
    OperandValue URb;
    OperandValue UPr;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP36_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP36_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPp;
    OperandValue URb;
    OperandValue URc;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP36_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP36_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URa;
    OperandValue URb;
    OperandValue URc;
    OperandValue uimm8;
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP38_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP38_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue UPp;
    OperandValue UPq;
    OperandValue UPr;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP38_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP38_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue UPp;
    OperandValue URb;
    OperandValue UPr;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP38_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP38_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue UPp;
    OperandValue URb;
    OperandValue URc;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPLOP38_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPLOP38_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue URb;
    OperandValue URc;
    OperandValue uimm8;
    OperandValue vimm8;
    LUTOnly lut;
    SIGNONLY sign_a;
    SIGNONLY sign_b;
    SIGNONLY sign_c;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPSETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPSETP6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue UPp;
    OperandValue UPq;
    OperandValue UPr;
    PSETP_BOP0 bop0;
    PSETP_BOP0 bop1;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPSETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPSETP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPp;
    OperandValue UPq;
    PSETP_BOP0 bop0;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCS2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCS2UR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue SRa;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue SRa;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue sbidx;
    OperandValue URb;
    OperandValue scoreboard_list;
    LEONLY le;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue sbidx;
    OperandValue cnt;
    OperandValue scoreboard_list;
    LEONLY le;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedDEPBAR1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedDEPBAR1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue scoreboard_list;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedAL2P3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedAL2P3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    AIO io;
    AInteger sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISBERD3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISBERD3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    PIXLD_MODE mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedISBEWR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedISBEWR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue barReg;
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBREAK2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBREAK2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue barReg;
    RELIABLEONLY reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBSSY3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBSSY3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue barReg;
    OperandValue Sa;
    std::uint8_t rel;
    RELIABILITY_RELIABLE_RECONVERGENT reliability;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedYIELD1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedYIELD1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRA2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRA2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue sImm;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    ALLOnly all;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRX3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRX3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Ra;
    OperandValue Ra_offset;
    DEPTH depth;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMP2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMP2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Sa;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue Ra;
    OperandValue Ra_offset;
    DEPTH depth;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedEXIT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedEXIT1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    EXIT_MODE mode;
    NO_ATEXIT no_atexit;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLEPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLEPC2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue sImm58;
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
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue a;
    OperandValue off;
    ABSONLY_ret addr;
    RET_DEPTH depth;
    std::uint8_t rel_imm;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedRET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedRET2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue a;
    RET_ADDR addr;
    RET_DEPTH depth;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIDE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIDE1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sb;
    IDEAction action;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedKILL1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedKILL1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBPT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBPT1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sb;
    BPT_TRAP_INT bpt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedNANOSLEEP1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedNANOSLEEP1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    CLEARONLY clear;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDS3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_offset;
    LDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDG3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    E e;
    RedOp op;
    COP cop;
    REDSSIZE sz;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URb;
    E e;
    Cache cache;
    COP_PF1_WB_IV_RS_PML2_DML2 cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue a;
    OperandValue off;
    E e;
    Cache cache;
    COP_PF1_WB_IV_RS_PML2_DML2 cop;
    LDCONLY ldc;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_URb;
    E e;
    Cache cache;
    PF2ONLY cop;
    QFAULTONLY qfault;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_offset;
    E e;
    Cache cache;
    PF2ONLY cop;
    QFAULTONLY qfault;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL3_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL3_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue sector_count;
    E e;
    Cache cache;
    RML2ONLY cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL3_3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL3_3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue sector_count;
    E e;
    Cache cache;
    RML2ONLY cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLL0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLL0>(*this);
    }
    COP_IVALL_WBALL cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLL2_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLL2_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URb;
    COP_PF1_PF2_WB_IV_RS cop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTLL2_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTLL2_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue c;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Rb;
    OperandValue c;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue queryType;
    OperandValue c;
    OperandValue URe;
    BA ba;
    Dim1 dim;
    UAI uai;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACMDFLUSH1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACMDFLUSH1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACCTL1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACCTL1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    IVALLONLY_utmacctl ivall;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedS2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedS2UR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue SRa;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTTUMACROFUSE1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTTUMACROFUSE1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sb;
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
struct DecodedCCTL4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sa;
    OperandValue Sa_bank;
    OperandValue a;
    OperandValue off;
    CONLY cache;
    LDCONLY ldc;
    IVONLY cop;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedCCTL4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedCCTL4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Sa;
    OperandValue URa;
    OperandValue b;
    OperandValue Sa_offset;
    CONLY cache;
    LDCONLY ldc;
    IVONLY cop;
    SHALLOWONLY depth;
    LDCUONLY ldcu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDC5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDC5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Sa;
    OperandValue Sa_bank;
    OperandValue Ra;
    OperandValue Ra_offset;
    SZ_U8_S8_U16_S16_32_64 sz;
    AdMode ad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDC5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDC5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Sa;
    OperandValue URa;
    OperandValue Rb;
    OperandValue Sa_offset;
    SZ_U8_S8_U16_S16_32_64 sz;
    AdMode ad;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIADD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    FMT_viadd fmt;
    ISAT isat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUVIMNMX5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUVIMNMX5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    FMT_vimnmx fmt;
    RELU relu;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIABS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIABS3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2I3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2I3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    DSTFMT_i2i dstfmt;
    S32ONLY_i2i srcfmt;
    SATONLY SAT;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUI2IP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUI2IP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    FTZ ftz;
    NAN nan;
    XORSIGN xorsign;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFMNMX6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFMNMX6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSET5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSET5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    BFONLY bf;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSETP6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    FCMP fcomp;
    FTZ ftz;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFSETP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFSETP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    FCMP fcomp;
    FTZ ftz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFADD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue c;
    FTZ ftz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFHADD4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFHADD4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    FMZ_hfma2 fmz;
    Round1 rnd;
    SAT sat;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUFHFMA5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUFHFMA5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue URb;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    F32ONLY_i2fp dstfmt;
    SRCFMT_i2fp srcfmt;
    RND_RN_RZ rnd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMNMX8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMNMX8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    OperandValue UPq;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMNMX7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMNMX7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSEL5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSEL5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    ONLY64 size;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    Bop bop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    OperandValue UPr;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUISETP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUISETP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue UPr;
    ICmpAll icmp;
    FMT_64_DIST fmt;
    EXONLY ex;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD37 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD37>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD39 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD39>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue UPp;
    OperandValue UPq;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA7_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA7_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    OperandValue scaleU5;
    HIONLY_lea hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA7_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA7_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue scaleU5;
    OperandValue UPp;
    HIONLY_lea hilo;
    XONLY X;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue scaleU5;
    HIONLY_lea hilo;
    SX32ONLY sx32;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEA8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEA8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    OperandValue scaleU5;
    OperandValue UPp;
    HIONLY_lea hilo;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue UPp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP38 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP38>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue imm8;
    OperandValue UPp;
    LUTOnly lut;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP37_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP37_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue UPp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP37_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP37_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue imm8;
    LUTOnly lut;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP36 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP36>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPRMT5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPRMT5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    IDXOnly idx;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD3_647 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD3_647>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIADD3_649 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIADD3_649>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue UPv;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue UPp;
    OperandValue UPq;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHF5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHF5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    SDIR dir;
    CWMode cw;
    FMT_shf fmt;
    HILO hilo;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHL4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHL4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue Sa;
    OperandValue URb;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHL4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHL4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSHR4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSHR4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    CWMode cw;
    FMT_S32_U32 fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSGXT4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSGXT4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    CWMode cw;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBMSK4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBMSK4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    CWMode cw;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    LOOnly wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    WIDEONLY wide;
    FMT fmt;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
    OperandValue UPp;
    LOOnly wide;
    FMT fmt;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUIMAD7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUIMAD7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue URc;
    OperandValue UPp;
    WIDEONLY wide;
    FMT fmt;
    XONLY X;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    SRCFMT_E5M2_E4M3 srcfmt;
    UNPACK_BONLY merge;
    RNONLY rndMode;
    EXTRACT extract;
    SATFINITE satfinite;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    Float32 srcfmt;
    PACK_ABONLY merge;
    RNDMODE_RN_RZ rndMode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    OperandValue c;
    SATFINITE satfinite;
    RELU relu;
    DSTFMT_uf2fp dstfmt;
    F16ONLY_uf2fp srcfmt;
    UNPACK_B_MERGE_CONLY merge;
    RNONLY rndMode;
    EXTRACT extract;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUF2FP5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUF2FP5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue b;
    OperandValue c;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue b;
    FMT fmt;
    SH sh;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBREV3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBREV3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUPOPC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUPOPC3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd2;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sa_offset;
    OperandValue word_mask;
    OperandValue UPp;
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue Sa;
    OperandValue Sa_bank;
    OperandValue URa;
    OperandValue Sa_offset;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue Sa;
    OperandValue URa;
    OperandValue URb;
    OperandValue Sa_offset;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU6_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU6_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd2;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sa_offset;
    OperandValue word_mask;
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDTRAM4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDTRAM4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue srcAttr;
    OperandValue URa;
    OperandValue URa_offset;
    MODE_ldtram mode;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue URa_offset;
    OperandValue URb;
    OperandValue URc;
    CASONLY emuop;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMASTG5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMASTG5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue desc;
    OperandValue URe;
    TENSORDIM dim;
    MODE_utmastg mode;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMAREDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMAREDG3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue URc;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
    OperandValue URc;
    L2ONLY cache;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUBLKPF5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUBLKPF5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
    OperandValue URc;
    OperandValue desc;
    OperandValue URe;
    L2ONLY cache;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARSET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARSET2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_SET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_SET2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETMAXREG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETMAXREG3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue b;
    TRY_ALLOCONLY mode;
    CTAPOOLONLY pool;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETMAXREG2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETMAXREG2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue b;
    DEALLOCONLY mode;
    CTAPOOLONLY pool;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETSHMSZ2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETSHMSZ2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUGETNEXTWORKID3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUGETNEXTWORKID3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
    OperandValue URb;
    UGETNEXTWORKID_CAST cast;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUMEMSETS5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUMEMSETS5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
    OperandValue URa_offset;
    OperandValue URb;
    OperandValue URc;
    ONLY64 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEPC2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEPC2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue indexURb;
    OperandValue URb;
    OperandValue PixMaskU04;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedMOV4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedMOV4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue indexURd;
    OperandValue URd;
    OperandValue b;
    OperandValue PixMaskU04;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedIPA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedIPA6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Pu;
    OperandValue srcAttr;
    OperandValue URa;
    OperandValue URa_offset;
    OperandValue b;
    MODE ipaop;
    OFFSETONLY msi;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRA3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRA3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue UPq;
    OperandValue sImm;
    DEPTH depth;
    UONLY cond;
    USEL usel;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRA3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRA3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue URb;
    OperandValue sImm;
    DEPTH depth;
    COND_DIV_CONV cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMP3_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMP3_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue UPq;
    OperandValue Sa;
    DEPTH depth;
    UONLY cond;
    USEL usel;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMP3_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMP3_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue URb;
    OperandValue Sa;
    DEPTH depth;
    COND_DIV_CONV_jmp cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS5_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS5_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    PHASECHKONLY op;
    TRANS64ONLY bartype;
    WAIT wait;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS5_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS5_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    ARRIVEONLY_syncs op;
    TRANS64ONLY bartype;
    RETVAL_OLDSTATE_TMASK_RED retval;
    OPTOUT optout;
    PARAMTYPE paramtype;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS5_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS5_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue URa_offset;
    OperandValue URb;
    EXCHONLY emuop;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU8_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU8_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd2;
    OperandValue URd;
    OperandValue Sa;
    OperandValue Sa_bank;
    OperandValue URa;
    OperandValue Sa_offset;
    OperandValue word_mask;
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU8_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU8_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd2;
    OperandValue URd;
    OperandValue Sa;
    OperandValue URa;
    OperandValue URb;
    OperandValue Sa_offset;
    OperandValue word_mask;
    ONLY256_ldcu sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS4_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS4_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    LDONLY cctl_mode;
    ONLY64_syncs sz;
    WATCH watch;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS4_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS4_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue URa_offset;
    LDONLY_syncs emuop;
    ONLY64_syncs sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS4_2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS4_2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    TCNTONLY op;
    TRANS64ONLY bartype;
    BarRED retval;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMALDG3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMALDG3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URb;
    OperandValue URa;
    OperandValue desc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_GET2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_GET2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedELECT2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedELECT2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue URd;
    IGNORE_KILL ignoreKill;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDSM4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDSM4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    STSM_SZ sz;
    STSM_MODE mode;
    LDSM_NUM num;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUP2UR5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUP2UR5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPR;
    OperandValue URa;
    OperandValue b;
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUP2UR3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUP2UR3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPR;
    B3B0 insert;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUR2UP4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUR2UP4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPR;
    OperandValue URa;
    OperandValue b;
    B3B0 ur2up_selA;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP32I6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP32I6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sb;
    OperandValue UPp;
    LOP lop;
    LOP_POP pop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULOP32I5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULOP32I5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue UPu;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sb;
    LOP lop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCLEA6 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCLEA6>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue UPu;
    OperandValue URa;
    OperandValue b;
    OperandValue constSizeU05;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedBRXU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedBRXU3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue URa;
    OperandValue UR_offset;
    DEPTH depth;
    COND cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedJMXU3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedJMXU3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pp;
    OperandValue URa;
    OperandValue UR_offset;
    DEPTH depth;
    COND cond;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDG8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URb;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue word_mask;
    OperandValue Pnz;
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
struct DecodedLDG7_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG7_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URb;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
struct DecodedLDG7_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDG7_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    OperandValue word_mask;
    OperandValue Pnz;
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
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTG7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTG7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rb2;
    OperandValue word_mask;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue Rb2;
    OperandValue word_mask;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URb;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URb;
    OperandValue Ra;
    OperandValue Ra_offset;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDL4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDS4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
    LDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedST5 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedST5>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTL4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTL4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    COP cop;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTS4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedATOM8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedATOM8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
    OperandValue wr_early;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    REDSOP op;
    REDSSIZE sz;
    STRIDE stride;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDG4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDG4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Rd;
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Ra_URb;
    OperandValue Ra_offset;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sa_offset;
    OperandValue UPp;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDCU4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDCU4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue URa;
    OperandValue Sa_offset;
    SZ_U8_S8_U16_S16_32_64_128 sz;
    TEXUNPACK texunpack;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedARRIVES3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedARRIVES3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    LDGSTSBARONLY arrive;
    CInteger_64 sz;
    BAROP barop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSYNCS3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSYNCS3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    CCTLONLY cctl_mode;
    SYNCS_CCTL_OP cctlop;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUTMACCTL2 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUTMACCTL2>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URa;
    COP_utmacctl cop;
    ONEONLY one;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABARARV1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABARARV1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    SYNCALL syncall;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_ARV1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_ARV1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    SYNCALL syncall;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUSETSHMSZ1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUSETSHMSZ1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    FLUSHONLY_usetshmsz flush;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedULEPC3 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedULEPC3>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    OperandValue URd;
    OperandValue sImm58;
    std::uint8_t rel;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedTEX8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedTEX8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue paramA;
    BONLY b;
    MODE_FOOTPRINT mode;
    LODCTRL lodctrl;
    LODLC lodlc;
    DIV div;
    NODEP nodep;
    SCRONLY scr;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGSTS6_0 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS6_0>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rb;
    OperandValue Rb_URc;
    OperandValue Rb_offset;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
struct DecodedLDGSTS6_1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS6_1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rb;
    OperandValue Rb_offset;
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Pnz;
    EONLY_ldgsts e;
    LOC loc;
    COP cop;
    SP2 sp2;
    SIZE2 sz;
    FILLCTRL fc;
    SEM sem;
    SCO sco;
    PRIVATE private_;
    U32ONLY input_reg_sz_32_dist;
    ONLY64 input_reg_sz_64_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedLDGSTS8 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedLDGSTS8>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Rb;
    OperandValue Rb_URc;
    OperandValue Rb_offset;
    OperandValue memoryDescriptor;
    OperandValue Ra_URd;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue queryType;
    OperandValue Rc;
    OperandValue URc;
    OperandValue URe;
    BA ba;
    Dim1 dim;
    UAI uai;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedSTAS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedSTAS4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
    SZ_32_64_128 sz;
    ONLY64 input_reg_sz_64_dist;
    U32ONLY input_reg_sz_32_dist;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedREDAS4 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedREDAS4>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Ra_URc;
    OperandValue Ra_offset;
    OperandValue Rb;
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
    // Named operand fields (one per role position).
    OperandValue UPg;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedUCGABAR_WAIT1 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedUCGABAR_WAIT1>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue UPg;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedHMMA9 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedHMMA9>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue indexURd;
    OperandValue URd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue indexURc;
    OperandValue URc;
    OperandValue UPp;
    OperandValue Re;
    OperandValue id;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue URe;
    OperandValue paramA;
    OperandValue wmsk;
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
    // Named operand fields (one per role position).
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue query;
    OperandValue URc;
    OperandValue wmsk;
    NODEP nodep;
    BONLY b;
    std::uint8_t subclass;  // generated semantic flags
};
struct DecodedFOOTPRINT7 : DecodedInstruction {
    std::unique_ptr<DecodedInstruction> clone() const override {
        return std::make_unique<DecodedFOOTPRINT7>(*this);
    }
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd2;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue URc;
    OperandValue paramA;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue URc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Pu;
    OperandValue Rd;
    OperandValue Ra;
    OperandValue Rc;
    OperandValue URc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue URc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Ra;
    OperandValue Rb;
    OperandValue Rc;
    OperandValue URc;
    OperandValue URe;
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
    // Named operand fields (one per role position).
    OperandValue Rb;
    OperandValue Rb_offset;
    OperandValue memoryDescriptor;
    OperandValue Ra_URc;
    OperandValue Ra;
    OperandValue Ra_offset;
    OperandValue Pnz;
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

}  // namespace semu::shape

// The per-variant operand-role manifest (ShapeManifest /
// kShapeManifests / kShapeRoles_*) lives in isa_manifest.hpp — a
// decode/CLI/test bridge header NOT included by the interpreter,
// which reads n_ops from DecodedInstruction::n_ops (set at fill
// time) instead.
