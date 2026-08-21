# Typed-IR refactor analysis — eliminating `ops[]` from `Decoded<Mnemonic><N>`

Status: analysis only (2026-08).  Goal: replace the positional
`OperandValue ops[N]` array of every specialized `Decoded<Mnemonic><N>`
type with one named field per operand.  This doc answers the prerequisite
question: **which instructions reuse one `ops[]` position for operands of
*different meaning* across their variants** (i.e. where a plain
positional field name would be ambiguous).

Method: every sm120 variant's FORMAT operand roles (schedule slots, `Pg`
guard and modifier slots excluded — exactly `shape_operand_roles` in
`tools/gen_isa.py`) were grouped by `(mnemonic, operand-count)` — the
same grouping that produces the 425 `Decoded<Mnemonic><N>` types.  For
each group, each position's slot-name set across variants was compared.

## Summary

| class | count | meaning |
|---|---|---|
| total `Decoded<Mnemonic><N>` types | 425 | |
| single-variant or fully position-stable | 221 | every position already has ONE name across all variants → ops[] can be renamed mechanically to fields |
| kind-only polyvalence | 161 | the position always means the SAME semantic role; only the OperandKind varies (`{Rb,Sb,URb}`, `{Rc,Sc,URc}`, `{Ra,URa}`, `{URb,Sb}`, `{Sc,Sc1}` …) → ONE field, kind stays dynamic |
| **semantic polyvalence** | **50** | the same position carries different operand *meanings* across variants → needs per-variant resolution (see below) |

Note: the "kind-only" set includes the compiler's slot-name *naming
artifacts* — e.g. HFMA2's second source is `Sb` in the F32i form and `Sc`
in the fixed forms, HSET2's third source is `Rc`/`Sc`/`URc`, WARPSYNC's
mask is `Ra`/`sImm`.  All are the same operand role; the name difference
comes from the spec's per-form slot naming.  (The strict classification
above keeps `Sb1`/`Sc1`/`sImm`/`Sa` as DISTINCT keys, which is why the
semantic count is 50, not the looser 43.)

## The 50 semantic-polyvalence groups

Full per-variant role lists are below; this is the same position being
*reused for different operands*:

```
mnemonic nops | conflicting positions (name sets)
ATOM     6    p3:{Ra_URc,Ra_offset} p4:{Ra_offset,Rb}            (plain vs .ARRIVE uniform base)
ATOM     7    p3:{Ra_URc,Ra_offset} p4:{Ra_offset,Rb} p5:{Rb,Rc} (+CAS)
ATOMG    6    p3:{Ra_URc,Ra_offset} p4:{Ra_offset,Rb} p5:{Rb,Rc}
ATOMS    4    p2:{Ra_URc,Ra_offset} p3:{Ra_offset,Rb}
ATOMS    5    p0:{Pu,Rd} p2:{Ra_URc,Ra_offset} p3:{Ra_offset,Rb} p4:{Rb,Rc}
B2R      2    p1:{Pu,barname}
BMOV     2    p0:{Rd,atexit_pc,barReg,cbu_state} p1:{Ba,Rb,Sb,URb,barReg,cbu_state}
BRA      3    p1:{UPq,URb}                                        (uniform-pred guard vs uniform target)
CCTL     2    p0:{Ra,URa} p1:{Ra_URb,Ra_offset,Sa_offset}
CCTL     3    p0:{Pu,Ra} p1:{Ra,Ra_URb,Ra_offset} p2:{Ra_URb,Ra_offset,sector_count}
CCTL     4    p1:{Sa_bank,URa} p2:{Ra,Rb,URa,URb} p3:{Ra_offset,Sa_offset}
CCTLL    2    p1:{Ra_URb,Ra_offset}
DEPBAR   3    p1:{URb,cnt}                                        (LE count-imm vs UR form)
ELECT    3    p2:{Pp,URa}                                         (pred vs uniform source)
HFMA2    5    p3:{Rc,Sb1,Sc,URc} p4:{Pp,Rc,Sc1}                   (relu/mma vs RIR/RRI pack forms)
HMMA     7    p0:{Rd,indexURd} p1:{Ra,URd} p2:{Ra,Rb} p3:{Rb,Rc}
               p4:{UPp,indexURc} p5:{Re,URc} p6:{UPp,id}          (sparse vs indexedRF)
HSET2    4    p3:{Pp,Sc1}
HSETP2   5    p4:{Pp,Sc1}
IMAD     5    p1:{Pu,Ra} p2:{Ra,Rb,Sb,URb} p3:{Rb,Rc,Sb,Sc,URb,URc}
               p4:{GetPseudoOp*,Pp,Rc,URc}                        (x/wide/hi/pseudo rotations)
IPA      5    p3:{URa,attr} p4:{Rb,Sb,URa_offset}
JMP      3    p1:{UPq,URb}
LDC      5    p2:{Sa_bank,URa} p3:{Ra,Rb} p4:{Ra_offset,Sa_offset} (LDC vs LDC.UR layouts)
LDCU     6    p1:{URd,URd2} p2:{Sa,URd} p3:{Sa_bank,URa} p4:{Sa_offset,URa,URb} p5:{Sa_offset,word_mask}
LDCU     8    p4:{Sa_bank,URa} p5:{URa,URb}
LDG      7    p0:{Pu,Rd2} p2:{Ra,memoryDescriptor} p4:{Ra,Ra_offset} p5:{Ra_offset,word_mask}
               (256-bit uniform vs memdesc layouts)
LDGSTS   6    p1:{Rb_URc,Rb_offset} p2:{Ra,Rb_offset} p3:{Ra,Ra_URc}  (RUR vs RR32U/RR64U)
LEA      6    p4:{Rc,Sc,scaleU5} p5:{Pp,scaleU5}                   (imm/x forms shift the tail)
LOP3     6    p5:{Pp,imm8}                                         (LUT vs no-LUT)
MOV      4    p0:{Rd,indexURd} p1:{URd,indexURb}                   (indexed-RF)
PLOP3    4    p3:{Pr,UPr}
PLOP3    5    p1:{Pp,Ra} p2:{Pq,Rb,URb} p3:{Pr,Rc,UPr}
PLOP3    7    p2:{Pp,Ra} p3:{Pq,Rb,URb} p4:{Pr,Rc,UPr}
PSETP    5    p4:{Pr,UPr}
QSPC     3    p0:{Pu,Rd}
QSPC     4    p0:{Pu,Rd} p1:{Ra,Rd} p2:{Ra,Ra_URb}                 (dest-is-pred vs dest-is-reg)
RPCMOV   2    p0:{Rd,Rpc,RpcN} p1:{Rb,RpcN,Sb,URb}
SYNCS    4    p0:{Ra,Rd,UPg} p1:{Ra,Ra_URc,URd} p2:{Ra_URc,Ra_offset,URa} p3:{Ra_offset,Rb,URa_offset}
SYNCS    5    p0:{Pu,Rd,UPg} p1:{Ra,URd} p2:{Ra_URc,URa} p3:{Ra_offset,URa_offset} p4:{Rb,URb}
               (arrive/tcnt/ld/phasechk/exch are layout-disjoint)
UIMAD    6    p2:{UPu,URa} p3:{Sb,URa,URb} p4:{Sb,Sc,URb,URc} p5:{UPp,URc}
ULEA     7    p5:{Sc,URc,scaleU5} p6:{UPp,scaleU5}
ULOP3    7    p6:{UPp,imm8}
UPLOP3   6    p2:{UPp,URa} p3:{UPq,URb} p4:{UPr,URc}
UPLOP3   8    p3:{UPp,URa} p4:{UPq,URb} p5:{UPr,URc}
```

