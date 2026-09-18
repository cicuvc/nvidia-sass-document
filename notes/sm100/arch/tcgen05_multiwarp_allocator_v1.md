# TCGEN05 多 warp 1-CTA allocator（V1 entry fragment）

## 已验证结论

`tests/asm_construct/tcgen05_alloc_multiwarp_v1_sm100.sass` 是当前最小的
“一个 CTA 内多个 warp、只有 warp 0 分配/释放、所有 warp 消费同一个 TMEM
base”的 V1 基线。它完全由仓库 assembler 生成 cubin，不 patch nvcc 产物。

在 Modal B200 上分别以 `block=64/128/160`、`grid=1` 运行成功。每个 warp 的
lane 0 都在第一次 CTA barrier 后从 shared 读到相同的 TMEM column base
（这些运行中均为 `0x0`），第二次 CTA barrier 后 warp 0 完成 dealloc 和
allocation-permit relinquish。64-thread 最终 metadata 版本又独立重复 3 次，
均正常退出。

当前 smoke payload 只验证 allocation、CTA 发布和完整释放闭环；它尚未让所有
consumer warp 执行 LDTM/STTM。后续 TMEM payload helper 应插在两个 CTA barrier
之间，不应改变 allocator owner 或退出协议。

## 控制拓扑

```text
所有 warp
  |
  +-- warp 0: V1 alloc lowering -> STS [shared+0x400], tmem_base
  |      其它 warp: 跳过 allocator
  |
  +-- BAR.SYNC 0                  # 发布 tmem_base
  |
  +-- 每个 warp lane 0: LDS base -> out[warp_id]
  |
  +-- BAR.SYNC 0                  # consumer quiescence
  |
  +-- warp 0: dealloc -> relinquish -> EXIT
         其它 warp: EXIT
```

不能让每个 warp 各自调用 PTX allocator lowering。V1 lowering 先读取每 CTA 的
reserved-shared `allocation_phase`，并假定调用 execution group 是唯一 owner；
多 warp 协议必须在它之外做 CTA 范围的发布和退出同步。

## 与 CUDA 12.8 ptxas 的 SASS 对照

CUDA 源使用 `if (threadIdx.x < 32)` 包围 alloc/dealloc/relinquish，并在 payload
前后各放一个 `__syncthreads()`。ptxas 生成的 `alloc_multi` 有 136 条 user SASS。
仓库版本对其 lift 后，仅做 assembler 方言所需的显式 64-bit register group
展开；最终 136 个 128-bit instruction words（包含 scheduling control）逐 bit
完全相同。回归用的 user-text SHA-256 为：

```text
9f2fe6d6a0d5119415af239ab9f13dde050ba23c6ff939445f2e00681c0f1c4b
```

SASS 中值得保留的边界是：

- `S2R SR_TID.X` 后以 `tid > 31` 把非 owner warp 跳到第一次 CTA barrier；
- owner warp 的 alloc/dealloc 内部仍保留 `WARPSYNC.ALL`；
- `BAR.SYNC.DEFER_BLOCKING 0` 是 CTA 发布和 quiescence 屏障；
- owner/non-owner 或 elected-lane 分支形成的 execution groups 必须在上述
  `BAR.SYNC` 前先经 `WARPSYNC.ALL`（或匹配的 `BSYNC`）完整汇聚；仅让各 group
  最终执行同一条 BAR 会在 B200 上触发 719；
- 非 owner warp 在第二个 barrier 后直接 `EXIT`；
- owner warp 才执行 `UTCATOMSWS.AND`、`UVIRTCOUNT.DEALLOC.SMPOOL` 和
  reserved `allocation_phase=1` store。

## V1 ELF / EIATTR contract

除单 warp 已验证的 V1 contract 外，多 warp 版本需要：

