# TCGEN05 TMEM `.exclusive` 分配（PTX ISA 9.4 / CUDA 13.4）与 ptxas 后端 bug

<!-- notes-status -->
**Status:** active  
**Evidence:** sm100+sm103-silicon  
**Tier confidence:** high  
**Last verified:** 2026-09-25  
**Probe:** `tests/tcgen05_alloc_exclusive.cu`  
**Open items:** 3  
**Audit:** `tools/notes_audit.py` · basis: B200 and B300 silicon measurements

## Conclusion

本文记录 `tcgen05.alloc.exclusive` / `tcgen05.dealloc.exclusive` 的编码、
lowering、以及 **CUDA 13.4 ptxas 的一个后端缺陷**：`.exclusive` 的
`nCols` 被完全忽略，硬件实际按整块 TMEM（512 列）分配。结论在 B200
(sm_100a) 与 B300 (sm_103a) 上均已实测。

相关：`utcatomsws.md`、`tcgen05_multiwarp_allocator_v2.md`、
`tmem_entry_fragment.md`、`instr/ldtm.md`、`instr/sttm.md`。

## 1. 限定符与语法

- 新增于 **PTX ISA 9.4**（CUDA 13.4）。CUDA 13.1 的 ptxas 报
  `Unknown modifier '.exclusive'`。
- CCCL 头文件
  `cuda/__ptx/instructions/generated/tcgen05_alloc.h`（`#if __cccl_ptx_isa >= 940`）：

```ptx
tcgen05.alloc.exclusive.cta_group::1.sync.aligned.shared::cta.b32 [dst], nCols;
tcgen05.alloc.exclusive.cta_group::2.sync.aligned.shared::cta.b32 [dst], nCols;
tcgen05.dealloc.exclusive.cta_group::1.sync.aligned.b32          taddr, nCols;
tcgen05.dealloc.exclusive.cta_group::2.sync.aligned.b32          taddr, nCols;
```

`.exclusive` 紧跟在 `alloc` / `dealloc` 之后，位于 `.cta_group` 之前。
支持 `SM_100a/f, SM_103a/f, SM_107a/f, SM_110a/f`。

### nCols 约束变化（前端，实测 ptxas 13.4）

| 指令 | 约束 | 非法 nCols 报错 |
|---|---|---|
| `tcgen05.alloc` | power of 2，[32,512] | `value must be power of 2` |
| `tcgen05.alloc.exclusive` | **32 的倍数**，[32,512] | `expected to be multiple of 32` |

例：96、160、224、320 仅 `.exclusive` 接受；33/40/48 两者都拒绝
（`unexpected value 'NN', expected to be multiple of 32`）。

## 2. Lowering：exclusive vs 普通路径

### 2.1 普通（power-of-2）路径（CUDA 13.4, `nCols=128`）

```sass
UMOV UR8, 0x4                 ; FIND_AND_SET 请求 = units = 128/32
IMAD.MOV.U32 R3, RZ, RZ, 0xf  ; range_mask = (1<<units)-1
IMAD.MOV.U32 R5, RZ, RZ, 0x1  ; head one-hot 基
DEPBAR.LE SB0, 0x36
UTCATOMSWS.FIND_AND_SET.ALIGN UP0, UR4, UR8   ; ← 带 .ALIGN
SHF.L.U32 R2, R3, R0, RZ      ; maskA(+0x14) = range_mask << idx
SHF.L.U32 R3, R5, R0, RZ      ; maskB(+0x18) = 1 << idx
SHF.L.U32 R0, R0, 0x5, RZ     ; taddr = idx*0x20
ATOMS.OR RZ, [UR6+0x14], R2
ATOMS.OR RZ, [UR6+0x18], R3
STS [UR7], R0                 ; 发布 tmem base 到 shared+0x400
```

分配阶段**不写 phase**（`partition+0x1c` 只在 relinquish 写 1）。

### 2.2 `.exclusive` 路径（CUDA 13.4）

