# RG520N-CN 驱动、QMAP 与 MTK PPE 调查（2026-09-11）

> 后续复核更正：见 [联合审计](combined-upstream-audit-2026-09-11.md)。本文的 CPU 1.622% 为 iperf3 进程口径，不能证明整机无 CPU/softirq 瓶颈；用户历史 200 Mbit/s 出口及 CM 断联唯一原因未获完整证实；标准软件 flow offload 被本树 fw4 补丁阻断，不能直接通过开关启用。下文的绝对化根因与瓶颈判断以联合审计限定为准。

## 结论摘要

1. GitHub Discussion #65 **不是当前 5gmodem 接口、初始化或优先级故障的同一根因**。该讨论的明确故障是 Linux 5.4 上的 RNDIS `eth2`、IRQ 134 异常、NETDEV WATCHDOG，随后整个 xHCI 主控死亡和 USB 设备断开；本机使用 Linux 6.6.133、QMI raw-IP `wwan0`，此前采样没有出现上述特征。
2. Discussion #65 提到的 `cfc9700009` 仅把文件作用域的 `int mape_toggle;` 改为 `int mape_toggle = 0;`。按 C 语言静态存储期规则，两种写法都以零初始化；而且原报告者数日后再次出现同样的 IRQ/xHCI 故障。因此不能把这一个提交视为已经解释或根治 USB 崩溃。
3. 当前树对 QMI raw-IP/QMAP 的 MTK PPE/HNAT 支持**没有闭环**。实机 PPE 基础模块、外部设备登记和 ppe0 回注通道存在，但持续采样硬件 BIND 为 0；源码又有外部 USB 出口提前返回、IPv4 邻居必须有以太网 MAC、硬件外发路径补入 Ethernet header 等与 raw-IP 不相容的条件。这里已经不只是“尚未测到”，而是有静态兼容缺口。
4. PPE 未闭环会导致蜂窝 NAT 流量继续走 CPU、在高速下 CPU/USB 中断压力上升，可能限制吞吐；**它不应导致改优先级后所有子网设备立即完全断网**。软件转发仍应工作。该完全断网现场的直接阻断点是 fw4 生效规则没有 `wwan0` 的 forward/NAT；5gmodem 修复已经补入接口创建/优先级调整后的 fw4 同步。
5. 对 RG520N-CN，当前最稳妥默认仍是主线 `qmi_wwan`。若追求 USB 极限吞吐，最值得继续验证的是两条路线：主线 `qmi_wwan` pass-through + `rmnet` 的完整 QMAPv5，或排他加载 `qmi_wwan_q` + Quectel-CM。后者已经确认能为 `2c7c:0801` 建立 QMAPv5/31 KiB/上行聚合路径，但本轮实测在 Quectel-CM 写入默认路由后失去了远程管理，尚不能给出公平速度值。
6. 当前 n41 小区在强制走蜂窝的 CN2 测试中约 30.6 Mbit/s，路由器本机 CPU 仅约 1.6%；这一现场无线侧先成为瓶颈，不能据此排出不同驱动的极限速度名次。用户此前看到约 200 Mbit/s 的未绑定测试实际按路由走了 `eth1`，不是模块链路。

Discussion 原文：<https://github.com/padavanonly/immortalwrt-mt798x-6.6/discussions/65>

## 设备与测试基线

| 项目 | 现场结果 |
| --- | --- |
| 路由器 | BPI-R3 Mini / MT7986，Linux 6.6.133 |
| 模组 | Quectel RG520N-CN，USB ID `2c7c:0801` |
| 固件 | `RG520NCNAAR03A01M4G` |
| USB | USB 3.x，枚举速度 5 Gbit/s |
| 当前 USB 模式 | Quectel usbnet 0，QMI 控制 `/dev/cdc-wdm0`，数据接口 4 |
| SIM/网络 | 中国广电，MCC 460 / MNC 15，5G SA n41 |
| 典型无线指标 | RSRP -83 至 -86 dBm，RSRQ -13 至 -15 dB，SINR 9 至 10 dB |
| 固件默认驱动 | 主线/本树定制 `qmi_wwan`，raw_ip=Y |
| 当前缺项 | 固件配置没有 `kmod-rmnet`；OpenWrt ModemManager netifd 脚本没有暴露 multiplex 参数 |

