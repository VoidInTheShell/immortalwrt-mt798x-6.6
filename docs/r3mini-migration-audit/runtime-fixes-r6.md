# R3 Mini 启动日志修复与 r6 构建验收

日期：2026-09-07

源码提交：`4987967fa4 r3mini: fix r6 boot-time service and netns warnings`

固件版本：`PortalWRT 24.10.2 GLaDOS-R3Mini-Autoneg-r6`

内核：Linux 6.6.133；固件 revision：`r33648+13-ec9ef10efc`。

## 修复内容

1. NTP 服务冲突

   - 固件同时选择 BusyBox sysntpd 和完整 ntpd。完整 ntpd 的 postinst 会按设计删除 `/usr/sbin/ntpd` BusyBox 链接，但 sysntpd 启动脚本仍调用该路径，造成 jail dependency error 和 crash loop。
   - `r3mini-defaults` 升级到 `2026.09.07-r4`，一次性迁移为禁用 sysntpd、启用已有的 `/sbin/ntpd` 服务。标记被纳入 sysupgrade keep 列表，因此迁移后不再覆盖用户后续的服务选择。

2. daed 创建 netns 时的三个 conntrack WARN

   - 新补丁 `999-3005-netfilter-fix-vendor-sysctl-netns-safety.patch` 将 `nf_conntrack_qos` 正确绑定到各自 `net->ct.sysctl_qos`。
   - 仍属于全局语义的 `nf_conntrack_nat_mode` 和 `nf_conntrack_tcp_no_window_check` 在非 init_net 中显式设为只读；init_net 继续保持 0644，原 HNAT/NAT 配置接口不变。
   - 不删除 Linux 6.6 的安全检查，不禁用 daed、eBPF、HNAT、WED 或 PPE。

3. HAProxy 3.0 配置兼容

   - 当前配置的 PassWall `INCLUDE_Haproxy=y` 对 HAProxy 有真实条件依赖，因此保留组件。
   - HAProxy 升级为包 release `3.0.25-r2`，默认 health listener 从已移除的 `mode health` 改为 `mode http` 和 `http-request return status 200`。
   - `r3mini-defaults` 对保留配置仅迁移精确匹配的旧 `mode health` 行，不改其他用户代理规则。迁移后的完整实机配置副本已经由 HAProxy 3.0.25 `-c` 校验通过。

4. 插件初始化

   - `luci-app-adguardhome` 升级为 `1.1.1-r2`，`addhost.sh` 以 0755 安装，消除启动时 Permission denied。
   - advancedplus 在 netwizard 未安装时立即返回，不再访问缺失的 UCI section 或菜单 JSON。

5. MTK 无线/WARP 初始化日志

   - ACK/CTS 自定义功能未启用时，不再把宽于 16 位的 TMAC 寄存器默认值当成用户 timeout 下发；显式启用后的原设置路径不变。
   - R3 Mini 的片上 DBDC Wi-Fi 只有一个 WARP 客户端，且原 `wed2` 探测始终因没有可用客户端 entry 而失败。板级 DTS 禁用这个重复 alias 节点；实际工作的 `wed@15010000`、组合 WED 资源、WO 固件和 WDMA 路径保留。

6. 版本与验收

   - 版本号更新为 Autoneg-r6，production 分区继续为 2048 MiB。
   - 镜像验收新增 NTP/HAProxy 迁移、HAProxy/AdGuardHome 包 release、AdGuard helper 权限、advancedplus guard、wed2 disabled 和 FIT/rootfs revision 一致性检查。

## 构建与离线验收

- 最终构建目录：`logs/r3mini-build-r6-release-final`。
- 10/10 阶段成功，最终一次 committed/release 构建用时约 357.5 秒。
- 主机源码回归：38 项通过，包括实际 C 函数测试、迁移配置验证、源码快照可重放、shell 语法及 r5 回归。
- 解包验收结果：`.r3mini-checks/r6-image-20260907/result.json`。
- FIT、kernel、DTB、rootfs 的内嵌 CRC/SHA1 均通过。
- FIT metadata 与 rootfs `DISTRIB_REVISION` 均为 `r33648+13-ec9ef10efc`。
- DTB 中 `wed@15010000` 保留，`wed2@15011000 status = "disabled"`。
- 镜像仍包含 `mtkhnat.ko`、`mt_wifi.ko`、`mtk_warp.ko`、`mtk_warp_proxy.ko`、WO/Wi-Fi 固件、daed 和 ModemManager。
- production GPT 大小为 2147483648 字节（2 GiB）。
- 旧 r5 sysupgrade SHA256 仍为 `1087f0fa31e5ebe605c94edb2616d31b8c41dafdfca45573b0b9e7d50751e97d`，未被覆盖。

## 最终固件

文件：

`.r3mini-output/autoneg-r6/targets/mediatek/filogic/portalwrt-24.10.2-glados-r3mini-autoneg-r6-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb`

大小：255198293 字节。

SHA256：`924fd3a782570a8d5abb492db5e69f146075a2d7798d25babec5345028f118b9`

构建系统仍会生成标准 eMMC 组件，但按用户最新要求没有再制作独立上位机 host-flash bundle；本轮交付对象是保留配置升级使用的 sysupgrade 镜像。

## 实机状态与待验收项

- r5 日志里的 daed `Exiting: terminated` 已由用户确认是手动关闭，不属于崩溃；r6 迁移不改变 daed 当前关闭状态，也不恢复 daed/HNAT 互斥。
- r6 已完成编译和离线验收，但构建机最后连接 `10.243.1.156:22` 超时，未上传固件、未运行远端 `sysupgrade -T`，更没有刷写设备。
- 刷入 r6 后仍需实机复查：三个 conntrack WARN 消失；NTP 守护进程正常；HAProxy 不再 crash loop；AdGuardHome/advancedplus/ACK-CTS/WED2 启动错误消失；HNAT/WED/无线加速和 daed 按需启动仍正常。
