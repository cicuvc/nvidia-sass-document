# GB202 固定执行管线转发延迟总表

本文汇总 RTX 5090（GB202，sm_120）上固定延迟执行域的实测转发信息，
供 cycle-accurate simulator 直接使用。覆盖范围包括：

- ALU Lite；
- ALU Heavy；
- FMA Lite；
- FMA Heavy；
- coupled packed-FP16；
- UDP/URF 固定算术路径；
- 固定结果到 MIO late collector、CBU late-read 和 `R2UR` 的入口；
- GPR、predicate 和最终 RF commit 之间的区别。

详细的逐类实验记录仍保留在：

- [`alulite_latency.md`](alulite_latency.md)
- [`aluheavy_latency.md`](aluheavy_latency.md)
- [`fmalite_latency.md`](fmalite_latency.md)
- [`fmaheavy_latency.md`](fmaheavy_latency.md)
- [`fp16_latency.md`](fp16_latency.md)
- [`udp_urf_topology.md`](udp_urf_topology.md)
- [`../sm90/arch/pipe_forwarding.md`](../sm90/arch/pipe_forwarding.md)
- [`../sm90/arch/pipe_forward_survey.md`](../sm90/arch/pipe_forward_survey.md)

## 1. 术语和计时口径

本文的 `t+N` 或 gap `N` 表示 producer 与 consumer 的**名义发射距离**。
producer 使用 `stall=1`，其余距离由 NOP 填充；consumer 不等待
scoreboard，因此 stale/fresh 边界直接暴露旁路网络何时能够提供值。

使用了两种等名义距离的填充布局：

- `fine`：多个 stall-1 NOP；
- `coarse`：较少的 NOP，每条携带较大的 stall。

若两者不同，表中同时给出：

- `fine`：密集布局中测到的最早永久 fresh 边界；
- `safe`：对指令打包和 issue-group 相位更稳健的 coarse 边界。

因此 `3 fine / 4 safe` 的 simulator 建议值是 **4**。孤立出现一次 fresh、
随后又变 stale 的窗口不算 ready event。

这些数字是 **consumer-visible forwarding ready time**，不是：

- 指令 initiation interval；
- execution pipe occupancy；
- result queue 深度；
- 最终 RF/PRED file 写回时间；
- `sm_90_latencies.txt` 中的保守调度表值。

早期短 unrolled probe 受 CS2R/前后端固定开销影响，曾给出约 2.5--3
clocks/op；新的 block-loop 外推把 steady single-warp issue floor 校准为
约 **2.06 clocks/op**。因此 `t+1/t+2` 仍应理解为 SASS 调度距离和相对
pipeline event，而不是未经校准的精确物理周期。

后续持续依赖链证明：isolated t+2 是 phase-specific early bypass，而不是
所有 PC/issue phase 都安全的 issue-to-use latency。普通 ALU/FMA/packed
scalar 链需要约 **4.04 clocks** 才能持续正确；`IMAD.WIDE -> IMAD.WIDE`
low dependency 约为 **7.01 clocks**。详见
[`fixed_pipeline_issue_to_use_zh.md`](fixed_pipeline_issue_to_use_zh.md)。
同一轮 non-identity recurrence 还把 WIDE low/high 拆开：low 到
Lite/FMA/packed leaf 不超过约 2.06 clocks，但 final low 到 ALU Heavy
约 3.05 clocks；high 到 Lite/FMA/packed leaf 约 4.04 clocks，到 ALU Heavy
约 5.03 clocks。

## 2. 固定 GPR 结果总览

四种 consumer leaf 的探测指令为：

| consumer leaf | 探测指令 | 作用 |
|---|---|---|
| ALU Lite | `MOV` | bit-preserving copy |
| ALU Heavy | `IADD3 ..., RZ, RZ` | bit-preserving add-zero |
| FMA Lite | `FADD ..., RZ` | 对选定 normal-FP32 payload 保持位值 |
| FMA Heavy | `IMAD ..., 1, RZ` | bit-preserving integer multiply-by-one |

最常用的 simulator 快速表如下：

