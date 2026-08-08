# CONTEXT.md — launchprobe 交接文档（2026-08-08）

> 写给下一个 agent。本文件是当前工作状态快照；历史结论见 `NOTES.md`（Phase 4-10）。
> **注意 NOTES.md Phase 9 的"GPU 在 wire 与 kernel 之间插入 0x24 字节"段落是错的**：
> 后续 224/224 dword 实测证明 wire 896B ↔ kernel c[0x0] 是**恒等映射**，
> "0x24 插入"是哨兵锚定错位造成的伪影。待修正。

## 1. 总目标

逆向 CUDA kernel launch 时驱动/libcuda 与 GPU 的通信协议（RTX 5090, sm_120 为主），
最终**全用户态手动构造命令段加载并 launch 一个 cubin**。

- Phase 10 已达成：手写 SASS kernel（仓库 assembler 生成）从零构造 launch 成功
  （`target/construct.cu`，最小充分段 = inline QMD 记录 + report sema 记录）。
  ⚠️ **重测注意（2026-08-08 晚）**：`target/construct` 现在运行 FAIL
  （sema 触发但 STG illegal access）。原因见 §3.5 —— 它之前的成功依赖 UVM arena
  bank 描述符截断后恰读到 desc=0，环境变化后不成立。
- **Phase 11 已达成（2026-08-08 晚）**：真实 nvcc cubin（`target/cblaunch.cu` +
  `target/demo_kernel.cubin`）从零 launch **连续 10/10 SUCCESS**，
  out = 63 64 65 66（sema=0xdead0002），参数通用化（CB_A/CB_B 换值全过）。
  方案 = **方案 D 完全版**（§3.5）：driver 的 ref launch 把 {d_out, A, B} 写进
  它自己的 bank，注入 QMD 复用同一 bank 描述符，SM 读到正确参数，无需写 bank。
  成功判据 §7 的**两条全达成**：10 连过 + 换 cubin/参数成立
  （`CB_KERNEL=demo2` 5/5 过，demo2 = a*b−tid；A/B 多组值全过）。
- 遗留：真正的"无 driver 参与"常量供应（方案 B，RM ioctl 申请 SM 常量域 sysmem）
  未做，工作量较大；机制层（QMD/GPFIFO/注入/代码提取/参数复用）已全用户态手动。

## 2. 环境与运行方式

- RTX 5090 (GB202) + RTX 2080 Ti，驱动 580.65.06（GSP-RM），CUDA 13.0
- `export PATH=/usr/local/cuda/bin:$PATH`（nvcc/cuobjdump）
- 工作目录 `launchprobe/`；构建：`nvcc -arch=sm_120 -O2 -o target/cblaunch target/cblaunch.cu`
- 运行：
  ```bash
  rm -rf /tmp/nvseg-cbl && mkdir -p /tmp/nvseg-cbl
  LD_PRELOAD=./libnvtrace.so NVTRACE_OUT=/tmp/nvtrace-cbl.jsonl \
    NVTRACE_DUMP_DIR=/tmp/nvseg-cbl NVTRACE_TRAP=1 NVTRACE_TRAP_ALL=1 \
    CUDA_VISIBLE_DEVICES=0 ./target/cblaunch
  ```
- tracer lib 源码 `src/doorbell_trap.c` / `src/nvtrace.c`，改后需重新 build
  （Makefile 目标）。
- sudo 密码 x854y@d1Xa19；外网 `HTTPS_PROXY=http://127.0.0.1:7890`

## 3. Phase 11 已确认的事实（本session新结论，NOTES.md 未写）

### 3.1 已成功部分

- `tools/extract_cubin.py`：纯 stdlib 从 cubin ELF 提取 `.text.<kernel>` +
  cuobjdump resource-usage 拿 regcount。**无代码重定位**（仅 debug_frame rela）。
- 从零注入 QMD 执行真实 nvcc SASS：**成功过多次**（out = 63 64 65 66 = 7*9+i ✓），
  但成功率约 50-60%，失败时报 illegal memory access / unspecified launch failure。
