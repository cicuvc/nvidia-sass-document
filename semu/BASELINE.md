# Phase 0 基线冻结记录

本文件是 SIM_PLAN Phase 0（工程骨架与基线冻结）的记录。冻结内容同时编译进
capability manifest（`semu capability`），由 `tools/gen_capability.py` 生成。

## 冻结日期

2026-08-11（repo HEAD `9c8a44f`，SIM_PLAN.md 已提交但 Phase 0 实现未提交）。

## 目标 ISA 数据规模（sm120.json，由 tools/parse_sm120.py 生成）

| 项 | 数量 |
|---|---|
| encoding variants（含 ALTERNATE CLASS） | 1414 |
| mnemonics | 259 |
| enums | 449 |
| tables（含 illegal-encoding 表） | 89 |
| FUNIT uC fields | 2142 |
| pipe（latency 文件 OPERATION SETS 条目） | 300 |

Phase 1 目标：1414 variants 全部可唯一解码（decode-only 升级）。

## 参考平台

- GPU：NVIDIA RTX 5090（GB202, sm_120, Blackwell consumer）
- CUDA：13.0（launchprobe 平台记录）；13.1（repo sm90/sm100 工具链验证）
- driver：580.65.06（open kernel modules, GSP-RM）

> ISA 事实来源：`sm120_instructions.txt` / `sm120_latencies.txt`（nvdisasm dump）。
> 无 CUDA 环境时不能做 GPU differential；L3 仅在 sm120 机器上可选运行。

## 现有验证测试清单（基线快照，生成时统计）

- `tests/*.cu`：203 个 CUDA kernel
- `tests/asm_construct/test_*.py`：121 个 assembler/round-trip 测试
- `tools/decode_*.py`：111 个 decoder 脚本（Phase 1 向量来源）

## 能力状态约定

`capability_data.{hpp,cpp}` 中每个 variant 记录
`decode-only` / `functional` / `profiled` / `unsupported` 之一。

Phase 0 基线：全部 1414 variants = `unsupported`。
Phase 1 完成后：全部 variants 升级为 `decode-only`（decoder 唯一 + round-trip）。

## 已冻结的公共契约

- 错误模型 v1：`Status` / `Error`（原因链 + context 帧）/ `Result<T>` /
  `Fault`（kernel/PC/CTA/warp/active mask/原始指令/decoded variant/原因链）。
- capability manifest schema v1（`to_json`/`from_json` byte-identical round-trip）。
- 生成器确定性：重复运行产生 byte-identical 输出（CTest `manifest_regen`）。
- CLI 退出码：0 成功 / 1 运行错误 / 2 用法错误。

## Phase 0 退出条件核对

- [x] 无 CUDA 环境可 configure/build/CTest（本机验证：g++12.2 + Ninja + CTest）。
- [x] `semu --version`、空 module、非法命令行 → 结构化错误。
- [x] capability manifest 重复生成 byte-identical（`manifest_regen` 通过）。
- [x] ASan+UBSan 构建通过全部测试（`build-asan`）。
- [x] 未修改仓库根目录未跟踪的 `sim.py`。
- [x] Phase 1 将 manifest 全量升级 decode-only（下一阶段）。

## Phase 1 完成记录（2026-08-11）

### 目标

1414 个 sm120 encoding variants 全部可唯一解码（decode-only 升级），通用 decoder
只依赖生成的 ISA 表（`semu/generated/isa_data.*`）。

### 交付物

- `src/decoder/`：`decoder.cpp`（candidate 匹配 + legality）、`expr.cpp`（条件
  谓词求值）、`render.cpp`（规范化反汇编，`tools/sass_disasm.py` 的 C++ port）。
- `tools/gen_isa.py` → `generated/isa_data.{hpp,cpp}`（1414 variants / 451 enums /
  89 tables / 322 shared-opcode groups / 9 pipes）。
- `tools/gen_corpus.py` → 每个 variant 一个合法 encoding word 的 corpus。
- `cli/semu disasm`：单字 + stdin 批量解码（OK / AMBIG / ILLEGAL + 候选原因）。
- CTest 门禁：`decoder`（L0 单测）、`decoder_roundtrip`、`decoder_ambig`、
  `isa_regen`，加上原有 `core`/`cli_smoke`/`manifest_regen`。

### 关键实现决策

