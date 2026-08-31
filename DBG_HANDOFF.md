# DBG_HANDOFF.md — sassdbg 调试器实现现状与交接文档

> 维护状态: 2026-08-30 (M10 真实 cubin 挂载完成后的工作树)
> 配套源码: `sassdbg/patch.py`(M9 引擎)、`sassdbg/real.py`(M10)、`sassdbg/stepper.py`、`sassdbg/cli.py`、`sassdbg/cubin.py`
> 配套测试: `tests/asm_construct/test_sassdbg_m*.py` (m3–m10)

---

## 0. 一句话总结

设备侧 SASS 动态补丁调试器: 把断点处 16 字节指令覆写成 `JMP <stub>`，
借 kernel 自己的寄存器(R0-R7)完成 spill/上报/自旋/恢复，**零寄存器预留**，
多 warp/多 CTA/发散组感知，支持断点、单步、反向、命令注入、CLI，
并可直接挂载真实 nvcc cubin(无需源码、无需重汇编)。

---

## 1. 整体原理 (M1–M10 演变)

### 1.1 核心机制链

```
bp 命中(执行到达 patch 词) ──> JMP ──> per-bp stub ──> per-warp handler(自旋停车)
                                         │                    │
                                spill kernel 寄存器      上报 hit(写 hit slot)
                                R0/R1→RPC, R2-R7→frame   等 release
                                        │                    │
                                        └──> host 看到 hit → dump/set/exec
                                             release → per-lane F_RTGT/F_RELEASE + GO
                                                    → 组整体收敛退出 handler
                                             → thunk(重放原指令 + JMP 后继) → kernel 继续
```

### 1.2 关键设计决策

| 决策 | 内容 | 动机 |
|------|------|------|
| **零寄存器预留** (M9) | stub 借 R0/R1，handler 借 R2-R7，全部 spill/restore | 真实 cubin 有寄存器预算，任何预留都不安全；ptxas 保证 ≥24 个寄存器 |
| **RPC 当 64-bit spill 槽** | stub 入口 `RPCMOV Rpc.LO/HI, R0/R1` 把 kernel R0/R1 暂存进 RPC | JMP IMM 不写 RPC；RPC 在 stub→handler 的 F_R01 store 前存活 |
| **Frame pool** | 每 (warp,lane) 一个 0x80 帧，`f = CTAID*(ctawarps*32)+TID` 索引 | 无 SETLMEMBASE(基址 warp 共享会干扰兄弟组)；spill 走绝对 devmem |
| **per-warp handler 副本** | 0x1000 步进，烘焙各自 comms 地址 | 免去每 lane 区分 warp；`handler_va = h0 + (f>>5)*0x1000` |
| **ELECT 选 leader** | `ELECT P6, URZ, PT`(候选 = MACTIVE)，最低活跃 lane | 替代 M8b 的 FLO+ISETP；hit-slot RMW 只由 leader 执行 |
| **GO 广播释放** | 逐 lane 写 F_RTGT/F_RELEASE → 最后 bump per-warp GO 字 | 消除 lane 滴漏(逐 lane 出自旋导致 ITS 不再收敛 → 碎片 BAR/断点) |
| **per-bp stub + 持久 bp** | patch 词永不恢复，release 走 thunk | 无 restore-vs-refetch 竞态；循环重命中无需重新 arm；icache 冷线 |
| **per-site thunk 缓存** | `(bp,insts,target_va)` → 共享 thunk VA | 同 (warp,site) 的组执行同一 blob VA → BAR/WARPSYNC 同 PC 会合 |
| **JMP IMM 是绝对跳转原语** | `JMP 0x94a`, UImm(57) SCALE 4 | 传字节地址给 assemble_flat(它自己 /4) |
| **patcher = 设备内核** | 一个 STG.E.128 写 16B patch 词到代码空间 | host cuMemcpy 不能写代码 VA；warm-up launch 先跑一次 |
| **CCTL.I.IVALL 硬化** | `IVALL; NOP×32(stall 8); IVALL` | 单次 IVALL 会与 in-flight fill 竞态(至多一次陈旧执行) |

