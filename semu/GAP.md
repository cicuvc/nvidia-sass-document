# Phase 0/1 验收差距记录

**验收日期：** 2026-08-11  
**验收范围：** `SIM_PLAN.md` Phase 0（工程骨架与基线冻结）和 Phase 1（ISA 数据生成与通用 decoder）  
**当前结论（2026-08-11 四次复验；Phase 2 于 2026-08-12 完成并通过验收）：** Phase 0
已通过；Phase 1 的全部 GAP-01～GAP-11 均已关闭，CTest 12/12（普通）与
10/10（ASan+UBSan）通过（Phase 2 新增 `cubin_loader`/`cubin_load` 后为 14/14）。
Phase 2 的 P2-GAP-01～P2-GAP-08 于 2026-08-12 全部关闭（详见
`semu/GAP_PHASE2.md`），Phase 2 状态为 **Closed / Pass**。
复查指出的三处不一致（GAP-09 unknown-token 缺 C++ 侧、GAP-10 modifier
单向比较与 branch target 未比较、GAP-10 篡改测试未入 CTest）均已修复并
纳入门禁。Phase 1 状态为 **Closed / Pass**。allowlist 的 260 项属于显式
技术债，集合保持冻结：新增项失败、失效项提示清理。

初验仅执行检查、构建和测试，没有修改 semu 实现。后续修复与二次、三次复验结果
记录在第 7～10 节。

## 1. 阻断问题

### GAP-01 — 64-bit 字段提取存在未定义行为

**严重级别：** Blocker  
**位置：** `semu/src/decoder/decoder.cpp:65`

`extract_field()` 在字段 range 宽度为 64 时执行：

```cpp
val = (val << width) | part;
```

当 `width == 64` 时会产生 `uint64_t << 64`，属于 C++ 未定义行为。UBSan 在全量 decoder corpus 的第 829 个 word 附近稳定报告：

```text
semu/src/decoder/decoder.cpp:65:20:
runtime error: shift exponent 64 is too large for 64-bit type
```

结果是 sanitizer 构建下的 `decoder_roundtrip` 只输出 828/1414 行并失败。

**影响：**

- Phase 0 的 ASan+UBSan 退出条件未满足。
- Phase 1 的 1414 variants 全量 decoder 门禁未在 sanitizer 下通过。
- Release/普通 Debug 构建中的行为依赖编译器，不能作为正确性依据。

**修复要求：**

- 对 `width == 64` 单独赋值，禁止执行 64-bit shift。
- 同时审计 `semu/src/word.cpp` 中结构相同的 bit-range 拼接逻辑。
- 增加单 range 64-bit、跨 lo/hi range 和多个 range 累积的 unit tests。

**复验要求：**

- ASan+UBSan 下 `decoder_roundtrip` 完整处理 1414 行。
- UBSan 输出中不存在 shift、signed overflow 或越界报告。

### GAP-02 — Renderer 使用指针地址比较字符串

**严重级别：** Blocker  
**位置：** `semu/src/decoder/render.cpp:528-530`

`isa::Slot::name` 是 `const char*`，代码使用：

```cpp
sj.name == "Pu"
sj.name == "Pv"
sj.name == "Pp"
sj.name == "Pq"
sj.name == "Pnz"
```

这比较的是指针地址而不是字符串内容。当前 GCC 可能因为字符串常量合并而偶然工作，但结果不受语言保证。编译器已经产生 `-Waddress` 警告。

**影响：**

- `is_memaddr()` 可能无法跳过 predicate slot。
- 可能错误判断 composite memory operand，进而影响反汇编文本和 round-trip。
- 不同编译器、优化级别或链接方式可能得到不同结果。

**修复要求：**

- 统一使用 `std::string_view(sj.name) == "Pu"`、`strcmp` 或项目内字符串 helper。
- 清理同一文件中的 unused variable/function 警告。
- 增加 predicate slot 位于 register 和 offset 之间的 memory operand tests。

**复验要求：**

- GCC/Clang 使用 `-Wall -Wextra -Wpedantic -Werror` 构建成功。
- Debug、Release、ASan 构建的反汇编输出 byte-identical。

### GAP-03 — Round-trip 门禁弱化了原计划的 bit-exact 要求

**严重级别：** Blocker  
**位置：** `semu/tests/decoder_roundtrip_test.py`

普通构建下实测结果：

```text
1414/1414 corpus words decode uniquely
0 ambiguous
0 illegal
1112 bit-exact re-encode
42 branch skipped
260 assembler-matcher gaps
```

