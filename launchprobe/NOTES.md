# launchprobe — CUDA kernel launch ↔ GPU 通信逆向笔记

平台：RTX 5090 (GB202, sm_120)，驱动 580.65.06（open kernel modules, GSP-RM），CUDA 13.0。
工具：`libnvtrace.so`（LD_PRELOAD 拦截 open/ioctl/mmap + mprotect/SIGSEGV MMIO 写陷阱 + TF 单步模拟）。

## 结论先行：一次 kernel launch 的用户态可见通信（实测）

以 `vecadd<<<4096,256>>>` 为例，**每次 launch 恰好 4 次写**，无 ioctl：

| 序 | 目标 | 偏移 | 值 | 含义 |
|---|---|---|---|---|
| 1 | GPFIFO 环（reg3, GPU fd 2MB 映射） | +0x500, +0x504（每 launch 推进 8B） | `0x00633c94`, `0x00073a02` | 8 字节 GPFIFO entry（NVC06F_GP_ENTRY 格式） |
| 2 | userd 页（同一映射内） | +0x208c | `0x000000a1`（每次 +1） | **GPPut** = userdOffset(0x2000) + Nvc96fControl.GPPut(0x8c) |
| 3 | BAR doorbell 页（reg2, GPU fd 64KB PROT_WRITE-only 映射） | +0x90 | `0x40000004`（run 内恒定） | doorbell "kick"，token 值 |

方法字节流（QMD 等，本例每段 1848B）**不经过任何 nvidia fd 映射**——写在普通系统内存里（UVM 统一寻址后 GPU 可 DMA 读取）。GPFIFO entry 的地址字段指向这些段。

### GPFIFO entry 解码实例（launch 1）

- lo=`0x00633c94` → GET[31:2]；hi=`0x00073a02` → GET_HI[7:0]=0x02，LENGTH[30:10]=0x1ce=462 dword=1848B
- 段地址 = {GET_HI, GET} = GPU VA `0x200633c94`，长度 1848B
- 后续 launch 段地址递增恰好 0x738=1848B（libcuda 定长段分配）

## 关键映射识别（vecadd 一次运行的 29 个 mmap）

| 映射 | fd | 大小/prot | 用途（实测/推断） |
|---|---|---|---|
| 0x200400000 | nvidia-gpu | 2MB RW | **GPFIFO 环 + userd**：gpFifoOffset=0x200400000（channel alloc 参数），userd 在 +0x2000 |
| 0x200600000 | nvidiactl | 48MB RW | pushbuffer 段的 GPU-VA 镜像（CPU 可读写，但 launch 时无写流量——写入走系统内存别名） |
| 0x7fb6024eb000 | nvidia-gpu | 64KB **W-only** | **BAR doorbell 页**：launch 时唯一被写的 BAR 页，固定偏移 +0x90 |
| 0x7fb5f8928000.. ×15 | nvidiactl | 4KB RW | 各 channel userd/notify 页（setup 时被 movups 清零，launch 时无流量） |
| 0x7fb3efa00000 等 | nvidiactl | 2MB/6MB RW | 其他堆（拷贝/同步原语等，未深究） |

## ioctl 层（450 个事件/vecadd 运行）

- libcuda 用 `open64`/`mmap64`（**必须 hook 64 变体**，否则丢 90% 事件）
- 每个分配一个 fd：26 次 open /dev/nvidiactl，mmap offset 全为 0（现代驱动用 per-fd 绑定）
- RM 号验证：0x2b=RM_ALLOC（结构 48B：{hClient,hParent,hObject,hClass,u64 params,u32 status,...}，hexdump 实测确认）；0x2a=RM_CONTROL；0x4e=RM_MAP_MEMORY；0x29=RM_FREE；0x5d/0x27 出现少量
- 0xd7（560B 结构，GPU fd 上）未识别——本地头文件无定义
- 未见 NV_ESC_IOCTL_XFER_CMD 用于常规路径

### channel 建立（RM_ALLOC hClass=0xC96F BLACKWELL_CHANNEL_GPFIFO_A，16 次）

params（NV_CHANNEL_ALLOC_PARAMS，sdk `alloc_channel.h`）实测解码：
- gpFifoOffset=0x200400000，gpFifoEntries=1024
- hUserdMem=0x5c00001a，userdOffset=0x2000 ← 与 userd GPPut 实测位置 (reg3+0x208c) 精确吻合
- engineType=0（compute），cid 每次不同

class 分布：0xc96f×16（channel）、0xcab5×12（BLACKWELL_DMA_COPY_B）、0xcb33×1（疑 BLACKWELL_COMPUTE_A）、0xcec0×8、0x40/0x3e（NV01 内存类）。

## doorbell token 语义（已解，run9 实测）

BAR doorbell 页 +0x90 是**广播 doorbell 寄存器**（所有 channel 写同一地址），
写入值标识要 kick 的 channel：

```
doorbell_value = 0x40000000 | (runlist_id << 16) | chid
```

- bit 30（0x40000000）恒置位，flag
- [31:16] = runlist id；[15:0] = 该 runlist 内的 HW channel id（chid，RM 分配，run 间变化）

实测对照（16 个 channel，userd 偏移 0x2000+i×0x3000，每次 doorbell 前最后一次 GPPut 写的 userd 偏移反查 channel）：

| channel | userdOff | token | 解读 |
|---|---|---|---|
| 0 | 0x2000 | 0x40000004 | runlist 0, chid 4（compute，launch 全走它，×173） |
| 1–7 | … | 0x40000005–0x4000000b | runlist 0, chid 5–11 |
| 8 | 0x1a000 | 0x400d0006 | runlist 13, chid 6（cudaMemcpy 主用 CE channel，×103） |
| 9–11 | … | 0x400d0007–9 | runlist 13, chid 7–9 |
| 12–15 | … | 0x400e0003–6 | runlist 14, chid 3–6 |

- chid 不从 0 开始（系统里其他进程/上下文占用 id）；run5 中 compute channel 是 chid 12（token `0x4000000c`），run7/run9 是 chid 4——同一 channel 类型每次落在 runlist 0
- "低 16 位递增/回退"的旧观察实际是**不同 chid 的 CE channel 轮用**（channel pool），非计数器
- 工作量的传递全靠 userd GPPut；doorbell 值不含 put，纯粹是"哪个 channel 有新活"的通知

## Open questions

1. ~~doorbell 值语义~~ → 已解（见上）。
2. 0xd7 ioctl（560B）与 0xcb33 class（=NV_CONFIDENTIAL_COMPUTE，为何出现在普通 vecadd？）未完全识别。
3. 2080 Ti (Turing) 对照实验未做（预期 Put@0x40、doorbell 布局不同——clc06f.h）。
4. kernel params 的实际写入路径未直接抓到（推测写到 host pinned 参数缓冲，如 `0x7f50ff768000`，属普通内存写、不在 nvidia fd 映射内）。
5. 16 个 channel 的角色分配（1 compute + 15 个 CE/内部 channel）未逐一标定；engineType 全为 0（可能 decode 偏移或 RM 实际行为）。

---

# Phase 4 — pushbuffer 方法流与 QMD（Blackwell, 实测）

工具升级：doorbell 写完成的瞬间（SIGTRAP 单步结束后），tracer 读 userd GPPut，
回溯 dump 新 GPFIFO entry 指向的方法段到 sidecar 文件（`nvtrace-seg-*.bin`）。
GPU-VA 与 CPU-VA 同值（UVM 统一映射），进程内直接读。

