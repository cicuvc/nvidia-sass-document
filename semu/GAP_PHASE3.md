# Phase 3 虚拟设备内存与 launch ABI 验收差距

**验收日期：** 2026-08-12  
**验收范围：** `SIM_PLAN.md` Phase 3 — 虚拟设备内存与 launch ABI  
**当前结论（2026-08-12 修复后复验；二轮/三轮/四轮审阅修复）：**
**Closed / Pass**。

初验发现的 3 项 Blocker、3 项 High、3 项 Medium（P3-GAP-01～P3-GAP-09）
全部关闭。修复摘要：

- P3-GAP-01（Blocker）：`ConstantBank::write_slot` 改为 **absolute bank
  offset**（不再加 param_base）；构造时校验 layout 不变量（param_base ≤
  size、preset slot 完整落入 bank，违规抛 `invalid_argument`）；launch 前
  `prepare_bank` 先 `clear()` 再 seed kernel const0 再写 preset；写/读
  全部 overflow-safe bounds-check。
- P3-GAP-02（Blocker）：`KernelArg::pointer` 经 `validate_pointer_arg`
  通过 allocator 验证——必须落在 **live global allocation** 内（interior
  pointer 允许，one-past-end/未知 VA/freed/shared 指针拒绝）；错误包含
  kernel、ordinal、VA、原因，且发生在任何 backend 调用之前。
- P3-GAP-03（Blocker）：新增 `IRuntimeServices`（backend 唯一设备访存
  通道）+ `BackendLaunchRequest`（kernel/IR handle、config、constant
  bank、shared view）；`Function` 持有 module 的 `shared_ptr` handle，
  module 销毁后 Function 不再悬空；`bind_runtime` 在 launch 时绑定
  Context 实例（create 返回 by-value，提前绑定会悬空）。
- P3-GAP-04（High）：`DevicePtr::add` 用 uint64 幅度计算
  （`-(delta+1)+1`），INT64_MIN 不再触发有符号取反 UB；UBSan
  `halt_on_error=1` 下通过。
- P3-GAP-05（High）：packed launch 拆分为 `ParamPackFormat::kKparamBlob`
  与 `kFullBankImage` 强类型枚举；完整 image 的 params 位于
  param_base + KPARAM.offset、preset 槽保留 image 内容；两种格式与逐项
  参数路径可 byte-for-byte 比较。
- P3-GAP-06（High）：新增 `DeviceAccess`（width/alignment/space/kind）+
  `read_typed`/`write_typed`，返回可区分错误码（kAlignmentViolation /
  kOob / kLifecycle / kBadAddress / kInvalidArgument）；byte-copy API 的
  非对齐语义单独文档化。
- P3-GAP-07（Medium）：`Allocation::owner` 域标识 + `allocate(...,owner)`
  + `free_domain(owner)`（CTA/warp teardown 回收）。
- P3-GAP-08（Medium）：shared size `static+extra` overflow-safe 加法，
  溢出返回结构化 `kOutOfRange`（"shared size overflow"）。
- P3-GAP-09（Medium）：`prepare_bank` 固定初始化流程
  （clear → kernel .nv.constant0 seed → ABI preset → params），消除跨
  launch 的非参数字节泄漏。

二轮审阅（2026-08-12）补充修复：

1. **P3-GAP-07 完整关闭**：`DeviceAccess::domain` 携带访问方 domain；
   `resolve_typed` 对 shared/local 强制 owner 相等（空 domain / 跨 CTA /
   跨 warp 拒绝，kBadAddress 含 "owned by"）；launch 按 CTA 逐个创建
   shared allocation（owner `cta:<稳定序号>`，单调递增不与历史 launch
   碰撞）；backend 成功与失败路径都回收 CTA allocation（无 backend 时
   同样回收）；`BackendLaunchRequest::shared_domain` 暴露给 interpreter。
   测试：`memory_domain_access_isolation`（跨 CTA/跨 warp 拒绝矩阵）、
   `context_repeated_launch_no_shared_leak`（连续 5 次 launch live 计数
   回到基线）。
2. **P3-GAP-06 完整关闭**：`check_kind_consistency` 校验操作/kind 一致性
   （kLoad 拒绝写、kStore 拒绝读 → kInvalidArgument）；atomic 限制
   {1,2,4,8} 宽度 + global/shared 空间；text 只读 + 仅 global。
   `memory_typed_access_width_matrix` 覆盖 1/2/4/8/16/32/128/256 的
   aligned/misaligned/OOB/wrong-space。
