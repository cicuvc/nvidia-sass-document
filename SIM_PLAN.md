# SM120 SASS 行为模拟器实施计划

## 1. 目标与边界

在 `semu/` 下实现一个 C++20 编写的 sm120 SASS 行为模拟器。模拟器加载标准 sm120 cubin，枚举其中的 kernel，按照 cubin 的 KPARAM 元数据装入任意参数，并通过 CPU interpreter 执行 kernel。

核心目标：

- 功能级、尽量位精确地模拟 sm120 SASS，不承诺周期精确。
- 支持标准 nvcc cubin 和本仓 assembler 生成的 cubin，包括多 kernel module。
- 提供稳定的 backend 接口；首个 backend 是 CPU interpreter，未来可增加 JIT。
- 支持 CTA 级 CPU 多核并行，以及用于调试和回归的确定性串行模式。
- 提供动态 warp 指令级单步调试、断点、watchpoint 和状态检查接口。
- 提供 shared-memory bank conflict、global-memory coalescing、LDGSTS/L1TEX 等 profiler。
- 内存系统显式分层：SM 内 L1TEX 使用 4-subcore serialization 模型，SM 间
  L2/显存交互使用 event-based 模型；两层不得合并成一个全局串行队列。
- 提供设备程序 data-race detector，至少覆盖 shared memory 与 global memory，
  报告冲突访问、字节范围、lane/warp/CTA/SM、PC 以及缺失的同步关系。
- 所有推测性硬件模型都携带适用范围和置信度，不把近似结果报告成精确计数。

首版明确不支持：

- device runtime、动态并行和 device `printf`。
- 未解析的外部 device function 调用。
- 纹理、surface、图形管线和其他非 compute 专用功能。
- 对错误 control code 所产生具体 stale register 值的周期级复现。

未实现但已能解码的指令不会阻止 module load 或 kernel launch；只有实际执行到该 PC 时才产生结构化 `UnsupportedInstruction` fault。CLI 的 inspection 功能会提前列出 kernel 中的 decode-only/unsupported 指令。

## 2. 总体架构

### 2.1 目录和构建

在 `semu/` 下建立独立 CMake 工程：

```text
semu/
  CMakeLists.txt
  include/semu/       公共 C++ API
  src/                cubin、decoder、runtime 和公共实现
  src/interpreter/    CPU interpreter backend
  src/debugger/       调试 session
  src/profiler/       profiler 和访存模型
  tools/              ISA 表生成工具
  tests/              unit/integration/golden tests
  cli/                semu 命令行程序
```

核心库不依赖 CUDA Driver/Runtime。Python 仅用于开发期从 `sm120.json` 生成 C++ ISA 数据；生成结果纳入构建输入，使普通用户构建 semu 时不需要重新解析原始 ISA dump。

### 2.2 稳定公共 API

公共对象边界如下：

- `Context`：拥有虚拟地址空间、加载的 module、backend 和运行配置。
- `Module`：已解析 cubin，可枚举和查找 kernel。
- `Function`：kernel text、metadata 和预解码指令。
- `DevicePtr`：模拟器虚拟地址，不能隐式转换为宿主裸指针。
- `KernelArg`：支持 `scalar<T>`、`device_ptr` 和任意 byte blob。
- `LaunchConfig`：grid、block、dynamic shared、worker 数、调度 seed 和指令上限。
- `LaunchResult`：完成状态、fault、统计、调试、profiler 和 data-race 结果。
- `IBackend`：消费不可变 module IR、launch request 和 runtime services。

`LaunchConfig` 提供独立开关 `memory_profile` 与 `race_detection`。race detector
至少支持 `off`、`report` 和 `fail-fast`；`report` 不改变程序值和调度，
`fail-fast` 在第一个确定 race 处产生结构化 simulator fault。未来 JIT backend
必须产生相同的规范化 memory/synchronization events，不能另建不兼容的检测器。

参数提供两种入口：

1. 根据 KPARAM ordinal/offset/size 逐项传入 `KernelArg`，并严格校验大小。
2. 直接传入完整 parameter byte buffer，支持大型结构体和尚不知道类型的参数。

cubin 元数据不能判断某个 8-byte 参数是整数还是指针，因此只有显式 `KernelArg::device_ptr` 才执行 allocation 生命周期检查。

### 2.3 指令 IR 与 backend 边界

`DecodedInstruction` 至少保存：

- 原始 128-bit instruction word 和 byte PC。
- mnemonic、encoding class/variant 和 pipe。
- guard predicate、typed operands、modifiers。
- schedule/control word：stall/usched、yield/batch、wait mask、read/write scoreboard。
- legality/ambiguity 状态和原始字段值。

interpreter、debugger、profiler 和未来 JIT 都消费同一 IR。语义 handler 不直接访问 interpreter 私有内存，而通过 register view、memory service、collective service 和 event sink 工作。

### 2.4 分层内存系统与事件边界

功能内存值、微架构排队模型和分析器分为三个层次：

1. `MemoryService` 是功能正确性的唯一权威，执行地址翻译、边界检查、原子操作和
   值提交；L1/L2 profiler 模型不得私自保存另一份可见内存值。
2. 每个 SM 建立 4 个稳定编号的 subcore issue stream。warp 在 CTA 生命周期内
   固定映射到一个 subcore；映射规则进入 model metadata。每个 stream 保持本
   subcore 的动态 memory-instruction 顺序，L1TEX 模型在四条 stream 之间做
   serialization/arbitration，不把整个 SM 或多个 SM 粗暴全序化。
3. L1 miss/writeback/atomic 等跨出 SM 的请求转化为 L2 events。L2 是跨 SM 的
   event-based 状态机：事件携带因果依赖和逻辑时间，可按确定性 tie-break 或指定
   seed 排序；首版不承诺逐 cycle 的 L2 pipeline/cache replacement 精度。

规范化 `MemoryEvent` 至少包含：event id、kernel/launch、SM/subcore/CTA/warp、PC、
active lane、address space、allocation id、每 lane byte range、load/store/atomic、
width、cache/operator modifier、atomic memory order/scope，以及对应的 L1/L2 parent
event。`SynchronizationEvent` 至少包含 barrier、mbarrier、fence、atomic、kernel
boundary 和它们的参与者/scope/epoch。Profiler 与 race detector 都只订阅这些事件。

## 3. Phase 划分

### Phase 0 — 工程骨架与基线冻结

#### 实现内容

- 建立 `semu/` C++20/CMake 工程和 CPU-only test target。
- 定义统一 `Status`、`Error` 和 `Fault`。
- Fault 包含 kernel、PC、CTA、warp、active mask、原始指令、decoded variant 和原因链。
- 建立 capability manifest，状态包括 `decode-only`、`functional`、`profiled` 和 `unsupported`。
- 记录 sm120 数据规模、参考 GPU/CUDA/driver 版本和现有验证测试清单。
- 建立 sanitizer 和可选 GPU differential 构建选项。
- 不修改仓库根目录现有未跟踪的 `sim.py`。

#### 验证方式

- CPU-only configure、build、CTest smoke test。
- `semu --version`、空 module 和非法命令行测试。
- capability manifest 重复生成 byte-identical。
- AddressSanitizer 和 UndefinedBehaviorSanitizer 构建通过。

#### 退出条件

- 没有 CUDA 环境也能构建并运行基础测试。
- 后续 backend、debugger 和 profiler 不需要改变公共错误模型。
- CI/本地命令能够分别运行 unit、integration 和 optional GPU tests。

### Phase 1 — ISA 数据生成与通用 decoder

#### 实现内容

- 增加 generator，从 `sm120.json` 生成紧凑 C++ ISA tables。
- 按 `{bit[91], bits[11:0]}` 的 13-bit opcode 建立 candidate index。
- 支持 enum、固定字段、slot、slot attribute、table function、immediate scale 和 schedule/control word 的逆向解码。
- 使用 discriminator、reserved bits、table membership 和 legality condition 区分共享 opcode 的 variants。
- 输出规范化反汇编文本，供 CLI、debugger 和错误信息使用。
- 无法唯一判定时返回所有候选及各候选失败/保留原因，不静默选择。

当前数据中 1414 个 variants 分布在 578 个 opcode 上；单个 opcode 最多有约 15 个候选，因此不能只依赖 mnemonic/opcode 映射。

#### 验证方式

- 检查全部 1414 variants 的字段宽度、范围、opcode index 和生成表完整性。
- 使用现有 assembler vectors 做 encode -> decode -> encode bit-exact round-trip。
- 使用现有 cuobjdump vectors 比较 mnemonic、variant、operand 和 modifier。
- 为 F2FP、F2I、BAR、CCTL、PLOP3/PSETP 等高重叠 opcode 建立专门歧义测试。
- 对有效编码随机翻转 reserved/discriminator bits，确认不会误匹配其他 variant。
- generator 连续运行不产生非确定性 diff。

#### 退出条件

- 所有已有测试向量可以唯一解码。
- 任意 128-bit word 只会得到唯一结果、明确非法结果或明确 ambiguous 结果。
- 所有执行 backend 均只依赖生成后的 IR，不需要自行解释原始 bitfield。

### Phase 2 — 标准 cubin loader

#### 实现内容

- 解析 ELF64 little-endian sm120 cubin 和 architecture flags。
- 支持 section/string/symbol table、多个 `.text.*`、`.nv.info*`、constant/shared/local sections 和常用 relocation。
- 解析 KPARAM ordinal/offset/size、regcount、static shared、barrier、exit offset 和 cluster metadata。
- 根据 symbol/section link 将 text、constant bank、shared section 和 per-kernel info 正确关联。
- module load 时预解码所有 kernel text，但保留 decode-only 指令。
- CLI 增加 `inspect`、`list-kernels` 和 `disasm`。

loader 面向原始 cubin，不负责从 fatbin 中选择 architecture image。

#### 验证方式

- 加载 assembler 生成的单 kernel cubin。
- 加载 nvcc 生成的多 kernel cubin，核对 kernel 数量、符号、text size 和参数布局。
- 与 `readelf`、`cuobjdump -elf/-res-usage` 输出逐字段对照。
- 覆盖截断 section、越界 offset、错误 ELF flags/architecture、损坏 symbol、未知 EIATTR 和 relocation failure。
- 未知但可跳过的 metadata 保留并告警；影响执行的未知 metadata 返回明确 fault。

#### 退出条件

- 能稳定枚举并反汇编普通 nvcc sm120 cubin 中的所有 kernel。
- assembler 与 nvcc 参数 metadata 都能转换为统一 `KernelMetadata`。
- loader 不链接或动态加载 CUDA Driver API。

### Phase 3 — 虚拟设备内存与 launch ABI

#### 实现内容

- 实现稳定的 64-bit 虚拟地址空间和 `DevicePtr`。
- 提供 `allocate/free/read/write/memset`，检查生命周期、越界和对齐。
- 建立 global、constant、shared 和 local address-space abstraction。
- allocation 使用稳定 `allocation_id + offset` 标识；事件和 race report 不依赖可
  重用的宿主地址。shared allocation 绑定 CTA，global allocation 绑定 Context。
- 支持逐项 `KernelArg` 和完整 packed parameter buffer。
- 按 sm120 ABI 将参数写入 constant0 对应 offset，并初始化已知 preset/special constant slots。
- 完成 `Context`、`Module`、`Function`、`LaunchConfig` 和 `LaunchResult` API。
- 定义 `IBackend`，interpreter 只能通过 runtime services 访问内存和事件系统。

#### 验证方式

- 1/2/4/8/16/128/256-byte 参数及混合对齐参数。
- 指针、标量、大型结构和零参数 kernel。
- OOB、use-after-free、double-free、错误参数数量和错误参数宽度。
- 转换 assembler `test_bigparam` 和 parameter-offset 用例为 CPU tests。
- packed buffer 与逐项参数生成的 constant0 内容完全相同。

#### 退出条件

- 任意 KPARAM byte layout 可以无损装入。
- 模拟地址在相同分配序列的不同宿主运行中保持确定性。
- future JIT 无需绕过 `Context` 或直接访问 interpreter 私有内存。

### Phase 3.5 — Cluster DSMEM 地址翻译（Phase 3 后置）

此阶段建立 cluster 内 distributed shared memory 的地址语义和 runtime ABI，供
Phase 4 interpreter 执行 shared-memory 指令时直接使用。Phase 3 的普通 per-CTA
shared allocation、domain 隔离与回收保持不变；DSMEM 是一条显式授权的跨 CTA
翻译路径，不能通过关闭 owner 检查或直接拼接模拟 VA 实现。

#### 地址与访问语义

- DSMEM 逻辑地址按 sm120 已验证形式解析：
  `target_cluster_cta_rank = address[31:24]`，
  `offset = address[23:0]`，即
  `(cluster_cta_rank << 24) + offset`。
- 在访问描述中增加显式模式，例如 `SharedAccessMode::kLocal` 与
  `SharedAccessMode::kDistributed`。普通 shared 指令始终选择当前 CTA；只有明确
  的 DSMEM 路径才解释地址高 8 bit。不得仅以 `address >> 24 != 0` 推断 DSMEM，
  因为 DSMEM rank 0 合法，而普通 shared offset 的高 8 bit 也可能为零。
- DSMEM 的 rank 是 cluster 内 rank，不是 grid-linear CTA id，也不是 Context 的
  allocation owner 序号。翻译结果显式保存 source CTA、target CTA、cluster id、
  target rank、allocation id、allocation offset 和最终 `DevicePtr`。
- source 与 target 必须属于同一 cluster；跨 cluster、rank 不存在、cluster 未启用、
  offset/range 越过目标 CTA shared window均返回结构化错误。普通 shared 的
  `source_domain == allocation.owner` 规则不变；DSMEM 经 cluster membership 验证后
  才允许 source domain 与 target owner 不同。
- load/store/atomic 使用同一翻译入口。atomic 继续服从 Phase 3 的 width、alignment、
  address-space 和 `AccessKind` 门禁，不建立绕过 typed memory service 的特殊路径。

#### Cluster 拓扑与 API

- 从 `KernelMetadata` 已解析的 cluster metadata 和 launch 配置建立稳定的
  `ClusterTopology`：cluster dimensions、cluster-linear id、cluster 内 CTA rank、
  grid-linear CTA id，以及每个 rank 对应的 `CtaSharedView`。
- 明确 cluster launch 的合法性：维度非零、乘积/映射 overflow-safe、cluster size
  不超过 sm120 capability、显式 cluster metadata 与 launch override 一致；尾部
  非满 cluster 是拒绝还是建模为 absent ranks，必须依据仓库 sm120 验证结果固定，
  未验证前默认结构化拒绝而不是猜测。
- 扩展 `BackendLaunchRequest`，向 backend 提供只读 cluster topology；禁止 backend
  通过 `shared_views` 顺序、地址差或 owner 字符串反推 rank。
- 在 `IRuntimeServices` 增加受控翻译/访问接口，例如
  `translate_shared(source_cta, logical_address, width, mode)`；返回稳定的
  `TranslatedSharedAddress`。后端只能用该结果或等价的 runtime read/write API，
  不得自行执行 `(rank << 24)` 解码后访问 allocator。
- shared allocation 生命周期覆盖整个同步 backend launch；所有 cluster/CTA view
  在 backend 返回后统一回收，成功、fault、early-stop 和 allocation rollback
  路径行为一致。

#### Event、race 与 profiler 边界

- 扩展 shared-memory basic event，至少记录 access mode、source/target cluster、
  source/target CTA、target rank、逻辑 DSMEM 地址、translated allocation id/offset、
  width、读写/atomic 和失败原因。
- race detector 以目标 shared allocation 的 byte range 建 shadow state，同时保留
  source CTA；同一 target byte 上的本地访问与远程 DSMEM 访问必须进入同一冲突域。
- cluster barrier、fence、mbarrier、atomic scope 对 DSMEM 的 happens-before 语义不在
  此阶段猜测；Phase 7 实现同步/race 规则，但 Phase 3.5 的事件必须携带足够身份和
  scope 信息，避免以后更改地址翻译 ABI。
- shared bank conflict 分析使用 target CTA 的 bank mapping；远程访问的额外网络/
  cluster fabric 成本留给 profiler 阶段单独建模，不混入普通 shared bank conflict。

#### 验证方式

- 纯 CPU translation golden：rank 0、当前 CTA rank、同 cluster 其他 rank，以及
  `offset = 0/1/0xfffffe/0xffffff` 的边界组合。
- cluster `(2,1,1)`、`(2,2,1)`、`(2,2,2)` 下逐 rank 映射；证明 rank 与 grid CTA
  id、owner domain id 相互独立，且不能通过 allocation VA 间距推导。
- 同 cluster 跨 CTA load/store 正向测试：source CTA 写入 target rank，target CTA
  本地读取相同 bytes；反向读写同样成立。
- 负向矩阵：cluster 未启用、rank 越界/absent、跨 cluster、offset OOB、
  `offset + width` 溢出或越界、misalignment、错误 address space、访问已回收窗口。
- DSMEM atomic 覆盖 1/2/4/8-byte 合法宽度，以及 16-byte/错误 scope 负向量。
- 明确证明普通 local shared access 不解析 rank bits；DSMEM rank 0 确实访问 cluster
  rank 0，而不是隐式访问 source CTA。
- event golden 同时断言 logical address、source/target CTA、allocation id/offset；
  race golden 覆盖本地与远程访问同一 byte 的读写/写写冲突。
- 将 `tests/asm_construct` 中 cluster/DSMEM 探针移植为硬件 differential：对照目标
  CTA 最终 shared/global 可观测结果。若硬件结果与 `rank<<24|offset` 边界规则冲突，
  以实测更新模型并在文档中保留差异。

#### 退出条件

- backend 不做地址算术即可对任意合法 cluster rank 完成 DSMEM load/store/atomic。
- 所有非法 rank、跨 cluster、OOB、alignment 和 lifecycle 情况在访问目标内存前
  结构化失败，且不会退化为普通 shared access。
- 普通 shared domain isolation 门禁保持全绿；DSMEM 只通过显式 cluster 授权跨 CTA。
- translator、event 和 race identity 使用稳定 `allocation_id + offset`，不依赖
  owner 字符串、宿主地址或 shared allocation 的相邻关系。
- 普通、ASan+UBSan 和硬件 differential 门禁全部通过后，Phase 4 才把 DSMEM
  指令语义接入 interpreter。

### Phase 3.5 完成记录（2026-08-12，`semu/GAP_PHASE3_5.md`）

- DSMEM 地址语义：`(rank << 24) | offset`（sm120 实测）；`SharedAccessMode`
  显式 kLocal/kDistributed，普通 shared 不解析 rank bits。
- `ClusterTopology`：cluster dims + grid 构建，非零/overflow/cap(8)/尾部
  部分 cluster 拒绝；rank 与 grid CTA id、owner 序号独立。
- `IRuntimeServices::translate_shared` + `read_shared`/`write_shared`：
  backend 唯一 DSMEM 通道；翻译结果携带 source/target CTA、cluster id、
  rank、logical address、allocation id+offset、DevicePtr。
- `BackendLaunchRequest::cluster` 只读 topology；active-launch 状态在
  backend 调用期间有效，返回后清理回收（成败一致）。
- `BasicMemoryEvent` 扩展 DSMEM 身份字段（mode/source/target/rank/logical/
  allocation id+offset）。
- `cluster` CTest 13 项（翻译 golden、3D 拓扑映射、跨 CTA roundtrip、
  负向矩阵、local-vs-DSMEM、rank0 语义、event golden、真 atomic RMW、
  伪造翻译矩阵、跨 Context 拒绝、自动 event）。
- 初验修复（2026-08-12）：3D cluster tile 映射（逐轴整除、双向）；
  launch_generation 令牌 + 全身份重验证（伪造/过期/跨 Context 拒绝）；
  真 DSMEM atomic RMW；DeviceAccess 进 DSMEM API（alignment/space/kind
  门禁）；local width overflow-safe；grid product overflow-safe；
  runtime 自动 event。
- 二轮修复（2026-08-12）：capability token 加 Context-unique nonce
  （跨 Context 重放拒绝）；AccessKind/alignment/space 绑定 capability
  （交叉复用拒绝）；MemoryAllocator 临界区 atomic_rmw（多线程精确计数 +
  TSan 门禁）；logical_address 重推导验证 + 非法枚举拒绝；event stop
  语义明确（提交后事件 + event_stopped() 查询）；kMin/kMax 明确 unsigned。
- codex 复核修复（2026-08-12）：capability 拆为完整 64 位
  context_nonce + launch_generation（无位宽截断）；generation 溢出返回
  结构化错误（不回绕）；受控 counter 注入测试覆盖 nonce ≥ 2^32、
  generation UINT64_MAX 边界、跨 launch 失效。
- codex 第三轮（2026-08-12）：generation exhaustion 检查提前 + RAII
  LaunchGuard 统一清理（overflow 无泄漏/无 active state/backend 未调）；
  nonce CAS claim（UINT64_MAX → kOutOfRange，永不回绕）；同 Context
  generation-advance 真重放测试（debug_set_backend）。
- codex 第四轮（2026-08-12）：NonceAllocator 抽为可测试类（claim 真实
  边界 + 多线程竞争恰好一个成功）；generation 重放测试断言 kLifecycle
  错误码。
- 修复：read/write_shared value-copy 写丢失（→ read_at/write_at）；
  空参数 launch 的 nullptr memcpy UB。
- 普通 CTest 16/16、ASan+UBSan（halt_on_error=1）全绿、零编译警告。

### Phase 4 完成记录（2026-08-12）

- Interpreter：`include/semu/interpreter.hpp` + `src/interpreter.cpp` —
  每 thread（GPR/P0..P6/lane PC/exit/fault）、每 warp（UR/UP0..UP6/
  BSSY-BSYNC sync stack/active mask）、每 CTA（shared memory/warp 列表/
  named barrier）。
- per-lane PC independent thread scheduling：next_group 选同 PC lane group
  执行一条动态 warp instruction；多 warp CTA 逐 warp 调度。
- 控制流：guard predicate、BRA（`pc+16+sImm*4`，56-bit 位移）、BRX/JMX
  （Ra+Ra_offset）、JMP（Sa*4 绝对）、EXIT（含 @P0 部分退出）、BSSY/BSYNC
  （sync-stack 压栈/弹栈汇合）、自然汇合。
- S2R/S2UR special registers：TID/CTAID/NTID/NCTAID/LANEID/WARP/SMID
  （硬件编码值实测：SR_LANEID=0、SR_TID.X=33、SR_CTAID.X=37）。
- 最小 ALU：MOV/IADD3/ISETP（ICmpAll dstfmt）/IMAD，支撑控制流 kernel。
- 动态指令上限（kInstructionLimit）、无进展检测（kNoProgress）、barrier
  deadlock（kBarrierDeadlock，含参与 warp 数 + barrier id）。
- decode-only 指令实际命中 → Fault(kUnsupportedInstruction) 带 kernel/
  pc/warp/active-mask/instruction 定位。
- 验证：`interp` CTest 15 项 —— 单 lane/partial warp/full warp/多 warp
  CTA、S2R TID、BRA 循环、JMP 绝对/BRX 寄存器间接、partial EXIT 分歧、
  @P0 MOV per-lane guard、BSSY/BSYNC lane 汇合、指令上限、barrier
  deadlock（按 CTA+barrier 分组报告）、连续 vs 逐步一致
  （`step_consistent`）、decode-only 定位、非法 branch target fault。
  普通 CTest 17/17、ASan+UBSan/TSan 全绿、零编译警告。
- codex 审阅修复（2026-08-12）：BRX/JMP/JMX dispatch（原缺失）；
  BSSY/BSYNC 真 lane 汇合（SyncEntry 记 reconverge target + 参与 lane
  集合，lazy reconvergence）；round-robin 调度器（CTA/warp cursor 防
  饿死）；per-lane guard 过滤 executing_mask（同-PC lane 全部推进 PC、
  @P0 分歧测试）；kNoProgress 移除（无限循环只由 instruction limit 终止，
  不再误分类）；branch target 校验（16 对齐/在 text 内/溢出）；
  barrier deadlock 按 (CTA, barrier id) 分组报告 arrived/waiting/exited。
