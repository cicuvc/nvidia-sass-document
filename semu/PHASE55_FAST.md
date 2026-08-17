# semu Phase 5.5 — 快速解释器执行引擎（Fast Interpreter）

Phase 5.5 在**同一份** `Interpreter` 状态机中引入可选的快速计算语义模式
（`ExecutionMode::kFast`）。它只替换 FP / conversion 计算叶节点；decoder、
线程状态、调度器、控制流、predicate、barrier、collective、fault、
instruction limit、step/debugger 和内存可见性全部与 precise 共享且语义不变。

**重要：fast 不是 sm_120 位精确模型。** 只有 `ExecutionMode::kPrecise`（默认）
声称可复现 sm_120 位模式，且它是 Phase 5 GPU differential 唯一验证的对象。
fast 结果用于速度优先的探索/仿真，不能作为 ISA 逆向结论、GPU differential
期望值或任何要求复现 sm_120 bit pattern 的调试依据。

## 架构（实际实现）

不做 `FpSemantics` 虚基类/虚函数；mode/fallback 决策收敛到统一入口：

- **算术/转换叶**：`plan_fp32()` / `plan_fp64()` 每条指令解析一次
  （`use_fast` / `need_exceptional` / `ignored_modifier`），lane 循环按计划
  直调 fast（`fast_fp.cpp`）或 precise（`fp.cpp`）helper。
- **计数**：统一 `note_fast_leaf(approximate_result)` 覆盖所有 FP 叶
  （`fast_fp_ops` / `any_fast_fp`）；fallback 走 `precise_fallback_ops`。每个 FP
  leaf 恰好归入 fast 或 precise-fallback 一次（无重复计数）。
- **共享-native 叶**（FRND/FMNMX/FSEL/FSETP/FSET）：两模式走同一 host 原生
  运算，位一致，fast 下仅计数（`fast_fp_ops`），不置 approximate。
- **fenv guard**：run/step 全程在 `std::optional<FenvGuard>` 内 `arm()` 一次性
  保存 caller rounding 并钉住 RN（move-only，无拷贝析构提前恢复的 bug），成功后
  fast 叶必然在 RN 下执行；析构恢复失败向 stderr 输出可观测。
- **F2F fallback 分类**：kExceptional 下 native 结果按**目标格式**分类（F16/BF16
  用低 16 位指数域，F64 用完整 double，F32 用 f32）——有限 16 位结果不会被误判成
  subnormal f32 而误触发 fallback。
- **BF16 寄存器布局**：BF16 位模式位于寄存器**低 16 位**（与 precise/sm120 契约
  一致，如 `F2F.BF16.F32(1.0f) == 0x00003f80`）；F32→BF16 舍入后置于低 16 位，
  BF16→F32 从低 16 位读取并左移 16 位。源/目的 exceptional 分类均按 BF16 布局
  （有限 BF16 走 fast，BF16 NaN/Inf/subnormal 与 F32→BF16 溢出成 Inf 在
  kExceptional 下恰好一次 fallback）。F16/BF16 NaN→F32 映射到精确的 canonical
  NaN（0x7fffffff）。

## CLI

```text
semu run [--precise|--fast] [--fast-fallback=none|exceptional|modifiers]
         [--instruction-limit=N] <cubin> <kernel> <grid.x> <block.x> ...
```

- 默认 `--precise`，保持所有既有脚本与 GPU differential 行为不变。
- `--fast` 默认 fallback `none`，JSON 顶层新增 `execution_mode`、
  `approximate` 与 `fast_stats`（`fast_fp_ops` / `precise_fallback_ops` /
  `ignored_modifier_ops`）。
- fast-only 参数（`--fast-fallback=*`）用于 precise 时返回 usage error（退出码 2），
  避免配置看似生效。
- 退出码、fault JSON 与 lane-state JSON schema 向后兼容，只新增字段；fault JSON
  同样携带 `execution_mode` / `fast_stats`。

示例：

