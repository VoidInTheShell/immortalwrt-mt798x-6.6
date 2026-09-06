# R3 Mini 内核源代码预检

检查时间（本机 epoch）：`1788695137.200`

这份检查只展开并检查 Linux 6.6.133 源码与 OpenWrt 内核补丁栈，没有调用固件、内核或目标架构程序编译。

## 输入与可复现路径

- 源码归档：`dl/linux-6.6.133.tar.xz`
- 归档 SHA-256：`e6da5b8a3097a46df0e86cd72f3c4f4694652e79acf06673736af3255398f115`
- 检查树：`.r3mini-checks/linux-6.6.133`
- 是否复用已标记展开树：`是`
- 本次检查耗时：`0.403` 秒（不含之后真正编译）
- 补丁顺序与 `include/quilt.mk` / `scripts/patch-kernel.sh` 一致：`generic-backport/` → `generic/`（本仓库为 `pending-6.6`）→ `generic-hack/` → `platform/`（`mediatek/patches-6.6`）。

## 覆盖文件

| 覆盖目录 | 文件数 |
|---|---:|
| `target/linux/generic/files` | 84 |
| `target/linux/mediatek/files-6.6` | 207 |

## 补丁结果

| 阶段 | 总数 | 成功 | 失败 | 有偏移/模糊 |
|---|---:|---:|---:|---:|
| `generic-backport` | 420 | 420 | 0 | 1 |
| `generic-pending` | 154 | 154 | 0 | 1 |
| `generic-hack` | 52 | 52 | 0 | 2 |
| `mediatek-platform` | 291 | 291 | 0 | 121 |
| 合计 | 917 | 917 | 0 | 125 |

全部列出的补丁均以 `patch -f -p1 --batch --no-backup-if-mismatch` 成功应用；其中 `125` 个补丁报告了上下文偏移或 fuzz。它们没有被当作失败吞掉，但仍应在真正 kernel prepare/编译中复核。

## PWM、设备树与 HNAT 源码检查

- `drivers/hwmon/pwm-fan.c` 存在：`True`；保留 thermal cooling-device 注册：`True`；支持 `mediatek,initial-pwm-zero`：`True`；该属性会把初始状态设为 0：`True`。
- R3 Mini DTS 存在 pwm-fan 且有 cooling-levels：`True` / `True`；R3 Mini 误用 WH3000Pro 初始零输出属性：`False`。
- WH3000Pro DTS 单独声明初始零输出属性：`True`。
- HNAT 读取 `mtketh-wan`：`True`；把 DT 名称复制到 WAN 字段：`True`；WAN 字段硬编码为 eth0：`False`。其余 datapath 中仍有 `2` 个 eth0/eth1 字面量，这是旧驱动端口分类逻辑，不能等同于 WAN 选择字段已经可配置。
- 补丁残留 `.rej` 文件数：`0`；`.orig` 文件数：`0`。

## BPF、daed 与私有硬件栈配置前置条件

```json
{
  "root_config": {
    "target": "\"DEVICE_bananapi_bpi-r3-mini\"",
    "subtarget": "\"filogic\"",
    "rootfs_partsize": "2048",
    "bpf_toolchain_host": "y",
    "kernel_debug_info_btf_request": "y",
    "kernel_cgroups_request": "y",
    "kernel_cgroup_bpf_request": "y"
  },
  "generic_kernel_base": {
    "BPF": {
      "value": "y",
      "expected_base": "y"
    },
    "BPF_SYSCALL": {
      "value": "y",
      "expected_base": "y"
    },
    "BPF_JIT": {
      "value": "y",
      "expected_base": "y"
    }
  },
  "base_fragments_before_root_config_and_package_selections": {
    "CGROUPS": "n",
    "NET_INGRESS": "y",
    "NET_EGRESS": "y",
    "NETFILTER": "y",
    "NF_CONNTRACK": "y",
    "NF_FLOW_TABLE": "y",
    "MTK_THERMAL": "y",
    "MTK_LVTS_THERMAL": "y",
    "NET_MEDIATEK_SOC": "y",
    "NET_MEDIATEK_SOC_WED": "y"
  },
  "daed_kernel_requests": {
    "DEBUG_INFO": "y",
    "DEBUG_INFO_BTF": "y",
    "BPF_EVENTS": "y",
    "CGROUP_BPF": "y",
    "BPF_STREAM_PARSER": "y",
    "XDP_SOCKETS": "y"
  },
  "private_hardware_package_selection": {
    "CONFIG_PACKAGE_kmod-mediatek_hnat": "y",
    "CONFIG_PACKAGE_kmod-conninfra": "y",
    "CONFIG_PACKAGE_kmod-mt_wifi": "y",
    "CONFIG_PACKAGE_kmod-warp": "y",
    "CONFIG_PACKAGE_luci-app-turboacc-mtk": "y"
  },
  "interpretation": "The generic 6.6 fragment supplies BPF/JIT/BPF_SYSCALL; the filogic fragment supplies the MediaTek/WED/netfilter base.  CGROUP_BPF, NET_CLS_BPF/ACT, ingress and related options may be dependency or root CONFIG_KERNEL_* results, so their final values must be checked in the generated build_dir kernel .config after a real prepare step."
}
```

通用 6.6 fragment 提供 BPF/JIT/BPF_SYSCALL，filogic fragment 提供 MediaTek/WED/netfilter 基础项；CGROUP_BPF、NET_CLS_BPF/ACT、ingress 及其依赖项可能由根配置或包依赖在内核配置阶段补入。daed 所需的 DEBUG_INFO/BTF/BPF_EVENTS、stream parser、XDP 等由根 `.config` 的 `CONFIG_KERNEL_*` 请求交给 OpenWrt 内核配置阶段。这里检查了 fragment 和请求，不能代替真正 prepare 后读取 `build_dir/target-*/linux-*/linux-6.6.133/.config`。

## 结论

- 源码补丁栈：`通过`。
- 本检查没有编译固件、内核、daed 或 BPF，也没有执行任何 ARM/aarch64 目标文件；因此不会伪造编译通过或运行时硬件加速结论。
- 重新执行：`python3 scripts/r3mini-kernel-check.py --fresh`；不加 `--fresh` 时只复用归档、补丁栈和覆盖文件指纹一致的标记树。

机器可读的逐补丁记录保存在 `.r3mini-checks/patch-results.jsonl`，配置与源检查保存在 `.r3mini-checks/kernel-check.json`。
