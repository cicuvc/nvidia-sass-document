# semu — SM120 SASS 行为模拟器

`semu/` 是 SIM_PLAN.md（仓库根目录）定义的 sm120 SASS CPU 行为模拟器的 C++20 实现。

- **公共 API**：`include/semu/`（稳定接口；Phase 0 冻结 Status/Error/Fault）。
- **核心库**：`src/semu_core`，无 CUDA 依赖，CPU-only。
- **Decoder**：`src/decoder/`（Phase 1）——由 `tools/gen_isa.py` 生成的编译期
  ISA 表驱动，把 128-bit instruction word 唯一解码为规范化反汇编文本。
- **CLI**：`cli/semu`（`--version` / `capability` / `disasm` / `load` / `--help`）。
- **测试**：`tests/`（L0 unit + decoder + CLI smoke + Phase 1 验证门禁）。
- **生成器**：`tools/gen_capability.py`（capability manifest）、
  `tools/gen_isa.py`（ISA 表）、`tools/gen_corpus.py`（encoding corpus）。
- **生成的构建输入**：`generated/`（提交到仓库；普通构建不需要 Python）。

## 构建

```bash
cmake -S semu -B semu/build -G Ninja -DCMAKE_BUILD_TYPE=Debug
cmake --build semu/build
ctest --test-dir semu/build --output-on-failure
```

CPU-only：不查找/链接任何 CUDA 组件。

### 可选选项

| 选项 | 默认 | 说明 |
|---|---|---|
| `SEMU_BUILD_CLI` | ON | 构建 `semu` 命令行 |
| `SEMU_BUILD_TESTS` | ON | 构建并注册 CTest |
| `SEMU_ENABLE_SANITIZERS` | OFF | ASan + UBSan（`-fsanitize=address,undefined`） |
| `SEMU_ENABLE_GPU_DIFFERENTIAL` | OFF | 预留 GPU differential hook（Phase 3+ 才生效） |

### 重新生成 capability / ISA 数据（开发期）

```bash
python3 semu/tools/gen_capability.py      # generated/capability_data.{hpp,cpp}
python3 semu/tools/gen_isa.py             # generated/isa_data.{hpp,cpp}
python3 semu/tools/gen_corpus.py          # /tmp/semu_corpus.json（encoding corpus）
```

生成是确定性的：`ctest -R 'isa_regen|manifest_regen'` 验证重复生成 byte-identical，
且与提交的构建输入一致。

## Phase 1 — ISA 数据生成与通用 decoder

- **ISA 表**：`tools/gen_isa.py` 从 `sm120.json` 生成紧凑 C++ 表
  （1414 variants / 451 enums / 89 tables / 322 shared-opcode groups）。
- **Decoder**：按 `{bit[91], bits[11:0]}` 的 13-bit opcode 建 candidate index；
  用 enum-membership（star_slot discriminator）、table membership、固定字段、
  reserved bits 和 legality condition 区分共享 opcode 的 variants；无法唯一判定时
  返回所有候选及各候选失败原因，不静默选择。
- **歧义消解**：F2FP/F2I/BAR/CCTL/PLOP3/PSETP/HMMA/QMMA 等高重叠 opcode 通过
  `*dstfmt`/`*srcfmt`/`*merge` 等 discriminator 字段的 enum 校验唯一解码。
- **CLI `disasm`**：单字解码 `semu disasm <lo> <hi>`，以及批量
  `lo hi` 每行一个的 stdin 流式解码。
- **CLI `scan-conds`**：三态 condition 解析覆盖率门禁（20003 conditions，
  0 parser gaps）。
- **CLI `cond-eval <cls> <lo> <hi>`**：对指定 variant class 的每个 condition
  输出三态 verdict（1/0/2），供逐条 Python/C++ 对比（GAP-09）。
- **CLI `decode-json <lo> <hi>`**：结构化 decode（mnemonic/modifiers/
  operands 字段），供 cuobjdump 结构化对比（GAP-10）。
- **三态 legality evaluator**（GAP-04）：无法完整解析的 condition 不会被当作
  satisfied；支持 `TABLES_x(...)` 裸表名取值。

### Phase 1 验证门禁（CTest，17 项全绿）