```sass
MOV R0, 0x200                 ; = __tcgen05_tmem_max_col_size (512)，与 nCols 无关
SHF.R.S32.HI R0, RZ, 0x5, R0  ; R0 = 16 个 32-column unit
R2UR UR4, R0                  ; FIND_AND_SET 请求 = 16
S2UR UR8, SR_SWINHI
SHF.L.U32 R3, R3, R0, RZ      ; R3 = 0xffffffff << 16
DEPBAR.LE SB2, 0x36
UTCATOMSWS.FIND_AND_SET UP0, UR4, UR4   ; ← 无 .ALIGN
LOP3.LUT R3, RZ, R3, RZ, 0x33 ; R3 = ~(0xffffffff<<16) = 0xffff
IMAD.MOV.U32 R5, RZ, RZ, 0x1  ; head one-hot 基
SHF.L.U32 R3, R3, R2, RZ      ; maskA(+0x14) = 0xffff << idx
SHF.L.U32 R0, R5, R2, RZ      ; maskB(+0x18) = 1 << idx
IMAD.SHL.U32 R2, R2, 0x20, RZ ; taddr = idx*0x20
ATOMS.OR RZ, [UR5+0x14], R3
ATOMS.OR RZ, [UR5+0x18], R0
STS [UR7], R2                 ; 发布 base
ST.E.U8.STRONG.GPU [RZ.U32+UR4+0x1c], R5   ; phase = 2（R5=2）
```

所以 exclusive 相对普通路径的**真实语义差别**只有：

1. `FIND_AND_SET` **去掉 `.ALIGN`** —— 允许任意长度的连续 run（非 2 的幂）；
2. 分配阶段把 `partition+0x1c` 写为 **phase = 2**，用 `ST.E.U8.STRONG.GPU`
   写（配合 `SR_SWINHI`），普通路径用 `STS.U8` 写 1；
3. 其余（maskA=range、maskB=head、`taddr=idx*0x20`）完全同构。

### 2.3 ptxas 13.4 的 bug：`nCols` 未进入编码

`nCols ∈ {32,64,96,128,160,192,224,256,320,512}` 编译出的 cubin **逐字节
相同**（`md5=ce6d48bd…`，7112 B）；运行时寄存器形式的 `nCols` 也完全不被
SASS 引用。原因是后端固定使用常量符号：

```
.nv.shared.reserved.0 符号表：  __tcgen05_tmem_max_col_size = 0x200 (512), size 4
MOV R0, 0x200                  ; 该符号被直接立即数化
```

即 exclusive 恒请求 **16 unit（512 列）/ maskA = 0xffff**。`-g`
（`--g-tensor-memory-access-check`）不改变这一点。普通路径则没有这个符号，
range 由 `nCols` 折出。

**后果**：`tcgen05.alloc.exclusive ..., 96` 在硬件上吃掉整块 TMEM。

### 2.4 正确的 exclusive 编码（反推 + 实测验证）

让 `units = nCols/32`（nCols 为 32 的倍数时 units 可为任意 1..16）：

- FIND_AND_SET 请求 = `units`（不是 one-hot、不是 max）
- 无 `.ALIGN`
- `maskA(+0x14) = ((1<<units)-1) << idx`
- `maskB(+0x18) = 1 << idx`
- `phase(+0x1c) = 2`
- `taddr = idx*0x20`

最小验证方法：把 ptxas 产物里 **所有** `MOV R?, 0x200` 的立即数改成目标
`nCols`（例如 96=`0x60`）。这一步就同时驱动了 `>>5`（units）、请求值、
range_mask。多分配内核里有 **两处**：alloc 常量 + 每个 dealloc 的期望 mask
常量，必须一起改，否则 dealloc guard 不匹配 → CUDA 719。

> 注意 exclusive 的 dealloc 仍保持双 mask 校验 + 两次 `REDUX`（`+0x14`
> range、`+0x18` head），与 `utcatomsws.md` 记录的 V2 双 REDUX 一致。

## 3. 真机验证（B200 / B300）

测试入口：本地 nvcc 13.4 生成 cubin，`tools/modal_tcgen05_alloc.py
--hand-cubin … --function-name …` 在真机加载运行。B300 需 `-arch=sm_103a`
（`sm_100a` cubin 报 `CUDA error 209 NO_BINARY_FOR_GPU`）。

