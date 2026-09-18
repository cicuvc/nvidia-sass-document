# sm100 TCGEN05 工具链检查点（2026-09-17）

本文记录暂停硬件探测时的状态。目标是先建立能独立生成 cubin 的可靠工具链，
再继续分析 TCGEN05。除非另有说明，本文中的“通过”只指 B200/sm_100a；
sm_103 需要独立验证。

## 硬性工作规则

1. 后续 TCGEN05 测量 kernel 必须由本仓库 assembler 从源 SASS 完整生成。
2. 可以把 nvcc/ptxas 输出作为 ISA、ABI 和 lowering 的观察样本，但不得再把
   patch nvcc cubin、修改其指令流或依赖其数值地址 ABI 作为实验的执行路径。
3. lift 后不修改地 round-trip 仍可用于验证 assembler；lift 后修改的 cubin 只能
   作为诊断材料，不能产生可引用的性能或正确性数据。
4. 多 warp TMEM allocator 和 mbarrier helper 未通过下述验收前，不继续做
   UTCHMMA 与多 contender 的联合吞吐实验。

## 当前可靠基础

- assembler 已能表达 sm_100a 的 `tmem[...]`、`idesc[...]` operand，并能生成
  driver 可加载的 cubin。
- `tests/asm_construct/tcgen05_alloc_sm100.sass` 中的 allocator/deallocator
  transcription 已在 **32-thread、单 warp CTA** 上运行；它同时保留了
  `TCGEN05_1CTA_USED`、int-warp-wide/cooperative-group offset 和保留 shared
  symbol 等 loader ABI 信息。
- 裸 `LDTM`/`STTM`、`UTCCP`、`UTCSHIFT` 和单 warp `UTCHMMA` 已有可运行的
  assembler 路径。具体结论仍以各 instruction note 为准。
- B200 的独立 shared/LSU 基准是可靠的：单 stream 约 0.5 request 或
  wavefront/cycle，四 subcore 合计约 1 wavefront/cycle。见
  `b200_lsu_exchange_topology.md`。
- assembler 已支持 `NUM_MBARRIERS`、`TCGEN05_1CTA_USED`；并会从最终 SASS
  自动生成 `EXIT`、`VOTEU/REDUX` 的 offset 表，cooperative-group 位置则由
  零长度 `#coop_group` 标注生成（旧 numeric pragma 仅作兼容与一致性校验）。
  这仍不等于能自动推导完整 TCGEN05 ABI。
- V1 `AT_ENTRY_FRAGMENT_TMEM_CTA1` 已动态捕获：driver 在用户代码前拼接
  `0x1b0` bytes 的有效初始化序列和 5 条 NOP，并顺序 fall-through 到用户
  instruction 0；详见 `tmem_entry_fragment.md`。Modal CUDA 12.8 nvcc 默认
  发出 V1，不是 V2。
- V2 已由本地 assembler 完整生成并在 Modal B200 上动态验证。它不能通过只改
  entry enum 获得：V2 还要求 32-byte opaque reserved-shared partition、API
  `0x83`、`EIATTR 0x5f=0x101` 和对应 `.nv.compat`。补齐后，即使运行容器仍为
  CUDA 12.8.1，driver 也会注入 V2；其有效 fragment 为 `0x170` bytes，加 1
  条 NOP 后 fall-through 到用户 instruction 0。详见 `tmem_entry_fragment.md`。
- V2 多 warp allocator user lowering 也已独立完成：CUDA 13.1 的 120 条 SASS
  逐 bit 复现，并在 block=64/128/160 上各重复 3 次通过完整
  owner/publish/quiesce/dealloc/relinquish 闭环。V2 partition 的 user-visible
  状态为 `+0x14/+0x18` 两份 mask 和 `+0x1c` phase。详见
  `tcgen05_multiwarp_allocator_v2.md`。

## 四 contender 实验恢复结果（2026-09-18）

原目标已经用 `tests/asm_construct/probe_sm100_utchmma_lds_saturation.py`
恢复。执行 cubin 完全由本仓库 assembler 生成；V1 512-column allocation 在
B200 上连续通过，LDS.128 使用三组 scoreboard 并静态展开，避免 loop-control
和 late writeback 混杂。有效短窗口结果为 LDS-only 643 cycles，4×UTCHMMA
combined 906 cycles，增量 263 cycles = 65.75 cycles/MMA，和 A+B 的 64 个
128-B wavefront 对上。详细解释见 `../instr/utchmma.md`。

以下故障记录仅描述已经淘汰的旧原型，仍然不能引用为微架构证据。

## 旧原型：不能引用的实验

目标实验是 warp 0 连续发射 UTCHMMA，warps 1--4 分布在四个 subcore 上连续
发射 `LDS.128`，以饱和 B200 的 shared read data stage。当前没有得到可信
结果：

- ptxas 版本把循环内地址不变的 `LDS.128` 提到循环外，循环体只保留 XOR；
  它不是 shared saturation 测试。