### 1.3 真实 cubin 挂载 (M10, 最新)

```
cubin 文件 ── 解析 ELF(.text.<func> 定位/入口偏移/reloc 重叠检查)
   └─> patch 入口 0x20 字节: LEPC {R8,R9} + JMP <heap prologue>
   └─> cuModuleLoadData(patched bytes) ──> CudaModule
heap prologue (arena+Layout.kprol, arena VA 烘焙成 MOV32I 立即数):
   STG CTRL_BASE 报告 kernel base(来自 LEPC)
   gate 自旋 ──> 硬化 IVALL ──> 重放原 inst 0/1 ──> RET 回 entry+0x20
   (orig 0/1 就住在 heap 重放槽; 这两个地址也可以下 bp)
```

- 无需源码、无需重汇编；`dbgctrl` 参数不存在 → arena VA 烘焙进 prologue 立即数。
- 被 trampoline 覆盖的原 inst 0/1 由 lift 文本重汇编回放(语料 round-trip 字节精确)。
- 入口窗口 [entry, entry+0x20) 有文本重定位的 kernel 会被 `cubin.load_kernel` 拒绝。
- M10 E2E: `test_sassdbg_m10.py` T0–T3 (裸 trampoline / 双 bp+dump+set / 持久重挂 / 步进)。

---

## 2. Arena / comms 布局 (Layout, patch.py)

```
arena (16B 对齐, Layout.total = kprol + KPROL_SZ)
├─ +0x000  ctrl: +0x00 CTRL_BASE(u64 base 报告)  +0x08 CTRL_GATE(u32 启动门)
├─ +0x100  stub 槽区  STUB_OFF.. STUB_SZ=0x200/槽 × max_bps   (per-bp, 24 insts)
├─ handler 区        每 warp 0x1000(149 insts, retline=0x940, cmdret=0x530)
├─ +0x10000 thunk arena  0x100/槽 × 64  (16 insts max/槽, host 构建)
├─ hslots   mw×32 × 16B  hit 槽  {u32 mask, u32 va_lo, u32 va_hi, u32 seq}
├─ go       mw × 16B    per-warp GO 字 (+0, 16B 对齐为了让 cmdbuf 16B 对齐)
├─ cmdseq   mw × 16B    per-warp 命令序列号 (host 写 +0, handler echo 到 +4)
├─ cmdbuf   mw × 0x400  per-warp 命令缓冲(≤56 insts + epilogue)
├─ results  mw × 0x400  per-warp 命令结果窗口
├─ pool     mw×32 × 0x80  per-(warp,lane) 帧
└─ kprol    0x400         M10 heap 入口 prologue (重放 orig inst 0/1)
```

### 2.1 Frame (FRAME=0x80, per (gwarp,lane))

| 偏移 | 字段 | 说明 |
|------|------|------|
| +0x00..0x14 | F_R2..F_R7 | kernel R2-R7 spill (6×4B) |
| +0x18 | F_PR | P2R PR 快照 |
| +0x20 | F_R01 | kernel R0/R1 (8B — **必须 8B 对齐**, 0x1C 会 716) |
| +0x28 | F_SITE | site VA (8B, stub 烘焙) |
| +0x30 | F_RELEASE | per-lane 释放代数 |
| +0x34 | F_F | 全局 lane-frame 索引 f |
| +0x38 | F_RTGT | 本次释放的 thunk VA (u64) |
| +0x40 | F_CMD | per-lane 命令基线 |
| +0x44 / +0x48 | F_RELBASE / F_GOBASE | 命令分派前保存的自旋基线(命令可 clobber R2-R7) |

### 2.2 Stub (24 insts, 借 R0/R1)

