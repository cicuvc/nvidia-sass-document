# TCGEN05 TMEM entry fragment（B200）

## 结论

在 Modal B200、CUDA 12.8 环境中，指定
`EIATTR_AT_ENTRY_FRAGMENTS = AT_ENTRY_FRAGMENT_TMEM_CTA1` 后，driver 会把
一段原生 SASS 放在用户 kernel 代码之前，并从该 fragment 顺序落入用户入口。

这不是“单独 trampoline 跳到用户 kernel”的模型：fragment 的最后一条有效
指令是设置 `ATEXIT_PC` 的 `BMOV.64`，随后是 5 条 NOP，再直接执行用户第 0 条
指令；中间没有 `BRA/JMP/CALL/JMX`。因此 V1 不需要通过 RPC 恢复某条入口跳转
指令的 PC。

本机 CUDA 12.8.1 容器中的 nvcc/ptxas 对
`tcgen05.alloc.cta_group::1` 默认写入枚举值 **4**，cuobjdump 显示为
`AT_ENTRY_FRAGMENT_TMEM_CTA1`，不是枚举值 6 的
`AT_ENTRY_FRAGMENT_TMEM_CTA1_V2`。

## 捕获方法

探测工具是 `tools/modal_sm100_entry_fragment.py`，执行 kernel 完全由仓库
assembler 生成，没有 patch nvcc cubin。

实验严格分成三个独立的 Modal invocation/context：

1. V1 kernel 的指令 0 仅执行 `LEPC {R4,R5}`，随后把值写回 global memory；
   得到非零、16-byte 对齐的代码 VA。
2. 新 context 中加载相同 V1 kernel 和最小 `copy16` kernel，从 LEPC 返回地址
   读取 16 字节；结果逐 bit 等于 assembler 生成的 LEPC 指令字：
   `4e730400000000000000000000ca0f00`。
3. 再开新 context，从 `LEPC & ~0xfff` 复制包含用户入口的 4-KiB 代码页。
   用户入口位于页内 `0xb00`，该处开始的全部用户指令与原 cubin 相同。

三步远端函数 timeout 均为 30 秒。没有把 V1/V2、RPC、ATEXIT 读取或多个候选
方案放进同一个 CUDA context。

一次代表性运行中：

```text
LEPC                  = 0x00002b031f5a9b00
captured page base    = 0x00002b031f5a9000
user entry page offset= 0xb00
entry fragment        = 0x900..0xaa0
padding               = 0xab0..0xaf0
user instruction 0    = 0xb00
```

绝对 VA 每次 module load 都会变化，页内布局与内容稳定。

## V1 fragment SASS

下面的 offset 相对于捕获的 4-KiB page。`0x910/0x920/0xaa0` 是当前通用
disassembler 尚未渲染的 BMOV composite，但 operand field 和既有
`ATEXIT_PC` probe 足以确定其含义。

```sass
0900  S2UR UR8, SR_CgaCtaId
0910  BMOV.32 R4, ATEXIT_PC.LO
0920  BMOV.32 R5, ATEXIT_PC.HI
0930  UMOV UR4, 0
0940  LDCU.64 {UR6,UR7}, c[0x0][0x340]
0950  UPRMT UR4, UR8, 0x654, UR4
0960  BRA.U.NOT_TID0 +0xc0               // non-TID0 跳到共同初始化尾部
0970  ELECT P0, URZ, PT
0980  UMOV UR5, 0x40
0990  ULEA UR5, UR8, UR5, 0x18
09a0  @P0 STS.U8 [RZ+UR5], RZ            // allocation phase = 0
09b0  UMOV UR5, 0x50
09c0  ULEA UR5, UR8, UR5, 0x18
09d0  @P0 STS [RZ+UR5], RZ               // allocation mask = 0
09e0  UMOV UR5, 0x48
09f0  ULEA UR5, UR8, UR5, 0x18
0a00  @P0 STS.64 [RZ+UR5], {R4,R5}       // 保存 previous ATEXIT_PC
0a10  @P0 ACQSHMINIT
0a20  @P0 SYNCS.ARRIVE.TRANS64.A1T0 RZ, [RZ+UR4], RZ
0a30  ACQSHMINIT
0a40  SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR4], RZ
0a50  @!P0 BRA +0
0a60  SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR4], RZ
0a70  @!P0 NANOSLEEP.SYNCS 0x10000
0a80  @!P0 SYNCS.PHASECHK.TRANS64 P0, [RZ+UR4], RZ
0a90  @!P0 BRA -0x40
0aa0  BMOV.64 ATEXIT_PC, {UR6,UR7}
0ab0  NOP
0ac0  NOP
0ad0  NOP
0ae0  NOP
0af0  NOP
0b00  LEPC {R4,R5}                       // 用户 kernel 第 0 条指令
```

`c[0x0][0x340]` 提供 driver 安装的 TMEM at-exit handler VA；fragment 先把旧
`ATEXIT_PC` 保存到每 CTA reserved shared 的 `+0x48`，清空 `+0x40` allocation
phase 和 `+0x50` allocation mask，完成 CTA 范围的 shared-init rendezvous，
最后把新 handler 写进 `ATEXIT_PC`。这与
`tmem_atexit_handler.md` 中 handler 最终从 `+0x48` 恢复 previous hook 的行为
闭合。

## V2 ABI 与动态捕获

本机 CUDA 13.1/13.4 对 `sm_100a` 和 `sm_103a` 生成的最小样本均使用枚举值
**6**：`AT_ENTRY_FRAGMENT_TMEM_CTA1_V2`。V2 不能只把 V1 的 entry-fragment
枚举从 4 改成 6；这样构造的 cubin 虽能加载，但 launch 会报 CUDA 719。除枚举
之外，至少还需要匹配以下 ABI：

