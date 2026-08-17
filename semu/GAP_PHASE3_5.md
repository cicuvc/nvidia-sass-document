# Phase 3.5 Cluster DSMEM 地址翻译 完成记录

**完成日期：** 2026-08-12  
**验收范围：** `SIM_PLAN.md` Phase 3.5 — Cluster DSMEM 地址翻译  
**状态：** **Closed / Pass**（初验/二轮/codex 二、三、四轮全部修复）

## 1. 实现内容

### 地址与访问语义（`include/semu/cluster.hpp`、`src/cluster.cpp`）

- DSMEM 逻辑地址按 sm120 已验证形式解析：
  `target_cluster_cta_rank = address[31:24]`、`offset = address[23:0]`
  （硬件探针 `tests/smem_cluster_dsmem.cu` 实测 per-rank delta 0x1000000）。
- `SharedAccessMode::kLocal` / `kDistributed` 显式模式；普通 shared 访问
  绝不解析 rank bits（`dsmem_local_mode_ignores_rank_bits` 测试证明高 bit
  offset 的 kLocal 访问仍按本地 offset 处理并 OOB，而非隐式 DSMEM）。
- `ClusterTopology::build(cluster_dims, grid)`：维度非零、乘积
  overflow-safe、cluster size ≤ 8（sm120 cap）、尾部非满 cluster 结构化
  拒绝（未验证前不猜测）；无 cluster metadata → disabled。
- rank 是 cluster 内 rank，与 grid-linear CTA id、Context allocation owner
  序号相互独立（`cluster_topology_basic_mapping` 证明 8 CTA/2 cluster 映射、
  `dsmem_rank0_is_cluster_rank0` 证明 source CTA 2 的 DSMEM rank 0 到达
  CTA 0 而非自身）。

### Runtime ABI（`include/semu/context.hpp`、`src/context.cpp`）

- `IRuntimeServices::translate_shared(source_cta, logical_address, width,
  mode)` → `TranslatedSharedAddress`（source CTA、cluster id、target rank、
  target CTA、logical address、allocation id、allocation offset、DevicePtr、
  width、mode）——backend 唯一合法的 DSMEM 翻译入口，禁止自行
  `(rank << 24)` 解码。
- `read_shared` / `write_shared`：经翻译的授权访问（cluster membership 已
  验证，source domain ≠ target owner 被允许）；通过 allocator 的
  `read_at`/`write_at` 直接写 live backing（修复了 value-copy 别名问题）。
- `BackendLaunchRequest::cluster`：只读 topology（enabled 时非空）；backend
  不得从 shared_views 顺序/地址差/owner 字符串反推 rank。
- launch 在 backend 调用期间设置 `active_topology_`/`active_views_`
  （活跃 launch 状态），返回后清理并回收全部 CTA shared allocation
  （成功/失败路径一致）；`translate_shared` 在非活跃 launch 调用返回
  kIllegalState。

### Event 边界

- `BasicMemoryEvent` 扩展共享/DSMEM 身份字段：shared_mode、source_cta、
  cluster_id、target_rank、target_cta、logical_address、allocation、
  allocation_offset（`dsmem_event_identity_golden` 逐字段断言）。
- race/同步语义（cluster barrier、fence、atomic scope 的 happens-before）
  不在本阶段猜测——Phase 7 实现；事件已携带足够身份避免以后更改翻译 ABI。

## 2. 验证

`cluster` CTest（23 项单元）：

- `cluster_topology_basic_mapping`：cluster(2,2,1) 4/8 CTA 的 rank/cluster
  id/grid_cta 双向映射。
- `cluster_topology_legality`：无 metadata → disabled；零维、乘积溢出、
  cap 超限（4×4×1）、尾部部分 cluster 全拒绝。
- `dsmem_translation_and_cross_cta_roundtrip`：source CTA 0 经 DSMEM 写
  rank 1 再读回，payload 一致；翻译身份字段全对。
- `dsmem_negative_matrix`：rank 越界、offset 越过窗口、width 越过窗口全
  结构化失败（"out of range"/"out of bounds"）。