- **QMD +0x84[31:16] = 寄存器/local 分配尺寸**：STACK=0 kernel 时为
  `0x100 + 4*regcount`（driver 数据点：reg8→0x120、reg16→0x140；driver 对
  EIATTR REG:10 向上取 16）。**欠配会静默钳制可用寄存器窗口**（R8+ fault）。
- **+0x8c[23:16] = 2**（alloc mode？）已设置（未单独隔离验证必要性，建议保留）。
- c[0x0][0x37c] 必须 = 0x00fffdc0（每线程栈帧基址），nvcc prologue 会读进 R1；
  手写 kernel 不读所以 Phase 10 没踩到。
- 排障方法论：同一 SASS 经仓库 assembler 的 CudaModule 正常 launch 全 OK →
  fault 在构造环境而非指令字节/调度 bracket。

### 3.2 根本原因（已定位）

**常量 bank 描述符只编码 VA[37:6]**：QMD +0xa8/+0xb0/+0xd0/+0xe0 = `(uint32)(VA>>6)`，
`desc<<6 == VA & 0x3fffffffff`。因此：

- 我们的 cudaHostAlloc arena 在 UVM 下是 0x7f.. VA（bit 46）→ 截断后指向
  0x3F.. 窗口内的**随机驱动内存** → SM 读 c[0x0] 拿到垃圾 → 参数 out_ptr 垃圾 →
  STG 野指针 fault。这解释了 50-60% 成功率的非确定性（有时垃圾值恰好无害）。
- driver 自己的 bank 不走 UVM：每次 launch 用小 DMA（pushbuffer inline 数据）
  写 0x7f.. CPU staging VA，描述符指 **GPU VA 0x..a2a0000（<2^38，逐 launch
  +0x400 轮换）**——两者是**同一批 pinned 物理页的两重映射**（低 32 位完全相同，
  实测多次：staging 0x7fXXYY2a0000 ↔ bank GPU VA 0x..YY2a0000）。
- driver 描述符 mask 字段逐 launch 会变：+0xac 见过 0x020001fb / 0x020001fc /
  0x020001fe（bit0-2 疑似 valid/版本位），**应整体照抄捕获值，不要手写**。

### 3.3 已排除的路径（全部实测失败）

1. **bank 放自己 pinned arena（0x7f.. VA）**：描述符截断 → 非确定性 fault（原方案）。
2. **compute channel 小 DMA（mthd 0x188/0x180/0x1b0）把 bank 写进 QMD ring 槽
   （0x2_07a0exxx）或自己 arena**：**段卡死**（后续记录全不执行，sema 探针不触发，
   channel 报 unspecified launch failure）。即使与 driver 段逐字节同构（目标同为
   0x7f.. sysmem）也卡。**原因未明**——最大嫌疑是 GPFIFO entry 的
   PRIV/LEVEL/SYNC 位（`submit_segment` 目前从前一条 entry 继承，见
   `src/doorbell_trap.c:159-164`），或 inline-DMA 对 pushbuffer 取数方式有
   额外前提。注意 driver 的 4B semaphore 预写就是用同方法写 0x2_07237f2c
   （设备 VA）成功的，所以目标 aperture 不是唯一变量。
3. **report-semaphore 记录当 4B 写原语戳 bank/ring VA**（0x2_07a0exxx、
   0x..a2a0380）：第一条就卡死 channel。该原语只对 UVM 0x7f.. VA 好用
   （我们的 report sema 一直是 host arena，工作正常）。driver 的 report-sema
   目标是 0x2_0720fff0 也好用——所以 0x2_07xx 里只有某些区域可写，
   QMD ring 和 bank 映射不可写。
4. **CPU 直写 driver bank staging 的 CPU VA**（0x7fXXYY2a0000，从段里 DMA 目标
   提取）：**SIGSEGV**——该 CPU VA 在本进程不可写（UVM 设备侧映射/PROT_NONE）。
5. **spacer 链 vs 自链 vs 无链**（QMD +0x30）：三种都非确定性，排除为根因。
   当前默认 spacer 链（CB_NOLINK/CB_SELFLINK env 可切）。
6. **+0x90 config 描述符**（driver=0x04b44808, block≤64）：曾列为嫌疑，
   填入与否未改变非确定性（根因是 bank，见 3.2）。