3. **P3-GAP-01 边界**：layout slot 检查改 overflow-safe
   `offset > size || 8 > size - offset`；`constant_bank_layout_boundary`
   覆盖 UINT64_MAX / UINT64_MAX-7 / 恰好贴边。
4. **P3-GAP-03 event ABI**：`IEventSink` + `MemoryEvent` + 
   `IRuntimeServices::emit_event/set_event_sink`（SIM_PLAN "内存和事件
   系统"通道冻结；具体事件模型随 Phase 8 profiler 落地）。
   `context_event_channel` + `context_backend_event_channel`（backend 经
   services 发事件）。

三轮审阅（2026-08-12）补充修复：

1. **Blocker：多 CTA shared request**——`CtaSharedView`（cta_linear_id/
   base/size/domain）数组经 `BackendLaunchRequest::shared_views`（span）
   显式传给 backend，每 CTA 一个 entry，禁止算术推导（allocator 每分配
   重新对齐）；`LaunchResult::shared_views` 保留诊断元数据。测试
   `context_multi_cta_shared_views`：grid=(2,2,1) 四 CTA 地址互不重叠、
   domain 唯一、跨 CTA 访问被拒、launch 返回后全部回收。
2. **High：CTA domain ID Context-local**——`next_cta_domain_` 移入
   Context（非全局静态，多 Context 不共享不竞争）；ID range 在分配前
   一次性 checked 保留（失败不复用）；`LaunchConfig::grid_threads()` /
   `block_threads()` overflow-checked。测试
   `context_cta_domain_ids_context_local`（两 Context 各自 cta:0 起始、
   独立 allocator）+ `context_grid_dims_overflow_rejected`。
3. **High：LaunchResult 不再返回失效 shared pointer**——`shared_base`/
   `shared_size` 从 LaunchResult 移除，只保留诊断 `shared_views` +
   `has_shared`；头文件注释明确 windows 在 launch() 返回前已回收。
   测试 `context_launch_result_shared_not_dangling`：返回后 typed access
   必须失败（kLifecycle/kBadAddress）。
4. **High：event 记录改名**——`MemoryEvent` → `BasicMemoryEvent`，头文件
   注释明确它不是 SIM_PLAN 规范化 MemoryEvent（event/launch ID、SM/CTA/
   warp、active lanes、per-lane byte ranges、cache/operator modifier、
   atomic order/scope、L1/L2 parent 随 Phase 8 profiler 落地；sink 接口
   稳定，记录类型届时扩展而非替换）。

四轮审阅（2026-08-12）补充修复：

1. **High：block dims launch 验证**——`Context::launch` 在任何 shared
   allocation / backend 调用前同时验证 grid 与 block product
   （`grid_threads()` + `block_threads()` 均 overflow-checked）；拒绝任一
   维度为零（CUDA 风格）；sm120 block-thread 上限 1024 作为 capability
   validation 强制（不静默接受任意非溢出尺寸）。测试
   `context_block_dims_overflow_rejected`（三乘积溢出 → kOutOfRange、
   零 block/grid 维度 → kInvalidArgument、1025 线程 → 拒绝、1024 → 通过）。
2. **测试质量**：`context_launch_result_shared_not_dangling` 的 double
   `take_error()` 改为先取一次再判断双码；`LaunchResult`/`shared_views`
   注释改为"不暴露 live/owning shared pointer"（诊断地址保留是设计决定，
   明确不得解引用）。

门禁：`memory` CTest 32 项单元（含 P3-GAP 回归矩阵）+ 原有
cubin_loader/cubin_load/core/decoder；普通 Debug/Werror 构建 CTest 15/15、
ASan+UBSan（`halt_on_error=1`）下全部 loader/memory 测试通过，零编译警告。

## 1. 验收证据

### 已通过

- 干净 Debug 构建，`SEMU_WERROR=ON`：CTest **15/15** 通过。
- ASan+UBSan 下 `cubin_loader|memory|cubin_load`：**3/3** 通过。
- 已实现 64-bit `DevicePtr`、单调且不复用的 `AllocationId`，以及 global、
  constant、shared、local 地址空间枚举。
- allocator 已覆盖 allocate/free、已释放 allocation、基本 OOB、copy/memset 和
  allocation alignment 校验。
- 已有 `RuntimeModule`、`Function`、`KernelArg`、`LaunchConfig`、
  `LaunchResult`、`IBackend` 和 `Context` 的公共 API 骨架。
