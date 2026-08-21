# Arch-specific polyvalent-group declarations for the typed decoded-IR
# schema (gen_isa.py --shapes).
#
# The generator groups decoded variants into one `Decoded<Mnemonic><Nops>`
# struct per (mnemonic, operand-count).  MOST of those structs are
# position-unambiguous, but a subset reuses one `ops[]` position for
# operands of DIFFERENT meaning across their variants (e.g. LDC's
# [Rd,Sa,Sa_bank,Ra,Ra_offset] vs LDC.UR's [Rd,Sa,URa,Rb,Sa_offset], or
# SYNCS.ARRIVE vs SYNCS.PHASECHK vs SYNCS.EXCH layouts).  Automatic
# detection is intentionally NOT used here: the list is curated from the
# position-polyvalence analysis (see docs/ops-array-polyvalence.md) and
# injected at generation time.
#
# For every (mnemonic, nops) in POLY_GROUPS the generator splits the group
# into one `Decoded<Mnemonic><Nops>_<k>` struct per kind-collapsed role
# signature (variant role order with kind-only slots collapsed, e.g.
# {Rb,Sb,URb} -> one key), so every split struct is position-unambiguous.
#
# This file is sm120-specific (the keys come from sm120.json); a new arch
# gets its own copy or an empty POLY_GROUPS.

POLY_GROUPS = {
    ("ATOM", 6),     # atom_int/fp [..,Ra,Ra_offset,Rb,..] vs atom_arrive [..,Ra,Ra_URc,Ra_offset,..]
    ("ATOM", 7),     # + CAS (Rc at the tail)
    ("ATOMG", 6),    # cas vs int/fp uniform base forms
    ("ATOMS", 4),    # plain vs arrive forms
    ("ATOMS", 5),    # dest-Pu vs dest-Rd, cas, uniform base
    ("B2R", 2),      # barname vs Pu destination
    ("BMOV", 2),     # 10 forms (Rd/atexit_pc/barReg/cbu_state dests, Ba/Rb/Sb/URb sources)
    ("BRA", 3),      # uniform-pred guard vs uniform target reg
    ("CALL", 2),     # register vs uniform base
    ("CCTL", 2),     # Ra+offset vs URa+Sa_offset vs Ra+Ra_URb
    ("CCTL", 3),     # +Pu/+sector_count forms
    ("CCTL", 4),     # const bound/bindless (Sa_bank vs URa/Rb/URb)
    ("CCTLL", 2),    # offset vs UR base
    ("DEPBAR", 3),   # LE count-imm vs URb
    ("ELECT", 3),    # Pp source vs URa source
    ("F2FP", 3),     # f2fp [Rd,Ra,Rb] vs downconvert/merge [Rd,Rb,Rc] naming
    ("HADD2", 4),    # F32i [..,Sb,Sc] vs fixed [..,Sc,Sc1]
    ("HFMA2", 5),    # RRR/relu vs RRI vs RIR pack forms
    ("HFMA2", 6),    # RRI vs RIR + Pp tails
    ("HMMA", 7),     # sparse vs indexedRF
    ("HSET2", 4),    # Rc/Sc/URc source, Pp vs Sc1 tail
    ("HSETP2", 5),   # same as HSET2 with Pu/Pv
    ("IMAD", 5),     # x/wide/hi/pseudo rotations (Pu vs Ra, GetPseudoOp/Pp/Rc/URc tail)
    ("IPA", 5),      # attr/URa + Rb/Sb/URa_offset
    ("JMP", 3),      # uniform-pred guard vs uniform target reg
    ("LDC", 5),      # LDC [Sa_bank,Ra,Ra_offset] vs LDC.UR [URa,Rb,Sa_offset]
    ("LDCU", 6),     # 256-ur-offset vs const-RCR vs const-RCxR
    ("LDCU", 8),     # 256-const RCxR vs RCR
    ("LDG", 7),      # 256-uniform [Rd2,Rd,..,word_mask] vs memdesc [Pu,..,desc,..]
    ("LDGSTS", 6),   # RUR vs RR32U/RR64U base/offset swaps
    ("LEA", 6),      # Rc/scaleU5 tail vs scaleU5/Pp x-forms
    ("LOP3", 6),     # LUT imm8 vs Pp tail
    ("MOV", 4),      # indexedRF (indexURd/URd dests)
    ("PLOP3", 4),    # Pr vs UPr
    ("PLOP3", 5),    # pred/1-reg/2-reg/3-reg operand shapes
    ("PLOP3", 7),    # pred/1-reg/2-reg/3-reg operand shapes
    ("PSETP", 5),    # Pr vs UPr
    ("QSPC", 3),     # dest Pu vs Rd
    ("QSPC", 4),     # dest Pu vs Rd, Ra vs Rd, Ra vs Ra_URb
    ("RPCMOV", 2),   # Rd vs Rpc/RpcN dests
    ("SHL", 3),      # Ra/Sa shift source vs Rb/Sb/URb 2nd
    ("SYNCS", 4),    # ld / tcnt / uniform-ld layouts
    ("SYNCS", 5),    # arrive / phasechk / uniform-exch layouts
    ("UIMAD", 6),    # x/wide/hi rotations (UPu/URa, Sb/URb tails)
    ("ULEA", 7),     # Rc|Sc|scaleU5 + UPp|scaleU5 tails
    ("ULOP3", 7),    # LUT imm8 vs UPp tail
    ("UPLOP3", 6),   # pred/1-reg/2-reg/3-reg operand shapes
    ("UPLOP3", 8),   # pred/1-reg/2-reg/3-reg operand shapes
    ("UF2FP", 4),    # [UPg,URd,URa,URb] vs [UPg,URd,URb,Sc] vs [UPg,URd,Sb,URc]
    ("USHL", 4),     # Sa/URa shift source
    ("UVIRTCOUNT", 2),  # imm vs UR
    ("WARPSYNC", 2), # Ra vs sImm mask
}