测试对 re-encode 失败执行：

```python
known_gap += 1
n_ok += 1
```

因此任何数量的 matcher/re-render gap 都不会使测试失败。当前结果能证明 corpus word 唯一解码，但不能证明 1414 variants 全量 encode -> decode -> encode bit-exact round-trip。

**影响：**

- `decoder_roundtrip` 测试名称和 Phase 1 完成记录容易夸大覆盖程度。
- 新增 renderer regression 可能被自动归入 `known_gap`，门禁仍然通过。
- 260 个 gap 没有稳定 allowlist，无法检测 gap 集合变化。

**修复要求：**

- 将 unique-decode 和 bit-exact-round-trip 拆成两个统计和门禁。
- 生成固定、可审阅的 gap allowlist，至少记录 variant class 和失败类型。
- 只有 allowlist 内的预期 gap 可以跳过；新增 gap 必须失败。
- branch variants 应使用 kernel/label-aware round-trip，或维护独立明确的 branch skip list。
- `BASELINE.md` 和 `SIM_PLAN.md` 应准确区分 1414 unique 与 1112 bit-exact。

**复验要求：**

- gap 集合与已提交 allowlist 完全一致。
- 任意新增 re-encode failure 都导致 CTest 失败。
- 修复 renderer/matcher 后逐步缩小 allowlist，并记录原因。

## 2. 重要验证缺口

### GAP-04 — Legality predicate 解析失败时默认接受

**严重级别：** High  
**位置：** `semu/src/decoder/expr.cpp:240-246`

`ExprEvaluator::eval_bool()` 捕获解析异常后返回 `true`：

```cpp
catch (...) {
    return true;
}
```

此外，求值结束后没有检查 token 是否全部消费。未知字符会在 tokenizer 中被跳过。这种策略避免误拒绝合法 encoding，但可能静默接受违反未正确解析 condition 的非法 encoding。

**修复要求：**

- evaluator 返回三态：true、false、unresolved，而不是把 unresolved 当 true。
- variant legality 判定遇到 unresolved condition 时不得宣称 authoritative unique decode；应拒绝、报告不确定，或使用专门的已验证 allowlist。
- generator 应统计所有 condition 的可解析率，并列出未完整解析表达式。
- 增加 Python `ConditionEvaluator` 与 C++ evaluator 的 differential corpus。

**复验要求：**

- 所有用于 variant 区分的 condition 都能完整消费 token。
- 合法/非法 tuple 与 Python evaluator 一致。
- 未解析 condition 数量为 0，或全部有逐项审阅的 allowlist。

### GAP-05 — 缺少独立真实 sm120 cuobjdump 向量门禁

**严重级别：** High

当前 1414-word corpus 由 `sm120.json` 和本仓 assembler encoder 生成；C++ unit test 中的四个 known words 也来自该 corpus。这可以验证 encoder/decoder 的内部一致性，但不是独立地面真值。

`BASELINE.md` 提到 sm90 vectors，但当前 `semu/tests` 中没有对应的可执行测试或 vector fixture。sm90 vector 也不能替代 sm120 硬件向量。

**修复要求：**

- 收集本仓 `tests/asm_construct`、nvcc sm120 cubin 和 cuobjdump 输出中的真实 128-bit words。
- fixture 至少覆盖高重叠 opcode、immediate、constant/uniform operand、memory、branch、predicate 和 schedule fields。
- 保存期望 mnemonic、variant、operand/modifier 和 lo/hi word。
- differential test 不通过 generator 重新构造期望结果。

**复验要求：**

- 独立 sm120 vector fixture 通过 C++ API 和 CLI 两条路径。
- vector 来源、CUDA/driver、kernel 和 cuobjdump 文本可追溯。

### GAP-06 — Reserved-bit 测试没有覆盖非法 encoding 条件

**严重级别：** Medium

`decoder_ambig_test.py` 只翻转同 opcode 所有 candidate encoding field 都未覆盖的 bit。实测 2488 次翻转全部保持原 variant：

```text
0 illegal, 2488 same, 0 ambiguous, 0 other
```

这证明 decoder 没有读取这些完全未覆盖 bit，但没有验证 illegal-encoding tables、enum INVALID 值、register-range condition 或 discriminator 非成员值会被拒绝。

**修复要求：**

- 从 `*_illegal_encodings` tables 自动生成 negative vectors。
- 对 enum hole/INVALID、固定字段破坏、register group 越界和 condition false tuple 建立测试。
- negative vector 必须验证预期 rejection reason，而不只是 outcome=ILLEGAL。

