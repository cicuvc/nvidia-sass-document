# UISETP — Uniform Integer Set-Predicate

**Opcode mnemonic:** UISETP  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

<!-- arch-scope-banner -->
> **Arch scope:** the *silicon evidence* in this note was collected on RTX 5090
> (sm_120). A real sm_90 rerun is currently blocked because the accompanying test source
> uses sm_120 FORMAT shapes the sm_90 spec rejects at match time.

> Status and follow-up tracking: `notes/sm120/silver-status.md`,
> `notes/sm90/arch/sm90_resilver_audit.md`; Blackwell-only context lives under
> `notes/sm120/`.

## Semantics

Uniform integer comparison producing uniform predicate outputs. Compares two uniform registers (or register+immediate) and sets uniform predicate bits accordingly. Equivalent to `ISETP` for uniform registers.

Two forms:
- **Simple:** `UPu = (URa icmp URb)` — single comparison, one predicate output
- **Full:** `UPu = comp bop UPp; UPv = !comp bop UPp` — combined with the
  input predicate via AND/OR/XOR, two predicate outputs

**Silicon-verified on SM120 (`tests/asm_construct/test_uisetp.py`, RTX 5090):**
all 8 icmp modes (F/LT/EQ/LE/GT/NE/GE/T) × 3 input sets, the full-form
bop/UPp matrix (11 cases: `UPu = comp bop UPp`, `UPv = !comp bop UPp`,
incl. negated `!UPp`), and imm16 operands.

Uniform-datapath notes from the verification:
- A UISETP-written uniform predicate is not reliably readable by the FIRST
  udp consumer — one dummy udp read (a second UISETP using UPp=UP0,
  result discarded) settles it, exactly like LDCU-loaded uniform registers.
- Only udp instructions with a `UniformPredicate` guard (e.g. UMOV) can
  consume uniform predicates; `@UP0 MOV32I` would encode a GPR predicate.
- The 64-bit forms (`.U64`/`.S64`) pass direction tests (signed negatives,
  high-word differences, `LT(1<<32, (1<<32)+1)`) but some equal/low-word
  cases return unexpected results (e.g. `EQ(5,5)=0`, `LT(5,5)=1`) — **open
  question**, likely a sm_120 silicon quirk or a different 64-bit predicate
  convention.

No empirical examples found on sm_90, CUDA 13.1.

## Variant overview

| Variant | Opcode | Format | Outputs |
|---------|--------|--------|---------|
| `uisetp_simple` (ALT) | `0x128c` | `UISETP.icmp UPu, URa, URb` | UPu |
| `uisetp` (full) | `0x128c` | `UISETP.icmp.bop UPu, UPv, URa, URb, UPp` | UPu, UPv |
| `uisetp_optional_upr` | `0x128c` | w/ EXONLY (UPp optional) | UPu, UPv [, UPp] |
| Imm variants | `0x188c` | URb → SImm(32) | same patterns |

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| icmp | sco | [78:76] | F=0, LT=1, EQ=2, LE=3, GT=4, NE=5, GE=6, T=7 |
| fmt | sz | [73] | S32=0 |
| bop | bop | [75:74] | AND=0, OR=1, XOR=2, INVALID3=3 |

For `uisetp_simple` ALT: bop forced to *0 (AND), UPv forced to UPT (*7), UPp forced to UPT (*7).

## Bit layout (simple noimm — opcode 0x128c)

```
[90:90]              input_reg_sz_32_dist <= *0
[89:87]              Pnz                  <= *7 (UPT)
[86:84]              cop                  <= *7 (UPT)
[83:81]              Pu                   <= UPu
[78:76]              sco                  <= icmp
[75:74]              bop                  <= *0 (AND)
[73:73]              sz                   <= fmt (S32=0)
[37:32]              Ra_URb               <= URb
[29:24]              Sa                   <= URa
[15:15]              Pg_not               <= UPg@not
[14:12]              Pg                   <= UPg
[91:91],[11:0]       opcode               <= 0b1001010001100
```

Full variant differs: bop = variable, cop = UPv, Pnz = UPp, input_sz = UPp@not.

## Bit layout (simple imm — opcode 0x188c)

Same as above but URb replaced with 32-bit signed immediate at [63:32].

## Latency

`UDP_subset` group in UGPR. IDEST_SIZE=0 (predicate output, not register).

## Cross-comparison

### UISETP vs ISETP

| Property | ISETP | UISETP |
|----------|-------|--------|
| Pipe | `int_pipe` | `udp_pipe` |
| Registers | Regular (`Ra`, `Rb`) | Uniform (`URa`, `URb`) |
| Predicates | Regular (`Pu`, `Pg`) | Uniform (`UPu`, `UPg`) |
| Comparison types | Same ICmpAll | Same ICmpAll |
| Boolean ops | Same Bop (AND/OR/XOR) | Same Bop |

## Open questions

- No empirical examples found. Under what conditions does ptxas emit UISETP vs ISETP? Likely related to uniform control flow (predicated ULDC/ULEA sequences).