- codex 复验第 2 轮修复（2026-08-12）：真 round-robin（展平 runnable
  (cta,warp,pc-group)、rr_ cursor、公平性测试验证低-PC group 无限循环时
  其他 group 仍执行）；BRX/JMX checked 算术（checked_mul4/checked_add，
  INT64_MIN/MAX 边界测试 UBSan 下无 UB）；`validate_control_target` 统一
  供 BRA/BRX/JMP/JMX/BSSY 共用（BSSY OOB join target → kInvalidInstruction）。
- codex 复验第 3 轮修复（2026-08-12）：BSYNC 真 lane 汇合 ——
  `SyncEntry` 增加 barrier_register + participating/pending/arrived lane
  集合；BSYNC 只处理当前 exec_mask 到达的 participating lanes，先到 lanes
  进 sync-wait 挂起（不推进），全部 pending 到达后统一恢复 join PC
  （reconverge_pc+16）；EXIT 从 pending 集合移除退出 lanes 并可能触发
  完成；调度器保留 sync-wait warp 不误标 done。32-lane 双路径测试：
  @P0 走路径 A 写 R2、@!P0 走路径 B 写 R3，汇合后两组都保持各自值且都
  到达 join（R4=4）。
- codex 复验第 4 轮修复（2026-08-12）：`converge_completed_sync` helper
  消除 do_exit 删除 sync entry 后的失效 reverse_iterator —— 先收集所有
  pending==0 的 entry 索引，统一恢复 participating lanes 到 join，再按
  索引从大到小安全 erase（多 entry 同时完成时无 UB）。测试
  `interp_nested_bssy_partial_exit`：两层嵌套 BSSY（B0 outer/B1 inner），
  lanes 0-15 EXIT 完成 inner entry（释放已到达的 16-31）、16-31 依次经过
  内外 BSYNC 到 R4=4；ASan/UBSan 下无 iterator 失效。

### Phase 4 — Interpreter 执行核心与控制流

#### 实现内容

- 每 thread 保存 GPR、predicate、lane PC、local state 和 exit/fault state。
- 每 warp 保存 UR、uniform predicate、barrier/convergence 和 collective state。
- 每 CTA 保存 shared memory、warp 列表、named barrier 和调度状态。
- 使用 per-lane PC 表达 independent thread scheduling。
- 每次选择一个同 PC lane group，执行一条动态 warp instruction。
- 实现 guard predicate、BRA/BRX/JMP/JMX、EXIT、BSSY/BSYNC 和自然汇合。
- 实现 S2R/S2UR 所需 thread/block/grid/lane/warp special registers。
- 加入动态指令上限、无进展检测和 barrier deadlock detection。
- decode-only 指令只有实际命中时才返回 `UnsupportedInstruction`。

#### 验证方式

- 单 lane、partial warp、完整 warp、非 32 倍 block 和多 warp CTA。
- if/else、nested branch、loop、partial EXIT、BSSY/BSYNC。
- 对照 `test_bssy_bsync`、`test_brx`、`test_jmp`、`test_jmx`、`test_s2r` 和 `test_s2ur`。
- 连续运行与逐条执行的最终状态一致。
- 无限循环由 instruction limit 终止；错误 barrier 由 deadlock detector 给出参与者和等待原因。

#### 退出条件

- 常规控制流 kernel 可以运行到 EXIT。
- active mask、lane PC 和 reconvergence trace 与硬件验证笔记一致。
- fault 总能定位到动态 warp 指令和参与 lane。

### Phase 5 — 常规计算指令语义

#### 实现内容

- MOV/LDC/LDCU、整数算术、carry、bit operation、shift、permute、comparison 和 predicate。
- FP16/BF16/FP32/FP64、FMA、conversion、rounding、SAT、FTZ/FMZ。
- vote、shuffle、elect、redux 等 warp collective。
- 统一 typed operand access，处理 RZ/URZ、register group、immediate、constant operand、negate 和 absolute。
- FP 路径显式处理 +/-0、subnormal、NaN、Inf 和 NVIDIA 特殊值规范化。

优先覆盖普通 nvcc compute kernel，tensor/TMA 延后到 Phase 9。

#### 验证方式

- 每个实现 mnemonic 至少有一个独立语义测试。
- 每个实现 variant/modifier 至少有 decode/operand test。
- 复用 `tests/asm_construct` 的整数、FP、conversion、predicate、vote/shuffle 用例做 GPU differential。
- 随机 operand fuzz：相同 cubin 和参数分别在 GPU 与 semu 执行，逐 word 比较。
- FP 覆盖边界值和全部 rounding/flush modifier。

#### 退出条件

- 常规无内存计算 kernel 达到 bit-exact differential。
- 每个 `functional` capability 都有成功、边界和非法输入测试。
- 不使用未初始化值伪装未实现语义；未实现路径必须 fault。

#### 完成记录（2026-08-13）

- **解释器 compute 语义**：新增 `do_compute` 按 mnemonic 分发的整数/bit、FP、
  conversion、compare、collective 处理器，以及统一 typed operand access
  （`inst.operands` slot/值/negate/absolute、`inst.slot_values` modifier 值，
  decoder 在 render 阶段填充）。新增 `fp.cpp`（host IEEE + fenv 位精确引擎）。
- **已实现 mnemonic（29）**：FFMA、FADD、FMUL、DADD、DMUL、DFMA、F2F、F2I、
  I2F、FSETP、FSET、FMNMX、FSEL、FRND、LOP3、LOP、SHF、IABS、IMNMX、
  ISCADD、LEA、POPC、FLO、BFE、BMSK、BFREV、PRMT、P2R、VOTE、SHFL、ELECT、
  REDUX（含 IMAD.WIDE/HI、IADD3 全变体、MOV UR 源、ISETP bop/Pv）。
  未实现路径（MUFU/FCHK 等硬件近似表）仍走 `do_unsupported` fault。
- **关键经验发现（GPU 实测 sm_120）**：
  - FP32 算术 NaN 结果规范化到 `0x7fffffff`（正 quiet NaN 全 1 payload）；
    FP64 保留输入 NaN（两个 NaN 时取第二个操作数）。
  - FFMA/FMUL 用 `fmz` slot（FTZ=2），FADD 用 `ftz`；FMZ 同时 flush a/b/c
    三个输入（符号保留），denormal/zero 结果按 RN/RP/RZ→+0、RM→加数符号。
  - SHF.L/.R 的 hilo 决定移位来源（LO 值在 Ra、HI 值在 Rc），LO 的 funnel
    fill 只在 `.R` 出现。
  - F2F 的 BF16/F16 源在寄存器低 16 位；`dstfmt.srcfmt` 是合并编码。
  - LOP3 LUT 索引 = `(a<<2)|(b<<1)|(c<<0)`（a 是 MSB）。
  - FSETP 的 Pv = `(!cmp) BOP Pp`（不是 `!Pu`）。
  - VOTE.ANY Rd 是 ballot mask；SHFL 越界保留本 lane 值；REDUX/ELECT 写 UR。
- **验证**：`tools/diff_phase5.py` 80/80 GPU vs semu 逐 word 一致（覆盖
  FP rounding/FTZ/FMZ/SAT、F64、conversion、compare、min/max、整数、VOTE/
  SHFL/ELECT/REDUX）；`tools/fuzz_phase5.py` 随机 operand fuzz 5 seed ×
  225 = 1125/1125 通过（含 denormal/±0/subnormal/NaN/Inf 边界）；CTest 17 项
  全过（interp 增至 24 个 TEST，含 4 个 compute 语义测试）；ASan/UBSan/TSan 干净。
- **CLI**：新增 `semu run <cubin> <kernel> <grid.x> <block.x> [...]` 命令，
  执行 kernel 并 dump 每 lane GPR JSON（differential harness 的 semu 侧）。

#### Codex 审阅修复（2026-08-13，2 High + 2 Medium 全关）

- **High-1** — FP16 subnormal directed rounding：重写 `f32_to_f16`，补全
  RN ties-to-even/RM/RP/RZ 与完整 discarded-bit accounting（normal 13-bit
  shift、subnormal `m = M*2^(E-126)`、overflow→inf/max-finite、subnormal→
  smallest-normal 进位）。GPU differential 新增 80 个 FP16 边界向量
  （2^-14/2^-24 附近 × 4 rounding × 双符号），全部逐 word 一致。
- **High-2** — fuzz 门禁：非 GPU 模式不再自动 PASS——每个 case 用独立 host
  reference oracle（numpy float32 + fenv 位精确，独立于 C++ fp.cpp）校验，
  无 reference 且无 GPU 的 case 标记 SKIP（不计数为 PASS）；输出 JSON report
  记录 gpu/seed/case count；新增 CTest 验收 target `fuzz_phase5`
  （reference fuzz + mutation gate + report 键检查）；新增 `--mutation`
  模式（翻转 semu 结果 word 低位，门禁必须检出 108/108）。
- **Medium-1** — fenv 编译契约：`fp.cpp` 声明 `#pragma STDC FENV_ACCESS ON`
  （仅 Clang，GCC<13 会 warning）+ `-frounding-math`（`set_source_files_properties`
  只对 fp.cpp）；新增 `RoundingGuard` RAII（异常/早退也恢复 fenv），全部
  push/pop 改为 guard；新增 `semu_test_fp` 验证每种 rounding mode 产生不同
  last bit 且 guard 恢复宿主 rounding。
- **Medium-2** — 覆盖补齐：diff 新增 F64 conversion（I2F.F64/F2F.F64.F32/
  F2F.F32.F64）、IMAD.HI/.WIDE 大乘积（signed 语义）、DFMA rounding 边界、
  BMSK/LEA/P2R 变体、FP16 subnormal directed rounding；MUFU 和 FCHK 各自独立
  runtime fault 测试（断言 UnsupportedInstruction kind、pc=0、message 含
  mnemonic）。修复过程中发现并修正：`std::bit_cast<double>(double)` 在
  GCC-12 + `-frounding-math` 下被误编译为 0（改用 `bit_cast<uint64_t>(double)`）、
  IMAD WIDE/HI 用 variant_class 区分（mnemonic 均为 "IMAD"）、IMAD.HI 取
  high32、IMAD signed 语义、BMSK position/width 语义、LEA `scaleU5` + hilo、
  FSETP U-variant unordered-true-on-NaN。
- **验证（最终）**：`diff_phase5.py` 191/191（189 differential + 2 fault）；
  `fuzz_phase5.py` 5 seed × 108 GPU + 2 seed 非 GPU 全过、mutation 108/108
  检出；CTest 19 项全过（+fuzz_phase5 +fp）；ASan/UBSan 干净；repo 的
  asm_construct GPU 测试 10/10 无回归。

#### Codex 复验第 2 轮修复（2026-08-13，2 High 全关）

- **High-1 — IMAD.WIDE/HI 符号扩展 + signed overflow UB**：
  1) 32×32 signed/unsigned 乘积先得到 64 位 bit pattern（signed 模式把两个
     32 位输入符号扩展到 int64，`|int32|^2 ≤ 2^62` 不溢出；unsigned 用
     uint64 宽度）；2) addend 始终使用完整寄存器对（不再根据低半 bit31
     重新符号扩展——`c=0x00000000ffffffff` 不会被错误覆盖成 `-1`）；
     3) `prod + c` 全部用 `uint64_t` modular 加法（无 signed overflow UB）；
     4) HI 取最终 64 位结果高 32 位；5) 新增 diff 回归向量：高半非符号扩展
     形式、低半 bit31=1、大 addend wraparound（`0xffffffff×0xffffffff+
     0xffffffffffffffff`）、signed 低半符号位与真实符号不同；全部 GPU 一致。
     6) IMAD.X/WIDE.X/HI.X（carry-in `[!]Pp` + carry-out `Pu` + `[~]Rc`）Phase 5
     未实现，改为**显式降级为 unsupported**（do_imad 检测 `_x` variant_class
     后 fault），避免静默丢弃 carry 产生错误结果；diff 新增 IMAD.X 与
     IMAD.WIDE.X 两个 runtime fault 测试。
- **High-2 — mutation gate 过弱**：`run_mutation()` 现在返回
  `(detected, total, errors)`；semu 自身 fault/error **不再计入 detected**
  （避免 harness/runtime 故障掩盖 gate 失效，单独计 errors）；退出条件改为
  `total > 0 && detected == total && errors == 0`（仅 ≥1 检出不再通过）；
  新增 `/tmp/fuzz_phase5_mutation.json`（detected/total/errors/skipped）；
  CTest wrapper 解析该 JSON 明确断言 `detected == total` 且 `errors == 0`。
  修复过程中发现并修正 run_mutation 写错 cubin 路径（写 `/tmp/fz_mut.cubin`
  但 run_semu 读 `/tmp/fz_semu.cubin`，导致全部误报 semu error）。
- **验证（第 2 轮最终）**：`diff_phase5.py` 200/200（196 differential +
  4 fault：MUFU/FCHK/IMAD.X/IMAD.WIDE.X）；mutation 108/108 detected、
  0 errors（退出码与 JSON 双重校验，且逻辑上 missed/error/empty 均拒绝）；
  fuzz GPU 2 seed × 90 + 非 GPU 1 seed × 63 全过；CTest 19/19；ASan/UBSan
  干净；repo asm_construct GPU 测试 11/11 无回归。

#### Codex 复验第 3 轮修复（2026-08-13，1 Blocker 全关）

- **Blocker — F64→F32/F16/BF16 经 FP32 中间值导致双舍入**：原实现
  `static_cast<float>(f64)`（宿主默认 RN，无 RoundingGuard）后再转 F16/BF16，
  存在 double rounding、忽略 directed rounding、不处理 F64 NaN payload/
  subnormal/overflow。新增三个**直接 bit-pattern 转换** `f64_to_f32` /
  `f64_to_f16` / `f64_to_bf16`（fp.cpp `f64_down_round` 共享实现）：直接从
  F64 sign/exponent/53-bit significand 按目标精度（f16 10-bit frac/bias 15、
  f32 23-bit/bias 127、bf16 7-bit/bias 127）做 directed rounding，禁止经
  FP32 中间值。覆盖：正常/overflow→inf-or-max-finite、subnormal（含
  ties-to-even 到 smallest normal 进位）、RN/RM/RP/RZ、F32 NaN payload
  保留（`sign + 0x7f800000 + (payload>>29)|0x400000`，验证
  `F32.F64(0x7ff123456789abcd)→0x7fc91a2b`）、F16/BF16 NaN/inf 低 16 位
  sign bit15、FTZ 输出 flush。
- **发现并修复的附带 bug**：subnormal 路径 `1ULL << (m_shift-1)` 在
  `m_shift ≥ 64` 时是移位 UB（GCC 截断 `%64` 得到错误 half 导致 2^-127 被
  误舍入为 1）——carry 决策对 `shift ≥ 64` 直接返回 false。
- **验证**：GPU 差分新增 22 个 F64 边界值 × 3 目标 × 5 rounding = 大量
  向量（double-rounding trap 值 `0x3ff0020008000000` 等：direct F16 RN=
  0x3c01 而经 FP32=0x3c00、NaN payload、2^-127 subnormal→0、f32max±、
  f64max overflow、±0/±inf/NaN），全部逐 word 一致；diff_phase5 扩展到
  452/452（448 differential + 4 fault）；fuzz 新增 `gen_f2f64_cases` +
  Python `ref_f2f64`（精确整数舍入，独立于 C++），GPU/非 GPU 全过；
  新增 `fp_f64_to_narrow_direct` CTest 锁定 double-rounding 与 directed
  rounding；CTest 19/19、ASan/UBSan 干净、repo asm_construct 无回归。
- **验证（第 3 轮最终）**：`diff_phase5.py` 452/452；fuzz GPU/nonGPU +
  mutation 108/108 (0 errors)；CTest 19/19；ASan/UBSan 干净。

#### Codex 复验第 4 轮修复（2026-08-13，1 High 全关）

- **High — .SAT 的 NaN 语义错误且测试门禁未覆盖**：GPU 实测 sm120 的 SAT
  语义：clamp 到 [0,1]，NaN → +0、+inf → 1.0、-inf/-1 → +0、>1 → 1.0、
  ±0 → +0、0.5/1.0 原样通过（FADD/FMUL/FFMA 全一致；inf+(-inf) 生成 NaN
  同样 → +0）。修复：
  1) `sat_f32`/`sat_f64` 显式处理 `isnan()`（NaN → +0）与 `-0` 规范化
     （`f == 0.0` → +0），替换原 `f<0?:f>1?` 的 NaN 原样返回 bug。
  2) `fadd`/`fmul`/`ffma`/`fadd64`/`fmul64`/`fma64` 的 NaN 早退分支改为
     `sat ? 0 : kCanonicalNan`；`f64_down_round` 的 NaN/Inf/overflow 早退
     也应用 sat（NaN → +0、±inf → 1.0/+0、溢出 → 1.0/+0，仅 F32 目标）。
  3) GPU differential 新增 .SAT 用例：NaN、±inf、-1、±0、0.5、1、>1、
     inf+(-inf)→NaN，覆盖 FADD/FMUL/FFMA；fuzz 的 FFMA/FADD/FMUL 生成器
     加入 `.SAT` modifier + Python `sat_ref` 参考（NaN→0、-0→+0），非 GPU
     与 GPU 双模式校验。
- **验证（第 4 轮最终）**：`diff_phase5.py` 484/484（480 differential +
  4 fault）；fuzz GPU/nonGPU + mutation 108/108 (0 errors)；CTest 19/19
  （含新增 `fp_sat_special_values`）；ASan/UBSan 干净；repo asm_construct
  无回归。

#### Codex 复验第 5 轮修复（2026-08-13，1 High 全关）

- **High — f64_down_round() 部分提前返回绕过 SAT**：三处有限值出口未应用
  sat_final：1) `exp==0 && frac==0` 直接 `return sign_bit()`（F64 -0 → F32
  0x80000000 而 SAT 契约要求 +0）；2) mantissa 舍入进位后 `(ef+1)<<frac_bits`
  直接返回（最大小于 2 的 F64 `0x3fffffffffffffff` RN 舍入为 F32 2.0 直接
  返回，SAT 应 clamp 到 1.0）；3) subnormal 向 smallest-normal 进位直接返回。
  修复：新增 `sat_final` target-format finalize helper（sat 且 F32 目标时对
  最终位模式应用 `sat_f32`：+0 规范化、>1→1.0、NaN→+0），并统一应用到
  零、mantissa-carry、subnormal→smallest-normal 及所有正常/subnormal 出口
  （overflow/NaN/±inf 早退第 4 轮已处理）。
- **验证**：新增 `fp_f64_to_f32_sat_finalize` CTest 覆盖 -0→+0、最大<2.0
  F64 RN→F32 2.0（nosat）vs 1.0（sat）、±1/±inf/NaN/+0/0.5 在 SAT 下的
  语义；diff_phase5 484/484、fuzz GPU/nonGPU + mutation 108/108、
  CTest 19/19、ASan/UBSan 干净、repo asm_construct 无回归。

### Phase 5.5 — 快速解释器执行引擎（Fast Interpreter）（Phase 5 后置）

**状态**：实现完成（2026-08-13，M0–M5 全部落地，见 /tmp/phase55_plan.md 与 semu/PHASE55_FAST.md）

#### 目标与非目标

在不复制 decoder、线程状态、调度器和控制流实现的前提下，为 CPU interpreter 增加性能优先的计算语义模式。浮点结果允许与 sm_120/Phase 5 精确模式不同，但控制流、predicate、整数语义、barrier、fault、instruction limit、step/debugger 状态和内存可见性的契约不变。非目标：不做 JIT、SIMD lane vectorization、memory hierarchy、tensor/MUFU/FCHK；不通过全局 `-ffast-math` 改变 precise 语义。

#### 架构（codex 设计结论 + 实现）

- **不建独立 `FastInterpreter`**（避免复制 Phase 4 状态机/控制流），**不做整体模板化**（编译面和 API 复杂化）。
- 保留唯一 `Interpreter`（状态机、调度器、控制流、fault/trace/step 全部复用），通过 **`ExecutionMode` + `FastFpFallback` policy** 切换计算叶节点。实现不做 `FpSemantics` 虚基类/虚函数，而是把 mode/fallback 决策收敛到统一入口：
  - 算术/转换叶：`plan_fp32()` / `plan_fp64()` 每条指令解析一次（`use_fast`/`need_exceptional`/`ignored_modifier`），lane 循环按计划直调 fast 或 precise helper；
  - 计数：统一 `note_fast_leaf(approximate_result)` 覆盖所有 FP 叶（`fast_fp_ops`/`any_fast_fp`），fallback 走 `precise_fallback_ops`；
  - 共享-native 叶（FRND/FMNMX/FSEL/FSETP/FSET）直接走 host 原生运算（两模式位一致），仅计数不置 approximate。
- 新增 `include/semu/execution.hpp`（ExecutionMode、RunOptions、FastFpFallback）、`include/semu/fast_fp.hpp`、`src/fast_fp.cpp`。
- 模式不得改变 opcode 支持集合：precise 中 unsupported 的 MUFU/FCHK 在 fast 中同样 fault。

#### 快速 FP 策略

- 宿主 `float/double/std::fma` 直接计算；整次 run 最多设一次 `FE_TONEAREST`（run-scope RAII 恢复），**禁止逐指令 RoundingGuard**。
- `.RM/.RP/.RZ`：默认按 RN 执行并记录 `ignored_directed_rounding` 计数，不伪装位精确。
- FTZ/FMZ：默认不模拟逐输入/结果符号细节；SAT 用低成本显式 clamp（NaN/-0/negative→+0、>1/+Inf→1）。
- NaN/Inf/subnormal/signed zero：native 语义，不保证 payload/规范化；特殊值或精确需求走 fallback。
- **fallback 策略** `RunOptions::fast_fp_fallback`：`kNone`（最快）/ `kExceptional`（NaN/Inf/subnormal 或非 RN/FTZ/FMZ 时调 precise helper，API 默认）/ `kStrictModifiers`（仅非 RN/FTZ/FMZ 和精确 NaN payload fallback）。fallback 判定按 lane 完成，不允许整次 launch 重跑；Result 记录 `fast_fp_ops`/`precise_fallback_ops`/`ignored_modifier_ops`。

#### 指令路由矩阵

| 类别 | Fast 处理 | 契约 |
|---|---|---|
| 整数/bit/predicate（MOV/IADD3/IMAD/ISETP/LOP3/SHF/…）| 复用现有 handler | 位精确 |
| 控制流/同步（BRA/BSSY/BSYNC/BAR/S2R/S2UR）| 原状态机 | 与 precise 一致 |
| FADD/FMUL/FFMA、DADD/DMUL/DFMA | fast_fp host 运算 | RN 近似；modifier/特殊值按 policy |
| F2F/I2F | host cast + 简化 pack | 不保证 directed rounding/payload/double-rounding，除非 fallback |
| F2I | checked host conversion | NaN/Inf/越界必须 precise 饱和 helper，**禁止 UB 裸 cast** |
| FSETP/FSET/FMNMX/FSEL | native compare/select | predicate 结果尽量精确；保留 unordered truth table |
| VOTE/SHFL/ELECT/REDUX | 复用 collective | lane membership/ballot 完全一致 |
| MUFU/FCHK、未实现 variant | 与 precise 相同的 kUnsupportedInstruction | 不得返回伪结果 |

#### API 与 CLI

```cpp
enum class ExecutionMode { kPrecise, kFast };
enum class FastFpFallback { kNone, kExceptional, kStrictModifiers };
struct RunOptions { ExecutionMode mode = kPrecise; FastFpFallback fast_fp_fallback = kExceptional; ... };
static Result run_result(const Kernel&, const LaunchEnv&, const RunOptions& = {});
```
- 旧 overload 保留转发 precise；Result 新增 `execution_mode`/`fast_stats`/`approximate`。
- CLI：`semu run [--precise|--fast] [--fast-fallback=none|exceptional|modifiers] [--instruction-limit=N] <cubin> <kernel> ...`；`--fast` 默认 fallback none；fast-only 参数用于 precise 报 usage error；JSON 只增字段保持兼容。