- **歧义消解**：共享 opcode 的 variants 用以下机制区分：
  - `*dstfmt`/`*srcfmt`/`*merge`/`*op` 等 star_slot discriminator 字段做
    **enum-membership 校验**（值必须是该 slot 的 enum 成员，否则拒绝该 candidate）；
  - `*TABLES_x(...)` 字段做 **table reverse lookup**（LDGMC/UBLKCP 的 mem 字段）；
  - 固定字段（`num`/`star_num`/`star_slot` 字面量）、reserved bits 和 legality
    condition 联合判定。
- **解码正确性验证**：decode → 用参考 assembler 重新 encode → bit-exact 对比。
  对 1414 个 corpus word，1112 个 bit-exact round-trip；其余为 assembler matcher
  覆盖缺口（与参考 disassembler `tools/sass_disasm.py` 完全一致，非 decoder bug）。
- **corpus 生成**：`gen_corpus.py` 求解器包含 discriminator 归一化、按需 backtracking
  （处理 TEX/TLD 等 617-condition 变体）、格式默认值优先。全部 1414 variants 可编码。

### 验证结果

- 1414/1414 corpus word 通过 `semu disasm` **唯一解码**（0 ambiguous / 0 illegal）。
- 高重叠 opcode（F2FP/F2I/BAR/CCTL/PLOP3/PSETP/HMMA/QMMA/IMAD/...）361 个词全部唯一。
- reserved-bit 翻转测试：2488 次翻转全部与未翻转解码一致（无跨 variant 误匹配）。
- `gen_isa.py`/`gen_corpus.py` 在 8 个不同 `PYTHONHASHSEED` 下 byte-identical。
- ASan+UBSan 构建通过全部 CTest（含全量 1414-word roundtrip），无 UB 报告。
- 真实 sm120 cuobjdump 向量：450 个唯一 words 通过**结构化比较**
  （guard/mnemonic/双向 modifier 相等/按位置 operand/寄存器双向相等/branch
  target 按 PC 位移比较），覆盖 branch=31、const=48、desc=65、guard=48、
  mem=11、plain=247（`decoder_cuobjdump`）；4 类篡改由
  `decoder_cuobjdump_tamper` 验证被拒。
- 负向量：398 个（illegal-encodings 表行 / discriminator enum hole / 寄存器
  对齐破坏）全部被拒（`decoder_negative`）。
- condition evaluator：20003/20003 条件完整解析（`semu scan-conds` 0 gaps）；
  21358 次逐 condition Python/C++ 三态比较 0 mismatch、0 意外 unresolved
  （`cond_differential`）。
- fixture 可复现性：`cuobj_regen` 从仓库内容（committed cubins + regen 源）
  重建 450 words 与提交 fixture 一致。

### Phase 1 退出条件核对

- [x] 所有已有测试向量可以唯一解码（1414/1414 corpus words；431 个 sm90 向量中
      356 个 opcode 与 sm120 重合者全部唯一解码，其余为 sm90 专属编码）。
- [x] 任意 128-bit word 只会得到唯一结果、明确非法结果或明确 ambiguous 结果
      （decoder 的 `OK`/`ILLEGAL`/`AMBIG` 三态 + 候选原因；不静默选择）。
- [x] 所有执行 backend 均只依赖生成后的 IR（decoder 仅消费 `isa_data.*`，从不
      访问原始 dump）。

### 验收差距修复（2026-08-11，详见 GAP.md 第 7～9 节）

- GAP-01（64-bit shift UB）、GAP-02（字符串指针比较）已修复，`-Werror` 零警告。
- GAP-03：round-trip 门禁改为固定 allowlist（`tests/data/roundtrip_gaps.json`，
  260 项），新增 gap 即失败。
- GAP-04：condition evaluator 三态化 + `TABLES_x` 取值语法 + `scan-conds` +
  Python differential。
- GAP-05：真实 cuobjdump vector fixture（450 words）+ `decoder_cuobjdump` 门禁。
- GAP-06：负向量门禁 `decoder_negative`（398 例）。
- GAP-07：core dump / clangd cache 清理并 gitignore。
- GAP-08：`SEMU_WERROR=ON` 默认开启。
- GAP-09：`semu cond-eval`/`eval-cond` 三态 API（含直接对指定表达式+slot map
  求值）+ Python `evaluate_tristate`，21358 次同 slot map 对比 0 mismatch；
  unknown-token/resolved 样例双侧验证。