```bash
# precise（默认）
semu run /tmp/k.cubin _Z3foo 1 32 1 1 1 1
# fast，永不 fallback（最快）
semu run --fast /tmp/k.cubin _Z3foo 1 32 1 1 1 1
# fast，NaN/Inf/subnormal 或非 RN/FTZ/FMZ 时按 lane 回退 precise
semu run --fast --fast-fallback=exceptional /tmp/k.cubin _Z3foo 1 32 1 1 1 1
```

## C++ API

```cpp
#include <semu/execution.hpp>
#include <semu/interpreter.hpp>

semu::RunOptions opts;
opts.mode = semu::ExecutionMode::kFast;                 // 或 kPrecise（默认）
opts.fast_fp_fallback = semu::FastFpFallback::kExceptional;

auto r = semu::Interpreter::run_result(kernel, env, opts);
// r.execution_mode   -> 实际执行模式
// r.fast_stats       -> fast_fp_ops / precise_fallback_ops / ignored_modifier_ops
// r.approximate      -> 是否有 fast FP 叶执行过（结果可能偏离 sm_120）
// r.fault / r.ctas   -> 与 precise 语义一致
```

- `RunOptions{ mode, fast_fp_fallback, instruction_limit, report_trace }`；
  缺省即 precise 配置，旧 overload（`run_result(kernel, env, limit)` 等）转发 precise。
- `Interpreter::step_consistent(kernel, env, RunOptions, &state)` 支持双 mode 的
  step-vs-continuous 一致性校验。
- fast 运行使用 run-scope `FE_TONEAREST`（RAII 恢复）：成功与 fault 路径都会把
  caller 的宿主 rounding mode 恢复原状。

## Fallback 策略

| `FastFpFallback` | 行为 | 适用 |
|---|---|---|
| `kNone` | 永不回退；`.RM/.RP/.RZ`、FTZ/FMZ 按 RN 执行并计入 `ignored_modifier_ops` | 最快；纯性能测量 |
| `kExceptional`（API 默认） | 输入 NaN/Inf/subnormal、**native 结果** NaN/Inf/subnormal（如溢出）或非 RN/FTZ/FMZ 时按 lane 回退 precise helper | 需要比 native 更接近 precise 的结果 |
| `kStrictModifiers` | 仅非 RN/FTZ/FMZ 编码回退；普通特殊值保持 native | 对 modifier 精确、对特殊值宽容 |

fallback 判定按 lane 完成，**不整次 launch 重跑**。kExceptional 同时检查算术输入
与 native 计算结果：即使输入全部有限，结果溢出成 NaN/Inf/subnormal 也会触发
fallback（High-2 修复）。

## 限制表（fast 模式下不可依赖的语义）

| 语义 | fast 行为 | 需要精确时 |
|---|---|---|
| NaN payload / 规范化 | native，不保证与 sm_120 一致 | 用 precise 或 fallback |
| signed zero | native，可能随宿主 FP 环境变化 | precise |
| subnormal 输入/输出 | native（kNone）；kExceptional 会 fallback | precise / fallback |
| 非 RN rounding（.RM/.RP/.RZ） | 按 RN 执行并计数 ignored | precise / fallback（kExceptional / kStrictModifiers） |
| FTZ / FMZ | kNone 不 flush 并计数 ignored | precise / fallback |
| F2F/F2I/I2F directed rounding | host RN，不保证 ULP/double-rounding | precise / fallback |
| F2I 越界 / NaN / Inf | checked，回退 precise 饱和 helper（无 UB） | 始终安全 |
| 跨平台 golden | 宿主 float/double 依赖编译器与 CPU | 不可作为 golden |
| 控制流受 FP compare 影响 | fast 的近似结果可能改变 FSETP→分支路径 | 数值稳定性/收敛判断必须用 precise |

## 指令路由矩阵

