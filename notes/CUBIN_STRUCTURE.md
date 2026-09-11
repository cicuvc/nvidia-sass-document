# CUBIN ELF 格式规范(sm_90 / sm_120)

本文档是 NVIDIA CUDA cubin(单个已链接 kernel 的 ET_EXEC ELF)格式的完整说明,
面向已经熟悉 ELF 的读者:读完应能**逐字节构建一份可被驱动加载、被 CUDA 工具链
解析的合法 cubin**。

内容来源(均为本仓库实测,非官方文档):

- `assembler/sass_elf.py` — 手写 cubin 构建器(`CubinBuilder`),其产物在
  sm_120(RTX 5090)与 sm_90(H20)真机上通过 `cuModuleLoadData` 加载并执行,
  通过 `cuobjdump -elf` / `-sass` / `nvdisasm` 解析,通过 `ncu` profile。
- `assembler/minimal.cubin` — nvcc(sm_120, CUDA 12.8)产出的参考 cubin,
  note / `.debug_frame` 模板字节取自它。
- `tests/m2_smoke.cubin` — nvcc(sm_120, CUDA 13.1)参考 cubin。
- 大量针对驱动与 cuobjdump 的探针实验(失败模式见 §8)。
- `notes/sm90/arch/cubin_elf.md` — 侧重**重定位与常量 bank** 的姊妹篇
  (R_CUDA_* 重定位、`.nv.constant3/4`、`.nv.global`、 Mercury 节等 nvcc
  完整形态;本文聚焦单 kernel 全链接 cubin 的构建规范)。

-------------------------------------------------------------------------------

## 1. 总体布局

cubin 是 **64 位小端 ELF**(ELFCLASS64, ELFDATA2LSB),只使用 section,
不使用 segment:

```
+-----------------------+ 0x0000
| ELF header (64 字节)  |
+-----------------------+ 0x0040
| 各 section 数据        |  ← 按声明顺序排列,各自对齐到 sh_addralign
| (NOBITS 不占文件空间)  |
+-----------------------+
| section header table  |  ← 文件末尾,e_shoff 指向这里
+-----------------------+
```

约定(对 nvcc 与本仓库构建器均成立):

- **没有程序头**(e_phoff=0, e_phnum=0)。nvcc 会发 5 个 PHDR/LOAD,但实测
  全部删掉后驱动与 cuobjdump 均正常 —— 程序头是**可选**的。
- section header 表放在文件末尾;`e_shstrndx = 1`(`.shstrtab` 固定为 1 号节)。
- NOBITS 节的 sh_offset 取**当前文件偏移**(与下一个实数据节重叠),不占字节。
- 每个 kernel 拥有独立的一套 `.text.<fn>` / `.nv.info.<fn>` / `.nv.constant0.<fn>`。
  本仓库的构建器每 cubin 只装一个 kernel;nvcc 支持多 kernel(每 kernel 一套,
  外加共享的 `.nv.info` / `.nv.callgraph` 等)。

-------------------------------------------------------------------------------

## 2. ELF 头(64 字节)

| 偏移 | 字段 | 值 |
|------|------|----|
| 0x00 | e_ident[0:4] | `7F 45 4C 46` |
| 0x04 | EI_CLASS | 2 (ELFCLASS64) |
| 0x05 | EI_DATA | 1 (LSB) |
| 0x06 | EI_VERSION | 1 |
| 0x07 | EI_OSABI | **随架构**:sm_90 = 0x33,sm_120 = 0x41 |
| 0x08 | EI_ABIVERSION | **随架构**:sm_90 = 7,sm_120 = 8 |
| 0x09 | EI_PAD | 全 0 |
| 0x10 | e_type | 2 (ET_EXEC;可重定位 device 对象为 ET_REL=1) |
| 0x12 | e_machine | 190 (EM_CUDA,"NVIDIA CUDA architecture") |
| 0x14 | e_version | 1 |
| 0x18 | e_entry | 0(kernel 按符号进入,不用 ELF entry) |
| 0x20 | e_phoff | 0 |
| 0x28 | e_shoff | section header 表文件偏移 |
| 0x30 | e_flags | **随架构**,见下 |
| 0x34 | e_ehsize | 64 |
| 0x36 | e_phentsize | 0(无程序头) |
| 0x38 | e_phnum | 0 |
| 0x3a | e_shentsize | 64 |
| 0x3c | e_shnum | section 数 |
| 0x3e | e_shstrndx | 1 |