## Patterns behind the semantic conflicts

1. **Register-base vs uniform-base address forms** — `{Ra,URa}` +
   `{Ra_offset,Sa_offset}` / `{Ra_URb,Ra_offset}`: CCTL/CCTLL/RET/CALL/
   ALD/AST/ATOM(.ARRIVE)/LDGSTS.  These are *mergeable* into one
   `base`+`off` pair (the interpreter already treats them identically via
   `read_reg_ov`/`read_ur_ov` on the same position).
2. **Dest-is-predicate vs dest-is-register** — `{Pu,Rd}`: QSPC, ATOMS
   CAST, B2R.  One field with kind discriminator, or two optional fields.
3. **Same slot is immediate in one form, register in another** —
   `{Pp,imm8}` (LOP3/ULOP3 LUT), `{UPp,imm8}`, `{URb,cnt}` (DEPBAR),
   `{Rc,Sc,scaleU5}`/`{Pp,scaleU5}` (LEA/ULEA tail), `{UPq,URb}`
   (BRA/JMP uniform guard vs uniform target).
4. **Full layout rotations** — LDC/LDCU/LDG/SYNCS/IMAD/HMMA/RPCMOV/
   PLOP3/UPLOP3/BMOV: the forms share `(mnemonic,nops)` but reorder
   operands completely; a positional name would be wrong for every form
   but one.

## Design implications (next refactor)

IMPLEMENTED (2026-08): the 50 groups are declared in
`semu/tools/shapes_poly_config.py` (arch-specific injection at gen_isa
time); `gen_isa.py --shapes` splits each into one
`Decoded<Mnemonic><N>_<k>` per kind-collapsed role signature and emits
`kShapeSplitByVariant[vi]` so every split struct's positions are
unambiguous (verified: 0 unstable positions across the 126 split structs).

**OPS[] ELIMINATED (2026-08):** every `Decoded<Mnemonic><N>`/`_k` struct now
declares one NAMED `OperandValue` FIELD per role position (name = the
position's single slot name, or the kind-only family representative:
`b`/`c`/`a`/`off` for {Rb,Sb,URb} etc. — the kind lives in the field).
`fill_by_variant`/`slot_value_by_variant` write/read the named fields; the
generated `operand_field(vi, inst, p)` returns a pointer to field p for the
decode/CLI/test bridge; the interpreter resolves the fields ONCE per
instruction into a local `OperandFields` view (per-lane loops read the
local pointer array — no per-lane lookup, no struct-level ops[] array).
`operand_values_by_variant` is deleted; decoded_access.hpp's op_lookup
resolves via the manifest + operand_field.  Name = the single role name (stable) or the semantic role
  for kind-only positions (`src2`/`src3`/`base`/`off` — or keep the
  register name and let the kind live in the field, exactly like
  `OperandValue` today).
- **43 semantic groups**: a single per-position name is impossible.  The
  type must carry the UNION of the conflicting role names as separate
  (optional) fields, set by the per-variant filler — and the interpreter's
  shared per-mnemonic handler must select by *field presence* (or
  kind/subclass), not by position.  This is where the current
  position-based handlers carry pre-existing quirks (e.g. LEA nops=6 reads
  `ops[4]` as Rc, which is scaleU5 on the .X forms).
- The ShapeManifest (slot → (pos, kind)) stays as the decode-time map from
  ENCODING slots to those fields; it becomes the *fill* guide, and the
  interpreter stops indexing it per-lane.

## Full per-variant listing
total groups: 425
groups with polyvalent positions: 204
  pure kind-only (Rb/Sb/URb-style 2nd-source polymorphism): 154
  SEMANTIC (same position, different operand MEANING): 50

### ALD nops=5  (5 variants)
    pos 2: ['Ra', 'URa']
    pos 3: ['Ra_offset', 'URa_offset']
      ald__LOGICAL_RaRZ_default                [Rd, srcAttr, Ra, Ra_offset, Rb]
      ald__PATCH_RaNonRZOffset_P_RbRZ          [Rd, srcAttr, Ra, Ra_offset, Rb]
      ald__PATCH_RaRZ_P_RbRZ                   [Rd, srcAttr, Ra, Ra_offset, Rb]
      ald_UR__LOGICAL_URa_default              [Rd, srcAttr, URa, URa_offset, Rb]
      ald_UR__PATCH_URa_P_RbRZ                 [Rd, srcAttr, URa, URa_offset, Rb]