- lift/patch 版本依赖 ptxas 的数值 `CALL.REL`/`RET.REL`、保存 PC 常量、
  reconvergence frame 和 metadata offset。改变代码尺寸后，即便逐项重定位，
  仍很容易把 allocator/helper ABI 一同改变。
- 未 scoreboard 的 LDS destination 过早复用、将 `RZ` 当作反复 vector-load
  sink、以及只等待最后一个请求，都不能可靠完成整条异步请求流。
- 原 ptxas kernel 还把 R4/R5 用作 global output address；LDS 的晚写回曾与之
  重叠并产生 700/716。把输出地址移走只能消除一个混杂因素，不能证明其余
  closure 正确。
- 单个静态 LDS 序列有局部可运行样本，但更长序列、循环复用和 160-thread
  launch 出现过 719/721 或超时。这些只能说明工具协议不完整，不能据此推断
  TMEM/LSU 吞吐或资源深度。

因此此前四 contender 尝试中的故障、超时和周期数全部作废；尤其不能从中
得出“UTCHMMA 占 shared 带宽的一半”或其它定量结论。

## 多 warp TMEM allocator 的缺口

> 2026-09-18 更新：V1、V2 的最小 owner/publish/quiesce/dealloc 闭环均已打通。
> warp 0 是唯一 owner，两个 `BAR.SYNC` 包围 consumer 区域；仓库 assembler
> 生成物已在 block=64/128/160 的单 CTA 上运行成功。SASS、EIATTR、symbol 和
> relocation 对照见 `tcgen05_multiwarp_allocator_v1.md` 与
> `tcgen05_multiwarp_allocator_v2.md`。以下条目仍作为把该
> 基线抽象成通用 emitter、加入真实 TMEM payload 和覆盖异常路径的验收清单。

现有 `tcgen05_alloc_sm100.sass` 是对一个 block=32 lowering 的手工转录，不是
可复用的 CTA allocator。多 warp 版本至少必须显式解决：

1. **唯一 owner**：确定哪个 thread/execution group 获取 allocation permit、
   执行 `UTCATOMSWS` 协议并真正分配 TMEM。
2. **发布**：将分配出的 column/base 写入 CTA 内所有参与 warp 都能观察的
   shared 状态，并定义值有效的先后关系。
3. **入口 rendezvous**：非 owner warp 在使用 TMEM 前等待发布完成；不能只靠
   warp-local `WARPSYNC`。
4. **退出 quiescence**：所有使用 TMEM 的 warp 完成异步操作和 TMEM 访问后，
   唯一 deallocation owner 才能释放。
5. **permit/at-exit 协议**：明确 `relinquish_alloc_permit`、正常 dealloc 和
   loader 注入的 at-exit guard 各自负责什么，避免 double free 或泄漏。
6. **CTA 尺寸与 partial warp**：block=32/64/128/160 以及非整 warp 情形必须
   有定义，不能把 thread 0、warp 0、elect leader 三者混为一谈。
7. **metadata**：cooperative/int-warp-wide instruction offsets、保留 shared
   symbol、register/shared resource 需求应由源代码标注自动生成或检查，不能
   靠复制某个 nvcc kernel 的常量。

这里还存在一个容易混淆的两级同步要求：owner/non-owner 分支会先把一个 warp
拆成多个 execution group；在进入 CTA 级 `BAR.SYNC` 之前，必须先用匹配的
`BSYNC` 或 `WARPSYNC` 把每个 warp 完整汇聚。不能让各 execution group 分别
执行同一个 BAR 来替代汇聚，B200 上这样会报 719。nvcc 的 lowering 也总是在
BAR 前插入 BSYNC/WARPSYNC。当前 allocator builtin 会在内部 elected-owner
路径结束处发出 `WARPSYNC.ALL`，V1/V2 基线则在 publish/quiescence BAR 前保留
显式 warp 汇聚。

在共同分析 nvcc 的多 warp lowering 前，不假定 allocator 是“所有 warp 都执行
一次”、还是“一个 warp 分配后 CTA 广播”。这正是下一阶段需要确认的协议。

## 建议的 allocator 工具接口

优先实现 Python 侧的结构化 emitter，而不是先给 assembler 加文本宏。建议
接口形态如下（名称暂定）：

```python
alloc = Tcgen05CtaAllocator(
    cta_group=1,
    columns=512,
    block_threads=160,
    shared_state=SharedRegion(...),
    scratch=ScratchRegs(...),
)
source += alloc.emit_prologue()
source += payload(alloc.tmem_base)
source += alloc.emit_epilogue()
```

emitter 应返回的不只是字符串，还应包含：占用的 GPR/UR/predicate/SB、shared
范围、需要的 pragma/ELF attributes、生成的 cooperative instruction label，
以及 payload 必须满足的入口/退出契约。所有内部跳转使用 symbolic labels；
禁止让调用者维护数值 PC 或手工平移 offset。