- 逐项参数和最小 packed KPARAM blob 的正常路径已有测试，包含 128-byte 参数。

### 额外探针发现的问题

- 对 `DevicePtr{0x100}.add(INT64_MIN)` 运行 UBSan，报告：
  `negation of -9223372036854775808 cannot be represented`。现有 sanitizer
  corpus 未覆盖该边界。
- 代码路径证明 `write_slot(0x358)` 实际写到 `param_base + 0x358`；现有测试又以
  KPARAM-relative API 读取，错误互相抵消，形成假阳性。

## 2. 阻断问题

### P3-GAP-01 — constant0 特殊槽使用了 KPARAM-relative 地址

**严重级别：** Blocker  
**位置：** `include/semu/memory.hpp`、`src/memory.cpp`、`src/context.cpp`、
`tests/test_memory.cpp`

`ConstantBank::write_slot(offset)` 当前直接调用 `write_param(offset)`；后者会再加
`layout.param_base`。sm120 的 `SLOT_DEFAULT_CDESC` 是 constant0 内绝对偏移
`0x358`，当前 launch 因而把它写到 `0x380 + 0x358 = 0x6d8`。

现有测试执行 `write_slot(0x358)` 后调用 `read_param(0x358)`。写和读都错误地加上
`param_base`，所以测试通过并不能证明 slot 地址正确。`Context::launch()` 中默认
CDESC 的初始化也受此问题影响。

**关闭要求：**

- 明确区分 constant-bank absolute offset 与 KPARAM-relative offset；
  `write_slot` 必须按 absolute offset 写入。
- absolute raw read/write 和 parameter read/write 都做 overflow-safe bounds check。
- 为 `ConstantBankLayout` 增加不变量校验，至少保证 `param_base <= size`、特殊槽
  完整落入 bank。
- launch 前按已定义策略初始化/清理 constant0，避免上一次 launch 的非参数字节
  泄漏到下一次 launch；若需装载 kernel `.nv.constant0` 初始内容，应在此阶段明确。

**复验要求：**

- 写入 `write_slot(0x358)` 后直接断言 raw bank `[0x358,0x360)`，并断言
  `[0x6d8,0x6e0)` 未被修改。
- 使用非零哨兵验证逐项参数、packed 参数和特殊槽互不覆盖。
- malformed layout（`param_base > size`、slot 越界）结构化失败，并在 ASan/UBSan
  下运行。

### P3-GAP-02 — 显式 `DevicePtr` 参数未验证 allocation 生命周期

**严重级别：** Blocker  
**位置：** `include/semu/context.hpp`、`src/context.cpp`

`KernelArg::pointer` 当前只保存 VA；`pack_arg()` 将其直接序列化，不通过
`MemoryAllocator` resolve。未知地址、已释放 allocation、错误地址空间以及越过
allocation 尾部的地址均可被传给 backend。这不满足计划中“只有显式
`device_ptr` 执行 allocation 生命周期检查”的 ABI 要求。

**关闭要求：**

- launch 参数打包时识别 pointer kind，并通过 allocator 验证其属于存活的、允许
  作为 kernel 参数的 allocation。
- 明确是否允许 allocation 内部指针；若允许，至少验证 VA 位于存活 range 内，并
  保留 allocation id/offset 以供诊断和 race detector 使用。
- shared/local/constant 指针是否可由 host launch API 传入必须形成明确 allowlist；
  默认只允许 global allocation。
- raw integer 参数不得被误当成 pointer 验证，pointer 也不得通过 integer kind
  绕过已声明的参数类型策略；若 KPARAM 元数据无法区分类型，API 必须文档化该限制。

**复验要求：**

- live global base、合法 interior pointer 正向测试。
- unknown VA、null（按已定义语义）、freed pointer、one-past-end、shared/local/
  constant pointer 负向测试。
- 失败必须发生在 backend 被调用之前，错误中包含 kernel、ordinal、VA 和原因。

### P3-GAP-03 — `IBackend`/module 生命周期边界不足以支持 Phase 4

**严重级别：** Blocker  
**位置：** `include/semu/context.hpp`、`src/context.cpp`

当前 `IBackend::launch()` 只获得 kernel name、launch config、constant bank 与
shared base/size，未获得不可变 `Kernel`/predecoded IR，也没有受控的 global、
shared、local、constant memory/runtime-services 接口。`Context::create()` 接收已
构造 backend，但没有正式的 bind/runtime-service 协议。未来 interpreter/JIT
只能持有额外外部引用、按名称旁路查找，或绕过 `Context` private memory。