### AST nops=5  (5 variants)
    pos 1: ['Ra', 'URa']
    pos 2: ['Ra_offset', 'URa_offset']
      ast__LOGICAL_RaRZ                        [srcAttr, Ra, Ra_offset, Rb, Rc]
      ast__PATCH_RaNonRZOffset                 [srcAttr, Ra, Ra_offset, Rb, Rc]
      ast__PATCH_RaRZ                          [srcAttr, Ra, Ra_offset, Rb, Rc]
      ast_UR__LOGICAL_URa                      [srcAttr, URa, URa_offset, Rb, Rc]
      ast_UR__PATCH_RaRZ_URa                   [srcAttr, URa, URa_offset, Rb, Rc]

### ATOM nops=6  (10 variants)
    pos 3: ['Ra_URc', 'Ra_offset']
    pos 4: ['Ra_offset', 'Rb']
      atom_int__RaNonRZ                        [Pu, Rd, Ra, Ra_offset, Rb, wr_early]
      atom_int__RaRZ                           [Pu, Rd, Ra, Ra_offset, Rb, wr_early]
      atom_fp__RaNonRZ                         [Pu, Rd, Ra, Ra_offset, Rb, wr_early]
      atom_fp__RaRZ                            [Pu, Rd, Ra, Ra_offset, Rb, wr_early]
      atom_arrive__Ra32_arrive                 [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]
      atom_arrive__Ra32_popcinc                [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]
      atom_arrive__Ra64_arrive                 [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]
      atom_arrive__Ra64_popcinc                [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]
      atom_arrive__RaRZ_arrive                 [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]
      atom_arrive__RaRZ_popcinc                [Pu, Rd, Ra, Ra_URc, Ra_offset, wr_early]

### ATOM nops=7  (10 variants)
    pos 3: ['Ra_URc', 'Ra_offset']
    pos 4: ['Ra_offset', 'Rb']
    pos 5: ['Rb', 'Rc']
      atom_cas__RaNonRZ_CAS                    [Pu, Rd, Ra, Ra_offset, Rb, Rc, wr_early]
      atom_cas__RaNonRZ_CAST                   [Pu, Rd, Ra, Ra_offset, Rb, Rc, wr_early]
      atom_cas__RaRZ_CAS                       [Pu, Rd, Ra, Ra_offset, Rb, Rc, wr_early]
      atom_cas__RaRZ_CAST                      [Pu, Rd, Ra, Ra_offset, Rb, Rc, wr_early]
      atom_int_uniform__Ra32                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]
      atom_int_uniform__Ra64                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]
      atom_int_uniform__RaRZ                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]
      atom_fp_uniform__Ra32                    [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]
      atom_fp_uniform__Ra64                    [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]
      atom_fp_uniform__RaRZ                    [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb, wr_early]

### ATOMG nops=6  (8 variants)
    pos 3: ['Ra_URc', 'Ra_offset']
    pos 4: ['Ra_offset', 'Rb']
    pos 5: ['Rb', 'Rc']
      atomg_cas__RaNonRZ                       [Pu, Rd, Ra, Ra_offset, Rb, Rc]
      atomg_cas__RaRZ                          [Pu, Rd, Ra, Ra_offset, Rb, Rc]
      atomg_fp_uniform__Ra32                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]
      atomg_fp_uniform__Ra64                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]
      atomg_fp_uniform__RaRZ                   [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]
      atomg_int_uniform__Ra32                  [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]
      atomg_int_uniform__Ra64                  [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]
      atomg_int_uniform__RaRZ                  [Pu, Rd, Ra, Ra_URc, Ra_offset, Rb]

### ATOMS nops=4  (4 variants)
    pos 2: ['Ra_URc', 'Ra_offset']
    pos 3: ['Ra_offset', 'Rb']
      atoms__RaNonRZ                           [Rd, Ra, Ra_offset, Rb]
      atoms__RaRZ                              [Rd, Ra, Ra_offset, Rb]
      atoms_arrive__arrive                     [Rd, Ra, Ra_URc, Ra_offset]
      atoms_arrive__popcinc                    [Rd, Ra, Ra_URc, Ra_offset]

### ATOMS nops=5  (7 variants)
    pos 0: ['Pu', 'Rd']
    pos 2: ['Ra_URc', 'Ra_offset']
    pos 3: ['Ra_offset', 'Rb']
    pos 4: ['Rb', 'Rc']
      atoms_cas__RaNonRZ                       [Rd, Ra, Ra_offset, Rb, Rc]
      atoms_cas__RaRZ                          [Rd, Ra, Ra_offset, Rb, Rc]
      atoms_cast_destRd__RaNonRZ               [Rd, Ra, Ra_offset, Rb, Rc]
      atoms_cast_destRd__RaRZ                  [Rd, Ra, Ra_offset, Rb, Rc]
      atoms_cast_destPu__RaNonRZ               [Pu, Ra, Ra_offset, Rb, Rc]
      atoms_cast_destPu__RaRZ                  [Pu, Ra, Ra_offset, Rb, Rc]
      atoms_uniform_                           [Rd, Ra, Ra_URc, Ra_offset, Rb]

### B2R nops=2  (2 variants)
    pos 1: ['Pu', 'barname']
      b2r__BAR                                 [Rd, barname]
      b2r__RESULT                              [Rd, Pu]

### BMOV nops=2  (10 variants)
    pos 0: ['Rd', 'atexit_pc', 'barReg', 'cbu_state']
    pos 1: ['Ba', 'Rb', 'Sb', 'URb', 'barReg', 'cbu_state']
      bmov_clear__Rd                           [Rd, cbu_state]
      bmov_pquad__RRR                          [cbu_state, Rb]
      bmov_dst64__R                            [atexit_pc, Rb]
      bmov_pquad__RIR                          [cbu_state, Sb]
      bmov_dst64__I                            [atexit_pc, Sb]
      bmov_clear_barrier_                      [barReg, Ba]
      bmov_clear_bd__Bd                        [barReg, cbu_state]
      bmov_pquad_bar__RBR                      [cbu_state, barReg]
      bmov_pquad__RUR                          [cbu_state, URb]
      bmov_dst64__UR                           [atexit_pc, URb]

