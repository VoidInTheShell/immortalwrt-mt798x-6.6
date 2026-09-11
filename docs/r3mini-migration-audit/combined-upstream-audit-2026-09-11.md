# R3 Mini / Modem / PPE 联合审计复核

本轮为源码与已有实机记录复核，没有部署内核修改或新增实机测试。当前本地 HEAD 为 969d07519d，存在未提交的 Modem/主题修改。用户粘贴报告里的精确上游 SHA 在消息中被替换为 AETHER 占位符，不能将其当作已验证的可复现基线。本次直接读取公开上游文件交叉检查；动态分支不是原报告精确提交的替代品。

## 已确认的缺口及实施约束

| 项目 | 本地证据 | 结论与回移约束 |
| --- | --- | --- |
| option 中断短包 | 实际内核构建树 option.c:2646 回调无 actual_length 判断，直接读取请求字段和第 9 字节 | 明确缺失长度防护。优先级最高；长度 0–7、8、9 及正常/停止 URB 均须覆盖；上游短包分支直接 return，因此回移还应明确通知 URB 是否继续提交的行为 |
| EN8811H LED GPIO | 实际构建树 air_en8811h.c:1033 仅 probe 配 GPIO；config_init:1101 可 restart MCU | 缺少重启后的显式恢复。应放到 MCU ready、LED 初始化成功后的 config_init 路径并传播错误；普通拔线未必调用 config_init，不能只用拔线验收 |
| PPE 分层 MTU | 私有 hnat.h:83–86 只有寄存器定义；target 搜索未发现初始化/CHANGEMTU 写入 | 缺口确认。须按 NETSYSv2 寄存器位域映射，覆盖所有 PPE、启动/SER/MTU 变化；不能按名称假设三个 VLYR 寄存器全要写 |
| MM timeout | 官方 packages 当前实际 HTTP 文件含 timeout UCI 声明、默认 120、四种长命令及参数传递；浏览器缓存返回旧版本 | 改进确实存在。回移到本地 1.24.2 集成层即可；需参数验证、调用链传递及 5gmodem 重建保留，不能只替换字面量 120 |
| QMI RX 32 KiB | qmi_wwan bind 赋值 32768；usbnet_change_mtu 仅在 rx_urb_size == old_hard_mtu 时同步改大小 | 常规 1500/raw-IP 切换确实保留大缓冲；不能扩大成所有 MTU 序列永久保留，也不证明 WDA/QMAP 聚合协商和 USB 实际传输正常 |

PPE MTU 参考实现已在 BPI-Router-Linux 6.12-main 实际 HTTP 内容中确认：base=ETH_HLEN+最大 GMAC MTU，按 0/1/2/3 tag 加 0/4/8/12 字节，并写两个双字段寄存器。PPPoE/DSA 额外开销不能不加区分再次累加。是否进入 Torvalds 主线、进入哪一个 stable/OpenWrt 精确提交，应单独追踪；本轮浏览器获得的 torvalds/master 快照没有该函数，不据此断言原报告错误或该修复不存在。

## 对之前结论的必要修正

