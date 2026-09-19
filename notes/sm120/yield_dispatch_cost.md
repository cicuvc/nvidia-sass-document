# yield 调度位的发射成本 (sm_120 / GB202)

CS2R 窗口实测(RTX 5090, assembler dialect, 全部 `[wr:rd:{req}:stall:yield:batch_t]` 中只动 yield/batch_t 位)。

## 结论:yield = 强制 warp 切换提示,切换动作本身占 1 拍

模型(与全部数据自洽):yield 位提示调度器"下一条指令切换到别的
warp";**一次 warp 切换消耗 1 个发射周期**(死拍,任何 warp 都用不
了)。solo warp 时切换出去没有别人可切,下一拍再切回来,净成本同样是
1 拍 → 速率减半。

### Solo 速率(每 SMSP 单 warp 流)

| 指令 | `[1:0]` | `[1:1]` yield | `[1:0:7]` reuse |
|---|---|---|---|
| NOP(无操作数) | 1.098 | 2.016 | 非法组合 |
| MOV(1 源) | 1.098 | 2.016 | 1.098 |
| FADD(2 源) | 1.098 | 2.016 | 1.098 |
| FFMA(3 源) | 2.012 | 2.016 | **1.098** |
| IADD3 | 2.0(数据通路瓶颈) | 2.0 | 2.0 |

- NOP 无操作数、reuse cache 无从失效,yield 照样 +1 拍 → yield 的固有
  成本就是切换那一拍,**与 reuse 无关**。
- FFMA 的 `[1:0]`=2.0 是三源操作数采集受限(reuse 位补齐回 1.0),
  与 yield 无关;MOV/FADD(≤2 源)不需要 reuse。
- **yield + batch_t=7 是非法编码**(FFMA `[1:1:7]` 触发
  `ILLEGAL_INSTR_ENCODING_SASS_ONLY_ERROR`)→ 间接证实 yield 会使
  operand reuse cache 失效(硬件不允许在 yield 指令上设置 reuse 位)。
- stall 字段字面生效:stall=5 → 每指令 ~5 拍。

### 双 warp(同 subcore w0+w4,FFMA,窗口化)

| 配置 | w0 | w4 | 合计 |
|---|---|---|---|
| 都 no-yield | 0.482 | 0.479 | 0.96/clk(公平二分) |
| 都 yield | 0.248 | 0.273 | 0.52/clk |
| w0 yield / w4 no-yield | 0.326 | 0.877 | ~1.2(峰值) |
| w0 no-yield / w4 yield | 0.865 | 0.330 | ~1.2(峰值) |

- 都 yield:每条指令后强制切换 → 每拍必死 → 合计砍半,**sibling 填不进
  切换死拍**。
- 非对称:no-yield 的 warp 保持近满速(0.87),yield 方吃切换成本
  (0.33) → 死拍跟随"切换事件",可被不切换的一方利用。
- 异 subcore(w0+w1)各跑各的,yield 方各自减半,互不影响。

## 与 sm_89 (Ada) 对比

yield 行为两代一致(solo 减半、切换死拍不可被同 subcore sibling 利用)。
差异:

- sm_89 上无 yield 的 int_pipe 流会**锁死**同 subcore 调度(sibling 连
  NOP 都进不来);GB202 无此现象——iadd3×2 无 yield 时正常交叠
  (w0=0.497, w4=0.25)。
- GB202 同管双 FFMA 公平二分(0.48/0.48);sm_89 偏向低 warp 号。
- GB202 的 FFMA 满速额外依赖 reuse 位(sm_89 上 `[1:0]` vs `[1:0:7]`
  未单独测,待补)。

## NCU 尝试(教训)

试图用 ncu 的 `smsp__issue_active` / `cycles_active` 验证:全 SM 满载或
全 warp 同跑时,elapsed/active 被启动与收尾开销淹没(body 只占 ~20%),
两种 bracket 看不出差别;`issue_active.max` 返回垃圾百分比。这类一拍级
的调度效应只能用 CS2R 窗口测,NCU 的聚合计数器分辨率不够。

复现:`/tmp/opencode/yield120.py`(local),关键 fixture 是 S2R 要 claim
barrier(`[5:7:{}:5:1]`)且消费者 req{5},否则 warp 选择静默失效。