拨号程序和内核数据驱动必须分开看。`uqmi`、qmiraw、ModemManager、Quectel-CM 主要负责控制面：设置 APN、协商 IP family、WDA 数据格式、创建路由；连接建立后每包吞吐主要由 `qmi_wwan`/`qmimux`/`rmnet`/`qmi_wwan_q`、USB 聚合参数、CPU 与无线空口决定。

## 已完成的实机吞吐取证

### 路由纠正

未指定源地址或接口的 `iperf3 -R` 会遵从主路由。现场曾同时存在：

- `eth1` 默认路由 metric 110；
- 蜂窝 `qmimux0` 默认路由 metric 200。

因此此前约 200 Mbit/s 的结果选中有线出口。后续测试均给 CN2 端点添加临时 `/32` 路由，并核对 `ip route get` 的 source、gateway 和 device，避免把有线吞吐计入模块。

### 结果表

| 数据路径 | 测试 | 下行 | 上行 | CPU/补充 | 解释边界 |
| --- | --- | ---: | ---: | --- | --- |
| 主线 `qmi_wwan` raw-IP，无 QMAP | Ookla 重试第 1 轮 | 35.31 Mbit/s | 20.62 Mbit/s | CPU 7.2%；idle 48.529 ms；负载延迟高 | 真实蜂窝出口；单轮无线瞬时状态 |
| 主线 `qmi_wwan` + sysfs `add_mux 0x81` + CM 1.6.5 | Ookla | 21.97 Mbit/s | 9.35 Mbit/s | 换了小区/扇区 | 不能与上一轮按驱动直接比较 |
| 同上，强制 CN2 `/32` 路由 | `iperf3 -R` 20 秒 | 30.616 Mbit/s receiver | 未测 | 本机 CPU 1.622%，1 次重传；接口无 error/drop | 可证明走 `qmimux0`；不能代表驱动上限 |

QMAP 协商日志确认：主线驱动创建 `qmimux0`，mux ID `0x81`，QMAP mode 1、QMAP v1、最大包 16384；WDA 上行聚合是 11 个 datagram / 8192 字节。Quectel-CM 尝试私有 ioctl `0x89f2` 失败，说明主线 qmimux 路径没有启用厂商驱动的专用上行聚合接口。

本轮测得的约 22–35 Mbit/s 波动大于预计的 USB 驱动开销，而且 QMAP 轮次落在不同小区/扇区。它们只证明各路径能够传输，不能用作“QMAP 比 raw-IP 慢”或“某驱动最快”的结论。

## `qmi_wwan_q` 取证与当前未完成项

### 静态和构建结果

本树 `feeds/qmodem/driver/quectel_QMI_WWAN` 的包版本为 1.5。已在本地按当前 6.6.133 内核成功编出模块；现存固件包仓中另有 1.2.9 版本。

对于 RG520N/RG520N-CN 的 `2c7c:0801`、USB interface 4，厂商表映射为 SDX55 参数 `(9 << 8) | 31`：

- 内部 QMAP version 9，即 QMAPv5；
- 31 KiB 聚合尺寸；
- 强制 qmap_mode=1；
- `use_rmnet_usb=1`，源码注释明确用于改善上行数据聚合；
- 自动建立 `wwan0_1` mux 子接口；
- 提供主线 `qmi_wwan` 没有的 Quectel 私有 UL aggregation ioctl。

`qmi_wwan_q` 的 QMAP 子接口仍是 `ARPHRD_NONE`/raw-IP，而且源码没有 MTK HNAT/PPE 专用 hook。因此它可能降低 USB URB/中断负担、提高软件路径吞吐，但不会自动补齐本树的 PPE raw-IP 外发语义。

### 实机切换结果与断联边界

