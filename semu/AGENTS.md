# semu — SM120 SASS 行为模拟器（Agent 工作指引）

本文件是 `semu/` 子项目的 Agent 工作手册。仓库根目录另有 AGENTS.md（sm90 逆向工程总纲），
两者配合使用：根 AGENTS.md 讲仓库历史与 assembler/notes 工具链，本文件讲 semu 的
构建/测试/标准与关键上下文。

## 项目介绍

`semu/` 是 **sm120（Blackwell）SASS 行为模拟器** 的 C++20 实现（SIM_PLAN.md 定义）。核心目标：
在 CPU 上对 sm120 SASS 指令做**位精确**行为模拟（含 FP 舍入/NaN 语义、内存模型、race
detector、profiler、tensor-core 数学），供 GPU 逆向工程与工具链（debugger/JIT 未来）使用。

**Phase 状态（2026-08-18 全部达成，Phase 10 已冻结）**：
- Phase 0✅ 1✅（decoder 1414/1414 唯一解码） 3.5✅ 4✅ 5✅（compute 位精确，GPU diff 484/484）
  5.5✅（fast interpreter，FFMA ~2.1x） 6✅（MemoryService/worker pool/unified L1TEX/race detector）
  7✅（debugger + CLI REPL） 8✅（profiler：shared/global/L1TEX-L2 分层 + JSON schema v1.0）
  9✅（LDGSTS async/mbarrier/TMA/tensor map/cluster dsmem + tensor 数学）
  10✅（**接口冻结**：IBackend/decoded IR/runtime services/event stream/fault ABI，版本标记=1）

**冻结范围与 waiver（必须如实标注，禁止反向声称）**：
- TMA（utmaldg/utmastg/utmaredg）：**decode-only，不冻结语义**（capability = decode-only）
- OMMA：functional 但 **gpu_waiver**（GPU 三方一致缺失，用户指示跳过）
- QMMA e3m2/e2m3：**user-skip**（用户指示跳过，仅 CPU bit-exact 证据，禁止写 "GPU validated"）
- 以上标注已写入 capability manifest note 字段（`semu capability --full` 可见）：
  `user_skip:e3m2,e2m3`、`gpu_waiver:OMMA`、MXQMMA/UTMA* = decode-only

## 目录结构

```
include/semu/    公共 API（冻结面：api.hpp 版本标记 + 10 个冻结头文件）
src/             核心库 semu_core（CPU-only，无 CUDA 依赖）
  decoder/       指令解码（gen_isa.py 生成的表驱动）
  interpreter/   解释器
  cubin/         ELF/cubin 加载
  profiler/      Phase 8 profiler
cli/             semu CLI（--version/capability/disasm/load/debug/run --profile）
tests/           L0-L4 测试（CTest 注册）
tools/           gen_*.py 生成器、run_semu_cpu_gate.sh 门禁脚本、差分 harness
generated/       capability_data/isa_data（提交到仓库，普通构建无需 Python）
benchmarks/      record.json（吞吐记录）
docs/            USER_GUIDE.md（capability matrix）、API_EXAMPLES.md
```

## 构建

环境（新机器 local-debian）：CUDA 13.1 在 `/usr/local/cuda/bin`（nvcc/ncu），
Python 用 **miniconda**（`/home/cicuvc/miniconda3/bin/python3`，有 numpy；
系统 `/usr/bin/python3` 无 numpy——跑门禁必须把 conda bin 放 PATH 前面）。

```bash
export PATH="/home/cicuvc/miniconda3/bin:/usr/local/cuda/bin:$PATH"
cmake -S semu -B semu/build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build semu/build
```

构建树约定（保持一致性）：
- `semu/build`：Debug（门禁主树）
- `semu/build-asan`：`-DSEMU_ENABLE_SANITIZERS=ON`（ASan+UBSan）
- `semu/build-tsan`：TSan 树
- `semu/build-rel`：Release（benchmark 用，`-DSEMU_WERROR=OFF`——GCC-12 -O3 有
  vector::resize memmove 误报；Debug/ASan/TSan 树保持 -Werror）

CMake 选项：`SEMU_BUILD_CLI`、`SEMU_BUILD_TESTS`、`SEMU_ENABLE_SANITIZERS`、
`SEMU_ENABLE_GPU_DIFFERENTIAL`。

## 测试标准（门禁）

**主门禁**：`tools/run_semu_cpu_gate.sh <build_dir>` —— **36 项**，三树（Debug/ASan/TSan）
各 **36/36** 必须全绿（含 `cond_compile_equiv`：校验 kConds 编译期固化生成的 C++ thunk
与 sass_cond 参考求值器在随机槽图上语义等价）。**必须** `export PATH="/home/cicuvc/miniconda3/bin:..."` 再跑
（脚本内 `PY=$(command -v python3)` 覆盖环境变量，PATH 决定 python）。