## 方法头格式（经 1848B 段完美平铺验证）

```
dword hdr: [12:0]=method/4  [15:13]=subchannel  [28:16]=count  [31:29]=mode (1=INC, 3=NONINC)
```

## 一次 launch 的方法段（vecadd<<<4096,256>>>，1848B，subch 全为 1）

| 方法 | 名字（NVC1C0，Hopper 命名在 Blackwell CEC0 上验证有效） | 内容 |
|---|---|---|
| 0x188/0x18c | SET_OFFSET_OUT_UPPER/OUT | 64-bit 目标地址（host pinned `0x7f50_xxxxxxxx`） |
| 0x180/0x184 | SET_LINE_LENGTH_IN / LINE_COUNT | 896B × 1 |
| 0x1b0 | LAUNCH_DMA = 0x41 | 触发 DMA：把下面的 inline data 搬到 OFFSET_OUT |
| 0x1b4 | LOAD_INLINE_DATA ×224 (NONINC) | **896B staging 块**（QMD 模板 + 常量数据；含 host VA 对） |
| （同上 4 方法）×2 | | 第二个小 DMA：28B（3 个 64-bit host 指针 + 4B） |
| 0x318/0x31c | **SET_INLINE_QMD_ADDRESS_A/B** | QMD GPU VA >> 8；A 的 bit30=0x40000000 是 flag（launch trigger） |
| 0x320..0x3a8 | **LOAD_INLINE_QMD_DATA(0..95)** | **384B QMD 内联上传 → 触发 grid launch** |
| （重复一次）| | 第二个 QMD：spacer/terminator（见下） |
| 0x188..0x1b4 | 小 DMA ×4B | 值 5 → `0x2_07237f3c`（semaphore payload 写） |
| 0x1b00..0x1b0c | SET_REPORT_SEMAPHORE_A..D | addr=`0x2_0720fff0`，C=0xa0，D=4（完成报告信号量） |

即每次 launch 实际包含 **两个 QMD 上传**：第一个是"真" kernel QMD（字段密集），
第二个是稀疏的 spacer QMD（仅 +0x10=0x00800002、+0x28=0x00230000、+0x88/0x8c 有值）。
真 QMD 的 +0x30 链接字 = spacer 的地址 >>8；spacer 的 +0x30 链到下一个 QMD——QMD 链式执行。

## Blackwell QMD（384B = 96 dword；与 Ampere 256B 布局不同，字段为实测标定）

对照实验：`vecadd<<<4096,256>>>(a,b,c,n)` vs `dummy2<<<17,128>>>(x,k)`，两 QMD 逐 dword diff：

| 偏移 | 值（vecadd → dummy2） | 标定 |
|---|---|---|
| +0x30 | `0207a108 → 0207a110` | **next-QMD 链接指针**（GPU VA>>8） |
| +0x3c | `07237f34 → 07237f2c` | semaphore payload 地址（GPU VA） |
| +0x4c | `80610000 → 80c10000` | kernel 属性 flag（bit22 不同；疑寄存器/SM 配置，未解） |
| +0x50 | `9 → a` | 序号/计数（每 kernel +1?） |
| +0x80 | `0ff76750 → 0ff76800` | **kernel 参数缓冲指针**（GPU VA>>8；param buffer 各 kernel 独立） |
| +0x88[15:0] | `0x0100 → 0x0080` | **blockDim.x**（256→128 实锤） |
| +0x88[31:16] | 1 | blockDim.y（推测） |
| +0x90 | `02b41808 → 04b42808` | **kernel 入口地址**（编码含 flag 位；两 kernel 代码 VA 不同） |
| +0x9c | `4096 → 17` | **gridDim.x**（实锤） |
| +0xa0/+0xa4 | 1 / 1 | gridDim.y / gridDim.z |
| +0xa8/+0xb0/+0xd0/+0xe0 | `43f8a4xx → 43f8a8xx` 配 `020001fc/d` | 常量缓冲描述符（param buffer 另一编码？高 32 含 `0x?1fc/d` flag） |
| +0xe8/+0xec | `10300011, 50ff7675 → 50ff7680` | 参数缓冲指针（第二处，>>8） |
| +0xf0 | `0x7f` | 固定值（flag?） |

另观察到每段还有一个 896B staging DMA（目标 host pinned `0x7f50_xxxxxxxx`），
内容 = QMD 模板 + 常量/参数区（含 `0xff768000` 等 param buffer 指针值）。
参数本体（`{a,b,c,n}`）未在段内出现 → 由 libcuda 用普通 store 直接写 pinned 参数缓冲。

## 文件

- `src/nvtrace.c` — 拦截器主体 + JSONL
- `src/doorbell_trap.c` — SIGSEGV/TF 陷阱 + doorbell 时刻 GPFIFO/段快照
- `src/mini_decode.c` — x86-64 store 解码（GP 寄存器/imm/SSE/movnti）
- `tools/analyze.py` — trace 浏览；`tools/parse_seg.py` — 段→方法流；`tools/parse_qmd.py` — QMD 提取/对比
- `include/sdk/` — NVIDIA open-gpu-kernel-modules 头文件（clc96f/clc1c0/alloc_channel/ctrl0080fifo/cla0c0qmd 等，MIT）
- `include/nvrm_ioctl.h` — RM ioctl 号/结构（本地 nv-ioctl.h 权威部分 + hexdump 实测校准）

## 使用

```bash
make
LD_PRELOAD=./libnvtrace.so NVTRACE_OUT=/tmp/t.jsonl NVTRACE_TRAP=1 [NVTRACE_TRAP_ALL=1] \
    CUDA_VISIBLE_DEVICES=0 ./target/vecadd
python3 tools/analyze.py /tmp/t.jsonl summary|mmaps|classes|timeline|find|around
```

- `NVTRACE_TRAP=1`：陷阱候选小映射（doorbell 页 + 4KB userd 页）
- `NVTRACE_TRAP_ALL=1`：加 ≤64MB 的大映射（GPFIFO 环/pushbuffer 镜像）
- 目标程序可 `dlsym("nvtrace_mark")` 打标对齐 launch 窗口
- 开销：每次被陷阱的写 ~600µs（fsync + 2×mprotect + 单步）；10 次 launch 的 run 约几分钟

---

# Phase 5 — 指令上传时机 & H2D memcpy 机制（实测）

## kernel 指令（SASS）何时上传到 VRAM？

**时机：首次 launch 时（lazy module load），之后不重传。**
10 次连续 launch 中只有第 1 次伴随一个 696B 的代码上传段（其余 9 次只有 1848B launch 段）。