1. 1.2.9 模块已排他加载成功；`/proc/modules`、USB interface driver 和自动创建的 `wwan0_1` 均确认有效。
2. 启动 Quectel-CM 后，蜂窝默认路由被以 metric 0 写入。远程管理所依赖的 ZeroTier underlay 随即失联。
3. 失联前已向 Quectel-CM 发送 TERM；但设备仍无法从 ZeroTier 到达。模块在 `/tmp` 手动加载、没有加入自动加载，物理重启会回到固件原本的主线 `qmi_wwan`。
4. 没有取得失联后的内核日志，不能把这次事件称为 qmi 驱动、xHCI 或 PPE 崩溃。已有行为与“控制程序改变默认路由导致管理路径自切断”完全相容。

恢复后重测必须先保护管理路径，再启动 CM；要保存 QMAP/WDA 协商、强制蜂窝的 iperf JSON、CPU/IRQ、接口 error/drop 与内核日志，最后卸载厂商驱动并恢复主线插件会话。完成前不发布 `qmi_wwan_q` 的速度排名。

## Discussion #65 对照结论

| 对照项 | Discussion #65 | 当前 RG520N-CN 现场 | 是否吻合 |
| --- | --- | --- | --- |
| 内核 | 5.4.284 | 6.6.133 | 否 |
| USB 数据协议 | RNDIS，`rndis_host`，`eth2` | QMI raw-IP，`qmi_wwan`/`qmimux`，`wwan0` | 否 |
| 首次栈 | `do_hnat_mape_w2l_fast` | 无对应栈 | 否 |
| 核心告警 | `irq 134: nobody cared`，IRQ 被关闭 | 未见 | 否 |
| 网卡故障 | `NETDEV WATCHDOG: eth2 transmit queue timed out` | 未见 | 否 |
| USB 结果 | xHCI host dead，整个 USB disconnect | 先前测试无 USB disconnect；当前仅 ZeroTier 管理不可达 | 否 |
| 后续复发 | 所谓修复后 3 天再次发生；第二次栈中无 Map-E 函数 | 当前无同类事件可比较 | 不能据此归因 |

该 discussion 对本项目的价值是建立一个压力回归特征集，而不是提供当前故障根因。以后持续 USB 吞吐测试需要同时监控：

- `irq 134: nobody cared` / `Disabling IRQ #134`；
- `NETDEV WATCHDOG`；
- `xhci-mtk ... unknown event`；
- `host controller not responding` / `HC died`；
- 模组 USB disconnect/re-enumeration；
- 流量前后 `mape_toggle`、PPE BIND、USB IRQ/softirq CPU。

### `mape_toggle` 提交为何不足以证明修复

Discussion 中建议的提交是 `cfc9700009f1b6bcb3546799e54127afd665693a`：

```diff
-int mape_toggle;
+int mape_toggle = 0;
```

这是文件作用域静态存储期对象，未显式初始化时也会放入 BSS 并以 0 开始。除非还有报告未展示的构建、内存破坏或运行期写入因素，这一行本身不改变正常初值。本地 6.6 树已写成 `int mape_toggle=0`，不能再靠重复这一变更修复当前问题。

此外，该 discussion 的原报告者先说问题消失，随后又贴出相同 IRQ 关闭、RNDIS watchdog 和 xHCI dead 的复发日志；六月对 6.6 + FM350 USB offload 的“没有 xHCI 错误”只是单个用户的后续观察，不是对 RG520N/QMI 路径的系统验证。

## 当前树的 PPE/HNAT raw-IP 缺口

### 实机动态证据

- `mtkhnat` 已加载，hook enabled；
- `external_interface` 已列出 `wwan0`；
- `hnat_ppd_if` preferred/active 均为 `ppe0`，ppe0 有实际包计数；
- fw4 修复/重启后已经观察到下游终端通过蜂窝 NAT 的双向 ASSURED conntrack；
- 多轮采样 `BIND_PPE0=0`、`BIND_PPE1=0`，流表只见 UNBIND；
- 一次短采样蜂窝流量不足，不能单靠动态样本断言达到 bind threshold 后失败，但它与以下源码缺口一致。

### 源码门槛一：有线来源到外部 USB 提前退出

`mtk_hnat_nf_post_routing()` 中：

```c
if (!IS_WHNAT(out) && IS_EXT(out) && !FROM_WED(skb))
    return 0;
```