| producer 类别 | ALU Lite | ALU Heavy | FMA Lite | FMA Heavy |
|---|---:|---:|---:|---:|
| 普通 FMA Lite FP32 | 2 | 2 | 2 | 2 |
| `FSWZADD` | 2 | 2 | 2 | 2 |
| 普通 FMA Heavy LO | 2 | 3 fine / **4 safe** | 2 | 2 |
| 普通 packed `HADD2/HMUL2/HFMA2` | 2 | 2 | 2 | 2 |
| `HADD2.F32` | 2 | 3 fine / **4 safe** | 2 | 2 |
| scalar `FHADD/FHFMA` | 2 | 3 fine / **4 safe** | 2 | 2 |

ALU Lite 和 ALU Heavy 的 instruction-dependent 分类见后文。不能用一个
全局的“INT latency”或“FMA latency”替代这些 producer/consumer 组合。

## 3. ALU Lite producer

动态 ALU-Lite 集合主要包括：

```text
FMNMX FSEL FSET FSETP IADD IADD32I IMNMX ISETP MOV SEL
```

GPR 输出：

| producer | -> ALU Lite | -> ALU Heavy | -> FMA Lite |
|---|---:|---:|---:|
| `FMNMX/FSEL/FSET/IMNMX/SEL` | 2 | 2 | 2 |
| `MOV/IADD/IADD32I` | 2 | 3 fine / **4 safe** | 2 |

ALU-Lite producer 到 FMA-Heavy consumer 尚未按每个 mnemonic 做完整孤立矩阵，
不要仅因为 ALU Lite 与 FMA Heavy 位于同一个 physical macro 就自动填 2。

`IADD/IADD32I -> IADD3` 在非法早读窗口看到的是 `Ra`，不是旧 `Rd`，
也不是最终 sum；`MOV -> IADD3` 还可能看到 launch/residue garbage。对正确
调度的 simulator，只需把 t+4 以前标为 not-ready；若希望重现 malformed
SASS，才需要描述这些 payload。

## 4. ALU Heavy producer

实测集合：

```text
BMSK F2FP F2IP I2FP I2I I2IP IABS IADD3 ISCADD ISCADD32I
LEA LOP LOP3 LOP32I P2R PLOP3 PRMT PSETP R2P SGXT SHF SHL SHR
HMNMX2 HSET2 HSETP2
```

所有 GPR-producing ALU-Heavy 指令到 ALU Heavy 自己都是 **t+2**。

到 ALU Lite：

| 边界 | producer |
|---|---|
| **2** | `IABS`, `I2I`, `I2IP` |
| 3 fine / **4 safe** | `BMSK`, `F2FP`, `F2IP`, `I2FP`, `IADD3`, `ISCADD`, `ISCADD32I`, `LEA`, `LOP`, `LOP3`, `LOP32I`, `P2R`, `PRMT`, `SGXT`, `SHF`, `SHL`, `SHR`, `HMNMX2`, `HSET2` |

到 FMA Lite：

| 边界 | producer |
|---|---|
| **2** | `IADD3`, `LOP`, `LOP3`, `PRMT`, `SHL`, `SGXT`, `HMNMX2`, `HSET2` |
| 3 fine / **4 safe** | `BMSK`, `F2FP`, `F2IP`, `I2FP`, `I2I`, `I2IP`, `IABS`, `ISCADD`, `ISCADD32I`, `LEA`, `LOP32I`, `P2R`, `SHF`, `SHR` |

ALU-Heavy producer 到 FMA-Heavy leaf 尚未完成同等粒度的逐 mnemonic 孤立扫描。
已经证明的是结果可进入公共 fixed-result staging/bypass，而不是每一种
ALU-Heavy result tag 都必然在 t+2 被 FMA Heavy 收集。

## 5. FMA Lite producer

### 5.1 普通 FP32

```text
FADD FADD32I FFMA FFMA32I FMUL FMUL32I
```

以上指令到 ALU Lite、ALU Heavy、FMA Lite、FMA Heavy 均为 **t+2**。
add、multiply、fused multiply-add 和 immediate form 没有测出差异。

### 5.2 scalar `FHADD/FHFMA`

这些指令读取 F16/BF16 scalar source，但 architectural result 是 FP32：

| consumer | 最终 FP32 ready |
|---|---:|
| ALU Lite | 2 |
| FMA Lite | 2 |
| FMA Heavy | 2 |
| ALU Heavy | 3 fine / **4 safe** |