**路径（实测，段 nvtrace-seg-0273，compute channel ch0）：**
```
SET_OFFSET_OUT = 0x7f35_d3767500     ← host pinned 系统内存（不是 VRAM!）
SET_LINE_LENGTH_IN = 0x280 = 640B    ← 恰好是 vecadd 的 SASS 代码大小
LAUNCH_DMA = 0x41
LOAD_INLINE_DATA ×160 dword          ← SASS 字节原样内联（与 cuobjdump 的 cubin 逐字节吻合）
SET_REPORT_SEMAPHORE
```
- 代码经 compute channel 自己的 inline-data DMA 搬到 pinned 缓冲 `0x7f35d3767500`
- 该地址出现在每次 launch 的 896B staging 块 +0x21c 处（QMD 模板引用代码）
- **未观察到任何把代码从 pinned 搬到 VRAM 的 host channel DMA**
  → 两种可能：(a) GPU 直接从 pinned sysmem 经 PCIe 取指；(b) GSP-RM 在 GPU 侧
  自主完成 pinned→VRAM 拷贝（host 不可见）。QMD +0x90 字段随 kernel 变化
  （`0x02b41808`/`0x04b42808`，若 <<8 则落在 0x2b4/0x4b 高 GPU VA 区，支持 (b) 的
  VRAM 代码堆假说）——未最终定论，见 open questions。

## cudaMemcpy H2D（pageable → device）如何传输？

以 4MB `cudaMemcpy(da, ha, HostToDevice)` 为例（run10）：

1. libcuda 先把 pageable 源数据拷入 **1MB pinned staging 缓冲**（普通内存写，tracer 不可见）
2. 在 **CE channel**（本 run 为 ch8，runlist 13/chid 6）提交 GPFIFO：**每 1MB 一个 60B 方法段**，共 4 段：

```
[subch 4] OFFSET_IN  = 0x7f35_d2600000 (+1MB/段)   ← pinned staging 源
          OFFSET_OUT = 0x7f35_cb000000 (+1MB/段)   ← da，UVM 统一 VA（CPU/GPU 同址）
          LINE_LENGTH_IN = 0x100000                ← 1MB
          LAUNCH_DMA = 0x182
          SET_SEMAPHORE A/B/PAYLOAD                ← payload 0x60+i（chunk 序号）
          LAUNCH_DMA = 0x14                        ← completion flush
```
- 源/dst 都是 0x7f35xxxxxxxx 统一 VA：cudaMalloc 的 "device pointer" 在 UVM 下是 CPU/GPU 同值 VA
- DMA_COPY class（CAB5，BLACKWELL_DMA_COPY_B）方法布局与公开 c0b5/c1c0 一致
  （OFFSET_IN/OUT@0x400+，LINE_LENGTH@0x418，LAUNCH_DMA@0x300，SEMAPHORE@0x240）
- 4MB = 4 chunk × 1MB，串行依赖由 per-chunk semaphore 管理

## Open questions（更新）

1. ~~doorbell 值语义~~ → 已解。
2. QMD +0x90 的编码（kernel 入口）：若 <<8 为 VA 则指向 VRAM 代码堆，意味着 GSP 侧有 host 不可见的代码拷贝；需进一步验证（对比 pinned 地址与 QMD 字段的位关系，或换不同大小/位置的 kernel 采样）。
3. 0xd7 ioctl（560B）与 0xcb33 class（NV_CONFIDENTIAL_COMPUTE 为何出现在普通 vecadd？）。
4. 2080 Ti (Turing) 对照实验未做。
5. kernel params 本体写入路径未直接抓到（pinned 参数缓冲的普通内存写）。
6. 16 channel 角色逐一标定；H2D 的大块（>staging）与 pinned 源（免 staging 直接 DMA）路径未测。

---

# Phase 6 — QMD 代码指针 & 参数上传路径（已解）

## kernel 入口地址编码（+0x90 之谜解开：入口不在 +0x90）

对照 vecadd（code@`0x7f35d3767500`）与 dummy2（code@`0x7f35d3768000`）的 QMD，实测：

| 字段 | vecadd | dummy2 | 解码 |
|---|---|---|---|
| +0x80/+0x84 | `5d376750`/`014007f3` | `5d376800`/`014007f3` | **代码 VA>>8 拆分**：`+0x80[31:4]`=低 28 位，`+0x84[15:0]`=高位（0x7f3）；`+0x80[3:0]`=flag(0)，`+0x84` 高半=attr(0x014) |
| +0xec/+0xf0 | `35d37675`/`0000007f` | `35d37680`/`0000007f` | **同一代码 VA>>8 的第二份拷贝**（plain 64-bit `0x0000007f35d37675`） |
| +0x90 | `02b41808` | `04b42808` | per-kernel 常量（10 次 launch 不变，换 kernel 才变）；host 侧无对应 mmap → GPU VA 空间的 per-function 驱动结构指针（>>8），语义未定 |

**结论：QMD 直接携带 host pinned 内存的代码地址（>>8），GPU 指令取值经 PCIe 读 host pinned 内存；host channel 流量中不存在 pinned→VRAM 的代码拷贝。**

## kernel 参数上传路径（open question 5 已解）

每次 launch 有**两个 inline DMA**：
1. **896B 块** → pinned `0x7f35d2280000`：**驱动常量 bank**（c[0x0] 区）。首 qword = 指针 `0x7f35d2c38300`；`+0x1fc` = 完整代码 VA（未移位）；`+0x204+` = launch 配置常量（`1.0f`×3、`0x400`、`0x1000` 等）
2. **28B 块** → pinned `0x7f35d2280380`（紧跟 896B 之后）：**kernel 参数本体**
   - vecadd: `{da=0x7f35cb000000, db=0x7f35cb400000, dc=0x7f35cb800000, n=0x100000}` ✓
   - dummy2: `{dc=0x7f35cb800000, n=0x880=2176=17blk×128thr}` ✓

QMD +0xa8 为 per-launch 参数环形缓冲指针（每次 +0x400、8 项循环），指向 GPU VA 空间。

## Open questions（再更新）

1. ~~doorbell 值语义~~ → 已解（Phase 4）。
2. ~~kernel 入口编码~~ → 已解（+0x80/84 与 +0xec/f0 双拷贝 = code VA>>8；GPU 直接从 pinned sysmem 取指）。
3. ~~kernel params 写路径~~ → 已解（per-launch 28B inline DMA）。
4. +0x90 的 per-kernel 常量语义（GPU VA per-function 结构？可用多 kernel 采样或改 code 位置复测）。
5. 0xd7 ioctl（560B）与 0xcb33 class（NV_CONFIDENTIAL_COMPUTE 为何出现在普通 vecadd？）。
6. 2080 Ti (Turing) 对照实验未做。
7. 16 channel 角色逐一标定；H2D pinned 源（免 staging）路径未测。

---

# Phase 7 — QMD 全字段标定（qmdprobe 13 kernel + regprobe 梯子矩阵，实测）

采样：`target/qmdprobe.cu`（13 个 launch：grid/block 维度、静态/动态 shared、regcount、
local spill、barrier、cluster、printf、多参数）+ `target/regprobe.c` + `target/regs/`
（-maxrregcount 与 stack 梯子，driver API cuLaunchKernel 加载独立 cubin）。
注意 sm_120 的 maxrregcount 下限是 24（ptxas 自动 clamp）。

## QMD（384B, Blackwell V03 实测布局；公开头文件只有 V01_07=256B，GitHub master 亦无）

