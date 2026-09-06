# BPI-R3 Mini 硬件基线实施记录

## 已完成的实现

准确的包名和 Kconfig 选择记录在 [`hardware-required.config`](hardware-required.config) 中，已由根迁移脚本应用到完整配置并验证。最终运行约束和后续修复以 [implementation.md](implementation.md) 为准。

- R3 Mini 的镜像默认包由不存在的 `kmod-mt7915e`、`kmod-mt7986-firmware`、`mt7986-wo-firmware` 换成仓库中真实存在且互相配套的 `kmod-conninfra`、`kmod-mt_wifi`、`kmod-warp`、`wifi-dats`、`mtwifi-cfg`。`kmod-phy-airoha-en8811h`、USB、文件系统和自动挂载包继续保留。
- HNAT 使用内核包 `kmod-mediatek_hnat`，配置页和统计页使用 `luci-app-turboacc-mtk`。这个页面已经提供 HNAT 开关、IPv4/IPv6 设置、绑定速率以及每个 PPE 的统计展示；Makefile 现在显式依赖 HNAT 驱动，单独选择页面时不会产生“只有管理页、没有驱动”的不完整固件。
- Wi-Fi 使用 `kmod-conninfra`、`kmod-mt_wifi`、`wifi-dats`、`mtwifi-cfg` 和 `luci-app-mtwifi-cfg`。片段固定第一张卡为 MT7986、flash EEPROM、AX4200、`mt7976`，打开 MT7986 新固件、二进制固件加载、WHNAT 和 WARP 相关功能。旧的 `luci-app-mtk` 和 `wifi-profile` 没有选入，以免两个 `/admin/network/wifi`/`/sbin/wifi` 配置拥有者相互覆盖；`mtwifi-cfg` 是当前唯一的 Wi-Fi 配置执行路径。
- WARP 配置的 `WARP_VERSION` 和 `WARP_CHIPSET` 对 R3 Mini 默认到 MT7986。`WARP_NEW_FW` 原来虽在 `config.in` 中存在，却没有进入 Makefile 的 `PKG_KCONFIG`，因此不会稳定传给编译和安装阶段；现在已加入传递列表，`CONFIG_WARP_NEW_FW=y` 会实际安装 MT7986 的新版 WO 固件。
- 硬件队列工具选入 `mtkhqos_util`，默认 `enabled=0,hqos=0`，不管理 HNAT 总开关。仅另保留 QoSmate，两者禁止同时启用。`luci-app-eqos-mtk` 虽带 MTK 名称，但实际为软件 EQOS，且启停会清空共享 mangle PREROUTING，已取消选择。`mtk-smp` 保留用于 MT7986 IRQ/RPS 绑定。

## HNAT WAN/LAN 处理

[`mt7986a.dtsi`](../../target/linux/mediatek/files-6.6/arch/arm64/boot/dts/mediatek/mt7986a.dtsi) 已经把 HNAT 节点声明为 `mtketh-wan = "eth1"`、`mtketh-lan = "eth0"`。R3 Mini 的 [`02_network`](../../target/linux/mediatek/filogic/base-files/etc/board.d/02_network) 也把 `eth0` 放在 LAN、`eth1` 放在 WAN。HNAT 源码原来读取了 `mtketh-wan`，随后却无条件把 `hnat_priv->wan` 写回 `eth0`，这样 `g_wandev`、接口注册通知和按 ifindex 查找都会指向 LAN。

[`hnat.c`](../../target/linux/mediatek/files-6.6/drivers/net/ethernet/mediatek/mtk_hnat/hnat.c) 现在用 `strscpy()` 保留设备树提供的 WAN 名称。包分类仍然使用源码既有的 `IS_WAN()`/`IS_LAN()` 宽匹配宏，没有把接口判断收窄到某个固定字符串；这同时修正了 R3 Mini 的实际设备映射和外接 USB/WWAN 等扩展接口路径。

## R3 Mini PWM/风扇修复

问题来自 [`998-pwm-fan-fix.patch`](../../target/linux/mediatek/patches-6.6/998-pwm-fan-fix.patch)：原补丁为了 Huasifei WH3000 Pro 的启动脉冲，移除了 `pwm-fan` 的 thermal cooling-device 注册，并对所有 Mediatek 板子在 probe 时写入零占空比。R3 Mini 的设备树依赖 `pwm-fan` cooling maps 控制 CPU 温度，thermal 注册被移除后就会失去正常调速能力。

补丁现在保留上游 thermal 注册流程，只增加一个 `mediatek,initial-pwm-zero` 设备树属性。Huasifei WH3000 Pro 的 [`&fan`](../../target/linux/mediatek/dts/mt7981b-huasifei-wh3000-pro.dts) 单独声明该属性，继续得到它需要的初始零输出；R3 Mini 没有该属性，因此保留 cooling maps、热保护和运行时调速。这个修复把行为限定在真正需要的板子上，没有关闭合法的 thermal 控制。

## TurboACC 行为修复