```
RPCMOV Rpc.LO/HI ← R0/R1          # kernel R0/R1 -> RPC
S2R R0,CTAID; IMAD R0,R0,K,RZ     # K=ctawarps*32 烘焙
S2R R1,TID; IADD3 R0,R0,R1        # f = ctaid*(ctawarps*32)+tid
MOV32I R1,pool_lo; IMAD R0,R0,0x80,R1; MOV32I R1,pool_hi   # {R0,R1}=帧地址
STG [帧+F_R2..3], R2/R3           # kernel R2/R3 spill
RPCMOV R2/R3 ← Rpc.LO/HI; STG.64 [帧+F_R01]               # 恢复 kernel R0/R1
MOV32I R2/R3 = site VA; STG.64 [帧+F_SITE]
# 计算 handler VA = h0 + (f>>5)*0x1000
CALL.ABS.NOINC PT, {R2,R3}, 0x0
```

### 2.3 Handler (149 insts, 借 R2-R7 + P0/P6; 每 warp 一份)

入口 → 自旋 → 命令 → 退出:
- **入口**: spill R4-R7 → P2R R2,PR → STG F_PR → 读基线(R6=F_RELEASE, R7=GO, **先于上报**) → 读 F_SITE → 算 f 存 F_F → **ELECT P6,URZ,PT**(stall 13 yield=1)。
- **hit 上报 (leader-only)**: 槽地址 = hslots + f*16；顺序写 va_lo/va_hi STG(req{4}) → @P6 BMOV R2,MACTIVE → mask STG → seq LDG R3 → +1 → **seq 最后写**。
- **自旋**: `NANOSLEEP 0x100` → 轮询 GO 字(烘焙地址) → GO 变则 `MOV R7,R2` 追平 → 查自己 F_RELEASE vs R6 → 变则 BRA dbgresume；否则查 cmdseq → 分派。
- **命令分派**: 保存 R6/R7 → F_RELBASE/F_GOBASE → 硬化 IVALL → CALL cmdbuf → cmdret 重载基线 → BRA 自旋。
- **dbgresume**: LDG F_RTGT → RET 位手术(self-构造 `RET.ABS.NODEC RZ, imm` 覆写本副本 retline) → 硬化 IVALL → R2P PR(stall 13 **yield=1**) → R2-R7 LDG 链(全 SB2, 一个 req{2} 覆盖) → `LDG.E.64 {R0,R1}` 自恢复 → MOV req{2} → RET → thunk。

### 2.4 Thunk / 重放 (host 构建)

```
<重放 inst 或 @P0 JMP 目标或 verbatim>   # 原指令(语义重放)
JMP <后继 VA>                            # build_thunk 自动附加
```
- BRA 站点 → 绝对 JMP 对(谓词保留); BSSY 原样(其 Sa 惰性)。
- 条件执行语义: 谓词在 thunk 里重估(断点 pre-predicate 触发)。

### 2.5 命令注入 (M7, M9 帧化)

- 命令契约: R2-R7 + P0-P6 空闲(内核值在帧里); **禁写 R0/R1**(帧指针); 仅直线; ≤56 insts。
- dump/set R0-R7/PR 走**帧**(内核视图); 其他寄存器直读/直写(实时)。
- `dump_regs` lane 视图: 结果窗口 = results + warp*0x400，reg-major ×32 lanes。
- exec 对 R2-R7 看到的是 **handler scratch**(与 dump/set 的帧视图不一致)——只用非 scratch 寄存器做 exec-then-dump(m6 测试用 R10)。

---

## 3. 反依赖纪律 (M9 最高优先级教训)

**LDG.E 发射后才采样地址寄存器** —— 紧随的 MOV32I 可能抢在采样前覆写 → 野地址 → 700。
depcheck **不检查**这类 anti-dep。同类: STG 晚读地址/数据寄存器; CALL/RET 寄存器目标。