ALU Heavy 在 t+2 会读到格式化之前的窄 payload：

| 模式 | 最终结果 | t+2 的 ALU-Heavy 观察值 |
|---|---:|---:|
| F16 | `0x3f800000` | `0x00003c00` |
| BF16 | `0x3f800000` | `0x00003f80` |

同一时刻其他 consumer 已经看到最终 FP32。因此不能把它建模成一个全局
`Rd` 先写 raw16、再改成 FP32；正确模型是 consumer-selective bypass node。

## 6. FMA Heavy producer

### 6.1 普通 32-bit result

```text
FSWZADD IDP.2A IDP.4A IMAD.LO IMUL IMUL32I.LO
```

`FSWZADD` 到四种 leaf 均为 t+2。其余普通 FMA-Heavy LO：

| consumer | 最终结果 ready |
|---|---:|
| ALU Lite | 2 |
| FMA Lite | 2 |
| FMA Heavy | 2 |
| ALU Heavy | 3 fine / **4 safe** |

后者在 ALU-Heavy t+2 窗口读到的始终是原始 `Ra`：

- IDP 不是 dot-product 中间结果；
- IMAD 不是 multiplier product；
- IMUL 不是最终 product；
- immediate form 也返回 register source `Ra`。

这说明 Shared-FMA-Heavy macro 内部存在一个可被 ALU-Heavy input path
误接入的 early operand/pass-through node。

### 6.2 `HI/WIDE`

| 输出 | ALU Lite | ALU Heavy | FMA Lite | FMA Heavy |
|---|---:|---:|---:|---:|
| `IMAD.WIDE` low | **1** | 最终值 2；t+1 为 `Ra` | **1** | **1** |
| `IMUL32I.WIDE` low | **1** | 最终值 2；t+1 为 `Ra` | **1** | **1** |
| `IMAD.WIDE` high | 2 | 3 fine / **4 safe** | 2 | 2 |
| `IMUL32I.WIDE` high | 2 | 3 fine / **4 safe** | 2 | 2 |
| `IMAD.HI` result | 2 | 3 fine / **4 safe**；t+2 为 `Ra` | 2 | 2 |

WIDE low 的 t+1 只表示 low-result bypass 很早，并不表示 HI/WIDE 的
execution occupancy 很短。已有吞吐结果仍为：

- LO 约 0.5 inst/cycle；
- HI/WIDE 约 0.25 inst/cycle。

## 7. Coupled packed-FP16

普通 register forms：

```text
HADD2 HMUL2 HFMA2 HFMA2.MMA
```

它们同时占用 FMA Heavy 和 FMA Lite，但最终 packed result 向四种 scalar
leaf 统一在 **t+2** 可见。两个 leaf 的 occupancy 不代表结果串行经过两级。

特殊形式：

| producer | ALU Lite/FMA Lite/FMA Heavy | ALU Heavy |
|---|---:|---:|
| `HADD2_32I` | 2 | 2 |
| `HMUL2_32I` | 2 | 3 fine / **4 safe**；t+2 为 `Ra` |
| `HFMA2_32I` | 2 | 3 fine / **4 safe**；t+2 为 `Ra` |
| `HADD2.F32` | 2 | 3 fine / **4 safe**；t+2 仍 stale |

## 8. Predicate 转发

predicate 至少有三个可观察目的地：

1. ALU-Lite selector，如 `SEL ..., P0`；
2. ALU-Heavy predicate-file read，如 `P2R`；
3. effective guard/CBU distribution，如 `@P0 instruction` 和 `@P0 BRA`。

后续持续链进一步发现，`@P0 instruction` 本身还要按 consumer 分类：
`PLOP3 -> @P0 IADD/IADD3/FADD/HADD2` 在 nominal gap 5 持续正确，而
`@P0 IMAD` 和无源 `@P0 MOV32I` 仍需要 gap 12。以下旧表中的
“instruction guard=12”特指原始 `@P0 MOV32I` 探针，不能推广到所有 fixed
consumer。完整修正见
[`fixed_pipeline_issue_to_use_zh.md`](fixed_pipeline_issue_to_use_zh.md)。

