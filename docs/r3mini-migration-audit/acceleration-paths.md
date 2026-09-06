# 加速替代路径复核

不能从 `luci-app-turboacc-mtk=n` 推出“没有硬件加速”，也不能把 `kmod-mediatek_hnat=n` 当作所有平台都失去硬件 NAT 的充分条件。本次进一步核对了内核内建选项、模块选择生成规则、以太网补丁、fw4 后端、LuCI 入口及 rootfs 覆盖文件。

## 两条加速路径确实同时存在于源码中

| 路径 | 驱动与控制面 | 当前构建状态 |
| --- | --- | --- |
| MTK 私有 HNAT | `CONFIG_NET_MEDIATEK_HNAT` / `mtkhnat.ko`，私有 netfilter hooks，debugfs `hnat` | 当前包未选；按真实 `package-metadata.pl kconfig` 生成的 kernel override 明确为 `# CONFIG_NET_MEDIATEK_HNAT is not set`，没有发现借别名自动选入 |
| 内建以太网 PPE + Linux flowtable | `CONFIG_NET_MEDIATEK_SOC=y` 的 `mtk_eth` 包含 `mtk_ppe.o`、`mtk_ppe_offload.o`；fw4/nft flowtable 下发流 | 内核配置/源码保留，但本树 fw4 补丁禁用了正常下发路径，不能把它认定为当前已经接替私有 HNAT |
| 无线 WED/WO | 既有内核 `CONFIG_NET_MEDIATEK_SOC_WED=y`，也有私有 `kmod-warp` | 内核 WED 支持不等于 Wi-Fi 驱动及其固件完整。当前 mt_wifi/conninfra/warp/profile 未选，机型 DEFAULT 指向的 mt76 包又不在索引中 |

关键依据：

- `target/linux/mediatek/filogic/config-6.6:327`：内建 `NET_MEDIATEK_SOC` 和 `NET_MEDIATEK_SOC_WED`。
- `target/linux/mediatek/patches-6.6/999-2705-net-ethernet-mtk_eth_soc-support-proprietary-debugfs.patch:8`：mtk_eth 对象列表保留 mtk_ppe/mtk_ppe_offload。
- `999-2745-mtkhnat-add-mtkhnat-driver-support.patch:134`、`:156`：未编译私有 HNAT 时保留主线 PPE start/probe；编译私有 HNAT 时走另一分支。因此它们不是应无条件同时启用的两个独立加速器。
- 执行 `scripts/package-metadata.pl kconfig tmp/.packageinfo .config 6.6` 得到 `NET_MEDIATEK_HNAT=n`；同时 `NFT_FLOW_OFFLOAD`、`NF_FLOW_TABLE`、`NF_FLOW_TABLE_HW`、`NF_FLOW_TABLE_INET` 为 `m`。

## 通用防火墙面板存在，但后端行为不同

已选中的 `luci-app-firewall` 在 `feeds/luci/applications/luci-app-firewall/htdocs/luci-static/resources/view/firewall/zones.js:78` 提供软件/硬件流量卸载入口；它写的是 `firewall.@defaults[0].flow_offloading{,_hw}`。

然而当前 `package/network/config/firewall4/patches/002-forbid-using-flow-offload.patch`：

1. 删除 nft flowtable 的 `flags offload`。
2. 使 `resolve_offload_devices()` 无条件 `return []`。

所以这里确实有另一个 UI 入口，但它不能代替私有 HNAT 管理，并且按当前 fw4 补丁不会正常建立通用硬件卸载路径。不能仅检查页面是否有勾选框或 nft 内核模块是否存在。

没有发现后续 fw4 补丁恢复这两处逻辑；该包当前只有 001 和 002 两个补丁。rootfs 覆盖目录也没有发现另行注入的 .ko 或自动建立硬件 flowtable 的脚本。

## 私有 HNAT 不依赖 TurboACC 面板才能工作

`hnat.c:800` 启动 PPE，`:812` 在驱动 probe 中调用 `hnat_enable_hook()`；该函数把 `hook_toggle` 设为 1。只要驱动和设备树正确，完全可以不用 LuCI TurboACC 页面，由驱动默认行为或自定义 init 管理。

现存其他入口有：

- `mtkhqos_util/files/mtkhqos`：可 modprobe mtkhnat、切换 hook，属于 HQoS 工具，但当前该包未选。
- `luci-app-mtk`、`mtwifi-cfg`：属于私有 Wi-Fi 管理体系，不能仅因名称带 MTK 就认定其代替了 HNAT 控制；当前也未选。
- 直接通过模块参数、debugfs 管理，不要求必须安装 `luci-app-turboacc-mtk`。

`luci-app-turboacc-mtk` 本身不依赖 `kmod-mediatek_hnat`，进一步说明“有面板”和“有驱动”是两个独立问题。

## WAN 映射与 MTK QoS 的额外风险

HNAT 节点从 mt7986a.dtsi 继承，写的是 WAN eth1、LAN eth0，板级网络初始化也以 eth1 为 WAN。不过 `hnat.c:698-703` 读取 mtketh-wan 后，实际把 `hnat_priv->wan` 硬编码成 eth0，随后用它取得 g_wandev。必须核对这份私有驱动是否正确处理 R3 Mini 端口及蜂窝 WAN，不能只凭 DTS 就认定匹配。

这还不能直接断言“eth1 一定不能加速”：同目录 `hnat.h:894-899` 的 IS_WAN 与 IS_LAN 都宽泛匹配 eth0、eth1、lan、wan、bond，明显不是标准严格的 LAN/WAN 分类。因此不能在未核对路径前只改一个字符串；需检查 g_wandev 使用、两个方向及扩展接口的实际绑定。

`luci-app-eqos-mtk/root/usr/sbin/eqos:97-107,139-168` 同时操作私有 HNAT 的 qos_toggle/QDMA 和 tc/IFB，是混合实现：部分用户使用硬件队列，超过其硬件队列分配范围的用户标记 0x99 后走 tc。不能把它简单描述成纯软件 QoS，也不能称其等价于 CAKE。该脚本还改 turboacc 配置、firewall.user 和共享 mark，迁移时要审查启停影响。

## 这次能得出的结论

1. 源码中确实存在替代的内建 PPE/WED 组件，先前仅凭未选包名判断不足。
2. 按**当前源码与构建配置**，私有 HNAT 没有被内建/别名偷偷选入；通用 PPE 又缺少正常 fw4 配套下发，完整无线驱动选择也没有落实。因此当前配置仍不能作为“已验证完整硬件/加速基线”。
3. 不能由此说以太网驱动、校验和卸载、加密硬件或全部硬件支持都不存在。这些是不同能力。
4. 本目录尚无已编译 vmlinux、模块目录或固件 manifest，且未连接实机；此结论不描述用户现在正在运行的另一份固件。最终要检验构建后的 kernel config、模块/rootfs manifest，以及真实流量的 PPE 绑定。
5. 面向该私有 MTK 分支，优先整理一套完整、相互匹配的私有驱动配置；如果改走主线 PPE/mt76，则需要同步处理 fw4、无线源码、固件及设备树，不能只补一个加速开关。