### 2.1 e_flags 与每架构常量

`e_flags` 编码 GPU 架构,**驱动会校验**——与设备不匹配直接
`CUDA_ERROR_NO_BINARY_FOR_GPU`(实测:H20 上加载带 sm_120 flags 的 cubin 即此错)。

实测值:

| 架构 | e_flags(本仓库构建器,驱动验证过) | nvcc 直出 cubin | EI_OSABI / ABIVER |
|------|------|------|------|
| sm_90 | `0x005a055a`(H20 验证) | `0x06005a04` | 0x33 / 7(nvcc 用 0x41 / 8) |
| sm_120 | `0x06007802`(= nvcc) | `0x06007802` | 0x41 / 8 |

两种布局都能被 cuobjdump 正确解码(`EF_CUDA_SMxx EF_CUDA_VIRTUAL_SM(...)`):

- **旧布局**(`0x005a055a`):byte0 = SM 版本(0x5a = 90),byte1 = 特性位
  0x05 = `EF_CUDA_TEXMODE_UNIFIED`(0x01) | `EF_CUDA_64BIT_ADDRESS`(0x04),
  byte2 = virtual SM 版本(0x5a)。这与更老架构的历史值(如 sm_70 ≈ `0x00460046`)
  模式一致。
- **新布局**(nvcc 12.8/13.1 直出,`0x06007802` / `0x06005a04`):SM 版本移到
  bits[15:8](0x78 = 120,0x5a = 90),byte3 = 0x06,byte0 为特性位
  (0x02 / 0x04;TEXMODE_UNIFIED/64BIT_ADDRESS 不再出现,已成默认)。
  bit 级语义未完全逆向,建议**直接照搬上表实测常量**。

其他每架构常量(`assembler/arch.py`):

| 架构 | 参数区基址 param_base | 默认全局缓存描述符槽位 | note/.nv.compat 节 |
|------|------|------|------|
| sm_90 | `c[0x0][0x210]` | `c[0x0][0x208]`(H800 验证) | **禁止**(带上会被 Hopper 驱动拒绝:NO_BINARY_FOR_GPU) |
| sm_120 | `c[0x0][0x380]` | `c[0x0][0x358]`(RTX 5090 验证) | **必须**(Blackwell 驱动期望) |

-------------------------------------------------------------------------------

## 3. Section 布局

单 kernel cubin 的标准形态(sm_120;sm_90 去掉注有 ★sm120 的三节,
其余顺移,**但 `.debug_frame` 必须仍是 4 号**):

| idx | 名称 | type | flags | link | info | align | entsize |
|-----|------|------|-------|------|------|-------|---------|
| 0 | (NULL) | 0 | 0 | 0 | 0 | 0/1 | 0 |
| 1 | `.shstrtab` | STRTAB(3) | 0 | 0 | 0 | 1 | 0 |
| 2 | `.strtab` | STRTAB(3) | 0 | 0 | 0 | 1 | 0 |
| 3 | `.symtab` | SYMTAB(2) | 0 | 2 | 见 §6 | 8 | 24 |
| 4 | **`.debug_frame`** | PROGBITS(1) | 0 | 0 | 0 | 1 | 0 |
| 5 | `.note.nv.tkinfo` ★sm120 | NOTE(7) | 0x02000000 | 0 | 0 | 4 | 0 |
| 6 | `.note.nv.cuver` ★sm120 | NOTE(7) | 0x01000040 | 5 | 9 | 4 | 0 |
| 7 | `.nv.info` | 0x70000000 | 0 | 3 | 0 | 4 | 0 |
| 8 | `.nv.info.<fn>` | 0x70000000 | 0x40 | 3 | text idx | 4 | 0 |
| 9 | `.nv.compat` ★sm120 | 0x70000086 | 0 | 0 | 0 | 4 | 0 |
| 10 | `.nv.callgraph` | 0x70000001 | 0 | 3 | 0 | 4 | 8 |
| 11 | `.text.<fn>` | PROGBITS(1) | 0x6 (A\|X) | 3 | func sym idx | **128** | 0 |
| 12 | `.nv.shared.reserved.0` | NOBITS(8) | 0x3 (W\|A) | 0 | 0 | 1 | 0 |
| 13 | `.nv.shared.<fn>`(可选) | NOBITS(8) | 0x43 | 0 | text idx | 4 | 0 |
| 14 | `.nv.constant0.<fn>` | PROGBITS(1) | 0x42 (A\|INFO_LINK) | 0 | text idx | 4 | 0 |