## 3. 工程卫生差距

### GAP-07 — 未忽略的构建/编辑器产物

**严重级别：** Medium

当前存在：

- `semu/core`：约 1.2 MB 的 ELF core dump。
- `semu/.cache/clangd/`：clangd index cache。

二者目前未被 `.gitignore` 排除，且整个 `semu/` 尚未跟踪，容易在首次 `git add semu` 时误提交。

**修复要求：**

- 删除或移出 core dump 和 clangd cache。
- `.gitignore` 加入 `semu/core`、`semu/core.*` 和 `semu/.cache/`。
- 增加提交前检查，拒绝 core dump、build tree、cache 和 `__pycache__`。

### GAP-08 — 新工程尚未启用 warning-as-error

**严重级别：** Medium

当前普通和 sanitizer 构建均出现：

- `-Waddress`：字符串字面量指针比较。
- unused variable `t2`。
- unused function `is_imm_type`。

至少 `semu_core` 和 semu tests 应在 Phase 0 使用 `-Werror`，避免可疑警告进入后续阶段。

## 4. 已通过项目

以下项目本次实测通过：

- 干净 Debug configure/build 成功。
- 非 sanitizer CTest：7/7 通过。
- `parse_sm120.py` validation OK：
  - 1414 variants
  - 259 mnemonics
  - 451 enums
  - 89 tables
  - 2142 FUNIT fields
  - 300 pipe entries
- parser 重新生成结果与当前 `sm120.json` byte-identical。
- capability manifest regeneration deterministic。
- ISA/corpus generator regeneration deterministic。
- 普通构建下 1414/1414 corpus words 唯一解码，0 ambiguous、0 illegal。
- 高重叠 opcode 集合 361/361 unique。
- 2488 次完全未覆盖 bit 翻转没有跨 variant 误匹配。
- `assembler/sass_encoder.py` 和 `tools/parse_sm120.py` 通过 Python syntax check。
- 全部 1414 variants 可以由当前 corpus generator 编码。

这些结果足以证明 Phase 0/1 的基本结构和主要 decoder 路径已建立，但不足以覆盖上述 blocker。

## 5. Sanitizer 环境说明

默认 LeakSanitizer 在当前执行环境下因 ptrace 限制报错：

```text
LeakSanitizer has encountered a fatal error.
LeakSanitizer does not work under ptrace.
```

这属于测试环境限制。使用以下设置禁用 leak detection 后，ASan/UBSan 可以继续执行并暴露 GAP-01：

```bash
ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1 \
  ctest --test-dir /tmp/semu_accept_asan --output-on-failure
```

禁用 LeakSanitizer 不能解释或豁免 `shift exponent 64`；后者是实现中的真实 UB。

## 6. 复验门禁

Phase 0/1 重新验收前必须满足：

1. 修复 GAP-01 和 GAP-02，普通构建无编译警告。
2. ASan+UBSan 下 7/7 CTest 通过；受限环境可禁用 LSan，但不能禁用 ASan/UBSan。
3. 1414 corpus words 在 sanitizer 下全部处理完成。
4. 将 260 个 round-trip gap 固定为 allowlist，新增 gap 会失败。
5. condition evaluator 有完整解析统计和 Python differential test。
6. 增加真实 sm120 cuobjdump vector fixture。
7. 增加 illegal table/enum/condition negative tests。
8. 清理并忽略 core dump、clangd cache 和其他生成垃圾。
9. 更新 `BASELINE.md` 与 `SIM_PLAN.md`，使完成记录与实测数字一致。

复验结果应记录：构建命令、编译器、sanitizer 配置、CTest 明细、unique/round-trip/negative vector 数量，以及尚存 allowlist 的逐项原因。

## 7. 修复记录（2026-08-11）

