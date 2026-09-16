# GB202 固定管线 issue-to-use 周期

状态：第一轮完成，2026-09-17，RTX 5090（GB202，sm_120）。探针：
[`probe_fixed_issue_to_use.py`](../../tests/asm_construct/probe_fixed_issue_to_use.py)。

本文回答一个与 isolated forwarding latency 不同的问题：一条 fixed-pipe
依赖链在所有 issue phase 上持续正确时，producer issue 到 dependent use
究竟需要多少真实 GPU clock。

## 为什么不能直接使用 isolated forwarding gap

一次性 poison/fresh sweep 已证明很多 fixed edge 在 nominal gap 2 就能
读到新值。但该实验把 producer 固定在一个 PC/issue-group phase。把同一
edge 周期性重复后，consumer 会经过其他 phase；某些 phase 接上早期
bypass，另一些 phase 仍读到旧值或中间 payload。

因此至少要区分：

```text
L_isolated(P,C,phase)  # 固定 PC phase 的最早旁路窗口
L_safe(P,C)            # 持续链经过所有 phase 后仍正确的 issue-to-use
T_commit(P)            # scoreboard/RF commit，另一个事件
```

上一轮的 t+2 主要是 `L_isolated`，本轮测量 `L_safe` 和对应真实时钟。

## 方法

每个测试构造一个 32--128 条指令的依赖 block，并循环执行，使 CS2R 的
固定开销和 loop-control 开销可以通过 block size 外推消除。依赖链在两组
寄存器之间交替，并且每一步对值执行 `+1`，所以漏用一次新结果就会在最终
值中留下差异；不再使用可能掩盖 stale read 的恒等 pass-through。

每个配置同时测量：

- dependent chain；
- 相同指令和 scheduling bracket 的 independent chain；
- 相同 scheduling bracket 的 NOP chain。

对 block size `B`，测得：

```text
T_measured(B) = T_steady + H_loop / B + O_clock / (B * loops)
```

使用 `B=64/128` 外推 `T_steady ≈ 2*T(128)-T(64)`。最终值则与总操作数
严格比对。

## scheduling gap 到真实周期的校准

普通 scalar/NOP 流的外推结果：

| encoded nominal gap | steady issue interval |
|---:|---:|
| 1 | 约 2.06 clocks |
| 2 | 约 2.06 clocks |
| 3 | 约 3.05 clocks |
| 4 | 约 4.04 clocks |
| 5 | 约 5.03 clocks |

gap 1/2 都被单 warp/调度前端约两拍的 floor 覆盖。不能把 bracket 中的
数字直接当成真实时钟，也不能把长链未外推的 CS2R 平均值直接使用。

## 普通 fixed scalar 结果

当前用非恒等 recurrence 验证的代表：

| leaf | 指令 | nominal gap 2/3 | 首个持续正确 gap | 外推真实 issue-to-use |
|---|---|---|---:|---:|
| ALU Lite | `IADD` | 静默错误 | **4** | **约 4.04 clocks** |
| ALU Heavy | `IADD3` | 静默错误 | **4** | **约 4.04 clocks** |
| FMA Lite | `FADD` | 静默错误 | **4** | **约 4.04 clocks** |
| FMA Lite | `FFMA` | 静默错误 | **4** | **约 4.04 clocks** |
| FMA Heavy LO | `IMAD` | 静默错误 | **4** | **约 4.04 clocks** |
| coupled packed FP | `HADD2` | 静默错误 | **4** | **约 4.04 clocks** |

`MOV` 的 alternating pass-through control 也只在 gap 4 后收敛到正确值，
但它不是每步 `+1` 的强校验，因此暂列为 corroborating evidence。

在 gap 2/3 时，dependent、independent 和 NOP 的耗时完全相同；也就是
普通 fixed RAW 没有自动 hardware interlock。错误仅反映在最终数值中，
kernel 不会变慢、不会 fault、也不会等待正确结果。

这恢复了早期 cuBLAS/ptxas corpus 中常见的 4-cycle dependent schedule：

- isolated t+2 是某个 phase 上真实存在的 early bypass；
- sustained issue-to-use 需要覆盖所有 phase，当前为约 4 clocks；
- 静态表中的 4 对普通 FMA 恰好接近该值；INT 表中的 6 仍然保守。

## `IMAD.WIDE`

`IMAD.WIDE` 使用 low result 构造 `x <- x+1` 的跨 pair 依赖链。外推结果：

| 流 | nominal gap 2 时真实间隔 | phase-safe/steady 结果 |
|---|---:|---:|
| NOP control | 约 2.05 | — |
| independent `IMAD.WIDE` | **约 4.03** | initiation/service 约 4 clocks |
| dependent low->next-WIDE | **约 7.01** | dependent issue-to-use 约 7 clocks |

当 encoded gap 增大到 5 时，dependent 与 independent 都收敛到约
7.01 clocks/op。较小 encoded gap 下，dependent 流本身被内部
admission/operand availability 拉长，而 independent 流只承受 WIDE 的
约 4-cycle service cost。