类型 0x70000000/0x70000001/0x70000086 为 CUDA 私有 SHT(cuobjdump 分别显示为
`CUDA_INFO` / `CUDA_CALLGRAPH` / `CUDA_COMPAT_INFO`)。

flags 位:0x1 WRITE,0x2 ALLOC,0x4 EXECINSTR,0x40 INFO_LINK;
CUDA 私有:0x01000000 RETAIN,0x02000000 LINK_ONCE。

### 3.1 硬性顺序约束(实测)

- **`.debug_frame` 必须恰好是 4 号 section**(`cuobjdump -elf` 的要求):
  缺失 → `cuobjdump fatal : Invalid ELF`;放在任何其他索引 → 同样报错。
  **内容完全不被解析**(4 字节全零 stub 也通过)。驱动、`cuobjdump -sass`、
  `nvdisasm` 均不在乎此节。nvcc 的所有 cubin(sm_90/sm_120  alike)都把
  `.debug_frame` 放在 `.symtab` 之后第一位,本构建器照搬。`.rela.debug_frame`
  **不需要**。
- `.shstrtab` = 1 号节且 `e_shstrndx = 1`(nvcc 与本构建器一致;未单独探针
  验证为硬性,建议保持)。
- 其余 section 顺序、符号表内部顺序、`.nv.info*` 内容、`.nv.compat` 内容均已
  探针验证为宽松(可自由替换为本构建器的版本仍通过 `cuobjdump -elf`)。

-------------------------------------------------------------------------------

## 4. 各 section 详述

### 4.1 `.shstrtab` / `.strtab`

标准 ELF 字符串表:`\0` 开头,每个名字以 NUL 结尾,去重存储。
`.shstrtab` 存所有 section 名;`.strtab` 存所有符号名。
构建器把 `.shstrtab` 数据放在 0x40(紧跟 ELF 头)。

### 4.2 `.symtab`

见 §6(符号表规范)。

### 4.3 `.debug_frame`

DWARF CFI(CIE + 每函数 FDE)。**只要求存在于 4 号索引**,内容不被任何工具
校验。本构建器从 `assembler/minimal.cubin` 按名提取真实模板(0x68 字节,
见附录 A.4)原样发出;多 kernel cubin 也只需一份。

### 4.4 `.note.nv.tkinfo` / `.note.nv.cuver`(仅 sm_120)

标准 ELF NOTE 记录:`{namesz:u32, descsz:u32, type:u32}` + name(4 字节对齐)
+ desc(4 字节对齐)。两节的 name 均为 `"NVIDIA Corp."`(namesz=12)。

**`.note.nv.tkinfo`**(type = 0x7d0,descsz = 0x8c)desc 布局(已从
minimal.cubin 模板完整解码):

```
u64 flags = 0x80
u32 name_off    = 1      ┐
u32 version_off = 7      │ 字符串区内偏移
u32 build_off   = 0x36   │ (字符串区从 desc+24 开始)
u32 cmdline_off = 0x60   ┘
--- 字符串区(NUL 分隔,无对齐填充)---
""  "ptxas"  "Cuda compilation tools, release 12.8, V12.8.93"
"Build cuda_12.8.r12.8/compiler.35583870_0"  "-arch sm_120 -m 64 "
```

**`.note.nv.cuver`**(type = 0x3e8,descsz = 0x0c)desc = 3 个 u32:
`{0x00780001, 1, 1}`(sm_120 模板;0x78 = 120 为 SM 版本)。
其 sh_link = `.note.nv.tkinfo` 索引,sh_info = `.nv.compat` 索引;
flags = INFO_LINK | CUDA_RETAIN(0x01000040)。
(nvcc 13.1 起此节改名 `.note.nv.cuinfo`,两种名字 cuobjdump 都接受。)