### BRA nops=3  (4 variants)
    pos 1: ['UPq', 'URb']
      bra_uniform_pred_                        [Pp, UPq, sImm]
      bra_uniform_pred_rel_                    [Pp, UPq, sImm]
      bra_uniform_                             [Pp, URb, sImm]
      bra_uniform_rel_                         [Pp, URb, sImm]

### CALL nops=3  (6 variants)
    pos 1: ['Ra', 'URa']
    pos 2: ['Ra_offset', 'Sa_offset']
      call_abs__RRR                            [Pp, Ra, Ra_offset]
      call_rel__RRR                            [Pp, Ra, Ra_offset]
      call_rel_imm__RRR                        [Pp, Ra, Ra_offset]
      call_abs__URIR                           [Pp, URa, Sa_offset]
      call_rel__URIR                           [Pp, URa, Sa_offset]
      call_rel_imm__URIR                       [Pp, URa, Sa_offset]

### CCTL nops=2  (10 variants)
    pos 0: ['Ra', 'URa']
    pos 1: ['Ra_URb', 'Ra_offset', 'Sa_offset']
      cctl__sImmOffset                         [Ra, Ra_offset]
      cctl__sImmOffset_pf2                     [Ra, Ra_offset]
      cctl__uImmOffset                         [Ra, Ra_offset]
      cctl__uImmOffset_pf2                     [Ra, Ra_offset]
      cctl_c_ldc_va_                           [URa, Sa_offset]
      cctl_c_ldcu_va_                          [URa, Sa_offset]
      cctl__sUROffset                          [Ra, Ra_URb]
      cctl__sUROffset_pf2                      [Ra, Ra_URb]
      cctl__uUROffset                          [Ra, Ra_URb]
      cctl__uUROffset_pf2                      [Ra, Ra_URb]

### CCTL nops=3  (8 variants)
    pos 0: ['Pu', 'Ra']
    pos 1: ['Ra', 'Ra_URb', 'Ra_offset']
    pos 2: ['Ra_URb', 'Ra_offset', 'sector_count']
      cctl__sImmOffset_pf2_q                   [Pu, Ra, Ra_offset]
      cctl__sImmOffset_rml2                    [Ra, Ra_offset, sector_count]
      cctl__uImmOffset_pf2_q                   [Pu, Ra, Ra_offset]
      cctl__uImmOffset_rml2                    [Ra, Ra_offset, sector_count]
      cctl__sUROffset_pf2_q                    [Pu, Ra, Ra_URb]
      cctl__sUROffset_rml2                     [Ra, Ra_URb, sector_count]
      cctl__uUROffset_pf2_q                    [Pu, Ra, Ra_URb]
      cctl__uUROffset_rml2                     [Ra, Ra_URb, sector_count]

### CCTL nops=4  (4 variants)
    pos 1: ['Sa_bank', 'URa']
    pos 2: ['Ra', 'Rb', 'URa', 'URb']
    pos 3: ['Ra_offset', 'Sa_offset']
      cctl_c_ldc_const_bound_                  [Sa, Sa_bank, Ra, Ra_offset]
      cctl_c_ldc_const_bindless_               [Sa, URa, Rb, Sa_offset]
      cctl_c_ldcu_const_bindless_              [Sa, URa, URb, Sa_offset]
      cctl_c_ldcu_const_bound_                 [Sa, Sa_bank, URa, Sa_offset]

### CCTLL nops=2  (4 variants)
    pos 1: ['Ra_URb', 'Ra_offset']
      cctll__sImmOffset                        [Ra, Ra_offset]
      cctll__uImmOffset                        [Ra, Ra_offset]
      cctll__Ra_RZ_UR                          [Ra, Ra_URb]
      cctll__Ra_nonRz_UR                       [Ra, Ra_URb]

### DEPBAR nops=3  (2 variants)
    pos 1: ['URb', 'cnt']
      depbar__LE                               [sbidx, cnt, scoreboard_list]
      depbar_ur_                               [sbidx, URb, scoreboard_list]

### ELECT nops=3  (2 variants)
    pos 2: ['Pp', 'URa']
      elect_Pp_                                [Pu, URd, Pp]
      elect_                                   [Pu, URd, URa]

### HADD2 nops=4  (3 variants)
    pos 2: ['Sb', 'Sc']
    pos 3: ['Sc', 'Sc1']
      hadd2_F32i_                              [Rd, Ra, Sb, Sc]
      hadd2__RI                                [Rd, Ra, Sc, Sc1]
      hadd2_fixed__RI                          [Rd, Ra, Sc, Sc1]

### HFMA2 nops=5  (15 variants)
    pos 2: ['Rb', 'Sb', 'URb']
    pos 3: ['Rc', 'Sb1', 'Sc', 'URc']
    pos 4: ['Pp', 'Rc', 'Sc1']
      hfma2_mma_relu__RRR                      [Rd, Ra, Rb, Rc, Pp]
      hfma2_relu__RRR                          [Rd, Ra, Rb, Rc, Pp]
      hfma2_relu_fixed__RRR                    [Rd, Ra, Rb, Rc, Pp]
      hfma2__RRI                               [Rd, Ra, Rb, Sc, Sc1]
      hfma2_fixed__RRI                         [Rd, Ra, Rb, Sc, Sc1]
      hfma2_mma__RRI                           [Rd, Ra, Rb, Sc, Sc1]
      hfma2__RIR                               [Rd, Ra, Sb, Sb1, Rc]
      hfma2_fixed__RIR                         [Rd, Ra, Sb, Sb1, Rc]
      hfma2_mma__RIR                           [Rd, Ra, Sb, Sb1, Rc]
      hfma2_mma_relu__RUR                      [Rd, Ra, URb, Rc, Pp]
      hfma2_relu__RUR                          [Rd, Ra, URb, Rc, Pp]
      hfma2_relu_fixed__RUR                    [Rd, Ra, URb, Rc, Pp]
      hfma2_mma_relu__RRU                      [Rd, Ra, Rb, URc, Pp]
      hfma2_relu__RRU                          [Rd, Ra, Rb, URc, Pp]
      hfma2_relu_fixed__RRU                    [Rd, Ra, Rb, URc, Pp]