- GAP-10：cuobjdump 结构化比较（双向 modifier、寄存器组、branch target 按 PC
  位移），450/450；`decoder_cuobjdump_tamper` 验证 4 类篡改被拒。
- GAP-11：committed cubins + regen 源（均已纳入版本控制）+
  `rebuild_cuobj_fixture.py` + `cuobj_regen` 门禁，fixture 可从仓库内容重建。
- CTest 12/12 通过；ASan+UBSan（halt_on_error）10/10 通过。

### 未解决项

- 剩余非 round-trip 的 corpus word（260 项 allowlist）是 assembler matcher 的
  覆盖缺口，与参考 disassembler 表现一致；Phase 2 cubin loader 不依赖逐字
  round-trip。修复 renderer/matcher 后应逐项缩小 allowlist。
- `tools/decode_*.py` 是 sm_90 解码器，其向量不能直接作为 sm120 输入（opcode 布局
  不同）；sm120 的地面真值是本 repo 的 sm120.json + assembler encode 路径 +
  `tests/data/cuobj_vectors_sm120.json` 真实 cuobjdump fixture。

## Phase 2 完成记录（2026-08-12）

- Loader 位于 `src/cubin/loader.cpp` + `include/semu/cubin.hpp`（`Module` /
  `Kernel` / `KernelMetadata` / `SectionInfo` / `SymbolInfo` / `LoadWarning`）。
  纯 ELF64 解析，无 CUDA driver 链接（Phase 2 退出条件 3）。
- ELF 校验：magic / class=2 / data=1 / e_machine=EM_CUDA / e_flags=0x06007802 /
  OSABI=0x41 / ABI=0x08；section/symbol/strtab 全量 bounds-check。
- Kernel 关联规则（与 nvcc 12.8 + repo assembler 一致）：
  GLOBAL|STT_FUNC|STO_ENTRY(0x10) 符号、shndx→`.text.<mangled>`；
  `.nv.info.<mangled>` 经 sh_info→text 关联；device `.nv.info` 经 func_sym
  关联 REGCOUNT/FRAME_SIZE/MIN_STACK；`.nv.shared.<mangled>` 经 sh_info 关联
  static shared（size−0x400 为 CTA 可用窗口）；`.nv.constant0.<mangled>` 经
  sh_info 关联。
- EIATTR 记录格式（fmt=1 marker / fmt=2 bval / fmt=3 hval / fmt=4 sized），
  已解析 id：0x2f REGCOUNT、0x17 KPARAM（ordinal/offset/size-code
  `(size<<2)|1`）、0x1c EXIT、0x39 MBARRIER（16B 记录）、0x4c NUM_BARRIERS、
  0x38 NUM_MBARRIERS、0x1b MAXREG、0x19 CBANK_PARAM_SIZE、0x0a PARAM_CBANK、
  0x3d/0x3e CLUSTER、0x37 CUDA_API_VERSION、0x11/0x12/0x23 stack。
  未知 fmt=2/3/小 fmt=4 → warning 保留；未知大 fmt=4（可能 exec-affecting）
  → kUnsupportedMetadata。
- Relocation：`.rela.*` symbol/目标 section/offset 校验；text 目标应用
  R_CUDA_ABS64/ABS32/PTR/SYMOFF；unsupported type on exec → fault；非 exec
  目标（`.rela.debug_frame`）跳过+告警。
- 预解码：load 时解码全部 16B words，decode-only 指令保留，非唯一 word 记
  warning（不阻断 load）。
- CLI：`load`（替换 Phase 0 placeholder，保持 missing/empty 行为）、
  `inspect`、`list-kernels`、`disasm <cubin> [kernel]`（与单 word
  `disasm <lo> <hi>` 按首个参数形态自动判别）。
- 实测对照（nvcc 12.8 多 kernel cubin）：3 kernels（_Z5k_nopv 256B、
  _Z7k_scalePKfPfif 384B、_Z5k_addPKfS0_Pfi 512B；REG 4/10/12；KPARAM
  8/8/8/4@0/8/16/24）与 `readelf -SW/-s`、`cuobjdump -res-usage` 逐字段一致；
  committed tma/pmtrig cubins 全部可加载（tma_test: regs=38、152 inst、
  mbarrier+cluster 元数据）。
