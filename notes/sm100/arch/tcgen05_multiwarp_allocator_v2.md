# TCGEN05 多 warp 1-CTA allocator（V2 entry fragment）

## 结论

`tests/asm_construct/tcgen05_alloc_multiwarp_v2_sm100.sass` 是独立的 CUDA
13.1 V2 lowering，不能由 V1 kernel 只增加
`AT_ENTRY_FRAGMENT_TMEM_CTA1_V2` pragma 得到。其 120 条 user SASS（含调度控制）
与 CUDA 13.1 ptxas 输出逐 bit 相同，SHA-256 为：

```text
1452d1deab36497257b07ddce5605e5728cc00daa2648a14bdb902de4b6a964a
```

仓库 assembler 生成的 cubin 已在 Modal B200 上以一个 CTA、
`block=64/128/160` 分别运行，每种配置重复 3 次。所有 warp 的 lane 0 都读回
同一个 TMEM base（本轮均为 0），随后 owner warp 正常 dealloc、relinquish 并
退出，没有 hang 或 CUDA launch error。

这里的 bit-exact 基线特指 CUDA 13.1。CUDA 13.4 对同一 CUDA 源生成了更短的
`0x700`-byte user text，并把 offset 表相应改为 int-wide
`0x400/0x450`、cooperative `0x40/0x1d0/0x330/0x530`、exit
`0x2b0/0x560/0x5a0`；它仍访问同样的 `+0x14/+0x18/+0x1c` V2 状态布局。
当前 hand-SASS 选择 13.1 是因为仓库 V2 ELF contract 也是已动态验证的 13.1
`CUDA_API_VERSION=0x83` 组合，而不是把两个 toolkit 版本的 contract 混合。

## 为什么 V1 user SASS 不能复用

V1 entry fragment 与 allocator helper 使用：

- `reserved+0x40`：allocation phase；
- `reserved+0x48`：previous `ATEXIT_PC`；
- `reserved+0x50`：allocation mask。

V2 把 `reserved+0x40..0x5f` 变成一个 opaque partition。动态捕获的 entry
fragment 会在 `+0x40` 保存 previous `ATEXIT_PC`，所以 V1 helper 若继续从
`+0x40` 读取 phase，会把 handler 地址低字节误解释为 allocator 状态。

CUDA 13.1 lowering 显示用户侧可见的 V2 字段为：

| partition offset | allocator 用途 |
|---:|---|
| `+0x14` | allocation mask A |
| `+0x18` | allocation mask B |
| `+0x1c` | allocation phase |

入口 fragment 清零 `+0x14..+0x1f`。分配成功后，helper 对 `+0x14` 和
`+0x18` 都执行 `ATOMS.OR`；释放前分别读取并校验两份 mask，随后对两者执行
`ATOMS.AND`。最终在 relinquish 前向 `+0x1c` 写入 phase=1。

`+0x00..+0x07` 仍由 entry/exit fragment 保存 previous `ATEXIT_PC`；
`+0x08..+0x13` 没有被 user allocator SASS 访问，继续视为 driver 私有状态。

## 多 warp 控制结构

只有 warp 0 进入 warp-synchronous `tcgen05.alloc/dealloc` lowering。第一次
`BAR.SYNC 0` 发布写在 static shared `+0x400` 的 TMEM base；每个 warp 的 lane 0
把该值写到 `out[warp_id]`；第二次 `BAR.SYNC 0` 保证所有 consumer 离开后，
warp 0 才清理两份 V2 mask、释放 SM pool permit 并把 phase 置为 1。

两个 CTA barrier 都有 warp-convergence 前置条件。allocator 内部的
owner/elected 路径结束后必须先执行 `WARPSYNC.ALL`（若使用结构化分歧则用
匹配的 `BSYNC`）；多个 execution group 分别抵达相同 `BAR.SYNC` 不能替代
warp 汇聚，B200 实测会报 CUDA 719。当前基线与 nvcc lowering 都在 BAR 前
保留了这一步。

## CUDA 13.1 EIATTR contract

| 项目 | 值 |
|---|---|
| entry fragment | `AT_ENTRY_FRAGMENT_TMEM_CTA1_V2`（6） |
| reserved shared | `0x60` bytes |
| opaque partition | offset `0x40`、size `0x20` |
| static shared | `0x404` bytes |
| `NUM_BARRIERS` | 1 |
| int-warp-wide offsets | `0x490, 0x4e0` |
| cooperative offsets | `0x60, 0x250, 0x3c0, 0x5c0` |
| exit offsets | `0x340, 0x5f0, 0x630` |
| user instructions | 120（`0x780` bytes） |

这些 offset 由 assembler 根据最终 SASS 和 `#coop_group` 标注生成。与 V1
一样，它们相对 cubin user text，不包含 driver 注入的 V2 entry prefix。

## 回归入口

- 参考 CUDA：`tests/tcgen05_alloc_multiwarp.cu`
- hand SASS：`tests/asm_construct/tcgen05_alloc_multiwarp_v2_sm100.sass`
- 静态测试：`python3 tests/asm_construct/test_tcgen05_alloc_multiwarp_v2_sm100.py`
- 真机：`tools/modal_tcgen05_alloc.py --hand-source ... --block-size N`