#### 性能目标（Release 基准，median）

- FP arithmetic-heavy（fallback none）：相对 precise **≥2.0x**（stretch 3–5x）
- mixed compute：**≥1.3x**
- integer-only：不慢于 precise 5%
- exceptional fallback：不比 precise 慢 15% 以上，报告 fallback rate
- 基准：预热 3 次 + 正式 15 次，AB/BA 交替，报告 median/p10/p90、ns/dynamic-inst、M inst/s；校验退出状态 + dynamic instruction count + 控制流 fingerprint 防假加速。

#### 测试策略

1. 完全相等集合（整数/bit/控制流/collective membership/fault/instruction count/lane exit/PC）precise/fast 必须一致
2. 普通有限 FP：RN 按类型比较（FP32 rtol=2e-6 atol=1e-7、FP64 rtol=1e-12 atol=1e-15、F16/BF16 1–2 ULP）
3. 非 RN/FTZ/FMZ：fallback 模式与 precise bit-equal；none 模式只要求不 fault + ignored counter 增加
4. NaN/Inf/subnormal/signed zero：比较类别而非 payload
5. F2I 安全边界：NaN/±Inf/min/max±1/U32 negative 与 precise 一致（无 UB）
- 回归：Phase 4 控制流测试参数化双 mode 全等；Phase 5 exact/diff_phase5 不传 mode 证明默认 precise；fast 专属 unit tests + mutation test + sanitizers。
- Phase 5.5 **不新增 GPU differential**（GPU evidence 由 precise Phase 5 维护）。

#### 实施里程碑

- **[x] M0**：冻结 5 个 benchmark kernel（FP32 FFMA 链 / FP64 DFMA+F2F 混合 / 多 warp divergence+FP / integer-only / exceptional-heavy），benchmark runner + JSON schema，记录 precise 基线（CV<10%）
- **[x] M1**：ExecutionMode/RunOptions/Result metadata + CLI --fast（fast 暂时全走 precise）；现有 19 CTest 无修改通过，precise/fast 全状态 bit-equal
- **[x] M2**：fast_fp.cpp 实现 FADD/FMUL/FFMA/DADD/DMUL/DFMA native RN + SAT + run-scope RN + counters/fallback；FFMA/DFMA microbench ≥2x；caller fenv 成功/fault 后都恢复
- **[x] M3**：F2F/I2F/F2I/FSETP/FSET/FMNMX/FSEL/FRND 路由；F2I checked range/fallback；directed/FTZ/FMZ 计数完整
- **[x] M4**：全 interpreter 集成；step/run_shared/trace 接收 options；控制流测试双 mode；MUFU/FCHK 仍 fault
- **[x] M5**：profile 收敛（mode branch/operand decode/函数指针开销，按数据预绑定）；CLI/API 文档 + 限制表

**实测性能（Release，32-lane warp，median）**：FFMA **2.05x**、DFMA+F2F mixed **1.32x**、
divergence+FP **1.83x**、integer-only **1.00x**（无回退）、exceptional-heavy **1.55x**。
M5 通过 Fp32/Fp64Plan 预解析 + operand 预绑定 + 指令级 policy 提升把 FFMA 从 1.38x 提升到 2.05x。
benchmark runner：`semu_bench_fast_interp`（每次 timed run 校验 fault/dynamic-count/控制流
fingerprint）；用户指南/限制表：`semu/PHASE55_FAST.md`。

**codex 审阅修复（2026-08-13）**：Blocker-1 fast_i2f 按 srcfmt 符号扩展；High-2 kExceptional
同时检查 native 结果；High-3 F64 conversion 用 double 分类；High-4 note_fast_leaf 统一计数覆盖
全部 FP 叶；Medium-5 bench fingerprint + 参数 off-by-one；Medium-6 pred[7] OOB/补 conversion
kernel/fast-step FP leaf/31-1 fallback mix；Medium-7 统一 fast dispatch 入口 + 如实文档；
Medium-8 fenv guard int 类型 + 失败检查 + 仅 fast 模式。修复后 CTest 19/19、diff 484/484、
fuzz 110/110、mutation 108/108、ASan/UBSan 全绿。

**codex 复验第 2 轮修复（2026-08-13）**：Issue-1 FenvGuard 改为 move-only 且在
`std::optional` 内直接 `arm()`（消除拷贝析构在 interpreter 执行前提前恢复 rounding 的 bug），
并新增 `interp_fast_pins_rn_during_run` 测试（caller 设 FE_UPWARD，tie kernel 断言 fast 结果
为 RN 语义 + 返回后仍 FE_UPWARD）；Issue-2 F2F result-exceptional fallback 改为单一公共出口
计数（消除同一 lane/leaf 计两次 fallback），并按目标格式分类 native 结果
（F16/BF16 低 16 位、F64 完整 double、F32 f32），新增 `interp_fast_f2f_overflow_fallback_single_count`
测试（F32→F16 溢出成 Inf：fast_fp_ops==0、precise_fallback_ops==1、结果为精确 F16-Inf）。
修复后 CTest 19/19、diff 484/484、fuzz 110/110、mutation 108/108、ASan/UBSan 全绿、Release
bench FFMA 2.19x / mix 1.32x / div 1.83x / int 1.00x / exc 1.57x。

**codex 复验第 3 轮修复（2026-08-13）**：Blocker fast BF16 寄存器布局与 precise/sm120 相反——
`host_bf16()` 改回把舍入后的 16-bit 置于结果**低 16 位**（`F2F.BF16.F32(1.0f)==0x00003f80`），
BF16→F32 从低 16 位读取并左移 16 位；F16/BF16 NaN→F32 映射到精确 canonical NaN（0x7fffffff）；
新增格式感知的源分类 `exceptional_f2f_source`（BF16 有限值不再被当成 subnormal f32 误 fallback）。
修复 test_fp.cpp 的错误期望并直接与 `fp::f2f()/fp::f32_to_bf16()` 比较；新增
`interp_fast_bf16_layout_dual_mode`（F32→BF16、BF16→F32、溢出成 Inf 恰好一次 fallback、
BF16 NaN/subnormal 分类与计数）。400 个随机 BF16 双方向转换 fast==precise 0 失配。
修复后 CTest 19/19、diff 484/484、fuzz 110/110、mutation 108/108、ASan/UBSan 全绿、Release
bench FFMA 2.17x / mix 1.34x / div 1.92x / int 1.00x / exc 1.64x。

#### Phase 5.5 完成定义（全部满足才 Closed）

1. 单一状态机、双 FP semantics 架构落地，无复制控制流实现
2. precise 为默认，Phase 5 exact/GPU differential 行为不变
3. 路由矩阵无静默 unsupported，所有近似/fallback 可通过 Result/trace 观察
4. F2I 等安全敏感 conversion 无 UB
5. Phase 4 双 mode 回归、fast tolerance/fallback tests、sanitizers 全绿
6. Release 稳定基准达到 FP-heavy ≥2x、mixed ≥1.3x、integer regression ≤5%
7. CLI/API 文档明确 fast 不是 sm_120 位精确模型及其禁用场景

#### 风险与限制

- fast FP 结果可能改变后续 FP compare/predicate 从而改变控制流（数值稳定性/收敛/边界分支必须用 precise）
- NaN payload、signed zero、subnormal、directed rounding、FTZ/FMZ、double-rounding trap 在 fallback none 下不可依赖
- 不同 CPU/编译器/宿主 FP environment 产生不同 fast 结果；fast 不可作为跨平台 golden
- 修改 MXCSR/FPCR 会污染调用线程，初版禁止；interpreter 实例不得跨线程迁移执行
- fast mode 不得用于生成 ISA 逆向结论、GPU differential expected values 或任何要求复现 sm_120 bit pattern 的调试

### Phase 6 — Memory、同步与多核 interpreter

**状态**：Step 1（内存指令 + 基础同步 + atomic + 逻辑 scoreboard）、Step 2A（CPU worker
pool）、Step 2B（Unified L1TEX estimator + 4-subcore trace）、Step 2C（event-based L2）、
Step 2D（HB/race detector，含多 worker 共享 detector 确定性合并修复）均实现完成
（2026-08-13）。Step 2E（集成与性能：profiler/race 四开关组合 + 开销测量）验证完成。
后经 codex 二审与复验第 1–4 轮：Step 2F 全面修复落地（FastTrack 区间 shadow、atomic
release/acquire 契约、128-bit 内存路径、L2 确定性等），第 4 轮修正 atomic writer 兼容
豁免过宽问题（`race_detector.cpp`）。全量门禁（第 4 轮最终）：
CTest 24/24（normal/ASan/TSan 各 24/24）、diff_phase5 484/484、fuzz 120/120、
mutation 108/108、l1tex_oracle 840/365/216/520，`sim.py` 未修改。
各 Step 交付见本节末尾对应小节。

**codex 二审（2026-08-16）**：修复 4 Blocker + 4 High + 4 Medium + 3 门禁问题，全部落地并
重跑全量门禁（见下方 **Step 2F 交付（codex 审阅修复）**）。race detector 改为 FastTrack
风格区间 shadow（clock snapshot 有向 HB、RAW/WAR/WAW、同 warp 指令序）；atomic/fence
release/acquire 契约落地；128-bit 内存路径全宽；UnifiedV1Estimator 真正接入 coupled
L1→shared 路径；MemoryService 边界/对齐/溢出检查补全；真实 allocation 生命周期 +
generation 查询；launch 级共享 L2 engine + 显式 CTA→SM 映射 + 全局稳定 event id；
subcore warp-linear id 修正；`mem_width_info` 非法 size 拒绝、worker fenv 失败结构化
fault、race dedup key 规范化 actor 序、L2 循环回绕保护；CTest 24/24 对齐、numpy 安装、
`l1tex_oracle` 指向真实 arch/l1tex。`sim.py` 未修改。

#### 实现内容

- 实现 LDC/LDCU、LDG/STG、LDS/STS、local access 和主要 width/sign-extension variants。
- 实现 atomic、BAR、MEMBAR、FENCE 和 memory scope。
- 建立逻辑 scoreboard/pending operation，支持正确程序中的 wait、DEPBAR 和显式同步。
- control word 进入依赖诊断，但不复现缺 wait 时的具体 stale 数据。
- CPU worker pool 按 CTA 分发；单个 CTA 在一次 launch 中由同一 worker 维护。
- 默认 debug/deterministic 模式使用单 worker；吞吐模式允许多个 CTA 并行。
- 每个模拟 SM 建立 4-subcore memory issue/serialization 状态；warp-to-subcore 映射
  稳定且可在 trace 中观察。该层保持 SM 内顺序，不承担跨 SM 的全局排序。
- 建立 event-based L2 request/completion 层；跨 SM global access、L1 miss、
  writeback 和相应 atomic 通过 L2 event 交互，确定性模式使用稳定事件序。
- 实现 happens-before data-race detector：shared memory 检测同一 CTA 内的
  lane/warp 冲突，global memory 检测同一 launch 内跨 lane/warp/CTA/SM 冲突。
- data-race-free kernel 在不同 worker 数下必须结果一致；检测到 race 的 kernel
  不承诺跨调度模式结果一致，但必须产生稳定、可解释的 race report。

Race detector 的首版语义：

- 两个重叠 byte range 的访问中至少一个是 write，且二者不都是兼容 atomic，且
  happens-before 不可证明时，报告 race；按 byte range 判断，不能只按首地址。
- 同一动态 warp memory instruction 中各 active lane 视为并发参与者；同址多写、
  读写混合需要报告，atomic/broadcast 等明确例外单独分类。
- lane program order、CTA barrier、named barrier/mbarrier、支持的 fence、具有相应
  memory order 与 scope 的 atomic、kernel launch/completion 建立 HB edge。仅有
  control-flow convergence、同一宿主 worker 或偶然事件执行先后不建立 HB。
- shared shadow state 以 CTA allocation 为域；CTA 结束即可回收。global shadow
  state以 allocation+byte range 为域，跨 SM 共享，并在 free/reallocate 时使用
  generation 防止地址复用混淆。
- 报告包含两侧 PC/指令、access kind、精确重叠范围、lane/warp/CTA/SM/subcore、
  atomic/order/scope、已观察到的同步链和“为何没有 HB”的原因。重复报告使用稳定
  key 去重，并保留 occurrence count。
- 未实现的 memory-order/scope 组合标为 `race-analysis-unsupported`，不得静默按
  race-free 处理。race detector 的 shadow memory 自身必须线程安全，且不能被
  ThreadSanitizer 的宿主 race 检测替代。

#### 验证方式

- LDG/STG 全宽度、sign extension、alignment、OOB 和 address-space errors。
- LDS/STS、dynamic/static shared、named barrier 和 atomic contention。
- 对照 `test_ldg_stg`、`test_lds_sts`、`test_atom`、`test_depbar` 和 memory-order tests。
- 同一 race-free workload 分别使用 1/2/4/宿主核数 worker，并比较输出和 fault。
- ThreadSanitizer 检查宿主实现不存在 data race。
- 4 个 subcore 分别单独发流、两两交错和四路同时发流，验证每流 program order、
  L1TEX arbitration reason 与确定性 replay；确认不会错误地把整个 SM 全序化。
- 至少两个模拟 SM 产生相同/不同 L2 sector 请求，验证 L2 event 因果边、稳定
  tie-break、seed replay 和 functional value 与事件调度解耦。
- shared race golden：同 warp lane 写写/读写、跨 warp 无 barrier、BAR 后无 race、
  不相交字节、相同地址 atomic、partial active mask 和动态 shared 边界。
- global race golden：跨 CTA/SM 写写与读写、atomic、正确/错误 fence+flag publish、
  不同 allocation、重叠非对齐 range，以及 kernel boundary 建立 HB。
- 对每个 race case 验证两侧 PC、CTA/warp/lane、重叠 byte range、space、原因链；
  同一确定性执行的 JSON report 必须 byte-for-byte 一致。
- profiler/race detector 四种组合（off/off、on/off、off/on、on/on）的功能输出一致。
- 错误 scoreboard 用例产生依赖诊断，但不要求匹配硬件 stale register 值。

#### 退出条件

- vector add、reduction、shared tile、branch-heavy 和 atomic kernel 可从标准 nvcc cubin 运行。
- 多 worker 不改变无数据竞争程序的结果。
- 所有非法访存转化为 simulator fault，不造成宿主内存越界。
- shared/global race golden corpus 无漏报；明确支持的 barrier/fence/atomic 用例无
  误报；unsupported memory-order/scope 必须显式诊断。
- L1TEX trace 能区分 4 个 subcore 的 serialization，L2 trace 能表达跨 SM 事件
  因果关系；两层均不改变 `MemoryService` 的功能结果。

#### Step 1 交付（2026-08-13）

实现范围（本轮）：

- **`MemoryService` 抽象**（`include/semu/memory_service.hpp` + `src/memory_service.cpp`）：
  在既有 `MemoryAllocator` 之上提供 SASS 级 typed 访存（LDG/STG/LDS/STS/LDC/LDL +
  global/shared atomic），按 width/alignment/bounds/space 强制检查并把访问错误转换为
  `Fault`（kIllegalMemoryAccess / kAlignmentFault / kLifecycleFault，绝无宿主越界）。
  为后续 L1/subcore serialization、L2 event 层与 race detector 预留接口
  （`MemoryConfig` 挂在 `RunOptions` 上，global buffer/params/shared/local 窗口）。
- **内存指令**：LDG/STG（descriptor+Ra+offset 与 sImmOffset 形式）、LDS/STS（含
  `NonZeroRegister` 地址修复）、LDC/LDCU（constant bank + 参数）、LDL/STL（per-warp
  local 窗口）、窄宽度 U8/S8/U16/S16 的符号/零扩展。
- **atomic**：ATOM/ATOMS/RED/REDS + ATOMG/REDG（global/shared RMW：add/min/max/and/or/
  xor/exch），pre-value 写回 Rd；多 warp contention 下结果正确（64 线程加 1 → 64）。
- **同步**：BAR.SYNC（多 warp 会合）、MEMBAR/FENCE（功能 no-op）、ERRBAR/CGAERRBAR/
  CCTL（membar 周围发射的 cache 屏障 no-op）、DEPBAR/LDGDEPBAR（逻辑 scoreboard：
  同步模型下 wait 即可见全部数据，control-word 依赖进入诊断）。
- **CLI**：`--global=<hex>`（global 缓冲 + STG 结果 JSON 回读）、`--param-hex=<hex>`
  （constant0 参数）、`--shared-size=<N>`。

验证：

- CTest 19/19 全绿（新增：`interp_phase6_lds_sts_ldg_stg`、`interp_phase6_shared_oob_fault`、
  `interp_phase6_atomic_contention`、`interp_phase6_membar_depbar_order` +
  MemoryService 单元测试：宽度/符号扩展、store 宽度、shared round-trip+OOB、shared atomic）。
- diff_phase5 484/484、fuzz 110/110、mutation 108/108（含 ASan）全绿，precise 无回归。
- ASan/UBSan 干净（含 LDC constant-bank 尺寸修复与 NonZeroRegister 读取）。
- 真实 nvcc cubin：`tests/membar_test.cu` 全部 11 个 kernel（mb_cta/gl/sys、fence_*、
  fence_cluster、fence_proxy_async）经 semu 运行至完成。
- CLI 端到端：LDG/STG round-trip（global 0x5A→读回、写 0x2A 回读）、LDS/STS round-trip、
  global/shared ATOM/ATOMG add、LDC 参数读取（0xDEADBEEF）、STL/LDL local round-trip、
  BAR.SYNC 64 线程同步、MEMBAR/DEPBAR 顺序保持。

已知限制（后续 Step）：

- `cp.async`（LDGSTS/commit_group/wait_group）与 `UMOV` 等 uniform ALU 未实现，故
  `depbar_test.cu` / `ldgsts_test.cu` 的 nvcc cubin 尚不能完整运行（DEPBAR.LE 语义已通过
  assembler 路径验证）。
- nvcc cubin 中未识别的 EIATTR（如 atom_order_test 的 0x31）会阻止加载；汇编器生成
  cubin 不受影响。
- global 64-bit atomic 的 pre-value 高半暂不原子回读（step 1 单 writer 模型）。

#### Step 2A 交付（CPU worker pool，2026-08-13）

按 codex 审阅调整后的方案（`/tmp/phase6_plan_review.md`）拆分实施：

- **多 CTA 基础**：`Interpreter` 按 grid 构建全部 CTA；每个 CTA 独立 shared window +
  per-warp local window；`next_group`/`execute_group` 增加 CTA 维度（修正原单 CTA 假设）；
  `SR_CTAID.X/Y/Z` 返回真实 CTA 坐标。
- **worker pool**：`RunOptions::worker_count`（1=确定性单 worker，>1=吞吐模式）。
  `run_owned()` 提取单实例运行循环；`run_result_parallel()` 按 `cta_id % worker_count`
  把 CTA 固定归属到 worker 线程，全部 worker 共享一个 `MemoryService`（`setup_mutex_`/
  `global_mutex_` 保证构造与 global 读写线程安全）；fast 模式每 worker 独立 fenv guard
  （fenv 为线程局部）。fault 确定性选择最小 `(cta_id, dynamic_instructions)`。
- **验证**：
  - 1/2/4 worker 运行 race-free 多 CTA kernel（global 写 + shared/BAR round-trip），
    输出 GPR/shared/global 逐字节一致（新增 `interp_phase6_worker_count_invariance`）。
  - ThreadSanitizer（`/tmp/semu-tsan`）在 interpreter 测试 + CLI `--workers=4` 并行路径
    下无宿主 data race。
  - 修复合入时发现的真实 bug：多 CTA 下 `do_memory`/`do_bar` 误用全局 `cta_id` 索引
    `ctas_`（改为 `local_cta_id`）、`NonZeroRegister` 地址读取、constant-bank 尺寸。

#### Step 2B 交付（Unified L1TEX estimator + 4-subcore trace，2026-08-13）

- **纯 C++ `UnifiedV1Estimator`**（`l1tex_model.hpp/cpp`，版本 `unified-v1`）：密封
  128-B token（4/8/16 B → 32/16/8 lane/token）、read-wave greedy coloring（tbk 排序）、
  write-wave greedy coloring、joint fiber（read-bank span + write-bank span 二元组）、
  `SharedWf = read_waves + write_waves - largest_joint_fiber`。纯函数，无 MemoryService/
  scheduler 副作用；只用于 coupled L1→shared 路径的 SharedWf 估计。
- **与 Python oracle 逐字段一致**：`tools/l1tex_oracle_check.py` 对全部冻结 fixture 验证
  C++==Python（含每 token 分解）：GF2 840/840、GF2-near 365/365、token 216/216、
  random 520/520；GPU random 精确度 176/400 MAE .738、19/60 MAE 1.167、32/60 MAE .817
  与冻结期望一致（random 只锁定总体 exact/MAE，不要求逐例命中）。注册为 CTest
  `l1tex_oracle`。
- **4-subcore scheduler**（`subcore_scheduler.hpp/cpp`）：每 SM 4 个独立 `SubcoreIssueState`
  （issue cursor + subcore-local sequence），`warp % 4` 稳定映射（封装 `ISubcoreMapper`）；
  subcore 内保 program order，4 个 subcore 各自独立发流、不把整个 SM 全序化；
  `subcore_trace_line` 逐 subcore 列出 issue 序。`test_subcore.cpp` 覆盖映射稳定、同
  subcore 单调序、跨 subcore 不强制排序、trace 不合并。
- **事件 schema**（`memory_events.hpp`）：`MemoryEvent`/`TokenServiceEvent`（含
  model_version="unified-v1"、prediction 标记）；`MemoryModelOptions{l1tex, l1tex_model,
  simulated_sm_count, deterministic_seed}` 挂 `RunOptions`；CLI `--l1tex` 输出 JSON 事件。
- **trace-only 约束**（codex 关键约束全部满足）：
  - estimator/SharedWf 只作为 trace 事件，绝不改变功能值、scoreboard 完成、
    atomic 线性化或 HB（`interp_phase6_l1tex_trace_only_and_subcore` 验证 off/on 功能一致）；
  - 普通 LDG/STG/LDS/STS/atomic/constant **不**喂 estimator（只预留给显式 LDGSTS 的
    coupled 路径），不跨指令融合 token；
  - 预测扰动 gate：estimator 返回 1 / 真实 SharedWf / SharedWf+N 时功能结果、scoreboard、
    race JSON 必须一致（当前 estimator 未接入 ordinary 路径，天然满足；后续 LDGSTS 接入时
    由 `interp_phase6_l1tex_trace_only_and_subcore` + stub 注入门禁保证）；
  - 性能模型不进入 `MemoryService`（独立组件）。

验证汇总：CTest 22/22（新增 l1tex、subcore、l1tex_oracle、worker-count、trace-only）、
diff_phase5 484/484、fuzz mutation 108/108、ASan/UBSan、TSan 全绿；`sim.py` 未修改。

#### Step 2C 交付（event-based L2，2026-08-13）

- **`L2EventEngine`**（`l2_events.hpp/cpp`）：跨 SM 的 L2 request/completion 层。global
  访问按 128-B sector 拆分；`simulated_sm_count` + `deterministic_seed` 提供稳定 tie-break；
  同 seed 重复执行事件序列字节级一致（seed replay）。
- **interpreter 接入**：`record_l2_access`/`flush_l2_events`（仅 global，trace-only，
  绝不改变功能值）；`L2Mode` 挂 `MemoryModelOptions`；CLI `--l2`。
- **验证**：`test_l2.cpp` + `interp_phase6_l2_trace_only`（L2 on/off 功能结果逐字节一致 +
  seed replay 一致）。

