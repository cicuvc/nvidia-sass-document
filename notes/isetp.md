# ISETP — Integer Set-Predicate

**Opcode mnemonic:** ISETP  |  **Pipe:** `int_pipe`  |  **INSTRUCTION_TYPE:** `INST_TYPE_COUPLED_MATH`

## Semantics

Integer comparison producing regular predicate outputs: compares two registers (or register+immediate/constant/UR) and sets up to 3 predicate bits. The most common SASS instruction for conditional branching and predicated execution.

Two forms:
- **Simple:** `Pu = (Ra icmp Rb)` — single comparison, one predicate output
- **Full:** `{Pu, Pv} = bop( (Ra icmp Rb), Pp )` — combined with prior predicate via boolean AND/OR/XOR, two predicate outputs

The EXONLY (`ex`) modifier adds an optional third predicate slot (UPp equivalent for extended predication).

## Variant overview (20 total)

Matrix: {full, simple} × {EX, noEX} × {RRR, RIR, RCR, RCxR, RUR}

| Mode | EX | RRR | RIR | RCR | RCxR | RUR |
|------|----|-----|-----|-----|------|-----|
| Full | noEX | `0x20c` | `0x80c` | `0xa0c` | `0x1a0c` | `0x1c0c` |
| Full | EX | same | same | same | same | same |
| Simple (ALT) | noEX | `0x20c` | `0x80c` | `0xa0c` | `0x1a0c` | `0x1c0c` |
| Simple (ALT) | EX | same | same | same | same | same |

All variants within a source type share the same opcode; the encoding differs in the bop/cop/Pnz fields (pinned to *0/*7 for simple, variable for full).

## Modifiers

| Modifier | Field | Bits | Values |
|----------|-------|------|--------|
| icmp | sco | [78:76] | F=0, LT=1, EQ=2, LE=3, GT=4, NE=5, GE=6, T=7 |
| fmt | sz | [73] | S32=0 |
| bop | bop | [75:74] | AND=0, OR=1, XOR=2 |

Simple ALT: bop→*0, cop→*7, Pnz→*7.
EX variants: Pnz becomes free (UPp slot), input_reg_sz adds Pp@not.

## Bit layout (full RRR noEX — opcode 0x20c)

```
[90:90]              input_reg_sz <= Pp@not
[89:87]              Pnz          <= Pp
[86:84]              cop          <= Pv
[83:81]              Pu           <= Pu
[78:76]              sco          <= icmp
[75:74]              bop          <= bop
[73:73]              sz           <= fmt (S32=0)
[39:32]              Rb           <= Rb
[31:24]              Ra           <= Ra
[15:15]              Pg_not       <= Pg@not
[14:12]              Pg           <= Pg
[91:91],[11:0]       opcode       <= 0b1000001100
```

Simple (ALT): same opcode, but bop=*0(AND), cop=*7(PT), Pnz=*7(PT), input_sz=*0.

## Cross-comparison

| Property | ISETP | UISETP |
|----------|-------|--------|
| Pipe | `int_pipe` | `udp_pipe` |
| Registers | Regular (`Ra`, `Rb`) | Uniform (`URa`, `URb`) |
| Predicates | Regular (`Pu`, `Pv`, `Pg`) | Uniform (`UPu`, `UPv`, `UPg`) |
| Opcode base | `0x20c` | `0x128c` |
| Source variants | RRR,RIR,RCR,RCxR,RUR | URURUR, URIR |
| Modifiers | Same ICmpAll | Same ICmpAll |
| Boolean ops | Same Bop (AND/OR/XOR) | Same Bop |

## Latency

`int_pipe`, `INST_TYPE_COUPLED_MATH`. `FXU_OPS` group in GPR tables. Predicate output uses `MATH_PRED_NO_FP16_FP64_OPS` in PRED tables.

One of the most ubiquitous SASS instructions — appears in virtually every compiled kernel for loop bounds, branch conditions, and predicated data movement.
