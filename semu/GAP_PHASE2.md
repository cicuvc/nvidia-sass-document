# Phase 2 cubin loader 验收差距

**验收日期：** 2026-08-12  
**验收范围：** `SIM_PLAN.md` Phase 2 — 标准 cubin loader  
**当前结论（2026-08-12 修复后复验；二轮审阅修复；三轮审阅修复）：**
**Closed / Pass**。
P2-GAP-01～P2-GAP-08 全部关闭：kernel 与 constant/shared/local section
关联、KPARAM ordinal 规范化与校验、稳定 per-word IR、text/symbol 尺寸校验、
linked-symtab relocation、OSABI/ABI 强制校验和 EIATTR reviewed allowlist
均已实现并纳入门禁。

二轮审阅发现的 6 项问题已修复（2026-08-12）：

1. **OOB relocation sh_info 崩溃**（Blocker）：`apply_relocations` 在
   `rela.info >= sections.size()` 检查前索引 `section_names[rela.info]`，
   实测 sh_info=0xffff → SIGSEGV（status=139）。现全部消息经 `sec_name()`
   bounds-checked 辅助函数；探针复现 → exit 1 + 结构化错误，ASan 下无
   崩溃。回归测试 `cubin_relocation_oob_shinfo_no_crash`。
2. **inspection 模式不降级未知 EIATTR**（P2-GAP-08 语义）：`parse_eia_record`
   现接收 `inspect_mode`；非 allowlist 未知 id 在 inspection 下转为
   warning（带 "(inspection mode)" 标记），strict 下仍
   `kUnsupportedMetadata`。回归测试
   `cubin_inspection_allows_unknown_eiattr` + CLI `disasm`（inspection）
   容忍 0x51 探针。
3. **KPARAM 错误传播双 take_error**：现先 `Error e = kp.take_error()` 再
   `push_context` 再 `failure(std::move(e))`；回归测试
   `cubin_kparam_error_keeps_context` 断言 message 与 kernel context 都在
   report 中。
4. **overlap 检测依赖 ordinal/offset 同序**：现对副本按 offset 排序做
   range 检查（不依赖 ordinal 顺序），结果仍按 ordinal 排序输出。正向量
   `cubin_kparam_non_monotonic_offsets_ok`（ordinal 升序 + offset
   非单调不重叠）+ 负向量 `cubin_kparam_overlap_non_monotonic_rejected`。
5. **DecodedInstruction::pc 仍是文件偏移**：`PredecodedWord` 新增
   `file_offset`；`inst.pc` 与 `PredecodedWord::pc` 统一为 kernel-relative。
   回归测试 `cubin_word_pc_is_kernel_relative`。
6. **NOBITS relocation 不安全**：现明确拒绝（结构化错误），绝不写 raw
   cubin。回归测试 `cubin_relocation_nobits_target_rejected`。

三轮审阅发现的 3 项问题已修复（2026-08-12）：

1. **text alignment 0 被豁免**：`if (t.align != 0 && t.align < kTextAlign)`
   改为直接 `if (t.align < kTextAlign)`；实测 align 128→0 的真实 cubin 现在
   拒绝（`text section alignment 0 below 128`）。负向量
   `cubin_rejects_text_align_below_128`（align 0/1/16/64 全拒、128 通过）。
2. **debug relocation allowlist 过宽**：`target_debug` 从"非 exec 非 data 非
   NOBITS 一律跳过"改为精确名称 allowlist（`.debug_*`/`.zdebug_*`/
   `.eh_frame`）；其他非 exec 非 data 未知 target 在 strict 模式硬失败
   （`kUnsupportedMetadata`，消息含 "debug allowlist"），inspection 模式
   warning；并移除 `(inspect_mode || true)` 恒真短路。回归测试
   `cubin_relocation_unknown_target_strict_fails` +
   `cubin_relocation_debug_allowlist_skips`；真实 nvcc `.rela.debug_frame`
   仍正常跳过。
3. **缺 `Module::executable()`**：新增 API，strict `load` → true、
   `load_for_inspection` → false；回归测试 `cubin_executable_flag`。

干净 Debug 构建 CTest 15/15，`cubin_loader` 43 项单元测试与 `cubin_load`
集成门禁在普通与 ASan+UBSan 下全部通过，零编译警告。Phase 2 正式
**Closed / Pass**。

## 1. 已验证通过的能力