#### Step 2D 交付（HB/race detector + 多 worker 共享修复，2026-08-13）

- **`HbClock` + `RaceDetector`**（`hb_clock.hpp/cpp` + `race_detector.hpp/cpp`）：happens-
  before detector。shared 以 CTA allocation 为域、global 以 (allocation, generation, byte
  range) 为域；重叠 byte range + 至少一个 write + 非兼容 atomic 且 HB 不可证明时报告；
  lane program order / CTA barrier / 匹配 order+scope 的 atomic 建立 HB 边；unsupported
  order/scope 标记 `race-analysis-unsupported`；稳定 dedup key + occurrence count；shadow
  memory 自身 mutex 线程安全（宿主 race 由 TSan 检查，不替代）。
- **interpreter 接入**：`record_race_access`（load/store/atomic，shared/global）+ barrier
  释放事件；`RaceMode` 挂 `MemoryModelOptions`；CLI `--race`；`Result::race_reports`。
- **13 个 golden 用例**（`test_race.cpp`）：shared 同 warp 写写/读写、跨 warp 无 barrier、
  BAR 后无 race、不相交字节、同址 atomic、partial active mask、动态 shared 边界；global
  跨 CTA/SM 写写与读写、fence 单独无 HB、不同 allocation、非对齐重叠 range、同执行
  JSON 字节一致。
- **多 worker race 报告一致性修复**（本会话）：原先 `run_result_parallel` 中每个
  worker-subset interpreter 各建独立 `RaceDetector`（interpreter.cpp），导致跨 CTA/global
  race 漏检，且 1/2/4 worker 的 race JSON 非逐字节一致（各 504 race 但内容不同）。修复：
  - 每个 interpreter 不再直接 `observe`，而是把 race 事件（access + barrier）按执行顺序
    追加到 `race_log_`（带 per-CTA ordinal）。
  - `run_result_parallel` 创建**单个共享 `RaceDetector`** 传给所有 worker（构造器新增
    `shared_detector` 参数，仅 owned 时在构造器内 `set_enabled`，避免跨线程写 `enabled_`）；
    全部 worker join 后按 `(cta_id, ordinal)` 确定性合并 replay（`replay_race_log`，
    单线程提交，线程安全）。单 worker 路径用同一 `(cta, ordinal)` replay 顺序，保证两种
    模式 report 集与顺序一致。
  - 结果合并改用共享 detector 的 `reports()`（不再按 worker 拼接），fault/正常路径一致。
  - **重验**：1/2/4 worker race JSON 逐字节一致（504 race 全同）；跨 CTA/global race
    不再漏检（grid=4 的 global 写写 kernel 在 1/2/4 worker 均检出 c0→c1/c1→c2/c2→c3 三条
    跨 CTA race）；新增 `interp_phase6_race_worker_count_json_identity`（1/2/4 worker
    race JSON 逐字节一致 + 跨 CTA race 存在）。

#### Step 2E 验证（集成与性能，2026-08-13）

- profiler/race 四开关组合（off/off、l1tex-only、race-only、l1tex+race、l2）功能输出
  逐字节一致（`--race`/`--l1tex`/`--l2` 均为 trace-only）。
- 全量门禁：CTest 24/24、diff_phase5 484/484（480 differential + 2 fault check）、fuzz
  110/110、mutation 108/108、ASan/UBSan CTest 23/23、TSan CTest 23/23（含 `--workers=4`
  并行路径无宿主 data race）；`sim.py` 未修改。

#### Step 2F 交付（codex 审阅修复，2026-08-16）

按 codex 二审报告修复（`race_detector.*` / `hb_clock.*` / `memory_service.*` /
`l2_events.*` / `interpreter.*` / `interpreter.hpp` / `tests/CMakeLists.txt`）：

**Blocker-1 — race detector HB 算法重写**（`race_detector.cpp`）：
- 改 FastTrack 风格区间 shadow：每个 writer/reader 保存访问时的 clock **snapshot**
  （`writer_clock` / `readers{actor->(access, clock)}`），有向 HB 判断 `prior->current`
  用 `current_clock.dominates(prior_clock)`，不再查可变 `clocks_`（消除“同步后追溯性
  改变旧访问顺序”）。
- 同 lane：指令号 program order；同 warp 不同 lane：不同动态指令按指令号 program order
  （barrier 后同 warp lane 不再误报），同一动态指令的 lane 视为并发参与者（仍报 race）。
- 分别检查 RAW / WAW / WAR：新 write 会逐个比对 interval 内所有 reader（原实现只比
  `last_write`，WAR 漏检）。
- 区间 split/merge：部分重叠访问按字节拆分保留未覆盖片段。
- barrier/named barrier 构造 actor 使用 CTA 对应 SM（`sm_of_cta`），与访存 actor 一致。

**Blocker-2 — atomic/fence HB 契约**（`race_detector.*` + interpreter）：
- `fence()` 不再为空：记录 fence 事件（scope 保留，单独不建立 HB），replay 走 `kFence`。
- `atomic_rmw()` 实现 release/acquire：按 (space, allocation/cta, generation, byte
  range, scope) 域维护 **release clock**；release/acq_rel/strong 发布本 actor clock，
  acquire/acq_rel/strong 合并 release clock（`is_release_order`/`is_acquire_order`）。
- replay 事件保留 atomic/fence 类型（`RaceEvent::kAtomic`/`kFence`），interpreter 不再把
  atomic 记为普通 `kObserve`；atomic 的 sem/sco 从指令槽位真实解码（WEAK/STRONG/MMIO、
  nosco/cta/sm/vc/gpu/sys）。
- `classify_order_scope()` 使用 scope；`order_scope_ok` 进入 JSON report。

**Blocker-3 — 128-bit 内存/atomic 路径**：
- MemoryService 全部 load/store/atomic 改传固定 `MemValue`（4×32-bit word）；128-bit
  load/store 读写全部 16 字节（原来只 lo/hi，高 8 字节丢/写零）。
- interpreter 128-bit load 写 Rd..Rd+3、128-bit store 读 Rb..Rb+3。
- 未实现 128-bit atomic：`atom_global`/`atom_shared` 对 width==16 返回结构化错误
  （kNotSupported），绝不进入 8-byte RMW（原来 width=16 越界复制 `cur[8]`）。

**Blocker-4 — UnifiedV1Estimator 真正接入**：
- 普通 LDG/STG/LDS/STS/atomic 不再伪造 coupled prediction（`record_memory_event` 只做
  subcore issue，`coupled_l1_to_shared`/`prediction` 恒 false）。
- 新增 `record_coupled_l1_to_shared`：仅在真实 coupled L1→shared（LDGSTS/cp.async）路径
  构造完整 per-lane global/shared offset 数组 + active mask + element width，调用
  `UnifiedV1Estimator::estimate`，产出 prediction + token-service 事件。LDGSTS 已接入
  opcode 派发（0x1fae/0x1dae）并在未实现 fault 前记录预测事件。
- 新测试 `interp_phase6_l1tex_coupled_ldgsts_prediction` 逐字段校验。

**High-1 — MemoryService 边界/对齐/溢出**：
- `checked_add`（signed offset 安全加减，无回绕）；`off <= size && len <= size-off`
  全部替换 `off+len>size`；按 width 自然对齐检查（1/2/4/8/16）→ kAlignmentViolation；
  `ldg`/`stg`/`lds`/`sts`/`ldc`/atomic 入口校验 `MemWidthInfo.valid`。
- 新测试 `memory_service_bounds_alignment_overflow`。

**High-2 — 真实 allocation 生命周期 + generation**：
- interpreter 通过 `MemoryService::global_allocation_id()` 传真实 alloc id（不再硬编码 1）；
- `observe` 对 global 访问查询当前 generation（`current_generation`），`key_of` 同样查询；
- `reclaim_allocation` bump generation **并清掉该 allocation 的旧 shadow**（防地址复用
  混淆，原来只递增从未查询的 map）。新测试 `race_global_reclaim_generation_isolates`。

**High-3 — 真实多 SM L2 拓扑**：
- launch 级共享 `L2EventEngine`（worker 间同一实例 + mutex 保护），request/completion/
  event id 全局唯一；worker 不 drain 共享引擎，launch join 后 drain 一次并按
  (sm,cta,subcore,sector,event_id) 确定性排序，再全局重编号（消除跨 worker event id
  重复）。
- 显式 CTA→SM 映射：`sm_of_cta = cta % simulated_sm_count`（>1 时）贯穿 race/L2/subcore
  层；barrier/fence 事件携带 CTA 的 SM。
- 新测试 `interp_phase6_l2_cta_sm_mapping`、`interp_phase6_l2_worker_count_shared_engine`。

**High-4 — subcore warp-linear id**：
- `warp_linear_id` 用 `ceil(block_threads/32)`（原来 floor，block<32 时全部为 0）。
  新测试 `interp_phase6_subcore_warp_linear_small_block`（block=16、grid=4 → 4 个不同
  subcore）。

**Medium**：
- `mem_width_info` 对 sz>=7 返回 `valid=false`（非法 encoding 拒绝，不再默认 4 字节）。
- worker fast mode `fenv arm()` 失败 → 结构化 `kInternal` fault（与单 worker 一致）。
- race report dedup key 规范化 actor 顺序（反向观察不产生重复报告），新测试
  `race_dedup_reversed_observation_order`。
- `L2EventEngine::issue_global` sector 循环以 `len` 为界（addr+len 回绕保护）。

**门禁**：
- CTest 注册数对齐：正常 / ASan / TSan 均为 **24/24**（含 `l1tex_oracle`）。
- `fuzz_phase5` 依赖的 numpy 已安装（系统 python3.11，`pip install --user --break-system-packages numpy`）。
- `l1tex_oracle` 的 `L1TEX_ARCH_DIR` 默认指向 `/home/cicuvc/cs/projects/arch/l1tex`（不再
  自动探测相对路径），确保 840/365/216/520 Python oracle 对比真实执行。

**重验（2026-08-16）**：CTest 24/24、diff_phase5 **484/484**、fuzz **120/120**、mutation
**108/108**（0 errors）、ASan/UBSan CTest **24/24**、TSan CTest **24/24**（含
`--workers=2/4` 共享 L2 engine + 共享 race detector 无宿主 data race）、`l1tex_oracle`
**840/365/216/520 + 随机 GPU 期望一致**；`sim.py` 未修改。

#### Step 2F 复验第二轮（2026-08-16，semu 实现者修复）

codex 复验 Phase 6 第2轮发现 4 Blocker + 3 High，全部修复并重跑全量门禁。改动：
`race_detector.*` / `memory_service.*` / `memory.*` / `interpreter.*` /
`decoder/render.cpp` / `tests/test_race.cpp` / `tests/test_interp.cpp`。

**Blocker-1 — FastTrack 区间 read 丢 writer/readers**（`race_detector.cpp`）：
- `observe` 改为真正区间分割：新访问覆盖区间按既有 interval 边界切割；head/tail
  片段保留原 writer/readers；**READ 复制被覆盖区间的 writer + 全部 readers 再添加
  当前 reader**（绝不丢 writer，否则后续 WAW 漏检）；**WRITE 在完成 RAW/WAW/WAR
  检查后**才替换子区间 writer 并清 readers。反例（warpA write X → barrier →
  warpB read X → 未同步 warpC write X）第三步同时报 WAW(A,C) 与 WAR(B,C)。
- 新测试 `race_read_preserves_writer_for_waw`。

**Blocker-2 — 反向 HB 判定隐藏 race**（`race_detector.cpp`）：
- `check_interval` 删除两处 `happens_before(current, prior)` 反向检查；HB 只按
  prior→current 有向测试（同 lane/warp 程序序 + 向量时钟快照）。replay 顺序与动态
  instruction id 不一致 / 跨 CTA replay / 错误输入下不再因反向边隐藏 race。
- 新测试 `race_reverse_instruction_order_still_races`（先喂 inst-5 write 再喂
  inst-3 write 仍报 race；旧代码反向程序序边抑制了报告）。

**Blocker-3 — Race/L2 用未加 displacement 的错误地址**（`interpreter.cpp` +
`decoder/render.cpp`）：
- 统一先算 overflow-safe `effective = base + signed offset`（constant 空间已折叠
  offset 不再二次加），MemoryService / race detector / L2 sector trace 全用
  effective（原 functional 用 addr+off 而 race/L2 用裸 addr，同 base 不同 disp 误判
  重叠、不同 base+disp 同址漏报、L2 sector 错）。
- 修复 `read_addr_pair` 只接受 `Register` kind（`NonZeroRegister` 的 STG/STS
  sImmOffset 形式返回 0）；解码器 `collect_operands` 对 SImm/RSImm operand 值按字段
  宽度符号扩展（24/20/12-bit 负 displacement 不再解成巨大正值），interpreter 内存
  偏移改读 operand 值（新 `offset_value`）。
- 新测试：跨 sector displacement（STG base 0x70 +0x20 → L2 sector 1 而非 0）、正负
  displacement 等价有效地址跨 warp race（warp0 `[R1+0x10]` vs warp1 `[R1-0x20]` 同指
  shared 0x110）。

**Blocker-4 — atomic 静默降级 ADD**（`interpreter.cpp` + `memory_service.*` +
`memory.*`）：
- 实现 INC/DEC（U32-only wrap-to-bound：`inc=(old>=b)?0:old+1`、
  `dec=(old==0||old>b)?b:old-1`）、CAS（Rc compare，`find_op("Rc")` 识别，compare
  从 Rc 读）、S32/S64 signed MIN/MAX；FP atomic（ATOMICFPOPS）、SAFEADD、INVALID
  op、非法 width/op 组合返回 kNotSupported（绝不降级 ADD）。
- `AtomicOp` 增 kInc/kDec/kCas/kMinSigned/kMaxSigned；`apply_atomic` 统一按
  (op,width) 计算；allocator 路径同步实现新语义并对 kCas 结构化拒绝。
- 新测试 `interp_phase6_atomic_inc_dec_cas_signed`（INC wrap、DEC 三分支、signed
  min/max 边界、CAS 命中/未命中）+ `interp_phase6_atomic_unknown_op_not_downgraded`
  （FP atomic 结构化 fault，非静默整数 ADD）。

**High-1 — atomic scope 域**（`race_detector.*`）：
- ReleaseKey 去掉 scope 字段；`release_clocks_` 改为 location → `vector<ReleaseRecord>`
  （releasing actor + scope + clock）。acquire 按 PTX §8.5/§8.7 显式判定兼容性：
  `scope_visible(rel, acq) && scope_visible(acq, rel)` — cta 含 CTA、sm 含 SM、
  gpu/sys 覆盖整个 launch/系统、nosco≈cta、未知 scope 不兼容。
- 新测试：release.cta 不跨 CTA 同步、同 CTA gpu acquire 可见、gpu release 对异 CTA
  cta acquire 不可见、sm scope 按 SM 域隔离。

**High-2 — 多 worker L2 trace 非调度独立确定性**（`interpreter.*`）：
- worker 执行期不再驱动共享 L2 engine（mutex 锁获取序不确定 ⇒ request id / 同
  sector 插入序 / event id tie-break 都依赖调度），只把稳定 request descriptor
  （cta, per-CTA ordinal, lane, addr, len, ...）追加到 `l2_log_`；join 后按
  (cta, ordinal, lane) 排序，由单线程 launch-level engine 分配 request/event id 与
  seed schedule，再 drain。单 worker 路径走同一 (cta, ordinal, lane) 排序。
- 新测试 `interp_phase6_l2_worker_count_deterministic_trace`：1/2/4 worker 的 L2
  事件流 byte-for-byte 一致（含 event id），同配置重复运行亦一致。

**High-3 — LDGSTS 收集的 global 地址不完整**（`interpreter.cpp`）：
- LDGSTS goff 改用与 LDG 相同的完整地址解析：64-bit Ra:R(a+1)（RR64U/RUR/desc 形式）
  + uniform base（Ra_URc）+ signed Ra_offset；负 offset 借高 32 位不 underflow。
- 新测试：高 32 位非零 + 负位移（base 0x1_0000_0000、offset -0x10 → goff
  0xFFFFFFF0，prediction ReadWf=4 而非 naive 20）、uniform base 跨 128-byte tag。

**门禁重验（2026-08-16）**：CTest **24/24**、diff_phase5 **484/484**（480
differential + 2 fault checks）、fuzz **40/40** + mutation **108/108**（0 errors）、
ASan/UBSan CTest **24/24**、TSan CTest **24/24**（含 `--workers=2/4` 共享 race
detector + 单线程 L2 引擎无宿主 data race）、`l1tex_oracle` **840/365/216/520** 一致；
`sim.py` 未修改。

### Phase 6 状态更新（2026-08-16）— 保留语义注记

**状态**：Phase 6 目前落实：Step 1+2A-2E（2026-08-13）、codex 二审修复与 **Step 2F
复验第二轮**（2026-08-16，见下）均已完成并跑通全量门禁（上一段门禁重验结果）。语义
方面：race detector 为 FastTrack 风格区间 shadow（有向 HB、RAW/WAR/WAW、atomic↔atomic
同 range 兼容豁免）；atomic/fence release/acquire 契约与 scope 可见性已落地；
`sim.py` 全程未修改。

#### Step 2F 复验第 4 轮（2026-08-16，semu 实现者修复）

codex 复验第 4 轮发现 1 个问题（`race_detector.cpp` `check_interval` 的 atomic writer
豁免条件过宽），已修复并重跑全量门禁。改动：`semu/src/race_detector.cpp` /
`semu/tests/test_race.cpp`。

**Blocker — atomic writer 豁免被错误应用到无同步 plain read**：
- 旧条件 `writer_exempt = has_write && last_write.is_atomic && (!access.is_write ||
  (access.is_atomic && same_range))` 中 `!access.is_write` 使旧 writer 为 atomic 时，
  后续任意普通 read 都跳过 RAW 检查、不要求 HB。这是错误语义：atomic 不会自动让无
  同步的 non-atomic 访问合法 —— A atomic write X → B 无同步 plain read X 应报 RAW，
  但被豁免隐藏。
- 修复：豁免严格限制为 **atomic↔atomic 同 range writer pair**：
  `writer_exempt = has_write && last_write.is_atomic && access.is_atomic &&
  byte_begin == last_write.byte_begin && byte_end == last_write.byte_end`。
  语义：atomic A → atomic C writer pair 豁免；atomic A → plain read B 执行 RAW HB
  检查，无 HB 则报；plain read B → atomic C 继续走 WAR 检查；release/acquire 真正
  建立 HB 时由有向 vector clock 消除报告（不再依赖 atomic 类型豁免）。
- 回归测试 `race_atomic_write_plain_read_atomic_write_reports_war` 改为：1) A atomic
  write 无报告；2) B unordered plain read **期望 1 个 A/B RAW**（旧代码此处 `r.empty()`
  恰锁定错误行为）；3) C atomic write 期望新增 1 个 B/C WAR（A/C WAW 仍豁免）。并新增
  `race_atomic_write_plain_read_with_release_acquire_hb_no_report`：同一场景但在 flag
  上做 release/acquire（同 CTA、gpu scope）后 plain read 不误报 —— 证明第 2 步的 RAW
  源于缺失 HB 边，而非访问类别本身。
- 验证（修复前可复现失败）：临时恢复旧豁免后新测试在 step 2 失败（`r.size()==1` 未
  满足），修复后全绿。

**门禁重验（第 4 轮最终，2026-08-16）**：CTest **24/24**（normal 与 ASan/UBSan/TSan
三个构建树各自 **24/24**）、测试二进制直接运行（race/interp ASan、TSan 全绿）、
diff_phase5 **484/484**（480 differential + 2 fault checks）、fuzz **120/120**
（`-n 110 --seed 20260813`，0 failed 0 skipped）、mutation **108/108**（0 semu
errors）、`l1tex_oracle` **840/365/216/520**（C++==Python 1941/1941）一致；
`sim.py` 未修改。

### Phase 7 — 单步调试接口

#### 实现内容

- `DebugSession::step()` 每次执行一个动态 warp instruction。
- 返回 kernel、CTA、warp、PC、active mask、decoded instruction、register diff 和 memory events。
- 支持 PC/mnemonic breakpoint、CTA/warp/lane 条件和 memory watchpoint。
- 支持查看和修改 GPR、UR、predicate、special register、PC、memory、barrier、scoreboard 和 pending state。
- 支持 continue、选择 warp step、fault stop 和 instruction limit。
- CLI `debug` 提供 REPL；底层能力全部来自公共 C++ API。

debug session 固定为单 worker，以保证逐步运行可复现。

#### 验证方式

- step N 次再 continue 与直接 continue 结果一致。
- divergence 中 breakpoint 只命中正确 PC group 和 lane mask。
- watchpoint 覆盖多 lane、跨界和 atomic 访问。
- 修改 register/memory 后按修改后的状态继续执行。
- unsupported instruction 在执行前停止，且状态仍可查看。

#### 退出条件

- debug trace 完全可复现。
- debugger 不依赖 profiler，也不绕过 backend API。
- 单步状态足以解释 functional fault 和 memory fault。

### Phase 7 完成记录（2026-08-16）

Phase 7 已实现并跑通全量门禁（CTest **25/25**，原 24/24 不回归 + 新增
`debugger` 测试；diff_phase5 **484/484**；fuzz **40/40** + mutation
**108/108**（0 errors）；ASan/UBSan 与 TSan 构建树各自 **25/25**；
`l1tex_oracle` 840/365/216/520 + 随机一致；`sim.py` 未修改）。

**实现内容**：

- `DebugSession`（`semu/include/semu/debugger.hpp` + `src/debugger.cpp`）：
  - `step()` / `step_n(n)` / `continue_run()`：每次执行一个动态 warp
    instruction，返回 kernel/CTA/warp/PC/实际执行 active mask/decoded
    instruction/register diff/memory events。
  - PC 与 mnemonic breakpoint，支持 CTA/warp/lane-mask 条件；continue 命中
    breakpoint 后自动 step-over 该词一次（GDB 语义）。
  - memory watchpoint：space（global/shared/local/constant）+ byte 区间 +
    r/w/a 种类 + CTA/warp/lane 条件；按 per-lane 已提交访问（多 lane、跨界
    区间相交、atomic RMW）命中，`WatchHit` 携带命中的 lane mask。
  - 查看/修改：GPR、UR、predicate、uniform predicate、lane PC、special
    register、device memory（global/constant/shared/local）、named barrier、
    pending memory-op scoreboard 组、`decode_at(pc)` 的 schedule/scoreboard
    位。
  - fault stop（终止态、状态可查）、instruction limit（可在运行期提高后
    继续）、warp step（`set_focus` 把调度限制到单个 CTA/warp）。
  - `DebugStepInfo::canonical()`：所有可复现字段的确定性序列化，用于证明
    trace 逐字节可复现。
- debug session 固定 **单 worker**：`DebugSession::begin` 强制
  `worker_count == 1`，并关闭 interpreter 内部指令上限（会话自持 limit，
  可在运行期提高）；相同 setup + 相同命令序列逐字节复现（C++ 测试与 CLI
  双重验证）。
- CLI `semu debug <cubin> <kernel> <grid> <block>`：REPL（`s/c/b/wb/del/
  info/r/ur/pred/pc/sreg/mem/focus/limit/fault/trace/help/q`），全部命令
  仅调用公共 `DebugSession` API——不依赖 profiler、不绕过 backend API。
- interpreter 新增 Phase 7 公共面：`step_group`（schedule filter +
  pre-exec veto）、`supports(inst)`（decode-only 在执行前停车）、
  `ctas()/memory()/executed()` 活动状态访问、`special_register_value`、
  每步已提交 lane 内存访问捕获（`record_debug_access`，与 race detector
  同 commit 点）、`execute_group` 回传 guard 过滤后的执行 mask。

**验证方式核对**：

- step N 次再 continue 与直接 continue 结果一致：`dbg_step_n_then_continue_matches_direct_continue`
  （`semu_test_debugger`，kLoop，GPR/pred/exited 全等）。