### 8.1 ALU-Lite predicate producer

`FSETP/ISETP/IADD.Pu/IADD32I.Pu`：

| consumer | fine | safe coarse |
|---|---:|---:|
| selector | 3 | **4** |
| `P2R` | 3 | **4** |
| effective instruction guard | 7 | **12** |
| CBU branch | 7 | **12** |

### 8.2 ALU-Heavy predicate producer

| producer | selector | `P2R` | guard/CBU |
|---|---:|---:|---:|
| `IADD3.Pu/PSETP/PLOP3/HSETP2` | 3 fine / **4 safe** | **2** | 7 fine / **12 safe** |
| `R2P` whole-file merge | 3 fine / **4 safe** | 3 fine / **4 safe** | 7 fine / **12 safe** |

算术 predicate 可以通过 ALU-Heavy local loopback 在 t+2 被 `P2R` 读取；
`R2P` 是 predicate-file merge/update，不走这个入口。

### 8.3 FMA-Heavy `Pu`

`IMAD.WIDE/IMAD.HI/IMUL32I.WIDE` 的 `Pu`：

| consumer | fine | safe coarse |
|---|---:|---:|
| selector | 3 | **4** |
| `P2R` | 3 | **4** |
| effective guard | 7 | **12** |
| CBU branch | 7 | **12** |

因此 simulator 不能只有一个 predicate-ready bit。至少要区分：

```text
local predicate forwarding/read ready
effective predication ready
CBU-visible predicate ready
```

## 9. 固定结果到非 scalar consumer

下列数字是 producer 与 consumer 的最小 SASS issue gap。late-read consumer
会在自身管线后段才真正采样寄存器，所以 `minG=1` 不代表 producer 在 t+1
已经完成。

| producer -> consumer | minG | 解释 |
|---|---:|---|
| `IADD3 -> LDG` address/AGU | **1** | MIO late collection 吸收 producer latency |
| `FFMA` address producers -> `LDG` | **1** | 同上 |
| `HADD2 -> MUFU` source | **2** | fixed bypass 可达 MIO late collector |
| `IADD3 -> NANOSLEEP R` | **1** | CBU late-read |
| `HADD2 -> NANOSLEEP R` | **1** | CBU late-read |
| `IADD3 -> R2UR` GPR input | **2** | R2UR 的 early GPR collector |
| `FADD/HADD2 -> R2UR` GPR input | **3** | 多一个入口/跨域阶段 |

`R2UR` 捕获 GPR 后，产生 UR result 还需要约 13--15 cycles；这是另一段
cross-lane datapath，不能和输入收集延迟混为一谈。

固定 INT/FMA result staging、XU result staging 和 MIO2RF completion staging
都能在最终 RF commit 之前向 MIO late collector 提供值。这个 collector
没有为 malformed、未等待 scoreboard 的代码自动补全所有 RAW hazard；
正确代码仍须遵守相应固定调度距离或 variable-latency scoreboard。

## 10. UDP/URF 固定路径

| producer -> consumer | 实测 minG |
|---|---:|
| `UIADD3 -> UIADD3` | **2** |
| `UIADD3 -> MOV R,UR` | **3** |
| `UIADD3 -> IADD3.RUR` | **3** |
| `UIADD3 -> FFMA.RRU` | **3** |
| `UMOV -> MOV R,UR` | **1** |
| `UMOV -> DEPBAR.LE` UR count | **2** |
| `UIADD3 -> LDG [R+UR+imm]` | **4** |

UR address-offset path比 GPR base/address late collector 更慢。`LDCU` 是
scoreboarded constant load，`R2UR` 是 cross-lane operation；两者不能套用
普通 UDP ALU 的 2/3-cycle forwarding 规则。

## 11. Bypass 带宽与 RF commit

固定结果旁路不仅有 latency，还有可见的 parity-phased collection 带宽：

| pending result tags | parity 分布 | 额外开销 |
|---|---|---:|
| 1 个 distinct tag | 任意 | 0 |
| 2 个 distinct tags | E+O | 0 |
| 2 个 distinct tags | E+E 或 O+O | 约 2 clocks |
| 3 个 distinct tags | 2+1 split | 0 |
| 3 个 distinct tags | 全同 parity | 约 2 clocks |
| 同一个 tag 重复用于多个 operand slot | 任意 | 0 |