- 解析 ELF64 little-endian、`EM_CUDA` 和 sm120 `e_flags=0x06007802`。
- assembler 生成的单 kernel cubin 可以加载、枚举和反汇编。
- nvcc 生成的三 kernel cubin可以加载；kernel 名、text size 和 regcount 与
  `readelf`/`cuobjdump -res-usage` 对照一致。
- 当前 assembler/nvcc 样本中的 KPARAM ordinal/offset/size 可以提取。
- static shared、named barrier、mbarrier、exit offset 和 cluster metadata 的
  已覆盖主路径存在。
- CLI `inspect`、`list-kernels`、`disasm <cubin> [kernel]` 可用。
- loader 是纯 C++ parser，不链接或动态加载 CUDA Driver API。
- 干净 Debug、Ninja、`SEMU_WERROR=ON`：CTest **14/14** 通过。
- Phase 2 专项门禁 `cubin_loader` 与 `cubin_load` 均通过。

这些结果证明核心路径已经建立，但不能覆盖以下阻断项。

## 2. 阻断问题（已全部关闭，2026-08-12）

关闭证据（对应修复提交）：
- P2-GAP-01：`Kernel::constant0/shared/local` + `KernelSectionRef` +
  `Module::section_view()`（span，bounds-checked，NOBITS 空 view）；
  `FRAME_SIZE/MIN_STACK_SIZE/MAX_STACK_SIZE` 解析进 `KernelMetadata`。
- P2-GAP-02：`normalize_kparams()` 按 ordinal 升序排序并拒绝
  duplicate/zero-size/overlap/溢出/OOB；`param_by_ordinal()` 支持 ABI hole。
- P2-GAP-03：`PredecodedWord` 每 16B word 一个稳定 entry（unique 状态 +
  reason + kernel-relative pc）；strict load 对 illegal/ambiguous 失败，
  `load_for_inspection` 保留 placeholder；`word_at(kernel, pc)` 按 kernel PC
  索引。
- P2-GAP-04：text size % 16 == 0、section align >= 128、function symbol
  range ⊆ text section 均强制校验。
- P2-GAP-05：`apply_relocations` 用 linked symtab、按 relocation width 做
  bounds 检查、debug-only target 按 section 类型 allowlist 跳过、
  unknown exec/data type 硬失败；positive vectors（ABS32/ABS64/secondary
  symtab/constant target）+ negative vectors（bad symbol/unknown type）。
- P2-GAP-06：symtab 名称经各自 sh_link 的 strtab 解析；entsize>=24、
  size%entsize==0、sh_link 指向 strtab、st_shndx 合法、overflow-safe
  `range_fits()`。
- P2-GAP-07：OSABI 0x41 / ABI version 0x08 allowlist 强制校验。
- P2-GAP-08：EIATTR reviewed allowlist（0x1e 等可跳过 warn；其余未知默认
  kUnsupportedMetadata）；`load`（strict）与 `load_for_inspection`
  （permissive）双模式。

### P2-GAP-01 — Kernel 未关联 constant/local sections

**严重级别：** Blocker  
**位置：** `include/semu/cubin.hpp`、`src/cubin/loader.cpp`

`Kernel` 当前只保存 text section、预解码结果和 `KernelMetadata`。loader 只对
`.nv.shared.<kernel>` 计算了 `static_shared`，没有向 kernel 暴露或关联：

- `.nv.constant0.<kernel>` 及其他 constant bank；
- `.nv.local.<kernel>` 或由 frame/local metadata 表达的 per-thread local storage；
- section 在 raw image 中的 byte view、section index、alignment 和关联依据。

真实 `tests/tma_test.cubin` 已包含 `.nv.constant0.<kernel>`，但该关联只能从全局
section 列表由调用方重新猜测。已识别的 `FRAME_SIZE`/stack 类 EIATTR 也被直接
忽略。这不满足计划中“根据 symbol/section link 将 text、constant bank、shared/
local section 和 per-kernel info 正确关联”的要求，并会阻塞 Phase 3 初始化
constant0 和 local address space。

**关闭要求：**

- `Kernel` 或 `KernelMetadata` 明确保存 per-kernel constant/shared/local section
  association；使用 `sh_info`、symbol `shndx`/link 等 ELF 关系，不只靠名称猜测。
- 提供 bounds-checked、只读 section byte view；NOBITS section 记录逻辑大小而不
  读取文件 payload。
- 解析并保存执行所需 frame/local/stack metadata；暂不支持的执行相关字段必须
  返回 `UnsupportedMetadata`，不能静默忽略。