- divergence 中 breakpoint 只命中正确 PC group 和 lane mask：
  `dbg_breakpoint_divergence_pc_group_and_lane_mask`（taken-lane spin 路径，
  pc 0x50 的 breakpoint 连续两次 mask==0x0000ffff）。
- watchpoint 覆盖多 lane、跨界、atomic：`dbg_watchpoint_multilane`
  （@P0 STG，命中 lane 0x0000ffff）、`dbg_watchpoint_cross_boundary_and_negative`
  （8B store 与 [0x44,0x48) 区间相交命中；区间外不命中）、
  `dbg_watchpoint_atomic_and_kind_negatives`（WK_ATOMIC 命中、WK_READ 不命中，
  值仍提交）。
- 修改 register/memory 后按修改后状态继续执行：`dbg_modify_register_changes_execution`
  （R1=99 → IADD3 结果 lane+99）、`dbg_modify_memory_changes_execution`
  （改写 global[0x40] → LDG 读到新值）。
- unsupported instruction 在执行前停止且状态仍可查看：
  `dbg_unsupported_stops_before_exec_and_state_viewable`（MUFU 停在 pc 0x10，
  executed 计数不前进，GPR/PC 可读，后续 step 仍停车）。
- 单步状态足以解释 functional/memory fault：`dbg_fault_stop_state_viewable_memory_fault`
  （STG OOB → kIllegalMemoryAccess，fault 携带 pc/warp/active_mask/message，
  状态可查）。
- trace 完全可复现：`dbg_trace_fully_reproducible`（同一脚本两会话 canonical
  trace 逐字节相同）+ CLI 脚本两次运行 diff 为空。
- 新增公共 API 均有 compile test 与最小使用示例（`semu_test_debugger` +
  `semu debug` REPL）。

### Phase 7 codex 复验修复（2026-08-16）

codex 审阅 Phase 7 发现 **2 Blocker + 3 Medium**，实现已完成、修复在本节落地并
重跑 CPU 门禁。改动文件：`semu/src/interpreter.cpp`、`semu/src/debugger.cpp`、
`semu/include/semu/interpreter.hpp`、`semu/include/semu/debugger.hpp`、
`semu/cli/main.cpp`、`semu/tests/test_debugger.cpp`；`sim.py` 未修改。

**Blocker-1 — focus warp 语义与 launch Done 混淆**（`step_group` / `next_group` /
`drive_group`）：
- 旧行为：focus warp（warp-step 限定到单个 CTA/warp）无可执行 group 时，
  `step_group()` 直接返回"无 runnable group"，debugger 据此标记 launch **Done**。
  但 focus warp 可能只是**等 barrier**（其他 warp 尚未到达）或**已退出**（其他
  warp 仍可运行）——这两种都不是 launch 完成，clear focus 后必须还能继续。
- 修复：
  - `next_group()` 增加 `eligible_blocked` 输出：扫描时无条件判定
    `any_runnable`（不因 filter 改变 launch-done 判定）；`groups` 为空时
    `*eligible_blocked = any_runnable` —— 真 launch done（全 warp 退出/死锁）为
    false，focus 排除了活 warp 为 true。
  - `step_group()` 新增 `StepGroupFrame::focus_blocked`（两个假分支之一），
    `DebugSession` 新增 `DebugStopReason::kFocusBlocked`：drive_group 遇到
    `frame.focus_blocked` 时**不 latch `done_`**、不报 kDone，会话保持存活，清
    focus / 改 focus 后继续；只有 `focus_blocked == false` 才走 launch-done。
  - `set_focus` 对不存在的 (cta, warp) **结构化拒绝**（`Error::invalid_argument`），
    绝不静默当作"launch done"。
  - do_exit/warp-done 确认：`do_exit` 只把 lane 置 `exited/active=false`（不直接设
    `w.done`）；`next_group` 在扫描时惰性判定 `ws.done`（全部 lane exited、无
    sync-wait、无 barrier-wait 才置位），因此 focus warp 退出后再次 step 时该 warp
    被跳过、`any_runnable` 来自其余 warp → `kFocusBlocked` 而非 kDone。
- 回归测试：
  - `dbg_focus_warp_exits_then_clear_focus_continues`（focus warp 退出 → step 报
    `kFocusBlocked` 且 `finished()==false` → clear focus 后 warp 0 照常执行到
    kDone，两个 warp 的 S2R 结果都正确）。
  - `dbg_focus_warp_waiting_barrier_released_by_other`（focus warp 停在
    BAR.SYNC 0 → step 报 `kFocusBlocked` → clear focus 后 warp 1 到达 barrier、
    释放 warp 0、launch 正常完成）。
  - `dbg_focus_nonexistent_cta_warp_rejected`（CTA 1 / warp 4 的 focus 均结构化
    拒绝、`focus()` 仍为空、后续 valid focus 与执行不受影响）。

**Blocker-2 — shared/local 查看修改缺少作用域**（`debugger.cpp` read/write_memory）：
- 旧行为：shared/local 只按 `(space, address, len)` 做 **offset first-match**，
  读写在哪个 CTA/warp 的窗口上是歧义且可能静默写错窗口。
- 修复：`read_memory` / `write_memory` 增加显式 `MemoryScope`
  （`cta` / `warp` / `lane`）：shared 必须带 `scope.cta`（该 CTA 的 shared
  窗口）；local 必须带 `scope.cta + scope.warp`（该 warp 的 local 窗口），
  `scope.lane` 若给出则校验为真实 lane（0..31）；缺 scope / 指向不存在的
  CTA/warp / lane 越界均结构化失败——**删除 first-match 扫描**。global/constant
  忽略 scope。
- 回归测试：`dbg_shared_local_memory_requires_explicit_scope`（shared 缺 scope
  拒绝、local 缺 cta/warp 拒绝、CTA 0↔CTA 1 与 warp 0↔warp 1 窗口隔离不串、
  scope.lane=32 拒绝、scope.cta=99 not-found、global 忽略 scope 仍可用）。

> ⚠️ **选型变更（round 2 High-1 采用 per-warp 窗口，round 3 复验确认）**：本条
> Blocker-2 修复记录中的 `MemoryScope`（`cta` / `warp` / `lane`）与
> "`scope.lane` 若给出则校验为真实 lane（0..31）" 已被 **per-warp local 窗口
> 选型**取代 —— 本 sim 的 local 模型是 per-warp 窗口（`WarpState::local`，
> per-thread frame 由编译器把 lane\*stride 折进 SASS 地址），`MemoryScope`
> **已删除 `lane` 成员**，`scope.lane` 不再存在、也不再校验。旧验收记录里的
> "scope.lane=32 拒绝" 断言随之删除，替换为 per-warp 窗口语义断言（见下方
> round 2 "High-1" 与 round 3 "Medium-1" 修复记录）。

**Medium-1 — watchpoint/debugger 内存区间算术回绕**：
- 旧行为：`Watchpoint::hits` / 区间端点 `base+size` 直接相加可能回绕
  uint64，导致越界区间的相交判定错误。
- 修复：`add_watchpoint` 拒绝 `base > UINT64_MAX - size`（回绕区间）；`hits()`
  改用**减法式** bounds 检查（`base - addr < width` / `addr - base < size`）；
  `read_memory`/`write_memory` 的窗口检查用 `in_window`（`off<=size &&
  len<=size-off`，先 bounds 后 resize）。
- 回归测试：`dbg_watchpoint_range_overflow_rejected`（`base=UINT64_MAX` 拒绝、
  `base=UINT64_MAX-1,size=2` 拒绝、`size=1` 接受；`read_memory(global, 0,
  UINT64_MAX)` 与 `(UINT64_MAX, 4)` 均在 resize/bad_alloc 之前结构化失败）。

**Medium-2 — breakpoint step-over PC 截断 32 位**（`debugger.cpp`）：
- 旧行为：continue 越过 breakpoint 词一次的 `SuspendBp::pc` 为 `uint32_t`，
  PC ≥ 2^32 的词会被截断、step-over 失效。
- 修复：`SuspendBp::pc` 改为 `uint64_t`（与 lane PC、`Breakpoint::pc` 同宽），
  step-over 的 bypass 比较按完整 64-bit 词地址匹配。
- 回归测试：`dbg_breakpoint_step_over_64bit_pc`（`read_pc` 全 64-bit round-trip、
  `write_pc(0x100000010)` 结构化拒绝而非截断、step-over 在 kDivSpin 0x50 上连续
  两次命中保持 GDB 语义；高 PC 值因内核文本尺寸限制无法在本机构造 >4GB 内核，以
  API round-trip + 拒绝路径 + step-over 行为做结构性验证）。

**Medium-3 — CLI breakpoint/watchpoint ID 空间冲突**：
- 旧行为：breakpoint 与 watchpoint 各自独立编号，`del <id>` 总命中 breakpoint，
  无法按 id 删除 watchpoint。
- 修复：`DebugSession` 用**单一 id 分配器**（`next_id_`），breakpoint 与
  watchpoint 的 id 全局唯一、不重用；CLI `del <id> | del b <id> | del w <id>`：
  裸 `del <id>` 按统一 id 删除，`del b/del w` 限种类、跨种类 id 报错。
- 回归测试：`dbg_breakpoint_watchpoint_shared_id_pool`（bp=1、wp=2、bp=3 顺序
  分配；`remove_breakpoint(2)` / `remove_watchpoint(1)` 跨种类失败；删除后新分配
  id=4 不重用）。

**门禁重验（2026-08-16）**：CPU 侧全量通过 ——
- CTest **25/25**（`tools/run_semu_cpu_gate.sh`，`ctest` 本机不可用，直接驱动
  测试二进制 + python 驱动；normal / ASan+UBSan / TSan 三个构建树各自 **25/25**）。
- fuzz_phase5 **gpu=False**（非 GPU 参考 oracle 模糊）：n=40 + mutation
  **108/108**、0 errors。
- `l1tex_oracle` **C++==Python**（frozen jsonl 数据，非实时 GPU）：
  **1941/1941**（affine/near/token exact + random 一致）。
- **GPU 侧门禁挂起**：本机 **GPU0（RTX 5090, sm_120）已拆走**，仅剩 RTX 2080 Ti
  （sm_75，不能运行 sm_120 验证）——diff_phase5 的 **GPU differential**、
  `l1tex_oracle` 的 **GPU 采样部分**、fuzz 的 **--gpu 模式**本轮全部跳过，
  待 5090 回归后补跑（见下方 Phase 7 状态更新）。

### Phase 7 状态更新（2026-08-16）— GPU0 拆走，GPU differential 挂起

**状态**：Phase 7 实现 + codex 复验修复（第 1 轮 2 Blocker + 3 Medium，第 2 轮
2 Blocker + 1 High + 1 Medium，第 3 轮 1 Medium —— local memory CLI/help 与文档
残留 lane 声明，见上）全部落地，CPU 侧门禁全绿。**本机 GPU0
（RTX 5090 / sm_120）已拆走**，只剩 RTX 2080 Ti（sm_75），
**sm_120 硬件验证全部挂起**：
- diff_phase5 的 GPU differential（此前 Phase 5/6 为 484/484）—— 待 5090 回归后补跑；
- l1tex_oracle 的 GPU 采样（840/365/216/520 中的 GPU-exact 部分，本轮用 frozen
  jsonl 数据只做 C++==Python 1941/1941）—— 待 5090 回归后补跑；
- fuzz_phase5 的 `--gpu` 模式 —— 待 5090 回归后补跑。
CPU 侧：CTest **25/25**（normal/ASan/UBSan/TSan 三树，含 CLI help golden 断言）、
fuzz **gpu=False** + mutation **108/108**（0 errors）、
l1tex_oracle **C++==Python 1941/1941**；`sim.py` 未修改。

### Phase 7 codex 复验第 2 轮修复（2026-08-16，semu 实现者）

codex 复验 Phase 7 第 2 轮发现 **2 Blocker + 1 High + 1 Medium**，全部修复并在
本节落地。改动文件：`semu/src/interpreter.cpp`、`semu/src/debugger.cpp`、
`semu/include/semu/interpreter.hpp`、`semu/include/semu/debugger.hpp`、
`semu/cli/main.cpp`、`semu/tests/test_debugger.cpp`、`semu/tests/test_interp.cpp`；
`sim.py` 未修改。

**Blocker-1 — mnemonic breakpoint 未比较 mnemonic**（`debugger.cpp`）：
- 旧行为：`Breakpoint::matches()` 对 `kMnemonic` 类型只检查目标字符串非空，从不与
  待执行指令的 mnemonic 比较；调用点（continue 路径）也没有传指令 mnemonic。于是
  `break mnem STG` 会在任意第一条指令（如入口 S2R）停车，既有测试
  `dbg_breakpoint_cta_warp_lane_condition` 用入口 S2R 测 S2R breakpoint，因此检不出。
- 修复：`matches()` 新增 `f_mnemonic` 参数，`kMnemonic` 分支要求
  `mnemonic == f_mnemonic`（`f_mnemonic` 为空或不等都返回 false）；调用点传入
  pre-exec 回调里的 `inst.mnemonic`。`dbg_breakpoint_cta_warp_lane_condition`
  因此真正验证 mnemonic 比较。
- 回归测试：
  - `dbg_mnemonic_breakpoint_compares_mnemonic`（新增 MOV32I→MOV32I→IADD3→STG
    kernel：`break mnem STG` 只在 STG（pc 0x30）停车，MOV/IADD3 均不停车，
    executed_count==3；继续 step-over 后 Done，global[0x40]==0x1239）。
  - `dbg_mnemonic_breakpoint_nonexistent_target_runs_to_done`（`break mnem MUFU`
    对不含 MUFU 的 kernel 一路跑到 Done、STG 照常提交、无 fault）。

**Blocker-2 — barrier deadlock 被报成 Done**（`debugger.cpp:597` + `interpreter.cpp`）：
- 旧行为：`drive_group` 在 `step_group` 返回 false 且 `focus_blocked==false` 时
  无条件 `done_=true` + `kDone`；barrier-deadlock 扫描只在正常运行路径
  `run_owned` 的循环后执行。真正 barrier deadlock 的 launch 被调试器报为正常完成，
  违背 fault-stop 契约。
- 修复：抽取 Interpreter **公共终态分类接口** `ExecutionTerminalState`
  （`kRunning/kDone/kBarrierDeadlock/kNoProgress/kFocusBlocked`）+
  `terminal_state(eligible)` + `barrier_deadlock_fault()`；调度扫描抽取为
  `scan_schedule`（`next_group` 与 `terminal_state` 共用，避免两份逻辑漂移）。
  - `next_group` 空时若存在 barrier 等待 → `kBarrierDeadlock`；sync-wait 无活 lane
    → `kNoProgress`；否则 `kDone`；filter 排除全部 runnable → `kFocusBlocked`。
  - 调试路径复用：`drive_group` 在 step_group false 且非 focus-blocked 时调用
    `terminal_state()`，`kBarrierDeadlock`/`kNoProgress` 置 `terminal_fault_` 并报
    `kFault`（消息与正常运行路径一致，`barrier_deadlock_fault()` 共享）；
    只有 `kDone` 才 latch `done_` + `kDone`。
  - 正常运行路径 `run_owned` 同步改用同一分类（行为不变：clean done 仍无 fault、
    barrier deadlock 仍报同一 fault；新增强化：sync-wait 卡死现在报 kNoProgress
    fault 而非干净完成）。
- 回归测试：
  - `dbg_continue_run_barrier_deadlock_reports_fault`（warp 0 停在 BAR.SYNC 0、
    warp 1 @!P0 EXIT 不到达：`continue_run()` 报 `kFault` +
    `FaultKind::kBarrierDeadlock`，`faulted()==true`、`finished()==false`、状态可查，
    再次 drive 仍报同一 fault）。
  - `interp_terminal_state_classification`（直接构造调度状态驱动四种分类：
    新鲜 launch `kRunning`、仅 warp 1 可跑时 filter 到 warp 0 `kFocusBlocked`、
    barrier 等待 `kBarrierDeadlock` + `barrier_deadlock_fault()` 消息、
    sync-wait 无活 lane `kNoProgress`、全退出 `kDone`）。

**High-1 — `MemoryScope::lane` 不参与 local memory 定位**（`debugger.cpp:1024/1097`）：
- 旧行为：`read_memory`/`write_memory` 的 local 路径最终都访问同一个
  `ws.local[address]`，lane 0 与 lane 1 指向相同字节；而 header 声称
  CTA+warp+lane/thread+offset 精确定位，声明与实现不一致。
- 修复（选型 2）：本 sim 的 local 模型**明确是 per-warp 窗口**（SIM_PLAN
  "LDL/STL（per-warp local window）"，`WarpState::local`，per-thread frame 由编译器
  把 lane*stride 折进 SASS 地址）。因此**删除 `scope.lane` 与 thread 精确定位声明**：
  - `MemoryScope` 移除 `lane` 成员，注释改为"per-warp 窗口、按 raw byte offset 寻址、
    无 lane 维度"；
  - `debugger.cpp` local 读写删除 lane 校验；
  - CLI `mem` 移除 `--lane` scope 解析（显式拒绝并提示 local 是 per-warp 窗口），
    help 文本同步更新；
- 回归测试：`dbg_shared_local_memory_requires_explicit_scope` 删除 scope.lane=32
  校验块，新增 per-warp 窗口语义断言（同一 (cta,warp) 内不同 offset 各自独立、
  offset 0x100/0x104 写入分别读回、offset 0 不受影响）。

**Medium-1 — 64-bit PC 测试未真实覆盖高位 step-over**（`test_debugger.cpp:1194`）：
- 旧行为：高位 PC 只验证 `write_pc()` 拒绝越界，真正 step-over 仍在 0x50，无法对
  旧 uint32_t `SuspendBp::pc` 形成 mutation 门禁。
- 修复：`SuspendBp` 从 `DebugSession` private 区移到公共头，加 `matches()` 方法
  （完整 64-bit 三元组比较）；`drive_group` 两处 bypass/reset 比较改用它。
- 回归测试：`dbg_suspend_bp_identity_64bit` 直接构造高位 PC（0x100000050）的
  SuspendBp，验证 `matches()` 区分高位/低位（`0x100000050` ≠ `0x50`，uint32_t
  截断回归必被该断言抓住）、邻接高位地址、错 cta/warp 均不匹配。

**门禁重验（2026-08-16，round 2）**：CPU 侧全量通过 ——
- CTest **25/25**（normal / ASan+UBSan / TSan 三树，`tools/run_semu_cpu_gate.sh`）；
- fuzz_phase5 **gpu=False**：n=40 + mutation **108/108**、0 errors；
- l1tex_oracle **C++==Python 1941/1941**（affine/near/token/random 一致）；
- **GPU 侧挂起不变**：GPU0（RTX 5090, sm_120）已拆走，diff_phase5 GPU differential、
  l1tex_oracle GPU 采样、fuzz `--gpu` 仍待 5090 回归后补跑。

### Phase 7 codex 复验第 3 轮修复（2026-08-16，semu 实现者）

codex 复验 Phase 7 第 3 轮只剩 **1 个 Medium**：local memory 的 CLI/help 与文档
仍残留 `scope.lane`/`--lane` 声明 —— 实际 API 早已删除 `MemoryScope::lane`、
CLI 也显式拒绝 `--lane`（round 2 High-1 落地），但**用户可见帮助仍把 `--lane N`
列为合法参数**。全部修复并重跑 CPU 门禁。改动文件：`semu/cli/main.cpp`、
`semu/src/debugger.cpp`、`semu/tests/cli_smoke_test.py`；`sim.py` 未修改。

**Medium-1 — local memory CLI/help 与文档残留 lane 声明**：
- 旧行为：`mem` 的 usage 字符串（`cli/main.cpp`）与 `help` 命令的 `mem` 行仍印
  `[--lane N]` / `[--cta N [--warp N [--lane N]]]`，让用户以为 memory scope 支持
  lane 维度；而 `parse_scope` 实际显式拒绝 `--lane`（local 是 per-warp 窗口）。
- 修复：
  - `cli/main.cpp` `mem` usage 与 `help` 的 `mem` 行删除 `[--lane N]`
    （`mem <g|s|l|c> <addr> [len] [--cta N] [--warp N]`；`help` 行
    `mem <g|s|l|c> <addr> <len> [--cta N [--warp N]]`）—— 保留最后的
    `conds: --cta N --warp N --lane 0xMASK`，那是 breakpoint/watchpoint 的
    lane mask，不是 memory scope；
  - 两处 scope 解析错误串 `bad scope tokens (--cta/--warp/--lane)` 改为
    `(--cta/--warp)`（`--lane` 不是合法 scope token）；
  - `debugger.cpp` `scope_cta_index` 注释更新：不再声称 "`scope.lane`, when set,
    must be a real lane of the warp"（该字段已删除）；
  - `SIM_PLAN.md` round 1 Blocker-2 验收记录明确标为已被 per-warp 选型替代
    （见上方 ⚠️ 注）。
- 回归测试：`cli_smoke` 新增 **CLI help golden** 断言 —— 驱动 `semu debug`
  REPL（assembler 生成的 cubin）执行 `help` / `mem`：
  - memory scope 帮助（`mem` 行 + `mem` usage）**不出现 `--lane`**；
  - breakpoint/watchpoint conditions 帮助（`conds:` 行）**仍保留 lane mask**
    （`--lane 0xMASK`，且是全帮助中唯一出现 `--lane` 的地方）。

**门禁重验（2026-08-16，round 3）**：CPU 侧全量通过 ——
- CTest **25/25**（normal / ASan+UBSan / TSan 三树，`tools/run_semu_cpu_gate.sh`；
  CLI help golden 并入 `cli_smoke`，计数不变）；
- fuzz_phase5 **gpu=False**：n=40 + mutation **108/108**、0 errors；
- l1tex_oracle **C++==Python 1941/1941**（affine/near/token/random 一致）；
- **GPU 侧挂起不变**：GPU0（RTX 5090, sm_120）已拆走，diff_phase5 GPU differential、
  l1tex_oracle GPU 采样、fuzz `--gpu` 仍待 5090 回归后补跑。

### Phase 8 — Profiler 与访存原因分析

#### 实现内容

定义 backend-neutral execution/memory event stream。interpreter 产生事件，分析器订阅事件，不反向影响执行。

Shared LDS/STS 模型：

- 32 个 bank，`bank = (byte_address / 4) % 32`。
- scalar/v2/v4 分别按 whole/half/quarter-warp 分组。
- 区分 same-word broadcast/coalescing 与 same-bank distinct-word conflict。
- 输出每个 pass、冲突 lane、bank、word 和原因链。

Global LDG/STG 模型：

- 输出 useful/requested bytes、32-byte sectors、128-byte lines、跨界和 overfetch。
- 输出 lane-to-sector/line 映射和 coalescing efficiency。
- L1 data-bank 与 tag-bank 分析独立报告，避免与 shared conflict 混同。

L1TEX/L2 分层模型：

- L1TEX 是 per-SM 模型，输入为 4 条 subcore-ordered memory stream；分别报告每
  subcore serialization、四路 arbitration、data-bank/tag-bank、sector 合并和
  miss/bypass 原因。报告必须携带 `sm_id`、`subcore_id` 和模型映射版本。
- L1TEX 产生的 L2 request 是层间接口，不以 L1 完成顺序冒充跨 SM 全序。
- L2 是 event-based 跨 SM 模型，聚合 request/sector/line、atomic serialization、
  completion dependency 和可选 cache-state 推断；首版仅对有证据的事件关系给出
  exact 结果，latency/replacement 等未知项标记 approximate/unsupported。
- profiler 输出分别提供 `l1tex.per_sm/per_subcore` 与 `l2.global_events`，禁止把
  L1 bank conflict、shared bank conflict 和 L2 request contention 合并为同一计数。

LDGSTS 模型：