这两节是 **toolkit 版本来源**:cuobjdump -elf 首行的 `toolkit=12.8` 即读自
tkinfo。sm_90 cubin 不带 note 节,cuobjdump 显示 `toolkit=1`(无害)。

### 4.5 `.nv.info` / `.nv.info.<fn>`(EIATTR 容器)

内容为 **EIATTR 记录序列**(编码见 §5)。

- `.nv.info`(设备级):对本模块**每个函数**各发一组
  REGCOUNT / FRAME_SIZE / MIN_STACK_SIZE / MAX_STACK_SIZE
  (payload 首 u32 = 函数符号索引)。
- `.nv.info.<fn>`(per-kernel):参数、cbank、EXIT 偏移等,见 §5.2 表。
  sh_flags 带 INFO_LINK,sh_info 指向对应 `.text.<fn>` 节索引。

### 4.6 `.nv.compat`(仅 sm_120)

EICOMPAT 记录(与 EIATTR 相同的 fmt 编码)。本构建器发出的 16 字节模板
(CUDA 12.8 形式):

```
02 02 01 00    BVAL type=0x02 ISA_CLASS = 1
02 05 05 00    BVAL type=0x05 TCGEN05_MMA = 5
02 03 00 00    BVAL type=0x03 INST_TENSORMAP_V1 = 0
02 06 01 00    BVAL type=0x06 OPPORTUNISTIC_FINALIZATION(CAN_FASTPATH_FINALIZE)= 1
```

nvcc 13.1 产物的 `.nv.compat` 为 28 字节,另含 `BVAL 0x09=0`、
`HVAL 0x07=0x0101`(MERCURY_ISA_MAJOR_MINOR 1.1)、`SVAL 0x0b`(8 字节,
CUDA_ACCELERATOR_TARGET)。驱动对两者均接受。

### 4.7 `.nv.callgraph`

CUDA_CALLGRAPH 节,entsize=8,内容为 `(caller:u32, callee:u32)` 记录,
索引相对 sh_link 指向的符号表。叶子 kernel 的固定模板(32 字节):

```
{0, -1} {0, -2} {0, -3} {0, -4}
```

负值 callee 是哨兵(-1..-4 分别标记 leaf / 间接调用 / 外部 / no-return),
驱动用它界定 CRS(调用-返回)栈尺寸。有设备函数调用时 nvcc 发真实边
(见 `notes/sm90/arch/cubin_elf.md` §Symbols & callgraph)。

### 4.8 `.text.<fn>`

SASS 机器码:**每条指令 16 字节(128 位)**,小端存放 lo64 后 hi64;
opcode 为 13 位 `{bit[91], bits[11:0]}`(详见 `sm_90_instructions.txt` 与
`tools/query_sm90.py`)。

- sh_addralign = **128**(对齐到 128 字节)。
- sh_link = symtab 索引,sh_info = **函数符号索引**。
- 构建器把代码填充到 **≥256 字节**,填充物为 NOP 指令
  (lo64 = `0x0000000000007918`,hi64 = `0x000fc00000000000`),与 nvcc 一致。

### 4.9 `.nv.shared.reserved.0` / `.nv.shared.<fn>`

- `.nv.shared.reserved.0`:NOBITS,固定 0x40 字节,W|A —— 驱动保留的静态
  shared 槽(`__nv_reservedSMEM_offset_0_alias` 符号指向其 0x40 偏移处)。
  **必须存在**。
- `.nv.shared.<fn>`:仅当 kernel 用静态 shared 内存(LDS/STS 窗口)时存在;
  NOBITS,size = **shared 字节数 + 0x400**(0x400 是 CTA shared 基址窗口,
  可用 = size − 0x400),flags = W|A|INFO_LINK(0x43),
  **sh_info = `.text.<fn>` 节索引**——这是把 shared 分配挂到 kernel 的链接。

### 4.10 `.nv.constant0.<fn>`