1. 私有 HNAT/PPE 的有线 external 出口门槛、邻居 MAC 假设、TX L2 格式缺口成立；但 BIND=0 低流量样本并不能定位每个方向的失败。下行到 GMAC/Wi-Fi 与上行到 USB 需要分别论证。
2. 本树 raw-IP RX 强制补 Ethernet header 只是局部改动。usbnet 的 protocol==0 分支会 eth_type_trans；qmimux/pass-through 又提前分支，因此不能泛化“所有 QMI 下行均已适配 PPE”。仍需 skb protocol、mac/network header、headroom、mux parent/child、ifindex 生命周期取证。
3. fw4 的 002-forbid-using-flow-offload.patch 不仅删 flags offload，还让 resolve_offload_devices 无条件返回空列表。此前建议直接打开软件 flow offload 不完整；需要独立设计与私有 HNAT 的排他或按路径共存方案。
4. iperf3 JSON 的 cpu_utilization_percent 是测试进程 CPU 时间口径，不是整机每核 IRQ/softirq 利用率。此前用 1.622% 认定路由器 CPU 不饱和、无线必为瓶颈，证据不足。约 30.6 Mbit/s 不能单独排除主机软中断、USB、服务器、运营商路径或整形瓶颈。
5. 当时未绑定测试的路由选中 eth1，可说明当时路径；不能仅凭后续路由快照百分百重建用户更早的约 200 Mbit/s 测试出口，后者应表述为高度可疑、缺少当时流量证据。
6. qmi_wwan_q/CM 后失联与默认路由变化相关，但没有故障后日志，不应把路由抢占写成已证实唯一原因。恢复前也不能排除内核故障。Discussion #65 尚无匹配证据，不等于已经完全排除所有共同底层缺陷。
7. 原始概率性创建失败没有完整重现，已确认并修复的是检测/锁/状态/metric/fw4 缺陷；不能将全部概率失败都归为已经确定的并发原因。
8. 当前完整固件的优势是本机已有部署验证、开箱包集合及管理功能。相对官方默认镜像的配置优势，不代表驱动质量、峰值吞吐或维护性全面领先，更不代表主线超集。

## 已有验收证据保留

runtime-fixes-r5.md:64 记录 5 GHz 终端经有线 WAN 的双向 IPv4 BIND、GMAC2/WDMA0 输出和硬件计数增长，支持该特定路径硬件卸载已工作。不能外推到 USB、IPv6、PPPoE、QinQ、所有 HQoS 或代理策略变化。

5gmodem-theme-fixes-2026-09-11.md 记录源码、热部署、回归和新镜像 payload 检查；新镜像尚未完成冷启动全链路验收。fw4 缺失蜂窝 forward/NAT 的原始阻断证据仍成立，单纯未绑定硬件流不会替代这个诊断。

## 推荐实施和验收顺序

1. option 长度防护和 EN8811H GPIO 恢复作为两个独立小补丁构建验证。
2. MM timeout 接入 netifd、界面/配置及接口重建保留；保留已存在的 MM inhibit/设备所有权逻辑。
3. PPE 分层 MTU 适配私有 HNAT。重点验证全部 PPE 的寄存器、SER 恢复、不同 GMAC MTU；用终端比较无 tag/单 tag/QinQ/PPPoE 的尺寸边界、DF/PMTUD、BIND 与 punt reason。
4. 恢复设备后补齐 qmi_wwan_q。管理出口固定之外还应在设备本地预置定时恢复，避免依赖失联后 SSH 清理。相同端点交错多轮测速，采集 /proc/stat、interrupts、softirqs、USB 和源出口计数。
5. USB PPE 独立设计 raw-IP/QMAP 注入及外发、mux 设备注册/注销、flow 失效、GSO/GRO/校验、MTU/IPv6；先保持正常软件转发，再分方向和终端介质验收硬件流。

## 外部参考

- Linux option 修复公告：https://lists.openwall.net/linux-cve-announce/2026/09/04/77
- Linux option 当前源码：https://github.com/torvalds/linux/blob/master/drivers/usb/serial/option.c
- EN8811H 上游修复：https://git.zx2c4.com/wireguard-linux/commit/?h=davem%2Fnet&id=03b4702fc5e311cbac9ba8654021a88f0dac914c
- BPI PPE MTU 参考：https://github.com/frank-w/BPI-Router-Linux/blob/6.12-main/drivers/net/ethernet/mediatek/mtk_ppe.c
- OpenWrt MM 集成：https://github.com/openwrt/packages/blob/master/net/modemmanager/files/lib/netifd/proto/modemmanager.sh
- 标准 PPE 输出选择：https://github.com/torvalds/linux/blob/master/drivers/net/ethernet/mediatek/mtk_ppe_offload.c