- reserved shared 从 V1 的 `0x54` bytes 增大到 `0x60` bytes；
- V1 的三个具名状态 symbol 被一个 `__nv_reservedSMEM_tcgen05_partition`
  （offset `0x40`、size `0x20`）替代；
- per-kernel CUDA API version 为 `0x83`，并带 `EIATTR 0x5f = 0x101`；
- `.nv.compat` 使用 CUDA 13.1/13.4 的 V2 contract，其中 ISA class 为 2，另有
  `0x101` ABI marker 和 fastpath-finalize 记录。

补齐这些字段后，由本仓库 assembler 在本地生成的 V2 cubin 可以在 Modal 的
CUDA 12.8.1 容器、B200 driver 上正常加载和执行。这里容器中的 nvcc 版本只
决定构建工具；实际 entry fragment 由 host driver 根据 cubin contract 注入。

V2 也按 LEPC、copy16、copy-page 三个独立 context 验证。一次代表性运行为：

```text
LEPC                  = 0x00002a6b9d5a9a80
captured page base    = 0x00002a6b9d5a9000
user entry page offset= 0xa80
entry fragment        = 0x900..0xa60
padding               = 0xa70
user instruction 0    = 0xa80
```

copy16 的 16 bytes 同样逐 bit 等于 cubin 中 assembler 编码的第 0 条 `LEPC`。
V2 仍是直接拼接并 fall-through，不是 trampoline：

```sass
0900  S2UR UR6, SR_CgaCtaId
0910  BMOV.32 R4, ATEXIT_PC.LO
0920  BMOV.32 R5, ATEXIT_PC.HI
0930  UMOV UR4, 0x40
0940  UMOV UR5, 0
0950  LDCU.64 {UR8,UR9}, c[0x0][0x340]
0960  ULEA UR4, UR6, UR4, 0x18
0970  UPRMT UR5, UR6, 0x654, UR5
0980  BRA.U.NOT_TID0 +0x60
0990  ELECT P0, URZ, PT
09a0  @P0 STS.64 [RZ+UR4], {R4,R5}     // partition +0x00: previous ATEXIT_PC
09b0  @P0 STS [RZ+UR4+0x14], RZ
09c0  @P0 STS.64 [RZ+UR4+0x18], RZ
09d0  @P0 ACQSHMINIT
09e0  @P0 SYNCS.ARRIVE.TRANS64.A1T0 RZ, [RZ+UR5], RZ
09f0  ACQSHMINIT
0a00  SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR5], RZ
0a10  @!P0 BRA +0
0a20  SYNCS.PHASECHK.TRANS64.TRYWAIT P0, [RZ+UR5], RZ
0a30  @!P0 NANOSLEEP.SYNCS 0x10000
0a40  @!P0 SYNCS.PHASECHK.TRANS64 P0, [RZ+UR5], RZ
0a50  @!P0 BRA -0x40
0a60  BMOV.64 ATEXIT_PC, {UR8,UR9}
0a70  NOP
0a80  LEPC {R4,R5}                     // 用户 kernel 第 0 条指令
```

V2 把有效入口序列从 V1 的 `0x1b0` bytes 缩短为 `0x170` bytes，并把 padding
从 5 条 NOP 缩到 1 条。partition 中 `+0x00..+0x07` 保存旧 `ATEXIT_PC`，
`+0x14..+0x1f` 被入口清零。CUDA 13.1/13.4 的真实 user allocator lowering
进一步证明 `+0x14/+0x18` 是两份 allocation mask，`+0x1c` 是 phase；
`+0x08..+0x13` 仍未被 entry fragment 或 user allocator 访问，应继续视为
driver 私有布局。详见 `tcgen05_multiwarp_allocator_v2.md`。

## V1/V2 对照

| 项目 | V1（CUDA 12.8 产物） | V2（CUDA 13.1/13.4 产物） |
|---|---:|---:|
| entry enum | 4 | 6 |
| reserved shared | `0x54` | `0x60` |
| 用户入口页内 offset | `0xb00` | `0xa80` |
| 有效 fragment 长度 | `0x1b0` | `0x170` |
| 尾部 NOP | 5 | 1 |
| 新 handler VA | `UR6/UR7` | `UR8/UR9` |
| 状态 symbol | phase/ATEXIT/mask | opaque 32-byte partition |

## 对 allocator 工具的直接影响

- V1 entry fragment 已经完成 reserved bookkeeping 的初始化和 at-exit hook
  安装；assembler 侧 allocator 不应重复实现这段入口协议。
- 用户 SASS 的 instruction offset 仍从自身 `0x0` 计数；driver 拼接不会改变
  cubin 内的 branch/metadata offset。运行时 `LEPC` 则返回拼接后用户代码的
  实际 VA。
- fragment 使用 CTA-wide `ACQSHMINIT/SYNCS` rendezvous，因此多 warp kernel
  在进入用户指令 0 前已经共同经过这一入口同步；这与用户代码内部真正的
  TMEM allocation/publication 协议仍是两个层次。
- V1/V2 必须由 source pragma 明确选择；assembler 不能随本机 toolkit 版本静默
  切换 ABI。两者的 reserved-shared symbol 和 compat metadata 也必须成套生成。
- allocator user SASS 同样必须匹配版本：V1 helper 访问 `+0x40/+0x50`，V2
  helper 访问 partition `+0x14/+0x18/+0x1c`，不能只替换 entry enum。

## 相关文件

- `tmem_atexit_handler.md`：与本 entry fragment 配对的 leak-recovery handler。
- `tcgen05_tooling_checkpoint.md`：多 warp allocator 与 mbarrier 工具验收计划。
- `notes/sm100/instr/utcatomsws.md`：allocator software-state 操作。