所以 simulator 的初始模型应为：

```text
IMAD.WIDE initiation interval       ≈ 4 clocks
IMAD.WIDE low -> IMAD.WIDE use      ≈ 7 clocks
```

这不否定 isolated sweep 中 WIDE low 对普通 Lite/FMA consumer 的 t+1
bypass；它说明 WIDE->WIDE 自身使用的是另一条、明显更晚的 dependent path。

### `IMAD.HI` 的 Rc-high 路径

另一条 recurrence 令 `IMAD.HI` 从 64-bit `Rc` 的 high half 读取前一条
结果，并利用 low-half carry 每次执行 `high <- high+1`。该链从 nominal
gap 2 起就持续正确；dependent 与 independent 耗时一致：

```text
IMAD.HI independent service                 ≈ 4.03 clocks/op
IMAD.HI result -> next IMAD.HI Rc.high use  ≈ 4.03 clocks/op
```

因此 HI/WIDE 不能共用一个“FMA-Heavy-wide latency”：

- WIDE low 作为下一条 WIDE 的 `Ra`：约 7 clocks；
- HI result 作为下一条 HI 的 `Rc.high`：被约 4-clock service 完全覆盖。

这里同时混入了 operand-slot/collector 差异。尚不能据此断言
`IMAD.HI -> IMAD.HI.Ra` 也是 4 clocks。

[`probe_fixed_hi_ra_issue_to_use.py`](../../tests/asm_construct/probe_fixed_hi_ra_issue_to_use.py)
随后专门测了 `Ra`。由于 `IMAD.HI` 是 signed multiply，简单 `x+1`
recurrence 不成立；探针改用一条不会在短 block 内收敛的 signed nonlinear
recurrence，每轮重置后执行 8--20 个 HI，并在 loop 内校验最终值。这样既
覆盖不同 issue phase，又不会因长期收敛到 fixed point 而掩盖 stale read。

结果是 nominal gap 1--3 每轮都错误，gap 4 开始正确。正确链的原始均值为：

| block size | clocks/op（含每轮 reset/check） |
|---:|---:|
| 8 | 19.894 |
| 16 | 14.453 |
| 20 | 13.367 |

按 `T(B)=Tsteady+H/B` 消去每轮固定开销，`B=16/20` 给出约 **9.02
clocks/op**，`B=8/16` 给出约 **9.01 clocks/op**。因此初始模型应明确
区分：

```text
IMAD.HI result -> next IMAD.HI Rc.high use  ≈ 4 clocks
IMAD.HI result -> next IMAD.HI Ra use       ≈ 9 clocks
```

nominal gap 4 只是触发/允许内部 dependent admission 拉长到约 9 clocks，
不能直接把 bracket 数字 4 当作这条边的真实 issue interval。

### WIDE low/high 到普通 fixed leaf

[`probe_fixed_wide_cross_issue_to_use.py`](../../tests/asm_construct/probe_fixed_wide_cross_issue_to_use.py)
把反向的 consumer-result -> next-WIDE edge 固定留出 nominal 8 cycles，
只扫描 WIDE -> consumer。low recurrence 故意使用非零的 `Rc.low`，构造
`WIDE(x*1+bias).low`；这能区分最终 low result 和 ALU-Heavy t+1 窗口中
曾观察到的 early `Ra` payload。high recurrence 由
`WIDE(0 + {0,x}).high` 构造。每项连续经过 1024 次依赖，并用最终值排除
silent stale read。

| WIDE result | consumer leaf / 指令 | 首个持续正确 nominal gap | 对应单-warp issue 间隔 |
|---|---|---:|---:|
| low | ALU Lite `IADD` | **1** | **不大于约 2.06 clocks** |
| low | ALU Heavy `IADD3` / `LEA` | **3** | **约 3.05 clocks** |
| low | FMA Lite `FADD` | **1** | **不大于约 2.06 clocks** |
| low | FMA Heavy `IMAD` | **1** | **不大于约 2.06 clocks** |
| low | coupled packed FP `HADD2` | **1** | **不大于约 2.06 clocks** |
| high | ALU Lite `IADD` | **4** | **约 4.04 clocks** |
| high | ALU Heavy `IADD3` / `LEA` | **5** | **约 5.03 clocks** |
| high | FMA Lite `FADD` | **4** | **约 4.04 clocks** |
| high | FMA Heavy `IMAD` | **4** | **约 4.04 clocks** |
| high | coupled packed FP `HADD2` | **4** | **约 4.04 clocks** |

ALU-Heavy 的 high 行已经把第二个源放在偶数 bank，排除了 `R41 + R29`
形成 2O RF collect 冲突的解释；再用 `LEA` 重测仍然是 gap 5。因此当前
证据支持：

- WIDE low 到 Lite/FMA/coupled leaf 有单独的极早 forwarding path；
- ALU Heavy 在更早窗口读到的不是 final low，而是 `Ra`；final low 要到
  约 3 clocks 才能被该 leaf 使用；