此外，`Function` 保存裸 `const Kernel*`，而 `Context` 不拥有
`RuntimeModule`。调用方销毁或移动 module 后，已有 `Function` 可能悬空。

**关闭要求：**

- 定义稳定的 `BackendLaunchRequest`（或等价结构），至少包含不可变 kernel/IR
  handle、launch config、constant/shared view，以及受控 runtime/memory services。
- backend 的所有设备访存必须经过 runtime services；不得直接取得 host backing
  vector 的可变引用或旁路 allocator 的生命周期/OOB/address-space 检查。
- 明确 Context、RuntimeModule、Function、Kernel/IR 的所有权。Function 在合法
  使用期内必须持有稳定 handle；销毁/move module 后不得留下悬空指针。
- 接口应允许未来 interpreter 和 JIT 使用同一 launch/runtime ABI，而不修改
  Context private state 或依赖全局 kernel-name lookup。

**复验要求：**

- 最小 mock backend 仅通过 request/runtime services 读取 IR、读写 global 和
  shared memory，并返回结构化结果。
- module move、原 handle 销毁、多个 module 含同名 kernel 的生命周期测试。
- backend 保存 request 中短生命周期 view 并在 launch 返回后使用时，API 应从
  类型/所有权上禁止或明确报错。

## 3. 高优先级正确性缺口

### P3-GAP-04 — `DevicePtr::add(INT64_MIN)` 触发 C++ 未定义行为

**严重级别：** High  
**位置：** `include/semu/memory.hpp`

负 offset 路径使用 `-delta` 计算绝对值。`delta == INT64_MIN` 时有符号取反不可
表示，UBSan 已实际报错。该函数注释承诺 overflow-checked，因此这是公共 API
契约违例。

**关闭要求：** 使用不执行有符号溢出的 magnitude 计算方式，并覆盖
`INT64_MIN`、`INT64_MAX`、零、恰好到零、差一字节 underflow/overflow。

**复验要求：** 新增单元测试并在 UBSan `halt_on_error=1` 下通过。

### P3-GAP-05 — packed launch 的“完整 bank image”契约未实现

**严重级别：** High  
**位置：** `include/semu/context.hpp`、`src/context.cpp`

公共注释声明 packed buffer 可以是完整 bank image 或最小 packed blob，但实现
无条件取前 `max_end` bytes 并写到 `param_base`。传入完整 constant0 image 时会把
image 的开头误当作 KPARAM 数据，注释中的两种格式无法可靠区分。

**关闭要求：**

- 最好拆分为显式 `launch_packed_params` 与 `launch_constant_bank_image`；或使用
  强类型 enum/variant 指定格式，不能根据长度含糊猜测。
- 完整 bank image 的特殊槽覆盖策略、kernel constant0 初值合并策略必须明确。
- 两种入口最终产生的 constant0 内容需要 byte-for-byte 可比较。

**复验要求：** 非零 bank prefix、KPARAM、padding、特殊槽分别放置哨兵，验证最小
blob、完整 image、逐项参数三种路径的预期内容；错误尺寸必须结构化失败。

### P3-GAP-06 — memory operation 没有访问对齐契约

**严重级别：** High  
**位置：** `include/semu/memory.hpp`、`src/memory.cpp`

当前只校验 allocation base alignment；`read/write/copy/memset` 不接受 required
alignment，也没有 typed access API。因此未来执行 2/4/8/16/128-byte 指令访存
时，runtime services 无法区分合法 byte copy 与应产生 misalignment fault 的设备
load/store。现有“alignment”测试仅覆盖分配参数，不覆盖访问地址。

**关闭要求：**

- byte-oriented host copy 与 instruction memory access 分层；后者显式传入 width、
  required alignment、address space 和 access kind。
- misalignment、OOB、use-after-free、wrong-address-space 使用可区分错误码，供
  debugger/profiler/race detector 消费。

**复验要求：** 对 1/2/4/8/16/128/256-byte access 覆盖 aligned、misaligned、
跨 allocation 尾部和错误 address-space；byte-copy API 的非对齐语义单独测试。

## 4. 中优先级缺口

### P3-GAP-07 — shared/local ownership 尚未建模

**严重级别：** Medium

计划要求 shared allocation 绑定 CTA、local allocation 绑定线程/warp、global
allocation 绑定 Context。目前 allocator 只有 address-space tag；launch 只创建
一个 shared window，未携带 CTA owner，且没有清晰的 launch-end 回收路径。

