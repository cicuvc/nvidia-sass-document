# UISETP — Uniform Integer Set-Predicate

**Opcode mnemonic:** UISETP  |  **Pipe:** `udp_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Uniform integer comparison producing uniform predicate outputs. Compares two uniform registers (or register+immediate) and sets uniform predicate bits accordingly. Equivalent to `ISETP` for uniform registers.

Two forms:
- **Simple:** `UPu = (URa icmp URb)` — single comparison, one predicate output
- **Full:** `{UPu, UPv} = bop( (URa icmp URb), UPp )` — combined with prior predicate via boolean AND/OR/XOR, two predicate outputs

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