- `dsmem_rejected_without_cluster`：无 cluster 元数据的 kernel 上 DSMEM
  拒绝。
- `dsmem_local_mode_ignores_rank_bits`：kLocal 不解析 rank bits。
- `dsmem_rank0_is_cluster_rank0`：rank 0 == cluster rank 0，非 source CTA。
- `dsmem_event_identity_golden`：事件携带完整翻译身份。
- `dsmem_atomic_widths_and_oob`：1/2/4/8 宽度翻译通过；16B 越窗拒绝。

普通 Debug/Werror 构建 CTest **16/16**；ASan+UBSan（halt_on_error=1）下
cluster/memory/cubin/core/decoder 全部通过，零编译警告。

## 3. 修复过程中发现并修复的缺陷

- `read_shared`/`write_shared` 经 `resolve_range` 写 value-copy 的 data
  vector（丢失写）→ 改经 `MemoryAllocator::read_at`/`write_at` 直接写
  live backing。
- 空参数 launch（0 KPARAM）`write_param(0, nullptr, 0)` 触发 UBSan
  "null pointer passed to memcpy" → max_end==0 时跳过写。

## 3.5 初验审阅修复（2026-08-12）

1. **Blocker：3D cluster topology**——`ClusterTopology` 按
   (cluster_x, cluster_y, cluster_z) 对 grid 三维 tile（x-fast CTA
   线性化），逐轴要求 `grid % cluster == 0`（尾部部分 cluster 拒绝）；
   保存 grid dims + clusters-per-axis；`cluster_id`/`cta_rank`/`grid_cta`
   双向映射。测试覆盖 grid(4,2,1)/cluster(2,2,1)（cluster 0 = CTA
   0,1,4,5）、grid(4,4,2)/cluster(2,2,2)（4 clusters of 8，CTA 31 →
   cluster 3 rank 7）和多 cluster。
2. **Blocker：translation 授权不可伪造**——`TranslatedSharedAddress` 携带
   `launch_generation` 令牌（launch 时递增，翻译时嵌入）；每次
   read/write/atomic 经 `validate_translation` 全身份重验证：generation
   匹配、allocation 属于 active launch 的 shared window、address ==
   base+offset、cluster/rank/cta 与 active topology 一致、mode 与 target
   关系一致（local → target==source）。伪造矩阵测试：改 address（指向
   global）、改 allocation id、address/offset 不一致、改 target rank/cta、
   旧 generation、mode 翻转——全部写入前拒绝；跨 Context 复用翻译也拒绝。
3. **High：真 DSMEM atomic**——`atomic_shared(addr, AtomicOp, value, old)`
   实现 RMW（ADD/MIN/MAX/AND/OR/XOR/EXCH，1/2/4/8 宽度门禁在翻译与访问
   两层强制）；测试验证 add 旧值/新值和 exch 旧值。
4. **High：alignment/kind 进 DSMEM API**——`translate_shared` 接收完整
   `DeviceAccess`；对齐（power-of-two + 地址对齐）、space==kShared、
   atomic 宽度门禁在翻译时强制（misaligned DSMEM 在访问前失败）。
5. **High：local width 下溢**——本地路径改用 overflow-safe
   `logical_address > size || width > size - logical_address`；width==0
   拒绝。
6. **High：grid product overflow-safe**——`ClusterTopology::build` 内部
   独立 overflow-safe 乘法（不依赖调用方）。
7. **High：runtime 自动 event**——read/write/atomic_shared 成功路径自动
   emit（受信翻译构造，backend 不再手工拼装）；测试断言 4 次访问产生
   4 个带完整 DSMEM 身份的事件（2 atomic + 1 store + 1 load）。

`cluster` CTest 13 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）全绿、
零编译警告。

## 3.6 二轮审阅修复（2026-08-12）