kernel 的 **常量 bank 0 镜像**(`c[0x0]`),PROGBITS,flags = ALLOC|INFO_LINK
(0x42),sh_info = `.text.<fn>` 节索引,内容**全零**,size =
`param_base + 参数区总字节数`。

运行时由驱动覆盖:

- `[0, param_base)` — 驱动预置区(含默认全局缓存描述符槽:
  sm_90 `c[0x0][0x208]`,sm_120 `c[0x0][0x358]`;完整 bank-0 布局见
  `notes/sm90/instr/ldc.md`)。
- `[param_base, param_base + total)` — kernel 参数,驱动在 launch 时把
  参数缓冲拷贝到这里。**参数偏移按声明序分配,对齐 = clamp(size, 4, 8)**;
  总尺寸 = `max(offset + size)`(注意:4 字节参数后接 8 字节参数会有对齐
  间隙,总尺寸**不能简单求和**,否则驱动拒绝启动,error 701)。

每个参数同时需要一条 `EIATTR_KPARAM_INFO`(§5.2)向驱动声明
ordinal / 偏移 / 尺寸。

-------------------------------------------------------------------------------

## 5. EIATTR / EICOMPAT 记录编码

`.nv.info*` 与 `.nv.compat` 的内容是同一种 TLV 记录流:

```
字节 0   : fmt  (EIFMT)
字节 1   : type (EIATTR_* / EICOMPAT_* 编号)
字节 2-3 : fmt=4 → payload 字节数;fmt=3 → 值本体(u16);fmt=2 → 值在字节 2
字节 4.. : payload(fmt=4 才有)
```

| fmt | 名称 | 含义 | 记录总长 |
|-----|------|------|----------|
| 1 | NVAL | 空标记(无值) | 4 |
| 2 | BVAL | 1 字节值(在字节 2) | 4 |
| 3 | HVAL | 2 字节值(在字节 2-3) | 4 |
| 4 | SVAL | payload 长度在字节 2-3,payload 紧随其后 | 4 + size |

记录紧密排列,无对齐填充,解析到节末尾为止。

### 5.1 `.nv.info`(设备级)属性

| type | 名称 | fmt | payload |
|------|------|-----|---------|
| 0x2f | REGCOUNT | SVAL(8) | `{func_sym:u32, regcount:u32}` |
| 0x49 | SHADER_TYPE | SVAL(8) | `{func_sym:u32, shader_type:u32}`,可选,计算 kernel 省略(默认 CS);值 0=UNKNOWN,1=VSA,4=CS,5=PS,… |
| 0x11 | FRAME_SIZE | SVAL(8) | `{func_sym:u32, bytes:u32}` |
| 0x12 | MIN_STACK_SIZE | SVAL(8) | 同上 |
| 0x23 | MAX_STACK_SIZE | SVAL(8) | 同上 |

**REGCOUNT 必须 ≥ kernel 实际用到的寄存器数**:低估会在启动时报
OUT_OF_RESOURCES,或运行时 `CUDA_ERROR_ILLEGAL_INSTRUCTION`(715)。
本构建器从指令位流扫描最大寄存器号,再按 `max(8, ceil8(max_reg+1) 含 +2
余量)` 圆整(每 8 寄存器分配窗的顶部 2 个被硬件保留;带 32 位立即数的
opcode —— MOV32I/MOV/MOV.64/UMOV/ISETP-imm/USETMAXREG —— 的 [63:32]
不当作寄存器扫描)。`#pragma MAXREG_COUNT(n)` 可显式覆盖。

### 5.2 `.nv.info.<fn>`(per-kernel)属性

按本构建器的发射顺序(nvcc 顺序略有不同,驱动不校验顺序):