`wwan0` 是 external interface、不是 Wi-Fi WHNAT；普通有线 LAN 报文也不是 FROM_WED。故有线 LAN → USB modem 在绑定处理前直接退出。Wi-Fi WED 来源可能越过这一关，但仍会撞到后面的 raw-IP 条件。

### 源码门槛二：IPv4 next-hop 强制要求以太网邻居 MAC

IPv4 postrouting 总是把 `hnat_ipv4_get_nexthop` 传入绑定函数。该函数先查 neighbor，再检查有效 Ethernet MAC。QMI raw-IP 接口却明确配置：

- `type = ARPHRD_NONE`；
- `hard_header_len = 0`；
- `addr_len = 0`；
- `IFF_POINTOPOINT | IFF_NOARP`。

点到点 raw-IP 出口没有可满足这条 Ethernet neighbor/MAC 假设的 ARP 邻居。主线 qmimux 和 qmi_wwan_q mux 子接口同样属于 raw-IP，不因换成 vendor 驱动而自然解决。

### 源码门槛三：PPE 外发函数向 skb 压入 Ethernet header

`do_hnat_ge_to_ext()` 对非 Wi-Fi external device 会 `skb_push(ETH_HLEN)` 后交给外部 netdev。本树 qmi_wwan 的 `ndo_start_xmit` 是 `usbnet_start_xmit`，driver_info 没有 tx_fixup，意味着 skb 数据会按现有起点送给 USB。模组 QMI raw-IP/QMAP 上行需要 IP/QMAP 帧，不接受凭空多出的以太网头。

因此不能通过删除提前 `return`、伪造 ARP/MAC 或把 `wwan0` 强行标成普通以太网来“快速修复”；这样可能产生格式错误包、静默丢包甚至数据破坏。

### 本树 RX 的一个不对称改动

本树 `qmi_wwan_rx_fixup()` 把局部 `rawip` 固定为 0，使收到的 IPv4/IPv6 raw packet 被补成合成以太网头。它能帮助 RX 侧现有 HNAT/bridge 代码看到 L2 头，却不改变 netdev 本身的 ARPHRD_NONE/NOARP，也没有处理 PPE 加速后的 TX 去头；因此它不是双向 raw-IP PPE 集成。

### 这能解释什么、不能解释什么

能解释：

- BIND 长期为 0；
- 有线 LAN 与 Wi-Fi 的 HNAT 结果可能不同；
- 软件转发正常而 CPU/USB IRQ 在高速下升高；
- QMAP/UL aggregation 能改善 USB 效率，却未必使 HNAT BIND 生效。

不能解释：

- 仅调整接口优先级后所有子网设备立即完全无法上网；
- WebUI “正在初始化”但温度正常；
- RSSI/RSRP/RSRQ/SINR 全空；
- 删除 `network.modem` 后概率创建失败。

后三类已经分别定位到 fw4 运行态未同步、注册域/信号采集门槛、接口状态/并发创建缺陷，详见同目录的 5gmodem 调查和修复报告。

## RG520N-CN 可用驱动与推荐顺序

| 路线 | 聚合/复用 | 稳定性与维护 | 预期性能 | 当前建议 |
| --- | --- | --- | --- | --- |
| 主线 `qmi_wwan` raw-IP + uqmi/qmiraw/MM | 无 QMAP 时一包/URB 倾向更高开销 | 主线、OpenWrt 集成最好；恢复/hotplug 最可控 | 中等；无线较慢时足够 | **固件默认** |
| 主线 `qmi_wwan` qmimux (`add_mux`) | QMAP 下行/mux；当前 CM 无 vendor UL ioctl | 主线内核，用户空间需正确管理动态子接口和路由 | 比纯 raw-IP 更有潜力，但当前单轮未体现 | 可作为受控实验 |
| 主线 `qmi_wwan` pass-through + `rmnet` | QMAP v1/v4/v5、上下行聚合/校验/多 mux | 架构最接近现代 Qualcomm 上游；本固件缺 rmnet 与完整 netifd 接线 | **理论上最优的长期 USB 路线** | 下一阶段优先集成验证 |
| `qmi_wwan_q` + Quectel-CM | 对 0801 自动 QMAPv5、31 KiB、UL aggregation、`wwan0_1` | out-of-tree；需排他绑定；CM 默认路由、fw4、热插拔和进程所有权必须封装 | **最有希望成为近期可部署的高速路线** | 完成保护管理路径后的 A/B 测试再决定 |
| `cdc_mbim` + umbim/MM | 标准 MBIM/NTB 聚合 | 标准化、主线、通常好维护；需切模组 USB composition | 通常明显优于无聚合路径，可能接近 QMAP | 推荐作为第二条稳定对照 |
| ECM/`cdc_ether` + DHCP | 模组内部处理，主机侧像 Ethernet | 最简单，常见自动连接；模组 NAT/双 NAT，控制能力较少 | 社区个案中可能低于 MBIM | 稳定优先的 fallback |
| GobiNet | 厂商旧式 QMI | 1.6.3 在 Linux 6.6 上因旧 API 无法编译 | 无合理优势 | **排除** |
| PCIe MHI/QRTR/MBIM | 绕过 USB；取决于模组/转接硬件 | 需要真实 PCIe 接线、供电、复位、固件和枚举支持 | 总线开销可更低 | 当前板载 USB 路径不可直接采用 |