- 参考实现为 `~/cs/projects/arch/l1tex/unified_model.py`（**不是** `model.py`）：
  前者只有一条核心规则 `SharedWf = read_waves + write_waves - largest_joint_fiber`，
  在结构化 pattern（affine/near-linear/equality/token-accumulator）上精度远优于后者；
  后者的大量 selector/特判是为随机数据精度服务，不使用。
- 输出 `SharedWf`、`SharedConf`、`GlobalConf`、`TWf`、`Sectors`、`TagConf` 和 `TSetAcc`。
- 按 `notes/sm90/arch/shared_bank_conflicts.md` 记录模型适用范围。
- scattered 8/16B、miss-path suppression 和 `.cg` bypass 等未闭合路径标记为 `approximate` 或 `unsupported`。

输出支持按 PC、variant、kernel 和 memory space 聚合的 text/JSON report，以及可选逐事件 trace。每项推断携带 model version、适用条件、confidence 和 reason。

#### 验证方式

- shared stride 1/2/4/8/16/32/33、broadcast 和 partial mask。
- 32/64/128-bit shared load/store golden cases与 `shared_bank_conflicts.md` 一致。
- global contiguous、strided、broadcast、misaligned 和 sector/line crossing。
- LDGSTS corpus 与 Python reference model 逐字段比较。
- 从 `~/cs/projects/arch/l1tex/model.py` 提取 4/8/16-byte lane-group、T-stage、
  read/write pass golden；在 4-subcore 输入排列下验证单流结果不变且跨流仲裁可解释。
- 构造 1/2/4 个 SM 的相同 L2 event multiset，打乱宿主 worker 到达顺序后，
  deterministic 模式的规范化 L2 trace 与聚合计数保持一致。
- 已知近似路径必须携带 confidence 标签，不能进入 exact bucket。
- 同一 kernel profiler on/off 的功能输出一致。

#### 退出条件

- 任意已支持 memory instruction 都能解释哪些 lane、地址、bank/sector 导致计数。
- JSON schema 有固定版本和兼容性测试。
- profiler 不改变指令调度、内存值或 fault。
- 每个 L1TEX 结论能追溯到 SM/subcore serialization；每个 L2 结论能追溯到输入
  event 与因果边。无法追溯的派生计数不得进入稳定 JSON schema。

#### Phase 8 完成记录（2026-08-16）

实现内容（全部落地于 `semu/`，`sim.py` 未修改）：

- **Backend-neutral event stream**：`MemoryEvent` 扩展 `lane_ranges`（逐 lane 已提交
  byte range）+ `address_space` + `is_write` + `ldgsts_goff/soff`；interpreter 在
  每个已提交访存点采集逐 lane 有效地址（committed-access 语义，与 race/L2 一致），
  分析器只订阅不反写执行 —— profiler on/off 功能输出逐字节一致。
- **Shared LDS/STS 模型**（`shared_bank.hpp/cpp`，`shared-bank-v1`）：32 bank
  `(byte/4)%32`；4/8/16 B 按 whole/half/quarter-warp 分组；区分 same-word
  broadcast/coalescing 与 same-bank distinct-word conflict；输出每个 pass、
  冲突 lane/bank/word/原因链。stride 1/2/4/8/16/32/33、broadcast、partial mask、
  32/64/128-bit golden 全部通过。
- **Global LDG/STG 模型**（`global_model.hpp/cpp`，`global-coalesce-v1`）：
  useful/requested bytes、32-B sectors、128-B lines、跨界、sector/line overfetch、
  lane→sector/line 映射、coalescing efficiency；L1 data-bank 与 tag-bank 独立报告，
  不与 shared conflict 混同。contiguous/strided/broadcast/misaligned/sector-line
  crossing 全部通过。
- **L1TEX/L2 分层**：L1TEX per-SM/per-subcore 报告（4 条 subcore-ordered stream，
  逐 subcore serialization、四路 arbitration 策略标注、sector 合并、miss/bypass
  原因，携带 sm_id/subcore_id/`l1tex-hierarchy-v1`/`warp%4` mapper 版本）；L2
  event-based 跨 SM 聚合（request/sector/line、atomic serialization、
  completion dependency、可选 cache-state 推断，latency/replacement 标
  approximate/unsupported）。`l1tex.per_sm/per_subcore` 与 `l2.global_events`
  分开输出；shared bank conflict / L1 data-tag bank / L2 request contention 为
  三个独立计数，绝不合并。
- **LDGSTS 模型**（`UnifiedV1Estimator::estimate_ldgsts`，基于
  `unified_model.py`，**不是** `model.py`）：输出 SharedWf/SharedConf/GlobalConf/
  TWf/Sectors/TagConf/TSetAcc；TWf/TagConf/TSetAcc/Sectors 为 exact-empirical
  纯计数（520/520 与硬件 corpus 一致）；SharedConf/GlobalConf 为定义性
  approximate；`.cg` bypass → unsupported；structured/scattered 由
  SharedWf confidence 区分。
- **报告**：按 PC/variant/kernel/space 聚合的 text/JSON report（schema
  `1.0`，固定版本 + `tools/profiler_report_test.py` 兼容性测试）；每项推断携带
  model version / 适用条件 / confidence；CLI `run --profile` 直接输出 profiler
  block。4-subcore 排列下单流结果不变、跨流仲裁可解释；1/2/4 SM 相同 L2 event
  multiset 打乱到达序后 deterministic 规范化 L2 trace 与聚合计数一致。

验证（CPU 侧全量通过，三树）：

- CTest **29/29**（normal / ASan+UBSan / TSan，`tools/run_semu_cpu_gate.sh`；
  新增 `cpp/shared_bank`、`cpp/global`、`cpp/profiler` + `profiler_report`
  Python gate）；
- fuzz_phase5 **gpu=False**：n=40 + mutation **108/108**、0 errors；
- l1tex_oracle **C++==Python 1941/1941** 无回归；
- LDGSTS corpus（data4/8/16_ldgsts_warmldg.jsonl）：base **C++==Python
  520/520**；TWf/TagConf/TSetAcc/Sectors **== hardware meas 520/520**；
  confidence-label 检查 520 rows；
- profiler schema v1.0 兼容 + 报告确定性通过。
- **GPU 侧挂起不变**：GPU0（RTX 5090, sm_120）已拆走，diff_phase5 GPU
  differential、l1tex_oracle GPU 采样、fuzz `--gpu` 仍待 5090 回归后补跑。

未解决项：LDGSTS SharedConf/GlobalConf 为定义性计数（不在 exact bucket）；
scattered 8/16B、miss-path suppression、`.cg` bypass 的完整 wavefront/conflict
计数标记 approximate/unsupported，按 `shared_bank_conflicts.md` 记录。

#### Phase 8 codex 复验修复记录（2026-08-16，2 Blocker + 4 High + 2 Medium）

codex 对 Phase 8 逐字段复验后发现 2 Blocker + 4 High + 2 Medium，全部修复并重跑
全量门禁。改动：`memory_events.hpp` / `interpreter.cpp` / `profiler.hpp/cpp` /
`global_model.hpp/cpp` / `l2_events.cpp` / `test_profiler.cpp` /
`test_global.cpp` / `tools/profiler_report_test.py` /
`tools/profiler_schema_v1.0.json`。`sim.py` 未修改。

**Blocker-1 — L1TEX subcore 确定性仲裁**（`profiler.cpp`）：miss/bypass 分析必须
消费 **deterministic arbitrated order**，而非原始 host event list 顺序 —— 每个
subcore 内按 `(issue_tick, event_id)` 排序，四路按 `(issue_tick, subcore_id)`
K-way merge（issue-tick round-robin）；所有 stateful cache/miss 判定（resident
128-B line、compulsory-miss 归属）都基于该 merged order，miss 归属对 host 侧
event-list 任意排列不变。旧实现直接按宿主数组顺序做 miss 归属，同一 multiset 不同
排列产生不同 attribution。新测试
`profiler_l1tex_miss_attribution_arrangement_invariant`（同 line 双 subcore，
最低 issue_tick 的 subcore 得 compulsory miss，任意排列 attribution 一致）。

**Blocker-2 — LDGSTS policy-confidence ABI**（`memory_events.hpp` +
`interpreter.cpp` + `profiler.cpp`）：`cache_policy` 由 FORMAT `loc` slot 派生
（`LOC@BYPASS` → `"cg"`、`LOC@ACCESS` → `"default"`）并随事件携带；`variant_class`
（如 `ldgsts__RR32U`）在每条 L1TexIssue 填充，分析器不再需要重新解码原始 word。
Analyzer 必须 honor policy：`.cg` 路径下 LDGSTS 的 SharedWf/conflict 计数标
`unsupported`，纯计数（TWf/TSetAcc/Sectors/TagConf）保持 `exact-empirical`，且与
default-policy 条目分离聚合。新测试
`profiler_ldgsts_cg_bypass_negative`（真实 interpreter `LDGSTS.E.BYPASS.128`
事件端到端流进 profiler JSON，携带 cache_policy、variant class、degraded
confidence）。

**High-1 — global 字节定义**（`global_model.cpp`）：byte 计数显式 denominated ——
`lane_requested_bytes`（逐 lane width 之和）与 `unique_useful_bytes`（distinct
byte union）绝不互相比较；overfetch 只对 useful bytes 计算。broadcast golden 修正为
efficiency `0.125`（4 useful / 32-byte sector），旧 golden `32.0` 是把 union 与 lane
sum 误比的结果。测试 `global_broadcast` 锁定该口径。

**High-2 — 跨 line 拆分**（`global_model.cpp` + `test_global.cpp`）：data-bank
pass/conflict 按每个 lane 的 **128-B line fragment** 分组；不同 line 永不共享 data
bank，故跨 line 同 bank 异 word **不算** conflict（旧实现跨 line 合并
`words_per_bank`，把 2 个伪 conflict 报出来）。新测试
`global_cross_line_bank_no_conflict`；并把 stale 的 `global_strided` golden 从
16 修正为 0（stride-8 跨 2 个 line，每 line 16 个互异 even bank → 2 pass、0
conflict，与跨 line 规则一致）。

**High-3 — variant 聚合**（`profiler.cpp`）：aggregate key 加入 `variant_class` 与
`cache_policy`（`space|mnemonic|variant|cache_policy|pc`），不同 encoding variant
同 mnemonic+pc 时**绝不 merge**（旧实现只按 pc/mnemonic 聚，把 RR 与 RR32U 混在一个
条目）。测试 `profiler_variant_aggregation_and_atomic_chain`。

**High-4 — L2 completion dependency**（`profiler.cpp` + `l2_events.cpp`）：L2
聚合**验证** request→completion 的 one-to-one 契约 —— 每条 completion 必须引用
live request、同一 request 不能被完成两次、parent L1 event 必须匹配；同 sector 的
atomic 在 deterministic L2 completion order 下成串行链。新增
`orphan_completions` / `duplicate_completions` / `completion_edges` /
`atomic_serialization_chains` 计数。新测试
`profiler_l2_orphan_duplicate_completions`（orphan=2、duplicate=1、valid edge=1、
parent mismatch 计入 orphan）。

**Medium-1 — schema golden**（`tools/profiler_report_test.py` +
`tools/profiler_schema_v1.0.json`）：schema 门禁不再只查 pc/mnemonic/space/events
子集 —— 加载完整 canonical schema golden，每个 REQUIRED 字段做
presence+type+enum 检查；未知**额外**字段容忍（forward-compatibility：producer 可
加字段而不破坏旧 validator）。schema 版本固定 `1.0` 并带 meta 字段。

**Medium-2 — JSON escaping**（`profiler.cpp`）：统一 `json_escape()` 处理所有
string 字段（kernel/mnemonic/variant/space/confidence/...），引号/反斜杠/控制字符
不再破坏 report 文档。新测试 `profiler_json_escape_special_chars`（escaping
round-trip、无字面换行泄漏进文档）。

**门禁重验（2026-08-16，三树重建后）**：CTest **29/29**（normal / ASan+UBSan /
TSan 三个构建树各自 **29/29**，`tools/run_semu_cpu_gate.sh`）；fuzz_phase5
**gpu=False** n=40 + mutation **108/108**、0 errors；l1tex_oracle **C++==Python
1941/1941**（840/365/216/520）；LDGSTS corpus **C++==Python 520/520**、纯计数
TWf/TagConf/TSetAcc/Sectors **== hardware meas 520/520**、confidence-label 检查
520 rows；profiler schema v1.0 兼容 + 报告 deterministic；ASan/UBSan/TSan 日志无
sanitizer 报告。`sim.py` 未修改。

#### Phase 8 round-3 修复记录（2026-08-16，2 个 L2 profiler 测试失败）

定位到 `profiler.cpp` 两处 L2 atomic serialization / completion 逻辑缺陷，新
失败断言（`semu_test_profiler`）为：

- `test_profiler.cpp:938`：`rep2.l2.atomic_serialization_chains == 1` —— 期望
  同 sector 两个已完成的 atomic 串成一条链，实际为 0；
- `test_profiler.cpp:1127`：`summarize(arr) == canonical`（3 个 host 排列均失败）
  —— 期望 `chains=1,edges=2,requests=4,completion_edges=4` 与排列无关。

根因：

- **atomic 属性取错对象**（High-4 遗留）：虚拟链成员资格取自 **completion** 事件
  的 `request_kind`；`test_profiler.cpp:891` 的 completion 合法地不携带
  `request_kind`（默认空串），于是 `atomic_seq` 从未填充、链恒为 0。atomic 归属
  必须来自 completion 所完成的 **request** 的身份。
- **completion 匹配依赖单遍宿主顺序**（循环缺陷）：原本在 pass-1 单循环里当
  completion 到达时才查 `l2_requests`；completion 排在 request **之前**
  （反转/交错/乱序到达等合法排列）就会被误判为 orphan，导致 completion_edges、
  链成员缩减 —— 与“permutation invariant”契约直接冲突。

修复（`profiler.cpp`，`sim.py` 未修改）：

- `L2RequestState` 增加 `request_kind` 字段（request 身份的一部分），request 分支
  记录它；
- pass-1 拆成 **1a + 1b 两遍**：1a 处理 trace、L2 **request** 记账、L1TexIssue 聚合
  （全部与顺序无关）；1b 单独遍历 **completion**，对**完整** request 表做 one-to-one
  校验 —— 只有 request id 在整个事件表里从来不存在才叫 orphan，先到/后列不是缺陷；
- 虚拟链的 atomic 判定与 `atomic_seq` 记录改从 `it->second.request_kind`（即
  request 身份）读取，completion 的 `issue_tick`（确定性 L2 完成序）仍为链序来源。

回归语义保持不变：orphan（id 不存在 / parent/sector/SM 身份不匹配）、duplicate
（同一 request 第二次完成）、duplicate request（首见身份为准）计数与既有测试
`profiler_l2_orphan_duplicate_completions`、`profiler_l2_duplicate_request_and_
identity` 全部一致。

**门禁重验（2026-08-16，round-3 三树重建后）**：`semu_test_profiler` 全过；
CTest **29/29**（normal / ASan+UBSan / TSan 三树各自 **29/29**，
`tools/run_semu_cpu_gate.sh`）；fuzz_phase5 **gpu=False** n=40 + mutation
**108/108**、0 errors；l1tex_oracle **C++==Python 1941/1941**
（840/365/216/520）；LDGSTS corpus **C++==Python 520/520**、纯计数
TWf/TagConf/TSetAcc/Sectors **== hardware meas 520/520**、confidence-label 检查
520 rows；profiler schema v1.0 兼容 + 报告 deterministic；ASan/UBSan/TSan 日志无
sanitizer 报告。`sim.py` 未修改。

#### Phase 8 B1/H1 收尾记录（2026-08-16，prediction-unavailable L1 建模 + atomic 边身份）

```
B1（coupled LDGSTS prediction==false 不得污染 L1 line/sector/cache 状态）与 H1
（atomic serialization 显式边身份）在本轮补全：schema 已在上轮落地，本轮确认实现、
补齐端到端测试并重跑全量门禁。改动：`tools/profiler_schema_v1.0.json`（上轮）、
`semu/tests/test_profiler.cpp`（本轮）。`profiler.cpp` 的 B1/H1 实现已在 round-3
随 code comment 落地，本轮逐条复核确认。`sim.py` 未修改。
```

- **schema（上轮已落地，确认通过）**：`profiler_schema_v1.0.json` 在
  `subcore_entry` 增加 REQUIRED `prediction_unavailable_reasons`（string 数组）；
  在 `l2_entry` 增加 REQUIRED `atomic_serialization_edges_list`（`atomic_edge`
  数组），`atomic_edge` 定义 `from_request_id`/`to_request_id`/`sector`/
  `from_seq`/`to_seq` 五个 REQUIRED 整数字段。schema JSON 校验 + 兼容测试通过。
- **B1 实现确认（`profiler.cpp` pass 2）**：`ev->coupled_l1_to_shared &&
  !ev->prediction` 的事件在 L1TEX 逐事件分析中直接 `continue` —— address
  computation overflow / invalid lane 时 goff/soff 为无效占位零偏移，绝不进入
  128-B line / 32-B sector / resident-line 状态建模（否则会把 line 0 虚造成
  resident、产生伪 compulsory miss、并把后续真实 line 0 访问错判为 hit）；事件改
  计为 `sc.prediction_unavailable` 并记录 `prediction_unavailable_reasons`
  （cap 8 条/子核）。aggregate 侧的 `prediction_unavailable_events` 与字段
  unsupported 置信度由 round-2 H1 路径负责，两者独立。
- **H1 实现确认（`profiler.cpp` pass 1b）**：`AtomicSerializationEdge` 列表
  （`atomic_serialization_edges_list`）为每条边携带显式身份 —— from/to request
  id、串行化 sector、两端确定性 L2 completion seq；链成员排序为
  `(completion_seq, request_id)`，completion seq 相同（tie）时按 request id 断序；
  `atomic_serialization_edges == edges_list.size()`；JSON comport、text report
  均输出每条边的 `from->to@sector(seq->seq)`。
- **新测试（`semu/tests/test_profiler.cpp`，profiler 套件 18→20）**：
  - `profiler_l1tex_prediction_unavailable_does_not_pollute_resident`：
    invalid LDGSTS（goff 全 0 = 占位 line 0，subcore 0，tick 0）之后真实 default
    访问 line 0（subcore 1，tick 1）仍 **compulsory miss**（sc0 n1/L0，sc1 m1/L1）；
    正序/反转排列 attribution 逐字节一致；同 subcore 双 invalid + 真实访问
    m1/n2/L1；占位 line 0 不进入任何 subcore/SM line 列表；JSON 含
    `prediction_unavailable`、`prediction_unavailable_reasons`（reason 串带
    sm/subcore 身份）。
  - `profiler_l2_atomic_chain_edge_identity`：同一 sector 0x20 的 4 个 atomic
    A=rid1/B=rid2/C=rid3/D=rid4，completion seq C=1/A=2/B=3/D=3 —— B/D 平局经
    `(completion_seq, request_id)` 断为 2<4 —— 断言精确三条边
    `3->1@32(seq1->2);1->2@32(seq2->3);2->4@32(seq3->3)`；4 种 host 排列
    （正序/反转/请求前置完成乱序/完成先于请求到达）边身份逐字节一致；JSON 含
    `from_request_id`/`to_request_id` 边项；另覆盖无平局的 C→A→B 两条边子例。
- **门禁重验（2026-08-16，B1/H1 收尾三树重建后）**：CTest **29/29**（normal /
  ASan+UBSan / TSan 三个构建树各自 **29/29**，`tools/run_semu_cpu_gate.sh`）；
  fuzz_phase5 **gpu=False** n=40 + mutation **108/108**、0 errors；l1tex_oracle
  **C++==Python 1941/1941**（840/365/216/520）；LDGSTS corpus **C++==Python
  520/520**、纯计数 TWf/TagConf/TSetAcc/Sectors **== hardware meas 520/520**、
  confidence-label 检查 520 rows；profiler schema v1.0 兼容 + 报告
  deterministic；ASan/UBSan/TSan 日志无 sanitizer 报告。`sim.py` 未修改。

### Phase 9 — Tensor、TMA 与高级异步语义

#### 实现内容

- 迁移 HMMA/QMMA/OMMA fragment mapping 和位精确数学模型。
- 支持相关 FP16/BF16/FP8/tensor formats。
- 实现 LDGSTS async、mbarrier、UTMALDG、UTMASTG、UTMAREDG、cluster/shared proxy。
- 支持 tensor map 参数 blob 和必要 descriptor parsing。
- 将高级指令接入 debugger 和 profiler。

#### 验证方式

- 复用 `test_hmma_model`、HMMA/QMMA precision 和 TMA/mbarrier tests。
- tensor 结果逐 accumulator bit 比较。
- async completion、phase、arrival count、try-wait 和 deadlock tests。
- profiler 验证 TMA/LDGSTS 地址展开与实际 shared/global access set 一致。

#### 退出条件

- 已标为 `functional` 的 tensor/TMA variant 必须有 GPU differential，或在
  capability manifest 中记录显式批准的 GPU waiver（如 OMMA：CPU-only 差分逐
  bit 一致 + user-instructed gpu_waiver，见 Phase 10 冻结范围与 waiver）。
- 异步状态可在 debugger 中完整查看。
- 尚未逆向清楚的 modifier 保持 decode-only，不使用猜测语义。

#### Phase 9 子集修复记录（2026-08-17，semu 实现者，mbarrier 位布局 / SYNCS / init 路径）

**权威 64-bit mbarrier 位布局（本轮落地）**：`bit0=保留`；
`bits[1:20]=Expected`（int20 对 expected 的补码，init(n) 写 `(0x100000-n)&0xFFFFF`）；
`bits[21:41]=tx`（int21）；`bit42=Lock`；`bits[43:62]=Arrive`（int20 对剩余到达数的
补码）；`bit63=Phase`。语义：arrive 使 Arrive 计数到 **0** → phase 翻转 + Arrive
重置为 Expected；只有当 **arrive==0 且 tx==0 双零**才翻转；本 phase 计数已满足后
再次 arrive（over-arrival）置 Lock 并 fault（barrier 永久卡死）；expect_tx 令
tx 朝 -bytes 走、TMA 完成 tx += 量；wait(phase) 满足 parity 即过；SYNCS 在 barrier
cache 内操作、不写回共享内存。`sim.py` 未修改。

- `semu/include/semu/mbarrier.hpp` / `semu/src/mbarrier.cpp`：按上述布局重写
  `encode()`/`from_init_word()`（Expected @[1:20]、tx @[21:41]、Lock @bit42、
  Arrive @[43:62]、Phase @bit63）；over-arrival 置 `locked` 并 fault（配合既有
  `corrupted`=tx-underflow「本次不 trap、下次 op trap」与 `invalid`=CCTL.IV 语义）；
  init(0) 的 canonical word 自带 bit63=1（`0x100000<<43`），phase 0 立即完成
  → parity 读作 1，不再额外翻转。L0 全过。
- `semu/src/interpreter.cpp`（Phase 9 子集 init 路径，mbarrier word 由
  UMOV+UIADD3+USHF 手工构造）：
  - `do_uiadd3`：**URc==255 即视作缺位**，改用 Sb 立即数作第三加数（此前 URc 槽
    带 255 时读到 0，遮蔽了 Sb，导致 `UR12 = 0x100000-1` 算成 0xFFFFFFFF）；
    同时规范 URa/URb/URc==255 的处理。
  - `do_ushf`：移数量从 **Sb**（bits[63:32]）读取（原来找不存在的 `Sh` 槽→ 恒 0），
    方向从 **SDIR**（bit76/memdesc，L=0/R=1）读取（原来按 variant_class 含
    `'R'` 判断，`ushf__URuIUR_URIR` 的类名误命中 → 左移被当成右移）。
  - 清理全部 `DBG*` 调试输出（umov/uiadd3/ushf/mbarrier_at/EXCH/STS/UTMASTG）。