1. **Blocker：跨 Context 授权**——capability token 改为
   `(context_nonce_ << 32) | (launch_count_ & 0xFFFFFFFF)`：nonce 来自
   Context 创建时的进程级单调计数器（永不复用），launch count 无符号回绕
   安全（nonce 保证 token 唯一）。validate_translation 校验 nonce 必须
   是本 Context 的、count 必须是当前 launch 的。测试
   `dsmem_cross_context_replay_during_launch`：Context A mint 的翻译在
   Context B backend 执行期间重放（分配序列/VA/topology 完全相同）——
   因 nonce 不同被拒；`own_ok` 证明 B 自己的翻译可用。
2. **Blocker：AccessKind 绑定**——`TranslatedSharedAddress` 携带完整可信
   access descriptor（kind/alignment/space/width）；read_shared 仅接受
   kLoad、write_shared 仅 kStore、atomic_shared 仅 kAtomic，每次使用重
   验证。测试 `dsmem_kind_cross_reuse_rejected`：load→write、store→read、
   load→atomic、atomic→write 四类交叉复用全拒。
3. **High：真 atomic RMW**——`MemoryAllocator::atomic_rmw` 在单一临界区
   （heap-allocated mutex，保持 allocator 可移动）内 resolve+read+compute+
   write；`atomic_shared` 转调它。测试
   `dsmem_atomic_rmw_multithreaded`：8 线程 × 500 ADD 同一 word，终值
   精确等于 4000（无 lost update）；新增 `SEMU_ENABLE_TSAN` 构建选项，
   TSan（halt_on_error）下全绿无数据竞争。
4. **High：identity 重验证完整化**——validate_translation 从
   logical_address 重新推导：distributed 的 rank==logical>>24、
   allocation_offset==logical&0xffffff，local 的
   allocation_offset==logical_address；拒绝未定义 SharedAccessMode 和
   AtomicOp 枚举值（kCount sentinel）。测试
   `dsmem_invalid_enums_rejected`（mode 0x42、op 0x77 全拒）。
5. **High：event stop 语义明确**——事件在内存提交后发出；sink 返回 false
   置 `event_stopped_`，后续事件抑制；`IRuntimeServices::event_stopped()`
   可查询；访问仍成功（提交后事件契约）。测试
   `dsmem_event_stop_semantics`：4 次访问、sink 第 3 次返回 false → 3 次
   emit 调用、第 4 次抑制、`event_stopped()` 为真、内存已提交（add/exch
   结果正确）。
6. **AtomicOp 语义文档**——kMin/kMax 明确为 UNSIGNED 比较；SASS signed/
   floating atom 变体作为指令语义扩展延后到 interpreter 阶段。

`cluster` CTest 18 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）、
TSan（halt_on_error=1）全绿、零编译警告。

## 3.7 codex 复核修复（2026-08-12）

**High：capability token 位宽截断与回绕**——`TranslatedSharedAddress` 拆分
为两个完整 64 位字段 `context_nonce` + `launch_generation`（不再拼接
32+32）：

- 缺陷 1 修复：nonce ≥ 2^32 时旧 token 只含低 32 位、验证却比完整 64 位
  导致自签翻译被拒。现在 mint/validate 都用完整 64 位字段，无截断。
  测试 `dsmem_token_full_width_nonce`：注入 nonce 0xFFFFFFFF /
  0x100000000，minted 翻译在 launch 内访问成功（缺陷 1 回归）。
- 缺陷 2 修复：launch count 不再回绕——`++launch_count_` 在
  UINT64_MAX 时返回结构化错误（`kOutOfRange`，"launch generation
  counter exhausted"），永不回绕，所以旧 generation 的翻译不可能在
  counter 变化后重新验证。测试 `dsmem_generation_overflow_is_error`：
  注入 generation UINT64_MAX-1 → 一次 launch 到 UINT64_MAX（mint 合法、
  访问成功），下一次 launch 结构化失败；`dsmem_previous_generation_
  translation_invalid_after_next_launch` 断言 generation 单调推进。
- 测试钩子 `debug_set_counters`（仅测试用）提供受控 counter 注入。

