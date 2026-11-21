# B200 tcgen05.mma.ws：CUDA/PTX 行为构造（2026-11-17）

<!-- notes-status -->
**Status:** active
**Evidence:** sm100-silicon
**Tier confidence:** medium
**Last verified:** 2026-11-21
**Probe:** linked in the construction and reproduction sections
**Open items:** none
**Audit:** B200 output-validated measurements; primary records linked below

## Conclusion

**Evidence:** sm100-silicon (Modal NVIDIA B200, cc 10.0)
**Probe:** `tests/tcgen05_ws_behavior.cu`
**Runner:** `tools/modal_tcgen05_ws.py`
**Result:** 144 configurations × 3 repetitions = 432 launches, all pass.

本轮只确认 dense BF16×BF16→FP32、K16、1CTA、A/B shared 的指令行为。
完全通过 CUDA + inline PTX 构造，由 nvcc 12.8.93 编译为 sm_100a；没有手写
SASS、assembler、lift 或 patch。SASS 只用于只读核对编译结果。

原始 stdout、编译器/设备信息、源文件 SHA256、UTCHMMA 反汇编摘录和 Modal
run URL 保存在 [原始结果](data/tcgen05_ws_behavior_20261117.json.gz)。完整反汇编
由 runner 写到指定 output 目录（本次 `/tmp/tcgen05-ws-validated/ws.sass`）。

## Evidence

## Test construction

一个 CTA、128 threads；warp 0 集体申请 256 columns TMEM，只有 thread 0
发射 MMA。四个 warp 初始化并读取各自 TMEM chunk。整个 allocation 预先写
FP32 7，MMA 完成后读取全部 128×256 个值：既检查每个输出元素，也检查输出
footprint 外的 7 未被改写。

Shared A/B 使用 K-major、无 swizzle 布局。按 BF16 元素计的地址公式为：

```
offset(mn,k) = (mn/8)*128 + (k/8)*64 + (mn%8)*8 + k%8
```

对应 descriptor：LBO=128 bytes、SBO=256 bytes、fixed bits=1<<46。
这组参数与这个显式的 8×8 atom 排列共同使用，不能直接拿旧探针不同的
LBO/SBO 与之混搭。

A/B 经 shared async-proxy fence 发布；TMEM 初始化完成后 CTA 同步并执行
`tcgen05.fence::after_thread_sync`。所有 MMA 在一个 completion epoch 中执行，
由一次 commit 和 init_count=1 的 mbarrier 收束，再经 CTA 同步、tcgen05 fence
以及 LDTM+wait 读取。每次 launch 独立初始化、分配和释放。

测试矩阵：M={32,64,128} × N={64,128,256}，每个 shape 两套输入：

- 行列标签：A[m,0]=m+1、A[m,1]=1，其余为0；B[0,n]=256、B[1,n]=n+1，
  其余为0。基础乘积为 `256*(m+1)+(n+1)`，可以辨认行列映射。
- 非均匀带符号输入：A[m,k]=(3m+5k)%7−3；B[k,n]=(5n+3k)%9−4，检查完整 K
  归约，防止只有两个非零 K 的标签测试漏掉问题。

四块独立 B shared 区分别为上述 B 的1/2/3/4倍；CPU 参考首先将输入舍入至
实际 BF16，再求 FP32 乘积。所有结果可以精确比较，无容差。

| mode | 指令序列 | 参考结果（Pi=A×Bi） |
|---:|---|---|
| 0 | discard，enable-input-d=false | P0 |
| 1 | discard，enable-input-d=true，初始D=7 | P0+7 |
| 2 | overwrite，再accumulate | 2P0 |
| 3–6 | 单独对b0/b1/b2/b3：fill覆盖写、use累加、lastuse累加 | 3Pi |
| 7 | fill b0→b3、use b0→b3、lastuse b3→b0 | 3(P0+P1+P2+P3) |

每次 use/lastuse 都有前置有效 fill，B 数据与 descriptor 保持不变。
未测试 use-after-lastuse 或运行中改写 collector 对应的 B。

## Verified output mapping

设 `w=threadIdx.x/32`、`l=threadIdx.x%32`，`c` 为普通
`tcgen05.ld.32x32b.x1` 相对 TMEM base 的 column offset。

| M | 每个 chunk 的有效列数 W | 逻辑 m | 逻辑 n |
|---:|---:|---:|---:|
| 128 | N | 32w+l | c |
| 64 | N/2 | 32(w%2)+l | (w/2)*(N/2)+c |
| 32 | N/4 | l | w*(N/4)+c |

整数除法。四个 warp 都向 LDTM 传入相同 `base+c`，warp rank 决定可访问的
32-row chunk。`c>=W` 的值仍为7。

因此 M64 WS 的逻辑输出排列为 `[[warp0,warp2],[warp1,warp3]]`；M32 为
`[warp0,warp1,warp2,warp3]` 横向分割 N；M128 沿 M 分成四份。
这与 PTX Layout E/G/D 一致，且已由非均匀数据逐元素确认。参考：
[NVIDIA PTX 8.7 datapath organization](https://docs.nvidia.com/cuda/archive/12.8.1/parallel-thread-execution/index.html#tcgen05-data-path-layout)。

这是**逻辑输出到 TMEM chunk 的映射**。不能仅据此把四个 chunk 等同于四个
特定物理计算阵列，或断言 shared 具有对应的广播网络。

## Compiler mapping and collector evidence

只读 cuobjdump 核对：

| PTX | 生成的 SASS B operand modifier |
|---|---|
| b0::discard | 无KEEP/REUSE |
| b0::fill | B_KEEP |
| b0::use | B_REUSE.B_KEEP |
| b0::lastuse | B_REUSE |
| b1/b2/b3 | 额外BUFFER1/2/3 |

全部生成 `UTCHMMA.WS gdesc[…], gdesc[…], …`，覆盖写/累加分别为 !UPT/UPT
或对应运行时 uniform predicate。

单 buffer 和四 buffer 同时存活的合法交错序列均数值正确。这证明指令组合及
buffer选择可用，**尚不证明每次use真的命中collector、四个物理buffer容量，
或省去多少shared读流量**。PTX允许collector reuse为机会性优化；验证缓存
收益需独立的流量/竞争/吞吐实验。


## History / retracted hypotheses

B200 measurements collected in November 2026; this edition retains current findings and primary evidence.