最小一致模型是：每个 parity 每约两拍收集一个 warp-wide 32-bit pending
result tag；一次 lookup 可以广播给多个 operand slot。等效带宽约为：

```text
64 B/clock/parity
128 B/clock/subcore aggregate
```

这是行为等效模型，不等价于证明物理上存在一条特定宽度的 wire。

旁路 ready 后，结果仍可能滞留在 result queue。使用 write-scoreboard
测到的 architectural commit 通常约为 5.4--5.8 clocks，而 local forwarding
约为 2--4。最终 fixed result 与 MIO2RF/XU/tensor completion 会在每个
subcore 的 even/odd RF bank commit arbiter 汇合；每个 bank 的实测写服务
为 1W。

## 12. 与静态 latency table 的关系

静态表大体上是保守调度元数据：

- fixed GPR path 的 table 值常为 4--6，实际 local bypass 多为 2；
- UDP cross-domain table 值可到 12，实际普通 UDP ALU forwarding 为 2--4；
- predicate -> branch 的 table 值约 13，coarse 实测 12--13，反而接近精确；
- variable MIO/CBU producer 的 catch-all table 可能过于乐观，必须等待
  scoreboard。

建议 simulator 同时保留两套信息：

```text
table_latency       # 编译器/静态调度约束元数据
forward_ready[event, consumer_class]
commit_ready[event, RF parity]
```

不要用其中任何一个字段替代另外两个。

## 13. FP64/CLMAD 不属于固定转发表

`DADD/DMUL/DFMA/DSETP/CLMAD` 虽然属于 scalar math 指令，但其后端是
redirectable、SM-wide shared service。isolated unsafe probes 中，dense
布局可在 nominal gap 16--20 看到结果，而 sparse/coarse 布局会延后到
48--56，CLMAD 还会出现非单调窗口。

因此它们必须建模为：

```text
subcore redirect/admission
    -> SM-wide FP64 service
    -> asynchronous completion
    -> scoreboard release
```

详情见 [`fp64_redirect_latency.md`](fp64_redirect_latency.md)。不得把 16 或
20 写入普通 fixed-forwarding latency table。

## 14. 推荐的初始 simulator 参数

在尚未实现所有 malformed-SASS payload 前，可采用以下 correctness-first
规则：

```text
普通 local fixed GPR isolated early bypass          2（phase-specific）
普通持续 fixed dependency 的 phase-safe use         4
普通 producer -> ALU Heavy 特殊 crossing           4
ALU-Heavy producer-class -> ALU Lite/FMA Lite       按第 4 节分类，2 或 4
FMA-Heavy WIDE low -> Lite/FMA leaves               1
FMA-Heavy WIDE low -> ALU Heavy isolated final      2（持续链约 3 clocks）
FMA-Heavy WIDE low -> 下一条 IMAD.WIDE              7（真实 steady clocks）
FMA-Heavy WIDE high -> Lite/FMA/packed              4（真实 steady clocks）
FMA-Heavy WIDE high -> ALU Heavy                    5（真实 steady clocks）
IMAD.HI result -> 下一条 HI 的 Rc.high              4（真实 steady clocks）
IMAD.HI result -> 下一条 HI 的 Ra                   9（真实 steady clocks）
local predicate selector/read                       4
ALU-Heavy arithmetic predicate -> P2R               2
PLOP3 -> 普通带源 fixed consumer guard              5
PLOP3 -> FMA-Heavy / source-less MOV32I guard        12
CBU predicate                                       12（尚待同法复核）
fixed INT address -> MIO late collector issue gap   1
fixed FMA/HADD2 -> R2UR input issue gap              3（IADD3 为 2）
UDP ALU -> UDP                                       2
UDP ALU -> GPR scalar consumer                      3
UDP ALU -> MIO UR-offset                            4
fixed-result RF commit                              独立事件，约 5.4--5.8
FP64/CLMAD                                           queue/service/scoreboard event
```

对未逐 mnemonic 测量的 ALU-Lite/ALU-Heavy -> FMA-Heavy 边，应保留
`unknown` 或使用静态表的保守值，而不是凭借物理邻接关系推断 t+2。