### 3.4 当前代码状态（target/cblaunch.cu）

**✅ 已达成（方案 D 完全版，2026-08-08 晚）**，见 §3.5。当前代码：
- ref launch = `demo<<<1,4>>>(d_out, A, B)`（CB_A/CB_B 可配，CB_KERNEL 换 demo2）
- 注入 QMD 照抄 driver 段捕获的 8 个 bank 描述符（+0xa8..+0xe4）
- 注入前 memset d_out=0 归因
- 连续 10/10 SUCCESS，demo2 5/5，多组参数全过

（以下为旧方案 3.4 记录，已被 §3.5 取代，保留作历史）
已验证：CB_NPOKE=0（不戳参数）时 **channel 存活、kernel 确实执行**
（sema=0xdead0002 ✓）——只是参数还是 driver ref demo 的旧值（out 写到 d_ref
去了，所以 out=0 FAIL 但机制成立）。

卡点：参数写不进 driver bank（CPU 直写 SIGSEGV；sema 记录戳卡死 channel）。

**另外注意**：最近一次重构后，程序在打印 "bank VA" 后、"sema =" 前无声退出——
即 CPU 直写 bank_cpu 处 SIGSEGV（符合上述 4）。这行 CPU 直写代码还在，
需要替换方案。

### 3.5 本轮新结论（2026-08-08 晚，方案 D 最终版 + 排除记录）

**方案 D 完整版 = Phase 11 成功方案**（cblaunch 当前代码）：
1. ref launch 直接 `demo<<<1,4>>>(d_out, A, B)`（A/B 由 CB_A/CB_B env 控制）
   → driver 用小 DMA 把 {d_out, A, B} 写进它自己的 bank（GPU VA <2^38，
   SM 常量域可读）。
2. 注入前 `cudaMemset(d_out,0)` —— 这样 out≠0 只能来自我们的注入 QMD，
   可归因。
3. 捕获 driver 段里 QMD 的 bank 描述符（+0xa8/+0xac/+0xb0/+0xb4/+0xd0/+0xd4/
   +0xe0/+0xe4）整体照抄进我们的 QMD。
4. 注入 QMD 复用同一 bank → SM 读到正确参数 → out = A*B+i。
- 实测：7*9→63..66、2*3→6..9、5*11→55..58、13*4→52..55、100*2→200..203 全过；
  **连续 10 次运行 10/10 SUCCESS**（每次都在干净 /tmp/nvseg-cbl 下跑）。
- **局限**：参数供应依赖 driver 的 ref launch（它必须带我们想要的参数）。
  通用化 = ref launch 用任意 A/B（env 可配）。换其他 cubin 需要 ref launch
  换成对应 kernel + 参数布局匹配（未测）。

**已实测排除（本轮）——为什么低 VA bank 走不通**：
- `mmap(0x200000) + cudaHostRegister`（低 VA <2^38，CPU 可写）：
  GPU **DMA 引擎（cudaMemcpy H2D / CE channel）能读**（实测读回 CAFE0001 ✓），
  但 **SM 常量路径（LDC c[0x0]）不能读**（LDC 返回 0，kernel 读到 0 参数 →
  STG 到 0 → illegal access）。→ 用户态 host 映射不在 SM 常量可访问域。
- `probe_lowva.cu` 探针（仓库 assembler kernel + 低 VA bank）：sema 触发、kernel
  启动，但 LDC c[0x0][0x358] 读 desc 与 c[0x0][0x380] 读参数全 0 → STG fault。
- **construct.cu 之前"成功"的真相**：bank 在 UVM arena (0x7f..)，描述符
  `cb_va>>6` 截断成 32 位后指向**低 VA 0x0db200000 一类的随机驱动内存**。
  construct kernel 只用 `LDCU.64 c[0x0][0x358]` 读 desc，之前恰读到 0
  （desc=0 恒等）→ STG 成功。**现在那个低 VA 位置内容变了（非 0）→ desc 非法
  → illegal access**。即 construct 成功是"踩中全零内存"的运气，不是可持续方案。