[`turboacc`](../../package/mtk/applications/luci-app-turboacc-mtk/root/etc/init.d/turboacc) 做了以下收敛：

1. HNAT reload 只写一次目标 `hook_toggle`，不再执行 `1 -> 0 -> 目标值` 的瞬时切换，避免每次 reload 清空活动流表。
2. debugfs、fullcone 和 TCP 拥塞控制接口都先检查是否存在；缺少接口时只记录日志，不把启动失败扩散到其它服务。
3. 空的 AP IPv4 选项不会再枚举接口、改写网络或重启防火墙。只有用户明确填写合法 IPv4 时，才进行 AP 转换，并且只提交 `network`、`dhcp`、`wireless` 三个配置。
4. 删除了启动时提交/重启 firewall、调整 `min_free_kbytes`、清空 page cache 和改写 `/etc/wgetrc` 的副作用。
5. `stop_service()` 不再调用 `stop` 自身（这会进入 rc.common 的递归），而是直接关闭 HNAT/fast-classifier 控制项并移除 IPv6 SFE 设备节点。
6. TurboACC 的 fullcone 默认从 `2` 改为 `0`，避免迁移后隐式打开 NAT 行为；用户显式设置的值仍会被应用。

## 选择与排除边界

以下名称在当前源码树中没有可用的包定义，或者按需求明确排除，不能写入 R3 Mini 片段：`kmod-nft-fullcone`、`bridger`、`autocore`、`athena-led`、`UA-Mask`、`UA3F`，以及镜像原来引用但不存在的 `kmod-mt7915e`、`kmod-mt7986-firmware`、`mt7986-wo-firmware`。WO/Wi-Fi 固件由 `kmod-warp` 和 `kmod-mt_wifi` 的安装阶段按 MT7986/AX4200 配置提供。

## 推荐默认值

- `turboacc.config.fastpath=mediatek_hnat`，`fastpath_mh_eth_hnat=1`，IPv6 hook 和 PPE 绑定速率保持开启；`fullcone=0`，避免迁移后改变 NAT 语义。
- `mtkhqos.global.enabled=0`、`hqos=0`；配置明确的 QDMA 队列并关闭 QoSmate 后，才把两者均改为 `1`。HNAT 总开关由 TurboACC 管理。
- 不安装 EQOS/SQM/qosify/nft-qos/qos-scripts；保留所选 HQoS/QoSmate 需要的底层队列模块。
- `mtk-smp` 负责 MT7986 的 IRQ/RPS 绑定时不启动通用 `irqbalance`；两个服务同时运行会互相改写亲和性。若用户需要 `irqbalance`，应先移除 `mtk-smp` 的固定绑定。
- Wi-Fi 只保留 `mtwifi-cfg`/`luci-app-mtwifi-cfg` 这条配置路径，第一张卡为 MT7986、AX4200、flash EEPROM；不启用旧 `wifi-profile`、`luci-app-mtk` 或 `mtwifi-wapp`。
- R3 Mini 的 CPU thermal cooling map 维持设备树原值。初始零 PWM 只由 Huasifei 的 `mediatek,initial-pwm-zero` 属性触发。

## 编译前和上机验证清单

这部分只记录硬件实现需要的验证点，尚未代替根任务的完整编译：

- 配置解析后确认 `CONFIG_PACKAGE_kmod-mediatek_hnat=y`、`CONFIG_PACKAGE_kmod-mt_wifi=y`、`CONFIG_PACKAGE_kmod-warp=y`、`CONFIG_MTK_CHIP_MT7986=y`、`CONFIG_MTK_WIFI_SKU_TYPE="AX4200"`、`CONFIG_WARP_CHIPSET="mt7986"` 和 `CONFIG_WARP_NEW_FW=y` 均保留。
- 检查最终镜像的 `/lib/modules/*/mtkhnat.ko`、`mt_wifi.ko`、`mtk_warp.ko`、`conninfra.ko` 及 MT7986 Wi-Fi/WO 固件；不要出现旧的不存在包名。
- R3 Mini 启动后检查 `dmesg` 中 HNAT 的 `wan = eth1`、`lan = eth0`，再查看 `/sys/kernel/debug/hnat/hook_toggle`、`hnat_stats`、PPE 统计和 TurboACC 页面显示是否一致。
- 通过 CPU 温度上升/下降观察 `/sys/class/thermal/thermal_zone*/` 的 cooling device 变化和 PWM 占空比；确认 `pwm-fan` 已注册为 thermal cooling device，且风扇可以从低档切到高档。Huasifei 设备则确认启动时仍保持零输出。
- 先保持 `mtkhqos` 禁用验证 HNAT，再单独启用一组 QDMA 队列；如果测试 QoSmate，先关闭 HQoS 并确认 HNAT 已暂时关闭，记录吞吐、CPU 占用和连接稳定性。
- 编译日志由根任务的分组编译脚本记录；本硬件组至少要单独统计 `conninfra`、`mt_wifi`、`warp`、HNAT 内核模块、TurboACC LuCI、Wi-Fi 配置和队列工具的阶段耗时。
