// Generated file -- do not edit.  Regenerate with:
//   python3 semu/tools/gen_isa.py
#pragma once

#include <cstdint>
#include <optional>
#include <string_view>

namespace semu { struct Word128; }  // forward decl (word.hpp)

namespace semu::isa {

// Instruction-category enums (1-based; kUnknown=0 reserved).
// DecodedInstruction spans the same enums so execution backends can
// dispatch on cheap integral values instead of strings.
enum class Mnemonic : std::uint16_t {
    kUnknown = 0,
    kACQBULK = 1,
    kACQSHMINIT = 2,
    kAL2P = 3,
    kALD = 4,
    kARRIVES = 5,
    kAST = 6,
    kATOM = 7,
    kATOMG = 8,
    kATOMS = 9,
    kB2R = 10,
    kBAR = 11,
    kBMOV = 12,
    kBMSK = 13,
    kBPT = 14,
    kBRA = 15,
    kBREAK = 16,
    kBREV = 17,
    kBRX = 18,
    kBRXU = 19,
    kBSSY = 20,
    kBSYNC = 21,
    kCALL = 22,
    kCCTL = 23,
    kCCTLL = 24,
    kCCTLT = 25,
    kCGAERRBAR = 26,
    kCLMAD = 27,
    kCS2R = 28,
    kCS2UR = 29,
    kCSMTEST = 30,
    kDADD = 31,
    kDEPBAR = 32,
    kDFMA = 33,
    kDMMA = 34,
    kDMUL = 35,
    kDSETP = 36,
    kELECT = 37,
    kENDCOLLECTIVE = 38,
    kERRBAR = 39,
    kEXIT = 40,
    kF2F = 41,
    kF2FP = 42,
    kF2I = 43,
    kF2IP = 44,
    kFADD = 45,
    kFADD32I = 46,
    kFCHK = 47,
    kFENCE = 48,
    kFFMA = 49,
    kFFMA32I = 50,
    kFHADD = 51,
    kFHFMA = 52,
    kFLO = 53,
    kFMNMX = 54,
    kFMUL = 55,
    kFMUL32I = 56,
    kFOOTPRINT = 57,
    kFRND = 58,
    kFSEL = 59,
    kFSET = 60,
    kFSETP = 61,
    kFSWZADD = 62,
    kGETLMEMBASE = 63,
    kHADD2 = 64,
    kHADD2_32I = 65,
    kHFMA2 = 66,
    kHFMA2_32I = 67,
    kHMMA = 68,
    kHMNMX2 = 69,
    kHMUL2 = 70,
    kHMUL2_32I = 71,
    kHSET2 = 72,
    kHSETP2 = 73,
    kI2F = 74,
    kI2FP = 75,
    kI2I = 76,
    kI2IP = 77,
    kIABS = 78,
    kIADD = 79,
    kIADD3 = 80,
    kIADD32I = 81,
    kIDE = 82,
    kIDP = 83,
    kIDP4A = 84,
    kIMAD = 85,
    kIMMA = 86,
    kIMNMX = 87,
    kIMUL = 88,
    kIMUL32I = 89,
    kIPA = 90,
    kISBERD = 91,
    kISBEWR = 92,
    kISCADD = 93,
    kISCADD32I = 94,
    kISETP = 95,
    kJMP = 96,
    kJMX = 97,
    kJMXU = 98,
    kKILL = 99,
    kLD = 100,
    kLDC = 101,
    kLDCU = 102,
    kLDG = 103,
    kLDGDEPBAR = 104,
    kLDGMC = 105,
    kLDGSTS = 106,
    kLDL = 107,
    kLDS = 108,
    kLDSM = 109,
    kLDTRAM = 110,
    kLEA = 111,
    kLEPC = 112,
    kLOP = 113,
    kLOP3 = 114,
    kLOP32I = 115,
    kMATCH = 116,
    kMEMBAR = 117,
    kMOV = 118,
    kMOV32I = 119,
    kMOV64IUR = 120,
    kMOVM = 121,
    kMUFU = 122,
    kMXQMMA = 123,
    kNANOSLEEP = 124,
    kNANOTRAP = 125,
    kNOP = 126,
    kOMMA = 127,
    kOUT = 128,
    kP2R = 129,
    kPIXLD = 130,
    kPLOP3 = 131,
    kPMTRIG = 132,
    kPOPC = 133,
    kPREEXIT = 134,
    kPRMT = 135,
    kPSETP = 136,
    kQMMA = 137,
    kQSPC = 138,
    kR2B = 139,
    kR2P = 140,
    kR2UR = 141,
    kREDAS = 142,
    kREDG = 143,
    kREDS = 144,
    kREDUX = 145,
    kRET = 146,
    kRPCMOV = 147,
    kRTT = 148,
    kS2R = 149,
    kS2UR = 150,
    kSEL = 151,
    kSETCTAID = 152,
    kSETLMEMBASE = 153,
    kSGXT = 154,
    kSHF = 155,
    kSHFL = 156,
    kSHL = 157,
    kSHR = 158,
    kST = 159,
    kSTAS = 160,
    kSTG = 161,
    kSTL = 162,
    kSTS = 163,
    kSTSM = 164,
    kSUATOM = 165,
    kSULD = 166,
    kSUQUERY = 167,
    kSURED = 168,
    kSUST = 169,
    kSYNCS = 170,
    kTEX = 171,
    kTLD = 172,
    kTLD4 = 173,
    kTMML = 174,
    kTTUCCTL = 175,
    kTTUCLOSE = 176,
    kTTUGO = 177,
    kTTULD = 178,
    kTTUMACROFUSE = 179,
    kTTUOPEN = 180,
    kTTUST = 181,
    kTXD = 182,
    kTXQ = 183,
    kUBLKCP = 184,
    kUBLKPF = 185,
    kUBLKRED = 186,
    kUBMSK = 187,
    kUBREV = 188,
    kUCGABARARV = 189,
    kUCGABARGET = 190,
    kUCGABARSET = 191,
    kUCGABARWAIT = 192,
    kUCGABAR_ARV = 193,
    kUCGABAR_GET = 194,
    kUCGABAR_SET = 195,
    kUCGABAR_WAIT = 196,
    kUCLEA = 197,
    kUF2F = 198,
    kUF2FP = 199,
    kUF2I = 200,
    kUF2IP = 201,
    kUFADD = 202,
    kUFFMA = 203,
    kUFHADD = 204,
    kUFHFMA = 205,
    kUFLO = 206,
    kUFMNMX = 207,
    kUFMUL = 208,
    kUFRND = 209,
    kUFSEL = 210,
    kUFSET = 211,
    kUFSETP = 212,
    kUGETNEXTWORKID = 213,
    kUI2F = 214,
    kUI2FP = 215,
    kUI2I = 216,
    kUI2IP = 217,
    kUIABS = 218,
    kUIADD3 = 219,
    kUIADD3_64 = 220,
    kUIMAD = 221,
    kUIMNMX = 222,
    kUISETP = 223,
    kULEA = 224,
    kULEPC = 225,
    kULOP = 226,
    kULOP3 = 227,
    kULOP32I = 228,
    kUMEMSETS = 229,
    kUMOV = 230,
    kUP2UR = 231,
    kUPLOP3 = 232,
    kUPOPC = 233,
    kUPRMT = 234,
    kUPSETP = 235,
    kUR2UP = 236,
    kUSEL = 237,
    kUSETMAXREG = 238,
    kUSETSHMSZ = 239,
    kUSGXT = 240,
    kUSHF = 241,
    kUSHL = 242,
    kUSHR = 243,
    kUTMACCTL = 244,
    kUTMACMDFLUSH = 245,
    kUTMALDG = 246,
    kUTMAPF = 247,
    kUTMAREDG = 248,
    kUTMASTG = 249,
    kUVIADD = 250,
    kUVIMNMX = 251,
    kUVIRTCOUNT = 252,
    kVIADD = 253,
    kVIMNMX = 254,
    kVOTE = 255,
    kVOTEU = 256,
    kVOTE_VTG = 257,
    kWARPSYNC = 258,
    kYIELD = 259,
};

enum class VariantClass : std::uint16_t {
    kUnknown = 0,
    kacqbulk_ = 1,
    kacqshminit_ = 2,
    kal2p__RaNonRZ = 3,
    kal2p__RaRZ = 4,
    kald_PHYS_ = 5,
    kald_UR__LOGICAL_URa_default = 6,
    kald_UR__PATCH_URa_P_RbRZ = 7,
    kald__LOGICAL_RaRZ_default = 8,
    kald__PATCH_RaNonRZOffset_P_RbRZ = 9,
    kald__PATCH_RaRZ_P_RbRZ = 10,
    karrives_ = 11,
    kast_PHYS_ = 12,
    kast_UR__LOGICAL_URa = 13,
    kast_UR__PATCH_RaRZ_URa = 14,
    kast__LOGICAL_RaRZ = 15,
    kast__PATCH_RaNonRZOffset = 16,
    kast__PATCH_RaRZ = 17,
    katom_arrive__Ra32_arrive = 18,
    katom_arrive__Ra32_popcinc = 19,
    katom_arrive__Ra64_arrive = 20,
    katom_arrive__Ra64_popcinc = 21,
    katom_arrive__RaRZ_arrive = 22,
    katom_arrive__RaRZ_popcinc = 23,
    katom_cas__RaNonRZ_CAS = 24,
    katom_cas__RaNonRZ_CAST = 25,
    katom_cas__RaRZ_CAS = 26,
    katom_cas__RaRZ_CAST = 27,
    katom_fp__RaNonRZ = 28,
    katom_fp__RaRZ = 29,
    katom_fp_uniform__Ra32 = 30,
    katom_fp_uniform__Ra64 = 31,
    katom_fp_uniform__RaRZ = 32,
    katom_fp_uniform__memdesc = 33,
    katom_int__RaNonRZ = 34,
    katom_int__RaRZ = 35,
    katom_int_uniform__Ra32 = 36,
    katom_int_uniform__Ra64 = 37,
    katom_int_uniform__RaRZ = 38,
    katom_int_uniform__memdesc = 39,
    katomg_cas__RaNonRZ = 40,
    katomg_cas__RaRZ = 41,
    katomg_fp__RaNonRZ = 42,
    katomg_fp__RaRZ = 43,
    katomg_fp_uniform__Ra32 = 44,
    katomg_fp_uniform__Ra64 = 45,
    katomg_fp_uniform__RaRZ = 46,
    katomg_fp_uniform__memdesc = 47,
    katomg_int__RaNonRZ = 48,
    katomg_int__RaRZ = 49,
    katomg_int_uniform__Ra32 = 50,
    katomg_int_uniform__Ra64 = 51,
    katomg_int_uniform__RaRZ = 52,
    katomg_int_uniform__memdesc = 53,
    katoms__RaNonRZ = 54,
    katoms__RaRZ = 55,
    katoms_arrive__arrive = 56,
    katoms_arrive__popcinc = 57,
    katoms_cas__RaNonRZ = 58,
    katoms_cas__RaRZ = 59,
    katoms_cast_destPu__RaNonRZ = 60,
    katoms_cast_destPu__RaRZ = 61,
    katoms_cast_destRd__RaNonRZ = 62,
    katoms_cast_destRd__RaRZ = 63,
    katoms_reds__RaNonRZ = 64,
    katoms_reds__RaRZ = 65,
    katoms_reds_uniform_ = 66,
    katoms_uniform_ = 67,
    kb2r__BAR = 68,
    kb2r__RESULT = 69,
    kb2r__WARP = 70,
    kbar__ARV_II_II = 71,
    kbar__ARV_IR_IR = 72,
    kbar__ARV_RI_RI = 73,
    kbar__ARV_RR_RR = 74,
    kbar__RED_II_optionalCount_II = 75,
    kbar__RED_IR_optionalCount_IR = 76,
    kbar__RED_RI_optionalCount_RI = 77,
    kbar__RED_RR_RR = 78,
    kbar__RED_dfrBlk_II_optionalCount_II = 79,
    kbar__RED_dfrBlk_IR_optionalCount_IR = 80,
    kbar__RED_dfrBlk_RI_optionalCount_RI = 81,
    kbar__RED_dfrBlk_RR_RR = 82,
    kbar__SCAN_II_II = 83,
    kbar__SCAN_IR_IR = 84,
    kbar__SCAN_RI_RI = 85,
    kbar__SCAN_RR_RR = 86,
    kbar__SYNCALL_dfrBlk_noSrc_II = 87,
    kbar__SYNCALL_noSrc_II = 88,
    kbar__SYNC_II_optionalCount_II = 89,
    kbar__SYNC_IR_optionalCount_IR = 90,
    kbar__SYNC_RI_optionalCount_RI = 91,
    kbar__SYNC_RR_RR = 92,
    kbar__SYNC_dfrBlk_II_optionalCount_II = 93,
    kbar__SYNC_dfrBlk_IR_optionalCount_IR = 94,
    kbar__SYNC_dfrBlk_RI_optionalCount_RI = 95,
    kbar__SYNC_dfrBlk_RR_RR = 96,
    kbmov_clear__Rd = 97,
    kbmov_clear_barrier_ = 98,
    kbmov_clear_bd__Bd = 99,
    kbmov_dst64__I = 100,
    kbmov_dst64__R = 101,
    kbmov_dst64__UR = 102,
    kbmov_pquad__RIR = 103,
    kbmov_pquad__RRR = 104,
    kbmov_pquad__RUR = 105,
    kbmov_pquad_bar__RBR = 106,
    kbmsk__RRR_RRR = 107,
    kbmsk__RUR_RUR = 108,
    kbmsk__RuIR_RIR = 109,
    kbpt__noDRAIN = 110,
    kbpt__onlyDRAIN = 111,
    kbra__CONV_DIV = 112,
    kbra__U = 113,
    kbra_rel__CONV_DIV = 114,
    kbra_rel__U = 115,
    kbra_uniform_ = 116,
    kbra_uniform_pred_ = 117,
    kbra_uniform_pred_rel_ = 118,
    kbra_uniform_rel_ = 119,
    kbreak_inst_ = 120,
    kbreak_reliability_ = 121,
    kbrev__RRR_RRR = 122,
    kbrev__RUR_RUR = 123,
    kbrev__RuIR_RIR = 124,
    kbrx_ = 125,
    kbrx_rel_ = 126,
    kbrxu_ = 127,
    kbrxu_rel_ = 128,
    kbssy_ = 129,
    kbssy_rel_ = 130,
    kbssy_reliability_ = 131,
    kbssy_reliability_rel_ = 132,
    kbsync_ = 133,
    kbsync_reliability_ = 134,
    kcall_abs__RIR = 135,
    kcall_abs__RRR = 136,
    kcall_abs__URIR = 137,
    kcall_rel__RIR = 138,
    kcall_rel__RRR = 139,
    kcall_rel__URIR = 140,
    kcall_rel_imm__RIR = 141,
    kcall_rel_imm__RRR = 142,
    kcall_rel_imm__URIR = 143,
    kcall_rel_reg__RRR = 144,
    kcall_rel_reg__URIR = 145,
    kcctl__IVALL_WBALL_D_U_noSrc = 146,
    kcctl__sImmOffset = 147,
    kcctl__sImmOffset_pf2 = 148,
    kcctl__sImmOffset_pf2_q = 149,
    kcctl__sImmOffset_rml2 = 150,
    kcctl__sUROffset = 151,
    kcctl__sUROffset_pf2 = 152,
    kcctl__sUROffset_pf2_q = 153,
    kcctl__sUROffset_rml2 = 154,
    kcctl__uImmOffset = 155,
    kcctl__uImmOffset_pf2 = 156,
    kcctl__uImmOffset_pf2_q = 157,
    kcctl__uImmOffset_rml2 = 158,
    kcctl__uUROffset = 159,
    kcctl__uUROffset_pf2 = 160,
    kcctl__uUROffset_pf2_q = 161,
    kcctl__uUROffset_rml2 = 162,
    kcctl_c_ivall_wball_nosrc_ = 163,
    kcctl_c_ldc_const_bindless_ = 164,
    kcctl_c_ldc_const_bound_ = 165,
    kcctl_c_ldc_ivall_ = 166,
    kcctl_c_ldc_va_ = 167,
    kcctl_c_ldcu_const_bindless_ = 168,
    kcctl_c_ldcu_const_bound_ = 169,
    kcctl_c_ldcu_ivall_ = 170,
    kcctl_c_ldcu_va_ = 171,
    kcctl_i_ivall_wball_nosrc_ = 172,
    kcctll__IVALL_WBALL_D_U_noSrc = 173,
    kcctll__Ra_RZ_UR = 174,
    kcctll__Ra_nonRz_UR = 175,
    kcctll__sImmOffset = 176,
    kcctll__uImmOffset = 177,
    kcctlt__IVALL = 178,
    kcctlt__Rb = 179,
    kcctlt__URb = 180,
    kcgaerrbar_ = 181,
    kclmad__RRR_RRR = 182,
    kclmad__RRU_RRU = 183,
    kclmad__RUR_RUR = 184,
    kcs2r_ = 185,
    kcs2ur_ = 186,
    kcsmtest_ = 187,
    kcsmtest_bop_ = 188,
    kcsmtest_cmp_ = 189,
    kdadd__RRR_RR = 190,
    kdadd__RRU_RU = 191,
    kdadd__RRsI_RI = 192,
    kdepbar__LE = 193,
    kdepbar__noLE = 194,
    kdepbar_all_ = 195,
    kdepbar_ur_ = 196,
    kdfma__RRR_RRR = 197,
    kdfma__RRU_RRU = 198,
    kdfma__RRsI_RRI = 199,
    kdfma__RUR_RUR = 200,
    kdfma__RsIR_RIR = 201,
    kdmma_ = 202,
    kdmul__RRR_RR = 203,
    kdmul__RUR_RU = 204,
    kdmul__RsIR_RI = 205,
    kdsetp__RRR_RR = 206,
    kdsetp__RRU_RU = 207,
    kdsetp__RRsI_RI = 208,
    kdsetp_simple__RRR_RR = 209,
    kdsetp_simple__RRU_RU = 210,
    kdsetp_simple__RRsI_RI = 211,
    kelect_ = 212,
    kelect_Pp_ = 213,
    kelect_noURa_ = 214,
    kendcollective_ = 215,
    kerrbar_ = 216,
    kexit_ = 217,
    kf2f_f32_downconvert__RIR_RIR = 218,
    kf2f_f32_downconvert__RRR_RRR = 219,
    kf2f_f32_downconvert__RUR_RUR = 220,
    kf2f_f32_upconvert__RIR_RIR = 221,
    kf2f_f32_upconvert__RRR_RRR = 222,
    kf2f_f32_upconvert__RUR_RUR = 223,
    kf2f_f32_upconvert_swap__RIR_RIR = 224,
    kf2f_f32_upconvert_swap__RRR_RRR = 225,
    kf2f_f32_upconvert_swap__RUR_RUR = 226,
    kf2f_f64_downconvert__RIR_RIR = 227,
    kf2f_f64_downconvert__RRR_RRR = 228,
    kf2f_f64_downconvert__RUR_RUR = 229,
    kf2f_f64_upconvert__R_32I_R_RIR = 230,
    kf2f_f64_upconvert__R_I16_R_RIR = 231,
    kf2f_f64_upconvert__R_R16_R_RRR = 232,
    kf2f_f64_upconvert__R_R32_R_RRR = 233,
    kf2f_f64_upconvert__R_UR16_R_RUR = 234,
    kf2f_f64_upconvert__R_UR32_R_RUR = 235,
    kf2f_f64_upconvert_swap__R_32I_R_RIR = 236,
    kf2f_f64_upconvert_swap__R_I16_R_RIR = 237,
    kf2f_f64_upconvert_swap__R_R16_R_RRR = 238,
    kf2f_f64_upconvert_swap__R_R32_R_RRR = 239,
    kf2f_f64_upconvert_swap__R_UR16_R_RUR = 240,
    kf2f_f64_upconvert_swap__R_UR32_R_RUR = 241,
    kf2fp_4b_upconvert__RIR = 242,
    kf2fp_4b_upconvert__RRR = 243,
    kf2fp_4b_upconvert__RUR = 244,
    kf2fp_4b_upconvert_scale__RIR = 245,
    kf2fp_4b_upconvert_scale__RRI = 246,
    kf2fp_4b_upconvert_scale__RRR = 247,
    kf2fp_4b_upconvert_scale__RRU = 248,
    kf2fp_4b_upconvert_scale__RUR = 249,
    kf2fp_8b_upconvert__RIR = 250,
    kf2fp_8b_upconvert__RRR = 251,
    kf2fp_8b_upconvert__RUR = 252,
    kf2fp_8b_upconvert_scale__RIR = 253,
    kf2fp_8b_upconvert_scale__RRI = 254,
    kf2fp_8b_upconvert_scale__RRR = 255,
    kf2fp_8b_upconvert_scale__RRU = 256,
    kf2fp_8b_upconvert_scale__RUR = 257,
    kf2fp_E8_upconvert__RIR = 258,
    kf2fp_E8_upconvert__RRR = 259,
    kf2fp_E8_upconvert__RUR = 260,
    kf2fp__RIR = 261,
    kf2fp__RRR = 262,
    kf2fp__RUR = 263,
    kf2fp_default_dst_src__RIR = 264,
    kf2fp_default_dst_src__RRR = 265,
    kf2fp_default_dst_src__RUR = 266,
    kf2fp_f16_to_4b_downconvert__RIR = 267,
    kf2fp_f16_to_4b_downconvert__RRI = 268,
    kf2fp_f16_to_4b_downconvert__RRR = 269,
    kf2fp_f16_to_4b_downconvert__RRU = 270,
    kf2fp_f16_to_4b_downconvert__RUR = 271,
    kf2fp_f16_to_8b_downconvert__RIR = 272,
    kf2fp_f16_to_8b_downconvert__RRI = 273,
    kf2fp_f16_to_8b_downconvert__RRR = 274,
    kf2fp_f16_to_8b_downconvert__RRU = 275,
    kf2fp_f16_to_8b_downconvert__RUR = 276,
    kf2fp_f16_to_mx8_downconvert_scale__RIR = 277,
    kf2fp_f16_to_mx8_downconvert_scale__RRI = 278,
    kf2fp_f16_to_mx8_downconvert_scale__RRR = 279,
    kf2fp_f16_to_mx8_downconvert_scale__RRU = 280,
    kf2fp_f16_to_mx8_downconvert_scale__RUR = 281,
    kf2fp_f32_to_4b_downconvert__RIR = 282,
    kf2fp_f32_to_4b_downconvert__RRI = 283,
    kf2fp_f32_to_4b_downconvert__RRR = 284,
    kf2fp_f32_to_4b_downconvert__RRU = 285,
    kf2fp_f32_to_4b_downconvert__RUR = 286,
    kf2fp_f32_to_8b_downconvert__RIR = 287,
    kf2fp_f32_to_8b_downconvert__RRI = 288,
    kf2fp_f32_to_8b_downconvert__RRR = 289,
    kf2fp_f32_to_8b_downconvert__RRU = 290,
    kf2fp_f32_to_8b_downconvert__RUR = 291,
    kf2fp_f32_to_mx8_downconvert_scale__RIR = 292,
    kf2fp_f32_to_mx8_downconvert_scale__RRI = 293,
    kf2fp_f32_to_mx8_downconvert_scale__RRR = 294,
    kf2fp_f32_to_mx8_downconvert_scale__RRU = 295,
    kf2fp_f32_to_mx8_downconvert_scale__RUR = 296,
    kf2fp_merge_c__RIR = 297,
    kf2fp_merge_c__RRI = 298,
    kf2fp_merge_c__RRR = 299,
    kf2fp_merge_c__RRU = 300,
    kf2fp_merge_c__RUR = 301,
    kf2fp_merge_c_default_dst_src__RIR = 302,
    kf2fp_merge_c_default_dst_src__RRI = 303,
    kf2fp_merge_c_default_dst_src__RRR = 304,
    kf2fp_merge_c_default_dst_src__RRU = 305,
    kf2fp_merge_c_default_dst_src__RUR = 306,
    kf2fp_tf32__RIR = 307,
    kf2fp_tf32__RRR = 308,
    kf2fp_tf32__RUR = 309,
    kf2fp_tf32_default_src__RIR = 310,
    kf2fp_tf32_default_src__RRR = 311,
    kf2fp_tf32_default_src__RUR = 312,
    kf2i_Rd64__IU_32b = 313,
    kf2i_Rd64__Ib_16b = 314,
    kf2i_Rd64__Ib_64b = 315,
    kf2i_Rd64__Ib_bf16 = 316,
    kf2i_Rd64__Rb_16b = 317,
    kf2i_Rd64__Rb_32b = 318,
    kf2i_Rd64__Rb_64b = 319,
    kf2i_Rd64__Rb_bf16 = 320,
    kf2i_Rd64__URb_16b = 321,
    kf2i_Rd64__URb_32b = 322,
    kf2i_Rd64__URb_64b = 323,
    kf2i_Rd64__URb_bf16 = 324,
    kf2i_Rd64_swap__IU_32b = 325,
    kf2i_Rd64_swap__Ib_16b = 326,
    kf2i_Rd64_swap__Ib_64b = 327,
    kf2i_Rd64_swap__Ib_bf16 = 328,
    kf2i_Rd64_swap__Rb_16b = 329,
    kf2i_Rd64_swap__Rb_32b = 330,
    kf2i_Rd64_swap__Rb_64b = 331,
    kf2i_Rd64_swap__Rb_bf16 = 332,
    kf2i_Rd64_swap__URb_16b = 333,
    kf2i_Rd64_swap__URb_32b = 334,
    kf2i_Rd64_swap__URb_64b = 335,
    kf2i_Rd64_swap__URb_bf16 = 336,
    kf2i__IU_32b = 337,
    kf2i__Ib_16b = 338,
    kf2i__Ib_64b = 339,
    kf2i__Ib_bf16 = 340,
    kf2i__Rb_16b = 341,
    kf2i__Rb_32b = 342,
    kf2i__Rb_64b = 343,
    kf2i__Rb_bf16 = 344,
    kf2i__URb_16b = 345,
    kf2i__URb_32b = 346,
    kf2i__URb_64b = 347,
    kf2i__URb_bf16 = 348,
    kf2i_swap__IU_32b = 349,
    kf2i_swap__Ib_16b = 350,
    kf2i_swap__Ib_64b = 351,
    kf2i_swap__Ib_bf16 = 352,
    kf2i_swap__Rb_16b = 353,
    kf2i_swap__Rb_32b = 354,
    kf2i_swap__Rb_64b = 355,
    kf2i_swap__Rb_bf16 = 356,
    kf2i_swap__URb_16b = 357,
    kf2i_swap__URb_32b = 358,
    kf2i_swap__URb_64b = 359,
    kf2i_swap__URb_bf16 = 360,
    kf2ip__RIR = 361,
    kf2ip__RRI = 362,
    kf2ip__RRR = 363,
    kf2ip__RRU = 364,
    kf2ip__RUR = 365,
    kfadd32i_ = 366,
    kfadd__RRI_RI = 367,
    kfadd__RRR_RR = 368,
    kfadd__RRU_RU = 369,
    kfchk__RIR_RI = 370,
    kfchk__RRR_RR = 371,
    kfchk__RUR_RU = 372,
    kfence_ = 373,
    kfence_g_ = 374,
    kffma32i_ = 375,
    kffma__RIR_RIR = 376,
    kffma__RRI_RRI = 377,
    kffma__RRR_RRR = 378,
    kffma__RRU_RRU = 379,
    kffma__RUR_RUR = 380,
    kfhadd__RR = 381,
    kfhadd__RU = 382,
    kfhfma__RRR = 383,
    kfhfma__RRU = 384,
    kfhfma__RUR = 385,
    kflo__RRR_RRR = 386,
    kflo__RUR_RUR = 387,
    kflo__RuIR_RIR = 388,
    kfmnmx__RIR_RIR = 389,
    kfmnmx__RRR_RRR = 390,
    kfmnmx__RUR_RUR = 391,
    kfmnmx_pred__RIR_RIR = 392,
    kfmnmx_pred__RRR_RRR = 393,
    kfmnmx_pred__RUR_RUR = 394,
    kfmul32i_ = 395,
    kfmul__RIR_RI = 396,
    kfmul__RRR_RR = 397,
    kfmul__RUR_RU = 398,
    kfootprint_b_noConst_ = 399,
    kfootprint_b_urc_ = 400,
    kfootprint_scr_b_noConst_ = 401,
    kfootprint_scr_b_urc_ = 402,
    kfootprint_scr_uniform_ = 403,
    kfootprint_uniform_ = 404,
    kfrnd__bf16_I = 405,
    kfrnd__bf16_R = 406,
    kfrnd__bf16_URb = 407,
    kfrnd__f16_I = 408,
    kfrnd__f16_R = 409,
    kfrnd__f16_URb = 410,
    kfrnd__f32_I = 411,
    kfrnd__f32_R = 412,
    kfrnd__f32_URb = 413,
    kfrnd__f64_I = 414,
    kfrnd__f64_R = 415,
    kfrnd__f64_URb = 416,
    kfrnd_swap__bf16_I = 417,
    kfrnd_swap__bf16_R = 418,
    kfrnd_swap__bf16_URb = 419,
    kfrnd_swap__f16_I = 420,
    kfrnd_swap__f16_R = 421,
    kfrnd_swap__f16_URb = 422,
    kfrnd_swap__f32_I = 423,
    kfrnd_swap__f32_R = 424,
    kfrnd_swap__f32_URb = 425,
    kfrnd_swap__f64_I = 426,
    kfrnd_swap__f64_R = 427,
    kfrnd_swap__f64_URb = 428,
    kfsel__RIR_RIR = 429,
    kfsel__RRR_RRR = 430,
    kfsel__RUR_RUR = 431,
    kfset__RIR_RIR = 432,
    kfset__RRR_RRR = 433,
    kfset__RUR_RUR = 434,
    kfset_simple__RIR_RIR = 435,
    kfset_simple__RRR_RRR = 436,
    kfset_simple__RUR_RUR = 437,
    kfsetp__RIR_RIR = 438,
    kfsetp__RRR_RRR = 439,
    kfsetp__RUR_RUR = 440,
    kfsetp_simple__RIR_RIR = 441,
    kfsetp_simple__RRR_RRR = 442,
    kfsetp_simple__RUR_RUR = 443,
    kfswzadd_ = 444,
    kgetlmembase_ = 445,
    khadd2_32i_ = 446,
    khadd2_32i_fixed_ = 447,
    khadd2_F32__RI = 448,
    khadd2_F32__RR = 449,
    khadd2_F32__RU = 450,
    khadd2_F32_fixed__RR = 451,
    khadd2_F32_fixed__RU = 452,
    khadd2_F32i_ = 453,
    khadd2__RI = 454,
    khadd2__RR = 455,
    khadd2__RU = 456,
    khadd2_fixed__RI = 457,
    khadd2_fixed__RR = 458,
    khadd2_fixed__RU = 459,
    khfma2_32i_ = 460,
    khfma2_32i_fixed_ = 461,
    khfma2__RIR = 462,
    khfma2__RRI = 463,
    khfma2__RRR = 464,
    khfma2__RRU = 465,
    khfma2__RUR = 466,
    khfma2_fixed__RIR = 467,
    khfma2_fixed__RRI = 468,
    khfma2_fixed__RRR = 469,
    khfma2_fixed__RRU = 470,
    khfma2_fixed__RUR = 471,
    khfma2_mma__RIR = 472,
    khfma2_mma__RRI = 473,
    khfma2_mma__RRR = 474,
    khfma2_mma__RRU = 475,
    khfma2_mma__RUR = 476,
    khfma2_mma_relu__RIR = 477,
    khfma2_mma_relu__RRI = 478,
    khfma2_mma_relu__RRR = 479,
    khfma2_mma_relu__RRU = 480,
    khfma2_mma_relu__RUR = 481,
    khfma2_relu__RIR = 482,
    khfma2_relu__RRI = 483,
    khfma2_relu__RRR = 484,
    khfma2_relu__RRU = 485,
    khfma2_relu__RUR = 486,
    khfma2_relu_fixed__RIR = 487,
    khfma2_relu_fixed__RRI = 488,
    khfma2_relu_fixed__RRR = 489,
    khfma2_relu_fixed__RRU = 490,
    khfma2_relu_fixed__RUR = 491,
    khmma_sparse_ = 492,
    khmma_sparse_indexedRF_ = 493,
    khmma_x8_ = 494,
    khmma_x8_indexedRF_ = 495,
    khmnmx2__RIR = 496,
    khmnmx2__RRR = 497,
    khmnmx2__RUR = 498,
    khmnmx2_fixed__RIR = 499,
    khmnmx2_fixed__RRR = 500,
    khmnmx2_fixed__RUR = 501,
    khmnmx2_pred__RIR = 502,
    khmnmx2_pred__RRR = 503,
    khmnmx2_pred__RUR = 504,
    khmnmx2_pred_fixed__RIR = 505,
    khmnmx2_pred_fixed__RRR = 506,
    khmnmx2_pred_fixed__RUR = 507,
    khmul2_32i_ = 508,
    khmul2_32i_fixed_ = 509,
    khmul2__RI = 510,
    khmul2__RR = 511,
    khmul2__RU = 512,
    khmul2_fixed__RI = 513,
    khmul2_fixed__RR = 514,
    khmul2_fixed__RU = 515,
    khset2__RI = 516,
    khset2__RR = 517,
    khset2__RU = 518,
    khset2_fixed__RI = 519,
    khset2_fixed__RR = 520,
    khset2_fixed__RU = 521,
    khset2_noBop__RI = 522,
    khset2_noBop__RR = 523,
    khset2_noBop__RU = 524,
    khset2_noBop_fixed__RI = 525,
    khset2_noBop_fixed__RR = 526,
    khset2_noBop_fixed__RU = 527,
    khsetp2__RI = 528,
    khsetp2__RR = 529,
    khsetp2__RU = 530,
    khsetp2_fixed__RI = 531,
    khsetp2_fixed__RR = 532,
    khsetp2_fixed__RU = 533,
    khsetp2_noBop__RI = 534,
    khsetp2_noBop__RR = 535,
    khsetp2_noBop__RU = 536,
    khsetp2_noBop_fixed__RI = 537,
    khsetp2_noBop_fixed__RR = 538,
    khsetp2_noBop_fixed__RU = 539,
    ki2f_Rd64__IS_32b = 540,
    ki2f_Rd64__IS_64b = 541,
    ki2f_Rd64__IU_32b = 542,
    ki2f_Rd64__IU_64b = 543,
    ki2f_Rd64__Rb_16b = 544,
    ki2f_Rd64__Rb_32b = 545,
    ki2f_Rd64__Rb_64b = 546,
    ki2f_Rd64__Rb_8b = 547,
    ki2f_Rd64__UR_16b = 548,
    ki2f_Rd64__UR_32b = 549,
    ki2f_Rd64__UR_64b = 550,
    ki2f_Rd64__UR_8b = 551,
    ki2f__IS_32b = 552,
    ki2f__IS_64b = 553,
    ki2f__IU_32b = 554,
    ki2f__IU_64b = 555,
    ki2f__Rb_16b = 556,
    ki2f__Rb_32b = 557,
    ki2f__Rb_64b = 558,
    ki2f__Rb_8b = 559,
    ki2f__UR_16b = 560,
    ki2f__UR_32b = 561,
    ki2f__UR_64b = 562,
    ki2f__UR_8b = 563,
    ki2fp__RRR = 564,
    ki2fp__RUR = 565,
    ki2fp__RsIR = 566,
    ki2fp__RuIR = 567,
    ki2i__RRR_RRR = 568,
    ki2i__RUR_RUR = 569,
    ki2i__RsIR_RIR = 570,
    ki2ip_24__RRR_RRR = 571,
    ki2ip_24__RUR_RUR = 572,
    ki2ip_24__RsIR_RIR = 573,
    ki2ip_24_relu__RRR_RRR = 574,
    ki2ip_24_relu__RUR_RUR = 575,
    ki2ip_24_relu__RsIR_RIR = 576,
    ki2ip_28__RRR_RRR = 577,
    ki2ip_28__RUR_RUR = 578,
    ki2ip_28__RsIR_RIR = 579,
    ki2ip_28_relu__RRR_RRR = 580,
    ki2ip_28_relu__RUR_RUR = 581,
    ki2ip_28_relu__RsIR_RIR = 582,
    ki2ip__RRR_RRR = 583,
    ki2ip__RUR_RUR = 584,
    ki2ip__RsIR_RIR = 585,
    ki2ip_relu__RRR_RRR = 586,
    ki2ip_relu__RUR_RUR = 587,
    ki2ip_relu__RsIR_RIR = 588,
    kiabs__RRR_R = 589,
    kiabs__RUR_UR = 590,
    kiabs__RsIR_I = 591,
    kiadd32i_imm__RsIR_RIR = 592,
    kiadd32i_x_imm__RIR_RIR = 593,
    kiadd3_imm__RsIR_RIR = 594,
    kiadd3_noimm__RRR_RRR = 595,
    kiadd3_noimm__RUR_RUR = 596,
    kiadd3_x_imm__RIR_RIR = 597,
    kiadd3_x_noimm__RRR_RRR = 598,
    kiadd3_x_noimm__RUR_RUR = 599,
    kiadd_64_imm__RsIR_RIR = 600,
    kiadd_64_noimm__RRR_RRR = 601,
    kiadd_64_noimm__RUR_RUR = 602,
    kiadd_64_x_imm__RIR_RIR = 603,
    kiadd_64_x_noimm__RRR_RRR = 604,
    kiadd_64_x_noimm__RUR_RUR = 605,
    kiadd_imm__RsIR_RIR = 606,
    kiadd_noimm__RRR_RRR = 607,
    kiadd_noimm__RUR_RUR = 608,
    kiadd_x_imm__RIR_RIR = 609,
    kiadd_x_noimm__RRR_RRR = 610,
    kiadd_x_noimm__RUR_RUR = 611,
    kide_ = 612,
    kidp4a__R = 613,
    kidp4a__URb = 614,
    kidp_2a__R = 615,
    kidp_2a__URb = 616,
    kidp_4a__R = 617,
    kidp_4a__URb = 618,
    kimad__RRR_RRR = 619,
    kimad__RRU_RRU = 620,
    kimad__RRsI_RRI = 621,
    kimad__RUR_RUR = 622,
    kimad__RsIR_RIR = 623,
    kimad_hi__RRR_RRR = 624,
    kimad_hi__RRU_RRU = 625,
    kimad_hi__RUR_RUR = 626,
    kimad_hi__RsIR_RIR = 627,
    kimad_hi_pseudo__RRR_RRR = 628,
    kimad_hi_pseudo__RRU_RRU = 629,
    kimad_hi_pseudo__RUR_RUR = 630,
    kimad_hi_pseudo__RsIR_RIR = 631,
    kimad_hi_x__RRR_RRR = 632,
    kimad_hi_x__RRU_RRU = 633,
    kimad_hi_x__RUR_RUR = 634,
    kimad_hi_x__RsIR_RIR = 635,
    kimad_hi_x_pseudo__RRR_RRR = 636,
    kimad_hi_x_pseudo__RRU_RRU = 637,
    kimad_hi_x_pseudo__RUR_RUR = 638,
    kimad_hi_x_pseudo__RsIR_RIR = 639,
    kimad_pseudo__RRR_RRR = 640,
    kimad_pseudo__RRU_RRU = 641,
    kimad_pseudo__RRsI_RRI = 642,
    kimad_pseudo__RUR_RUR = 643,
    kimad_pseudo__RsIR_RIR = 644,
    kimad_wide__RRR_RRR = 645,
    kimad_wide__RRU_RRU = 646,
    kimad_wide__RUR_RUR = 647,
    kimad_wide__RsIR_RIR = 648,
    kimad_wide_pseudo__RRR_RRR = 649,
    kimad_wide_pseudo__RRU_RRU = 650,
    kimad_wide_pseudo__RUR_RUR = 651,
    kimad_wide_pseudo__RsIR_RIR = 652,
    kimad_wide_x__RRR_RRR = 653,
    kimad_wide_x__RRU_RRU = 654,
    kimad_wide_x__RUR_RUR = 655,
    kimad_wide_x__RsIR_RIR = 656,
    kimad_wide_x_pseudo__RRR_RRR = 657,
    kimad_wide_x_pseudo__RRU_RRU = 658,
    kimad_wide_x_pseudo__RUR_RUR = 659,
    kimad_wide_x_pseudo__RsIR_RIR = 660,
    kimad_x__RRR_RRR = 661,
    kimad_x__RRU_RRU = 662,
    kimad_x__RRsI_RRI = 663,
    kimad_x__RUR_RUR = 664,
    kimad_x__RsIR_RIR = 665,
    kimad_x_pseudo__RRR_RRR = 666,
    kimad_x_pseudo__RRU_RRU = 667,
    kimad_x_pseudo__RRsI_RRI = 668,
    kimad_x_pseudo__RUR_RUR = 669,
    kimad_x_pseudo__RsIR_RIR = 670,
    kimma_ = 671,
    kimma_sp_ = 672,
    kimnmx_64__RIR_RsIR = 673,
    kimnmx_64__RRR_RRR = 674,
    kimnmx_64__RUR_RUR = 675,
    kimnmx_64_nopred__RIR_RsIR = 676,
    kimnmx_64_nopred__RRR_RRR = 677,
    kimnmx_64_nopred__RUR_RUR = 678,
    kimnmx__RIR_RsIR = 679,
    kimnmx__RRR_RRR = 680,
    kimnmx__RUR_RUR = 681,
    kimnmx_nopred__RIR_RsIR = 682,
    kimnmx_nopred__RRR_RRR = 683,
    kimnmx_nopred__RUR_RUR = 684,
    kimul32i_lo__RsIR_RIR = 685,
    kimul32i_wide__RsIR_RIR = 686,
    kimul__RRR_RRR = 687,
    kimul__RUR_RUR = 688,
    kimul__RsIR_RIR = 689,
    kimul_wide__RRR_RRR = 690,
    kimul_wide__RUR_RUR = 691,
    kimul_wide__RsIR_RIR = 692,
    kipa_ = 693,
    kipa_offset__IPA_Ib = 694,
    kipa_offset__IPA_Rb = 695,
    kipa_ur_ = 696,
    kipa_ur_offset__IPA_URa_Ib = 697,
    kipa_ur_offset__IPA_URa_Rb = 698,
    kisberd_ = 699,
    kisbewr_ = 700,
    kiscadd32i__RIR_RIR = 701,
    kiscadd_imm__RIR_RIR = 702,
    kiscadd_noimm__RRR_RRR = 703,
    kiscadd_noimm__RUR_RUR = 704,
    kisetp_64__RRR_RRR_EX = 705,
    kisetp_64__RRR_RRR_noEX = 706,
    kisetp_64__RUR_RUR_EX = 707,
    kisetp_64__RUR_RUR_noEX = 708,
    kisetp_64__RsIR_RIR_EX = 709,
    kisetp_64__RsIR_RIR_noEX = 710,
    kisetp_64_simple__RRR_RRR_EX = 711,
    kisetp_64_simple__RRR_RRR_noEX = 712,
    kisetp_64_simple__RUR_RUR_EX = 713,
    kisetp_64_simple__RUR_RUR_noEX = 714,
    kisetp_64_simple__RsIR_RIR_EX = 715,
    kisetp_64_simple__RsIR_RIR_noEX = 716,
    kisetp__RRR_RRR_EX = 717,
    kisetp__RRR_RRR_noEX = 718,
    kisetp__RUR_RUR_EX = 719,
    kisetp__RUR_RUR_noEX = 720,
    kisetp__RsIR_RIR_EX = 721,
    kisetp__RsIR_RIR_noEX = 722,
    kisetp_simple__RRR_RRR_EX = 723,
    kisetp_simple__RRR_RRR_noEX = 724,
    kisetp_simple__RUR_RUR_EX = 725,
    kisetp_simple__RUR_RUR_noEX = 726,
    kisetp_simple__RsIR_RIR_EX = 727,
    kisetp_simple__RsIR_RIR_noEX = 728,
    kjmp_imm__CONV_DIV = 729,
    kjmp_imm__U = 730,
    kjmp_imm_rel__CONV_DIV = 731,
    kjmp_imm_rel__U = 732,
    kjmp_imm_uniform_ = 733,
    kjmp_imm_uniform_pred_ = 734,
    kjmp_imm_uniform_pred_rel_ = 735,
    kjmp_imm_uniform_rel_ = 736,
    kjmx_ = 737,
    kjmx_rel_ = 738,
    kjmxu_ = 739,
    kjmxu_rel_ = 740,
    kkill_ = 741,
    kld__sImmOffset = 742,
    kld__uImmOffset = 743,
    kld_memdesc__Ra64 = 744,
    kld_uniform__Ra32 = 745,
    kld_uniform__Ra64 = 746,
    kld_uniform__RaRZ = 747,
    kldc__RaNonRZ = 748,
    kldc__RaRZ = 749,
    kldc_ur__URRzI = 750,
    kldc_ur__URnonRzI = 751,
    kldcu_256_const_RCR_ = 752,
    kldcu_256_const_RCxR_ = 753,
    kldcu_256_ur_offs_ = 754,
    kldcu_256_ur_offs_optional_upx_ = 755,
    kldcu_const_RCR_ = 756,
    kldcu_const_RCxR_ = 757,
    kldcu_ur_offs_ = 758,
    kldcu_ur_offs_optional_upx_ = 759,
    kldg_256_memdesc__Ra64 = 760,
    kldg_256_rml2_memdesc__Ra64 = 761,
    kldg_256_rml2_uniform__Ra32 = 762,
    kldg_256_rml2_uniform__Ra64 = 763,
    kldg_256_rml2_uniform__RaRZ = 764,
    kldg_256_uniform__Ra32 = 765,
    kldg_256_uniform__Ra64 = 766,
    kldg_256_uniform__RaRZ = 767,
    kldg__sImmOffset = 768,
    kldg__uImmOffset = 769,
    kldg_memdesc__Ra64 = 770,
    kldg_uniform__Ra32 = 771,
    kldg_uniform__Ra64 = 772,
    kldg_uniform__RaRZ = 773,
    kldgdepbar_ = 774,
    kldgmc_fp__Ra32 = 775,
    kldgmc_fp__Ra64 = 776,
    kldgmc_fp__RaRZ = 777,
    kldgmc_fp__memdesc = 778,
    kldgmc_int__Ra32 = 779,
    kldgmc_int__Ra64 = 780,
    kldgmc_int__RaRZ = 781,
    kldgmc_int__memdesc = 782,
    kldgsts__RR32U = 783,
    kldgsts__RR64U = 784,
    kldgsts__RUR = 785,
    kldgsts__desc_RRU = 786,
    kldgsts_memdesc_ = 787,
    kldgsts_no_ra__RRU = 788,
    kldgsts_no_ra__RUR = 789,
    kldl__sImmOffset = 790,
    kldl__uImmOffset = 791,
    kldl_memdesc_ = 792,
    kldl_uniform_ = 793,
    klds__sImmOffset = 794,
    klds__uImmOffset = 795,
    klds_uniform_ = 796,
    kldsm__UR_sI_R = 797,
    kldsm__sImmOffset = 798,
    kldsm_pseudo_ops__UR_sI_R = 799,
    kldsm_pseudo_ops__sImmOffset = 800,
    kldtram_ = 801,
    klea_hi_imm__RRuI_RRI = 802,
    klea_hi_imm__RuIR_RIR = 803,
    klea_hi_imm_sx32__RuIR_RIR = 804,
    klea_hi_imm_sx32_x__RuIR_RIR = 805,
    klea_hi_imm_x__RRuI_RRI = 806,
    klea_hi_imm_x__RuIR_RIR = 807,
    klea_hi_noimm__RRR_RRR = 808,
    klea_hi_noimm__RUR_RUR = 809,
    klea_hi_noimm_sx32__RRR_RRR = 810,
    klea_hi_noimm_sx32__RUR_RUR = 811,
    klea_hi_noimm_sx32_x__RRR_RRR = 812,
    klea_hi_noimm_sx32_x__RUR_RUR = 813,
    klea_hi_noimm_x__RRR_RRR = 814,
    klea_hi_noimm_x__RUR_RUR = 815,
    klea_lo_imm__RuIR_RIR = 816,
    klea_lo_imm_x__RuIR_RIR = 817,
    klea_lo_noimm__RRR_RRR = 818,
    klea_lo_noimm__RUR_RUR = 819,
    klea_lo_noimm_x__RRR_RRR = 820,
    klea_lo_noimm_x__RUR_RUR = 821,
    klepc__RRR = 822,
    klepc__R_I_R = 823,
    klepc_rel_ = 824,
    klop32i_ = 825,
    klop32i_optionalPp_ = 826,
    klop3_imm__RIR_RIR = 827,
    klop3_imm_optionalPp__RIR_RIR = 828,
    klop3_lut__RRR_RRR = 829,
    klop3_lut__RUR_RUR = 830,
    klop3_lut__RuIR_RIR = 831,
    klop3_lut_optionalPp__RRR_RRR = 832,
    klop3_lut_optionalPp__RUR_RUR = 833,
    klop3_lut_optionalPp__RuIR_RIR = 834,
    klop3_noimm__RRR_RRR = 835,
    klop3_noimm__RUR_RUR = 836,
    klop3_noimm_optionalPp__RRR_RRR = 837,
    klop3_noimm_optionalPp__RUR_RUR = 838,
    klop_imm_ = 839,
    klop_imm_optionalPp_ = 840,
    klop_noimm__RRR_RRR = 841,
    klop_noimm__RUR_RUR = 842,
    klop_noimm_optionalPp__RRR_RRR = 843,
    klop_noimm_optionalPp__RUR_RUR = 844,
    kmatch__ALL = 845,
    kmatch__ANY = 846,
    kmembar_ = 847,
    kmembar_async_ = 848,
    kmembar_tma_ = 849,
    kmov32i_ = 850,
    kmov64iur_imm_ = 851,
    kmov64iur_ur_ = 852,
    kmov_64__RR = 853,
    kmov_64__RU = 854,
    kmov__RI = 855,
    kmov__RR = 856,
    kmov__RU = 857,
    kmov_imm64_ = 858,
    kmov_indexedRF_IRFd__Ib = 859,
    kmov_indexedRF_IRFd__Rb = 860,
    kmov_indexedRF_Rd_ = 861,
    kmov_nonconformity__RU = 862,
    kmovm_ = 863,
    kmufu__RIR_RI = 864,
    kmufu__RRR_RR = 865,
    kmufu__RUR_RU = 866,
    kmufu_fp16__RI = 867,
    kmufu_fp16__RR = 868,
    kmufu_fp16__RU = 869,
    kmufu_fp16_swap__RR = 870,
    kmufu_fp16_swap__RU = 871,
    kmxqmma_scale_ = 872,
    knanosleep__I = 873,
    knanosleep__R = 874,
    knanosleep__U = 875,
    knanosleep_clear_ = 876,
    knanotrap__I = 877,
    knanotrap__R = 878,
    knanotrap__U = 879,
    knop_ = 880,
    komma_scale_ = 881,
    komma_sp_scale_ = 882,
    kout__CUT = 883,
    kout__EMIT_Imm = 884,
    kout__EMIT_Rb = 885,
    kout__EMIT_URb = 886,
    kout__FINAL = 887,
    kout_final_rz_ = 888,
    kp2r__RRR_RRR = 889,
    kp2r__RUR_RUR = 890,
    kp2r__RuIR_RIR = 891,
    kp2r_simple_ = 892,
    kpixld_ = 893,
    kplop3_1out_ = 894,
    kplop3_1out_uniform_ = 895,
    kplop3_lut_1out_ = 896,
    kplop3_lut_1out_1reg__RRR = 897,
    kplop3_lut_1out_1reg__RUR = 898,
    kplop3_lut_1out_2reg__RRR = 899,
    kplop3_lut_1out_2reg__RUR = 900,
    kplop3_lut_1out_3reg__RRR = 901,
    kplop3_lut_1out_3reg__RUR = 902,
    kplop3_lut_1out_uniform_ = 903,
    kplop3_lut_2out_ = 904,
    kplop3_lut_2out_1reg__RRR = 905,
    kplop3_lut_2out_1reg__RUR = 906,
    kplop3_lut_2out_2reg__RRR = 907,
    kplop3_lut_2out_2reg__RUR = 908,
    kplop3_lut_2out_3reg__RRR = 909,
    kplop3_lut_2out_3reg__RUR = 910,
    kplop3_lut_2out_uniform_ = 911,
    kpmtrig_ = 912,
    kpopc__RRR_RRR = 913,
    kpopc__RUR_RUR = 914,
    kpopc__RuIR_RIR = 915,
    kpreexit_ = 916,
    kprmt__RRR_RRR = 917,
    kprmt__RRU_RRU = 918,
    kprmt__RRuI_RRI = 919,
    kprmt__RUR_RUR = 920,
    kprmt__RuIR_RIR = 921,
    kpsetp_ = 922,
    kpsetp_simple_ = 923,
    kpsetp_uniform_ = 924,
    kqmma_ = 925,
    kqmma_rowcol_ = 926,
    kqmma_scale_ = 927,
    kqmma_sp_ = 928,
    kqmma_sp_rowcol_ = 929,
    kqmma_sp_scale_ = 930,
    kqspc_PuOnly__RaNonRZ = 931,
    kqspc_PuOnly__RaRZ = 932,
    kqspc_RdOnly__RaNonRZ = 933,
    kqspc_RdOnly__RaRZ = 934,
    kqspc__RaNonRZ = 935,
    kqspc__RaRZ = 936,
    kqspc_urb_PuOnly__Ra32 = 937,
    kqspc_urb_PuOnly__Ra64 = 938,
    kqspc_urb_PuOnly__RaRZ = 939,
    kqspc_urb_RdOnly__Ra32 = 940,
    kqspc_urb_RdOnly__Ra64 = 941,
    kqspc_urb_RdOnly__RaRZ = 942,
    kqspc_urb__Ra32 = 943,
    kqspc_urb__Ra64 = 944,
    kqspc_urb__RaRZ = 945,
    kr2b_ = 946,
    kr2p__RIR = 947,
    kr2p__RRR = 948,
    kr2p__RUR = 949,
    kr2ur__OR = 950,
    kr2ur__noOR = 951,
    kr2ur_nonconformity__OR = 952,
    kr2ur_nonconformity__noOR = 953,
    kredas_64__Ra64 = 954,
    kredas_64__RaRZ = 955,
    kredas__Ra32 = 956,
    kredg_fp__RaNonRZ = 957,
    kredg_fp__RaRZ = 958,
    kredg_fp_uniform__Ra32 = 959,
    kredg_fp_uniform__Ra64 = 960,
    kredg_fp_uniform__RaRZ = 961,
    kredg_fp_uniform__memdesc = 962,
    kredg_int__RaNonRZ = 963,
    kredg_int__RaRZ = 964,
    kredg_int_uniform__Ra32 = 965,
    kredg_int_uniform__Ra64 = 966,
    kredg_int_uniform__RaRZ = 967,
    kredg_int_uniform__memdesc = 968,
    kredux_ = 969,
    kret__ABS = 970,
    kret__ABS_UR = 971,
    kret__REL = 972,
    kret__REL_UR = 973,
    kret_rel__RIR = 974,
    kret_rel__URIR = 975,
    kret_rel_reg__RIR = 976,
    kret_rel_reg__URIR = 977,
    krpcmov_dstPc64__Imm = 978,
    krpcmov_dstPc64__URb = 979,
    krpcmov_dstPc_ = 980,
    krpcmov_dstPc_URb_ = 981,
    krpcmov_dstPc_imm_ = 982,
    krpcmov_srcPc_ = 983,
    krtt_ = 984,
    ks2r_ = 985,
    ks2ur_ = 986,
    ksel_64__RIR = 987,
    ksel_64__RRR = 988,
    ksel_64__RUR = 989,
    ksel__RRR_RRR = 990,
    ksel__RUR_RUR = 991,
    ksel__RuIR_RIR = 992,
    ksetctaid_ = 993,
    ksetlmembase_ = 994,
    ksgxt__RRR_RRR = 995,
    ksgxt__RUR_RUR = 996,
    ksgxt__RuIR_RIR = 997,
    kshf__RRR_RRR = 998,
    kshf__RRU_RRU = 999,
    kshf__RRuI_RRI = 1000,
    kshf__RUR_RUR = 1001,
    kshf__RuIR_RIR = 1002,
    kshfl__RII = 1003,
    kshfl__RIR = 1004,
    kshfl__RRI = 1005,
    kshfl__RRR = 1006,
    kshl__RRR_RRR = 1007,
    kshl__RUR_RUR = 1008,
    kshl__RuIR_RIR = 1009,
    kshl_imm_ = 1010,
    kshr__RIR_RIR = 1011,
    kshr__RRR_RRR = 1012,
    kshr__RUR_RUR = 1013,
    kst__sImmOffset = 1014,
    kst__uImmOffset = 1015,
    kst_memdesc__Ra64 = 1016,
    kst_uniform__Ra32 = 1017,
    kst_uniform__Ra64 = 1018,
    kst_uniform__RaRZ = 1019,
    kstas_64__Ra64 = 1020,
    kstas_64__RaRZ = 1021,
    kstas__Ra32 = 1022,
    kstg_256_memdesc__Ra64 = 1023,
    kstg_256_uniform__Ra32 = 1024,
    kstg_256_uniform__Ra64 = 1025,
    kstg_256_uniform__RaRZ = 1026,
    kstg__sImmOffset = 1027,
    kstg__uImmOffset = 1028,
    kstg_memdesc__Ra64 = 1029,
    kstg_uniform__Ra32 = 1030,
    kstg_uniform__Ra64 = 1031,
    kstg_uniform__RaRZ = 1032,
    kstl__sImmOffset = 1033,
    kstl__uImmOffset = 1034,
    kstl_memdesc_ = 1035,
    kstl_uniform_ = 1036,
    ksts__sImmOffset = 1037,
    ksts__uImmOffset = 1038,
    ksts_uniform_ = 1039,
    kstsm__UR_sI_R = 1040,
    kstsm__sImmOffset = 1041,
    ksuatom_cas_r_urc_ = 1042,
    ksuatom_cas_reg_ = 1043,
    ksuatom_cas_urc_ = 1044,
    ksuatom_r_urc_ = 1045,
    ksuatom_reg_ = 1046,
    ksuatom_urc_ = 1047,
    ksuld_d_r_urc_ = 1048,
    ksuld_d_reg_ = 1049,
    ksuld_d_urc_ = 1050,
    ksuld_p_r_urc_ = 1051,
    ksuld_p_reg_ = 1052,
    ksuld_p_urc_ = 1053,
    ksuquery_r_urc_ = 1054,
    ksuquery_reg_ = 1055,
    ksuquery_urc_ = 1056,
    ksured_r_urc_ = 1057,
    ksured_reg_ = 1058,
    ksured_urc_ = 1059,
    ksust_d_r_urc_ = 1060,
    ksust_d_reg_ = 1061,
    ksust_d_urc_ = 1062,
    ksust_p_r_urc_ = 1063,
    ksust_p_reg_ = 1064,
    ksust_p_urc_ = 1065,
    ksyncs_arrive_ = 1066,
    ksyncs_cctl_ = 1067,
    ksyncs_cctl_all_ = 1068,
    ksyncs_flush_ = 1069,
    ksyncs_ld_ = 1070,
    ksyncs_phasechk_ = 1071,
    ksyncs_tcnt_ = 1072,
    ksyncs_uniform_cas_ = 1073,
    ksyncs_uniform_exch_ = 1074,
    ksyncs_uniform_ld_ = 1075,
    ktex_b_noConst_ = 1076,
    ktex_b_urc_ = 1077,
    ktex_scr_b_noConst_ = 1078,
    ktex_scr_b_urc_ = 1079,
    ktex_scr_urc_ = 1080,
    ktex_urc_ = 1081,
    ktld4_b_noConst_ = 1082,
    ktld4_b_urc_ = 1083,
    ktld4_scr_b_noConst_ = 1084,
    ktld4_scr_b_urc_ = 1085,
    ktld4_scr_urc_ = 1086,
    ktld4_urc_ = 1087,
    ktld_b_noConst_ = 1088,
    ktld_b_urc_ = 1089,
    ktld_scr_b_noConst_ = 1090,
    ktld_scr_b_urc_ = 1091,
    ktld_scr_urc_ = 1092,
    ktld_urc_ = 1093,
    ktmml_b_noConst_ = 1094,
    ktmml_b_urc_ = 1095,
    ktmml_urc_ = 1096,
    kttucctl_ = 1097,
    kttuclose_ = 1098,
    kttugo_ = 1099,
    kttuld__close = 1100,
    kttuld__no_close = 1101,
    kttumacrofuse_ = 1102,
    kttuopen_ = 1103,
    kttust_ = 1104,
    ktxd_b_noConst_ = 1105,
    ktxd_b_urc_ = 1106,
    ktxd_urc_ = 1107,
    ktxq_b_noConst_ = 1108,
    ktxq_b_urc_ = 1109,
    ktxq_urc_ = 1110,
    kublkcp_ = 1111,
    kublkcp_desc_ = 1112,
    kublkcp_desc_one_ = 1113,
    kublkcp_one_ = 1114,
    kublkpf__UUU = 1115,
    kublkpf__UUU_desc = 1116,
    kublkpf_one__UUU = 1117,
    kublkpf_one__UUU_desc = 1118,
    kublkred_ = 1119,
    kublkred_desc_ = 1120,
    kublkred_desc_one_ = 1121,
    kublkred_one_ = 1122,
    kubmsk__URURUR_URUR = 1123,
    kubmsk__URuIUR_URI = 1124,
    kubrev__URURUR_URUR = 1125,
    kubrev__URuIUR_URI = 1126,
    kucgabar_arrive_ = 1127,
    kucgabar_get_ = 1128,
    kucgabar_set_ = 1129,
    kucgabar_wait_ = 1130,
    kucgabararrive_ = 1131,
    kucgabarget_ = 1132,
    kucgabarset_ = 1133,
    kucgabarwait_ = 1134,
    kuclea__Imm = 1135,
    kuclea__URb = 1136,
    kuf2f_f32_downconvert__URIR_URIR = 1137,
    kuf2f_f32_downconvert__UUU_UUU = 1138,
    kuf2f_f32_upconvert__URIR_URIR = 1139,
    kuf2f_f32_upconvert__UUU_UUU = 1140,
    kuf2f_f32_upconvert_swap__URIR_URIR = 1141,
    kuf2f_f32_upconvert_swap__UUU_UUU = 1142,
    kuf2fp_8b_upconvert__URIUR = 1143,
    kuf2fp_8b_upconvert__URURUR = 1144,
    kuf2fp__URIUR = 1145,
    kuf2fp__URURUR = 1146,
    kuf2fp_default_dst_src__URIUR = 1147,
    kuf2fp_default_dst_src__URURUR = 1148,
    kuf2fp_f16_to_8b_downconvert__URIUR = 1149,
    kuf2fp_f16_to_8b_downconvert__URURI = 1150,
    kuf2fp_f16_to_8b_downconvert__URURUR = 1151,
    kuf2fp_f32_to_8b_downconvert__URIUR = 1152,
    kuf2fp_f32_to_8b_downconvert__URURI = 1153,
    kuf2fp_f32_to_8b_downconvert__URURUR = 1154,
    kuf2fp_merge_c__URIUR = 1155,
    kuf2fp_merge_c__URURI = 1156,
    kuf2fp_merge_c__URURUR = 1157,
    kuf2fp_merge_c_default_dst_src__URIUR = 1158,
    kuf2fp_merge_c_default_dst_src__URURI = 1159,
    kuf2fp_merge_c_default_dst_src__URURUR = 1160,
    kuf2fp_tf32__URIUR = 1161,
    kuf2fp_tf32__URURUR = 1162,
    kuf2fp_tf32_default_src__URIUR = 1163,
    kuf2fp_tf32_default_src__URURUR = 1164,
    kuf2i__IU_32b = 1165,
    kuf2i__Ib_16b = 1166,
    kuf2i__Ib_bf16 = 1167,
    kuf2i__URb_16b = 1168,
    kuf2i__URb_32b = 1169,
    kuf2i__URb_bf16 = 1170,
    kuf2i_swap__IU_32b = 1171,
    kuf2i_swap__Ib_16b = 1172,
    kuf2i_swap__Ib_bf16 = 1173,
    kuf2i_swap__URb_16b = 1174,
    kuf2i_swap__URb_32b = 1175,
    kuf2i_swap__URb_bf16 = 1176,
    kuf2ip__RRI = 1177,
    kuf2ip__URIUR = 1178,
    kuf2ip__UUU = 1179,
    kufadd__URURUR_UUU = 1180,
    kufadd__URURsI_URURI = 1181,
    kuffma__URIUR_URIUR = 1182,
    kuffma__URURI_URURI = 1183,
    kuffma__UUU_UUU = 1184,
    kufhadd__UUU = 1185,
    kufhfma__UUU = 1186,
    kuflo__URURUR_URURUR = 1187,
    kuflo__URuIUR_URuIR = 1188,
    kufmnmx__URURUR_UUU = 1189,
    kufmnmx__URsIUR_URIR = 1190,
    kufmnmx_pred__URURUR_UUU = 1191,
    kufmnmx_pred__URsIUR_URIR = 1192,
    kufmul__URIR = 1193,
    kufmul__UUU = 1194,
    kufrnd__bf16_I = 1195,
    kufrnd__bf16_URb = 1196,
    kufrnd__f16_I = 1197,
    kufrnd__f16_URb = 1198,
    kufrnd__f32_I = 1199,
    kufrnd__f32_URb = 1200,
    kufrnd_swap__bf16_I = 1201,
    kufrnd_swap__bf16_URb = 1202,
    kufrnd_swap__f16_I = 1203,
    kufrnd_swap__f16_URb = 1204,
    kufrnd_swap__f32_I = 1205,
    kufrnd_swap__f32_URb = 1206,
    kufsel__URURUR_UUU = 1207,
    kufsel__URsIUR_URIR = 1208,
    kufset__URURUR_UUU = 1209,
    kufset__URsIUR_URIR = 1210,
    kufset_simple__URURUR_UUU = 1211,
    kufset_simple__URsIUR_URIR = 1212,
    kufsetp__URURUR_UUU = 1213,
    kufsetp__URsIUR_URIR = 1214,
    kufsetp_simple__URURUR_UUU = 1215,
    kufsetp_simple__URsIUR_URIR = 1216,
    kugetnextworkid_ = 1217,
    kugetnextworkid_one_ = 1218,
    kui2f__IS_32b = 1219,
    kui2f__IU_32b = 1220,
    kui2f__UR_16b = 1221,
    kui2f__UR_32b = 1222,
    kui2f__UR_8b = 1223,
    kui2fp__URsIR = 1224,
    kui2fp__URuIR = 1225,
    kui2fp__UUU = 1226,
    kui2i__URURUR_UUU = 1227,
    kui2i__URsIUR_URIR = 1228,
    kui2ip_24__URURUR_UUU = 1229,
    kui2ip_24__URsIUR_URRI = 1230,
    kui2ip_28__URURUR_UUU = 1231,
    kui2ip_28__URsIUR_URRI = 1232,
    kui2ip__URURUR_UUU = 1233,
    kui2ip__URsIUR_URRI = 1234,
    kuiabs__URURUR_UR = 1235,
    kuiabs__URsIUR_I = 1236,
    kuiadd3_64__URURUR_URURUR = 1237,
    kuiadd3_64__URsIUR_RIR = 1238,
    kuiadd3_64_x__URURUR_URURUR = 1239,
    kuiadd3_64_x__URsIUR_RIR = 1240,
    kuiadd3__URURUR_URURUR = 1241,
    kuiadd3__URsIUR_RIR = 1242,
    kuiadd3_x__URURUR_URURUR = 1243,
    kuiadd3_x__URsIUR_RIR = 1244,
    kuimad__URURUR_URURUR = 1245,
    kuimad__URURsI_URURI = 1246,
    kuimad__URsIUR_URIUR = 1247,
    kuimad_hi__URURUR_URURUR = 1248,
    kuimad_hi__URsIUR_URIUR = 1249,
    kuimad_hi_x__URURUR_URURUR = 1250,
    kuimad_hi_x__URsIUR_URIUR = 1251,
    kuimad_wide__URURUR_URURUR = 1252,
    kuimad_wide__URsIUR_URIUR = 1253,
    kuimad_wide_x__URURUR_URURUR = 1254,
    kuimad_wide_x__URsIUR_URIUR = 1255,
    kuimad_x__URURUR_URURUR = 1256,
    kuimad_x__URURsI_URURI = 1257,
    kuimad_x__URsIUR_URIUR = 1258,
    kuimnmx_64__URIR_URsIUR = 1259,
    kuimnmx_64__UUU_URURUR = 1260,
    kuimnmx_64_nopred__URIR_URsIUR = 1261,
    kuimnmx_64_nopred__UUU_URURUR = 1262,
    kuimnmx__URIR_URsIUR = 1263,
    kuimnmx__UUU_URURUR = 1264,
    kuimnmx_nopred__URIR_URsIUR = 1265,
    kuimnmx_nopred__UUU_URURUR = 1266,
    kuisetp_64__URURUR_URURUR = 1267,
    kuisetp_64__URsIUR_URIR = 1268,
    kuisetp_64_optional_upr__URURUR_URURUR = 1269,
    kuisetp_64_optional_upr__URsIUR_URIR = 1270,
    kuisetp_64_simple__URURUR_URURUR = 1271,
    kuisetp_64_simple__URsIUR_URIR = 1272,
    kuisetp_64_simple_optional_upr__URURUR_URURUR = 1273,
    kuisetp_64_simple_optional_upr__URsIUR_URIR = 1274,
    kuisetp__URURUR_URURUR = 1275,
    kuisetp__URsIUR_URIR = 1276,
    kuisetp_optional_upr__URURUR_URURUR = 1277,
    kuisetp_optional_upr__URsIUR_URIR = 1278,
    kuisetp_simple__URURUR_URURUR = 1279,
    kuisetp_simple__URsIUR_URIR = 1280,
    kuisetp_simple_optional_upr__URURUR_URURUR = 1281,
    kuisetp_simple_optional_upr__URsIUR_URIR = 1282,
    kulea_hi_imm__RRuI_RRI = 1283,
    kulea_hi_imm__RuIR_URIR = 1284,
    kulea_hi_imm_sx32__RuIR_URIUR = 1285,
    kulea_hi_imm_sx32_x__RuIR_URIUR = 1286,
    kulea_hi_imm_x__RRuI_RRI = 1287,
    kulea_hi_imm_x__RuIR_URIR = 1288,
    kulea_hi_noimm__URURUR_URURUR = 1289,
    kulea_hi_noimm_sx32__URURUR_URURUR = 1290,
    kulea_hi_noimm_sx32_x__URURUR_URURUR = 1291,
    kulea_hi_noimm_x__URURUR_URURUR = 1292,
    kulea_lo_imm__URuIUR_URIUR = 1293,
    kulea_lo_imm_x__URuIUR_URIUR = 1294,
    kulea_lo_noimm__URURUR_URURUR = 1295,
    kulea_lo_noimm_x__URURUR_URURUR = 1296,
    kulepc__URURUR = 1297,
    kulepc__UR_I_R = 1298,
    kulepc_rel_ = 1299,
    kulop32i_ = 1300,
    kulop32i_optionalUPp_ = 1301,
    kulop3_imm__URIR_URIR = 1302,
    kulop3_imm_optionalUPp__URIR_URIR = 1303,
    kulop3_lut__URURUR_URURUR = 1304,
    kulop3_lut__URuIUR_URIR = 1305,
    kulop3_lut_optionalUPp__URURUR_URURUR = 1306,
    kulop3_lut_optionalUPp__URuIUR_URIR = 1307,
    kulop3_noimm__URURUR_URURUR = 1308,
    kulop3_noimm_optionalUPp__URURUR_URURUR = 1309,
    kulop_imm_ = 1310,
    kulop_imm_optionalUPp_ = 1311,
    kulop_noimm__URURUR = 1312,
    kulop_noimm_optionalUPp__URURUR = 1313,
    kumemsets_ = 1314,
    kumov_64__UR = 1315,
    kumov__UI = 1316,
    kumov__UR = 1317,
    kumov_imm64_ = 1318,
    kup2ur__Imm = 1319,
    kup2ur__URb = 1320,
    kup2ur_simple_ = 1321,
    kuplop3_1out_ = 1322,
    kuplop3_lut_1out_ = 1323,
    kuplop3_lut_1out_1reg__URURUR = 1324,
    kuplop3_lut_1out_2reg__URURUR = 1325,
    kuplop3_lut_1out_3reg__URURUR = 1326,
    kuplop3_lut_2out_ = 1327,
    kuplop3_lut_2out_1reg__URURUR = 1328,
    kuplop3_lut_2out_2reg__URURUR = 1329,
    kuplop3_lut_2out_3reg__URURUR = 1330,
    kupopc__URURUR_URUUR = 1331,
    kupopc__URuIUR_URIR = 1332,
    kuprmt__URIUR = 1333,
    kuprmt__URURUR = 1334,
    kupsetp_ = 1335,
    kupsetp_simple_ = 1336,
    kur2up__Imm = 1337,
    kur2up__URb = 1338,
    kusel_64__URIR = 1339,
    kusel_64__UUU = 1340,
    kusel__URURUR_UUU = 1341,
    kusel__URuIUR_URIR = 1342,
    kusetmaxreg__Ib_alloc = 1343,
    kusetmaxreg__Ib_dealloc = 1344,
    kusetmaxreg__URb_alloc = 1345,
    kusetmaxreg__URb_dealloc = 1346,
    kusetshmsz__FLUSH = 1347,
    kusetshmsz__Ib = 1348,
    kusetshmsz__URb = 1349,
    kusgxt__URURUR_UUU = 1350,
    kusgxt__URuIUR_URIR = 1351,
    kushf__URURUR_URURUR = 1352,
    kushf__URURuI_URRI = 1353,
    kushf__URuIUR_URIR = 1354,
    kushl__URURUR_URURUR = 1355,
    kushl__URuIUR_URIR = 1356,
    kushl_imm_ = 1357,
    kushr__URIR_URIR = 1358,
    kushr__URURUR_URURUR = 1359,
    kutmacctl_ = 1360,
    kutmacctl_URa_ = 1361,
    kutmacctl_URa_one_ = 1362,
    kutmacctl_one_ = 1363,
    kutmacmdflush_ = 1364,
    kutmaldg_URc__UUU = 1365,
    kutmaldg_URc__UUU_desc = 1366,
    kutmaldg_URc_one__UUU = 1367,
    kutmaldg_URc_one__UUU_desc = 1368,
    kutmaldg__UUU = 1369,
    kutmaldg__UUU_desc = 1370,
    kutmaldg_one__UUU = 1371,
    kutmaldg_one__UUU_desc = 1372,
    kutmapf_URc__UUU = 1373,
    kutmapf_URc__UUU_desc = 1374,
    kutmapf_URc_one__UUU = 1375,
    kutmapf_URc_one__UUU_desc = 1376,
    kutmapf__UUU = 1377,
    kutmapf__UUU_desc = 1378,
    kutmapf_one__UUU = 1379,
    kutmapf_one__UUU_desc = 1380,
    kutmaredg__UUU = 1381,
    kutmaredg__UUU_desc = 1382,
    kutmaredg_one__UUU = 1383,
    kutmaredg_one__UUU_desc = 1384,
    kutmastg__UUU = 1385,
    kutmastg__UUU_desc = 1386,
    kutmastg_one__UUU = 1387,
    kutmastg_one__UUU_desc = 1388,
    kuviadd__URURUR_UUU = 1389,
    kuviadd__URuIUR_URIR = 1390,
    kuvimnmx__URIR_URsIUR = 1391,
    kuvimnmx__UUU_URURUR = 1392,
    kuvirtcount__UR = 1393,
    kuvirtcount__imm = 1394,
    kuvirtcount_one__UR = 1395,
    kuvirtcount_one__imm = 1396,
    kviadd__RRR_RRR = 1397,
    kviadd__RUR_RUR = 1398,
    kviadd__RuIR_RIR = 1399,
    kvimnmx__RIR_RsIR = 1400,
    kvimnmx__RRR_RRR = 1401,
    kvimnmx__RUR_RUR = 1402,
    kvote_ = 1403,
    kvote_vtg_ = 1404,
    kvote_vtg_bop_ = 1405,
    kvote_vtg_cmp_ = 1406,
    kvoteu_ = 1407,
    kwarpsync__RIR = 1408,
    kwarpsync__RRR = 1409,
    kwarpsync_collective__RIR = 1410,
    kwarpsync_collective__RRR = 1411,
    kwarpsync_rel__RIR = 1412,
    kwarpsync_rel__RRR = 1413,
    kyield_inst_ = 1414,
};

enum class Pipe : std::uint16_t {
    kUnknown = 0,
    kcbu_pipe = 1,
    kfe_pipe = 2,
    kfma64lite_pipe = 3,
    kfmalighter_pipe = 4,
    kfp16_pipe = 5,
    kint_pipe = 6,
    kmio_pipe = 7,
    kttu_pipe = 8,
    kudp_pipe = 9,
};

inline constexpr std::uint32_t kNumMnemonics = 259;
inline constexpr std::uint32_t kNumVariantClasses = 1414;
inline constexpr std::uint32_t kNumPipes = 9;

// Enum-value -> name tables (index 0 = kUnknown -> "").
extern const char* const kMnemonicNames[];
extern const char* const kVariantClassNames[];
extern const char* const kPipeNames[];

inline const char* mnemonic_name(Mnemonic m) {
    const std::uint32_t i = static_cast<std::uint32_t>(m);
    return i <= kNumMnemonics ? kMnemonicNames[i] : "";
}
inline const char* variant_class_name(VariantClass v) {
    const std::uint32_t i = static_cast<std::uint32_t>(v);
    return i <= kNumVariantClasses ? kVariantClassNames[i] : "";
}
inline const char* pipe_name(Pipe p) {
    const std::uint32_t i = static_cast<std::uint32_t>(p);
    return i <= kNumPipes ? kPipeNames[i] : "";
}

// Name -> enum lookup ("" / unknown -> kUnknown).  Defined in the .cpp.
Mnemonic mnemonic_from_name(const char* name);
VariantClass variant_class_from_name(const char* name);
Pipe pipe_from_name(const char* name);

// Modifier/operand enums.
struct EnumEntry {
    const char* name;
    std::int32_t value;   // -1 = valueless (presence means print)
};
struct EnumDef {
    const char* name;
    std::uint32_t n;
    const EnumEntry* entries;
};

// Decode tables (rows' `in` args comma-joined; `out` raw string).
struct TableDef {
    const char* name;
    std::uint32_t n;
    const char* const* in;
    const char* const* out;
    bool illegal;          // *_illegal_encodings rejection table
};

// Encoding field: one or more disjoint bit ranges (MSB-first).
struct Field {
    const char* name;
    std::uint8_t width;
    std::uint8_t nranges;
    const std::uint8_t* ranges;   // flattened [hi,lo] pairs
    const char* rhs;
    std::uint8_t rhs_kind;        // 0 slot,1 slot_attr,2 opcode,
                                 // 3 num,4 star_num,5 star_slot,
                                 // 6 table_fn,7 other_fn
    std::uint8_t scale;           // decode scale (logical = field*scale)
};
// Format slot.
struct Slot {
    const char* name;
    const char* type;
    const char* dflt;             // raw default string, may be null
    bool modifier;
};
// Per-variant LEGALITY-CHECK RESULT: the first failing condition's
// error type + message, or nullopt when every condition passes.
struct CondResult {
    const char* error_type;
    const char* message;
};

// Merged per-variant legality check (one lambda per CLASS, L1i-friendly):
// takes the raw instruction word plus THIS variant's own packed
// condition-slot array (length = kVariants[i].ncondslots, keys listed in
// kVariants[i].condslots), and returns the first failing condition's
// CondResult or nullopt.  Compiled from the predicate strings at
// generation time (tools/gen_isa.py): decode never runtime-parses a
// predicate and evaluates all of a variant's conditions in one call.
using CondCheck = std::optional<CondResult> (*)(const semu::Word128&,
                                                const std::int64_t* slots);

// Legality condition (spec-derived).  `predicate` string kept for
// diagnostics/tests; evaluation happens via the variant's merged CondCheck.
struct Cond {
    const char* error;
    const char* predicate;
    const char* message;
};

inline constexpr std::uint32_t kMaxCondSlots = 17;
// Size/pipe predicate (IDEST_SIZE, ISRC_*_SIZE, VIRTUAL_QUEUE, ...).
struct Pred {
    const char* key;
    const char* value;
};

struct Variant {
    Mnemonic mnemonic;
    VariantClass variant_class;
    std::uint16_t opcode;
    Pipe pipe;
    std::uint16_t nslots;   const Slot* slots;
    std::uint16_t nfields;  const Field* fields;
    std::uint16_t nconds;   const Cond* conds;
    CondCheck check;                    // merged legality check (nullptr: none)
    std::uint16_t ncondslots;           // packed condition-slot count
    const char* const* condslots;       // this variant's condition slot names
    std::uint16_t npreds;   const Pred* preds;
    bool alternate;         // ALTERNATE CLASS (not a decode candidate)
};

// Flat storage (all rows in one array for locality).
extern const EnumDef kEnums[];       extern const std::uint32_t kNumEnums;
extern const TableDef kTables[];      extern const std::uint32_t kNumTables;
extern const Variant kVariants[];     extern const std::uint32_t kNumVariants;
// Opcode candidate index: for each of the 8192 13-bit opcodes, the
// [kOpcodeStart[op], kOpcodeStart[op+1]) slice of kVariants.
extern const std::uint32_t kOpcodeStart[8193];
extern const char* const kParameters[]; extern const std::int64_t kParameterVals[];
extern const std::uint32_t kNumParameters;
extern const char* const kConstants[]; extern const std::int64_t kConstantVals[];
extern const std::uint32_t kNumConstants;

}  // namespace semu::isa