| type | 名称 | fmt | 值 / payload | 发射条件 |
|------|------|-----|--------------|----------|
| 0x37 | CUDA_API_VERSION | SVAL(4) | `0x80`(12.8 模板;nvcc 13.1 用 `0x83`) | 总是 |
| 0x17 | KPARAM_INFO | SVAL(12) | 见下 | 每参数一条,声明序 |
| 0x50 | SPARSE_MMA_MASK | HVAL | 0 | 总是 |
| 0x1b | MAXREG_COUNT | HVAL | 默认 0xff | 总是 |
| 0x54 | REG_RECONFIG | NVAL | — | kernel 含 USETMAXREG(PTX setmaxnreg)时 |
| 0x4a | VRC_CTA_INIT_COUNT | BVAL | 0 | 总是 |
| 0x1c | EXIT_INSTR_OFFSETS | SVAL(4n) | 每个 EXIT 的**字节**偏移(u32 数组) | 总是(EXIT 全部列出) |
| 0x4c | NUM_BARRIERS | BVAL | 最大命名 barrier 号 + 1 | 用到 BAR.SYNC 时 |
| 0x39 | MBARRIER_INSTR_OFFSETS | SVAL(16n) | 见下 | 用到 mbarrier 类 SYNCS 时 |
| 0x38 | NUM_MBARRIERS | HVAL | 数量;静态不可判定 = **0xffff** | 随 0x39 |
| 0x3d | CTA_PER_CLUSTER | SVAL(12) | `{x,y,z}` 3×u32 | cluster 启动 |
| 0x3e | EXPLICIT_CLUSTER | NVAL | — | 随 0x3d |
| 0x19 | CBANK_PARAM_SIZE | HVAL | 参数区总字节数 | 总是 |
| 0x0a | PARAM_CBANK | SVAL(8) | `{constant0符号索引:u32, (参数总尺寸<<16)\|param_base:u32}` | 总是 |
| 0x36 | SW_WAR | SVAL(4) | 0 | 总是 |

nvcc 还会发(本构建器未实现,详见 `notes/sm90/arch/cubin_elf.md`):
EIATTR_EXTERNS、SYSCALL_OFFSETS(外部调用点)、CRS_STACK_SIZE、
MERCURY_ISA_VERSION;13.1 另见 `HVAL 0x5f = 0x0101`(含义未逆向)。

**KPARAM_INFO(0x17)payload(12 字节)**:

```
u32[0] = 0
u32[1] = (参数在 cbank 参数区的字节偏移 << 16) | ordinal
u32[2] = flags = (((size << 2) | 1) << 16) | 0xf000
```

尺寸码 = `(size << 2) | 1`:4 → 0x11,8 → 0x21,16 → 0x41,128 → 0x201,
256 → 0x401(`__grid_constant__` CUtensorMap)。低 16 位固定 0xf000。

**MBARRIER_INSTR_OFFSETS(0x39)每条 16 字节**:
`{指令字节偏移:u32, 0xff:u32, 0:u32, kind_flags:u32}`。
kind_flags 低 16 位是种类,byte2 = mbarrier 地址寄存器(UR 号):

| kind_flags(低 16 位) | 指令 |
|------|------|
| 0x0100 | SYNCS.EXCH(mbarrier.init;地址寄存器取自 Sa 位域) |
| 0x0101 | SYNCS.ARRIVE.A1T0(mbarrier.arrive) |
| 0x0103 | SYNCS.ARRIVE.OPTOUT.A1T0(mbarrier.arrive_drop) |
| 0x0106 | SYNCS.PHASECHK(mbarrier.test_wait) |
| 0x0108 | SYNCS.CCTL.IV(mbarrier.inval) |
| 0x010a | SYNCS.PHASECHK.TRYWAIT(mbarrier.try_wait) |
| 0x010b | SYNCS.ARRIVE.A0TR(mbarrier.expect_tx) |
| 0x010c | SYNCS.ARRIVE.A0TX(mbarrier.complete_tx) |
| 0x0102(+0xff0000) | SYNCS.ARRIVE TMASK.ART0 |

(A1TR / arrive.expect_tx 不进表,nvcc 同样省略。)

-------------------------------------------------------------------------------

## 6. 符号表规范

ELF64 符号表项 24 字节:`{name:u32, info:u8, other:u8, shndx:u16, value:u64,
size:u64}`,info = `(bind << 4) | type`。

本构建器的符号清单(单 kernel、带静态 shared 的完整形态;驱动 + cuobjdump +
ncu 均验证):