### HFMA2 nops=6  (6 variants)
    pos 2: ['Rb', 'Sb']
    pos 3: ['Sb1', 'Sc']
    pos 4: ['Rc', 'Sc1']
      hfma2_mma_relu__RRI                      [Rd, Ra, Rb, Sc, Sc1, Pp]
      hfma2_relu__RRI                          [Rd, Ra, Rb, Sc, Sc1, Pp]
      hfma2_relu_fixed__RRI                    [Rd, Ra, Rb, Sc, Sc1, Pp]
      hfma2_mma_relu__RIR                      [Rd, Ra, Sb, Sb1, Rc, Pp]
      hfma2_relu__RIR                          [Rd, Ra, Sb, Sb1, Rc, Pp]
      hfma2_relu_fixed__RIR                    [Rd, Ra, Sb, Sb1, Rc, Pp]

### HMMA nops=7  (2 variants)
    pos 0: ['Rd', 'indexURd']
    pos 1: ['Ra', 'URd']
    pos 2: ['Ra', 'Rb']
    pos 3: ['Rb', 'Rc']
    pos 4: ['UPp', 'indexURc']
    pos 5: ['Re', 'URc']
    pos 6: ['UPp', 'id']
      hmma_sparse_                             [Rd, Ra, Rb, Rc, UPp, Re, id]
      hmma_x8_indexedRF_                       [indexURd, URd, Ra, Rb, indexURc, URc, UPp]

### HSET2 nops=4  (6 variants)
    pos 2: ['Rc', 'Sc', 'URc']
    pos 3: ['Pp', 'Sc1']
      hset2__RR                                [Rd, Ra, Rc, Pp]
      hset2_fixed__RR                          [Rd, Ra, Rc, Pp]
      hset2_noBop__RI                          [Rd, Ra, Sc, Sc1]
      hset2_noBop_fixed__RI                    [Rd, Ra, Sc, Sc1]
      hset2__RU                                [Rd, Ra, URc, Pp]
      hset2_fixed__RU                          [Rd, Ra, URc, Pp]

### HSETP2 nops=5  (6 variants)
    pos 3: ['Rc', 'Sc', 'URc']
    pos 4: ['Pp', 'Sc1']
      hsetp2__RR                               [Pu, Pv, Ra, Rc, Pp]
      hsetp2_fixed__RR                         [Pu, Pv, Ra, Rc, Pp]
      hsetp2_noBop__RI                         [Pu, Pv, Ra, Sc, Sc1]
      hsetp2_noBop_fixed__RI                   [Pu, Pv, Ra, Sc, Sc1]
      hsetp2__RU                               [Pu, Pv, Ra, URc, Pp]
      hsetp2_fixed__RU                         [Pu, Pv, Ra, URc, Pp]

### IMAD nops=5  (29 variants)
    pos 1: ['Pu', 'Ra']
    pos 2: ['Ra', 'Rb', 'Sb', 'URb']
    pos 3: ['Rb', 'Rc', 'Sb', 'Sc', 'URb', 'URc']
    pos 4: ['GetPseudoOpRIR', 'GetPseudoOpRRI', 'GetPseudoOpRRR', 'Pp', 'Rc', 'URc']
      imad_pseudo__RRR_RRR                     [Rd, Ra, Rb, Rc, GetPseudoOpRRR]
      imad_x__RRR_RRR                          [Rd, Ra, Rb, Rc, Pp]
      imad_x_pseudo__RRR_RRR                   [Rd, Ra, Rb, Rc, Pp]
      imad_wide__RRR_RRR                       [Rd, Pu, Ra, Rb, Rc]
      imad_wide_pseudo__RRR_RRR                [Rd, Pu, Ra, Rb, Rc]
      imad_hi__RRR_RRR                         [Rd, Pu, Ra, Rb, Rc]
      imad_hi_pseudo__RRR_RRR                  [Rd, Pu, Ra, Rb, Rc]
      imad_pseudo__RRsI_RRI                    [Rd, Ra, Rb, Sc, GetPseudoOpRRI]
      imad_x__RRsI_RRI                         [Rd, Ra, Rb, Sc, Pp]
      imad_x_pseudo__RRsI_RRI                  [Rd, Ra, Rb, Sc, Pp]
      imad_pseudo__RsIR_RIR                    [Rd, Ra, Sb, Rc, GetPseudoOpRIR]
      imad_x__RsIR_RIR                         [Rd, Ra, Sb, Rc, Pp]
      imad_x_pseudo__RsIR_RIR                  [Rd, Ra, Sb, Rc, Pp]
      imad_wide__RsIR_RIR                      [Rd, Pu, Ra, Sb, Rc]
      imad_wide_pseudo__RsIR_RIR               [Rd, Pu, Ra, Sb, Rc]
      imad_hi__RsIR_RIR                        [Rd, Pu, Ra, Sb, Rc]
      imad_hi_pseudo__RsIR_RIR                 [Rd, Pu, Ra, Sb, Rc]
      imad_x__RUR_RUR                          [Rd, Ra, URb, Rc, Pp]
      imad_x_pseudo__RUR_RUR                   [Rd, Ra, URb, Rc, Pp]
      imad_wide__RUR_RUR                       [Rd, Pu, Ra, URb, Rc]
      imad_wide_pseudo__RUR_RUR                [Rd, Pu, Ra, URb, Rc]
      imad_hi__RUR_RUR                         [Rd, Pu, Ra, URb, Rc]
      imad_hi_pseudo__RUR_RUR                  [Rd, Pu, Ra, URb, Rc]
      imad_x__RRU_RRU                          [Rd, Ra, Rb, URc, Pp]
      imad_x_pseudo__RRU_RRU                   [Rd, Ra, Rb, URc, Pp]
      imad_wide__RRU_RRU                       [Rd, Pu, Ra, Rb, URc]
      imad_wide_pseudo__RRU_RRU                [Rd, Pu, Ra, Rb, URc]
      imad_hi__RRU_RRU                         [Rd, Pu, Ra, Rb, URc]
      imad_hi_pseudo__RRU_RRU                  [Rd, Pu, Ra, Rb, URc]