门禁组成：C++ 单测（decoder/fp/interp/race/profiler/debugger/tensor/tensor_map/mbarrier/
mock_backend 等）+ cli_smoke + manifest_regen/isa_regen（byte-identical）+ decoder 系列
（roundtrip/ambig/cuobjdump/tamper/negative）+ cubin_load + fuzz_phase5 + l1tex_oracle +
profiler_report + tensor_differential + api_compile（30 头文件独立编译）。

**GPU differential（5090 在，CUDA 13.1）**：
- `python3 tools/diff_phase5.py`：**484/484**（480 differential + 2 fault checks）
- `python3 tools/fuzz_phase5.py -n 120 --seed 20260813`（GPU 模式）：120/120
- `python3 tools/fuzz_phase5.py --mutation`：108/108
- `python3 tools/tensor_gpu_differential.py`：54/54 checked PASS（HMMA k8/k16 f16/bf16 +
  QMMA k32 e4m3/e5m2/e3m4 + k16 e4m3/e5m2：GPU==semu==model 逐 accumulator bit；
  e3m2/e2m3/omma 24 项 user-skip；TMA 3 项 decode-only 不验证）

**其他基线数字**：l1tex_oracle C++==Python **1941/1941**（arch/l1tex 数据）、
LDGSTS corpus **520/520**（纯计数 == 硬件测量）、tensor differential（CPU 双模型）72/72。

**改代码后的铁律**：三树重建 + 门禁全绿 + 相关差分；GPU 相关的改动必须跑 GPU 项。

## 关键上下文（实现/修改必须遵守）

1. **语义实现不凭记忆**：实现/修改指令语义必须参考
   - 仓库 `notes/`（尤其 `notes/sm90/arch/tma_mbarrier.md`、`tensorcore_microarch_speculation.md`、`hmma_pipeline.md`）
   - `tests/asm_construct/` 的 GPU 实验
   - PTX ISA 语义（SASS 行为的上层契约）
   - 禁止只翻 sm120_instructions.txt/json 的编码表就写语义。
2. **mbarrier 64-bit 位布局（权威，Phase 9 落地）**：
   `bit0=保留`；`bits[1:20]=Expected`（int20 补码）；`bits[21:41]=tx`（int21）；
   `bit42=Lock`；`bits[43:62]=Arrive`（int20 补码）；`bit63=Phase`。
   arrive 到 0 → phase 翻转 + Arrive 重置 Expected；>0 → Lock 锁死 fault；
   expect_tx 设 tx=-bytes，TMA 完成 tx+=量，**arrive+tx 双零才翻转**；
   wait(phase) parity 满足即过；SYNCS 在 barrier cache 内操作不写回共享内存。
3. **HMMA/QMMA 结果不 scoreboard**（COUPLED_EMULATABLE）：读 Rd 前需 **≥16 NOP**
   （少了会 fault 0x715）。QMMA srcFmt enum（实测）：`E4M3=0, E3M4=1, E2M3=2,
   E5M2=4, E3M2=5, E2M1=6`（k16 只允许 raw 0/1）。
4. **LDGSTS 模型用 unified_model.py**（`arch/l1tex/unified_model.py`，单规则
   SharedWf=read_waves+write_waves−largest_joint_fiber，结构化 pattern 精度优于
   model.py 特判版）。Phase 6 已移植 UnifiedV1Estimator（C++，1941/1941 一致）。
5. **arch 采样数据有效性**：只有 `data4/8/16_ldgsts_warmldg.jsonl` 与 `data_gf2_*` 可信
   （warm artifact 修复后采的）；旧 jsonl（08-04/05）与 hit 系列**不可用**。
6. **race 语义**：atomic 豁免严格限定 atomic↔atomic 同 range writer pair；
   atomic 不自动让无同步 non-atomic access 合法；失败 atomic 不记录 race/L2。
7. **路径规则**：本仓库路径是 `/home/cicuvc/cs/projects/nvidia-sass-document`——
   拼错（`/home/cicuvc/semu`、`s/projects` 等）会触发权限拒绝中断。一律用相对项目根路径。
8. **不修改 sim.py**（仓库不存在该文件，从未创建）。
9. **冻结接口不改**：`api.hpp` 5 个版本标记 + 10 冻结头文件 + `IRuntimeServices`
   纯虚面；扩展走派生接口（如 `IRuntimeServicesV2` 前置声明已预留）。
10. **GCC-12 已知问题**：Release -O3 有 vector::resize memmove 误报（build-rel 用
    WERROR=OFF）；不要"修"这些 false positive。

## 工作流约定

- 用户习惯：opencode 实现 → 审查（codex gpt-5.6-sol 或 deepseek-v4-pro）→ 修复循环 → Closed。
- 实现完成后**先报告，等用户指示**再启动审查（用户可能指定审查模型）。
- 每个 Phase/修复更新 SIM_PLAN.md（仓库根）记录：根因、改动、门禁数字。
- 大阶段恢复上下文：读 SIM_PLAN.md 对应章节 + 仓库状态，不要凭记忆。