// ---------------------------------------------------------------------------
// Generated operand-width metadata (per-variant, from `*_SIZE` predicates).
// Each variant's widths are static member functions that extract the width
// directly from the 128-bit word (no slot map / string eval at runtime).
// kSizeFns[vi][key] is the dispatch table; a nullptr entry means the variant
// has no such predicate (the renderer falls back to its default width).
namespace semu::isa::metadata {
enum SizeKey : int {
    kDest2Size = 0,   // IDEST2_SIZE
    kDestIndexRfSize = 1,   // IDEST_INDEX_RF_SIZE
    kDestSize = 2,   // IDEST_SIZE
    kLabelRaSize = 3,   // ILABEL_Ra_SIZE
    kLabelRaUrbSize = 4,   // ILABEL_Ra_URb_SIZE
    kLabelRaUrcSize = 5,   // ILABEL_Ra_URc_SIZE
    kLabelRaUrdSize = 6,   // ILABEL_Ra_URd_SIZE
    kLabelRb2Size = 7,   // ILABEL_Rb2_SIZE
    kLabelRbSize = 8,   // ILABEL_Rb_SIZE
    kLabelRbUrcSize = 9,   // ILABEL_Rb_URc_SIZE
    kLabelRcSize = 10,   // ILABEL_Rc_SIZE
    kLabelReSize = 11,   // ILABEL_Re_SIZE
    kLabelRhSize = 12,   // ILABEL_Rh_SIZE
    kLabelUraSize = 13,   // ILABEL_URa_SIZE
    kLabelUrbSize = 14,   // ILABEL_URb_SIZE
    kLabelUrcSize = 15,   // ILABEL_URc_SIZE
    kLabelUreSize = 16,   // ILABEL_URe_SIZE
    kLabelUriSize = 17,   // ILABEL_URi_SIZE
    kSourceASize = 18,   // ISRC_A_SIZE
    kSourceB2Size = 19,   // ISRC_B2_SIZE
    kSourceBIndexRfSize = 20,   // ISRC_B_INDEX_RF_SIZE
    kSourceBSize = 21,   // ISRC_B_SIZE
    kSourceCIndexRfSize = 22,   // ISRC_C_INDEX_RF_SIZE
    kSourceCSize = 23,   // ISRC_C_SIZE
    kSourceESize = 24,   // ISRC_E_SIZE
    kSourceHSize = 25,   // ISRC_H_SIZE
    kSourceISize = 26,   // ISRC_I_SIZE
    kNumSizeKeys,
};

inline constexpr const char* const kSizeKeyNames[kNumSizeKeys] = {
    "IDEST2_SIZE",
    "IDEST_INDEX_RF_SIZE",
    "IDEST_SIZE",
    "ILABEL_Ra_SIZE",
    "ILABEL_Ra_URb_SIZE",
    "ILABEL_Ra_URc_SIZE",
    "ILABEL_Ra_URd_SIZE",
    "ILABEL_Rb2_SIZE",
    "ILABEL_Rb_SIZE",
    "ILABEL_Rb_URc_SIZE",
    "ILABEL_Rc_SIZE",
    "ILABEL_Re_SIZE",
    "ILABEL_Rh_SIZE",
    "ILABEL_URa_SIZE",
    "ILABEL_URb_SIZE",
    "ILABEL_URc_SIZE",
    "ILABEL_URe_SIZE",
    "ILABEL_URi_SIZE",
    "ISRC_A_SIZE",
    "ISRC_B2_SIZE",
    "ISRC_B_INDEX_RF_SIZE",
    "ISRC_B_SIZE",
    "ISRC_C_INDEX_RF_SIZE",
    "ISRC_C_SIZE",
    "ISRC_E_SIZE",
    "ISRC_H_SIZE",
    "ISRC_I_SIZE",
};

// Key name -> column index (std::string_view include in the header).
inline int size_key_index(std::string_view name) {
    for (int i = 0; i < kNumSizeKeys; ++i)
        if (name == kSizeKeyNames[i]) return i;
    return -1;
}

using SizeFn = std::int64_t (*)(const semu::Word128&);
extern const SizeFn kSizeFns[][kNumSizeKeys];

// One nested namespace per mnemonic; one struct per variant class (slug).
namespace MOV {
    // one struct per variant (slug = variant class)
    struct mov_64__RR;
    struct mov__RR;
    struct mov_imm64_;
    struct mov__RI;
    struct mov_indexedRF_IRFd__Rb;
    struct mov_indexedRF_IRFd__Ib;
    struct mov_64__RU;
    struct mov__RU;
    struct mov_nonconformity__RU;
    struct mov_indexedRF_Rd_;
}  // namespace MOV
namespace P2R {
    // one struct per variant (slug = variant class)
    struct p2r__RRR_RRR;
    struct p2r__RuIR_RIR;
    struct p2r_simple_;
    struct p2r__RUR_RUR;
}  // namespace P2R
namespace R2P {
    // one struct per variant (slug = variant class)
    struct r2p__RRR;
    struct r2p__RIR;
    struct r2p__RUR;
}  // namespace R2P
namespace SEL {
    // one struct per variant (slug = variant class)
    struct sel__RRR_RRR;
    struct sel_64__RIR;
    struct sel_64__RRR;
    struct sel__RuIR_RIR;
    struct sel__RUR_RUR;
    struct sel_64__RUR;
}  // namespace SEL
namespace FSEL {
    // one struct per variant (slug = variant class)
    struct fsel__RRR_RRR;
    struct fsel__RIR_RIR;
    struct fsel__RUR_RUR;
}  // namespace FSEL
namespace FMNMX {
    // one struct per variant (slug = variant class)
    struct fmnmx__RRR_RRR;
    struct fmnmx_pred__RRR_RRR;
    struct fmnmx__RIR_RIR;
    struct fmnmx_pred__RIR_RIR;
    struct fmnmx__RUR_RUR;
    struct fmnmx_pred__RUR_RUR;
}  // namespace FMNMX
namespace FSET {
    // one struct per variant (slug = variant class)
    struct fset__RRR_RRR;
    struct fset_simple__RRR_RRR;
    struct fset__RIR_RIR;
    struct fset_simple__RIR_RIR;
    struct fset__RUR_RUR;
    struct fset_simple__RUR_RUR;
}  // namespace FSET
namespace FSETP {
    // one struct per variant (slug = variant class)
    struct fsetp__RRR_RRR;
    struct fsetp_simple__RRR_RRR;
    struct fsetp__RIR_RIR;
    struct fsetp_simple__RIR_RIR;
    struct fsetp__RUR_RUR;
    struct fsetp_simple__RUR_RUR;
}  // namespace FSETP
namespace ISETP {
    // one struct per variant (slug = variant class)
    struct isetp_64__RRR_RRR_EX;
    struct isetp_64__RRR_RRR_noEX;
    struct isetp_64_simple__RRR_RRR_EX;
    struct isetp_64_simple__RRR_RRR_noEX;
    struct isetp__RRR_RRR_EX;
    struct isetp__RRR_RRR_noEX;
    struct isetp_simple__RRR_RRR_EX;
    struct isetp_simple__RRR_RRR_noEX;
    struct isetp_64__RsIR_RIR_EX;
    struct isetp_64__RsIR_RIR_noEX;
    struct isetp_64_simple__RsIR_RIR_EX;
    struct isetp_64_simple__RsIR_RIR_noEX;
    struct isetp__RsIR_RIR_EX;
    struct isetp__RsIR_RIR_noEX;
    struct isetp_simple__RsIR_RIR_EX;
    struct isetp_simple__RsIR_RIR_noEX;
    struct isetp_64__RUR_RUR_EX;
    struct isetp_64__RUR_RUR_noEX;
    struct isetp_64_simple__RUR_RUR_EX;
    struct isetp_64_simple__RUR_RUR_noEX;
    struct isetp__RUR_RUR_EX;
    struct isetp__RUR_RUR_noEX;
    struct isetp_simple__RUR_RUR_EX;
    struct isetp_simple__RUR_RUR_noEX;
}  // namespace ISETP
namespace IADD3 {
    // one struct per variant (slug = variant class)
    struct iadd3_noimm__RRR_RRR;
    struct iadd3_x_noimm__RRR_RRR;
    struct iadd3_imm__RsIR_RIR;
    struct iadd3_x_imm__RIR_RIR;
    struct iadd3_noimm__RUR_RUR;
    struct iadd3_x_noimm__RUR_RUR;
}  // namespace IADD3
namespace ISCADD {
    // one struct per variant (slug = variant class)
    struct iscadd_noimm__RRR_RRR;
    struct iscadd_imm__RIR_RIR;
    struct iscadd_noimm__RUR_RUR;
}  // namespace ISCADD
namespace LEA {
    // one struct per variant (slug = variant class)
    struct lea_hi_noimm__RRR_RRR;
    struct lea_hi_noimm_sx32__RRR_RRR;
    struct lea_hi_noimm_sx32_x__RRR_RRR;
    struct lea_hi_noimm_x__RRR_RRR;
    struct lea_lo_noimm__RRR_RRR;
    struct lea_lo_noimm_x__RRR_RRR;
    struct lea_hi_imm__RRuI_RRI;
    struct lea_hi_imm_x__RRuI_RRI;
    struct lea_hi_imm__RuIR_RIR;
    struct lea_hi_imm_sx32__RuIR_RIR;
    struct lea_hi_imm_sx32_x__RuIR_RIR;
    struct lea_hi_imm_x__RuIR_RIR;
    struct lea_lo_imm__RuIR_RIR;
    struct lea_lo_imm_x__RuIR_RIR;
    struct lea_hi_noimm__RUR_RUR;
    struct lea_hi_noimm_sx32__RUR_RUR;
    struct lea_hi_noimm_sx32_x__RUR_RUR;
    struct lea_hi_noimm_x__RUR_RUR;
    struct lea_lo_noimm__RUR_RUR;
    struct lea_lo_noimm_x__RUR_RUR;
}  // namespace LEA
namespace LOP {
    // one struct per variant (slug = variant class)
    struct lop_noimm__RRR_RRR;
    struct lop_noimm_optionalPp__RRR_RRR;
    struct lop_imm_;
    struct lop_imm_optionalPp_;
    struct lop_noimm__RUR_RUR;
    struct lop_noimm_optionalPp__RUR_RUR;
}  // namespace LOP
namespace LOP3 {
    // one struct per variant (slug = variant class)
    struct lop3_lut__RRR_RRR;
    struct lop3_lut_optionalPp__RRR_RRR;
    struct lop3_noimm__RRR_RRR;
    struct lop3_noimm_optionalPp__RRR_RRR;
    struct lop3_imm__RIR_RIR;
    struct lop3_imm_optionalPp__RIR_RIR;
    struct lop3_lut__RuIR_RIR;
    struct lop3_lut_optionalPp__RuIR_RIR;
    struct lop3_lut__RUR_RUR;
    struct lop3_lut_optionalPp__RUR_RUR;
    struct lop3_noimm__RUR_RUR;
    struct lop3_noimm_optionalPp__RUR_RUR;
}  // namespace LOP3
namespace IABS {
    // one struct per variant (slug = variant class)
    struct iabs__RRR_R;
    struct iabs__RsIR_I;
    struct iabs__RUR_UR;
}  // namespace IABS
namespace PRMT {
    // one struct per variant (slug = variant class)
    struct prmt__RRR_RRR;
    struct prmt__RRuI_RRI;
    struct prmt__RuIR_RIR;
    struct prmt__RUR_RUR;
    struct prmt__RRU_RRU;
}  // namespace PRMT
namespace IMNMX {
    // one struct per variant (slug = variant class)
    struct imnmx_64__RRR_RRR;
    struct imnmx_64_nopred__RRR_RRR;
    struct imnmx__RRR_RRR;
    struct imnmx_nopred__RRR_RRR;
    struct imnmx_64__RIR_RsIR;
    struct imnmx_64_nopred__RIR_RsIR;
    struct imnmx__RIR_RsIR;
    struct imnmx_nopred__RIR_RsIR;
    struct imnmx_64__RUR_RUR;
    struct imnmx_64_nopred__RUR_RUR;
    struct imnmx__RUR_RUR;
    struct imnmx_nopred__RUR_RUR;
}  // namespace IMNMX
namespace SHF {
    // one struct per variant (slug = variant class)
    struct shf__RRR_RRR;
    struct shf__RRuI_RRI;
    struct shf__RuIR_RIR;
    struct shf__RUR_RUR;
    struct shf__RRU_RRU;
}  // namespace SHF
namespace SHL {
    // one struct per variant (slug = variant class)
    struct shl__RRR_RRR;
    struct shl_imm_;
    struct shl__RuIR_RIR;
    struct shl__RUR_RUR;
}  // namespace SHL
namespace SHR {
    // one struct per variant (slug = variant class)
    struct shr__RRR_RRR;
    struct shr__RIR_RIR;
    struct shr__RUR_RUR;
}  // namespace SHR
namespace SGXT {
    // one struct per variant (slug = variant class)
    struct sgxt__RRR_RRR;
    struct sgxt__RuIR_RIR;
    struct sgxt__RUR_RUR;
}  // namespace SGXT
namespace BMSK {
    // one struct per variant (slug = variant class)
    struct bmsk__RRR_RRR;
    struct bmsk__RuIR_RIR;
    struct bmsk__RUR_RUR;
}  // namespace BMSK
namespace PLOP3 {
    // one struct per variant (slug = variant class)
    struct plop3_lut_1out_1reg__RRR;
    struct plop3_lut_2out_1reg__RRR;
    struct plop3_lut_1out_2reg__RRR;
    struct plop3_lut_2out_2reg__RRR;
    struct plop3_lut_1out_3reg__RRR;
    struct plop3_lut_2out_3reg__RRR;
    struct plop3_lut_1out_1reg__RUR;
    struct plop3_lut_2out_1reg__RUR;
    struct plop3_lut_1out_2reg__RUR;
    struct plop3_lut_2out_2reg__RUR;
    struct plop3_lut_1out_3reg__RUR;
    struct plop3_lut_2out_3reg__RUR;
}  // namespace PLOP3
namespace FMUL {
    // one struct per variant (slug = variant class)
    struct fmul__RRR_RR;
    struct fmul__RIR_RI;
    struct fmul__RUR_RU;
}  // namespace FMUL
namespace FADD {
    // one struct per variant (slug = variant class)
    struct fadd__RRR_RR;
    struct fadd__RRI_RI;
    struct fadd__RRU_RU;
}  // namespace FADD
namespace FHADD {
    // one struct per variant (slug = variant class)
    struct fhadd__RR;
    struct fhadd__RU;
}  // namespace FHADD
namespace FFMA {
    // one struct per variant (slug = variant class)
    struct ffma__RRR_RRR;
    struct ffma__RRI_RRI;
    struct ffma__RIR_RIR;
    struct ffma__RUR_RUR;
    struct ffma__RRU_RRU;
}  // namespace FFMA
namespace FHFMA {
    // one struct per variant (slug = variant class)
    struct fhfma__RRR;
    struct fhfma__RUR;
    struct fhfma__RRU;
}  // namespace FHFMA
namespace IMAD {
    // one struct per variant (slug = variant class)
    struct imad__RRR_RRR;
    struct imad_pseudo__RRR_RRR;
    struct imad_x__RRR_RRR;
    struct imad_x_pseudo__RRR_RRR;
    struct imad_wide__RRR_RRR;
    struct imad_wide_pseudo__RRR_RRR;
    struct imad_wide_x__RRR_RRR;
    struct imad_wide_x_pseudo__RRR_RRR;
    struct imad_hi__RRR_RRR;
    struct imad_hi_pseudo__RRR_RRR;
    struct imad_hi_x__RRR_RRR;
    struct imad_hi_x_pseudo__RRR_RRR;
    struct imad__RRsI_RRI;
    struct imad_pseudo__RRsI_RRI;
    struct imad_x__RRsI_RRI;
    struct imad_x_pseudo__RRsI_RRI;
    struct imad__RsIR_RIR;
    struct imad_pseudo__RsIR_RIR;
    struct imad_x__RsIR_RIR;
    struct imad_x_pseudo__RsIR_RIR;
    struct imad_wide__RsIR_RIR;
    struct imad_wide_pseudo__RsIR_RIR;
    struct imad_wide_x__RsIR_RIR;
    struct imad_wide_x_pseudo__RsIR_RIR;
    struct imad_hi__RsIR_RIR;
    struct imad_hi_pseudo__RsIR_RIR;
    struct imad_hi_x__RsIR_RIR;
    struct imad_hi_x_pseudo__RsIR_RIR;
    struct imad__RUR_RUR;
    struct imad_pseudo__RUR_RUR;
    struct imad_x__RUR_RUR;
    struct imad_x_pseudo__RUR_RUR;
    struct imad_wide__RUR_RUR;
    struct imad_wide_pseudo__RUR_RUR;
    struct imad_wide_x__RUR_RUR;
    struct imad_wide_x_pseudo__RUR_RUR;
    struct imad_hi__RUR_RUR;
    struct imad_hi_pseudo__RUR_RUR;
    struct imad_hi_x__RUR_RUR;
    struct imad_hi_x_pseudo__RUR_RUR;
    struct imad__RRU_RRU;
    struct imad_pseudo__RRU_RRU;
    struct imad_x__RRU_RRU;
    struct imad_x_pseudo__RRU_RRU;
    struct imad_wide__RRU_RRU;
    struct imad_wide_pseudo__RRU_RRU;
    struct imad_wide_x__RRU_RRU;
    struct imad_wide_x_pseudo__RRU_RRU;
    struct imad_hi__RRU_RRU;
    struct imad_hi_pseudo__RRU_RRU;
    struct imad_hi_x__RRU_RRU;
    struct imad_hi_x_pseudo__RRU_RRU;
}  // namespace IMAD
namespace IMUL {
    // one struct per variant (slug = variant class)
    struct imul__RRR_RRR;
    struct imul_wide__RRR_RRR;
    struct imul__RsIR_RIR;
    struct imul_wide__RsIR_RIR;
    struct imul__RUR_RUR;
    struct imul_wide__RUR_RUR;
}  // namespace IMUL
namespace IDP {
    // one struct per variant (slug = variant class)
    struct idp_2a__R;
    struct idp_4a__R;
    struct idp_2a__URb;
    struct idp_4a__URb;
}  // namespace IDP
namespace IDP4A {
    // one struct per variant (slug = variant class)
    struct idp4a__R;
    struct idp4a__URb;
}  // namespace IDP4A
namespace DMUL {
    // one struct per variant (slug = variant class)
    struct dmul__RRR_RR;
    struct dmul__RsIR_RI;
    struct dmul__RUR_RU;
}  // namespace DMUL
namespace DADD {
    // one struct per variant (slug = variant class)
    struct dadd__RRR_RR;
    struct dadd__RRsI_RI;
    struct dadd__RRU_RU;
}  // namespace DADD
namespace DSETP {
    // one struct per variant (slug = variant class)
    struct dsetp__RRR_RR;
    struct dsetp_simple__RRR_RR;
    struct dsetp__RRsI_RI;
    struct dsetp_simple__RRsI_RI;
    struct dsetp__RRU_RU;
    struct dsetp_simple__RRU_RU;
}  // namespace DSETP
namespace DFMA {
    // one struct per variant (slug = variant class)
    struct dfma__RRR_RRR;
    struct dfma__RRsI_RRI;
    struct dfma__RsIR_RIR;
    struct dfma__RUR_RUR;
    struct dfma__RRU_RRU;
}  // namespace DFMA
namespace CLMAD {
    // one struct per variant (slug = variant class)
    struct clmad__RRR_RRR;
    struct clmad__RUR_RUR;
    struct clmad__RRU_RRU;
}  // namespace CLMAD
namespace HADD2 {
    // one struct per variant (slug = variant class)
    struct hadd2_F32__RR;
    struct hadd2_F32_fixed__RR;
    struct hadd2__RR;
    struct hadd2_fixed__RR;
    struct hadd2_F32__RI;
    struct hadd2_F32i_;
    struct hadd2__RI;
    struct hadd2_fixed__RI;
    struct hadd2_F32__RU;
    struct hadd2_F32_fixed__RU;
    struct hadd2__RU;
    struct hadd2_fixed__RU;
}  // namespace HADD2
namespace HFMA2 {
    // one struct per variant (slug = variant class)
    struct hfma2__RRR;
    struct hfma2_fixed__RRR;
    struct hfma2_mma__RRR;
    struct hfma2_mma_relu__RRR;
    struct hfma2_relu__RRR;
    struct hfma2_relu_fixed__RRR;
    struct hfma2__RRI;
    struct hfma2_fixed__RRI;
    struct hfma2_mma__RRI;
    struct hfma2_mma_relu__RRI;
    struct hfma2_relu__RRI;
    struct hfma2_relu_fixed__RRI;
    struct hfma2__RIR;
    struct hfma2_fixed__RIR;
    struct hfma2_mma__RIR;
    struct hfma2_mma_relu__RIR;
    struct hfma2_relu__RIR;
    struct hfma2_relu_fixed__RIR;
    struct hfma2__RUR;
    struct hfma2_fixed__RUR;
    struct hfma2_mma__RUR;
    struct hfma2_mma_relu__RUR;
    struct hfma2_relu__RUR;
    struct hfma2_relu_fixed__RUR;
    struct hfma2__RRU;
    struct hfma2_fixed__RRU;
    struct hfma2_mma__RRU;
    struct hfma2_mma_relu__RRU;
    struct hfma2_relu__RRU;
    struct hfma2_relu_fixed__RRU;
}  // namespace HFMA2
namespace HMUL2 {
    // one struct per variant (slug = variant class)
    struct hmul2__RR;
    struct hmul2_fixed__RR;
    struct hmul2__RI;
    struct hmul2_fixed__RI;
    struct hmul2__RU;
    struct hmul2_fixed__RU;
}  // namespace HMUL2
namespace HSET2 {
    // one struct per variant (slug = variant class)
    struct hset2__RR;
    struct hset2_fixed__RR;
    struct hset2_noBop__RR;
    struct hset2_noBop_fixed__RR;
    struct hset2__RI;
    struct hset2_fixed__RI;
    struct hset2_noBop__RI;
    struct hset2_noBop_fixed__RI;
    struct hset2__RU;
    struct hset2_fixed__RU;
    struct hset2_noBop__RU;
    struct hset2_noBop_fixed__RU;
}  // namespace HSET2
namespace HSETP2 {
    // one struct per variant (slug = variant class)
    struct hsetp2__RR;
    struct hsetp2_fixed__RR;
    struct hsetp2_noBop__RR;
    struct hsetp2_noBop_fixed__RR;
    struct hsetp2__RI;
    struct hsetp2_fixed__RI;
    struct hsetp2_noBop__RI;
    struct hsetp2_noBop_fixed__RI;
    struct hsetp2__RU;
    struct hsetp2_fixed__RU;
    struct hsetp2_noBop__RU;
    struct hsetp2_noBop_fixed__RU;
}  // namespace HSETP2
namespace IADD {
    // one struct per variant (slug = variant class)
    struct iadd_64_noimm__RRR_RRR;
    struct iadd_64_x_noimm__RRR_RRR;
    struct iadd_noimm__RRR_RRR;
    struct iadd_x_noimm__RRR_RRR;
    struct iadd_64_imm__RsIR_RIR;
    struct iadd_64_x_imm__RIR_RIR;
    struct iadd_imm__RsIR_RIR;
    struct iadd_x_imm__RIR_RIR;
    struct iadd_64_noimm__RUR_RUR;
    struct iadd_64_x_noimm__RUR_RUR;
    struct iadd_noimm__RUR_RUR;
    struct iadd_x_noimm__RUR_RUR;
}  // namespace IADD
namespace VIADD {
    // one struct per variant (slug = variant class)
    struct viadd__RRR_RRR;
    struct viadd__RuIR_RIR;
    struct viadd__RUR_RUR;
}  // namespace VIADD
namespace IMMA {
    // one struct per variant (slug = variant class)
    struct imma_;
    struct imma_sp_;
}  // namespace IMMA
namespace I2I {
    // one struct per variant (slug = variant class)
    struct i2i__RRR_RRR;
    struct i2i__RsIR_RIR;
    struct i2i__RUR_RUR;
}  // namespace I2I
namespace I2IP {
    // one struct per variant (slug = variant class)
    struct i2ip_24__RRR_RRR;
    struct i2ip_24_relu__RRR_RRR;
    struct i2ip_28__RRR_RRR;
    struct i2ip_28_relu__RRR_RRR;
    struct i2ip__RRR_RRR;
    struct i2ip_relu__RRR_RRR;
    struct i2ip_24__RsIR_RIR;
    struct i2ip_24_relu__RsIR_RIR;
    struct i2ip_28__RsIR_RIR;
    struct i2ip_28_relu__RsIR_RIR;
    struct i2ip__RsIR_RIR;
    struct i2ip_relu__RsIR_RIR;
    struct i2ip_24__RUR_RUR;
    struct i2ip_24_relu__RUR_RUR;
    struct i2ip_28__RUR_RUR;
    struct i2ip_28_relu__RUR_RUR;
    struct i2ip__RUR_RUR;
    struct i2ip_relu__RUR_RUR;
}  // namespace I2IP
namespace MOVM {
    // one struct per variant (slug = variant class)
    struct movm_;
}  // namespace MOVM
namespace HMMA {
    // one struct per variant (slug = variant class)
    struct hmma_sparse_;
    struct hmma_x8_;
    struct hmma_sparse_indexedRF_;
    struct hmma_x8_indexedRF_;
}  // namespace HMMA
namespace F2FP {
    // one struct per variant (slug = variant class)
    struct f2fp_4b_upconvert__RRR;
    struct f2fp_8b_upconvert__RRR;
    struct f2fp_E8_upconvert__RRR;
    struct f2fp__RRR;
    struct f2fp_default_dst_src__RRR;
    struct f2fp_f16_to_4b_downconvert__RRR;
    struct f2fp_f16_to_8b_downconvert__RRR;
    struct f2fp_f16_to_mx8_downconvert_scale__RRR;
    struct f2fp_f32_to_4b_downconvert__RRR;
    struct f2fp_f32_to_8b_downconvert__RRR;
    struct f2fp_f32_to_mx8_downconvert_scale__RRR;
    struct f2fp_merge_c__RRR;
    struct f2fp_merge_c_default_dst_src__RRR;
    struct f2fp_tf32__RRR;
    struct f2fp_tf32_default_src__RRR;
    struct f2fp_f16_to_4b_downconvert__RRI;
    struct f2fp_f16_to_8b_downconvert__RRI;
    struct f2fp_f16_to_mx8_downconvert_scale__RRI;
    struct f2fp_f32_to_4b_downconvert__RRI;
    struct f2fp_f32_to_8b_downconvert__RRI;
    struct f2fp_f32_to_mx8_downconvert_scale__RRI;
    struct f2fp_merge_c__RRI;
    struct f2fp_merge_c_default_dst_src__RRI;
    struct f2fp_4b_upconvert_scale__RRR;
    struct f2fp_8b_upconvert_scale__RRR;
    struct f2fp_4b_upconvert__RIR;
    struct f2fp_8b_upconvert__RIR;
    struct f2fp_E8_upconvert__RIR;
    struct f2fp__RIR;
    struct f2fp_default_dst_src__RIR;
    struct f2fp_f16_to_4b_downconvert__RIR;
    struct f2fp_f16_to_8b_downconvert__RIR;
    struct f2fp_f16_to_mx8_downconvert_scale__RIR;
    struct f2fp_f32_to_4b_downconvert__RIR;
    struct f2fp_f32_to_8b_downconvert__RIR;
    struct f2fp_f32_to_mx8_downconvert_scale__RIR;
    struct f2fp_merge_c__RIR;
    struct f2fp_merge_c_default_dst_src__RIR;
    struct f2fp_tf32__RIR;
    struct f2fp_tf32_default_src__RIR;
    struct f2fp_4b_upconvert_scale__RIR;
    struct f2fp_8b_upconvert_scale__RIR;
    struct f2fp_4b_upconvert_scale__RRI;
    struct f2fp_8b_upconvert_scale__RRI;
    struct f2fp_4b_upconvert_scale__RUR;
    struct f2fp_8b_upconvert_scale__RUR;
    struct f2fp_4b_upconvert_scale__RRU;
    struct f2fp_8b_upconvert_scale__RRU;
    struct f2fp_4b_upconvert__RUR;
    struct f2fp_8b_upconvert__RUR;
    struct f2fp_E8_upconvert__RUR;
    struct f2fp__RUR;
    struct f2fp_default_dst_src__RUR;
    struct f2fp_f16_to_4b_downconvert__RUR;
    struct f2fp_f16_to_8b_downconvert__RUR;
    struct f2fp_f16_to_mx8_downconvert_scale__RUR;
    struct f2fp_f32_to_4b_downconvert__RUR;
    struct f2fp_f32_to_8b_downconvert__RUR;
    struct f2fp_f32_to_mx8_downconvert_scale__RUR;
    struct f2fp_merge_c__RUR;
    struct f2fp_merge_c_default_dst_src__RUR;
    struct f2fp_tf32__RUR;
    struct f2fp_tf32_default_src__RUR;
    struct f2fp_f16_to_4b_downconvert__RRU;
    struct f2fp_f16_to_8b_downconvert__RRU;
    struct f2fp_f16_to_mx8_downconvert_scale__RRU;
    struct f2fp_f32_to_4b_downconvert__RRU;
    struct f2fp_f32_to_8b_downconvert__RRU;
    struct f2fp_f32_to_mx8_downconvert_scale__RRU;
    struct f2fp_merge_c__RRU;
    struct f2fp_merge_c_default_dst_src__RRU;
}  // namespace F2FP
namespace DMMA {
    // one struct per variant (slug = variant class)
    struct dmma_;
}  // namespace DMMA
namespace HMNMX2 {
    // one struct per variant (slug = variant class)
    struct hmnmx2__RRR;
    struct hmnmx2_fixed__RRR;
    struct hmnmx2_pred__RRR;
    struct hmnmx2_pred_fixed__RRR;
    struct hmnmx2__RIR;
    struct hmnmx2_fixed__RIR;
    struct hmnmx2_pred__RIR;
    struct hmnmx2_pred_fixed__RIR;
    struct hmnmx2__RUR;
    struct hmnmx2_fixed__RUR;
    struct hmnmx2_pred__RUR;
    struct hmnmx2_pred_fixed__RUR;
}  // namespace HMNMX2
namespace F2IP {
    // one struct per variant (slug = variant class)
    struct f2ip__RRR;
    struct f2ip__RRI;
    struct f2ip__RIR;
    struct f2ip__RUR;
    struct f2ip__RRU;
}  // namespace F2IP
namespace I2FP {
    // one struct per variant (slug = variant class)
    struct i2fp__RRR;
    struct i2fp__RsIR;
    struct i2fp__RuIR;
    struct i2fp__RUR;
}  // namespace I2FP
namespace VIMNMX {
    // one struct per variant (slug = variant class)
    struct vimnmx__RRR_RRR;
    struct vimnmx__RIR_RsIR;
    struct vimnmx__RUR_RUR;
}  // namespace VIMNMX
namespace QMMA {
    // one struct per variant (slug = variant class)
    struct qmma_;
    struct qmma_rowcol_;
    struct qmma_sp_;
    struct qmma_sp_rowcol_;
    struct qmma_scale_;
    struct qmma_sp_scale_;
}  // namespace QMMA
namespace R2UR {
    // one struct per variant (slug = variant class)
    struct r2ur__OR;
    struct r2ur__noOR;
    struct r2ur_nonconformity__OR;
    struct r2ur_nonconformity__noOR;
}  // namespace R2UR
namespace FLO {
    // one struct per variant (slug = variant class)
    struct flo__RRR_RRR;
    struct flo__RuIR_RIR;
    struct flo__RUR_RUR;
}  // namespace FLO
namespace BREV {
    // one struct per variant (slug = variant class)
    struct brev__RRR_RRR;
    struct brev__RuIR_RIR;
    struct brev__RUR_RUR;
}  // namespace BREV
namespace FCHK {
    // one struct per variant (slug = variant class)
    struct fchk__RRR_RR;
    struct fchk__RIR_RI;
    struct fchk__RUR_RU;
}  // namespace FCHK
namespace F2F {
    // one struct per variant (slug = variant class)
    struct f2f_f32_downconvert__RRR_RRR;
    struct f2f_f32_upconvert__RRR_RRR;
    struct f2f_f32_upconvert_swap__RRR_RRR;
    struct f2f_f64_downconvert__RRR_RRR;
    struct f2f_f64_upconvert__R_R16_R_RRR;
    struct f2f_f64_upconvert__R_R32_R_RRR;
    struct f2f_f64_upconvert_swap__R_R16_R_RRR;
    struct f2f_f64_upconvert_swap__R_R32_R_RRR;
    struct f2f_f32_downconvert__RIR_RIR;
    struct f2f_f32_upconvert__RIR_RIR;
    struct f2f_f32_upconvert_swap__RIR_RIR;
    struct f2f_f64_downconvert__RIR_RIR;
    struct f2f_f64_upconvert__R_32I_R_RIR;
    struct f2f_f64_upconvert__R_I16_R_RIR;
    struct f2f_f64_upconvert_swap__R_32I_R_RIR;
    struct f2f_f64_upconvert_swap__R_I16_R_RIR;
    struct f2f_f32_downconvert__RUR_RUR;
    struct f2f_f32_upconvert__RUR_RUR;
    struct f2f_f32_upconvert_swap__RUR_RUR;
    struct f2f_f64_downconvert__RUR_RUR;
    struct f2f_f64_upconvert__R_UR16_R_RUR;
    struct f2f_f64_upconvert__R_UR32_R_RUR;
    struct f2f_f64_upconvert_swap__R_UR16_R_RUR;
    struct f2f_f64_upconvert_swap__R_UR32_R_RUR;
}  // namespace F2F
namespace F2I {
    // one struct per variant (slug = variant class)
    struct f2i__Rb_16b;
    struct f2i__Rb_32b;
    struct f2i__Rb_bf16;
    struct f2i_swap__Rb_16b;
    struct f2i_swap__Rb_32b;
    struct f2i_swap__Rb_bf16;
    struct f2i_Rd64__Rb_16b;
    struct f2i_Rd64__Rb_32b;
    struct f2i_Rd64__Rb_64b;
    struct f2i_Rd64__Rb_bf16;
    struct f2i_Rd64_swap__Rb_16b;
    struct f2i_Rd64_swap__Rb_32b;
    struct f2i_Rd64_swap__Rb_64b;
    struct f2i_Rd64_swap__Rb_bf16;
    struct f2i__Rb_64b;
    struct f2i_swap__Rb_64b;
    struct f2i__IU_32b;
    struct f2i__Ib_16b;
    struct f2i__Ib_bf16;
    struct f2i_swap__IU_32b;
    struct f2i_swap__Ib_16b;
    struct f2i_swap__Ib_bf16;
    struct f2i_Rd64__IU_32b;
    struct f2i_Rd64__Ib_16b;
    struct f2i_Rd64__Ib_64b;
    struct f2i_Rd64__Ib_bf16;
    struct f2i_Rd64_swap__IU_32b;
    struct f2i_Rd64_swap__Ib_16b;
    struct f2i_Rd64_swap__Ib_64b;
    struct f2i_Rd64_swap__Ib_bf16;
    struct f2i__Ib_64b;
    struct f2i_swap__Ib_64b;
    struct f2i__URb_16b;
    struct f2i__URb_32b;
    struct f2i__URb_bf16;
    struct f2i_swap__URb_16b;
    struct f2i_swap__URb_32b;
    struct f2i_swap__URb_bf16;
    struct f2i_Rd64__URb_16b;
    struct f2i_Rd64__URb_32b;
    struct f2i_Rd64__URb_64b;
    struct f2i_Rd64__URb_bf16;
    struct f2i_Rd64_swap__URb_16b;
    struct f2i_Rd64_swap__URb_32b;
    struct f2i_Rd64_swap__URb_64b;
    struct f2i_Rd64_swap__URb_bf16;
    struct f2i__URb_64b;
    struct f2i_swap__URb_64b;
}  // namespace F2I
namespace I2F {
    // one struct per variant (slug = variant class)
    struct i2f__Rb_16b;
    struct i2f__Rb_32b;
    struct i2f__Rb_8b;
    struct i2f_Rd64__Rb_16b;
    struct i2f_Rd64__Rb_32b;
    struct i2f_Rd64__Rb_64b;
    struct i2f_Rd64__Rb_8b;
    struct i2f__Rb_64b;
    struct i2f__IS_32b;
    struct i2f__IU_32b;
    struct i2f_Rd64__IS_32b;
    struct i2f_Rd64__IS_64b;
    struct i2f_Rd64__IU_32b;
    struct i2f_Rd64__IU_64b;
    struct i2f__IS_64b;
    struct i2f__IU_64b;
    struct i2f__UR_16b;
    struct i2f__UR_32b;
    struct i2f__UR_8b;
    struct i2f_Rd64__UR_16b;
    struct i2f_Rd64__UR_32b;
    struct i2f_Rd64__UR_64b;
    struct i2f_Rd64__UR_8b;
    struct i2f__UR_64b;
}  // namespace I2F
namespace FRND {
    // one struct per variant (slug = variant class)
    struct frnd__bf16_R;
    struct frnd__f16_R;
    struct frnd__f32_R;
    struct frnd_swap__bf16_R;
    struct frnd_swap__f16_R;
    struct frnd_swap__f32_R;
    struct frnd__f64_R;
    struct frnd_swap__f64_R;
    struct frnd__bf16_I;
    struct frnd__f16_I;
    struct frnd__f32_I;
    struct frnd_swap__bf16_I;
    struct frnd_swap__f16_I;
    struct frnd_swap__f32_I;
    struct frnd__f64_I;
    struct frnd_swap__f64_I;
    struct frnd__bf16_URb;
    struct frnd__f16_URb;
    struct frnd__f32_URb;
    struct frnd_swap__bf16_URb;
    struct frnd_swap__f16_URb;
    struct frnd_swap__f32_URb;
    struct frnd__f64_URb;
    struct frnd_swap__f64_URb;
}  // namespace FRND
namespace MUFU {
    // one struct per variant (slug = variant class)
    struct mufu__RRR_RR;
    struct mufu_fp16__RR;
    struct mufu_fp16_swap__RR;
    struct mufu__RIR_RI;
    struct mufu_fp16__RI;
    struct mufu__RUR_RU;
    struct mufu_fp16__RU;
    struct mufu_fp16_swap__RU;
}  // namespace MUFU
namespace POPC {
    // one struct per variant (slug = variant class)
    struct popc__RRR_RRR;
    struct popc__RuIR_RIR;
    struct popc__RUR_RUR;
}  // namespace POPC
namespace B2R {
    // one struct per variant (slug = variant class)
    struct b2r__BAR;
    struct b2r__RESULT;
    struct b2r__WARP;
}  // namespace B2R
namespace BAR {
    // one struct per variant (slug = variant class)
    struct bar__ARV_RR_RR;
    struct bar__RED_RR_RR;
    struct bar__RED_dfrBlk_RR_RR;
    struct bar__SCAN_RR_RR;
    struct bar__SYNC_RR_RR;
    struct bar__SYNC_dfrBlk_RR_RR;
    struct bar__ARV_RI_RI;
    struct bar__RED_RI_optionalCount_RI;
    struct bar__RED_dfrBlk_RI_optionalCount_RI;
    struct bar__SCAN_RI_RI;
    struct bar__SYNC_RI_optionalCount_RI;
    struct bar__SYNC_dfrBlk_RI_optionalCount_RI;
    struct bar__ARV_IR_IR;
    struct bar__RED_IR_optionalCount_IR;
    struct bar__RED_dfrBlk_IR_optionalCount_IR;
    struct bar__SCAN_IR_IR;
    struct bar__SYNC_IR_optionalCount_IR;
    struct bar__SYNC_dfrBlk_IR_optionalCount_IR;
    struct bar__ARV_II_II;
    struct bar__RED_II_optionalCount_II;
    struct bar__RED_dfrBlk_II_optionalCount_II;
    struct bar__SCAN_II_II;
    struct bar__SYNCALL_dfrBlk_noSrc_II;
    struct bar__SYNCALL_noSrc_II;
    struct bar__SYNC_II_optionalCount_II;
    struct bar__SYNC_dfrBlk_II_optionalCount_II;
}  // namespace BAR
namespace R2B {
    // one struct per variant (slug = variant class)
    struct r2b_;
}  // namespace R2B
namespace SETCTAID {
    // one struct per variant (slug = variant class)
    struct setctaid_;
}  // namespace SETCTAID
namespace ALD {
    // one struct per variant (slug = variant class)
    struct ald_PHYS_;
    struct ald__LOGICAL_RaRZ_default;
    struct ald__PATCH_RaNonRZOffset_P_RbRZ;
    struct ald__PATCH_RaRZ_P_RbRZ;
    struct ald_UR__LOGICAL_URa_default;
    struct ald_UR__PATCH_URa_P_RbRZ;
}  // namespace ALD
namespace AST {
    // one struct per variant (slug = variant class)
    struct ast_PHYS_;
    struct ast__LOGICAL_RaRZ;
    struct ast__PATCH_RaNonRZOffset;
    struct ast__PATCH_RaRZ;
    struct ast_UR__LOGICAL_URa;
    struct ast_UR__PATCH_RaRZ_URa;
}  // namespace AST
namespace OUT {
    // one struct per variant (slug = variant class)
    struct out__CUT;
    struct out__EMIT_Rb;
    struct out__FINAL;
    struct out_final_rz_;
    struct out__EMIT_Imm;
    struct out__EMIT_URb;
}  // namespace OUT
namespace IPA {
    // one struct per variant (slug = variant class)
    struct ipa_;
    struct ipa_offset__IPA_Rb;
    struct ipa_offset__IPA_Ib;
    struct ipa_ur_;
    struct ipa_ur_offset__IPA_URa_Rb;
    struct ipa_ur_offset__IPA_URa_Ib;
}  // namespace IPA
namespace CALL {
    // one struct per variant (slug = variant class)
    struct call_abs__RRR;
    struct call_rel__RRR;
    struct call_rel_imm__RRR;
    struct call_rel_reg__RRR;
    struct call_abs__RIR;
    struct call_rel__RIR;
    struct call_rel_imm__RIR;
    struct call_abs__URIR;
    struct call_rel__URIR;
    struct call_rel_imm__URIR;
    struct call_rel_reg__URIR;
}  // namespace CALL
namespace WARPSYNC {
    // one struct per variant (slug = variant class)
    struct warpsync__RRR;
    struct warpsync_collective__RRR;
    struct warpsync_rel__RRR;
    struct warpsync_collective__RIR;
    struct warpsync_rel__RIR;
}  // namespace WARPSYNC
namespace LEPC {
    // one struct per variant (slug = variant class)
    struct lepc__RRR;
    struct lepc__R_I_R;
    struct lepc_rel_;
}  // namespace LEPC
namespace RPCMOV {
    // one struct per variant (slug = variant class)
    struct rpcmov_dstPc_;
    struct rpcmov_srcPc_;
    struct rpcmov_dstPc_imm_;
    struct rpcmov_dstPc64__Imm;
    struct rpcmov_dstPc_URb_;
    struct rpcmov_dstPc64__URb;
}  // namespace RPCMOV
namespace BMOV {
    // one struct per variant (slug = variant class)
    struct bmov_clear__Rd;
    struct bmov_pquad__RRR;
    struct bmov_dst64__R;
    struct bmov_pquad__RIR;
    struct bmov_dst64__I;
    struct bmov_pquad__RUR;
    struct bmov_dst64__UR;
}  // namespace BMOV
namespace NANOTRAP {
    // one struct per variant (slug = variant class)
    struct nanotrap__R;
    struct nanotrap__I;
    struct nanotrap__U;
}  // namespace NANOTRAP
namespace NANOSLEEP {
    // one struct per variant (slug = variant class)
    struct nanosleep__R;
    struct nanosleep__I;
    struct nanosleep__U;
}  // namespace NANOSLEEP
namespace TEX {
    // one struct per variant (slug = variant class)
    struct tex_b_urc_;
    struct tex_scr_b_urc_;
    struct tex_b_noConst_;
    struct tex_scr_b_noConst_;
    struct tex_scr_urc_;
    struct tex_urc_;
}  // namespace TEX
namespace TMML {
    // one struct per variant (slug = variant class)
    struct tmml_b_noConst_;
    struct tmml_urc_;
    struct tmml_b_urc_;
}  // namespace TMML
namespace TXQ {
    // one struct per variant (slug = variant class)
    struct txq_b_noConst_;
    struct txq_urc_;
    struct txq_b_urc_;
}  // namespace TXQ
namespace LDG {
    // one struct per variant (slug = variant class)
    struct ldg__sImmOffset;
    struct ldg__uImmOffset;
    struct ldg_256_memdesc__Ra64;
    struct ldg_256_rml2_memdesc__Ra64;
    struct ldg_256_rml2_uniform__Ra32;
    struct ldg_256_rml2_uniform__Ra64;
    struct ldg_256_rml2_uniform__RaRZ;
    struct ldg_256_uniform__Ra32;
    struct ldg_256_uniform__Ra64;
    struct ldg_256_uniform__RaRZ;
    struct ldg_memdesc__Ra64;
    struct ldg_uniform__Ra32;
    struct ldg_uniform__Ra64;
    struct ldg_uniform__RaRZ;
}  // namespace LDG
namespace ST {
    // one struct per variant (slug = variant class)
    struct st__sImmOffset;
    struct st__uImmOffset;
    struct st_memdesc__Ra64;
    struct st_uniform__Ra32;
    struct st_uniform__Ra64;
    struct st_uniform__RaRZ;
}  // namespace ST
namespace STG {
    // one struct per variant (slug = variant class)
    struct stg__sImmOffset;
    struct stg__uImmOffset;
    struct stg_256_memdesc__Ra64;
    struct stg_256_uniform__Ra32;
    struct stg_256_uniform__Ra64;
    struct stg_256_uniform__RaRZ;
    struct stg_memdesc__Ra64;
    struct stg_uniform__Ra32;
    struct stg_uniform__Ra64;
    struct stg_uniform__RaRZ;
}  // namespace STG
namespace STL {
    // one struct per variant (slug = variant class)
    struct stl__sImmOffset;
    struct stl__uImmOffset;
    struct stl_memdesc_;
    struct stl_uniform_;
}  // namespace STL
namespace STS {
    // one struct per variant (slug = variant class)
    struct sts__sImmOffset;
    struct sts__uImmOffset;
    struct sts_uniform_;
}  // namespace STS
namespace SHFL {
    // one struct per variant (slug = variant class)
    struct shfl__RRR;
    struct shfl__RRI;
    struct shfl__RIR;
    struct shfl__RII;
}  // namespace SHFL
namespace ATOM {
    // one struct per variant (slug = variant class)
    struct atom_int__RaNonRZ;
    struct atom_int__RaRZ;
    struct atom_cas__RaNonRZ_CAS;
    struct atom_cas__RaNonRZ_CAST;
    struct atom_cas__RaRZ_CAS;
    struct atom_cas__RaRZ_CAST;
    struct atom_fp__RaNonRZ;
    struct atom_fp__RaRZ;
    struct atom_int_uniform__Ra32;
    struct atom_int_uniform__Ra64;
    struct atom_int_uniform__RaRZ;
    struct atom_int_uniform__memdesc;
    struct atom_fp_uniform__Ra32;
    struct atom_fp_uniform__Ra64;
    struct atom_fp_uniform__RaRZ;
    struct atom_fp_uniform__memdesc;
    struct atom_arrive__Ra32_arrive;
    struct atom_arrive__Ra32_popcinc;
    struct atom_arrive__Ra64_arrive;
    struct atom_arrive__Ra64_popcinc;
    struct atom_arrive__RaRZ_arrive;
    struct atom_arrive__RaRZ_popcinc;
}  // namespace ATOM
namespace ATOMS {
    // one struct per variant (slug = variant class)
    struct atoms__RaNonRZ;
    struct atoms__RaRZ;
    struct atoms_cas__RaNonRZ;
    struct atoms_cas__RaRZ;
    struct atoms_cast_destRd__RaNonRZ;
    struct atoms_cast_destRd__RaRZ;
    struct atoms_cast_destPu__RaNonRZ;
    struct atoms_cast_destPu__RaRZ;
    struct atoms_uniform_;
    struct atoms_arrive__arrive;
    struct atoms_arrive__popcinc;
}  // namespace ATOMS
namespace REDS {
    // one struct per variant (slug = variant class)
    struct atoms_reds__RaNonRZ;
    struct atoms_reds__RaRZ;
    struct atoms_reds_uniform_;
}  // namespace REDS
namespace CCTLT {
    // one struct per variant (slug = variant class)
    struct cctlt__Rb;
    struct cctlt__URb;
}  // namespace CCTLT
namespace SUATOM {
    // one struct per variant (slug = variant class)
    struct suatom_reg_;
    struct suatom_cas_reg_;
    struct suatom_urc_;
    struct suatom_r_urc_;
    struct suatom_cas_urc_;
    struct suatom_cas_r_urc_;
}  // namespace SUATOM
namespace SURED {
    // one struct per variant (slug = variant class)
    struct sured_reg_;
    struct sured_urc_;
    struct sured_r_urc_;
}  // namespace SURED
namespace MATCH {
    // one struct per variant (slug = variant class)
    struct match__ALL;
    struct match__ANY;
}  // namespace MATCH
namespace ATOMG {
    // one struct per variant (slug = variant class)
    struct atomg_fp__RaNonRZ;
    struct atomg_fp__RaRZ;
    struct atomg_int__RaNonRZ;
    struct atomg_int__RaRZ;
    struct atomg_cas__RaNonRZ;
    struct atomg_cas__RaRZ;
    struct atomg_fp_uniform__Ra32;
    struct atomg_fp_uniform__Ra64;
    struct atomg_fp_uniform__RaRZ;
    struct atomg_fp_uniform__memdesc;
    struct atomg_int_uniform__Ra32;
    struct atomg_int_uniform__Ra64;
    struct atomg_int_uniform__RaRZ;
    struct atomg_int_uniform__memdesc;
}  // namespace ATOMG
namespace QSPC {
    // one struct per variant (slug = variant class)
    struct qspc_PuOnly__RaNonRZ;
    struct qspc_PuOnly__RaRZ;
    struct qspc_RdOnly__RaNonRZ;
    struct qspc_RdOnly__RaRZ;
    struct qspc__RaNonRZ;
    struct qspc__RaRZ;
    struct qspc_urb_PuOnly__Ra32;
    struct qspc_urb_PuOnly__Ra64;
    struct qspc_urb_PuOnly__RaRZ;
    struct qspc_urb_RdOnly__Ra32;
    struct qspc_urb_RdOnly__Ra64;
    struct qspc_urb_RdOnly__RaRZ;
    struct qspc_urb__Ra32;
    struct qspc_urb__Ra64;
    struct qspc_urb__RaRZ;
}  // namespace QSPC
namespace GETLMEMBASE {
    // one struct per variant (slug = variant class)
    struct getlmembase_;
}  // namespace GETLMEMBASE
namespace SETLMEMBASE {
    // one struct per variant (slug = variant class)
    struct setlmembase_;
}  // namespace SETLMEMBASE
namespace REDUX {
    // one struct per variant (slug = variant class)
    struct redux_;
}  // namespace REDUX
namespace TTUST {
    // one struct per variant (slug = variant class)
    struct ttust_;
}  // namespace TTUST
namespace TTULD {
    // one struct per variant (slug = variant class)
    struct ttuld__close;
    struct ttuld__no_close;
}  // namespace TTULD
namespace FADD32I {
    // one struct per variant (slug = variant class)
    struct fadd32i_;
}  // namespace FADD32I
namespace HADD2_32I {
    // one struct per variant (slug = variant class)
    struct hadd2_32i_;
    struct hadd2_32i_fixed_;
}  // namespace HADD2_32I
namespace MXQMMA {
    // one struct per variant (slug = variant class)
    struct mxqmma_scale_;
}  // namespace MXQMMA
namespace OMMA {
    // one struct per variant (slug = variant class)
    struct omma_scale_;
    struct omma_sp_scale_;
}  // namespace OMMA
namespace MOV64IUR {
    // one struct per variant (slug = variant class)
    struct mov64iur_imm_;
    struct mov64iur_ur_;
}  // namespace MOV64IUR
namespace PMTRIG {
    // one struct per variant (slug = variant class)
    struct pmtrig_;
}  // namespace PMTRIG
namespace MOV32I {
    // one struct per variant (slug = variant class)
    struct mov32i_;
}  // namespace MOV32I
namespace CS2R {
    // one struct per variant (slug = variant class)
    struct cs2r_;
}  // namespace CS2R
namespace VOTE {
    // one struct per variant (slug = variant class)
    struct vote_;
}  // namespace VOTE
namespace CSMTEST {
    // one struct per variant (slug = variant class)
    struct csmtest_;
    struct csmtest_bop_;
    struct csmtest_cmp_;
}  // namespace CSMTEST
namespace VOTE_VTG {
    // one struct per variant (slug = variant class)
    struct vote_vtg_;
    struct vote_vtg_bop_;
    struct vote_vtg_cmp_;
}  // namespace VOTE_VTG
namespace ISCADD32I {
    // one struct per variant (slug = variant class)
    struct iscadd32i__RIR_RIR;
}  // namespace ISCADD32I
namespace LOP32I {
    // one struct per variant (slug = variant class)
    struct lop32i_;
    struct lop32i_optionalPp_;
}  // namespace LOP32I
namespace FMUL32I {
    // one struct per variant (slug = variant class)
    struct fmul32i_;
}  // namespace FMUL32I
namespace FSWZADD {
    // one struct per variant (slug = variant class)
    struct fswzadd_;
}  // namespace FSWZADD
namespace FFMA32I {
    // one struct per variant (slug = variant class)
    struct ffma32i_;
}  // namespace FFMA32I
namespace IMUL32I {
    // one struct per variant (slug = variant class)
    struct imul32i_lo__RsIR_RIR;
    struct imul32i_wide__RsIR_RIR;
}  // namespace IMUL32I
namespace ELECT {
    // one struct per variant (slug = variant class)
    struct elect_Pp_;
    struct elect_;
    struct elect_noURa_;
}  // namespace ELECT
namespace HFMA2_32I {
    // one struct per variant (slug = variant class)
    struct hfma2_32i_;
    struct hfma2_32i_fixed_;
}  // namespace HFMA2_32I
namespace HMUL2_32I {
    // one struct per variant (slug = variant class)
    struct hmul2_32i_;
    struct hmul2_32i_fixed_;
}  // namespace HMUL2_32I
namespace IADD32I {
    // one struct per variant (slug = variant class)
    struct iadd32i_imm__RsIR_RIR;
    struct iadd32i_x_imm__RIR_RIR;
}  // namespace IADD32I
namespace LDSM {
    // one struct per variant (slug = variant class)
    struct ldsm__sImmOffset;
    struct ldsm_pseudo_ops__sImmOffset;
    struct ldsm__UR_sI_R;
    struct ldsm_pseudo_ops__UR_sI_R;
}  // namespace LDSM
namespace STSM {
    // one struct per variant (slug = variant class)
    struct stsm__sImmOffset;
    struct stsm__UR_sI_R;
}  // namespace STSM
namespace UVIRTCOUNT {
    // one struct per variant (slug = variant class)
    struct uvirtcount__imm;
    struct uvirtcount_one__imm;
    struct uvirtcount__UR;
    struct uvirtcount_one__UR;
}  // namespace UVIRTCOUNT
namespace UMOV {
    // one struct per variant (slug = variant class)
    struct umov__UI;
    struct umov_imm64_;
    struct umov_64__UR;
    struct umov__UR;
}  // namespace UMOV
namespace VOTEU {
    // one struct per variant (slug = variant class)
    struct voteu_;
}  // namespace VOTEU
namespace CS2UR {
    // one struct per variant (slug = variant class)
    struct cs2ur_;
}  // namespace CS2UR
namespace S2R {
    // one struct per variant (slug = variant class)
    struct s2r_;
}  // namespace S2R
namespace AL2P {
    // one struct per variant (slug = variant class)
    struct al2p__RaNonRZ;
    struct al2p__RaRZ;
}  // namespace AL2P
namespace ISBERD {
    // one struct per variant (slug = variant class)
    struct isberd_;
}  // namespace ISBERD
namespace PIXLD {
    // one struct per variant (slug = variant class)
    struct pixld_;
}  // namespace PIXLD
namespace ISBEWR {
    // one struct per variant (slug = variant class)
    struct isbewr_;
}  // namespace ISBEWR
namespace BSSY {
    // one struct per variant (slug = variant class)
    struct bssy_;
    struct bssy_rel_;
    struct bssy_reliability_;
    struct bssy_reliability_rel_;
}  // namespace BSSY
namespace BRA {
    // one struct per variant (slug = variant class)
    struct bra__CONV_DIV;
    struct bra__U;
    struct bra_rel__CONV_DIV;
    struct bra_rel__U;
    struct bra_uniform_pred_;
    struct bra_uniform_pred_rel_;
    struct bra_uniform_;
    struct bra_uniform_rel_;
}  // namespace BRA
namespace BRX {
    // one struct per variant (slug = variant class)
    struct brx_;
    struct brx_rel_;
}  // namespace BRX
namespace JMP {
    // one struct per variant (slug = variant class)
    struct jmp_imm__CONV_DIV;
    struct jmp_imm__U;
    struct jmp_imm_rel__CONV_DIV;
    struct jmp_imm_rel__U;
    struct jmp_imm_uniform_pred_;
    struct jmp_imm_uniform_pred_rel_;
    struct jmp_imm_uniform_;
    struct jmp_imm_uniform_rel_;
}  // namespace JMP
namespace JMX {
    // one struct per variant (slug = variant class)
    struct jmx_;
    struct jmx_rel_;
}  // namespace JMX
namespace RET {
    // one struct per variant (slug = variant class)
    struct ret__ABS;
    struct ret__REL;
    struct ret_rel__RIR;
    struct ret_rel_reg__RIR;
    struct ret__ABS_UR;
    struct ret__REL_UR;
    struct ret_rel__URIR;
    struct ret_rel_reg__URIR;
}  // namespace RET
namespace IDE {
    // one struct per variant (slug = variant class)
    struct ide_;
}  // namespace IDE
namespace BPT {
    // one struct per variant (slug = variant class)
    struct bpt__noDRAIN;
    struct bpt__onlyDRAIN;
}  // namespace BPT
namespace LD {
    // one struct per variant (slug = variant class)
    struct ld__sImmOffset;
    struct ld__uImmOffset;
    struct ld_memdesc__Ra64;
    struct ld_uniform__Ra32;
    struct ld_uniform__Ra64;
    struct ld_uniform__RaRZ;
}  // namespace LD
namespace LDL {
    // one struct per variant (slug = variant class)
    struct ldl__sImmOffset;
    struct ldl__uImmOffset;
    struct ldl_memdesc_;
    struct ldl_uniform_;
}  // namespace LDL
namespace LDS {
    // one struct per variant (slug = variant class)
    struct lds__sImmOffset;
    struct lds__uImmOffset;
    struct lds_uniform_;
}  // namespace LDS
namespace REDG {
    // one struct per variant (slug = variant class)
    struct redg_int__RaNonRZ;
    struct redg_int__RaRZ;
    struct redg_fp__RaNonRZ;
    struct redg_fp__RaRZ;
    struct redg_int_uniform__Ra32;
    struct redg_int_uniform__Ra64;
    struct redg_int_uniform__RaRZ;
    struct redg_int_uniform__memdesc;
    struct redg_fp_uniform__Ra32;
    struct redg_fp_uniform__Ra64;
    struct redg_fp_uniform__RaRZ;
    struct redg_fp_uniform__memdesc;
}  // namespace REDG
namespace CCTL {
    // one struct per variant (slug = variant class)
    struct cctl__IVALL_WBALL_D_U_noSrc;
    struct cctl__sImmOffset;
    struct cctl__sImmOffset_pf2;
    struct cctl__sImmOffset_pf2_q;
    struct cctl__sImmOffset_rml2;
    struct cctl__uImmOffset;
    struct cctl__uImmOffset_pf2;
    struct cctl__uImmOffset_pf2_q;
    struct cctl__uImmOffset_rml2;
    struct cctl_c_ldc_const_bound_;
    struct cctl_c_ldc_va_;
    struct cctl_c_ldcu_va_;
    struct cctl_c_ldc_const_bindless_;
    struct cctl_c_ldcu_const_bindless_;
    struct cctl_c_ldcu_const_bound_;
    struct cctl__sUROffset;
    struct cctl__sUROffset_pf2;
    struct cctl__sUROffset_pf2_q;
    struct cctl__sUROffset_rml2;
    struct cctl__uUROffset;
    struct cctl__uUROffset_pf2;
    struct cctl__uUROffset_pf2_q;
    struct cctl__uUROffset_rml2;
}  // namespace CCTL
namespace CCTLL {
    // one struct per variant (slug = variant class)
    struct cctll__sImmOffset;
    struct cctll__uImmOffset;
    struct cctll__Ra_RZ_UR;
    struct cctll__Ra_nonRz_UR;
}  // namespace CCTLL
namespace SULD {
    // one struct per variant (slug = variant class)
    struct suld_p_reg_;
    struct suld_d_reg_;
    struct suld_p_urc_;
    struct suld_p_r_urc_;
    struct suld_d_urc_;
    struct suld_d_r_urc_;
}  // namespace SULD
namespace SUST {
    // one struct per variant (slug = variant class)
    struct sust_p_reg_;
    struct sust_d_reg_;
    struct sust_p_urc_;
    struct sust_p_r_urc_;
    struct sust_d_urc_;
    struct sust_d_r_urc_;
}  // namespace SUST
namespace SUQUERY {
    // one struct per variant (slug = variant class)
    struct suquery_reg_;
    struct suquery_r_urc_;
    struct suquery_urc_;
}  // namespace SUQUERY
namespace S2UR {
    // one struct per variant (slug = variant class)
    struct s2ur_;
}  // namespace S2UR
namespace TTUMACROFUSE {
    // one struct per variant (slug = variant class)
    struct ttumacrofuse_;
}  // namespace TTUMACROFUSE
namespace LDC {
    // one struct per variant (slug = variant class)
    struct ldc__RaNonRZ;
    struct ldc__RaRZ;
    struct ldc_ur__URRzI;
    struct ldc_ur__URnonRzI;
}  // namespace LDC
namespace UVIADD {
    // one struct per variant (slug = variant class)
    struct uviadd__URURUR_UUU;
    struct uviadd__URuIUR_URIR;
}  // namespace UVIADD
namespace UVIMNMX {
    // one struct per variant (slug = variant class)
    struct uvimnmx__UUU_URURUR;
    struct uvimnmx__URIR_URsIUR;
}  // namespace UVIMNMX
namespace UIABS {
    // one struct per variant (slug = variant class)
    struct uiabs__URURUR_UR;
    struct uiabs__URsIUR_I;
}  // namespace UIABS
namespace UI2I {
    // one struct per variant (slug = variant class)
    struct ui2i__URURUR_UUU;
    struct ui2i__URsIUR_URIR;
}  // namespace UI2I
namespace UI2IP {
    // one struct per variant (slug = variant class)
    struct ui2ip_24__URURUR_UUU;
    struct ui2ip_28__URURUR_UUU;
    struct ui2ip__URURUR_UUU;
    struct ui2ip_24__URsIUR_URRI;
    struct ui2ip_28__URsIUR_URRI;
    struct ui2ip__URsIUR_URRI;
}  // namespace UI2IP
namespace UFMNMX {
    // one struct per variant (slug = variant class)
    struct ufmnmx__URURUR_UUU;
    struct ufmnmx_pred__URURUR_UUU;
    struct ufmnmx__URsIUR_URIR;
    struct ufmnmx_pred__URsIUR_URIR;
}  // namespace UFMNMX
namespace UFSEL {
    // one struct per variant (slug = variant class)
    struct ufsel__URURUR_UUU;
    struct ufsel__URsIUR_URIR;
}  // namespace UFSEL
namespace UFSET {
    // one struct per variant (slug = variant class)
    struct ufset__URURUR_UUU;
    struct ufset_simple__URURUR_UUU;
    struct ufset__URsIUR_URIR;
    struct ufset_simple__URsIUR_URIR;
}  // namespace UFSET
namespace UFSETP {
    // one struct per variant (slug = variant class)
    struct ufsetp__URURUR_UUU;
    struct ufsetp_simple__URURUR_UUU;
    struct ufsetp__URsIUR_URIR;
    struct ufsetp_simple__URsIUR_URIR;
}  // namespace UFSETP
namespace UFADD {
    // one struct per variant (slug = variant class)
    struct ufadd__URURUR_UUU;
    struct ufadd__URURsI_URURI;
}  // namespace UFADD
namespace UFHADD {
    // one struct per variant (slug = variant class)
    struct ufhadd__UUU;
}  // namespace UFHADD
namespace UFFMA {
    // one struct per variant (slug = variant class)
    struct uffma__UUU_UUU;
    struct uffma__URURI_URURI;
    struct uffma__URIUR_URIUR;
}  // namespace UFFMA
namespace UFHFMA {
    // one struct per variant (slug = variant class)
    struct ufhfma__UUU;
}  // namespace UFHFMA
namespace UFMUL {
    // one struct per variant (slug = variant class)
    struct ufmul__UUU;
    struct ufmul__URIR;
}  // namespace UFMUL
namespace UF2IP {
    // one struct per variant (slug = variant class)
    struct uf2ip__UUU;
    struct uf2ip__RRI;
    struct uf2ip__URIUR;
}  // namespace UF2IP
namespace UI2F {
    // one struct per variant (slug = variant class)
    struct ui2f__UR_16b;
    struct ui2f__UR_32b;
    struct ui2f__UR_8b;
    struct ui2f__IS_32b;
    struct ui2f__IU_32b;
}  // namespace UI2F
namespace UF2F {
    // one struct per variant (slug = variant class)
    struct uf2f_f32_downconvert__UUU_UUU;
    struct uf2f_f32_upconvert__UUU_UUU;
    struct uf2f_f32_upconvert_swap__UUU_UUU;
    struct uf2f_f32_downconvert__URIR_URIR;
    struct uf2f_f32_upconvert__URIR_URIR;
    struct uf2f_f32_upconvert_swap__URIR_URIR;
}  // namespace UF2F
namespace UF2I {
    // one struct per variant (slug = variant class)
    struct uf2i__URb_16b;
    struct uf2i__URb_32b;
    struct uf2i__URb_bf16;
    struct uf2i_swap__URb_16b;
    struct uf2i_swap__URb_32b;
    struct uf2i_swap__URb_bf16;
    struct uf2i__IU_32b;
    struct uf2i__Ib_16b;
    struct uf2i__Ib_bf16;
    struct uf2i_swap__IU_32b;
    struct uf2i_swap__Ib_16b;
    struct uf2i_swap__Ib_bf16;
}  // namespace UF2I
namespace UFRND {
    // one struct per variant (slug = variant class)
    struct ufrnd__bf16_URb;
    struct ufrnd__f16_URb;
    struct ufrnd__f32_URb;
    struct ufrnd_swap__bf16_URb;
    struct ufrnd_swap__f16_URb;
    struct ufrnd_swap__f32_URb;
    struct ufrnd__bf16_I;
    struct ufrnd__f16_I;
    struct ufrnd__f32_I;
    struct ufrnd_swap__bf16_I;
    struct ufrnd_swap__f16_I;
    struct ufrnd_swap__f32_I;
}  // namespace UFRND
namespace UI2FP {
    // one struct per variant (slug = variant class)
    struct ui2fp__UUU;
    struct ui2fp__URsIR;
    struct ui2fp__URuIR;
}  // namespace UI2FP
namespace UIMNMX {
    // one struct per variant (slug = variant class)
    struct uimnmx_64__UUU_URURUR;
    struct uimnmx_64_nopred__UUU_URURUR;
    struct uimnmx__UUU_URURUR;
    struct uimnmx_nopred__UUU_URURUR;
    struct uimnmx_64__URIR_URsIUR;
    struct uimnmx_64_nopred__URIR_URsIUR;
    struct uimnmx__URIR_URsIUR;
    struct uimnmx_nopred__URIR_URsIUR;
}  // namespace UIMNMX
namespace USEL {
    // one struct per variant (slug = variant class)
    struct usel__URURUR_UUU;
    struct usel_64__URIR;
    struct usel__URuIUR_URIR;
    struct usel_64__UUU;
}  // namespace USEL
namespace UISETP {
    // one struct per variant (slug = variant class)
    struct uisetp_64__URURUR_URURUR;
    struct uisetp_64_optional_upr__URURUR_URURUR;
    struct uisetp_64_simple__URURUR_URURUR;
    struct uisetp_64_simple_optional_upr__URURUR_URURUR;
    struct uisetp__URURUR_URURUR;
    struct uisetp_optional_upr__URURUR_URURUR;
    struct uisetp_simple__URURUR_URURUR;
    struct uisetp_simple_optional_upr__URURUR_URURUR;
    struct uisetp_64__URsIUR_URIR;
    struct uisetp_64_optional_upr__URsIUR_URIR;
    struct uisetp_64_simple__URsIUR_URIR;
    struct uisetp_64_simple_optional_upr__URsIUR_URIR;
    struct uisetp__URsIUR_URIR;
    struct uisetp_optional_upr__URsIUR_URIR;
    struct uisetp_simple__URsIUR_URIR;
    struct uisetp_simple_optional_upr__URsIUR_URIR;
}  // namespace UISETP
namespace UIADD3 {
    // one struct per variant (slug = variant class)
    struct uiadd3__URURUR_URURUR;
    struct uiadd3_x__URURUR_URURUR;
    struct uiadd3__URsIUR_RIR;
    struct uiadd3_x__URsIUR_RIR;
}  // namespace UIADD3
namespace ULEA {
    // one struct per variant (slug = variant class)
    struct ulea_hi_noimm__URURUR_URURUR;
    struct ulea_hi_noimm_sx32__URURUR_URURUR;
    struct ulea_hi_noimm_sx32_x__URURUR_URURUR;
    struct ulea_hi_noimm_x__URURUR_URURUR;
    struct ulea_lo_noimm__URURUR_URURUR;
    struct ulea_lo_noimm_x__URURUR_URURUR;
    struct ulea_hi_imm__RRuI_RRI;
    struct ulea_hi_imm_x__RRuI_RRI;
    struct ulea_hi_imm__RuIR_URIR;
    struct ulea_hi_imm_sx32__RuIR_URIUR;
    struct ulea_hi_imm_sx32_x__RuIR_URIUR;
    struct ulea_hi_imm_x__RuIR_URIR;
    struct ulea_lo_imm__URuIUR_URIUR;
    struct ulea_lo_imm_x__URuIUR_URIUR;
}  // namespace ULEA
namespace ULOP {
    // one struct per variant (slug = variant class)
    struct ulop_noimm__URURUR;
    struct ulop_noimm_optionalUPp__URURUR;
    struct ulop_imm_;
    struct ulop_imm_optionalUPp_;
}  // namespace ULOP
namespace ULOP3 {
    // one struct per variant (slug = variant class)
    struct ulop3_lut__URURUR_URURUR;
    struct ulop3_lut_optionalUPp__URURUR_URURUR;
    struct ulop3_noimm__URURUR_URURUR;
    struct ulop3_noimm_optionalUPp__URURUR_URURUR;
    struct ulop3_imm__URIR_URIR;
    struct ulop3_imm_optionalUPp__URIR_URIR;
    struct ulop3_lut__URuIUR_URIR;
    struct ulop3_lut_optionalUPp__URuIUR_URIR;
}  // namespace ULOP3
namespace UPRMT {
    // one struct per variant (slug = variant class)
    struct uprmt__URURUR;
    struct uprmt__URIUR;
}  // namespace UPRMT
namespace UIADD3_64 {
    // one struct per variant (slug = variant class)
    struct uiadd3_64__URURUR_URURUR;
    struct uiadd3_64_x__URURUR_URURUR;
    struct uiadd3_64__URsIUR_RIR;
    struct uiadd3_64_x__URsIUR_RIR;
}  // namespace UIADD3_64
namespace USHF {
    // one struct per variant (slug = variant class)
    struct ushf__URURUR_URURUR;
    struct ushf__URURuI_URRI;
    struct ushf__URuIUR_URIR;
}  // namespace USHF
namespace USHL {
    // one struct per variant (slug = variant class)
    struct ushl__URURUR_URURUR;
    struct ushl_imm_;
    struct ushl__URuIUR_URIR;
}  // namespace USHL
namespace USHR {
    // one struct per variant (slug = variant class)
    struct ushr__URURUR_URURUR;
    struct ushr__URIR_URIR;
}  // namespace USHR
namespace USGXT {
    // one struct per variant (slug = variant class)
    struct usgxt__URURUR_UUU;
    struct usgxt__URuIUR_URIR;
}  // namespace USGXT
namespace UBMSK {
    // one struct per variant (slug = variant class)
    struct ubmsk__URURUR_URUR;
    struct ubmsk__URuIUR_URI;
}  // namespace UBMSK
namespace UPLOP3 {
    // one struct per variant (slug = variant class)
    struct uplop3_lut_1out_1reg__URURUR;
    struct uplop3_lut_2out_1reg__URURUR;
    struct uplop3_lut_1out_2reg__URURUR;
    struct uplop3_lut_2out_2reg__URURUR;
    struct uplop3_lut_1out_3reg__URURUR;
    struct uplop3_lut_2out_3reg__URURUR;
}  // namespace UPLOP3
namespace UIMAD {
    // one struct per variant (slug = variant class)
    struct uimad__URURUR_URURUR;
    struct uimad_x__URURUR_URURUR;
    struct uimad_wide__URURUR_URURUR;
    struct uimad_wide_x__URURUR_URURUR;
    struct uimad_hi__URURUR_URURUR;
    struct uimad_hi_x__URURUR_URURUR;
    struct uimad__URURsI_URURI;
    struct uimad_x__URURsI_URURI;
    struct uimad__URsIUR_URIUR;
    struct uimad_x__URsIUR_URIUR;
    struct uimad_wide__URsIUR_URIUR;
    struct uimad_wide_x__URsIUR_URIUR;
    struct uimad_hi__URsIUR_URIUR;
    struct uimad_hi_x__URsIUR_URIUR;
}  // namespace UIMAD
namespace UF2FP {
    // one struct per variant (slug = variant class)
    struct uf2fp_8b_upconvert__URURUR;
    struct uf2fp__URURUR;
    struct uf2fp_default_dst_src__URURUR;
    struct uf2fp_f16_to_8b_downconvert__URURUR;
    struct uf2fp_f32_to_8b_downconvert__URURUR;
    struct uf2fp_merge_c__URURUR;
    struct uf2fp_merge_c_default_dst_src__URURUR;
    struct uf2fp_tf32__URURUR;
    struct uf2fp_tf32_default_src__URURUR;
    struct uf2fp_f16_to_8b_downconvert__URURI;
    struct uf2fp_f32_to_8b_downconvert__URURI;
    struct uf2fp_merge_c__URURI;
    struct uf2fp_merge_c_default_dst_src__URURI;
    struct uf2fp_8b_upconvert__URIUR;
    struct uf2fp__URIUR;
    struct uf2fp_default_dst_src__URIUR;
    struct uf2fp_f16_to_8b_downconvert__URIUR;
    struct uf2fp_f32_to_8b_downconvert__URIUR;
    struct uf2fp_merge_c__URIUR;
    struct uf2fp_merge_c_default_dst_src__URIUR;
    struct uf2fp_tf32__URIUR;
    struct uf2fp_tf32_default_src__URIUR;
}  // namespace UF2FP
namespace UFLO {
    // one struct per variant (slug = variant class)
    struct uflo__URURUR_URURUR;
    struct uflo__URuIUR_URuIR;
}  // namespace UFLO
namespace UBREV {
    // one struct per variant (slug = variant class)
    struct ubrev__URURUR_URUR;
    struct ubrev__URuIUR_URI;
}  // namespace UBREV
namespace UPOPC {
    // one struct per variant (slug = variant class)
    struct upopc__URURUR_URUUR;
    struct upopc__URuIUR_URIR;
}  // namespace UPOPC
namespace LDCU {
    // one struct per variant (slug = variant class)
    struct ldcu_256_ur_offs_;
    struct ldcu_256_ur_offs_optional_upx_;
    struct ldcu_256_const_RCxR_;
    struct ldcu_const_RCR_;
    struct ldcu_ur_offs_;
    struct ldcu_ur_offs_optional_upx_;
    struct ldcu_const_RCxR_;
    struct ldcu_256_const_RCR_;
}  // namespace LDCU
namespace LDTRAM {
    // one struct per variant (slug = variant class)
    struct ldtram_;
}  // namespace LDTRAM
namespace SYNCS {
    // one struct per variant (slug = variant class)
    struct syncs_uniform_cas_;
    struct syncs_phasechk_;
    struct syncs_ld_;
    struct syncs_uniform_exch_;
    struct syncs_arrive_;
    struct syncs_tcnt_;
    struct syncs_cctl_;
    struct syncs_uniform_ld_;
}  // namespace SYNCS
namespace UTMALDG {
    // one struct per variant (slug = variant class)
    struct utmaldg_URc__UUU;
    struct utmaldg_URc__UUU_desc;
    struct utmaldg_URc_one__UUU;
    struct utmaldg_URc_one__UUU_desc;
    struct utmaldg__UUU;
    struct utmaldg__UUU_desc;
    struct utmaldg_one__UUU;
    struct utmaldg_one__UUU_desc;
}  // namespace UTMALDG
namespace UTMASTG {
    // one struct per variant (slug = variant class)
    struct utmastg__UUU;
    struct utmastg__UUU_desc;
    struct utmastg_one__UUU;
    struct utmastg_one__UUU_desc;
}  // namespace UTMASTG
namespace UTMAREDG {
    // one struct per variant (slug = variant class)
    struct utmaredg__UUU;
    struct utmaredg__UUU_desc;
    struct utmaredg_one__UUU;
    struct utmaredg_one__UUU_desc;
}  // namespace UTMAREDG
namespace UTMAPF {
    // one struct per variant (slug = variant class)
    struct utmapf_URc__UUU;
    struct utmapf_URc__UUU_desc;
    struct utmapf_URc_one__UUU;
    struct utmapf_URc_one__UUU_desc;
    struct utmapf__UUU;
    struct utmapf__UUU_desc;
    struct utmapf_one__UUU;
    struct utmapf_one__UUU_desc;
}  // namespace UTMAPF
namespace UBLKCP {
    // one struct per variant (slug = variant class)
    struct ublkcp_;
    struct ublkcp_desc_;
    struct ublkcp_desc_one_;
    struct ublkcp_one_;
}  // namespace UBLKCP
namespace UBLKRED {
    // one struct per variant (slug = variant class)
    struct ublkred_;
    struct ublkred_desc_;
    struct ublkred_desc_one_;
    struct ublkred_one_;
}  // namespace UBLKRED
namespace UBLKPF {
    // one struct per variant (slug = variant class)
    struct ublkpf__UUU;
    struct ublkpf__UUU_desc;
    struct ublkpf_one__UUU;
    struct ublkpf_one__UUU_desc;
}  // namespace UBLKPF
namespace UCGABARSET {
    // one struct per variant (slug = variant class)
    struct ucgabarset_;
}  // namespace UCGABARSET
namespace UCGABAR_SET {
    // one struct per variant (slug = variant class)
    struct ucgabar_set_;
}  // namespace UCGABAR_SET
namespace USETMAXREG {
    // one struct per variant (slug = variant class)
    struct usetmaxreg__URb_alloc;
    struct usetmaxreg__URb_dealloc;
    struct usetmaxreg__Ib_alloc;
    struct usetmaxreg__Ib_dealloc;
}  // namespace USETMAXREG
namespace USETSHMSZ {
    // one struct per variant (slug = variant class)
    struct usetshmsz__URb;
    struct usetshmsz__Ib;
}  // namespace USETSHMSZ
namespace UGETNEXTWORKID {
    // one struct per variant (slug = variant class)
    struct ugetnextworkid_;
    struct ugetnextworkid_one_;
}  // namespace UGETNEXTWORKID
namespace UMEMSETS {
    // one struct per variant (slug = variant class)
    struct umemsets_;
}  // namespace UMEMSETS
namespace ULEPC {
    // one struct per variant (slug = variant class)
    struct ulepc__URURUR;
    struct ulepc__UR_I_R;
    struct ulepc_rel_;
}  // namespace ULEPC
namespace UCGABARGET {
    // one struct per variant (slug = variant class)
    struct ucgabarget_;
}  // namespace UCGABARGET
namespace UCGABAR_GET {
    // one struct per variant (slug = variant class)
    struct ucgabar_get_;
}  // namespace UCGABAR_GET
namespace UP2UR {
    // one struct per variant (slug = variant class)
    struct up2ur__Imm;
    struct up2ur_simple_;
    struct up2ur__URb;
}  // namespace UP2UR
namespace UR2UP {
    // one struct per variant (slug = variant class)
    struct ur2up__Imm;
    struct ur2up__URb;
}  // namespace UR2UP
namespace ULOP32I {
    // one struct per variant (slug = variant class)
    struct ulop32i_;
    struct ulop32i_optionalUPp_;
}  // namespace ULOP32I
namespace UCLEA {
    // one struct per variant (slug = variant class)
    struct uclea__Imm;
    struct uclea__URb;
}  // namespace UCLEA
namespace BRXU {
    // one struct per variant (slug = variant class)
    struct brxu_;
    struct brxu_rel_;
}  // namespace BRXU
namespace JMXU {
    // one struct per variant (slug = variant class)
    struct jmxu_;
    struct jmxu_rel_;
}  // namespace JMXU
namespace LDGMC {
    // one struct per variant (slug = variant class)
    struct ldgmc_int__Ra32;
    struct ldgmc_int__Ra64;
    struct ldgmc_int__RaRZ;
    struct ldgmc_int__memdesc;
    struct ldgmc_fp__Ra32;
    struct ldgmc_fp__Ra64;
    struct ldgmc_fp__RaRZ;
    struct ldgmc_fp__memdesc;
}  // namespace LDGMC
namespace ARRIVES {
    // one struct per variant (slug = variant class)
    struct arrives_;
}  // namespace ARRIVES
namespace UTMACCTL {
    // one struct per variant (slug = variant class)
    struct utmacctl_URa_;
    struct utmacctl_URa_one_;
}  // namespace UTMACCTL
namespace DEPBAR {
    // one struct per variant (slug = variant class)
    struct depbar_ur_;
}  // namespace DEPBAR
namespace TLD4 {
    // one struct per variant (slug = variant class)
    struct tld4_b_noConst_;
    struct tld4_scr_b_noConst_;
    struct tld4_scr_urc_;
    struct tld4_urc_;
    struct tld4_b_urc_;
    struct tld4_scr_b_urc_;
}  // namespace TLD4
namespace TLD {
    // one struct per variant (slug = variant class)
    struct tld_b_noConst_;
    struct tld_scr_b_noConst_;
    struct tld_scr_urc_;
    struct tld_urc_;
    struct tld_b_urc_;
    struct tld_scr_b_urc_;
}  // namespace TLD
namespace TXD {
    // one struct per variant (slug = variant class)
    struct txd_b_noConst_;
    struct txd_urc_;
    struct txd_b_urc_;
}  // namespace TXD
namespace FOOTPRINT {
    // one struct per variant (slug = variant class)
    struct footprint_b_noConst_;
    struct footprint_scr_b_noConst_;
    struct footprint_b_urc_;
    struct footprint_scr_b_urc_;
    struct footprint_scr_uniform_;
    struct footprint_uniform_;
}  // namespace FOOTPRINT
namespace LDGSTS {
    // one struct per variant (slug = variant class)
    struct ldgsts__RUR;
    struct ldgsts_memdesc_;
    struct ldgsts_no_ra__RUR;
    struct ldgsts__RR32U;
    struct ldgsts__RR64U;
    struct ldgsts__desc_RRU;
    struct ldgsts_no_ra__RRU;
}  // namespace LDGSTS
namespace STAS {
    // one struct per variant (slug = variant class)
    struct stas_64__Ra64;
    struct stas_64__RaRZ;
    struct stas__Ra32;
}  // namespace STAS
namespace REDAS {
    // one struct per variant (slug = variant class)
    struct redas_64__Ra64;
    struct redas_64__RaRZ;
    struct redas__Ra32;
}  // namespace REDAS

}  // namespace semu::isa::metadata