长期应让 ELF builder 从指令 annotation/label 自动生成 offset attributes。
在自动生成完成前，至少由 assembler 在最终 layout 后解析 label 并生成，且对
手写数值 offset 与实际 opcode 位置不一致的情况报错。

## mbarrier 的心智负担与建议接口

当前 probe 重复手写以下易错片段：expected-arrival state 的位构造、单 leader
初始化、`SYNCS.EXCH.64` scoreboard、`FENCE.VIEW.ASYNC.S`、`UTCBAR` commit、
phase/parity wait loop，以及相应 BSSY/BSYNC 或 CTA rendezvous。代码看似短，
但寄存器、predicate、barrier index、phase 和 scoreboard 任一项复用错误都会
产生静默数据错误或 fault。

建议提供结构化 helper（名称同样暂定）：

```python
mbar = MBarrier(
    shared_addr=0x600,
    slot=0,
    scratch=ScratchRegs(...),
)
source += mbar.init(expected_arrivals=1, scope="cta", owner="thread0")
source += mbar.commit_tcgen05(cta_group=1)
source += mbar.wait_parity(0)
```

helper 必须：

- 自动汇总 `NUM_MBARRIERS`，校验 shared 地址的大小、对齐与不重叠；
- 明确区分初始化 owner、tcgen05 单线程 issuer 和等待参与者；
- 分配或由调用者显式提供 scratch 资源，拒绝隐式 clobber；
- 封装正确的 scoreboard claim/wait 和 yield/stall 组合；
- 用唯一 symbolic label 生成控制流，允许一个 kernel 使用多个实例；
- 把 `commit`、`wait`、普通 CTA rendezvous 和 memory fence 分成独立操作，
  不用一个“万能 barrier”隐藏不必要的同步；
- 输出可审计的原始 SASS，并提供 bit-exact/运行时单元测试。

## 工具链还需补齐的基础能力

- TCGEN05 operand 的 encode/decode/round-trip 专项测试，覆盖 `tmem`、`idesc`、
  1CTA/2CTA 和 omitted-default operand。
- source-level resource reservation：检测 allocator/helper/payload 的 GPR、UR、
  predicate、SB 和 shared-memory 冲突。
- assembler 在最终 layout 后生成 instruction-offset metadata，彻底去掉手算 PC。
- 一个异步请求 closure helper：区分 scoreboarded request、unscoreboarded steady
  stream 和退出前 drain；不能再以“最后一条 sentinel”未经验证地代表整流完成。
- 所有新 probe 默认 `check_deps=True`。只有说明 depchecker 尚不理解某种依赖、
  并有独立验证时才允许局部关闭。
- 为 generated SASS 保存 sidecar manifest：架构、block size、寄存器数、shared
  layout、barrier layout、TCGEN05 metadata 和 source hash，以便复现实验。

## 验收矩阵

### Allocator

- block=32、64、128、160：每个 CTA 只形成一次逻辑 allocation，所有 warp
  观察到相同且合法的 TMEM base。
- 每种 block size 连续多次 launch，初始化状态不依赖上一次 launch residue。
- 多个 CTA 在允许的 residency 下并发，无 shared/global 状态串扰。
- 正常路径、无 payload 路径和提前分支到共同 epilogue 均能 clean dealloc；
  driver 无 719/721，后续 allocator kernel 仍能运行。
- 使用 allocator 生成的最小 LDTM/STTM round-trip 能验证所有参与 warp 的数据。

### Mbarrier helper

- init + software arrive/wait 的最小测试。
- init + `UTCBAR` commit + parity wait，分别覆盖 1 个和多个 tcgen05 operation。
- 两个独立 mbarrier 实例，验证地址、slot、phase 和 scoreboard 不串扰。
- owner 不是所有 thread 时，等待者不会在初始化发布前访问对象。
- 生成的 `NUM_MBARRIERS` 和实际 shared layout/指令序列一致。

### 独立性与回归

- 测试构建和运行过程不读取 nvcc cubin，也不调用 patch/lift 生成被执行代码。
- `cuobjdump -elf/-sass`、nvdisasm 和 CUDA driver 均接受生成物。
- 对错误的 block size、资源重叠、缺失 metadata 和不闭合 async operation 提供
  明确的构建期失败。
- 基础通过后，才恢复“UTCHMMA + 四 subcore LDS.128”联合实验，并先运行
  LDS-only、MMA-only、combined 三个同源生成的 control。

## 下一次共同分析的切入点

先选取 nvcc 生成的 block=32/64/128/160 最小 alloc/dealloc 样本，只做静态
对照，不 patch。逐段回答：谁竞争 permit、allocation result 存在哪里、CTA
级发布/等待发生在哪、哪些分支属于错误/at-exit 路径、哪些 instruction offset
被 loader 消费。协议确定后，再冻结 allocator IR/API；mbarrier helper 可以与
其并行设计，但不要把两套同步状态混成同一个抽象。