- driver bank 的 0x..a2a0000 与 staging 0x7f.. 的低 32 位相同（同一物理页两映射），
  但该物理页的 CPU 侧映射在本进程不可写（PROT_NONE，直写 SIGSEGV）。

**方案 A（小 DMA 写 bank）重测结论**：注入段里的小 DMA 记录（SET_OFFSET_OUT +
LINE_LENGTH + LAUNCH_DMA 0x41 + LOAD_INLINE_DATA）**能执行**（写我们自己的 UVM
arena 成功，poke check 验证参数落位），但：
- 目标 = bank staging CPU VA (0x7f..) → **静默失败**（参数没写进，channel 存活）：
  该 0x7f.. 不在我们 context 的 GPU 页表（是 driver 进程映射）。
- 目标 = bank GPU VA (0x..2a0380) → **卡死 channel**（后续记录不执行，sema 不触发）。
→ 小 DMA 只能写我们自己 context 可见的内存（UVM arena），写不进 driver 的 bank。

**下一步（换 cubin 通用化）**：构建第二个 kernel 的 cubin（如 `demo2(int*,int,int)`），
ref launch 换成它 + 注入对应代码指针，验证换 cubin 也成立。
→ **已做（2026-08-08 晚）**：`target/demo2_kernel.cu` + `demo2_kernel.cubin`（a*b−tid），
cblaunch 加 `CB_KERNEL` env，demo2 5/5 过。Phase 11 判据全部达成。

## 4. 下一步候选方案（按优先级）

### 方案 A：修 compute channel 小 DMA（首选）
driver 每次 launch 都用它写 bank staging，从我们的注入段执行却卡死。
差异只在执行上下文。排查方向：
1. **GPFIFO entry flags**：`submit_segment` 目前 `hi = (old & 0x80000300) | ...`
   继承前一条 entry 的 SYNC/PRIV/LEVEL。dump driver launch 段的 entry hi 位
   对比我们的（tracer 在注入时打印 ring slot 附近 entry 内容即可）。
   试强制 SYNC=1 / LEVEL 不同值。
2. driver 的 launch 段可能是**多个 GPFIFO entry 分开提交**（bank DMA 一个
   entry、QMD 一个 entry），dump 的 seg 文件拼接掩盖了分界——查
   doorbell 事件里 entry 数量与长度映射。
3. inline-DMA 源数据读取可能要求 pushbuffer 段在**同一 4KB 页内连续**或
   entry LENGTH 恰好覆盖。

### 方案 B：内核态/RAM 路径申请低 GPU VA 缓冲
通过进程自己的 /dev/nvidia* fd 发 RM ioctl 分配+映射一块 GPU VA < 2^38 的
sysmem（模仿 driver bank 的双重映射），CPU 可写、描述符可用。
工作量较大，对应遗留 open 项"从零 ioctl bring-up 链"。
头文件：`/usr/src/nvidia-580.65.06/common/inc/nv-ioctl*.h`。
先抓 driver 分配 bank 时的 ioctl 序列（NVTRACE ioctl 日志过滤 ALLOC/MAP）
照抄参数。

### 方案 C：kernel 不读 c[0x0]（绕过 bank）
把参数烧进 SASS 立即数（Phase 10 风格）。对任意 cubin 不通用，但可以：
- 用仓库 assembler 写一个 trampoline kernel：立即数版 out_ptr/a/b，
  验证"无 bank 依赖的真实计算"全流程。
- 或对 cubin 做二进制 patch：把 LDC c[0x0][0x380+x] 替换为 MOV32I 立即数
  （需处理调度 bracket，工作量中等）。

### 方案 D：劫持 driver 的下一次 launch
不自己写参数——让 driver 的 ref launch 就带我们的参数（demo(d_out,7,9)
正常 launch），同时注入 QMD 复用同一份 bank 再跑一遍我们提取的代码。
参数天然正确，无需写 bank。**这是最便宜的验证路径**：把 ref launch 改成
`demo<<<1,4>>>(d_out, 7, 9)`，注入 QMD 用同一 bank VA 再 launch 一次，
out 应得到两遍 63..66。可立刻证明"复用 driver bank + 自己 QMD"端到端正确，
把问题缩小到只剩"如何供应自定义参数"。