### 为什么现在不能给出“最快驱动”的实测冠军

1. 强制蜂窝测试只有约 30 Mbit/s，本机 CPU 远未饱和；驱动差异被无线波动淹没。
2. raw-IP 和 QMAP 测试不在相同小区/扇区、相同瞬时负载下；不能把单轮数字横向排名。
3. `qmi_wwan_q` 的完整吞吐轮次因默认路由抢占远程管理而中断。
4. PPE/HNAT 当前未 BIND；路由器本机 iperf 又不会经过 LAN NAT，不能拿本机 CPU 值替代 PPE 验收。

合理的性能验收需要固定频段/小区、相同 APN 与服务器、每路径多轮交错测试，并从 LAN 有线客户端和 Wi-Fi 客户端分别发起，记录中位数/p10/p90、USB IRQ、softirq、每核 CPU、接口 drop/error、重传和 PPE BIND。

## 开源社区与上游资料的交叉判断

- Quectel 官方 Linux USB 驱动手册把 `2c7c:0801` 的 QMI 数据接口列为 interface 4、控制节点 `/dev/cdc-wdm0`，也列出可切换的 MBIM composition；因此 QMI 和 MBIM 都是该模组的正式可用协议，不是社区猜测。
- Quectel 的 QMAP/IP aggregation 资料明确说明无聚合时每个 URB 仅装一个 IP packet 会增加 CPU/中断压力，而一个 URB 承载多个数据包可提高吞吐。这支持继续做 QMAP/UL aggregation，但不等于任何一次测速必然更快。
- Linux 内核 rmnet 文档把 MAP/QMAP、USB/PCIe/Qualcomm IP accelerator 列为正式数据路径。主线 qmi_wwan 的 sysfs ABI也提供 `add_mux` 与 `pass_through`，说明“主线 qmi_wwan + rmnet”是有上游语义基础的方案。
- ModemManager/libqmi 已具备 QMAP v1/v4/v5 和 rmnet 能力，但当前 OpenWrt `modemmanager.sh` 没有把 multiplex 设置接到 netifd；“库支持”不等于此镜像已经在用。
- 新项目 wwand 宣称用 rmnet 做双向 QMAP、UL coalescing、QMAPv5 checksum，并让 netifd 持有路由；这个方向与本次缺口吻合，但项目较新，独立长期口碑不足，适合实验而非直接替换稳定默认。
- RM520 社区个案曾报告 ECM 约 240–260 Mbit/s、MBIM 约 600–700 Mbit/s；另有用户认为 ECM 稳定。此类结果支持“聚合与 USB composition 会产生明显差异”，但运营商、射频、小区、主机和固件不同，不能移植为本机保证值。

参考：