### IPA nops=5  (3 variants)
    pos 3: ['URa', 'attr']
    pos 4: ['Rb', 'Sb', 'URa_offset']
      ipa_offset__IPA_Rb                       [Rd, Pu, srcAttr, attr, Rb]
      ipa_offset__IPA_Ib                       [Rd, Pu, srcAttr, attr, Sb]
      ipa_ur_                                  [Rd, Pu, srcAttr, URa, URa_offset]

### JMP nops=3  (4 variants)
    pos 1: ['UPq', 'URb']
      jmp_imm_uniform_pred_                    [Pp, UPq, Sa]
      jmp_imm_uniform_pred_rel_                [Pp, UPq, Sa]
      jmp_imm_uniform_                         [Pp, URb, Sa]
      jmp_imm_uniform_rel_                     [Pp, URb, Sa]

### LDC nops=5  (4 variants)
    pos 2: ['Sa_bank', 'URa']
    pos 3: ['Ra', 'Rb']
    pos 4: ['Ra_offset', 'Sa_offset']
      ldc__RaNonRZ                             [Rd, Sa, Sa_bank, Ra, Ra_offset]
      ldc__RaRZ                                [Rd, Sa, Sa_bank, Ra, Ra_offset]
      ldc_ur__URRzI                            [Rd, Sa, URa, Rb, Sa_offset]
      ldc_ur__URnonRzI                         [Rd, Sa, URa, Rb, Sa_offset]

### LDCU nops=6  (3 variants)
    pos 1: ['URd', 'URd2']
    pos 2: ['Sa', 'URd']
    pos 3: ['Sa_bank', 'URa']
    pos 4: ['Sa_offset', 'URa', 'URb']
    pos 5: ['Sa_offset', 'word_mask']
      ldcu_256_ur_offs_optional_upx_           [UPg, URd2, URd, URa, Sa_offset, word_mask]
      ldcu_const_RCR_                          [UPg, URd, Sa, Sa_bank, URa, Sa_offset]
      ldcu_const_RCxR_                         [UPg, URd, Sa, URa, URb, Sa_offset]

### LDCU nops=8  (2 variants)
    pos 4: ['Sa_bank', 'URa']
    pos 5: ['URa', 'URb']
      ldcu_256_const_RCxR_                     [UPg, URd2, URd, Sa, URa, URb, Sa_offset, word_mask]
      ldcu_256_const_RCR_                      [UPg, URd2, URd, Sa, Sa_bank, URa, Sa_offset, word_mask]