- 多 kernel cubin 中每个 kernel 只能取得自己的 constant/shared/local sections。

**复验要求：** assembler 与 nvcc 多 kernel fixture 逐 kernel 对照 section index、
size、alignment 和 constant0 bytes；故意交换 `sh_info` 或越界关联必须失败。

### P2-GAP-02 — KPARAM 顺序违反公共 API 契约

**严重级别：** Blocker  
**位置：** `include/semu/cubin.hpp`、`src/cubin/loader.cpp`

公共头文件声明 `KernelMetadata::params` 按 ordinal 排序，但实现按 EIATTR 记录出现
顺序直接 `push_back`。真实 nvcc fixture 当前得到 ordinal `2,1,0`；集成测试也
显式接受该逆序。若 Phase 3 按 vector index 绑定 `KernelArg`，参数将被错误装入。

loader 也没有统一验证重复 ordinal、重复/重叠 byte range、零 size、参数越过
`cbank_param_size`，以及 ordinal 是否形成允许的布局。

**关闭要求：**

- 完成 EIATTR 聚合后按 `ordinal` 升序排序。
- 拒绝重复 ordinal、零 size、整数溢出、重叠 range 和越过 parameter cbank 的
  range；允许 padding 和非连续 offset。
- 明确定义 ordinal 是否必须连续；若 ABI 允许 hole，API 必须能按 ordinal 查找，
  不能用 vector index 隐式替代 ordinal。
- assembler 与 nvcc metadata 进入完全相同的规范化 `KernelMetadata`。

**复验要求：** 输入 EIATTR 顺序做全排列后 metadata byte-for-byte 相同；真实 nvcc
样本输出 ordinal `0,1,2...`；duplicate/overlap/OOB/zero-size negative vectors
全部被拒绝。

### P2-GAP-03 — 非唯一指令从 `predecoded` 删除，破坏 PC 索引

**严重级别：** Blocker  
**位置：** `src/cubin/loader.cpp` 的 kernel text 预解码循环

实现只把 unique decode 放入 `Kernel::predecoded`；illegal/ambiguous word 仅产生
warning，随后跳过。这样第一个失败 word 之后的 `predecoded[index]` 都不再对应
`PC = index * 16`，`instruction_at()` 可能返回错误指令。

实测将 `tests/tma_test.cubin` 的首个 128-bit word 清零：

- module 仍成功加载；
- 产生 non-unique warning；
- disassembly 从 `/*0010*/` 开始，`/*0000*/` 消失；
- 后续 vector 索引与真实 PC 错位。

这违反“module load 时预解码所有 kernel text”的要求，也无法安全地保留
decode-only/unsupported instruction。

**关闭要求：**

- 每个 16-byte word 必须对应一个稳定 IR entry，保存 unique/illegal/ambiguous
  状态、raw word、kernel-relative PC 和诊断原因；不得删除失败 entry。
- 或者将 illegal/ambiguous word 作为 module load failure。若允许 inspection-only
  module，必须显式标记 module/kernel 不可执行。
- `instruction_at` 使用 kernel-relative PC 或明确区分 file offset 与 kernel PC，
  不能让 file layout 泄漏为执行 PC。

**复验要求：** 在 text 首/中/末分别注入 illegal 和 ambiguous word，IR entry 数
保持 `text_size/16`，相邻 PC 不错位；CLI 必须显示失败位置和 raw word。

## 3. 高优先级正确性缺口

### P2-GAP-04 — 可执行 text 的尺寸和 symbol range 校验不足

**严重级别：** High

loader 没有要求 `.text.*` size 是 16 的整数倍。实测把真实 text size 从 2432
修改为 2431，module 仍成功加载并静默忽略尾部 15 bytes。

**关闭要求：**

- executable SASS text 必须满足 `size % 16 == 0` 和 sm120 所需 alignment。
- function symbol `st_value/st_size` 必须落在关联 text section 内，且不能整数溢出。
- 明确支持“一个 text section 多 function symbol”还是“一 kernel 一 section”；
  不支持的布局必须结构化失败。
- text section 与 function symbol size 不一致时不得静默选择其中之一。

### P2-GAP-05 — Relocation 实现和测试未形成有效门禁

**严重级别：** High  
**位置：** `src/cubin/loader.cpp` relocation loop、`tests/test_cubin.cpp`