- `semu/tests/test_interp.cpp`：
  - `interp_phase9_utmaldg_load`：修复断言 `shared[0x402]==0x03` → **0x02**
    （正确 tile 布局是 1..8 连续 little-endian f16：`01 00 02 00 03 00 …`，
    0x402 处是 value 2 的低字节）。phase==1 断言随 init 路径修复自然通过。
  - `interp_phase9_utmastg_store`：修正 4 条手写 `MOV32I` 的 32-bit 立即数字段
    （原词把 `0x00020001` 错编成 `0x1`、`0x00040003` 错编成 `0x3` 等——
    bits[63:32] 只写了低 16 位），改为 `0x0002000100007802` 等完整 imm；
    v1==2 / v7==8 随共享数据恢复连续布局通过。
- **门禁**：`semu_test_interp`（69 用例）、`semu_test_mbarrier`（8 用例）全过；
  三树重建后 `tools/run_semu_cpu_gate.sh` **31/31**（normal / ASan+UBSan / TSan
  各自 **31/31**）；fuzz_phase5 **gpu=False** n=40 + mutation **108/108**、
  0 errors；l1tex_oracle **C++==Python 1941/1941**（840/365/216/520）；LDGSTS
  corpus **C++==Python 520/520**、纯计数 TWf/TagConf/TSetAcc/Sectors
  **== hardware meas 520/520**、confidence-label 520 rows；ASan/UBSan/TSan 日志
  无 sanitizer 报告。`sim.py` 未修改。

#### Phase 9 子集修复记录 2（2026-08-17，semu 实现者，tensor 差分门禁打通）

首轮 `tools/tensor_differential_test.py` **68 例全失败**，三类系统性问题全部
定位并修复（GPU0 RTX 5090 已拆走，GPU 侧验证挂起，本门禁为 CPU-only：

**1. harness 的 kernel 名**：`#fn k(out<8>)` 的 ELF 符号名是 **mangled
`_Z1k`**，而 harness 向 `semu run` 传的是裸 `k` → `find_kernel` 精确匹配失败
报 "kernel 'k' not found"（此前 qmma_k16 的非 E4M3/E5M2 用例因加载先失败、
被路径 `kernel '_Z1k' word at +0xd0 decodes as illegal` 掩盖，实际同源）。
复用仓库惯例 `mangle() = _Z<len><name>`，harness 改传 `_Z1k`。

**2. QMMA srcFmt 补丁的位布局**：`qmma_` CLASS 的 ENCODING 把 srcFmtA 放在
[83:82]（高 2 位）+ [78]（低 1 位），decoder/extractor 按 **MSB-first 范围序**
取值 `4*b83+2*b82+b78`。原 harness 按 `bit78<<2 | bits[83:82]` 写位（把 b78
当高位），等于把 3-bit 值做了一次位反转 → 想写 probed 值 5(E3M2) 实际得到
decoder 认可的 raw 3，落入 do_tensor 的 `default → (srcFmtA) decode-only`
fault。修复：`b78 = val&1, bits[83:82] = val>>1`（srcFmtB 同理 @79/[85:84]）。
另核实 decoder/render 对 qmma_ 的 srcFmt 后缀用 sm120 枚举名（如 raw 1 显示
`.E5M2`），而 semu 语义按 probed 映射执行——两者仅命名层不一致，已记录。

**3. 规格可编码性约束（以 sm120.json 为准）**：
- `qmma_` CLASS 条件拒绝 raw 6/7（`INVALID6/7`）→ **E2M1（probed=6）在两种
  shape 上都无法编码**，从 k32 用例撤下。
- 16816 shape 条件 "size 16816 only allows srcfmt E5M2 or E4M3"（按 sm120 枚举
  raw 0/1）→ **k16 只有 probed E4M3(0)/E3M4(1) 可用**，其余四个格式必判
  illegal（这是规格性拒绝，不是 assembler/decoder bug）；k32 可用 probed
  E4M3(0)/E3M4(1)/E2M3(2)/E5M2(4)/E3M2(5)。
- **OMMA 全局布局修正**：kernel 模板的 LDG 布局是 C@words 8-11、Re/Rh@12-13，
  而 harness 把 C 放在 words 6-9、Re/Rh@10-11 → 寄存器里 C 变成
  [C2,C3,Re,Rh]、Re/Rh 读到 0，数值必然不匹配。全局镜像改为 kernel 布局，
  model frag16 保持 `[A,B,Re,Rh,C]`（hmma_model.omma_frag 要求）。
- `semu run` 的 `--global=` 选项必须先于 positional 参数（option parser 在
  首个 positional 处 break），harness 的调用顺序按此调整。

**成果**：`tensor_differential_test.py` **120/120（默认 --trials=6 时为
72/72；25 轮 300/300）0 failures 0 skipped**——HMMA k16/k8 bf16+f16、
QMMA k32×5 + k16×2 格式、OMMA.SF.16864 逐 accumulator bit 与
`hmma_model.py` / `fda_generic` EUC 一致。`semu_test_tensor` 全过。

**能力清单计数更新**：Phase 9 把 dense F32-accumulator tensor shape 标为
`functional` 后，capability manifest 从 1414 decode-only 变为 **1411
decode-only + 3 functional**（HMMA `hmma_x8_`/QMMA `qmma_`/OMMA
`omma_scale_`），`semu/tests/test_core.cpp` 的 `capability_manifest_scale`
断言同步更新。

**门禁（本轮全绿）**：CTest **32/32**（含 `tensor` 用例）、
`tools/run_semu_cpu_gate.sh` **31/31**、fuzz_phase5 **gpu=False** n=40 +
mutation **108/108**（0 errors）、l1tex_oracle **C++==Python 1941/1941**
（含 LDGSTS 520/520）、profiler_report 通过。`sim.py` 未修改。

### GPU 补测收尾（2026-08-18，RTX 5090 回归，semu 实现者）

**环境（新机器）**：GPU0 RTX 5090 回归，driver **590.48.01 / CUDA Version 13.1**；
本地工具链 **CUDA 13.1**（`Build cuda_13.1.r13.1/compiler.37061995_0`，cuobjdump
13.1）。2026-08-16 起因 GPU0 拆走挂起的 GPU 侧门禁本轮补跑；补齐前
`tools/fuzz_phase5.py`、`semu/src/fp.cpp`、`semu/src/interpreter.cpp`、
`semu/include/semu/fp.hpp`、`semu/tests/test_fp.cpp`、
`tests/asm_construct/test_ffma.py`、`notes/sm90/instr/ffma.md` 已就 FMZ/FTZ
语义与 fuzz/asm 用例做过收尾修改（工作树未提交）。`sim.py` 未修改。

**diff_phase5 GPU differential —— 补跑 PASS**：**484/484**（0 failed），逐 word
位精确一致：**480 differential cases + 4 个 runtime-fault checks**（MUFU / FCHK /
IMAD.X / IMAD.WIDE.X 必须报 `UnsupportedInstruction` 且 pc==0、message 含 mnemonic）。
注：harness 收尾打印仍写 `"2 fault checks"`（历史标签），实际
`check_runtime_fault` 计数为 4，480+4=484。覆盖：FFMA/FADD/FMUL 各舍入 + FTZ/FMZ +
SAT（NaN/±inf/-1/±0/0.5/1/>1、inf+(-inf)→+0）；FP64 DMUL/DADD/DFMA（含 2^-53
舍入 boundary × 4 模式）；F64→F16/F32/BF16 直接向下转换（double-rounding trap、
NaN payload、subnormal、overflow 边界 × 4 舍入）；I2F/F2I/F2F 各向；
FSETP/FMNMX/FSEL；整数/位（IADD3 LOP3 SHF IABS POPC PRMT IMNMX IMAD.WIDE IMAD.HI
BMSK LEA P2R）；FP16 subnormal 定向舍入；VOTE/SHFL/ELECT/REDUX collectives
（32-lane）。GPU 侧经 `CudaModule` 共享 driver context 串行跑完（沿用 5090 驱动对
反复 fresh-context teardown 报 ILLEGAL_ADDRESS 的规避），semu 侧逐 lane GPR dump
对照全部一致。

**cuobj_regen（GAP-11）FAIL 判定 —— 工具链版本差异（预授权选项 b：保留 committed
fixture，不提交重建）**：

- **现象**：本地重建 fixture 时 rebuilt word set 与 committed fixture 差
  **170 only-committed / 160 only-rebuilt**。**170/160 全部来自
  `vecmix.cubin`/`vecmix2.cubin`** 两个 regen 源（rebuild 用本地 nvcc 现场重编译
  `semu/tests/data/regen/*.cu`）；五个 committed repo cubin（pmtrig/tma_*）的
  word 逐字节一致。
- **根因**：committed fixture 由旧工具链生成（meta `cuobjdump (CUDA 13.x)`），
  本机为 CUDA 13.1——互补的 nvcc 后端把同一 vecmix 内核编成不同指令流：相同
  (cubin,kernel,pc) 处寄存器分配/划 scheduler/编码不同（如 committed
  `0x7077221/0xfe20000000000` vs rebuilt `0x700077223/0xfce0000000000`）；170 个
  only-committed 中 **23 个与 only-rebuilt 共享同一 lo word**（纯 scheduling 位差）。
  mnemonic 集合高度重合（同批指令类型），是编译器版本变化的典型特征，
  **不是 semu decode/sim 逻辑 bug**。
- **判定依据**：committed fixture 在 decode gate **450/450 全过** + tamper 四类
  篡改（register/modifier/branch-target/extra-operand）全部被拒（gate 非真空通过）。
  而**重建 fixture 反而在 1/440 失败**（gate 忠实报告了新工具链产物）：CUDA 13.1
  的 vecmix 新增一条 `R2P` word，cuobjdump 13.1 按 sm120 spec `r2p__RIR` FORMAT
  槽位打印显式 `PR` 操作数（`R2P PR, R0, 0x3`），semu renderer 不打印 `PR`。解码
  正确（r2p__RIR），属**既有 renderer 打印缺口**被新工具链产物首次触发，
  非重建引入的逻辑错误。
- **处置**：保留 committed fixture（450 words / 旧工具链 provenance），不提交
  CUDA-13.1 重建（会整体替换 word set + 变更 provenance，且 R2P `PR` 打印缺口使
  gate 仍不过）。cuobj_regen 记录为**已知环境差异**：门禁最关心的不变量
  （tma/pmtrig 字节级不变、vecmix 可解码）仍成立，仅编码/调度因编译器版本不同。
  后续若要恢复 CUDA 13.1 下 regen 全绿：给 semu renderer 补 `r2p__*` 的 `PR`
  操作数打印（1 处）后再 rebuild 提交新 fixture。
  - **后续已闭合（2026-08-18，commit 567c30f）**：`r2p__*` 的 `PR` 操作数打印
    缺口补齐，CUDA 13.1 重建 fixture（`cuobj_vectors_sm120.json`）全量通过，
    cuobj_regen 恢复绿色（见 Phase 10 前置项完成记录）。

**补测总结（2026-08-18 全量）**：fuzz **GPU 120/120** + non-GPU n=40 + mutation
**108/108（0 errors）**；CTest 各套件 PASS（唯一未闭合为 cuobj_regen，上述环境
差异，不影响 semu 逻辑；其后 R2P `PR` 打印缺口补齐、cuobj_regen 已恢复绿色，
见 Phase 10 前置项完成记录）；diff_phase5 **GPU differential 484/484**；
decoder_cuobjdump **450/450** + tamper **4/4**；l1tex_oracle **C++==Python
1941/1941**（frozen corpus；GPU 采样属 corpus 采集流程，本 retest 不另行重跑）。
GPU 侧门禁挂起项全部闭合。`sim.py` 未修改。

#### Phase 9 tensor GPU differential（2026-08-18，5090 回归，semu 实现者）

`tools/tensor_gpu_differential.py`（新增，sm120 / RTX 5090）在**真实 GPU**（经
`CudaModule` + hand-built assembler 驱动相同 hand-assembled kernel）与 **semu
interpreter** 上并行跑每个 FUNCTIONAL tensor variant，结果与 Python 参考模型
（`tools/hmma_model.py`）逐 word / 逐 accumulator bit 三方对照。

**结果（`/tmp/tgpu_v5.json`，已保存 `tools/tensor_gpu_differential_report.json`，
2026-08-18 用 v1.1.0 脚本 + seed 0x7E57C0DE 重跑再生、含 provenance）**：
**54/54 checked PASS（0 hard failures；semu == model 逐 bit 一致——CPU gate）**；
**24 skipped（user instructed skip，无 GPU 验证）**；**TMA 3 项 decode-only、
不冻结语义**。旧的 "78/78" 是 54 项真实对照 + 24 项用户指示跳过之和，被跳过项
的"三方一致" 不成立、**不得描述为 GPU validated**。

- **semu == model 54/54（逐 accumulator bit）**：HMMA k16/k8 bf16+f16
  （4 × 6 trial = 24）、QMMA k32 E4M3/E5M2/E3M4（3 × 6 trial = 18）、
  QMMA k16 E4M3/E5M2（2 × 6 trial = 12）；每项断言
  semu result == Python model，word-for-word。
- **GPU==semu==model 三方一致 51/54**；其余 3 条全在 **E5M2**（fp8 带显式
  ±inf/NaN 编码，accumulation 特例 lane 的 inf/NaN 符号约定与模型不同）：
  `qmma_k32_e5m2_t2`（+inf→-inf）、`qmma_k32_e5m2_t4`（-inf→+inf）、
  `qmma_k16_e5m2_t3`（-inf→NaN）——记录为 `gpu_only_note`，**非阻塞 warning**
  （semu==model 不受影响），report 逐项列出。
- **24 skipped = user instructed skip（e3m2/e2m3/omma，无 GPU 验证）**：
  `qmma_k32_e3m2`、`qmma_k32_e2m3` 各 6 trial、`omma_k64` 12 trial。用户在
  e3m2/e2m3/omma 上前述差分（见修复记录 2）已批准为跳过项，CPU-only 门禁仍
  覆盖其 bit 精确一致性，但**这三个格式在 GPU 侧未跑、无 GPU 验证，不得描述为
  GPU validated**（QMMA k32 在 GPU 侧仅有 E4M3/E5M2/E3M4 三种格式闭合；
  OMMA.SF.16864 不具 GPU 三方一致证据）。
- **TMA 3 项（utmaldg/utmastg/utmaredg）decode-only、不冻结语义**：`ok=false,
  unclosed=true`。GPU 侧已产出 observable 内存镜像，但 semu 侧存在已知缝隙
  （utmaldg 报 `mbarrier not initialized`、utmaredg 报 `element size != 4 is
  decode-only`），故 GPU image == semu image 尚未闭合——按 Phase 9 退出条件，
  TMA 的 non-blocking 完成语义标为 decode-only（非 functional、不冻结），
  不强行猜测。
- `semu_test_tensor` 已注册 CTest（`add_test(NAME tensor ...)`，
  `semu/tests/CMakeLists.txt`），`tensor_differential` 亦注册 CTest（`add_test`
  + `tools/run_semu_cpu_gate.sh` 的 `tensor_differential` 项）。`sim.py` 未修改。

#### Phase 8 `.cg` bypass —— 功能 vs 模型 confidence 区分（2026-08-18）

`.cg` bypass 的**功能语义**与**profiler 计数精度**是两回事，分别记录：

- **功能层（functional）**：`LDGSTS.E.BYPASS` 在 interpreter 中作为真实内存访存
  执行（`profiler_ldgsts_cg_bypass_negative` 用例覆盖真实
  `LDGSTS.E.BYPASS.128`），地址展开 / shared/global access set 正确——功能已闭合。
- **模型 confidence 层（profiler 计数）**：`.cg` bypass 路径下
  SharedWf/conflict 计数**维持 `unsupported`**（见 §5 LDGSTS 初始分级与
  profiler 策略：Analyzer honor policy，`.cg` 路径的完整 wavefront/conflict
  计数不生成）。这是**模型精度分级**的未闭合，不是功能缺失，不影响 deepcopy
  往返 / race 语义。两者在本次同步中明确区分，避免把"计数 unsupported"误读为
  "功能未实现"。

#### Phase 10 前置项完成记录（2026-08-18）

Phase 9/8 的所有 GPU 侧挂起前置项至此闭合，Phase 10 可开始：

- Phase 5 diff_phase5 GPU differential **484/484**（含 4 runtime-fault checks）。
- Phase 5 fuzz `--gpu` **120/120** + 非 GPU n=40 + mutation 108/108。
- Phase 7/8 l1tex_oracle **C++==Python 1941/1941**（frozen corpus）。
- Phase 9 tensor differential GPU 侧 **54/54 checked PASS 0 hard failures**
  （semu==model 逐 bit；51/54 GPU 三方一致 + 3 条 E5M2 inf/NaN 符号约定差异
  为 GPU-only warning；24 user-skip 无 GPU 验证 + TMA 3 decode-only 除外）。
- **cuobj_regen 已恢复绿色**：R2P `PR` renderer 打印缺口补齐（见下述记录），
  CUDA 13.1 重建 fixture 全量通过。
- 已知非闭合仅剩：tensor e3m2/e2m3/omma user-skip（无 GPU 验证，不得描述为
  GPU validated）、TMA non-blocking（decode-only）。`sim.py` 未修改。

### Phase 10 — 稳定化与 JIT 接口冻结

#### 实现内容

- 冻结 `IBackend`、decoded IR、runtime services、event stream 和 fault ABI。
- 增加 interpreter 性能 benchmark 和热点统计。
- 增加最小 mock backend，验证未来 JIT 可以接收 IR、访问 runtime，并对未 lowering 指令回退 interpreter。
- 完善用户文档、API 示例、capability matrix 和限制说明。

当前阶段不实现真正的 JIT backend。

#### 冻结范围与 waiver（2026-08-18 记录）

Phase 10 冻结的是**接口与 gate 语义**，不冻结仍未闭合的**指令语义**。以下范围
明确写入能力边界，不得在文档/capability matrix 中描述为已支持或已 GPU 验证：

- **TMA（utmaldg/utmastg/utmaredg）：decode-only，不冻结语义。** 三者的
  non-blocking 完成语义只有 GPU observable 镜像、无 semu 侧一致执行，属于
  `decode-only` 级别（可解码、不可执行），不参与冻结的 functional 集合；capability
  matrix 必须列出，后续补齐语义不视为破坏冻结 ABI。
- **OMMA：functional，但 GPU 侧有 waiver。** 位精确模型与 semu 执行在 CPU-only
  差分中逐 bit 一致（`functional`），但其 GPU 三方一致证据缺失（用户指示跳过，
  见 Phase 9 tensor GPU differential），report 中必须同时标 `functional` +
  `gpu_waiver`，不得写为 "GPU validated"。
- **user-skip 口径（e3m2/e2m3/omma）：不得反向声称。** 这三个格式在 GPU 侧
  **未执行**（用户指示跳过），只有 CPU-only bit 精确证据。任何文档表述必须
  区分 "semu==model（CPU）" 与 "GPU 验证"，禁止把跳过项写进 GPU 验证结论。
- **runtime services：保留版本化 async/TMA 扩展点。** 冻结的 runtime service 接口
  必须为后续 async/TMA 语义落地预留版本化扩展点（如 completion/commit 回调和
  mbarrier 状态查询），保证 TMA 从 decode-only 升级为 functional 时无需破坏既有
  `IBackend`/event stream/fault ABI。
- **mock JIT backend 的 fallback 面必须覆盖 tensor/TMA。** mock backend 在收到
  decode-only 的 tensor/TMA 指令时必须回退 interpreter（未 lowering 路径），或按
  fault ABI 报 `decode-only` fault；测试必须同时覆盖"回退 interpreter 成功执行"与
  "无法 lowering 时报 decode-only fault"两条路径，证明冻结的 fallback 契约对
  tensor/TMA 成立。

#### 验证方式

- 全量 CPU CTest、sanitizer、fuzz 和可选 sm120 GPU differential。
- 公共 API compile tests。
- mock backend 执行基础 block，并验证 fallback。
- benchmark 记录单 worker/多 worker动态指令吞吐和扩展比，不设置首版硬性性能 SLA。

#### 退出条件

- 添加 JIT backend 不需要修改 cubin loader、公开 launch API、memory model、debugger 或 profiler schema。
- 所有已知限制都出现在 capability/report 中。
- CPU-only 环境可以完成构建、加载、模拟、调试和 profile。

#### Phase 10 完成记录（2026-08-18，semu 实现者）

- **接口冻结**：`semu/include/semu/api.hpp` 定义版本标记 `kBackendApiVersion` /
  `kDecodedIrVersion` / `kRuntimeServicesVersion` / `kEventStreamVersion` /
  `kFaultAbiVersion`（均 = 1），并给每个冻结头文件（context/cubin/decoder/
  fault/interpreter/memory_events/profiler/race_detector/version）加冻结契约注释；
  `IRuntimeServices` 在 `context.hpp` 预留**版本化 async/TMA 扩展点**（completion/
  commit 回调和 mbarrier 状态查询，文档化形状 + 版本化扩展接口契约，未实现，
  不破坏既有 ABI）。`--version` 打印冻结接口版本。
- **Mock backend**：`include/semu/mock_backend.hpp` + `src/mock_backend.cpp`。
  验证未来 JIT 可接收 decoded IR（逐 word 分类 lowered / interpreter-fallback /
  decode-only）、访问 runtime services（constant bank 切片喂 interpreter +
  设备内存 write/read probe）、对未 lowering 指令回退 interpreter（整 launch
  经 `Interpreter::run_result` 执行成功）、对无法 lowering 指令按 fault ABI 报
  `FaultKind::kUnsupportedInstruction`。decode-only 边界显式覆盖 **TMA
  （UTMALDG/UTMASTG/UTMAREDG）与非 dense tensor variant**（走 fault 路径）。
  `interpreter_handles()` 从 `Interpreter::supports` 提取为自由函数（mock 无需
  构造 interpreter 即可查询运行时能力）。
- **热点统计**：`RunOptions::collect_hotspots`（opt-in）→
  `Interpreter::Result::pc_hotspots`（按静态字节 PC 的动态 issue 计数，并行
  worker 合并）；bench 用独立未计时 probe 取热点，不计入吞吐计时。
- **Benchmark**：`semu/tests/bench_interp_throughput.cpp`（Release 记录：
  grid 64×block 256×body 512，dyn=296960；worker 1→2→4→8 吞吐
  31.1/126.2/502.8/1688.0 instr/ms，扩展比 1.0/4.06/16.17/54.28；热点为
  FFMA 88.3%）。确定性门禁：每个 worker 数必须复现单 worker 控制流指纹。
  结果记录到 `semu/benchmarks/record.json`（含 git commit / build / host_cpus /
  recorded_at），不设硬性 SLA。
- **公共 API compile tests**：`semu/tests/compile_api_test.cpp`（聚合可运行
  烟测）+ 30 个公共头文件各自独立编译检查（object target，`-Werror`）。
- **文档**：`semu/docs/USER_GUIDE.md`（构建/CLI/API/freeze 契约/capability
  matrix 含 waiver/benchmark/限制）、`semu/docs/API_EXAMPLES.md`（7 组可编译
  示例）；`semu/README.md` 加 Phase 10 小节。
- **codex 复验遗留 3 Medium 修复**：
  a) SIM_PLAN Phase 9 退出条件口径改为 "functional variant 必须有 GPU
     differential 或在 capability manifest 记录显式批准的 GPU waiver"。
  b) `tools/tensor_gpu_differential.py` 头部描述改为 "compares three results;
     semu/model equality is asserted, GPU-only differences recorded as
     warnings"（script 1.2.0）。
  c) report provenance 增加 `git_dirty`、`source_tree_digest`（git-tracked 文件
     排序 + 各自 SHA-256 的聚合）、`tensor_gpu_differential_sha256`、
     `hmma_model_sha256`。