### LDG nops=7  (7 variants)
    pos 0: ['Pu', 'Rd2']
    pos 2: ['Ra', 'memoryDescriptor']
    pos 4: ['Ra', 'Ra_offset']
    pos 5: ['Ra_offset', 'word_mask']
      ldg_256_rml2_uniform__Ra32               [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_256_rml2_uniform__Ra64               [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_256_rml2_uniform__RaRZ               [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_256_uniform__Ra32                    [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_256_uniform__Ra64                    [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_256_uniform__RaRZ                    [Rd2, Rd, Ra, Ra_URb, Ra_offset, word_mask, Pnz]
      ldg_memdesc__Ra64                        [Pu, Rd, memoryDescriptor, Ra_URb, Ra, Ra_offset, Pnz]

### LDGSTS nops=6  (5 variants)
    pos 1: ['Rb_URc', 'Rb_offset']
    pos 2: ['Ra', 'Rb_offset']
    pos 3: ['Ra', 'Ra_URc']
      ldgsts__RUR                              [Rb, Rb_URc, Rb_offset, Ra, Ra_offset, Pnz]
      ldgsts_no_ra__RUR                        [Rb, Rb_URc, Rb_offset, Ra, Ra_offset, Pnz]
      ldgsts__RR32U                            [Rb, Rb_offset, Ra, Ra_URc, Ra_offset, Pnz]
      ldgsts__RR64U                            [Rb, Rb_offset, Ra, Ra_URc, Ra_offset, Pnz]
      ldgsts_no_ra__RRU                        [Rb, Rb_offset, Ra, Ra_URc, Ra_offset, Pnz]

### LEA nops=6  (10 variants)
    pos 3: ['Rb', 'Sb', 'URb']
    pos 4: ['Rc', 'Sc', 'scaleU5']
    pos 5: ['Pp', 'scaleU5']
      lea_hi_noimm__RRR_RRR                    [Rd, Pu, Ra, Rb, Rc, scaleU5]
      lea_hi_noimm_sx32_x__RRR_RRR             [Rd, Pu, Ra, Rb, scaleU5, Pp]
      lea_lo_noimm_x__RRR_RRR                  [Rd, Pu, Ra, Rb, scaleU5, Pp]
      lea_hi_imm__RRuI_RRI                     [Rd, Pu, Ra, Rb, Sc, scaleU5]
      lea_hi_imm__RuIR_RIR                     [Rd, Pu, Ra, Sb, Rc, scaleU5]
      lea_hi_imm_sx32_x__RuIR_RIR              [Rd, Pu, Ra, Sb, scaleU5, Pp]
      lea_lo_imm_x__RuIR_RIR                   [Rd, Pu, Ra, Sb, scaleU5, Pp]
      lea_hi_noimm__RUR_RUR                    [Rd, Pu, Ra, URb, Rc, scaleU5]
      lea_hi_noimm_sx32_x__RUR_RUR             [Rd, Pu, Ra, URb, scaleU5, Pp]
      lea_lo_noimm_x__RUR_RUR                  [Rd, Pu, Ra, URb, scaleU5, Pp]

### LOP3 nops=6  (6 variants)
    pos 3: ['Rb', 'Sb', 'URb']
    pos 5: ['Pp', 'imm8']
      lop3_lut_optionalPp__RRR_RRR             [Pu, Rd, Ra, Rb, Rc, imm8]
      lop3_noimm__RRR_RRR                      [Pu, Rd, Ra, Rb, Rc, Pp]
      lop3_imm__RIR_RIR                        [Pu, Rd, Ra, Sb, Rc, Pp]
      lop3_lut_optionalPp__RuIR_RIR            [Pu, Rd, Ra, Sb, Rc, imm8]
      lop3_lut_optionalPp__RUR_RUR             [Pu, Rd, Ra, URb, Rc, imm8]
      lop3_noimm__RUR_RUR                      [Pu, Rd, Ra, URb, Rc, Pp]

### MOV nops=4  (3 variants)
    pos 0: ['Rd', 'indexURd']
    pos 1: ['URd', 'indexURb']
    pos 2: ['Rb', 'Sb', 'URb']
      mov_indexedRF_IRFd__Rb                   [indexURd, URd, Rb, PixMaskU04]
      mov_indexedRF_IRFd__Ib                   [indexURd, URd, Sb, PixMaskU04]
      mov_indexedRF_Rd_                        [Rd, indexURb, URb, PixMaskU04]

### PLOP3 nops=5  (8 variants)
    pos 1: ['Pp', 'Ra']
    pos 2: ['Pq', 'Rb', 'URb']
    pos 3: ['Pr', 'Rc', 'UPr']
      plop3_lut_1out_1reg__RRR                 [Pu, Pp, Rb, Pr, uimm8]
      plop3_lut_1out_2reg__RRR                 [Pu, Pp, Rb, Rc, uimm8]
      plop3_lut_1out_3reg__RRR                 [Pu, Ra, Rb, Rc, uimm8]
      plop3_lut_1out_                          [Pu, Pp, Pq, Pr, uimm8]
      plop3_lut_1out_uniform_                  [Pu, Pp, Pq, UPr, uimm8]
      plop3_lut_1out_1reg__RUR                 [Pu, Pp, URb, Pr, uimm8]
      plop3_lut_1out_2reg__RUR                 [Pu, Pp, URb, Rc, uimm8]
      plop3_lut_1out_3reg__RUR                 [Pu, Ra, URb, Rc, uimm8]

### PLOP3 nops=7  (8 variants)
    pos 2: ['Pp', 'Ra']
    pos 3: ['Pq', 'Rb', 'URb']
    pos 4: ['Pr', 'Rc', 'UPr']
      plop3_lut_2out_1reg__RRR                 [Pu, Pv, Pp, Rb, Pr, uimm8, vimm8]
      plop3_lut_2out_2reg__RRR                 [Pu, Pv, Pp, Rb, Rc, uimm8, vimm8]
      plop3_lut_2out_3reg__RRR                 [Pu, Pv, Ra, Rb, Rc, uimm8, vimm8]
      plop3_lut_2out_                          [Pu, Pv, Pp, Pq, Pr, uimm8, vimm8]
      plop3_lut_2out_uniform_                  [Pu, Pv, Pp, Pq, UPr, uimm8, vimm8]
      plop3_lut_2out_1reg__RUR                 [Pu, Pv, Pp, URb, Pr, uimm8, vimm8]
      plop3_lut_2out_2reg__RUR                 [Pu, Pv, Pp, URb, Rc, uimm8, vimm8]
      plop3_lut_2out_3reg__RUR                 [Pu, Pv, Ra, URb, Rc, uimm8, vimm8]

### PLOP3 nops=4  (2 variants)
    pos 3: ['Pr', 'UPr']
      plop3_1out_                              [Pu, Pp, Pq, Pr]
      plop3_1out_uniform_                      [Pu, Pp, Pq, UPr]

### PSETP nops=5  (2 variants)
    pos 4: ['Pr', 'UPr']
      psetp_                                   [Pu, Pv, Pp, Pq, Pr]
      psetp_uniform_                           [Pu, Pv, Pp, Pq, UPr]

### QSPC nops=3  (4 variants)
    pos 0: ['Pu', 'Rd']
      qspc_PuOnly__RaNonRZ                     [Pu, Ra, Ra_offset]
      qspc_PuOnly__RaRZ                        [Pu, Ra, Ra_offset]
      qspc_RdOnly__RaNonRZ                     [Rd, Ra, Ra_offset]
      qspc_RdOnly__RaRZ                        [Rd, Ra, Ra_offset]

### QSPC nops=4  (8 variants)
    pos 0: ['Pu', 'Rd']
    pos 1: ['Ra', 'Rd']
    pos 2: ['Ra', 'Ra_URb']
      qspc__RaNonRZ                            [Pu, Rd, Ra, Ra_offset]
      qspc__RaRZ                               [Pu, Rd, Ra, Ra_offset]
      qspc_urb_PuOnly__Ra32                    [Pu, Ra, Ra_URb, Ra_offset]
      qspc_urb_PuOnly__Ra64                    [Pu, Ra, Ra_URb, Ra_offset]
      qspc_urb_PuOnly__RaRZ                    [Pu, Ra, Ra_URb, Ra_offset]
      qspc_urb_RdOnly__Ra32                    [Rd, Ra, Ra_URb, Ra_offset]
      qspc_urb_RdOnly__Ra64                    [Rd, Ra, Ra_URb, Ra_offset]
      qspc_urb_RdOnly__RaRZ                    [Rd, Ra, Ra_URb, Ra_offset]

### RET nops=3  (6 variants)
    pos 1: ['Ra', 'URa']
    pos 2: ['Ra_offset', 'Sa_offset']
      ret__ABS                                 [Pp, Ra, Ra_offset]
      ret__REL                                 [Pp, Ra, Ra_offset]
      ret_rel__RIR                             [Pp, Ra, Ra_offset]
      ret__ABS_UR                              [Pp, URa, Sa_offset]
      ret__REL_UR                              [Pp, URa, Sa_offset]
      ret_rel__URIR                            [Pp, URa, Sa_offset]

### RPCMOV nops=2  (6 variants)
    pos 0: ['Rd', 'Rpc', 'RpcN']
    pos 1: ['Rb', 'RpcN', 'Sb', 'URb']
      rpcmov_dstPc_                            [RpcN, Rb]
      rpcmov_srcPc_                            [Rd, RpcN]
      rpcmov_dstPc_imm_                        [RpcN, Sb]
      rpcmov_dstPc64__Imm                      [Rpc, Sb]
      rpcmov_dstPc_URb_                        [RpcN, URb]
      rpcmov_dstPc64__URb                      [Rpc, URb]

### SYNCS nops=5  (3 variants)
    pos 0: ['Pu', 'Rd', 'UPg']
    pos 1: ['Ra', 'URd']
    pos 2: ['Ra_URc', 'URa']
    pos 3: ['Ra_offset', 'URa_offset']
    pos 4: ['Rb', 'URb']
      syncs_phasechk_                          [Pu, Ra, Ra_URc, Ra_offset, Rb]
      syncs_uniform_exch_                      [UPg, URd, URa, URa_offset, URb]
      syncs_arrive_                            [Rd, Ra, Ra_URc, Ra_offset, Rb]

### SYNCS nops=4  (3 variants)
    pos 0: ['Ra', 'Rd', 'UPg']
    pos 1: ['Ra', 'Ra_URc', 'URd']
    pos 2: ['Ra_URc', 'Ra_offset', 'URa']
    pos 3: ['Ra_offset', 'Rb', 'URa_offset']
      syncs_ld_                                [Rd, Ra, Ra_URc, Ra_offset]
      syncs_tcnt_                              [Ra, Ra_URc, Ra_offset, Rb]
      syncs_uniform_ld_                        [UPg, URd, URa, URa_offset]

### UIMAD nops=6  (7 variants)
    pos 2: ['UPu', 'URa']
    pos 3: ['Sb', 'URa', 'URb']
    pos 4: ['Sb', 'Sc', 'URb', 'URc']
    pos 5: ['UPp', 'URc']
      uimad_x__URURUR_URURUR                   [UPg, URd, URa, URb, URc, UPp]
      uimad_wide__URURUR_URURUR                [UPg, URd, UPu, URa, URb, URc]
      uimad_hi__URURUR_URURUR                  [UPg, URd, UPu, URa, URb, URc]
      uimad_x__URURsI_URURI                    [UPg, URd, URa, URb, Sc, UPp]
      uimad_x__URsIUR_URIUR                    [UPg, URd, URa, Sb, URc, UPp]
      uimad_wide__URsIUR_URIUR                 [UPg, URd, UPu, URa, Sb, URc]
      uimad_hi__URsIUR_URIUR                   [UPg, URd, UPu, URa, Sb, URc]

### ULEA nops=7  (7 variants)
    pos 4: ['Sb', 'URb']
    pos 5: ['Sc', 'URc', 'scaleU5']
    pos 6: ['UPp', 'scaleU5']
      ulea_hi_noimm__URURUR_URURUR             [UPg, URd, UPu, URa, URb, URc, scaleU5]
      ulea_hi_noimm_sx32_x__URURUR_URURUR      [UPg, URd, UPu, URa, URb, scaleU5, UPp]
      ulea_lo_noimm_x__URURUR_URURUR           [UPg, URd, UPu, URa, URb, scaleU5, UPp]
      ulea_hi_imm__RRuI_RRI                    [UPg, URd, UPu, URa, URb, Sc, scaleU5]
      ulea_hi_imm__RuIR_URIR                   [UPg, URd, UPu, URa, Sb, URc, scaleU5]
      ulea_hi_imm_sx32_x__RuIR_URIUR           [UPg, URd, UPu, URa, Sb, scaleU5, UPp]
      ulea_lo_imm_x__URuIUR_URIUR              [UPg, URd, UPu, URa, Sb, scaleU5, UPp]

### ULOP3 nops=7  (4 variants)
    pos 4: ['Sb', 'URb']
    pos 6: ['UPp', 'imm8']
      ulop3_lut_optionalUPp__URURUR_URURUR     [UPg, UPu, URd, URa, URb, URc, imm8]
      ulop3_noimm__URURUR_URURUR               [UPg, UPu, URd, URa, URb, URc, UPp]
      ulop3_imm__URIR_URIR                     [UPg, UPu, URd, URa, Sb, URc, UPp]
      ulop3_lut_optionalUPp__URuIUR_URIR       [UPg, UPu, URd, URa, Sb, URc, imm8]

### UPLOP3 nops=6  (4 variants)
    pos 2: ['UPp', 'URa']
    pos 3: ['UPq', 'URb']
    pos 4: ['UPr', 'URc']
      uplop3_lut_1out_                         [UPg, UPu, UPp, UPq, UPr, uimm8]
      uplop3_lut_1out_1reg__URURUR             [UPg, UPu, UPp, URb, UPr, uimm8]
      uplop3_lut_1out_2reg__URURUR             [UPg, UPu, UPp, URb, URc, uimm8]
      uplop3_lut_1out_3reg__URURUR             [UPg, UPu, URa, URb, URc, uimm8]

### UPLOP3 nops=8  (4 variants)
    pos 3: ['UPp', 'URa']
    pos 4: ['UPq', 'URb']
    pos 5: ['UPr', 'URc']
      uplop3_lut_2out_                         [UPg, UPu, UPv, UPp, UPq, UPr, uimm8, vimm8]
      uplop3_lut_2out_1reg__URURUR             [UPg, UPu, UPv, UPp, URb, UPr, uimm8, vimm8]
      uplop3_lut_2out_2reg__URURUR             [UPg, UPu, UPv, UPp, URb, URc, uimm8, vimm8]
      uplop3_lut_2out_3reg__URURUR             [UPg, UPu, UPv, URa, URb, URc, uimm8, vimm8]

### WARPSYNC nops=2  (3 variants)
    pos 1: ['Ra', 'sImm']
      warpsync__RRR                            [Pp, Ra]
      warpsync_collective__RIR                 [Pp, sImm]
      warpsync_rel__RIR                        [Pp, sImm]

