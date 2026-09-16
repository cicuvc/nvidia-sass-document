# GB202 固定管线延迟研究交接

状态：**2026-09-17 主动暂停，可从本文继续**。实验机器为本地 RTX 5090
（GB202，sm_120）。本阶段没有提交 commit；工作树中还有大量其他研究任务
留下的修改和未跟踪文件，恢复工作时不要用 reset/checkout 清理整个仓库。

## 1. 当前目标与暂停位置

最终目标是为 cycle-accurate simulator 建立 fixed-latency scalar pipeline
模型。本阶段已经从“单次 producer/consumer 能在多早看到某个 payload”推进到：

1. 区分 isolated、phase-safe、RF commit 三类事件；
2. 校准 SASS scheduling gap 与真实 steady GPU clocks；
3. 测得普通 ALU/FMA、WIDE/HI 和 predicate 的第一批持续依赖延迟；
4. 证明 latency 不能只按 producer mnemonic 存一个标量，至少还取决于
   consumer leaf、operand slot 和 issue phase。

暂停点位于 `IMAD.HI.Ra` 路径刚测完之后。下一步尚未开始的是
`IMUL32I.WIDE`、WIDE high -> wide-op、scalar FHADD/FHFMA 以及更完整的
cross-leaf 矩阵。

## 2. 必须保留的三个时间概念

```text
L_isolated(P,C,phase)  # 固定 PC/issue phase 的最早可见 payload
L_safe(P,C,operand)    # 持续链在所有经过的 phase 上均正确
T_commit(P,bank)       # 最终 RF/PRED file commit；还受写回仲裁影响
```

此前 poison/fresh 探针得到的大量 t+1/t+2 是第一类事件，不能直接用作持续
RAW 链的 issue-to-use。普通 fixed scalar 的 isolated early bypass 可以在
t+2 出现，但 phase-safe chain 实测仍需要约 4 clocks。

simulator 至少应保存：

```text
early_forward_ready[producer_class, consumer_leaf, operand, phase]
phase_safe_use_ready[producer_class, consumer_leaf, operand]
architectural_commit_ready[rf_bank]
```

## 3. 已确认结果

### 3.1 scheduling gap 校准

长 block/loop 外推得到：

| nominal gap | steady single-warp interval |
|---:|---:|
| 1 | 约 2.06 clocks |
| 2 | 约 2.06 clocks |
| 3 | 约 3.05 clocks |
| 4 | 约 4.04 clocks |
| 5 | 约 5.03 clocks |

gap 1/2 均被单 warp 前端/调度 floor 覆盖。不要把 bracket 数字直接当真实
clock，也不要直接使用未按 block size 外推的 CS2R 平均值。

### 3.2 普通 fixed scalar

以下 non-identity recurrence 在 nominal gap 2/3 均静默读错，在 gap 4
开始持续正确：

| leaf | 代表指令 | phase-safe issue-to-use |
|---|---|---:|
| ALU Lite | `IADD` | 约 4.04 clocks |
| ALU Heavy | `IADD3` | 约 4.04 clocks |
| FMA Lite | `FADD`, `FFMA` | 约 4.04 clocks |
| FMA Heavy LO | `IMAD` | 约 4.04 clocks |
| coupled packed FP | `HADD2` | 约 4.04 clocks |

错误 gap 下 dependent、independent 和 NOP 流耗时相同：普通 fixed RAW
没有自动 interlock；只会产生错误结果，不会自动等待或 fault。

### 3.3 WIDE/HI operand-specific 路径

| edge | 当前建模值 |
|---|---:|
| independent `IMAD.WIDE` initiation/service | 约 4.03 clocks |
| `WIDE.low -> next WIDE.Ra` | 约 7.01 clocks |
| `WIDE.low -> Lite/FMA/packed` | 不大于约 2.06 clocks |
| `WIDE.low -> ALU Heavy` final low | 约 3.05 clocks |
| `WIDE.high -> Lite/FMA/packed` | 约 4.04 clocks |
| `WIDE.high -> ALU Heavy` | 约 5.03 clocks |
| `IMAD.HI result -> next HI.Rc.high` | 约 4.03 clocks |
| `IMAD.HI result -> next HI.Ra` | 约 9.02 clocks |

两个关键陷阱：