**修复范式**: 内存操作 claim **读记分板** (rd 字段, 如 `[3:1:{}:8:0]`)，覆写者在 req 里等
(`[7:7:{1}:5:1]`)。补充规则:
1. 等一个指令的 wr barrier 也覆盖其源读(claim 完成 = 源已消费)。
2. 同 barrier 链式 re-claim，一个 req 覆盖所有 outstanding claim。
3. **记分板 claim 跨 CALL/RET 存活** —— handler 首条 P2R req{1} 等 stub 最后 STG 的 rd claim(R2/R3 交接)。
4. CBU 寄存器目标 (CALL/RET {Ra,Rb}) 也是晚读 —— 目标生产 MOV32I/IADD3 提到 stall 13 (+yield=1)。
5. 拿不准就加 rd+req —— 只费周期，不会死锁(claim per-warp 自清理)。

**调试工具限制**: compute-sanitizer 会把 patcher 的代码空间 STG 报 OOB 并杀 kernel(不能用);
cuda-gdb 因汇编器无 debug 信息而无用。用 **STG-marker 插桩**(帧内 scratch 槽)或 **EXIT 二分**
(子进程内插入 EXIT，700 消失 = 之前全干净)。

---

## 4. 关键硬件/汇编器事实 (踩坑沉淀)

| 事实 | 出处 |
|------|------|
| `WARPSYNC Rmask` 要求所有执行线程 ∈ Rmask，否则 715 | M8d probe E0b |
| `ELECT` 只从当前活跃集选 leader，**不等待收敛** | elect.md |
| ISETP/R2P stall 13 必须 yield=1 (`:13:0` 触发 opex 非法表) | M5/M9 |
| 64-bit 寄存器对必须**连续且偶对齐** `{R2,R3}` 非 `{R3,R4}` | 多处 |
| 代码取指 VA 需 16B 对齐 (cmdbuf 718) | Layout 注释 |
| 64-bit 帧槽需 8B 对齐 (716) | F_R01=0x20 |
| 指令槽重叠会静默拼接(handler 45→槽太小的"第二个 hit 不到"bug) | probe_stub 教训 5 |
| 挂起 kernel 时 **cuCtxSynchronize 会死等** → 用 stream_query/sync | M3 probe |
| 需挂起的 kernel 必须跑 NON_BLOCKING stream(默认流会死锁 host poll) | probe_stub 教训 1 |
| HMMA/QMMA 结果不 scoreboarded: 读 Rd 前 ≥16 NOP | AGENTS |
| S2R SR_CTAID.X 是慢记分板读: 消费必须 req-wait | AGENTS |

---

## 5. 当前进度与状态

### 5.1 已提交
- `d3eff08` — M9 引擎并入 patch.py + LDG.E 晚读反依赖修复 + m3–m9 测试迁移。
  **串行全量回归 133/134** (唯一失败 = 既有 test_uimad 自身 bug)。

### 5.2 工作树 (未提交, M10)
- `sassdbg/cubin.py` — cubin ELF 解析(.text.<func>、FUNC 符号、reloc 窗口检查)。
- `sassdbg/real.py` — `CubinDebugger(Debugger)`: 入口 trampoline + heap prologue + 烘焙 arena。
- `sassdbg/patch.py` — `_setup` 提取、`_site_va/_orig_word/_bp_by_va/_base_delta/_append_dbgctrl` 钩子、KPROL 区、`_real_prologue_src`/`_trampoline_src`。
- `sassdbg/stepper.py` — 可选 `dbg=` 参数(真实 cubin 复用 Cfg + 引擎)。
- `sassdbg/cli.py` — `--cubin` 默认走 CubinDebugger 路径(`--cubin --trace` 保留 M2 lift+inject 路径)。
- `tests/asm_construct/test_sassdbg_m10.py` — T0–T3 全过(3/3 稳定)。