- 门禁：CTest `cubin_loader`（合成 cubin 单元测试）+ `cubin_load`（真实
  cubin 集成 + 错误路径注入）；CTest 14/14、ASan+UBSan 通过、零编译警告。

## Phase 2 验收关闭（2026-08-12，`semu/GAP_PHASE2.md`）

- P2-GAP-01～P2-GAP-08 全部关闭：Kernel constant/shared/local 关联 +
  byte/NOBITS view + frame/local/stack 元数据；KPARAM ordinal 规范化 +
  duplicate/overlap/OOB/zero-size 拒绝 + `param_by_ordinal`；每 word 稳定
  IR entry（strict 失败 / inspection placeholder，PC 不错位）；text 16B
  对齐 + symbol range 校验；linked-symtab relocation（width-aware、
  debug-only allowlist、unknown exec type 硬失败）；ELF link 关系全遵循
  （多 symtab/strtab、entsize、sh_link、st_shndx、overflow-safe 范围）；
  OSABI/ABI allowlist；EIATTR reviewed allowlist + strict/permissive 双
  模式。
- `cubin_loader` 38 项单元测试 + `cubin_load` 集成门禁（含 GAP 探针：
  坏 OSABI、odd text size、illegal word placeholder 不丢 PC、constant0
  关联、非 allowlist EIATTR 拒绝）。
- 二轮审阅（2026-08-12）修复：OOB relocation sh_info 崩溃（复现探针
  SIGSEGV→结构化错误，ASan 确认）、inspection 模式降级未知 EIATTR、
  KPARAM 单次 take_error + offset 排序 overlap 检测、inst.pc
  kernel-relative + file_offset 分离、NOBITS relocation 拒绝。
- 三轮审阅（2026-08-12）修复：text align 0 豁免移除（<128 拒绝）、
  relocation target 精确 debug allowlist、`Module::executable()` API。
- `cubin_loader` 43 项单元测试；普通 CTest 15/15 与 ASan+UBSan 全绿，
  零编译警告。Phase 2 **Closed / Pass**。

## Phase 3 完成记录（2026-08-12）

- 虚拟内存 `MemoryAllocator`：64-bit 确定性地址空间（相同分配序列 →
  相同地址）、单调不复用 `AllocationId`、global/constant/shared/local
  四空间、allocate/free/read/write/memset/copy 全部生命周期/越界/对齐
  结构化检查（OOB/use-after-free/double-free/未知指针）。
- `ConstantBank`：sm120 ABI 常量窗口（param_base 0x380、
  SLOT_DEFAULT_CDESC 0x358、size 0x10000）；参数经
  param_base + KPARAM.offset 落位；预置 slot 初始化。
- Launch ABI：`Context` / `RuntimeModule` / `Function` / `LaunchConfig` /
  `LaunchResult` / `IBackend`；逐项 `KernelArg` 与 packed buffer 两条
  路径 byte-identical（标量截断低字节、kBytes 精确宽度）；错参数数量/
  宽度、packed 过短、未知 kernel 结构化失败。
- 移植 assembler `test_bigparam` → CPU 测试（128B 参数在 constant0 中
  逐字节一致）。
- 门禁：CTest `memory` 20 项；普通 CTest 15/15、ASan+UBSan 全绿、
  零编译警告。Phase 3 退出条件全部满足。

## Phase 3 验收关闭（2026-08-12，`semu/GAP_PHASE3.md`）

- P3-GAP-01～09 全部关闭：constant slot absolute 写址 + layout 不变量 +
  bank 确定性初始化；pointer 参数生命周期验证；IRuntimeServices +
  BackendLaunchRequest + Function 所有权；INT64_MIN-safe 指针算术；
  ParamPackFormat 强类型；typed access 对齐/空间/宽度契约；owner 域隔离与
  回收；shared size overflow；跨 launch 银行清理。
- 二轮审阅（2026-08-12）：DeviceAccess::domain 域隔离（跨 CTA/跨 warp
  拒绝）、每 CTA shared allocation + 稳定 owner + 回收（成败路径 +
  无 backend）、AccessKind 一致性 + atomic/text 规则 + 1..256 全宽度矩阵、
  layout slot overflow-safe 检查、IEventSink/BasicMemoryEvent event ABI。