名为 `cubin_relocation_out_of_range_symbol_fails` 的单元测试没有构造 relocation，
只验证零 relocation cubin 可以加载。Python 集成测试也没有注入 relocation
failure。当前 committed cubin 的标准 `.rela.text.*` 均为空，因此 14/14 通过不能
证明 executable relocation 正确。

实现还存在以下问题：

- relocation symbol index 是其 `sh_link` 所指 symtab 内的局部 index；当前实现却
  直接索引合并后的全局 `symbols_`。
- 所有 relocation 先用 `r_off + 8` 检查，错误拒绝位于 section 尾部的合法 32-bit
  relocation。
- 没有严格验证 relocation `entsize >= 24`、`size % entsize == 0` 和 `sh_link`
  指向合法 symtab。
- non-executable target 的 relocation 一律跳过；若目标为 `.nv.constant*` 等执行
  可见数据，跳过会改变 kernel 语义，不能当作普通 warning。
- relocation 的 symbol section/value/addend 与最终载入地址语义尚未建立明确契约。

**关闭要求：**

- 每个 relocation section 使用自己的 linked symtab 和 linked string table。
- 按 relocation width 做 target bounds/overflow 检查。
- 明确支持的 `R_CUDA_*` 列表、计算公式、允许的 target section 和未支持策略。
- 对会影响 text/constant/global data 的未知 relocation 返回明确错误。
- 保留 debug-only relocation 可以跳过，但须按 section 类型精确 allowlist。

**复验要求：** 至少覆盖 ABS32、ABS64/指针、addend、多个 symtab、坏 `sh_link`、
坏 symbol index、target OOB、未知 executable type、constant target 和可跳过 debug
relocation；每个 positive vector 对照 `readelf -r` 或独立 reference patcher。

### P2-GAP-06 — ELF section/symbol table 校验未完全遵循 link 关系

**严重级别：** High

loader 通过名字查找全局 `.strtab`，没有使用每个 symtab 的 `sh_link`；多个 symtab
或非标准字符串表名会被错误解析。另有以下健壮性问题：

- 未要求 ELF64 symbol `entsize >= 24`。
- section table、section data 和字符串地址的 `offset + size` 检查可能发生无符号
  整数溢出，应改为 `offset <= file_size && size <= file_size - offset`。
- 无效 `sh_name` 当前可能得到空 section name而非明确失败。
- 没有验证 symtab entry 的 `st_shndx` 是否为合法 section/special index。

**关闭要求：** 所有 table/section 通过 `sh_link` 解析，入口尺寸和整除关系严格
校验，所有范围检查使用 overflow-safe 形式，并增加相应 malformed ELF corpus。

## 4. 文档与策略不一致

### P2-GAP-07 — CUDA OSABI 被记录但未验证

**严重级别：** Medium

源码注释和 `BASELINE.md` 声称检查 OSABI，实际只保存 `e_ident[EI_OSABI]` 与 ABI
version。将真实 cubin OSABI 从 `0x41` 改为 `0` 后仍成功加载。

**关闭要求：** 二选一并保持代码、API、测试和文档一致：

1. 强制 raw CUDA cubin 的预期 OSABI/ABI version allowlist，错误值拒绝；或
2. 证明 OSABI 非识别 sm120 raw cubin 的必要条件，删除“已验证”声明并把接受策略
   写入兼容性文档。

至少增加错误 OSABI 和未知 ABI version 测试。

### P2-GAP-08 — Unknown EIATTR 策略依赖 payload 大小猜测

**严重级别：** Medium

当前使用“fmt=4 且 payload>=8”近似判断未知 EIATTR 是否 execution-affecting；较短
payload 也可能改变执行语义，较长 payload 也可能只是可跳过注释。该启发式缺少
ABI 依据。

**关闭要求：** 建立按 EIATTR id/fmt/section scope 的 reviewed allowlist：已知可
跳过项 warning，已知执行相关项解析，未知项默认 `UnsupportedMetadata`。若需要
permissive inspection 模式，应与 executable module load 模式显式分开。

## 5. 必须补充的自动化验证

Phase 2 关闭前至少增加：

1. constant0/shared/local section 的单、多 kernel association tests。
2. KPARAM 顺序随机化，以及 duplicate/overlap/OOB/zero-size tests。
3. illegal/ambiguous word placeholder 与 PC/index stability tests。
4. odd text size、错误 alignment、symbol range/size mismatch tests。
5. 真实非空 relocation positive/negative corpus；不能以零 relocation 替代。
6. linked symtab/strtab、多 symtab、坏 `sh_link` 和过小 `entsize` tests。
7. offset/size 接近 `UINT64_MAX` 的 overflow tests。
8. OSABI/ABI policy tests。
9. unknown skippable 与 unknown execution-affecting EIATTR 的独立门禁。
10. ASan+UBSan 下全部 loader unit/integration/fuzz seed tests。

