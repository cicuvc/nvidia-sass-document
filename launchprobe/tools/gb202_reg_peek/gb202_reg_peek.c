// SPDX-License-Identifier: GPL-2.0-only
//
// One-shot, read-only GB202 feature-cluster sampler.
//
// The offsets are the Ada speed-select candidates proven by gpu-unlock-ada.
// This module intentionally reads only these five dwords: no BAR scan, no
// register writes, no PCI config changes, no reset, and no firmware load.

#include <linux/init.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/pci.h>

#define NVIDIA_VENDOR_ID 0x10de
#define GB202_RTX_5090_DEVICE_ID 0x2b85

#define GU_FEAT_PLM_OFFSET 0x00823804u
#define GU_FEAT_READOUT_0_OFFSET 0x00823814u
#define GU_FEAT_READOUT_1_OFFSET 0x00823818u
#define GU_FEAT_SS0_OFFSET 0x0082381cu
#define GU_FEAT_SS1_OFFSET 0x00823820u

static char *target;
module_param(target, charp, 0444);
MODULE_PARM_DESC(target, "exact PCI address, e.g. 0000:01:00.0; required");

struct peek_reg {
	const char *name;
	u32 offset;
	u32 value;
};

static struct peek_reg registers[] = {
	{ "FEAT_OVR_PLM", GU_FEAT_PLM_OFFSET },
	{ "FEAT_READOUT_0", GU_FEAT_READOUT_0_OFFSET },
	{ "FEAT_READOUT_1", GU_FEAT_READOUT_1_OFFSET },
	{ "FEAT_OVR_SM_SPEED_SELECT_SS0", GU_FEAT_SS0_OFFSET },
	{ "FEAT_OVR_SM_SPEED_SELECT_1_SS1", GU_FEAT_SS1_OFFSET },
};

static bool inaccessible(u32 value)
{
	return value == ~0u || (value & 0xffff0000u) == 0xbadf0000u;
}

static void decode_readout(const char *name, u32 value, unsigned int width)
{
	char fields[96];
	unsigned int i, pos = 0;
	u32 mask = width == 3 ? 7u : 15u;
	unsigned int count = width == 3 ? 9u : 8u;

	fields[0] = '\0';
	for (i = 0; i < count; ++i)
		pos += scnprintf(fields + pos, sizeof(fields) - pos, " %u",
				 (value >> (width * i)) & mask);
	pr_info("gb202_reg_peek: %s fields:%s\n", name, fields);
}

static int __init gb202_reg_peek_init(void)
{
	struct pci_dev *pdev;
	void __iomem *bar;
	resource_size_t bar_len;
	unsigned int domain, bus, slot, func, i;
	bool valid = true;

	if (!target || !*target) {
		pr_err("gb202_reg_peek: target= is required\n");
		return -EINVAL;
	}
	if (sscanf(target, "%x:%x:%x.%x", &domain, &bus, &slot, &func) != 4 ||
	    slot > 0x1f || func > 7) {
		pr_err("gb202_reg_peek: bad target %s\n", target);
		return -EINVAL;
	}

	pdev = pci_get_domain_bus_and_slot(domain, bus, PCI_DEVFN(slot, func));
	if (!pdev)
		return -ENODEV;
	if (pdev->vendor != NVIDIA_VENDOR_ID ||
	    pdev->device != GB202_RTX_5090_DEVICE_ID) {
		pr_err("gb202_reg_peek: expected 10de:2b85, got %04x:%04x\n",
		       pdev->vendor, pdev->device);
		pci_dev_put(pdev);
		return -ENODEV;
	}
	if (!(pci_resource_flags(pdev, 0) & IORESOURCE_MEM)) {
		pr_err("gb202_reg_peek: BAR0 is not memory\n");
		pci_dev_put(pdev);
		return -ENODEV;
	}
	bar_len = pci_resource_len(pdev, 0);
	bar = pci_iomap(pdev, 0, 0);
	if (!bar) {
		pr_err("gb202_reg_peek: BAR0 map failed\n");
		pci_dev_put(pdev);
		return -ENODEV;
	}

	pr_info("gb202_reg_peek: target=%s BAR0 length=%#llx\n",
		target, (unsigned long long)bar_len);
	for (i = 0; i < ARRAY_SIZE(registers); ++i) {
		struct peek_reg *reg = &registers[i];

		if ((resource_size_t)reg->offset > bar_len - sizeof(u32)) {
			valid = false;
			pr_err("gb202_reg_peek: offset %#x outside BAR0\n",
			       reg->offset);
			break;
		}
		reg->value = ioread32(bar + reg->offset);
		pr_info("gb202_reg_peek: %#010x %-31s = %#010x\n",
			reg->offset, reg->name, reg->value);
		if (inaccessible(reg->value)) {
			valid = false;
			pr_err("gb202_reg_peek: inaccessible value, stopping\n");
			break;
		}
	}

	if (valid) {
		decode_readout("FEAT_READOUT_1 (3-bit, 0=full)",
			       registers[2].value, 3);
		decode_readout("SS0 nibbles (bit3=enable, bits2:0=value)",
			       registers[3].value, 4);
		pr_info("gb202_reg_peek: SS1=%#x (low nibble=%#x)\n",
			registers[4].value, registers[4].value & 0xfu);
	}

	pci_iounmap(pdev, bar);
	pci_dev_put(pdev);
	return 0;
}

static void __exit gb202_reg_peek_exit(void) { }

module_init(gb202_reg_peek_init);
module_exit(gb202_reg_peek_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("One-shot read-only GB202 feature-cluster sampler");
MODULE_VERSION("0.1.0");