| # | 内核 | 说明 | B200 (sm_100a) | B300 (sm_103a) |
|---|---|---|---|---|
| A | `exclusive` 分配 96（nvcc 原样） | 单次分配 | `taddr=0`，正常退出 ✅ | `taddr=0` ✅ |
| B | `plain` 32 + `plain` 32 | 多次分配可行对照 | `taddr=0, 32` ✅ | — |
| C | `exclusive` 96 + `exclusive` 96（nvcc 原样） | 第二次 FIND_AND_SET | **30s 超时**（阻塞） ⛔ | **超时** ⛔ |
| D | 同 C，但把 `0x200` 改成 `0x60` | 修正为 3 unit | `taddr=0, 96` ✅ | `taddr=0, 96` ✅ |
| E | 单次 `exclusive` 96（patch 成 3 unit） | 修正单次 | `taddr=0` ✅ | — |

- C 的超时说明：第二次 96 列分配永远拿不到空间 ⇒ 第一次把 TMEM 全占了
  （nvcc 产物请求 16 unit）。
- D 说明：修正后每次只占 3 unit，两次分别落在 column 0 与 column 96，
  即 `.exclusive` 机制本身工作正常，问题只在 ptxas 没有使用 `nCols`。

## 4. 附带发现：不做分配直接用 TMEM 不报错

用裸 `tcgen05.st` / `tcgen05.ld`（完全没有 `tcgen05.alloc`）扫描：

| 访问（无任何 alloc） | B200 | B300 |
|---|---|---|
| `STTM` → column 0 / 300 / 511 | ✅ 成功 | ✅ 成功 |
| `STTM` → column 512 | ⛔ CUDA 700 | ⛔ CUDA 700 |
| `STTM` → 0xffff | ⛔ CUDA 700 | — |
| `LDTM` ← column 0 | ✅ 成功（读回 0） | — |

- **硬件只做物理范围检查**：TMEM 共 512 列，`column ∈ [0,512)` 一律允许，
  与是否分配无关；`≥512` 报 700。`__tcgen05_tmem_max_col_size = 0x200`
  正好对应这个物理上界。
- ptxas 的 `unallocated_columns_access` / `col_being_dealloced_not_returned_by_alloc`
  等属于**软件 guardrail**（依赖 reserved-shared 位图）。对“没有 alloc 的裸
  STTM”，即使 `-g` 也不插入任何 guardrail——SASS 里只有纯 `STTM`。
- 推论：`notes/sm100` 中关于“越出分配范围”的现象不能直接当硬件行为；用
  “越界访问是否 fault”判断分配大小是**无效**的（`plain 32` 之后写 column
  200 同样不报错）。分配大小只能靠“多次分配能否共存”判定。

## 5. 对仓库工具的影响

`assembler/sass_builtins.py::_expand_tmem_alloc_1cta` 已经按通用方式算掩码
（`units = columns//32; range_mask = (1<<units)-1`），只差入口断言
`columns ∈ {32,64,128,256,512}`。要支持（并修正）`.exclusive`：

1. 放宽 `columns` 为“32 的倍数”；
2. 去掉 `FIND_AND_SET` 的 `.ALIGN`；
3. 分配阶段写 `phase=2`（`ST.E.U8.STRONG.GPU` + `SR_SWINHI`），
   relinquish 仍写 1；
4. dealloc 保持双 mask 校验 + 双 `REDUX`。

这同时也是规避 CUDA 13.4 ptxas bug 的 workaround。

## 6. 复现

```console
# 静态
/usr/local/cuda-13.4/bin/nvcc -arch=sm_100a -O3 -cubin -o k.cubin k.cu
cuobjdump -arch sm_100a -sass k.cubin
# nCols 无关性
for n in 32 64 96 512; do
  sed "s/NCOLS/$n/" ref.cu > k$n.cu
  /usr/local/cuda-13.4/bin/nvcc -arch=sm_100a -O3 -cubin -o k$n.cubin k$n.cu
  md5sum k$n.cubin
done
# 真机
/home/cicuvc/miniconda3/envs/blkw/bin/modal run tools/modal_tcgen05_alloc.py \
  --hand-cubin k.cubin --function-name k --block-size 32
```

参考源码：`tests/tcgen05_alloc_exclusive.cu`。

## Open questions

- `ST.E.U8.STRONG.GPU` 写 `partition+0x1c` 时使用的 `SR_SWINHI` 具体地址语义
  （global-scope 写 shared window）未完全拆解；普通路径为何不需要它。
- `.exclusive` 的 phase=2 与 V1/V2 phase=1 的状态机含义（是否区分
  “exclusive 模式”）未确认。
- 该 bug 在 CUDA 13.4 之后的版本是否修复（本机无更高版本）。