- WIDE low 的 early `Ra` payload：若 recurrence 使用 `WIDE(x*1).low=x`，
  ALU Heavy 读到 early `Ra` 也会“看似正确”。必须加入非零 `Rc.low`；修正
  后 final low 到 ALU Heavy 是约 3 clocks。
- `IMAD.HI` 是 signed multiply，不能用假定 unsigned 的简单 `x+1`
  recurrence。`HI.Ra` 探针使用每轮重置的短 nonlinear chain，避免长期
  收敛到 fixed point 后掩盖 stale read。block size 8/16/20 两组外推均给出
  约 9.01--9.02 clocks。

### 3.4 Predicate

| edge | 结果 |
|---|---:|
| `PLOP3 -> next PLOP3` local predicate input | 约 4.03 clocks |
| `PLOP3 -> @P0 IADD/IADD3/FADD/HADD2` | 首个正确 nominal gap 5 |
| `PLOP3 -> @P0 IMAD` | 首个正确 nominal gap 12 |
| `PLOP3 -> @P0 MOV32I` | 首个正确 nominal gap 12 |

这表明 effective guard 不是单一全局 ready event。普通带源 consumer 似乎
能把 local-forwarded predicate 带到较后的 execute/squash point；FMA Heavy
admission 和 source-less `MOV32I` 需要更早得到 distributed/effective
predicate。这里仍是行为模型，尚未定位精确物理 stage。

### 3.5 RF commit

fixed architectural RF commit 仍应作为独立事件，当前约 5.4--5.8 clocks，
并受 even/odd bank 的 1W 写回仲裁影响。不能因某条 bypass 在 2--4 clocks
可用，就认为结果已写入 RF。

## 4. 文件入口

综合结论：

- [`fixed_pipeline_issue_to_use_zh.md`](fixed_pipeline_issue_to_use_zh.md)：
  本轮持续链、真实 clock 外推和 simulator 修正规则；恢复时先读此文件。
- [`fixed_pipeline_forwarding_latency_zh.md`](fixed_pipeline_forwarding_latency_zh.md)：
  isolated forwarding、跨 leaf、predicate、MIO/R2UR/UDP 和 commit 总表。
- [`gb202_compute_pipelines.md`](gb202_compute_pipelines.md)：管线/queue 拓扑。

各 leaf 的原始 latency 分类：

- [`alulite_latency.md`](alulite_latency.md)
- [`aluheavy_latency.md`](aluheavy_latency.md)
- [`fmalite_latency.md`](fmalite_latency.md)
- [`fmaheavy_latency.md`](fmaheavy_latency.md)
- [`fp16_latency.md`](fp16_latency.md)
- [`fp64_redirect_latency.md`](fp64_redirect_latency.md)

本轮主要探针：

| probe | 用途 |
|---|---|
| `tests/asm_construct/probe_fixed_issue_to_use.py` | 普通 scalar、WIDE->WIDE、HI Rc.high 的 dependent/independent/NOP 长链 |
| `tests/asm_construct/probe_fixed_wide_cross_issue_to_use.py` | WIDE low/high 到各 ordinary leaf；包含 non-identity bias |
| `tests/asm_construct/probe_fixed_hi_ra_issue_to_use.py` | 每轮重置 nonlinear chain，测 HI result -> HI.Ra |
| `tests/asm_construct/probe_fixed_pred_issue_to_use.py` | `PLOP3` local predicate recurrence |
| `tests/asm_construct/probe_fixed_pred_guard_issue_to_use.py` | consumer-specific effective guard |
| `tests/asm_construct/probe_*latency.py` | 各 leaf 的 isolated poison/fresh sweep |

## 5. 推荐复现命令

从仓库根目录执行。探针有意使用 `check_deps=False` 发出不安全 RAW schedule，
这是实验本身，不应“修复”为 dependency checker 自动拒绝。