| 偏移 | 字段 | 证据 |
|---|---|---|
| +0x10 | byte2=0x3f = 6 个 cache INVALIDATE 标志（launch 全置）；bit23 = cluster enable；byte3=0x01 | cluster kernel 变 0x1bf |
| +0x24 | =3 常量 | |
| +0x28 | =0x190000 常量 | |
| +0x30 | next-QMD 指针 >>8（QMD ring 8 槽 ×0x800） | |
| +0x38 | per-context 常量（队列/semaphore 基址相关，0x2f5003a4） | 跨 run 同 |
| +0x3c | completion semaphore 地址 >>8：**8 槽 ring，每 launch -8，payload=+0x50** | 全矩阵 |
| +0x40 | =2 常量 | |
| +0x44 | ring 世代标记：第一圈=6，第二圈=a（每次绕环 +4？待 17+ launch 验证） | 两次 run |
| +0x4c | byte3: 0x81 普通 / 0x80 cluster；byte2 = blockDim 类: b≤64→0x81, b128→0xc1, b256→0x61 | |
| +0x50 | semaphore payload = 8+(launch%8)，与 +0x3c ring 同步绕环 | |
| +0x58 | =0x4000000 常量 | |
| +0x80/+0x84[15:0] | **代码 VA>>8**（+0x80[31:4]=低28位，+0x84[15:0]=高位） | 全 kernel |
| +0x84[31:16] | f(REG,STACK,blockDim)，公式未完全拟合：REG≈12/reg + STACK 非线性项 + 常数。数据点(REG,STACK,b→val): (24,104,64)→800, (32,40,64)→640, (40,0,64)→576, (40,256,64)→1376, (40,512,64)→2432, (40,1024,64)→4512, (40,2048,64)→8192, (40,256,128)→1344 | regprobe 梯子 |
| +0x88 | blockDim.x \| blockDim.y<<16 | L01: 0x30002=(2,3) |
| +0x8c[2:0] | blockDim.z | L01=4 |
| +0x8c[15:8] | **寄存器数**（= cubin REG；微 kernel 最小 16；printf 类有附加） | 梯子线性实锤 |
| +0x90 | **per-config 描述符指针（>>8, GPU VA，低 8 位含 flag）**：f(blockDim, shared/L1 carveout, barrier)，跨 run 确定性复现，与 kernel 身份/REG/STACK 无关。b≤64→0x04b44808, b128→0x04b42808, b256→0x02b41808, b256+8K shared→0x0d348848, b256+1K shared+barrier→0x04b42810 | 两次 run 交叉复现 |
| +0x94 | per-context 常量（0x710000 / vecadd run: 0x640000） | |
| +0x9c/+0xa0/+0xa4 | gridDim.x/y/z | 全矩阵 |
| +0xa8..+0xe4 | 常量 bank 描述符组：{addr>>8, size\|0x1fc aperture} 对：+0xa8=param ring 基址(每次+0x400,8槽), +0xb0, +0xc8, +0xe0 常量；+0xd0=+0xa8+0xc（cluster: +8）；+0xd4: 普通 0x8001fc / cluster 0x10001fc | |
| +0xe8 | =0x10310011 常量 | |
| +0xec/+0xf0 | **代码 VA>>8 第二份拷贝**（plain 64-bit） | |
| +0x100 | cluster dims 打包（0x00010102 = x2,y1,z1）；+0x104 bit31 = cluster 使能 | k_cluster |

## 896B 驱动常量 bank（c[0x0] 区，inline DMA 到 pinned，每次 launch 重传）

| blk 偏移 | 字段 |
|---|---|
| +0x00 | qword 指针（→另一 pinned 结构） |
| +0x110 | per-launch param ring VA 高位（8 槽，每次 +0x10000） |
| +0x140 | **全局 launch 计数器**（单调递增） |
| +0x148 | QMD ring 槽地址（+0x800/槽） |
| +0x1f8 / +0x298 | 代码 VA 低 32 位（两份拷贝，高 dword 相邻） |
| +0x20c / +0x2ac | **动态 shared 字节数**（launch 参数；两份） |
| +0x21c / +0x2bc | **总 shared/CTA**（静态+动态+1KB reserved；两份） |
| +0x220/+0x224/+0x228, +0x2c0.., +0x370.. | gridDim xyz（三份拷贝） |
| +0x2a0/+0x2cc | cluster dim x（=2）；+0x2b0 = 1/cluster_size（0.5f）；+0x36c = cluster 使能 |
| +0x348 / +0x350 | param ring VA；+0x350 = ring + kernel param 区在 c[0] 的偏移（= .nv.constant0 大小） |
| +0x360/+0x364/+0x368 | blockDim xyz |

## 其他新事实
- kernel 参数在独立小 inline DMA（紧跟 896B 后），param VA = ring(+0x348) 指向处
- **shared 大小不在 QMD 里**，只在常量 bank（+0x20c/+0x21c）→ 改动态 shared 不需要改 QMD
- L07（100K 动态 shared）launch 无段：cudaFuncSetAttribute 未生效时 launch 被 user 态静默拒绝（无 GPU 流量）
- 驱动 API（cuLaunchKernel/cuModuleLoad）与 runtime 走完全相同的 channel 协议

## Open questions（再更新）
1. +0x84[31:16] 精确公式（数据点已列；需 blockDim/REG 双变量矩阵收尾）
2. +0x90 描述符指向的内容（GPU VA，host 不可读；可实验：replay 时清 0 看是否 fault）
3. +0x4c byte2 各位语义（b≤64→0x81/b128→0xc1/b256→0x61 模式）
4. +0x44 ring 世代值序列（6→a→e?）
5. 0xd7 ioctl / 0xcb33 class；Turing 对照；16 channel 角色

---

# Phase 8 — 段重放注入与 QMD 必需字段实测（injectprobe）

**手动 GPU 命令注入全链路打通**（libnvtrace 的 `nvtrace_mark("inject...")` API）：

## 注入机制（tracer 内实现）
- pushbuffer 段**紧密排列**：next_seg_VA = prev_VA + prev_len（全 trace delta=0）→ 注入 = 在尾部写段 + 写 GPFIFO entry + GPPut+1 + 敲 doorbell
- doorbell token **按 channel 区分**（ch0 compute: 0x4000000c/runlist0, ch12 CE: 0x400e0007/runlist14）；
  通过"doorbell 写后哪个 channel 的 GPPut 前进"关联——重放用错 token 则段永远不执行（第一次失败原因）
- patch 语法：`inject[ch][:off:val,...]`（段内 dword 补丁）、`seg:K`（重放倒数第 K 段）、`swapcode:K`（换代码指针）

## 实测结果（k_ptr<<<2,32>>> 重放矩阵）
| 实验 | 结果 |
|---|---|
| 原样重放 | ✅ x 再 +1 |
| QMD gridX 改 4（seg 0x62c） | ✅ x=[2,2,1,1] —— grid 完全可控 |
| QMD +0x90 → 0（config 描述符指针） | ✅ **不需要** |
| QMD +0x4c → 0（block 类） | ✅ 不需要 |
| QMD +0x38/+0x94/+0x24/+0x28/+0x58 → 0 | ✅ 都不需要 |
| QMD +0x10 → 0（cache invalidate/版本） | ❌ 必需 |
| QMD +0xe8 → 0（0x10300011，bit16 随 kernel 变） | ❌ 必需 |
| QMD +0x40 → 0（=2） | ❌ 必需 |
| QMD +0x84[31:16] → 0 | ❌ **必需**（公式仍待解） |
| QMD +0x8c regcount → 0 | ❌ 必需 |
| QMD 代码指针 → 0 | ❌ 必需 |
| swapcode 换成 k_sub 的代码 | ✅ x=[-1,-1] —— 代码指针完全可控 |
| **重放代码上传段（SASS FADD imm 1.0f→256.0f）+ 重放 launch** | ✅ **x=[256,256] —— 手动上传+执行任意 SASS 成立** |