- Quectel RG520N 产品页：<https://www.quectel.com/product/5g-rg520n-series/>
- Quectel Linux USB Driver Guide V3.2：<https://quectel.com/content/uploads/2024/04/Quectel_UMTS_LTE_5G_Linux_USB_Driver_User_Guide_V3.2.pdf>
- Linux rmnet 文档：<https://cdn.kernel.org/doc/html/latest/networking/device_drivers/cellular/qualcomm/rmnet.html>
- Linux qmi_wwan sysfs ABI：<https://github.com/torvalds/linux/blob/master/Documentation/ABI/testing/sysfs-class-net-qmi>
- ModemManager WWAN device types：<https://modemmanager.org/docs/modemmanager/wwan-device-types/>
- wwand reference：<https://github.com/ddimension/wwand/blob/main/docs/reference.md>
- RM520 ECM/MBIM 社区速度个案：<https://forums.quectel.com/t/unusually-low-speeds-in-ecm-mode-compared-to-mbim-on-rm520n-eu/46170>

## 固件决策

### 现在应保留的默认值

- 继续让主线 `qmi_wwan` 成为唯一自动加载并拥有 `2c7c:0801` 的 QMI 驱动。
- 不把 `qmi_wwan_q` 与主线 qmi_wwan 同时 autoload；否则插拔/启动时会产生不可重复的 USB interface 抢占。
- 已完成的 5gmodem 接口状态、自动创建、注册/信号、fw4 同步和 metric 修复继续固化；它们解决的是控制面/配置一致性，不冒充 PPE 修复。
- 在硬件 PPE 未闭环时启用软件 flow offload，并优先把 QMAP/UL aggregation 做成可回滚的独立 profile。

### 后续实现顺序

1. 完成 `qmi_wwan_q` + CM 的受保护 A/B 测试，只在它显著胜出且恢复/路由/fw4 全部稳定后，才提供“实验性高速 QMI”选项。
2. 增加 `kmod-rmnet`，把 qmi_wwan pass-through、WDA QMAPv5、rmnet mux、netifd route/firewall 生命周期做成一体，和 vendor 路线同场对比。
3. 切换 USB composition 做 MBIM 对照；若性能接近而生命周期明显更稳，可作为优先高速方案。
4. PPE 修复另立内核任务：定义 raw-IP/QMAP 的 PPE egress 表示、point-to-point next-hop、mux parent/child、TX L2 去头、RX/DL 方向、Wi-Fi WED 与有线 LAN 两条路径；不能把它塞进 5gmodem shell 修复。
5. 用 LAN 终端持续流量验收硬件 BIND；路由器本机发起的 iperf 只测 USB/驱动/空口，不测 NAT/HNAT。

## 与 5gmodem 现有修复的关系

- “一直初始化但温度正常”和四项信号为空：由 SIM/CS/PS/EPS/5GS 注册状态混用、详细信号查询被错误 REGOK 门槛挡住造成；不是 PPE，也不需要 USB crash 才能发生。
- 手动删除接口后概率创建失败：由网络 section 存在性未纳入常驻检测、一次性前端 UCI 快照、自动协议沿用旧选择、创建/回退并发和缺少统一操作代次造成；不是 PPE。
- 调整优先级后子网无法上网：现场 fw4 生效规则没有 wwan0 forward/NAT，这是立即断网的直接原因；PPE 未 BIND 只会让恢复后的流量走软件路径。
- 已修复并固化到本地固件构建：共享运行状态、缺接口自动恢复、创建锁、显式 auto 检测、状态/信号域拆分、metric 非冲突分配、fw4 同步，以及 KuCat/Argon 背景和 `#f0d1d9` 默认主色持久化。
- 尚未修复：MTK PPE 对 QMI raw-IP/QMAP 的完整硬件 offload。这是独立的内核数据面工作，不能借更换 5gmodem 插件或 qmi 拨号程序自动得到。

## 当前实机状态和恢复动作

在 qmi_wwan_q 测试中远程管理路径失联后，多次 ZeroTier SSH 均返回 `No route to host`。本地到该 ZeroTier 地址的路由仍正确，故当前更符合远端节点/underlay 不在线，而非本机路由误选。

由于 qmi_wwan_q 只从 `/tmp` 手动加载、没有持久化，设备断电重启后应自动回到固件主线 qmi_wwan。恢复后先采集 boot ID、USB/xHCI/IRQ 日志、驱动绑定和路由；确认无 #65 特征后，再以管理路由保护方式补测 qmi_wwan_q，最后恢复 5gmodem 原状态。