| GAP | 修复 | 验证 |
|---|---|---|
| GAP-01 | `extract_field()`/`extract_bits()`：`width>=64` 时改为赋值而非 `<<`；跨界分支 `lo_w==64` 不再移位。新增 64-bit/跨界/lo=0 unit tests。 | UBSan halt-on-error 下 decoder_roundtrip 全量 1414 words 通过，无 shift/signed-overflow 报告。 |
| GAP-02 | `is_memaddr()` 用 `std::string` 比较 slot 名；删除 unused `t2`/`is_imm_type`。 | `-Werror` 构建零警告；Debug/Release/sanitizer 反汇编输出一致。 |
| GAP-03 | round-trip 门禁拆分为 unique-decode 统计 + bit-exact round-trip；固定 allowlist（`tests/data/roundtrip_gaps.json`，260 项，含 variant class + kind）；新增 gap 或 kind 变化即失败；消失的 allowlist 项报 NOTE。 | 实测 1414 unique / 1112 bit-exact / 42 branch / 260 allowlisted；伪造新增 gap 时门禁正确失败。 |
| GAP-04 | `ExprEvaluator::eval_bool_tristate()` 三态（true/false/unresolved）；tokenizer 记录未知字符；求值后检查 token 全消费；`TABLES_x(...)` 裸表名取值支持（C++ + Python）；`semu scan-conds` 输出 20003 conditions / 0 parser gaps。 | 20003/20003 conditions 可由 C++ 完整解析；合法 corpus 在 Python evaluator 中全部为 true。逐 condition 的 Python/C++ 真值对比尚未实现，转 GAP-09。 |
| GAP-05 | `tools/extract_cuobj_vectors.py` 从真实 sm120 cubin 用 cuobjdump `-sass` 提取 450 个唯一 128-bit words；fixture 记录 cubin/kernel/PC/text/lo/hi 与来源；`decoder_cuobjdump` 门禁比较基础 mnemonic 和寄存器子集。 | 450/450 唯一解码且基础 mnemonic/被引用寄存器匹配。完整 variant/operand/modifier 对比与 fixture 自包含再生成分别转 GAP-10、GAP-11。 |
| GAP-06 | `decoder_negative` 门禁：illegal-encodings 表行 splice 进 mem 字段、star_slot discriminator enum hole（多成员 enum 且接受同类才算失败）、寄存器对齐破坏。 | 398 个 negative vectors 全部被拒。 |
| GAP-07 | 删除 `semu/core` core dump 与 `semu/.cache/`；`.gitignore` 增加 `semu/core`、`semu/core.*`、`semu/.cache/`、`semu_corpus.json`。 | `git status` 无残留产物。 |
| GAP-08 | `SEMU_WERROR=ON`（默认）给 core/CLI/tests 加 `-Werror`。 | GCC 全目标零警告构建。 |
| GAP-09 | C++ 增加 `condition_verdicts()`（按 word 解码 slot map 逐 condition 三态，`semu cond-eval`）与 `eval_predicate(predicate, slots)` 直接求值 API（`semu eval-cond` 从 stdin 读 `predicate<TAB>slot=value,...`）；Python `ConditionEvaluator.evaluate_tristate()`；测试对每条 corpus condition 用相同 slot map 比较两侧，并生成 false/unknown-token 样例——unknown-token 与 resolved 样例现在同时喂给 Python 和 C++ `eval-cond`。 | 21358 次比较：21337 true、21 false、0 unresolved、0 mismatch；21 false samples 两侧一致；unknown-token 样例 Python=None 且 C++=2（unresolved），resolved 样例 Python=True 且 C++=1。 |
| GAP-10 | `decoder_cuobjdump_test.py` 结构化比较：guard/mnemonic/**双向 modifier 相等**（SHL 与默认尺寸/半选 allowlist 后要求 m1s==m2s）/按位置 operand；寄存器双向相等；**branch target 按 fixture PC 转相对位移比较**（target == pc + 16 + disp）；float 位模式与十进制归一、hex 大小写归一、默认尾随立即数豁免。新增 `decoder_cuobjdump_tamper` CTest 验证 4 类篡改（寄存器/modifier/branch target/额外 operand）均被拒。 | 450/450 结构化比较通过，覆盖 branch=31、const=48、desc=65、guard=48、mem=11、plain=247；4 类篡改全部导致门禁失败。 |
| GAP-11 | 提交 reviewed cubin（`tests/tma_*.cubin`、`tests/pmtrig_test.cubin`，gitignore 例外，`git add -n` 确认可跟踪）与 regen 源（`semu/tests/data/regen/*.cu`）；`tools/rebuild_cuobj_fixture.py` 重建 fixture（含工具链版本 + SHA-256）；`cuobj_regen` CTest 验证重建一致性。 | 从仓库内容重建 450 words 与提交 fixture word-set 一致；7 个 fixture 文件（5 cubin + 2 源）均纳入版本控制。 |

复验后 CTest：**12/12 通过**（core, decoder, cli_smoke, manifest_regen, isa_regen,
decoder_roundtrip, decoder_ambig, cond_differential, decoder_cuobjdump,
decoder_negative, cuobj_regen, decoder_cuobjdump_tamper）；ASan+UBSan
（`detect_leaks=0 halt_on_error=1`）下 10/10 通过（含全量 1414-word
roundtrip、cond_differential、cuobjdump/tamper、negative/ambig 门禁），
无 UB 报告。

### 复验环境

- 编译器：g++ 12.2；构建：Ninja + CMake Debug。
- Sanitizer：`-fsanitize=address,undefined -fno-omit-frame-pointer`，
  `ASAN_OPTIONS=detect_leaks=0 UBSAN_OPTIONS=halt_on_error=1`（LSan 因 ptrace
  环境限制禁用；ASan/UBSan 未禁用）。
- cuobjdump：`/usr/local/cuda/bin/cuobjdump`（CUDA 13.x）。

### 尚存 allowlist

`tests/data/roundtrip_gaps.json` 260 项 = 193 matcher + 67 bits-differ，均为
assembler matcher 覆盖缺口（与参考 `tools/sass_disasm.py` 一致，非 decoder
bug）。修复 renderer/matcher 后应逐项缩小 allowlist 并记录原因。

## 8. 二次复验发现的剩余闭环项

### GAP-09 — `cond_differential` 尚未逐 condition 比较 Python/C++ 真值

**严重级别：** High  
**状态：** **Closed（2026-08-11）**  
**位置：** `semu/tests/cond_differential_test.py`

当前测试包含两条相关但不同的路径：

1. `semu scan-conds` 使用内建默认 slot 值检查 C++ parser 能完整消费并解析
   condition；
2. corpus word 的 slot map 仅交给 Python `ConditionEvaluator`，检查合法 word
   对所有 condition 求值为 true。

测试没有取得 C++ 对同一 `(condition, slot map)` 的逐条 verdict，因此
“Python 与 C++ 在 corpus words 上一致”尚未被直接证明。round-trip 和 negative
tests 只能提供端到端的间接佐证。

**关闭要求：**

- CLI 或测试 API 接受明确的 condition id/text 与完整 slot map，并返回
  `true/false/unresolved`，不得使用内建默认 slot 替代 corpus slot。
- 对全部合法 corpus condition 逐条比较 Python/C++ 三态结果。
- 生成 condition-false 与 unresolved/未知 token 样例，确认两侧均得到预期三态。
- mismatch、unresolved 或未完整消费必须使 CTest 失败；若确需例外，使用固定且
  可审阅的 allowlist。

**关闭证据：** CTest 输出至少记录总比较数、true/false/unresolved 数和 mismatch
数；验收要求 mismatch=0、意外 unresolved=0。unknown-token 与 resolved 样例
均通过 C++ `eval-cond` API 与 Python `evaluate_tristate()` 双侧验证：
unknown-token → C++=2 且 Python=None；resolved → C++=1 且 Python=True。

### GAP-10 — 真实 cuobjdump 门禁未覆盖完整 variant/operand/modifier

**严重级别：** High  
**状态：** **Closed（2026-08-11）**  
**位置：** `semu/tests/decoder_cuobjdump_test.py`

当前门禁只比较基础 mnemonic，并检查 cuobjdump 中出现的寄存器是否也出现在
semu 输出中。该检查是单向子集关系：多解码出错误寄存器仍可能通过；立即数、
predicate/not、variant、寄存器组、constant/uniform/memory operand 和 modifier
均未严格比较。

**关闭要求：**

- 将 cuobjdump 文本解析为规范化结构：predicate、完整 mnemonic/variant、按位置
  排列的 operand、立即数与 modifier；schedule text 可单独比较或明确排除。
- 将 semu `DecodedInst` 转成相同规范化结构，逐字段比较，而不是字符串包含检查。
- 寄存器必须按 operand 位置双向相等，禁止仅做 cuobjdump→semu 子集检查。
- fixture 至少覆盖 predicate/not、immediate、uniform/constant、memory、branch、
  register group 和高重叠 opcode；每类覆盖数写入测试输出。

**关闭证据：** 450 条现有向量全部通过结构化比较：双向 modifier 相等
（SHL 与默认尺寸/半选 allowlist 后要求 m1s==m2s）、按位置 operand、寄存器
双向相等、branch target 按 fixture PC 转相对位移比较
（target == pc + 16 + displacement）；`decoder_cuobjdump_tamper` CTest 对
4 类篡改（寄存器/modifier/branch target/额外 operand）逐一验证门禁失败。

### GAP-11 — sm120 真实向量 fixture 无法由仓库内容完整再生成

**严重级别：** Medium  
**状态：** **Closed（2026-08-11）**

fixture 的来源包含 `vecmix` 与 `vecmix2` cubin，但这两个输入当前不在仓库；提取
脚本只消费已有 cubin，并不生成这些输入。因此已提交 JSON 可以执行，却不能从
干净 checkout 独立重建。

**关闭证据：** `semu/tests/data/regen/vecmix.cu`、`vecmix2.cu` 已提交；
`tests/pmtrig_test.cubin`、`tests/tma_*.cubin` 作为 reviewed fixture cubin
提交（`.gitignore` 例外）；`semu/tools/rebuild_cuobj_fixture.py` 从仓库内容
重建 fixture（含工具链版本与输入 SHA-256 记录）；`cuobj_regen` CTest 验证
重建 word-set 与提交 fixture 一致（450/450）。

**关闭要求：** 以下方案任选其一：

- 提交可重建的 SASS/CUDA 源与确定性构建脚本；或
- 提交经过审阅的最小 cubin fixture；或
- 移除不可重建来源，并用仓库内可重建向量补齐同等覆盖。

生成脚本必须记录 CUDA toolkit/cuobjdump 版本、arch、输入 SHA-256、kernel、PC、
lo/hi word 和原始 disassembly。离线 CI 使用已提交 fixture；具备 CUDA 工具链的
regen test 应生成 byte-identical（版本导致文本差异时，至少规范化结构与 word
集合一致）的结果。

## 9. Phase 0/1 最终关闭矩阵

| 范围 | 状态 | 完成判据 |
|---|---|---|
| Phase 0 | **Closed / Pass** | 干净构建、`-Werror`、生成确定性、工程卫生、ASan+UBSan 均通过。 |
| Phase 1 核心 decoder | **Closed / Pass** | 1414/1414 unique，0 ambiguous/illegal；固定 round-trip allowlist；398 negative；450 real-word 基础检查。 |
| Phase 1 condition 等价性 | **Closed / Pass（GAP-09）** | 21358 次逐 condition Python/C++ 三态比较，0 mismatch、0 意外 unresolved；21 个 false samples 两侧一致；unknown-token 与 resolved 样例均经 C++ `eval-cond` API 双侧验证。 |
| Phase 1 独立反汇编等价性 | **Closed / Pass（GAP-10）** | 450 条真实向量全部通过结构化比较：双向 modifier 相等（allowlist 后 m1s==m2s）、按位置 operand、寄存器双向相等、branch target 按 PC 转位移比较；4 类篡改（寄存器/modifier/branch target/额外 operand）均有独立 CTest 验证被拒。 |
| Phase 1 fixture 可复现性 | **Closed / Pass（GAP-11）** | reviewed cubin 与 regen 源均纳入版本控制（`git add -n` 验证）；`cuobj_regen` 门禁从仓库内容重建 450 words 与提交 fixture 一致。 |

allowlist 的 260 项属于显式技术债，不阻止 Phase 1 关闭，但集合必须保持冻结：新增项失败、失效项提示清理。

## 10. 二次复验基线（2026-08-11）

- Debug、Ninja、`SEMU_WERROR=ON`：CTest **12/12** 通过，零编译警告。
- ASan+UBSan、`detect_leaks=0`、`halt_on_error=1`：CTest **10/10** 通过，
  无 UB；LSan 仅因 ptrace 环境限制禁用。
- Round-trip：1414 unique、0 ambiguous、0 illegal、1112 bit-exact、
  42 branch、260 allowlisted gaps。
- Conditions：21358 次逐 condition Python/C++ 三态比较（GAP-09），0 mismatch、
  0 意外 unresolved；21 false samples 一致；unknown-token/resolved 样例经
  C++ `eval-cond` 双侧验证。
- Real vectors：450/450 结构化比较通过（GAP-10），双向 modifier 相等、
  branch target 按 PC 位移比较；覆盖 branch=31、const=48、desc=65、guard=48、
  mem=11、plain=247；`decoder_cuobjdump_tamper` 验证 4 类篡改均被拒。
- Fixture 可复现性：`cuobj_regen` 从仓库内容重建 450 words 与提交 fixture
  word-set 一致（GAP-11）；fixture cubin 与 regen 源纳入版本控制。
- Negative vectors：398/398 rejected。
- `semu/core*`、`semu/.cache/`、build tree 与 Python cache 均已 ignore，工作树
  未发现这些生成物。