```bash
python3 tests/asm_construct/probe_fixed_issue_to_use.py \
  --op IADD --op IADD3 --op FADD --op FFMA --op IMAD --op HADD2 \
  --gap 2 --gap 3 --gap 4 --gap 5 --count 64 --loops 64 --reps 3

python3 tests/asm_construct/probe_fixed_wide_cross_issue_to_use.py \
  --gap 1 --gap 2 --gap 3 --gap 4 --gap 5 \
  --count 32 --loops 32 --reps 3

python3 tests/asm_construct/probe_fixed_hi_ra_issue_to_use.py \
  --gap 1 --gap 2 --gap 3 --gap 4 --gap 5 \
  --count 16 --loops 64 --reps 3

python3 tests/asm_construct/probe_fixed_pred_issue_to_use.py
python3 tests/asm_construct/probe_fixed_pred_guard_issue_to_use.py
```

`HI.Ra` 的 9-clock 外推还需要分别运行 `--count 8`、`16`、`20`；不要让
nonlinear chain 太长，因为当前选择的映射约 22 步后会进入 fixed point。

## 6. 探针设计规则与已踩坑

1. **必须校验最终值。** 错误 schedule 通常不变慢，只静默返回 stale 或
   internal payload。
2. **不要用恒等 pass-through 作为唯一证明。** 它可能让 early operand
   payload 与 final result 相同，WIDE low -> ALU Heavy 已实际踩中此坑。
3. **同时测 dependent/independent/NOP。** 否则无法区分 latency、pipe
   service interval 和 loop/CS2R 开销。
4. **按两个以上 block size 外推。** 使用
   `T(B)=Tsteady+H/B+O/(B*loops)`，而不是直接报告单个平均值。
5. **控制 RF bank 组合。** WIDE high 固定写 odd register；测试 ALU Heavy
   时应把其他源放到 even bank，并至少用两条指令（本轮为 `IADD3`/`LEA`）
   复核，避免把 collect conflict 当 latency。
6. **反向依赖要充分 pad。** cross-edge recurrence 中只扫描 P->C 时，C->P
   固定使用 nominal 8，避免两个方向混在一起。
7. **predicate guard 要排除 marker forwarding。** `MOV32I` guard 探针使用
   独立 accumulator，并在 guarded marker 后留足距离。
8. **loop control 自身也有 latency。** 当前模板对计数器、ISETP、BRA 使用
   保守 padding；缩短它们会出现多跑一轮或错误 branch 的假象。
9. **不要把 nominal gap 4 等同于 4 clocks。** 例如 `HI.Ra` 在 gap 4
   才正确，但内部 dependent admission 将 steady interval 拉到约 9 clocks。

## 7. 下一步优先级

建议按以下顺序恢复：

1. `IMUL32I.WIDE`：复刻 WIDE low/high cross-leaf 和 self-chain，判断其与
   `IMAD.WIDE` 是否共享全部 result stages。
2. WIDE high -> 下一条 WIDE/HI 的 operand-slot 矩阵，尤其 `Ra`、`Rc.low`
   和 `Rc.high`；沿用短 recurrence/reset 方法，避免恒等和收敛问题。
3. scalar `FHADD/FHFMA`：分别测 raw16 result 与 formatted-FP32 result，
   再与 packed `HADD2/HFMA2` 对照。
4. `_32I` packed-FP、`HADD2.F32` 等特殊 form，确认 immediate decode 和
   result stage 是否改变 phase-safe latency。
5. 扩展 ALU Heavy result subclass，不只 `IADD3/LEA`；优先覆盖 shift、
   permute、predicate merge 和 conversion。
6. 其他 predicate producer 及 CBU branch 的持续链，验证当前 guard=5/12
   分流是否由 producer class 改变。
7. 最后建立完整 cross-leaf P->C 方程组，将 producer result-ready 与
   consumer-use offset 分离，而不是只保存二者之差。

## 8. 恢复工作时的最短检查清单

```text
[ ] 先读 issue-to-use 总结和本文
[ ] 确认本地 GPU 仍是 GB202/sm_120，时钟状态没有明显变化
[ ] 先复跑 IADD gap 3/4 与 WIDE low->ALU Heavy gap 2/3 两个 canary
[ ] 新 probe 必须有 non-identity correctness oracle
[ ] 至少两个 block size，至少三次重复
[ ] 分开记录 nominal gap、实际 clocks、service interval 和最终值
[ ] 更新综合文档、leaf 文档和本交接的“下一步”状态
```

如果 canary 不再复现，首先检查 GPU clock/power state、loop-control schedule、
assembler encoding 是否变化以及是否误开了 dependency checker；不要先修改
已经记录的 latency 模型。