## 手动 launch 一个 cubin 的最小充分条件（实测结论）
1. 代码经 inline-DMA 段上传到 pinned 缓冲（或直接复用已有）
2. launch 段：896B 常量 bank + 参数 inline DMA + inline QMD
3. QMD 必须正确的字段：代码指针（+0x80/84lo/ec/f0）、+0x8c regcount、+0x84hi、
   +0x10、+0xe8、+0x40、grid/block dims、param 指针、semaphore
4. 可照搬参考 trace 的字段：+0x90、+0x4c、+0x38、+0x94、+0x24、+0x28、+0x58、+0x44、+0x50
5. 提交：GPFIFO entry + GPPut + 本 channel doorbell token

## 遗留
- +0x84[31:16] 公式（必需字段！目前有 17 个数据点，疑似 f(REG,STACK,blockDim,text 大小)）
- +0xe8 bit16 的含义（k_ptr=0x10300011 vs qmdprobe 多数 0x10310011）
- 从零构造段（非重放模板）：常量 bank 全字段、QMD spacer（QMD[0]）的作用

### Phase 8 补：必需字段逐位扫描结果（inject 变异，k_stk 2KB local 重压验证）
- **+0x84[31:16]**：值不敏感！0x40/0x800/0x1000/0x2000 全部正确执行（k_stk 640 条 STL/LDL、
  STACK=2048 结果依然正确）——只需**非零**（0 = 不执行）。公式不必再追，手工构造时令其非零即可。
  （注：重放场景 local 后备池已由正常 launch 分配；从零场景可能仍需合理值。）
- **+0x10**：只需 **byte3 = 0x01**（疑似 QMD 版本/valid）。byte2 的 6 个 cache-invalidate 位全可省。
- **+0xe8**：只需 **bit0 = 1**（0x00000001 即可，bit16/byte3 无关）。疑似 QMD valid/enable。
- 必需字段最终清单（除代码指针/regcount/dims/参数/semaphore 外）：
  **+0x10 byte3=0x01、+0xe8 bit0=1、+0x40=2、+0x84hi≠0、+0x8c regcount**
- 其余所有字段（+0x90/+0x4c/+0x38/+0x94/+0x24/+0x28/+0x58/+0x44/+0x50/+0xe8 高位）可填 0。

---

# Phase 9 — sm_120 c[0x0] 内核视角直读 + wire↔kernel 映射（cbank120，实测）

## 方法（sm_90 ldc_dump_const.cu 同款 trick 移植）
- `struct Big { u32 a[64]; }` 大体积 by-value 参数 + `#pragma unroll 1` 动态下标循环骗过 ptxas
  offset checker → 生成真正的 `LDC Rd, c[0x0][R+0x380]`（寄存器变址常量 load）。
- **坑1**：静态可见的负数下标会被 ptxas offset checker 静默降级为 `LDG param_ptr-0x380+i*4`
  （param 指针处的全局内存），读出来是驱动 host pinned 簿记数据而非 cmem —— 必须动态下标。
- **坑2**：sm_120 上数组参数按**指针**传（`c[0x0][0x380]` 存指向参数数据副本的设备指针，
  `__grid_constant__` 与否都一样）；struct Big 例外（真实 inline 在 c[0x0][0x380]）。
- target: `launchprobe/target/cbank120.cu`；dump: `/tmp/cbank120_dump.bin`；
  trace: `/tmp/nvtrace-cbank.jsonl` + `/tmp/nvseg-cbank/`。

## wire 块（896B）→ kernel c[0x0] 窗口映射（sentinel 对齐，239/256 dword 吻合）
- **⚠️ 修正（2026-08-08 晚）**：下文"0x24 字节 GPU 插入/上移 +0x24"是**错的**。
  后续 224/224 dword 实测证明 wire 896B ↔ kernel c[0x0] 是**恒等映射**
  （逐 dword 对齐）。原"0x24 插入"是哨兵锚定错位造成的伪影。
- `c0[0x380]` 起 = 参数区（wire `blk[0x380]` 起恒等）

## sm_120 c[0x0] 布局（kernel 视角；launch(1,1,1)/(1,1,1) 与 (3,5,7)/(2,4,6)+3KB dyn smem 双探针标定）
| 偏移 | 值/语义 | sm_90 对应（ldc.md） |
|---|---|---|
| 0x000 | 64b pinned VA（GPU 回填，wire=0） | 新 |
| 0x0c0 | 64b 每次 run 变化的值（timestamp/seed 样） | — |
| 0x0f8 | 0x000fffff | — |
| 0x104/0x10c | 0x100 ×2 | — |
| 0x108 | 0x02000000 (32MB) | — |
| 0x110 | 64b pinned VA，param ring（+0x10000/launch） | 0xc0:0xc4 ring ✓ |
| 0x118 | 64b pinned VA（页对齐） | — |
| 0x140 | **launch 序号计数器** | 0x30 ✓ |
| 0x148 | 64b QMD ring 槽设备 VA（0x2_07a0c000） | 0x38 ring（+0x800/槽）✓ |
| 0x16c | **0x400 reserved shared 基址**（不随 dyn smem 变） | 0x114 ✓ |
| **0x1b0..0x230 / 0x250..0x2d0** | **两个 0xa0 步长的 bank 块 B1/B2**（同布局） | cluster 块 ✓ |
| B+0x00 | 驱动常量 0x04b032c8 | 0x40=0x038432c8（同尾 32c8）✓ |
| B+0x18 | flag = 1 | — |
| B+0x28 | 常量 **0x120**（= QMD+0x84hi 平凡 kernel 值！） | 0x68=0x120 ✓ |
| B+0x48 | 64b **代码 VA**（pinned sysmem） | 新（sm_90 代码 VA 不在 preset 区） |
| B+0x50..0x58 | **cluster dims xyz** | 0x144/48/4c ✓ |
| B+0x5c | **动态 shared 字节数** | 0x2c ✓ |
| B+0x60..0x68 | **1.0f/clusterDim xyz** | 0x150/54/58 ✓ |
| B+0x6c | **shared 分配顶 = 0x400+dyn** | 0x13c ✓ |
| B+0x70..0x7c | gridDim xyz + 第 4 项=1 | grid-in-clusters 类似 |
| 0x2d0 | **SM 数 = 0xaa = 170**（RTX 5090 ✓） | 0x10c=114 (H800) ✓ |
| 0x2dc | **1<<24 DSMEM 每 CTA 片宽** | 0x16c ✓ |
| 0x2e0/0x2f0 | 两个 64b 设备 VA（0x7f32_00000000，TB 对齐） | — |
| 0x2f8 | 64b pinned VA | — |
| 0x348/0x350 | **param 区 VA 基址/末尾**（ring+0x380 .. +参数大小） | 0x198/0x1a0（0xc0 派生）✓ |
| 0x358 | **全局内存描述符 = 0**（SASS `LDCU.64 UR4, c[0x0][0x358]` → `desc[UR4]`） | 0x208 ✓ |
| 0x360..0x368 | **blockDim xyz**（SASS 入口 `LDC R7, c[0x0][0x360]`） | 0x00..0x08 ✓ |
| 0x370..0x378 | **gridDim xyz** | 0x0c..0x14 ✓ |
| 0x37c | **栈帧基址 → R1 = 0x00fffdc0**（与 sm_90 同值！SASS 首条 `LDC R1, c[0x0][0x37c]`） | 0x28 ✓ |
| 0x380 | **参数区基址**（EIATTR param base；sm_120 从 0x210 → 0x380） | 0x210 |