| idx | 名字 | bind/type | other | shndx | value | size |
|-----|------|-----------|-------|-------|-------|------|
| 0 | (NULL) | LOCAL/NOTYPE | 0 | 0 | 0 | 0 |
| 1 | `.text.<fn>` | LOCAL/SECTION | 0 | .text 节 | 0 | 0 |
| 2 | `.nv.shared.<fn>`(可选) | LOCAL/SECTION | 0 | shared 节 | 0 | 0 |
| 3 | `.nv.reservedSmem.offset0` | LOCAL/OBJECT | HIDDEN(2) | reserved.0 节 | 0x40 | 4 |
| 4 | `__nv_reservedSMEM_offset_0_alias` | GLOBAL/NOTYPE | 0 | reserved.0 节 | 0x40 | 0 |
| 5 | `.nv.callgraph` | LOCAL/SECTION | 0 | callgraph 节 | 0 | 0 |
| 6 | `<fn>`(mangled) | GLOBAL/FUNC | **0x10** | .text 节 | 0 | .text 字节数 |
| 7 | `.nv.constant0.<fn>` | LOCAL/SECTION | 0 | constant0 节 | 0 | 0 |

要点:

- **st_other bit 4(0x10)= STO_ENTRY**:把 FUNC 符号标记为 kernel 入口。
  缺了它 cubin 照常加载运行,但 **ncu 的 counter replay 启动会
  LaunchFailed**(实测:凡带 0x10 的值都通过,不带都失败;regcount/size
  无关)。
- symtab 的 **sh_info**(首个 non-local 符号索引):本构建器设为 FUNC 符号
  索引;nvcc 直接设为**符号总数**(使规则形同虚设)。两种 cuobjdump 与驱动
  都接受。注意本构建器的顺序里 GLOBAL(alias)先于 LOCAL(callgraph),
  严格按 ELF 规范属违规排列 —— readelf 会告警,但实际消费方均容忍。
- nvcc 另为 note / `.debug_frame` 发 LOCAL/SECTION 符号,并把
  `.nv.reservedSmem.offset0` 发成 WEAK/OBJECT/UND、alias 发成
  WEAK/NOTYPE other=0xa0 —— 均非必需。
- mangling:构建器直接按 Itanium 规则拼 `_Z<len><name>`(仅支持简单名)。

-------------------------------------------------------------------------------

## 7. 加载器硬性要求与实测失败模式

| 违反项 | 后果 |
|--------|------|
| e_flags / EI_OSABI 与设备架构不符 | `CUDA_ERROR_NO_BINARY_FOR_GPU`(实测 H20) |
| sm_90 cubin 携带 sm_120 的 note 模板节 | Hopper 驱动拒绝(NO_BINARY_FOR_GPU) |
| sm_120 cubin 缺 note / `.nv.compat` 节 | Blackwell 驱动拒绝(故两节仅 sm_120 发) |
| REGCOUNT 低估实际寄存器用量 | 启动 OUT_OF_RESOURCES 或运行 715 ILLEGAL_INSTRUCTION |
| 参数总尺寸未按 `max(off+size)` 计(漏对齐间隙) | 启动 error 701 |
| 缺 STO_ENTRY(0x10) | 正常运行,但 ncu replay LaunchFailed |
| `.debug_frame` 缺失或不在 4 号 | **仅** `cuobjdump -elf`:`Invalid ELF` |
| KPARAM 尺寸码与实际参数不符 | launch 时参数打包错位(宿主侧 runner 依赖 KPARAM) |

工具兼容性(对本构建器产物实测):

| 消费者 | 要求 |
|--------|------|
| CUDA 驱动(cuModuleLoadData/launch) | §7 全部驱动项 |
| `cuobjdump -sass` / `nvdisasm` | 无额外要求(缺 `.debug_frame` 也正常) |
| `cuobjdump -elf` | **`.debug_frame` 必须为 4 号 section**(内容不校验) |
| `ncu` | 函数符号带 STO_ENTRY(0x10) |
| readelf | 完全宽松(symtab 排列告警无碍) |

-------------------------------------------------------------------------------

## 8. nvcc 完整 cubin 中的其余 section(参考)

本构建器产物是全链接单 kernel cubin;nvcc 真实产物还可能有(细节见
`notes/sm90/arch/cubin_elf.md`):