| 类别 | Fast 处理 | 契约 |
|---|---|---|
| 整数/bit/predicate（MOV/IADD3/IMAD/ISETP/LOP3/SHF/…）| 复用现有 handler | 位精确 |
| 控制流/同步（BRA/BSSY/BSYNC/BAR/S2R/S2UR）| 原状态机 | 与 precise 一致 |
| FADD/FMUL/FFMA、DADD/DMUL/DFMA | `fast_fp` host 运算 | RN 近似；modifier/特殊值按 policy |
| F2F/I2F | host cast + 简化 pack | 不保证 directed rounding/payload/double-rounding |
| F2I | checked host conversion | NaN/Inf/越界 → precise 饱和 helper |
| FSETP/FSET/FMNMX/FSEL | native compare/select | predicate 结果尽量精确；保留 unordered truth table |
| VOTE/SHFL/ELECT/REDUX | 复用 collective | lane membership/ballot 完全一致 |
| MUFU/FCHK、未实现 variant | 与 precise 相同的 `kUnsupportedInstruction` | 不得返回伪结果 |

## 性能（Release，32-lane warp，median，本机）

| Kernel | speedup | precise ns/instr | fast ns/instr |
|---|---|---|---|
| FP32 FFMA 链 | **2.05x** | 1774 | 864 |
| FP64 DFMA+F2F 混合 | **1.32x** | 1261 | 974 |
| 多 warp divergence + FP | **1.83x** | 999 | 545 |
| integer-only | **1.00x** | 1315 | 1314 |
| exceptional-heavy | **1.55x** | 1242 | 802 |

- integer-only 无明显回退（≤5% 预算），证明 mode dispatch 已收敛（一次 resolve + 按 lane 直接调用）。
- 加速上限受“叶节点占单指令成本比例”约束：fast 只放宽 FP 叶，共享的 decode/operand
  binding 对两模式同价。M5 通过 **Fp32Plan/Fp64Plan 预解析**（mode/fallback/op 一次性决策）
  与 **operand 预绑定**（`bind_reg_index` 消除 per-lane 字符串比较）把 FFMA 从 1.38x 提到 2.05x。
  执行 policy 布尔量（kExceptional 与否）在指令级提升一次，避免 per-lane 重复比较。
- benchmark runner：`semu_bench_fast_interp <cubin> <kernel> <grid.x> <block.x> [runs]`，
  预热 3 + 正式 N 次 AB/BA 交替，报告 median/p10/p90、ns/dynamic-instruction、fallback ratio。
  每次 timed run 校验 **无 fault + dynamic instruction count + 控制流 fingerprint**（lane
  PC/exited/predicate 摘要，FNV-1a 哈希），防“少执行/改路径”假加速。

## 测试

- `interp_compute_ffma_fast` / `interp_compute_ffma_fast_fallback`：fast 叶 bit-equal + fallback 计数。
- `interp_fast_fenv_restore`：caller rounding mode 在成功与 fault 后恢复。
- `interp_fast_rounding_modifier_classification`：kNone 记 ignored、kExceptional 回退。
- `interp_dual_mode_state_equality`：控制流 + FFMA + conversion kernel（F2F.F16.F32 / I2F.F64 /
  F2F.F64.F32 / F2F.F32.F64）两模式全状态 bit-equal。
- `interp_step_fast_consistency`：fast 模式 step-vs-continuous 一致（用含 FFMA 的 kernel）。
- `interp_fast_per_lane_fallback_mix`：同一 warp 31 个有限 lane 走 fast、1 个 NaN lane 走 precise
  fallback，验证计数（63 fast 叶 = 32 FSEL + 31 FFMA；1 fallback）。
- `interp_fast_bf16_layout_dual_mode`：BF16 双模式位一致（F32 1.0→BF16 0x00003f80、BF16
  0x0000bf80→F32 0xbf800000、最大 F32→BF16 Inf 在 kExceptional 恰好一次 fallback、BF16
  NaN/subnormal 分类与计数）。
- `test_fp.cpp`：`fast_fp_finite_rn_matches_precise`、`fast_fp_sat_matches_precise`、
  `fast_f2i_checked_range`、`fast_f2f_matches_precise`、`fast_i2f_matches_precise`（含 S32 负值
  符号扩展、S16/S8/U16/U8 边界）。
- `tools/diff_phase5.py`（484 项）与 `tools/fuzz_phase5.py`（110 项）不传 mode，证明默认仍 precise。