## 要点
- sm_120 preset 区比 sm_90 大（896B vs 528B），整体后移并复制成 **B1/B2 双 bank 块**
  （与 QMD +0xa8..+0xe4 的多个 const bank 描述符对应：每 bank 一份镜像）。
- 所有 launch 形状字段（grid/block/cluster/dyn smem/shared 顶）都在 bank 块里，
  **QMD 只放一份 grid/block**；改 launch 形状主要改常量 bank。
- 0x120 常量出现在 c0 两个 bank 块 B+0x28 —— 与 QMD+0x84hi 的"平凡 kernel=0x120"强相关，
  支持 +0x84hi = per-kernel 常量（值不敏感实测结论不变，但语义线索+1）。
- 未标定：0x000（GPU 回填 VA）、0x0c0（per-run 64b）、0x0f8/0x104/0x108/0x10c、
  0x118、0x2e0/0x2f0/0x2f8 VA、coop launch 标志位/barrier ptr 槽位（sm_90 在 0x44/0x110，
  sm_120 未探测）、wire 块尾 0x24 描述符完整解码。

## 下一步候选
1. coop launch / cluster(2) / 非对称 cluster 探针补齐剩余槽位（sm_90 cbank0_sweep.cu 流程）
2. 解码 wire 块尾 0x24 launch 描述符（随参数个数/大小变，做参数矩阵）
3. 从零构造段：896B 模板（本表）+ 参数 DMA + inline QMD + spacer + semaphore 注入提交

## Phase 9 补 — cluster / cooperative sweep（cbank120_sweep，实测）

探针：同一 dumpc kernel，5 配置（base(3,5,7)/(2,4,6)+3KB、clu(2,1,1)、clu(4,2,1)、clu(1,1,2)、
coop(2,1,1)/(64,1,1)），c[0x0] 全窗口 + inline QMD 双视角 diff。
trace: `/tmp/nvtrace-sweep.jsonl` + `/tmp/nvseg-sweep/`；dumps: `/tmp/cbank120_{base,clu2,clu42,cluz,coop}.bin`。

### c[0x0] 新增/修正槽位
| 偏移 | 语义 | 证据 |
|---|---|---|
| **0x1b4/0x1b8 (B1+0x04), 0x254/0x258 (B2+0x04)** | **coop barrier ptr（64b VA）**，仅 coop 非零（0x7f85_76c00000，两个 bank 块各一份） | coop 唯一新增指针；sm_90 0x44:0x48 对应 |
| **0x2d4** | **coop flag = 1**（紧邻 SM 数 0x2d0） | 仅 coop=1；sm_90 0x110 对应 |
| 0x2a0/0x2a4/0x2a8 (B2+0x50) | cluster dims xyz | clu42 → (4,2,1) ✓ |
| 0x2b0/0x2b4/0x2b8 (B2+0x60) | 1.0f/clusterDim xyz | clu42 → 0.25f/0.5f/1.0f ✓ |
| **0x2cc (B2+0x7c)** | **cluster 总 CTA 数**（2/8/2，非 dim x） | 三配置乘积 ✓（修正 Phase 9 初表"gridDim+1"误读：B+0x70..0x78 是 gridDim xyz，+0x7c 是 cluster size，无 cluster 时=1） |
| **0x36c** | **cluster-present flag** | 仅三次 cluster launch =1；sm_90 0x140 对应 |
| 0x200..0x218 (B1+0x50..0x68) | **B1 的 cluster 槽永远不跟踪**（恒 1 / 1.0f），B1+0x70 (0x220..) 仍跟踪 gridDim | clu42 下 0x200/0x210 无 diff —— **B1=非 cluster bank 镜像，B2=cluster bank 镜像** |

### QMD 新增字段（spacer QMD 五次完全一致 → per-context 常量，与 launch 配置无关）
| 偏移 | 语义 | 证据 |
|---|---|---|
| +0x10 bit23 | cluster enable | 三次 cluster 全置位 |
| **+0x10 bit31** | 仅 **clu42（8 CTA cluster）** 置位（0x81bf0000）；size-2 cluster 不置 | 疑似"大 cluster"模式位 |
| **+0x10 = 0x02080000** | **coop 专属**：bit25 + bit19；普通 launch 的 bits[21:16]=0x3f 被清成 0x08 | coop 唯一 |
| +0x100 | cluster dims 打包 x=byte0,y=byte1,z=byte2 | clu42=0x00010204 ✓ |
| +0x104 bit31 | cluster enable | 三次 cluster 全置位 |
| **+0x108 = 0x00010002, +0x10c = 1** | **coop 专属**：lo16=2=coop grid 总 CTA 数，+0x10c=coop enable | 仅 coop 非零 |
| **coop 时 +0x9c/+0xa0/+0xa4 = 1,1,1** | **QMD grid 槽在 coop 下失真**，真实 grid 走常量 bank（c0[0x370..]=2,1,1 ✓） | coop grid=(2,1,1) 但 QMD=1,1,1 |
| +0x4c | cluster 下 0x81810000→0x80210000（此前已知可填 0） | 三次 cluster 一致 |
| +0xd4 hi16 | const bank 描述符 size：0x0100→**0x0180**（cluster 下常量 bank 增大，ring 步长 +0x200→+0x400） | 三次 cluster 一致 |
| **+0x124..0x134 = 0xffffffff ×5** | 仅 **clu42**（160 bit 全 1 掩码；疑似大 cluster 的 CTA/GPC bitmap） | 其他四次为 0 |
| +0x90 | coop 下 = 0x04b44808 —— 与 Phase 7 "b≤64" 值一致（coop block=64），佐证 +0x90=f(blockDim,shared,barrier) | ✓ |

### 对"从零构造"的影响
- 普通 launch：常量 bank 896B 模板 + 参数 + 主 QMD + spacer（固定常量）+ semaphore。
- cluster launch 额外：QMD +0x10 bit23、+0x100 dims、+0x104 bit31、+0x4c、+0xd4 size、
  常量 bank B2 的 cluster 槽（dims/reciprocals/size/flag 0x36c）；8-CTA cluster 再 +0x10 bit31 + +0x124..0x134。
- coop launch 额外：QMD +0x10=0x02080000、+0x108/+0x10c、grid 槽置 1、常量 bank B+0x04 barrier ptr + 0x2d4 flag。
- open：+0x124 掩码语义（160 bit 与 170 SM 不符，疑似 GPC/CPC 粒度）；+0x10 bits[21:16]=0x3f 的语义（普通 launch 恒 0x3f，疑似 raster/launch-type 字段）。

---

# Phase 10 — 从零构造 launch 成功（construct，无模板重放）✅

**目标达成**：全用户态构造的 GPU 命令段（常量 bank + inline QMD + report semaphore）
+ 仓库 assembler 手写的 SASS kernel，经 injectraw 注入执行成功：
report semaphore = 0xdead0001，out = 0xdeadbeef。
target: `launchprobe/target/construct.cu`；kernel 生成: `launchprobe/tools/gen_construct_kernel.py`。