## 5. 其他已知坑（血泪，勿再踩）

- **GPFIFO entry1 [30:10] = LENGTH(dwords)**，submit_segment 已修
  （`(old&0x80000300) | ((addr>>32)&0xff) | ((len/4)<<10)`），改提交路径别回退。
- **QMD +0x3c = semaphore VA 原始低 32 位**（不是 >>8）。
- **inline QMD staging 地址必须 < 2^40**（记录 addr 字段 = VA>>8 仅 32 位）→
  复用 driver QMD ring 下一槽（c[0x0][0x148]+0x800；QMD sema 放槽内 +0x400）。
- **SASS 调度纪律**：S2R/LDC 是不定周期指令，结果必须配 scoreboard
  （wr=SBn + 消费端 req 等待），否则野指针 fault。/tmp/bisect_*.bin 里
  D3/E2/F1 等 fault 有部分是我手写 bracket 太松，不是构造环境的问题。
- **寄存器窗口规则**：每 8 寄存器窗口顶部 2 个保留，可用 [0, regcount-2)；
  越界 fault 报 ILLEGAL_INSTRUCTION（notes/sm90/arch/sm120_findings.md #10）。
- 编译错误会被 `2>&1 | grep error` 吞掉导致跑旧二进制——构建后务必确认
  BUILD_OK 或检查二进制时间戳（本 session 踩过两次）。
- cudaMalloc 在 UVM 下返回 0x7f.. host 段 VA：QMD staging/semaphore 等
  32-bit 字段放不下，但 STG/LDG 全 64 位地址没问题。

## 6. 文件清单

| 文件 | 状态 |
|---|---|
| `target/cblaunch.cu` | Phase 11 主 target（**达成**：方案 D 完全版，10/10 SUCCESS + 换 cubin 通用化） |
| `target/construct.cu` | Phase 10 手写 SASS 从零 launch（⚠️ 现在运行 FAIL，原因见 §3.5：UVM bank 截断运气失效） |
| `target/cbank120.cu` / `cbank120_sweep.cu` | c[0x0] 直读探针（Phase 9/9补，完成） |
| `target/demo_kernel.cu` + `demo_kernel.cubin` | 对照 kernel `extern "C" demo(int*,int,int)` |
| `target/demo2_kernel.cu` + `demo2_kernel.cubin` | 换 cubin 验证 `demo2(int*,int,int)` = a*b−tid（5/5 过） |
| `target/probe_lowva.cu` | 低 VA bank 探针（仓库 assembler kernel；证明 SM 常量路径读不到低 VA bank） |
| `tools/extract_cubin.py` | cubin .text 提取 + regcount（好用） |
| `tools/gen_construct_kernel.py` / `gen_param_test_kernel.py` / `gen_probe_regs_kernel.py` / `gen_demo_clone_kernel.py` / `gen_param_read_kernel.py` | assembler kernel 生成器 |
| `src/doorbell_trap.c` | 写陷阱+注入器（submit_segment/nvtrace_inject_raw） |
| `src/nvtrace.c` | nvtrace_mark 分发（inject / injectraw） |
| `/tmp/bisect_*.bin` | 排障用 kernel bins（E0/E1 过；G1 过；F1/D3/E2 fault=bracket 问题；G3 R15 未验） |
| `/tmp/rawseg.bin` | cblaunch 最近一次注入段 |
| `NOTES.md` | Phase 4-11 结论（Phase 9 映射段已修正恒等映射，Phase 11 已写） |

## 7. 成功判据（Phase 11 完成标准）

cblaunch 连续 10 次运行全部 `SUCCESS`（out = 63 64 65 66，sema = 0xdead0002），
且换用其他 cubin/kernel 参数也成立（参数供应方案通用化）。

→ **已达成（2026-08-08 晚）**：
- demo 连续 10/10 SUCCESS（out=63..66，sema=0xdead0002）
- demo2（`CB_KERNEL=demo2`）连续 5/5 SUCCESS（out=a*b−tid）
- 参数通用化：CB_A/CB_B 多组值（2×3、5×11、13×4、100×2、6×7、3×8）全过