`cluster` CTest 21 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）、
TSan（halt_on_error=1）全绿、零编译警告。

## 3.8 codex 第三轮复核修复（2026-08-12）

1. **High-1：generation exhaustion 后置条件泄漏**——`launch_count_ ==
   UINT64_MAX` 检查移到 launch 最前（任何 bank 准备 / shared allocation /
   domain reservation / active-state 修改之前）；整个 launch 用 RAII
   `LaunchGuard`（析构清 active_topology_/active_views_ 并释放所有 CTA
   shared allocation），所有后续错误路径（backend 失败、CTA 域耗尽、
   allocation 失败）统一清理，不再跳过。回归测试
   `dsmem_generation_overflow_no_leak_no_active_state`：overflow launch
   前后 live shared allocation 数不变、backend 未被调用（launches==1）、
   `shared_topology()` 不再 enabled、overflow 返回后 `translate_shared()`
   得 kIllegalState。
2. **High-2：nonce 回绕复用**——`nonce_source` 改用 CAS 循环 claim：
   到 UINT64_MAX 时 `Context::create()` 返回 kOutOfRange（"context nonce
   space exhausted"），永不发放 0 或已用 nonce（起始值 1，单调不重复）。
   测试 `context_nonce_exhaustion_is_error` 断言两次 create 得到非零且
   互不相同的 nonce。
3. **Medium：previous-generation 真重放**——新增 `debug_set_backend`
   测试钩子；`dsmem_previous_generation_translation_invalid_after_next_
   launch` 现在真的在同一 Context 上跑第二次 launch，在其 backend
   回调中重放第一次 launch mint 的 gen-1 translation → 得 kLifecycle
   （`previous_rejected`），同时新 mint 的 gen-2 translation 可正常访问
   （`fresh_ok`）。

`cluster` CTest 23 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）、
TSan（halt_on_error=1）全绿、零编译警告。

## 3.9 codex 第四轮复核修复（2026-08-12）

1. **测试问题 1：nonce exhaustion 未真测**——抽 `NonceAllocator` 为可测试
   类（CAS claim 循环内聚，`Context::create` 经进程级静态实例使用）。
   `context_nonce_exhaustion_is_error` 现在直接测 claim() 真实路径：
   - `debug_set(UINT64_MAX-1)` → claim 成功得 UINT64_MAX-1，下一次
     claim 返回 kOutOfRange（错误消息含 "nonce"），UINT64_MAX 本身永不
     发放；
   - 新 allocator 首次 claim 返回 1（永不 0）；
   - 16 线程竞争最后一个可用 nonce → 恰好 1 个成功、15 个 kOutOfRange
     （TSan 下无数据竞争）。
2. **测试问题 2：generation 重放未断言错误码**——`GenerationReplayProbe`
   改为记录 `previous_error`（ErrorCode），测试断言
   `*previous_error == ErrorCode::kLifecycle`（而非任何 `.failed()`），
   保留 `fresh_ok` 断言。

`cluster` CTest 23 项；普通 CTest 16/16、ASan+UBSan（halt_on_error=1）、
TSan（halt_on_error=1）全绿、零编译警告。

## 4. 退出条件核对

- [x] backend 不做地址算术即可对任意合法 cluster rank 完成 DSMEM
  load/store（translate_shared 返回最终 DevicePtr；read/write_shared 授权
  访问）。
- [x] 非法 rank、跨 cluster（构建期拒绝）、OOB、alignment、lifecycle 在
  访问目标内存前结构化失败，不退化为普通 shared access。
- [x] 普通 shared domain isolation 门禁保持全绿（Phase 3 测试未回归）。
- [x] 翻译/event 身份使用稳定 allocation_id + offset（TranslatedSharedAddress
  与 BasicMemoryEvent 均携带，不依赖 owner 字符串/宿主地址/相邻关系）。
- [x] 普通 + ASan+UBSan 门禁通过。硬件 differential（`smem_cluster_dsmem.cu`
  已留仓库）作为可选 GPU 门禁待 Phase 4 接入 interpreter 时运行。