**关闭要求：** 引入稳定 owner/domain 标识，至少能够阻止 CTA/thread 间错误访问，
并定义 launch/CTA 结束时的回收。若实际 per-CTA materialization 延后到 Phase 4，
Phase 3 仍应冻结足够的 allocation/runtime-service ABI。

### P3-GAP-08 — shared size 加法缺少 overflow 检查

**严重级别：** Medium  
**位置：** `src/context.cpp`

`meta.static_shared + config.extra_shared` 直接以 `uint64_t` 相加，溢出后可能变为
很小的 allocation，导致错误 launch 成功。

**关闭要求：** overflow-safe 加法，并在 allocation/backend 调用前返回结构化
错误；覆盖恰好最大值和溢出一字节。

### P3-GAP-09 — constant bank 的跨 launch 初始化规则不完整

**严重级别：** Medium

bank 按 kernel 持久保存，launch 只覆盖参数区和一个 preset slot。padding、未使用
参数区和其他 constant0 bytes 可能保留上次 launch 的值；loader 已有关联
`Kernel::constant0`，但 launch 尚未明确从该 section seed bank。

**关闭要求：** 定义每次 launch 的 deterministic 初始化流程：清零、装载 kernel
constant0 初值、写 ABI preset、最后写参数（具体优先级需固定）；连续两次不同参数
launch 的完整 bank golden 应可预测。

## 5. Gap-closure 验收矩阵

| Gap | 级别 | 当前状态 | 关闭门禁 |
|---|---|---|---|
| P3-GAP-01 constant slot 地址 | Blocker | **Closed** | `constant_bank_param_layout` raw golden（0x358 写入、0x6d8 未动）+ `constant_bank_bad_layout_rejected` + `constant_bank_layout_boundary`（overflow-safe slot 检查）+ Context ABI 路径探针 |
| P3-GAP-02 pointer 生命周期 | Blocker | **Closed** | `context_pointer_arg_lifecycle_validation`（live/interior/one-past-end/unknown/freed/shared 矩阵） |
| P3-GAP-03 backend/所有权 ABI | Blocker | **Closed** | `context_services_backend_and_function_lifetime`（services-only mock + module 销毁后 Function 存活）+ `context_event_channel` / `context_backend_event_channel`（event ABI 冻结） |
| P3-GAP-04 `INT64_MIN` UB | High | **Closed** | `memory_deviceptr_int64_min_safe` + UBSan halt_on_error |
| P3-GAP-05 packed 格式 | High | **Closed** | `context_full_bank_image_launch`（image/blob/item byte golden + 过小 image 拒绝） |
| P3-GAP-06 access alignment | High | **Closed** | `memory_typed_access_contract`（kind 一致性 + atomic/text 规则）+ `memory_typed_access_width_matrix`（1..256 全宽度） |
| P3-GAP-07 shared/local owner | Medium | **Closed** | `memory_domain_access_isolation`（跨 CTA/跨 warp 拒绝）+ `context_repeated_launch_no_shared_leak`（回收无泄漏）+ `memory_domain_isolate_and_reclaim` |
| P3-GAP-08 shared size overflow | Medium | **Closed** | `context_shared_size_overflow`（静态 0x400 + UINT64_MAX → kOutOfRange） |
| P3-GAP-09 bank 初始化 | Medium | **Closed** | `prepare_bank` 固定流程（clear→seed→preset→params）+ 0x6d8 未污染探针 |

## 6. Phase 3 重新验收标准（2026-08-12 全部满足）

1. **P3-GAP-01～P3-GAP-06 全部关闭**；P3-GAP-07～09 全部关闭（不只切分）。
2. `SEMU_WERROR=ON` 干净构建，CTest **15/15** 通过，零编译警告。
3. cubin loader、memory、context/launch、mock backend 专项测试在普通、ASan 和
   UBSan（`halt_on_error=1`）下全部通过（`cubin_loader` 43 项 +
   `memory` 20 项 + 集成门禁）。
4. mutation/negative tests：错误 slot（0x6d8 未污染）、freed/unknown/space
   pointer、malformed packed image（过小）、misalignment（kAlignmentViolation）、
   overflow（kOutOfRange）、悬空 module/function（shared handle 存活）全部有
   门禁。
5. `SIM_PLAN.md` Phase 3 完成记录已更新并逐项链接上述测试。

Phase 3 状态：**Closed / Pass**。