| 项目 | 值 |
|---|---|
| `AT_ENTRY_FRAGMENT_TMEM_CTA1` | 4（V1） |
| `.nv.shared.reserved.0` | `0x54` bytes |
| `.nv.shared.<kernel>` | `0x404` bytes（cap `0x400` + 4-byte base） |
| `VRC_CTA_INIT_COUNT` | `0x80` |
| `NUM_BARRIERS` | 1 |
| `INT_WARP_WIDE_INSTR_OFFSETS` | `0x5b0, 0x600` |
| `COOP_GROUP_INSTR_OFFSETS` | `0x60, 0x310, 0x470, 0x6c0` |
| `COOP_GROUP_MASK_REGIDS` | 4 个 `0xffffffff`，与 offset 数量相等 |
| `EXIT_INSTR_OFFSETS` | `0x410, 0x6d0, 0x740` |
| `CRS_STACK_SIZE` | 0 |

Assembler 原先把 cooperative mask-regid 数量固定成 5；多 warp 样本证明其数量
应与 cooperative offset 数量相同，现已修正。`CRS_STACK_SIZE=0` 对 NOINC/NODEC
guardrail call 没有可见功能影响，但为与 ptxas contract 对齐也已补发。

## relocation 与 driver 插入前缀

CUDA 12.8 cubin 含一个零大小的 `.rela.text.alloc_multi` section，即原生 user
text relocation 数量为 **0**。仓库 builder 直接省略这个空 container，语义相同。
ptxas 的非空 relocation 全在 `.rela.debug_frame` 或 Mercury capsule 中；driver
加载 user SASS 不依赖它们。

因此 V1 entry fragment 的运行时拼接不会要求修改 user text：

- `BRA`/`CALL.REL`/`RET.REL` 都在同一个 user-text island 内，以 PC-relative
  形式编码；整个 island 前移相同距离后目标关系不变；
- `INT_WARP_WIDE`、`COOP_GROUP`、`EXIT` 等 EIATTR offset 仍是 cubin 中
  **user text-relative** offset，不能人为加 V1 fragment 的 `0x1b0` bytes；
- assembler 现在从最终布局自动收集 `EXIT` 和 `VOTEU/REDUX`，并用零长度
  `#coop_group` 标注绑定具体 cooperative-group 指令；因此插入/删除指令后
  offset 会随最终 user text 更新，不再依赖手工维护数值 pragma；
- guardrail trap helper 的 ptxas FUNC symbols 只服务符号化/debug-frame；仓库
  cubin没有这些内部 symbol 仍在真机正确运行，说明它们不是 loader relocation
  contract 的组成部分。

最终真机成功也直接验证了 driver 对 EIATTR user-text offset 与运行时 prefix 的
换算；assembler 不应尝试预先重定位这些字段。

## 回归入口

- 静态：`python3 tests/asm_construct/test_tcgen05_alloc_multiwarp_v1_sm100.py`
- 真机：`tools/modal_tcgen05_alloc.py --hand-source ... --block-size 64`
- V1 entry fragment：`tmem_entry_fragment.md`

## Assembler builtin（2026-09-18）

闭集 builtin `#!tmem_alloc_1cta` / `#!tmem_dealloc_1cta` /
`#!tmem_relinquish_alloc_permit_1cta` 现在同时支持 V1 和 V2，源级调用形式不随
版本改变。`TCGEN05_1CTA_USED` 且没有 V2 marker 时按既有 cubin ABI 选择 V1；
`#pragma AT_ENTRY_FRAGMENT_TMEM_CTA1_V2(1)` 则让三段 lowering 一起静默切到
V2。也可用 `#pragma AT_ENTRY_FRAGMENT_TMEM_CTA1(1)` 显式断言 V1；两种 marker
同时出现会在汇编期报错。

V1 builtin 使用 `reserved+0x40` phase 和 `reserved+0x50` 组合位图。组合位图
不是直接照搬最初的 `VIADD(index,16) -> SHF` 排程：真机诊断曾观察到依赖过近
时写成 `0x11` 而非 `0x00010001`，dealloc 后因此残留 `0x10` 并由 ATEXIT
报错。最终序列先生成低半区 one-hot，再把它显式左移 16 位并 OR；真机读回
验证分配后为 `0x00010001`、释放后为 `0`。V1、V2 builtin 均在 B200 上连续
运行三次正常退出。