## 6. Phase 2 关闭矩阵

| 能力 | 当前状态 | 关闭判据 |
|---|---|---|
| ELF64/sm120 基本识别 | **Closed / Pass** | OSABI 0x41/ABI 0x08 allowlist；全部范围检查 overflow-safe；linked table 校验完整。 |
| Section/symbol 枚举 | **Closed / Pass** | 多 symtab/strtab 经 sh_link 解析，entsize/size%entsize/sh_link/st_shndx 均有门禁。 |
| Kernel 枚举与 text | **Closed / Pass** | symbol range 合法、text 16B 对齐、每 word 有稳定 IR entry。 |
| KPARAM metadata | **Closed / Pass** | ordinal 升序规范化 + duplicate/overlap/OOB/zero-size 拒绝；param_by_ordinal。 |
| Resource metadata | **Closed / Pass** | reg/shared/barrier/exit/cluster 已有；frame/local/stack 已解析并暴露。 |
| Constant/shared/local 关联 | **Closed / Pass** | 每 kernel 经 sh_info 关联 constant0/shared/local，byte/NOBITS view 提供，多 kernel 不串联。 |
| Relocation | **Closed / Pass** | 非空 positive vectors（ABS32/ABS64/secondary symtab/constant target）+ 完整 negative corpus，text/constant 语义正确。 |
| CLI inspection/disasm | **Closed / Pass** | malformed word 显示 `<unresolved>` 不丢 PC；strict load 与 inspection disasm 状态明确。 |
| 无 CUDA Driver 依赖 | **Closed / Pass** | 纯 parser，当前已经满足。 |

P2-GAP-01～P2-GAP-08 全部满足关闭要求；三轮审阅补充修复（align 0 豁免、
relocation target 精确 allowlist、`Module::executable()`）已纳入门禁。
普通构建（CTest 15/15，`cubin_loader` 43 项单元 + `cubin_load` 集成）与
ASan+UBSan（`halt_on_error`，全部 loader 测试）下通过。Phase 2 状态为
**Closed / Pass**。

## 7. 本次复验命令与证据

普通构建：

```bash
cmake -S semu -B /tmp/semu_phase2_accept -G Ninja \
  -DCMAKE_BUILD_TYPE=Debug -DSEMU_BUILD_TESTS=ON \
  -DSEMU_BUILD_CLI=ON -DSEMU_WERROR=ON
cmake --build /tmp/semu_phase2_accept -j8
ctest --test-dir /tmp/semu_phase2_accept --output-on-failure
```

结果：CTest **14/14** 通过，零编译警告。专项 `cubin_loader`、`cubin_load`
均通过；nvcc 三 kernel fixture 的名称、text size、regcount 和当前 KPARAM 样本
与外部工具对照一致。

额外畸形输入探针（修复后）：

- OSABI `0x41 -> 0x00`：拒绝，`not an sm120 cubin (OSABI/ABI version
  mismatch)`（`cubin_rejects_wrong_osabi`/`cubin_rejects_wrong_abi_version`）。
- text size `2432 -> 2431`：拒绝，`not a multiple of 16`
  （`cubin_rejects_odd_text_size` + 集成门禁）。
- kernel 第一个 word 清零：strict `load` 拒绝（`decodes as illegal`）；
  `disasm`（inspection）输出 `/*0000*/  <unresolved: illegal ...>`，
  `/*0010*/` 保持原样，PC/index 不错位（`cubin_illegal_word_*` +
  集成门禁）。
- KPARAM EIATTR 顺序全排列：`cubin_kparam_permutations_normalize_to_same_order`
  验证 metadata 一致；duplicate/zero-size/overlap/OOB 各负向量拒绝。
- 真实非空 relocation：ABS32/ABS64（addend）、secondary symtab 独立
  strtab、constant target、bad symbol、unknown exec type 全部有正/负向量。
- 多 symtab/坏 sh_link/过小 entsize/无效 sh_name/st_shndx 均有 malformed
  ELF 门禁。
- 未知 EIATTR：allowlist（0x1e）→ warning + load 成功；非 allowlist（0x51）
  → kUnsupportedMetadata 拒绝（单元 + 集成）。