### 5.3 测试矩阵
| 测试 | 覆盖 | 状态 |
|------|------|------|
| m9 | 零预留断点引擎 | ✓ |
| m3 / m3w / m3c | 断点 / 多 warp / 多 CTA | ✓ |
| m4 | warp 级 trace + 反向 | ✓ |
| m5 / m5w | 单步 / 多 warp 单步 | ✓ |
| m6 | CLI | ✓ |
| m7 | 命令注入 | ✓ |
| m8 | 发散组 + BAR/WARPSYNC 步进 | ✓ |
| m10 | 真实 cubin 挂载 | ✓ (T0–T3) |

### 5.4 已知限制 / 待办
- [ ] **predicated EXIT 单步**: `next_pcs` 对 predicated EXIT 返回 `[]`(当作 terminal resume 放行)。
      真实 kernel 的 `@P0 EXIT` 早退 + 尾部 BRA 循环普遍; 若谓词被取则组从 thunk EXIT, pending mask
      永不完成 → 需"EXIT 判定"(stream 完成 / lane 消失) 或改 next_pcs 为 [fall]+退出检测。
- [ ] **brx/jmx/call 单步**: next_pcs 对动态目标 raise(步过需后续)。
- [ ] **--trace --cubin** 仍是 M2 重汇编路径(不真正挂载 cubin)。
- [ ] `cubin.load_kernel` 拒绝入口窗口有 reloc 的 kernel —— 可考虑 trampoline 后移(LEPC 位移)以支持。
- [ ] 多 CTA 真实 cubin 未 E2E(m10 只测了单/双 warp)。
- [ ] M9 尚未跑多轮并发回归(串行 133/134 一次)。
- [ ] AGENTS.md M10 段未写(本文件是交接, AGENTS 待补)。

### 5.5 上手命令
```bash
# 真实 cubin 交互
printf 'r\nb 12\nc\ndump 0 R2\nc\nq\n' | \
  python3 -m sassdbg.cli --cubin tests/m2_smoke.cubin --block 32
# 测试
python3 tests/asm_construct/test_sassdbg_m10.py
python3 tools/run_tests.py -j 1     # 串行全量(基线 133/134)
```

---

## 6. M11 warp-private backend 更新（2026-08-31）

本节覆盖并更新上面的 M10 工作树描述；详细设计和验证记录见
`SASSDBG_WARP_PRIVATE_PLAN.md`。

- M11a/M11b/M11c/M11d 均已完成；M11c/M11d 在 RTX 5090 sm_120 上通过。
- 新后端入口：`sassdbg/private.py::PrivateKernel`，同时支持 source 与真实
  cubin。每个 global warp 执行独立的 mutable heap SASS copy。
- M11d API：`arm(..., warps=...)`、`disarm`、`wait_hit`、`resume_hit`。
  运行期 executable write 只能落在 arena 内；module text 不参与 patch。
- 默认 stop 为 tight freeze：handler 没有 NANOSLEEP/YIELD。提交顺序为
  words/metadata -> code epoch -> COMMIT；handler 单次 IVALL -> ACK；host
  收到 ACK 后才 RELEASE。
- persistent breakpoint 通过 per-warp thunk 重放，disarm 从 materialized
  immutable template 恢复；relaunch 会重建 canonical image 和 overlay。
- `test_sassdbg_m11d.py`：warp 隔离、运行中只 patch frozen warp、多 CTA
  独立断点、tight-loop re-hit、恢复、改变 block/grid 的 relaunch、真实
  cubin FFMA 均通过，专项连续 5 轮稳定。
- 当前边界：M11d 仅接受 full/zero lane mask；partial mask、cooperative
  execution-group 收集和 group stepper 迁移属于 M11e。
- 当前全量：136/138；所有 sassdbg 测试通过，两个失败仅因为系统 Python
  缺少可选 NumPy（`test_hadd2_hmul2`、`test_hfma2`）。