| section | 用途 |
|---------|------|
| `.nv.constant3` | 用户 `__constant__` 数据(bank 3) |
| `.nv.constant4` | 全局变量/外部函数/字符串的 64 位**地址表**(bank 4) |
| `.nv.global[.init]` | `__device__` 变量(BSS / 初始化数据) |
| `.rela.*` | R_CUDA_* 重定位(本构建器产物无重定位,全解析) |
| `.nv.merc.*` / `.nv.capmerc.*` | Mercury capsule(sm_100+,CUDA 13) |
| 程序头(PHDR/LOAD×5) | 可选,实测可全部省略 |

-------------------------------------------------------------------------------

## 9. 最小合法 cubin 构建清单

1. **ELF 头**(§2):ET_EXEC / EM_CUDA=190 / shstrndx=1 / 无程序头;
   EI_OSABI、EI_ABIVERSION、e_flags 按目标架构取 §2.1 表值。
2. **Section 序列**(§3),确保 `.debug_frame` 落在 **4 号索引**;
   sm_120 加 tkinfo/cuver/compat 三节,sm_90 不加。
3. **`.text.<fn>`**:128 对齐,≥256 字节,NOP 填充;link=symtab,
   info=FUNC 符号索引。
4. **符号表**(§6):7~8 个符号,FUNC 符号 st_other |= 0x10。
5. **`.nv.info`**:REGCOUNT(≥ 实际用量,§5.1)+ FRAME/MIN/MAX_STACK。
6. **`.nv.info.<fn>`**(§5.2):API_VERSION、KPARAM×n、SPARSE_MMA_MASK、
   MAXREG_COUNT=0xff、VRC_CTA_INIT_COUNT、EXIT_INSTR_OFFSETS、
   CBANK_PARAM_SIZE、PARAM_CBANK、SW_WAR;按需加 NUM_BARRIERS /
   MBARRIER_* / cluster 三元组。
7. **`.nv.callgraph`**:叶子模板 `{0,-1},{0,-2},{0,-3},{0,-4}`(entsize=8)。
8. **`.nv.shared.reserved.0`**:NOBITS 0x40;用静态 shared 再加
   `.nv.shared.<fn>`(size = 用量 + 0x400,info = text 节)。
9. **`.nv.constant0.<fn>`**:全零,size = param_base + 参数区总尺寸
   (`max(off+size)`,参数对齐 clamp(size,4,8))。
10. **文件布局**:section 数据按序对齐摆放,NOBITS 只占头不占数据,
    section header 表压文件尾。

参考实现:`assembler/sass_elf.py`(`CubinBuilder.build()`),其产物逐条满足
上表并通过 §7 的全部检查。

-------------------------------------------------------------------------------

## 附录 A. 参考字节序列

### A.1 `.nv.compat`(16 字节,sm_120 / 12.8 模板)

```
02 02 01 00  02 05 05 00  02 03 00 00  02 06 01 00
```

### A.2 `.nv.callgraph`(32 字节,叶子 kernel)

```
00000000 ffffffff 00000000 feffffff 00000000 fdffffff 00000000 fcffffff
```

### A.3 `.note.nv.cuver`(完整 NOTE 记录,36 字节)

```
0c000000 0c000000 e8030000 "NVIDIA Corp.\0" 01007800 01000000 01000000
```

### A.4 `.debug_frame` 模板(0x68 字节,取自 minimal.cubin)

```
ffffffff 24000000 00000000 ffffffff ffffffff 0300047c ffffffff 0f0c8180
80280008 ff818028 08818080 28000000 ffffffff 2c000000 00000000 00000000
00000000 00000000 00000000 01000000 00000000 04040000 00040400 000c8180
80280000 00000000
```

### A.5 `.note.nv.tkinfo`(0xa4 字节)

结构见 §4.4;字节流固定从 `assembler/minimal.cubin` 按节名提取
(`assembler/sass_elf.py:_minimal_section`),包含 ptxas 版本串、build 串与
原始编译命令行。

### A.6 NOP 指令(128 位填充)

```
lo64 = 0x0000000000007918
hi64 = 0x000fc00000000000
```