| 测试 | 验证内容 |
|---|---|
| `decoder` | L0 C++ 单测：已知词唯一解码、未知 opcode 明确非法、opcode 索引。 |
| `decoder_roundtrip` | 1414 个 corpus word encode → decode → encode bit-exact round-trip；gap 必须命中固定 allowlist（`tests/data/roundtrip_gaps.json`），新增 gap 即失败。 |
| `decoder_ambig` | 高重叠 opcode 唯一解码；reserved-bit 翻转不误匹配其他 variant。 |
| `decoder_cuobjdump` | 450 个真实 sm120 cuobjdump 向量**结构化比较**（guard/mnemonic/双向 modifier 相等/按位置 operand/寄存器双向相等/branch target 按 PC 位移，GAP-10）。 |
| `decoder_cuobjdump_tamper` | 4 类篡改（寄存器/modifier/branch target/额外 operand）必须使 cuobjdump 门禁失败（GAP-10 mutation 门禁）。 |
| `cubin_loader` | 合成 cubin 单元测试：happy path（KPARAM/REGCOUNT/shared/exit/barrier）、坏 magic/截断/错 arch/坏 symtab/malformed EIATTR/未知 EIATTR warning（Phase 2）。 |
| `cubin_load` | 真实 cubin 集成门禁：assembler 单 kernel + nvcc 多 kernel（3 kernel，text size/regcount 与 readelf/cuobjdump 对照）、错误路径注入（Phase 2）。 |
| `memory` | 虚拟内存 + launch ABI 单元测试：确定性地址、生命周期/越界/对齐、allocation id、DevicePtr 算术、ConstantBank（param_base 0x380 + 预置 slot）、per-item/packed launch byte-identical、bigparam 128B 参数（Phase 3）。 |
| `cluster` | Cluster DSMEM 翻译测试：rank<<24 逻辑地址、ClusterTopology（合法性/cap/尾部拒绝）、跨 CTA roundtrip、负向矩阵、local-vs-DSMEM、rank0 语义、event 身份、atomic 宽度（Phase 3.5）。 |
| `interp` | Interpreter 执行核心：per-lane ITS、BRA/BRX/JMP/JMX/EXIT/BSSY/BSYNC、S2R/S2UR、最小 ALU、per-lane guard、round-robin 调度、checked 分支算术、统一控制目标校验、指令上限/barrier deadlock、decode-only fault 定位（Phase 4）。 |
| `decoder_negative` | 398 个负向量（illegal-encodings 表行 / enum hole / 寄存器对齐破坏）必须被拒。 |
| `cond_differential` | 21358 次逐 condition Python/C++ 三态对比（同 slot map），0 mismatch；unknown-token/resolved 样例经 `eval-cond` 双侧验证（GAP-09）。 |
| `cuobj_regen` | fixture 可从仓库内容重建（committed cubins + regen 源，GAP-11）。 |
| `isa_regen` | `gen_isa.py`/`gen_corpus.py` 重复生成 byte-identical，且与提交构建输入一致。 |

### 真实向量 fixture 再生成（GAP-11，需 CUDA 工具链）

```bash
python3 semu/tools/rebuild_cuobj_fixture.py   # 重建 tests/data/cuobj_vectors_sm120.json
```

fixture 由 committed cubin（`tests/*.cubin`，gitignore 例外）与 regen 源
（`semu/tests/data/regen/*.cu`）重建；`cuobj_regen` CTest 验证重建 word-set
与提交 fixture 一致。

  ## 阶段状态

见 `BASELINE.md`（Phase 0/1 基线记录）、`GAP.md`（验收差距修复记录）与
SIM_PLAN.md 第 8 节进度表。Phase 5.5 快速解释器（fast FP semantics）的用户
指南、CLI/API 与限制表见 `PHASE55_FAST.md`。

## Phase 10 — 稳定化与 JIT 接口冻结

- **用户文档 / API 示例 / capability matrix / 限制**：`docs/USER_GUIDE.md`、
  `docs/API_EXAMPLES.md`。
- **冻结契约**：`include/semu/api.hpp`（backend / decoded-IR / runtime
  services / event stream / fault ABI 的版本标记）；`context.hpp` 预留了
  版本化 async/TMA 扩展点。
- **Mock backend**：`include/semu/mock_backend.hpp` + `src/mock_backend.cpp`
  —— 验证未来 JIT 可接收 decoded IR、访问 runtime services、对未 lowering
  指令回退 interpreter、对 decode-only（TMA / 非 dense tensor）按 fault ABI
  报 fault。
- **热点统计**：`RunOptions::collect_hotspots` → `Result::pc_hotspots`
  （按静态字节 PC 的动态计数；并行 worker 合并）。
- **基准**：`tests/bench_interp_throughput.cpp`（单/多 worker 吞吐、扩展比、
  热点 profile），结果记录到 `benchmarks/record.json`，不设硬性 SLA。
- **公共 API compile tests**：`tests/compile_api_test.cpp` + 每个公共头文件
  的独立编译检查（`ctest -R api_compile` + header-object checks）。
- **验证门禁**：`tools/run_semu_cpu_gate.sh`（35 项 CPU 门禁，含 mock
  backend / api_compile）。