- WIDE high 明显更晚才可见；
- high 到 ALU-Heavy 又比到 Lite/FMA/coupled leaf 晚约一拍，说明
  consumer-use offset 不能只由 producer result-ready 一个标量表示；
- WIDE low -> next WIDE 的 7 clocks 更不是 low result 的普适延迟，而是
  下一条 WIDE 自身的 operand/admission 路径。

## 与 forwarding 表的修正关系

不能简单地把 isolated forwarding gap 当作 issue-to-use。当前应采用：

| 场景 | simulator 事件 |
|---|---|
| 单次、已知 issue phase 的精细重放 | 使用 consumer-specific isolated bypass 表 |
| 普通持续 fixed scalar dependency | phase-safe issue-to-use = 4 clocks |
| `IMAD.WIDE` independent | service/initiation = 4 clocks |
| `IMAD.WIDE -> IMAD.WIDE` low dependency | issue-to-use = 7 clocks |
| `IMAD.WIDE.low -> Lite/FMA/packed leaf` | 单 warp 可观测上限约 2.06 clocks |
| `IMAD.WIDE.low -> ALU Heavy` | final result issue-to-use 约 3 clocks |
| `IMAD.WIDE.high -> Lite/FMA/packed leaf` | issue-to-use 约 4 clocks |
| `IMAD.WIDE.high -> ALU Heavy` | issue-to-use 约 5 clocks |
| `IMAD.HI -> IMAD.HI Rc.high` dependency | service 覆盖，约 4 clocks |
| `IMAD.HI -> IMAD.HI Ra` dependency | operand-specific issue-to-use 约 9 clocks |
| fixed architectural RF commit | 独立约 5.4--5.8-clock completion/commit event |
| FP64/CLMAD | redirect queue + SM-wide service + scoreboard event |

也就是说，普通 fixed pipeline 至少需要两个 result-ready 状态：

```text
early_forward_ready[consumer, phase]
phase_safe_use_ready
```

RF commit 仍是第三个更晚且受 parity-bank arbitration 影响的状态。

## Predicate 持续 issue-to-use

[`probe_fixed_pred_issue_to_use.py`](../../tests/asm_construct/probe_fixed_pred_issue_to_use.py)
用 `PLOP3` 构造 `P0 <- !P0` 的 bit-exact recurrence。local predicate 输入
在 gap 1--3 时静默错误，从 nominal gap 4 开始持续正确；`B=63/127`
外推得到：

```text
PLOP3 result -> next PLOP3 predicate input ≈ 4.03 clocks
```

这与普通 GPR recurrence 的约 4.04 clocks 相同。isolated `PLOP3 -> P2R`
t+2 仍然只是更早的特定 phase loopback。

[`probe_fixed_pred_guard_issue_to_use.py`](../../tests/asm_construct/probe_fixed_pred_guard_issue_to_use.py)
进一步令 `PLOP3` 交替产生 true/false，并统计 predicated consumer 真正
执行的次数。结果显示 effective guard 不是一个全局事件，而依赖 consumer：

| producer -> guarded consumer | 首个持续正确 nominal gap |
|---|---:|
| `PLOP3 -> @P0 IADD`（ALU Lite） | **5** |
| `PLOP3 -> @P0 IADD3`（ALU Heavy） | **5** |
| `PLOP3 -> @P0 FADD`（FMA Lite） | **5** |
| `PLOP3 -> @P0 HADD2`（coupled packed FP） | **5** |
| `PLOP3 -> @P0 IMAD`（FMA Heavy） | **12** |
| `PLOP3 -> @P0 MOV32I`（无源 ALU-Lite op） | **12** |

`MOV32I` 行使用独立 accumulator，并给 guarded MOV 之后留出 12 cycles，
排除了“marker 尚未转发到计数器”的假象。它复现了旧 isolated/coarse
guard probe 的 12-cycle 结果。

最合理的初始解释是两种 predication point：

- 普通带 operand collection 的 ALU Lite/Heavy、FMA Lite 和 packed-FP
  可以携带 local-forwarded predicate 到较后的 execute/squash stage；
- 无源 `MOV32I` 和 FMA-Heavy admission 需要较早获得 distributed/effective
  predicate，因此落在约 12-cycle 路径。

这仍是行为模型；尚未证明具体哪一级保存 predicate tag。

## 下一步

仍需用同一 recurrence 方法补齐：

- ALU Heavy 各 result sub-class，而不只 `IADD3`；
- scalar `FHADD/FHFMA` 的 raw16 与 formatted-FP32 path；
- `IMUL32I.WIDE` 和 WIDE high-half 到下一条 wide-op 的 dependency；
- `_32I` packed-FP 特殊形式和 `HADD2.F32`；
- 其他 predicate producer、source-less/FMA-Heavy guard 特例以及 CBU branch
  的持续链；
- cross-leaf P->C 周期链，用来区分 producer result-ready 与 consumer-use
  offset，而不是只得到二者之差。