- 三轮审阅（2026-08-12）：CtaSharedView span 传 backend（多 CTA 完整
  可见）、CTA domain ID Context-local + checked range、LaunchResult 移除
  失效 shared pointer、grid/block dims overflow-checked、event 记录改名
  BasicMemoryEvent。
- 四轮审阅（2026-08-12）：launch 验证 block product（零维度拒绝、
  1024 线程 cap）；double take_error 修复；LaunchResult 注释明确
  "不暴露 live/owning pointer"。
- `memory` 32 项单元测试；普通 CTest 15/15、ASan+UBSan（halt_on_error=1）
  全绿、零编译警告。Phase 3 **Closed / Pass**。

## Phase 3.5 完成记录（2026-08-12，`semu/GAP_PHASE3_5.md`）

- Cluster DSMEM：`(rank<<24)|offset` 逻辑地址（sm120 实测）、
  `SharedAccessMode::kLocal/kDistributed` 显式模式、`ClusterTopology`
  （非零/overflow/cap 8/尾部部分 cluster 拒绝）、
  `IRuntimeServices::translate_shared/read_shared/write_shared`、
  `BackendLaunchRequest::cluster`、`BasicMemoryEvent` DSMEM 身份字段。
- 初验修复（2026-08-12）：3D cluster tile 映射、launch_generation 令牌
  防伪造、真 DSMEM atomic RMW、DeviceAccess 进 DSMEM API、local width
  overflow-safe、grid product overflow-safe、runtime 自动 event。
- 二轮修复（2026-08-12）：Context-unique nonce 授权 token、AccessKind
  绑定 capability、临界区 atomic_rmw（TSan 门禁）、logical 重推导 +
  非法枚举拒绝、event stop 语义、unsigned kMin/kMax 文档。
- codex 复核修复（2026-08-12）：capability 拆为完整 64 位
  context_nonce + launch_generation（无位宽截断）；generation 溢出
  kOutOfRange（不回绕）；debug_set_counters 测试钩子。
- codex 第三轮（2026-08-12）：generation exhaustion 检查提前 + RAII
  LaunchGuard（overflow 无泄漏/无 active state/backend 未调）；nonce CAS
  claim（永不回绕，exhaustion → kOutOfRange）；同 Context generation-
  advance 真重放（debug_set_backend）。
- codex 第四轮（2026-08-12）：NonceAllocator 可测试类（边界 + 多线程竞争）；
  generation 重放断言 kLifecycle。
- `cluster` CTest 23 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）、
  TSan（halt_on_error=1）全绿、零编译警告。Phase 3.5 **Closed / Pass**。

## Phase 4 完成记录（2026-08-12）

- Interpreter（interpreter.hpp/cpp）：per-lane ITS、BRA/BRX/JMP/JMX/EXIT/
  BSSY/BSYNC、S2R/S2UR、最小 ALU（MOV/IADD3/ISETP/IMAD）、指令上限/
  无进展/barrier deadlock、decode-only fault 定位。
- `interp` CTest 15 项（单/partial/full/multi-warp、BRA 循环、JMP/BRX、
  partial EXIT、@P0 per-lane guard、BSSY/BSYNC lane 汇合、指令上限、
  deadlock、连续 vs 逐步一致、非法 branch target）。
- codex 审阅修复（2026-08-12）：BRX/JMP/JMX dispatch、BSSY/BSYNC 真
  lane 汇合、round-robin 调度、per-lane guard exec_mask、kNoProgress
  移除、branch target 校验、barrier deadlock 分组报告。
- codex 复验第 2 轮（2026-08-12）：真 round-robin（展平 runnable group +
  rr_ cursor + 公平性测试）、BRX/JMX checked 算术（UBSan 边界）、
  validate_control_target 统一控制目标校验（BSSY OOB → fault）。
- codex 复验第 3 轮（2026-08-12）：BSYNC 真 lane 汇合（SyncEntry 四集合、
  exec_mask 到达、sync-wait 挂起、pending 清空后统一恢复 join、EXIT 移除
  退出 lanes、barrier register 匹配）；32-lane 双路径收敛测试。
- codex 复验第 4 轮（2026-08-12）：converge_completed_sync helper（收集
  完成索引→恢复→从大到小 erase，消除失效 iterator UB）；嵌套 BSSY 部分
  EXIT 测试（两层 entry 一次 EXIT 完成）。
- 普通 CTest 17/17、ASan+UBSan/TSan 全绿、零编译警告。