## 关键 bug（卡了两轮）：GPFIFO entry LENGTH 字段
- entry1 布局（clc06f.h）：[7:0]=GET_HI(addr>>32) [8]=PRIV [9]=LEVEL **[30:10]=LENGTH(dwords)** [31]=SYNC。
- 旧 submit_segment 保留上一个段的 LENGTH —— **重放同长段时恰好正确（Phase 8 没踩到），
  不同长的 raw 段会多抓旧字节 → 段尾垃圾方法使 QMD 不执行**。
- 修复：`hi = (old & 0x80000300) | ((addr>>32)&0xff) | ((len/4)<<10)`（保留 PRIV/LEVEL/SYNC）。

## 其他实测修正
- **QMD +0x3c = semaphore 设备 VA 原始低 32 位**（不是 >>8！证据：driver 的 4B 预写目标
  VA = 0x2_07237f3c = QMD +0x3c 值 0x07237f3c 补 0x2 前缀）。预写值 = launch 序号（grid 完成后
  GPU 写 +0x50 payload 覆盖）。
- **inline QMD staging 地址必须 < 2^40**（方法记录 addr 字段 = VA>>8 仅 32 位）：
  cudaMalloc 在 UVM 下返回 0x7f.. host 段 VA 不可用 → **复用 driver QMD ring 下一槽**
  （c[0x0][0x148] 读当前槽，+0x800 = 下一槽；QMD semaphore 放槽尾 +0x400 未用区）。
- **const bank 描述符地址 = (uint32_t)(VA>>6)**（截断即正确，driver 同规律；
  desc<<6 == VA & 0x3FFFFFFFFF 实测多 launch 验证）。不是物理地址——UVM VA 低 38 位直接编码。

## 从零段的最小充分内容（实测通过）
段 = 2 条方法记录（subch 1, INC）：
1. `hdr 0x206220c6`（mthd 0x318 SET_INLINE_QMD_ADDRESS_A, cnt 98）+ flags 0x40000000
   + staging_va>>8 + 96 dword QMD
2. `hdr 0x200426c0`（mthd 0x1b00 SET_REPORT_SEMAPHORE, cnt 4）+ VA64 + payload + flags 0x04

QMD 最小字段（其余全 0）：
- +0x10=0x013f0000、+0x30=自链（staging>>8）、+0x3c=sema VA 低32、+0x40=2、+0x50=payload
- 代码指针：+0x80=(VA>>4)&0xffffffff、+0x84=(0x120<<16)|((VA>>36)&0xffff)、+0xec/+0xf0=VA>>8 lo/hi
- +0x88=blockDim.x|y<<16、+0x8c=blockDim.z|regcount<<8、+0x9c..+0xa4=gridDim
- 4 个 bank 描述符全指 arena：+0xa8/+0xb0/+0xe0=(uint32_t)(VA>>6)、+0xd0=同|0xc，
  mask 0x020001fe/0x048001fe/0x010001fe/0x800001fe
- +0xe8=1

常量 bank（pinned arena，CPU 直写，无需 DMA 方法）：**全 0 + [0x0f8]=0x000fffff 即可运行**
（c[0x0][0x358]=0 → desc 恒等映射；kernel 若用 LDC 读参数/blockDim 等才需填对应槽）。

**不需要**：spacer QMD、4B 预写、常量 bank DMA 方法、+0x44/+0x4c/+0x90/+0x94/+0x24/+0x28/+0x58/+0x38、
coop/cluster 字段。

## kernel 侧
- 6 条指令（LDCU.64 c[0x0][0x358] → MOV32I×3 → STG.E desc → EXIT），仓库 assembler 生成，
  regcount=8 可运行（低于 ptxas 的 16 clamp）。
- 代码放 pinned sysmem（cudaHostAlloc arena+0x1000），GPU 经 PCIe 取指 ✓。
- STG 目标 = cudaMalloc 设备缓冲，地址作立即数烧进 MOV32I（无参数区也可行）。

## 流程（target 视角）
1. 任意 warm-up launch ×1（让 tracer 学到 ch0 doorbell/pushbuffer tail）
2. dumpc kernel dump c[0x0]（读 0x148 拿 QMD ring 槽 VA）
3. cudaHostAlloc arena：const bank @+0、code @+0x1000、report sema @+0x2000
4. 构 QMD + 段 → /tmp/rawseg.bin → `nvtrace_mark("injectraw:/tmp/rawseg.bin")`
5. 轮询 report sema + cudaMemcpy 验证 out

## tracer 新 API
- `nvtrace_mark("injectraw[ch]:/path/seg.bin")`：读文件原样提交（doorbell_trap.c `nvtrace_inject_raw`，
  提交路径重构为 `submit_segment` 公共函数，`nvtrace_inject_last` 与其共用）。

---

# Phase 11 — 真实 nvcc cubin 从零 launch 成功（cblaunch，方案 D 完全版）✅

**目标达成**：真实 nvcc 编译的 cubin（`target/demo_kernel.cubin` / `demo2_kernel.cubin`）
从零 launch 成功，**连续 10/10 SUCCESS**（out=63..66，sema=0xdead0002），
参数与 kernel 通用化（CB_A/CB_B/CB_KERNEL env 切换，全过）。
target: `launchprobe/target/cblaunch.cu`；对照 cubin: `target/demo_kernel.cu` / `demo2_kernel.cu`。

## 方案 D 完全版（最终方案）

1. **ref launch 带参**：`demo<<<1,4>>>(d_out, A, B)`（A/B 可配）→ driver 用小 DMA
   把 {d_out, A, B} 写进**它自己的 bank**（GPU VA <2^38，SM 常量域可读）。
2. **注入前清空 out**：`cudaMemset(d_out,0)` —— out≠0 只能来自注入 QMD，可归因。
3. **照抄 bank 描述符**：从捕获的 driver 段 QMD 提取
   +0xa8/+0xac/+0xb0/+0xb4/+0xd0/+0xd4/+0xe0/+0xe4 八个 dword 进我们的 QMD。
4. **注入 QMD 复用同一 bank** → SM 读到正确参数 → out = A*B±i。

实测矩阵（全 SUCCESS）：demo(7,9)→63..66、demo(2,3)→6..9、demo(5,11)→55..58、
demo(13,4)→52..55、demo(100,2)→200..203、demo2(6,7)→42 41 40 39、demo2(3,8)→24..21。
demo 连续 10 次 + demo2 连续 5 次全过。

**局限**：参数供应依赖 driver 的 ref launch 带我们想要的参数（它天然把参数写进自己的
bank）。"换 cubin" = ref launch 换成对应 kernel + 注入代码指针换对应 .text。

## 关键新结论（本轮实测）

1. **低 VA bank（mmap 0x200000 + cudaHostRegister）走不通**：
   GPU **DMA 引擎（CE/cudaMemcpy）能读**（读回 CAFE0001 ✓），但 **SM 常量路径
   （LDC c[0x0]）不能读**（LDC 返回 0 → STG 到 0 → illegal access）。
   → 用户态 host 映射（即使低 VA、即使注册）不在 SM 常量可访问域。
   probe: `target/probe_lowva.cu`（仓库 assembler kernel + 低 VA bank）。