- **验证**：
  - 全量 CPU CTest 三树：`tools/run_semu_cpu_gate.sh` **35/35**（Debug / ASan /
    TSan 各自 35/35；原 33 项 + `mock_backend` 11 项 + `api_compile` 7 项）。
  - fuzz **gpu=False** n=40 + mutation **108/108** 0 errors。
  - l1tex_oracle **C++==Python 1941/1941**；LDGSTS corpus **520/520** + 纯计数
    TWf/TagConf/TSetAcc/Sectors == hardware meas 520/520。
  - tensor differential（CPU）全绿；**tensor GPU differential 54/54 checked
    PASS 0 hard failures**（5090/CUDA 13.1，report 已带新 provenance）。
  - mock backend 11 项全过、api_compile 7 项全过、30 头文件独立编译全过。
  - benchmark 记录写入 `semu/benchmarks/record.json`。
  - `sim.py` 未修改（仓库无该文件）。
- **退出条件确认**：加 JIT backend 无需改 cubin loader / public launch API /
  memory model / debugger / profiler schema（mock backend 是证明）；所有已知
  限制（TMA decode-only、OMMA gpu_waiver、e3m2/e2m3/omma user-skip、`.cg`
  bypass 模型 unsupported）出现在 capability matrix 与 report；CPU-only 环境
  完成构建/加载/模拟/调试/profile（35/35 全 CPU 门禁）。

## 4. 全局验证体系

### 4.1 测试分层

- **L0：C++ unit tests**：decoder helpers、ELF parser、memory、operand 和语义函数；无 CUDA。
- **L1：CPU integration tests**：使用 assembler 生成 cubin，在 semu 中完整 launch。
- **L2：cubin fixture tests**：加载受控 nvcc 单/多 kernel cubin，验证 ELF/ABI。
- **L3：GPU differential tests**：同一 cubin/参数分别在 sm120 GPU 和 semu 执行。
- **L4：robustness tests**：decoder/ELF fuzz、ASan、UBSan 和 TSan。
- **L5：profiler golden corpus**：与 `arch/l1tex/model.py` 和仓库访存笔记对照。
- **L6：race/HB golden corpus**：shared/global 正负例、barrier/fence/atomic scope、
  跨 CTA/SM、非对齐重叠范围和确定性报告。

CPU-only tests 是基础门禁；GPU differential 是在 sm120 机器上运行的可选但权威验证。

### 4.2 Instruction Definition of Done

一个 mnemonic/variant 从 `decode-only` 升级为 `functional` 必须满足：

1. decoder 唯一且 round-trip 成功。
2. 语义 handler 覆盖所有实际使用的 operand 和 modifier。
3. 至少一个成功测试和一个边界/错误测试。
4. 可用时完成 sm120 GPU differential。
5. debugger 能显示其输入、输出和 fault。
6. memory instruction 能产生标准 profiler memory event。
7. memory instruction 的 access kind、byte range、atomic/order/scope 足以供 race
   detector 判断；无法判断的 variant 必须标为 race-analysis unsupported。
8. capability manifest 和文档同步更新。

### 4.3 Phase 回归门禁

每个 Phase 合并前必须满足：

- 本 Phase 的退出条件全部自动化或有明确硬件验证记录。
- 所有较早 Phase tests 保持通过。
- 新增推测性语义必须记录证据、假设、置信度和反例。
- 不允许把未解决行为硬编码为无条件规则。
- 新增公共 API 必须有 compile test 和最小使用示例。

## 5. Profiler 精度分级

Profiler 每项结果使用以下级别：

- `exact-architectural`：直接由地址集合和明确架构规则得出，例如 sector 数。
- `exact-empirical`：在已声明输入范围内与 sm120 硬件 corpus 完全一致。
- `approximate`：模型有已知误差，报告适用范围和误差来源。
- `unsupported`：缺少可靠模型，只提供原始访问事件，不生成计数。

LDGSTS 初始分级：

- 32-byte sectors、128-byte tags 和已验证 tag-bank范围：`exact-empirical`。
- 已验证 structured 4/8/16-byte patterns：`exact-empirical`。
- random scattered destination、miss-path suppression：`approximate`。
- `.cg` bypass 的完整 wavefront/conflict 计数：`unsupported`。

## 6. 确定性与并行语义

- `deterministic` 模式固定 CTA、warp、PC-group 顺序和 seed，使用单 worker。
- `parallel` 模式用 CPU worker pool 分发 CTA，面向吞吐。
- data-race-free kernel 在两种模式下必须得到相同结果。
- 跨 CTA 普通数据竞争的结果视为调度相关；race detector 必须报告，report 中标明
  worker count、seed、SM/subcore 映射和冲突事件。
- atomic 操作必须满足所声明 scope 内的原子性。
- debug session 始终使用 deterministic 模式。
- profiler 的计数对同一个确定性执行必须 byte-for-byte 可复现。
- race report 对同一个确定性执行必须 byte-for-byte 可复现；parallel 模式仅在
  worker count、seed 和 SM/subcore 映射相同时要求 replay 一致。race 已影响控制流
  或地址生成时，不要求不同 seed 产生相同 race key 集合。

## 7. 主要风险及处理

### Variant 解码歧义

通过 opcode candidate、固定字段、table inverse 和 legality condition 联合判定，并以 decode->encode round-trip 作为最终校验。无法唯一判定时停止解码，不猜测。

### nvcc cubin ABI 不完整

按 EIATTR allowlist 增量支持；未知 metadata 保留原始值。普通 kernel loader 与 device runtime/linker 功能明确分离。

### 浮点位精确性

使用显式 bit-level helper、受控 rounding 和硬件 differential；不能直接依赖宿主默认 NaN、FTZ 或 rounding 行为。

### 异步操作没有周期模型

使用逻辑 pending operation 和 completion dependency，保证正确同步程序的结果；不对完成 cycle 和错误调度产生的 stale 值作承诺。

### 多核与确定性冲突

把可复现串行模式和多核吞吐模式作为显式 launch 配置，不声称有数据竞争的多核程序可确定复现。

### 访存模型存在未解决项

所有模型版本化并携带 confidence；保留原始 per-lane event，使分析规则可在不重新执行 kernel 的情况下迭代。

## 8. 进度记录模板

实现期间在本文维护如下总表：

| Phase | 状态 | Decoder | Functional mnemonics | Profiled mnemonics | CPU tests | GPU differential | 未解决项 |
|---|---|---:|---:|---:|---:|---:|---|
| 0 | Done (2026-08-11) | 0 | 0 | 0 | 15 (3 CTest) | 0 | - |
| 1 | Done (2026-08-11) | 1414/1414 unique | 0 | 0 | 31 (12 CTest) | 0 | 260 allowlisted matcher gaps |
| 2 | Done (2026-08-12) | 3 kernels / 152+16+16+16 inst predecoded | 0 | 0 | 47 (14 CTest) | 0 | 0 (GAP_PHASE2 全关) |
| 3 | Done (2026-08-12) | - | 0 | 0 | 61 (15 CTest) | 0 | - |
| 3.5 | Done (2026-08-12) | - | 0 | 0 | 84 (16 CTest) | 0 | - |
| 4 | Done (2026-08-12) | - | control subset | 0 | 28 (17 CTest) | 0 | ITS corner cases (Phase 5+ 补充) |
| 5 | Done (2026-08-13) | - | compute subset (29 mnemonics) | 0 | 30 (19 CTest) | 484/484 diff + fuzz GPU/ref + mutation 108/108 (0 err) | MUFU/FCHK/IMAD.X (近似表/未实现 carry, Phase 9) |
| 6 | Done (2026-08-13) | - | memory/sync subset | l1tex/l2/race events | 24 CTest + 484 diff + 110 fuzz + 108 mutation + ASan/UBSan/TSan clean | 484/484 GPU diff | multi-writer global race report set 对 worker 数不承诺（单 race 对逐字节一致）；Step 2B 未接入 ordinary LDGSTS（后续 Phase 8/9） |
| 7 | Done (2026-08-16) | - | control + memory + compute subset | unchanged | 25 CTest (normal/ASan/UBSan/TSan) + fuzz gpu=False + mutation 108/108 (0 err) + l1tex C++==Python 1941/1941 | **GPU 侧已补跑**（2026-08-18，5090 回归，CUDA 13.1）：diff_phase5 **484/484** + fuzz --gpu **120/120**（此前因 GPU0 拆走挂起；l1tex 为 frozen-corpus 门禁 1941/1941，GPU 采样属 corpus 采集流程不另行重跑） | debugger UX |
| 8 | Done (2026-08-16) | - | unchanged | memory subset (shared/global/ldgsts/l1tex/l2) | 29 CTest (normal/ASan/UBSan/TSan) + fuzz gpu=False + mutation 108/108 + l1tex_oracle 1941/1941 + LDGSTS corpus C++==Python 520/520 + pure counts == HW 520/520 + codex 复验 8 项修复（2B+4H+2M） | **GPU 侧已补跑**（2026-08-18，5090 回归，CUDA 13.1）：diff_phase5 **484/484** + fuzz --gpu **120/120**（此前因 GPU0 拆走挂起） | LDGSTS SharedConf/GlobalConf 为定义性 approximate；scattered 8/16B、miss-path suppression；`.cg` bypass 仅 profiler model confidence unsupported（功能已实现） |
| 9 | In progress (tensor core GPU-verified) | - | tensor/TMA subset | tensor/TMA | 33 CTest (含 tensor/tensor_map/mbarrier) + tensor_differential CPU gate + fuzz/mutation/l1tex 全绿 | **tensor GPU differential 54/54 checked PASS 0 hard failures**（2026-08-18，5090/CUDA 13.1；semu==model 逐 word；51/54 模型==GPU==semu 三方一致 + 3 条 E5M2 inf/NaN 符号约定差异为 GPU-only warning）；`semu_test_tensor` 全过 | 24 user-skip（e3m2/e2m3/omma，无 GPU 验证、不得描述为 GPU validated）；TMA 3 decode-only 不冻结；`.cg` bypass 仅 profiler model confidence unsupported（功能已实现） |
| 10 | Done (2026-08-18) | full supported set | tracked | tracked | **35 CTest 三树（Debug/ASan/TSan）全绿** + fuzz gpu=False + mutation 108/108 + l1tex_oracle 1941/1941 + LDGSTS 520/520 + tensor_differential + mock backend 11 项 + api_compile 7 项 | GPU differential 可选（5090 在，tensor GPU 54/54 checked PASS 0 hard failures 已补跑，report 带 git_dirty/source-tree digest/脚本 SHA-256 新 provenance） | JIT follow-up（接口已冻结，不实现 JIT）；TMA decode-only 不冻结；OMMA functional+gpu_waiver；e3m2/e2m3/omma user-skip 不得写 GPU validated |

每个未解决行为应记录：关联 mnemonic/PC、硬件与软件版本、最小复现、观察结果、当前假设、反例、置信度和下一验证实验。

### Phase 1 完成记录（2026-08-11）

- Decoder：`src/decoder/`（decoder/expr/render）只消费 `generated/isa_data.*`。
- 1414/1414 variants 可唯一解码（0 ambiguous / 0 illegal），corpus 全部 encode 成功。
- 歧义消解：star_slot discriminator 的 enum-membership、`*TABLES_x` reverse
  lookup、固定字段/reserved bits/legality condition 联合判定。
- 验证门禁（CTest）：`decoder`、`decoder_roundtrip`（encode→decode→encode
  bit-exact）、`decoder_ambig`（高重叠 opcode + reserved-bit 翻转）、`isa_regen`
  （generator 确定性 + committed-match）。

### Phase 3 完成记录（2026-08-12）

- 虚拟内存：`include/semu/memory.hpp` + `src/memory.cpp` — `DevicePtr`
  （overflow-checked 64-bit 地址算术）、`AddressSpace`（global/constant/
  shared/local）、`AllocationId`（单调、不复用；race report 以此标识）、
  `MemoryAllocator`（确定性地址分配：相同分配序列 → 相同地址；
  allocate/free/read/write/memset/copy 全部带生命周期/越界/对齐检查，
  结构化错误不崩溃）。
- 常量 bank：`ConstantBank`（c[0x0][...] 窗口，sm120 ABI：param_base
  0x380、SLOT_DEFAULT_CDESC 0x358、size 0x10000）；`write_param` 按
  param_base + KPARAM.offset 落位，`read_raw` 绝对地址访问。
- Launch ABI：`include/semu/context.hpp` + `src/context.cpp` —
  `Context`（地址空间 + per-kernel banks + backend）、`RuntimeModule`、
  `Function`、`LaunchConfig`、`LaunchResult`、`IBackend`（interpreter
  只能通过 runtime services 访问内存）。逐项 `KernelArg`（pointer/int/
  float/raw）与 packed buffer 两条路径产生 byte-identical constant0 内容；
  标量按参数宽度截断低字节，kBytes 必须精确匹配宽度。
- 预置 slot：SLOT_DEFAULT_CDESC 初始化为规范占位值（Phase 6 细化真实
  descriptor 语义）。
- 错误路径：OOB 读写、use-after-free、double-free、未知指针、错参数数量、
  错参数宽度、packed buffer 过短、未知 kernel 全部结构化失败。
- 移植 assembler 用例：`test_bigparam`（out<8>@0x380 + big<128>@0x388，
  kernel 读 c[0x0][0x38c]）→ `context_bigparam_128_byte_arg` 验证
  constant0 逐字节内容。
- 门禁：`memory` CTest（20 项单元：确定性、生命周期、memset/copy、allocation
  id、DevicePtr 算术、ConstantBank、per-item launch、packed==item、
  错误路径、shared+backend、bigparam + P3-GAP 回归矩阵）。普通 CTest 15/15、
  ASan+UBSan 全绿，零编译警告。

### Phase 3 验收关闭记录（2026-08-12，`semu/GAP_PHASE3.md`）

- P3-GAP-01：`write_slot` absolute offset（不再 +param_base）；layout 不变量
  构造校验；launch 前 `prepare_bank` clear→seed→preset→params。
- P3-GAP-02：pointer 参数经 allocator 生命周期验证（live global、interior
  允许；unknown/freed/one-past-end/shared 拒绝；错误含 kernel/ordinal/VA）。
- P3-GAP-03：`IRuntimeServices` + `BackendLaunchRequest`；`Function` 持 module
  shared handle（销毁后不悬空）；`bind_runtime` 在 launch 时绑定。
- P3-GAP-04：`DevicePtr::add` INT64_MIN-safe（uint64 幅度，无有符号取反 UB）。
- P3-GAP-05：`ParamPackFormat`（kKparamBlob/kFullBankImage）强类型分离。
- P3-GAP-06：`DeviceAccess` + `read_typed`/`write_typed`（可区分错误码）。
- P3-GAP-07：`Allocation::owner` + `free_domain` 域隔离与回收。
- P3-GAP-08：shared size overflow-safe 加法（kOutOfRange）。
- P3-GAP-09：`prepare_bank` 确定性初始化（0x6d8 未污染探针）。
- 二轮审阅（2026-08-12）：P3-GAP-07 完整关闭（DeviceAccess::domain 访问
  隔离 + 每 CTA shared allocation + 稳定 CTA owner + backend 成败路径
  回收 + 连续 launch 无泄漏）；P3-GAP-06 完整关闭（kind/操作一致性 +
  atomic/text 规则 + 1..256 全宽度矩阵）；P3-GAP-01 layout slot
  overflow-safe 检查；P3-GAP-03 event ABI（IEventSink + MemoryEvent +
  emit_event/set_event_sink）。
- 三轮审阅（2026-08-12）：`CtaSharedView` 数组经
  `BackendLaunchRequest::shared_views` 显式传 backend（多 CTA 完整可
  访问）；CTA domain ID 移入 Context（checked range 保留、无全局静态）；
  LaunchResult 不再返回失效 shared pointer（仅诊断元数据）；event 记录
  改名 `BasicMemoryEvent`（Phase 8 扩展，sink ABI 稳定）。
- 四轮审阅（2026-08-12）：launch 同时验证 grid + block product（零维度
  拒绝、sm120 1024 线程 cap 强制）；修复 double take_error 测试写法；
  LaunchResult 注释明确"不暴露 live/owning pointer"。
- 复验：普通 CTest 15/15（`memory` 32 项）、ASan+UBSan（halt_on_error=1）
  全绿、零编译警告。Phase 3 状态 **Closed / Pass**。

## 9. 默认技术假设

- Linux x86-64，C++20，CMake。
- 输入为 raw sm120 cubin，不是 fatbin。
- 核心库无 CUDA runtime/driver 依赖。
- 开发期允许使用 Python 生成 ISA 数据和组织 differential tests。
- 首版优先正确性、可调试性和分析可解释性，不设置硬性吞吐 SLA。
- sm120 encoding dump、仓库硬件验证笔记和 `tests/asm_construct` 是 ISA/语义事实来源。
- `~/cs/projects/arch/l1tex/unified_model.py` 是 LDGSTS profiler 的参考实现，但其文档中的未解项必须原样保留为模型限制。
### Phase 2 完成记录（2026-08-12）

- Loader：`src/cubin/loader.cpp` + `include/semu/cubin.hpp`，纯 ELF64 解析
  （无 CUDA driver 依赖），只消费原始字节 + Phase 1 Decoder。
- ELF 解析：magic/class/data/machine(EM_CUDA)/e_flags(sm120)/OSABI 校验；
  section header table、`.shstrtab`/`.strtab`、`.symtab`、`.rela*` 全部
  bounds-checked。
- Kernel 关联：GLOBAL|FUNC|STO_ENTRY 符号 + shndx→`.text.<mangled>`；
  `.nv.info.<mangled>` 经 sh_info 关联；device `.nv.info` 经 func_sym 关联
  REGCOUNT；`.nv.shared.<mangled>` 经 sh_info 关联 static shared
  （size−0x400）。
- EIATTR 解析（fmt=1/2/3/4 记录）：REGCOUNT(0x2f)、KPARAM(0x17，
  ordinal/offset/size-code)、EXIT(0x1c)、MBARRIER(0x39)、NUM_BARRIERS(0x4c)、
  NUM_MBARRIERS(0x38)、MAXREG(0x1b)、CBANK_PARAM_SIZE(0x19)、
  PARAM_CBANK(0x0a)、CLUSTER(0x3d)+EXPLICIT(0x3e)、CUDA_API_VERSION(0x37)；
  未知但可跳过 → warning 保留，未知且疑似 exec-affecting（fmt=4 大 payload）
  → kUnsupportedMetadata。
- Relocation：`.rela.*` 校验 symbol/目标 section/offset 越界，text 目标应用
  R_CUDA_ABS64/ABS32/PTR/SYMOFF，unsupported type on exec section → fault；
  `.rela.debug_frame` 等非 exec 目标跳过并告警（nvcc 真实 cubin 验证）。
- 预解码：module load 时解码全部 kernel text（保留 decode-only 指令），
  非唯一解码 word 记录 warning 不阻断。
- CLI：`load`（真实 loader）、`inspect`（ELF/section/symbol/kernel 全量）、
  `list-kernels`（machine-readable 一行一 kernel）、`disasm <cubin> [kernel]`
  （cuobjdump 风格，与单 word `disasm <lo> <hi>` 自动判别）。
- 验证门禁（CTest）：`cubin_loader`（合成 cubin 单元测试，11 项）、
  `cubin_load`（assembler 单 kernel + nvcc 多 kernel + readelf/cuobjdump
  对照 + 错误路径注入：坏 magic/坏 e_flags/截断/坏 symtab/未知 EIATTR/
  malformed EIATTR）。
- 实测：nvcc 多 kernel cubin 3 kernel（256/384/512B text、REG 4/10/12、
  KPARAM 8/8/8/4 与 `cuobjdump -res-usage` 一致）；committed tma/pmtrig
  cubins 全部可加载（tma_test：regs=38、152 指令预解码、含 mbarrier +
  cluster 元数据）。
- CTest 14/14（普通）与 ASan+UBSan 10/10 通过，零编译警告。

### Phase 2 验收关闭记录（2026-08-12，`semu/GAP_PHASE2.md`）

- P2-GAP-01（Kernel section 关联）：`Kernel::constant0/shared/local`
  `KernelSectionRef` + `Module::section_view()`（span、bounds-checked、
  NOBITS 空 view）；`FRAME_SIZE/MIN/MAX_STACK_SIZE` 解析进
  `KernelMetadata::frame_size/min_stack_size/max_stack_size`。
- P2-GAP-02（KPARAM 契约）：`normalize_kparams()` ordinal 升序排序；
  duplicate/zero-size/overlap/整数溢出/越 cbank 全部拒绝；
  `param_by_ordinal()` 支持 ABI hole；EIATTR 全排列 → metadata 一致。
- P2-GAP-03（稳定 IR）：`PredecodedWord` 每 16B word 一个 entry（unique
  状态 + reason + kernel-relative pc）；strict `load` 对 illegal/ambiguous
  失败；`load_for_inspection` 保留 placeholder；`word_at(kernel, pc)` 按
  kernel PC 索引（text 首/中/末注入均保持 entry 数与 PC 对齐）。
- P2-GAP-04（text/symbol 校验）：size % 16 == 0、section align >= 128、
  function symbol range ⊆ text section 强制校验。
- P2-GAP-05（relocation）：linked symtab 解析（多 symtab + 独立 strtab
  实测）、按 width bounds 检查、debug-only target 按 section 类型精确
  allowlist、unknown exec/data type 硬失败；ABS32/ABS64/addend/secondary
  symtab/constant target positive vectors + bad symbol/unknown type 负向量。
- P2-GAP-06（ELF link 关系）：symtab 名称经各自 sh_link 的 strtab；
  entsize>=24、size%entsize==0、sh_link 指向 strtab、st_shndx 合法、
  overflow-safe `range_fits()` 全部门禁化。
- P2-GAP-07（OSABI）：0x41/0x08 allowlist 强制校验。
- P2-GAP-08（EIATTR 策略）：reviewed allowlist（0x1e → warning；
  其余未知 → kUnsupportedMetadata）；strict/permissive 双模式分离。
- 门禁规模：`cubin_loader` 43 项单元 + `cubin_load` 集成；普通 CTest 15/15
  与 ASan+UBSan 全绿，零编译警告。Phase 2 状态 **Closed / Pass**。
- 三轮审阅（2026-08-12）修复：text sh_addralign==0 不再豁免（<128 一律
  拒绝）；relocation target 精确 debug allowlist（`.debug_*`/`.zdebug_*`/
  `.eh_frame`，未知非 exec/data target strict 失败）；新增
  `Module::executable()`（strict=true / inspection=false）。
- 二轮审阅（2026-08-12）6 项修复：OOB relocation sh_info 崩溃（先
  bounds-check 再索引，SIGSEGV→结构化错误）；inspection 模式真正降级未知
  EIATTR；KPARAM 错误单次 take_error；overlap 检测按 offset 排序副本
  （支持 ordinal/offset 非单调合法布局）；`PredecodedWord::file_offset`
  独立于 kernel-relative `inst.pc`；NOBITS relocation 明确拒绝。

- Decoder：`src/decoder/`（decoder/expr/render）只消费 `generated/isa_data.*`。
- 1414/1414 variants 可唯一解码（0 ambiguous / 0 illegal），corpus 全部 encode 成功。
- 歧义消解：star_slot discriminator 的 enum-membership、`*TABLES_x` reverse
  lookup、固定字段/reserved bits/legality condition 联合判定。
- 验证门禁（CTest）：`decoder`、`decoder_roundtrip`（encode→decode→encode
  bit-exact）、`decoder_ambig`（高重叠 opcode + reserved-bit 翻转）、`isa_regen`
  （generator 确定性 + committed-match）。
- Round-trip：1112/1414 bit-exact re-encode；其余为 assembler matcher 覆盖缺口
  （与参考 `tools/sass_disasm.py` 一致，非 decoder bug）。
- 修改了共享文件：`tools/parse_sm120.py`（SLOT_RE/def_re 允许 type 名含点，
  修复 F64.F32ONLY / POPC.INCONLY 的解析）、`assembler/sass_encoder.py`
  （`*TABLES_x` star_slot 求值、`convertFloatType` slot 路由）。
