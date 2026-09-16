# B300 / sm_103 寄存器文件 bank 与读取带宽

**状态：** Modal B300 实测，2026-09-17。
**探针：** `tests/asm_construct/probe_sm100_rf_banks_modal.py --target b300`。
**方法：** 与 `notes/sm100/rf_bank_probe.md` 的 B200 实验完全相同。

## 结论

B300 与 B200 的结果逐项一致：scalar GPR collector 暴露两个由寄存器编号
奇偶选择的 bank，每个 bank 每周期只能接受一个独立的 warp-wide 32-bit row
address。没有观察到四个可独立服务的 mod-4 bank。

```text
bank = register_number & 1
read_cycles = max(even_rows, odd_rows)
instruction_cycles = max(pipe_admission_floor, read_cycles)
```

这里的 1R 是指架构可见的 full-warp row service。内部 SRAM 可以有更多物理
分片，但这些分片没有形成普通 SASS 可独立利用的 mod-4 bank。

## 两源 mod-4 矩阵

FADD 使用 `RZ` destination、无 reuse，行列分别是 Ra/Rb 的寄存器编号 mod 4：

```text
        Rb=0  Rb=1  Rb=2  Rb=3
Ra=0    2.000 1.000 2.000 1.000
Ra=1    1.000 2.000 1.000 2.000
Ra=2    2.000 1.000 2.000 1.000
Ra=3    1.000 2.000 1.000 2.000
```

汇总：same mod-4 = 2.000，same parity/different mod-4 = 2.000，different
parity = 1.000。NOP control = 1.000。这个棋盘格直接给出 parity bank mapping
和每 bank 有效 1R。

HADD2 的全部格子均为 2.000，说明其约 0.5-inst/cycle packed-FP admission
floor 隐藏了两源 RF 差异，不能单独用来判断 bank 数。

## 三源 FFMA 与 mod-4 排除实验

```text
sources                         cycles/instruction
(0,1,2) = 2E+1O                      2.000
(0,2,0), all operand permutations     3.000
(0,2,2), all operand permutations     3.000
(0,0,0), (2,2,2)                     3.000
odd-side equivalents                 3.000
```

如果 `0 mod 4` 和 `2 mod 4` 是独立的 1R bank，`(0,2,0)` 的最大单 bank
需求只有 2，应为两周期；实测为三周期并与 `(0,0,0)` 相同。因此 bank hash
只取最低一位，而不是最低两位。

## 显式 reuse

第六调度字段对 reusable math class 是 source reuse mask；no-reuse 使用
`[7:7:{}:1:0]`，reuse A/B/C 分别使用尾值 1/2/4。

```text
FADD 2E:       no reuse 2, reuse A 1, reuse C 1
FADD E+O:      no reuse 1
FFMA 3E:       no reuse 3, reuse any one 2, reuse two/all 1
FFMA 2E+1O:    no reuse 2, reuse one E 1, reuse O 2
FFMA2 3 pairs: no reuse 3, reuse one pair 2
```

FFMA 2E+1O 是最直接的端口对照：消掉一个 even request 后剩余 E+O，可在
一周期完成；消掉 odd 后剩余 2E，仍需两周期。

## FFMA2 / `fma.f32x2`

三个 64-bit source pair 分别向 even/odd bank 各提出三个 row request。pair
起始寄存器全为 `0 mod 4`、全为 `2 mod 4`、以及所有 0/2 的 2+1 排列，均为
3.000 cycles/instruction。四个 mod-4 bank 模型预测混排应降至 2，实测没有。

reuse 一个 pair 后降至 2.000；继续 reuse 仍保持 2.000，表明 FFMA2 另有
约两周期的 pipe/admission floor，与 B200 相同。

## sm_103 assembler bring-up

`tools/parse_sm100.py` 现在接受 `--instructions` / `--latencies`，可从新增 dump
生成 `sm103.json`；解析验证得到 1368 variants、259 mnemonics，并通过
`validation OK`。汇编器 sm103 配置采用：

```text
default cdesc = c[0][0x358]
parameter base = 0x380
ELF e_flags = 0x06006702
OSABI / ABI version = 0x41 / 0x08
```

自产 sm103 cubin 已在 Modal B300 上完成最小加载与执行验证，随后用于以上全部
实验。
