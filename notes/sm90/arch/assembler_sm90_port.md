# Assembler sm90 port — hardcode audit & arch management

Status of making `assembler/` target both sm90 (Hopper/H800) and sm120
(Blackwell).  `assembler/arch.py` now holds the per-arch config; `arch=`
selects it per call (process default sm120).  This note audits every
hardcode touched or reviewed.

## Per-arch config (`assembler/arch.py`)
| | sm90 | sm120 |
|---|---|---|
| ISA db | `sm90.json` | `sm120.json` |
| `SLOT_DEFAULT_CDESC` (`#spec_const`) | c[0x0][0x208] | c[0x0][0x358] |
| kernel param base | 0x210 | 0x380 |
| `PARAM_CBANK` EIATTR + `.nv.constant0` size | 0x210 | 0x380 |

## Fixed hardcodes (audit)
1. `sm120.json` db path — `__init__.py`, `sass_matcher.create_matcher`,
   `sass_asm.py` CLI (`--arch`) → `arch.db_path()`.
2. `SPEC_CONST_MAP` c[0x0][0x358] (`sass_parser.py`) → `arch.spec_const_map()`.
3. Kernel param base 0x380 — `operand.KernelDecl.param_base` (default_factory
   from arch) and `__init__` result params → `arch.current().param_base`.
4. `PARAM_CBANK` EIATTR 0x380 (`sass_elf.py`, EIATTR 0x0a) → arch param base.
5. `.nv.constant0` size base 0x380 (`sass_elf.py`) → arch param base.
6. `ConditionEvaluator` lacked ternary `?:` — sm90 size predicates use nested
   ternaries (`IDEST_SIZE = ((sz<=4)?1:((sz==5)?2:4))*32`) while sm120's were
   simple; added tokenize `?`/`:` + `_impl` ternary.
7. `LDCU`→`ULDC` cross-arch mnemonic alias (`sass_matcher.py`).

## Confirmed arch-independent (two gens agree)
- `REGCOUNT` opcode set {0x802, 0x402, 0x882} (MOV32I/MOV.64/UMOV).
- mbarrier SYNCS opcodes 0x15b2 / 0x19a7 and EIATTR_MBARRIER flags.
- ELF section layout, EIATTR encodings, `.nv.info` device attrs.
- runner.py KPARAM parsing + launch paths.
- depcheck CFG mnemonic sets (BSSY/BSYNC/BREAK/BRX/JMX … both gens).
- usched/opex/bracket encoding logic.

## Open items (H800 verification)
- **`minimal.cubin` template** (`sass_elf.py` note_nv_tkinfo/cuver read fixed
  byte offsets 0x4b8/0x55c from it) — it is the sm120 template; the toolkit
  note bytes may or may not be accepted on Hopper.  Highest-risk item.
- **`.nv.compat`** content (`TCGEN05_MMA=5`) is Blackwell-flavoured; nvcc sm90
  cubins don't even carry a compat section, so the driver likely ignores it —
  confirm on H800.
- **No `EIATTR_TARGET_INFO`** in the generated cubin — arch is implied; verify
  `cuModuleLoadData` accepts the minimal cubin on H800 (see main audit).
- sm90-only/sm120-only instruction sets (QGMMA vs QMMA/OMMA, ULDC vs LDCU,
  …) — db switch handles encoding; test sources using sm120-only ops must be
  rewritten for Hopper.

## Tests
`tests/asm_construct/test_arch.py` — arch switching, layouts, aliases,
restoration, unknown-arch rejection (assembler-only, no GPU).