2. **construct.cu 之前"成功"的真相**：bank 在 UVM arena (0x7f..)，描述符 `cb_va>>6`
   截断成 32 位 → SM 实际读低 VA 0x0db200000 一类随机驱动内存。construct kernel 只用
   `LDCU.64 c[0x0][0x358]` 读 desc，之前恰读到 0（desc=0 恒等）→ STG 成功。
   **现在该位置内容变了 → desc 非法 → illegal access**。construct 现在的运行 FAIL
   是"踩中全零内存"的运气失效，不是可持续方案。
3. **小 DMA 写 bank 半可行**：注入段小 DMA（SET_OFFSET_OUT+LINE_LENGTH+LAUNCH_DMA
   0x41+LOAD_INLINE_DATA）**能执行**（写我们 UVM arena 成功），但：
   - 目标=driver bank staging CPU VA (0x7f..) → 静默失败（不在我们 context GPU 页表）；
   - 目标=driver bank GPU VA (0x..2a0380) → 卡死 channel。
   → 只能写自己 context 可见内存，写不进 driver bank。
4. **driver bank 双重映射的 CPU 侧不可写**：bank GPU VA 0x..a2a0000 ↔ staging
   CPU VA 0x7f..（同一物理页，低 32 位相同），但该 CPU VA 在本进程 PROT_NONE
   （直写 SIGSEGV）。
5. **driver bank 常量域 = SM 可读的唯一来源**（实测）：普通 launch 的 c[0x0] 可读
   （cbank120），我们构造的低 VA/UVM bank 都不可读。方案 D 借 driver bank 是当前
   唯一通路。

## 遗留 / 后续
- 真正的"无 driver 参与"常量供应（方案 B：RM ioctl 申请 SM 常量域可访问的 sysmem）
  未做——工作量较大，对应遗留 open 项"从零 ioctl bring-up 链"。
- 参数经 ref launch 供应，是否算"全用户态手动构造"见仁见智；机制层（QMD/GPFIFO/
  注入/代码提取）全是用户态手动。真正的从零 = 方案 B 完成。
- construct.cu（Phase 10）现在 FAIL，需更新其文档或改用 cblaunch 方案。

---

# Phase 12 — cmem 分配链逆向（context creation 追踪，2026-08-08 晚）

目标：回答"正常 launch 路径 driver 怎么分配 constant memory (c[0x0])"。
方法：`target/ctxprobe.cu`（cuInit→context→1 launch）全程 LD_PRELOAD 追踪
open/ioctl/mmap + doorbell/GPFIFO 陷阱，把 context 阶段与 launch 阶段分开。

## 结论：cmem 不是"用户态分配"的，是 GSP-RM 内部 per-channel 资源

1. **用户态 ioctl 层看不到 bank 分配**：context 阶段 412 个 ioctl（RM_ALLOC 107、
   RM_CONTROL 236、RM_MAP_MEMORY 28、legacy 4 等），launch 阶段只有 **1 个**
   RM_ALLOC（hClass=0x40 NV01 内存，hObject=0x5c000087，paramsVA 用户态结构），
   **无对应 MAP_MEMORY 回填 bank VA**。bank 的 GPU VA 完全由 GSP-RM 内部管理。
2. **bank 是 per-launch 轮换的 2MB 对齐区**：QMD 描述符解析 bank VA 每次运行不同
   （0xf86280000 / 0x3fa280000 / 0x2da2280000），低 28 位稳定在 0xa280000 家族，
   逐 launch 轮换。bank 与 staging 低 32 位相同（同一物理页两映射）。
3. **bank 描述符结构（实测 0268 段）**：
   - +0xa8 = `0xb688a000` → bank VA 0x2da2280000（desc<<6）
   - +0xac = `0x020001fe`（mask，aperture/valid 位）
   - +0xb0 = `0xb6880400` → 0x2da2010000（第二槽）
   - +0xd0 = +0xa8 | 0xc
   - +0xe0 = `0xb6880000` → 0x2da2000000（base，另一份）
   - +0xe4 = `0x800001fe`
4. **bank 内容由 driver 每次 launch 用小 DMA 传 staging**：
   - 896B bank 镜像 → 0x7f..a2280000
   - 参数（LOAD_INLINE 2-4 dword）→ 0x7f..a2280380
   - bank staging 与 GPU VA 低 32 位相同（0xa2280000），确认同一物理页。
5. **launch 无 bank 相关显式寄存器写**：mmio_w 只有 GPFIFO entry 写 + GPPut +
   doorbell，无 bank 配置。bank 完全是 QMD 描述符引用的既存 GPU 内存。

## 对"手动分配 cmem"的意义

- 用户态 API（cudaHostAlloc/cudaMalloc/cudaHostRegister/mmap+register）**给不出**
  SM 常量路径可读的映射（Phase 11 已排除低 VA + UVM）。
- driver 的 bank 是 GSP-RM 预分配的 GPU 可访问 sysmem（0x..a2xx0000 区），
  用户态只有 QMD 描述符引用，没有分配/映射的 ioctl 可见。
- 真正的"从零手动分配"需要复刻 RM 的 sysmem 池（方案 B）：`RM_ALLOC_MEMORY`
  (0x5D) + `RM_MAP_MEMORY_DMA` (0x51)，带正确的内存属性使 SM 常量路径可读。
  目前未观察到 driver 走这些 ioctl 分 bank（可能用 GPU fd 上的 0x27 legacy
  或 RM_ALLOC hClass=0x40 池），需进一步对 bank 分配做针对性追踪。

## 待做
- 定位 bank 池的具体 ioctl：对比多次 launch，抓 hClass=0x40/0x3e 分配与
  bank VA 的对应关系（可能需要 hook paramsVA 指向的 NV_MEMORY_ALLOCATION_PARAMS）。
- 尝试直接调 RM_ALLOC_MEMORY + MAP_MEMORY_DMA 分配一块低 GPU VA sysmem，
  验证 SM 常量路径可读性（方案 B 的 bring-up）。

## Phase 12 补充（pushbuffer 段作为 bank 的实验，2026-08-08 晚）

- **pushbuffer 段（0x200600000-0x203600000，/dev/nvidiactl rw-s，CPU 可写）尝试作
  bank**：CPU 写 0x200700000+0x380 成功且读回正确（0x123456789abcdef0,7,9），但
  **SM 常量路径读到 0**（demo kernel LDC c[0x0][0x380] 返回 0，STG 到 0 → illegal
  access）。→ CPU 写 nvidiactl 映射 ≠ GPU 侧可见，pushbuffer 段不可作 bank。
- **driver bank 只读 probe**（PB_BANK_VA=driver bank，PB_NO_WRITE=1，真实 demo
  kernel）：kernel 启动、读到 desc/参数、STG 尝试（stale 指针→illegal access）。
  → 确认 **SM 常量路径确实只读 driver bank（GSP 预分配 sysmem）**。
- **关键教训**：probe 之前 demo_clone 报 illegal instruction 是 **QMD regcount 欠配**
  （用了 8，demo 需 10）→ 寄存器窗口钳制 → R8+ 访问 illegal instruction。
  **必须从 cubin meta 读 regcount 填 QMD +0x8c**（与 cblaunch 一致）。
- **SM 常量路径可读内存的候选全部排除**：UVM arena（截断）、低 VA mmap+register
  （LDC 返回 0）、pushbuffer 段（CPU 写 GPU 不见）。只剩 driver bank = GSP 预分配
  sysmem。方案 B（RM ioctl 复刻）是唯一出路。
