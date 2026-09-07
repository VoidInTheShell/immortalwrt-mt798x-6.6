#include <linux/version.h>
#include <linux/module.h>
#include <linux/types.h>
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/err.h>
#include <linux/slab.h>
#include <linux/of.h>
#include <asm/io.h>
#include <linux/mtd/mtd.h>
#include <linux/mtd/map.h>
#include <linux/mtd/concat.h>
#include <linux/mtd/partitions.h>
#if defined (CONFIG_MIPS)
#include <asm/addrspace.h>
#endif

int mt_mtd_write_nm_wifi(char *name, loff_t to, size_t len, const u_char *buf)
{
	int ret = -1;
	size_t rdlen, wrlen;
	struct mtd_info *mtd;
	struct erase_info ei;
	u_char *bak = NULL;

	mtd = get_mtd_device_nm("Factory");

	if (IS_ERR(mtd))
		mtd = get_mtd_device_nm("factory");

	if (IS_ERR(mtd))
		return -1;

	if (len > mtd->erasesize) {
		put_mtd_device(mtd);
		return -E2BIG;
	}

	bak = kmalloc(mtd->erasesize, GFP_KERNEL);
	if (bak == NULL) {
		put_mtd_device(mtd);
		return -ENOMEM;
	}

	ret = mtd_read(mtd, 0, mtd->erasesize, &rdlen, bak);

	if (ret != 0) {
		put_mtd_device(mtd);
		kfree(bak);
		return ret;
	}

	if (rdlen != mtd->erasesize)
		printk("warning: ra_mtd_write: rdlen is not equal to erasesize\n");

	memcpy(bak + to, buf, len);

#if (LINUX_VERSION_CODE < KERNEL_VERSION(4, 19, 0))
	ei.mtd = mtd;
	ei.callback = NULL;
	ei.priv = 0;
#endif
	ei.addr = 0;
	ei.len = mtd->erasesize;
	ret = mtd_erase(mtd, &ei);

	if (ret != 0) {
		put_mtd_device(mtd);
		kfree(bak);
		return ret;
	}

	ret = mtd_write(mtd, 0, mtd->erasesize, &wrlen, bak);



	put_mtd_device(mtd);
	kfree(bak);
	return ret;
}
EXPORT_SYMBOL(mt_mtd_write_nm_wifi);

/* R3 Mini ships its board EEPROM in DT, not a Factory MTD partition.
 * Keep real Factory MTD reads preferred and never write this fallback back.
 * The vendor driver's 0x5000-byte container includes optional calibration
 * storage; DT supplies only the 0x1000-byte base EEPROM. Its indication bits
 * leave pre-cal disabled, so the driver retains its runtime/EFUSE calibration.
 */
static int mt_wifi_read_r3mini_eeprom(loff_t from, size_t len, u_char *buf)
{
	struct device_node *np;
	const u8 *data;
	int size, ret = -ENODATA;
	size_t available;

	if (!of_machine_is_compatible("bananapi,bpi-r3-mini"))
		return -ENODEV;

	np = of_find_node_by_path("/soc/wifi@18000000");
	if (!np)
		return -ENODEV;

	data = of_get_property(np, "mediatek,eeprom-data", &size);
	if (!data || size != 0x1000 || data[0] != 0x86 || data[1] != 0x79)
		goto out;

	/* Do not manufacture missing pre-cal data or silently truncate reads. */
	if (from < 0 || from >= size) {
		ret = -ERANGE;
		goto out;
	}
	available = size - from;
	if (len > available && (from != 0 || len != 0x5000)) {
		ret = -ERANGE;
		goto out;
	}
	if (len > available && data[0x19a])
		goto out;

	memset(buf, 0, len);
	memcpy(buf, data + from, min(len, available));
	pr_info_once("mt_wifi: using R3 Mini device-tree base EEPROM (read-only)\n");
	ret = 0;
out:
	of_node_put(np);
	return ret;
}

int mt_mtd_read_nm_wifi(char *name, loff_t from, size_t len, u_char *buf)
{
	int ret;
	size_t rdlen;
	struct mtd_info *mtd;

	mtd = get_mtd_device_nm("Factory");

        if (IS_ERR(mtd))
                mtd = get_mtd_device_nm("factory");

	if (IS_ERR(mtd))
		return mt_wifi_read_r3mini_eeprom(from, len, buf);

	ret = mtd_read(mtd, from, len, &rdlen, buf);

	if (rdlen != len)
			printk("warning: ra_mtd_read_nm: rdlen is not equal to len\n");

	put_mtd_device(mtd);

	return ret;
}
EXPORT_SYMBOL(mt_mtd_read_nm_wifi);
