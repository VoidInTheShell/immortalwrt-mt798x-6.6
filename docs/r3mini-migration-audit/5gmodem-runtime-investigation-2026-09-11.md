# 5gmodem 接口与状态检测调查（2026-09-11）

## 范围与取证方式

用户报告删除接口后重建概率失败、状态长期显示初始化，随后补充插入广电 SIM 后 RSSI/RSRP/SINR/RSRQ 全为空。
在用户授权的 ZeroTier 设备上读取 UCI、netifd、插件现存缓存、系统日志和脚本校验值，并通过插件自带 AT 互斥队列执行查询命令。
未主动重建接口、修改 UCI、执行 ifup/ifdown、重启服务或模组；插卡由用户执行，后续 APN 更新和拨号由设备原有后台逻辑执行。
执行了绑定 wwan0 的两包 ICMP 连通性验证。未保存密码、完整 IMEI、IMSI、ICCID。

源码基准：`package/5gmodem-feed/luci-app-5gmodem`，2.4.60-r1；包目录有原有本地修改，本次未编辑插件代码。
实机 `mkiface.sh`、`5gmodem.sh`、`mm-inhibit.sh` 的 SHA-256 与本地源码逐一相同。
实机前端为压缩版本，校验值不同；直接检查部署 JS 中的初始化条件和 mIfExists 条件，与本地对应逻辑一致。

## 现场时间线（设备时间，CST）

| 时间/阶段 | 证据 | 解释 |
| --- | --- | --- |
| 10:44:02 | `mkiface: auto -> saved user choice (modemmanager)` | 手动选择 auto 后，后端仍先沿用已保存的 MM 选择 |
| 10:44:05 | `MM never assembled it ... switching interface modem to proto qmi (cdc-wdm driver qmi_wwan)` | 后台再次重建接口，改为 QMI |
| 10:46:26 | `kernel_proto_prepare failed for modem (qmi) - bringing it up anyway` | 后台 QMI 准备失败，仍执行拨号；无法据此确认当时准备失败的底层原因 |
| 插卡前 | CPIN 返回 `+CME ERROR: 10`；CREG/CEREG 为 `2,0` | 模组未检测到 SIM；用户后来确认当时确实没有插卡 |
| 插卡前 | netifd `up=false, pending=false, autostart=false, errors=SIM_ILLEGAL_STATE` | QMI 放弃重试；UCI 中没有 `auto=0` |
| 插卡前 | 新鲜缓存温度 42–43°C，registration=0，signal/ipaddr 为 `-` | 无卡错误被注册解析覆盖，前端显示初始化 |
| 11:21:35 | `SIM change (IMSI) on modem`，`autoapn ... APN cbnet (was internet)` | 插卡检测和自动 APN 匹配在本次现场有效 |
| 11:22:19 | `autoapn: waited 24s for network registration (no MM)` | 自动 APN 流程等待注册后继续拨号 |
| 11:22:26 | `modem_4 ... lease ... obtained`，子接口 up | 自动拨号成功，取得 IPv4、网关和 DNS |
| 插卡后 | `CPIN: READY`，`CEREG: 2,1,...,7`，`CREG: 2,3`，`CSQ: 28,99` | SIM ready、LTE 数据域注册成功，但语音域注册拒绝 |
| 插卡后 | 缓存 age=3，IP 已有、signal=90、mode=LTE，但 registration=3、pband=`-` | 后端总状态错误地沿用语音域状态，阻断详细指标采集 |
| 连通性验证 | `ping -I wwan0 -c 2 -W 2 1.1.1.1`：2 发 2 收 | 确认蜂窝接口具备实际外网连通性 |

当前采用 QMI，ModemManager 的只读检查为 needed=0、running=0；本次没有证据证明 MM 当前仍占用控制通道。

## 已确认的问题

### 1. SIM 错误被 CREG 覆盖，前端把无卡归入初始化

`root/usr/share/5gmodem/5gmodem.sh:1322` 先识别 CPIN/CME 错误，随后 `:1343` 无条件用 CREG 重写 REG。
现场 `CME ERROR: 10` 加 `CREG: 2,0` 最终输出 registration=0，丢失 SIM not inserted。
`htdocs/luci-static/resources/view/modem5g/5gdetail.js:1615` 在非注册状态且无信号时显示 Initialising modem，未将无卡、停止、缺接口等作为独立状态。
温度在 Quectel profile 最前面单独读取，因此无卡时仍正常显示。

### 2. LTE 数据域与语音域混用，导致四项信号全部被跳过

`5gmodem.sh:1368` 只在 CREG 为 6/7 时允许 CEREG 的成功注册覆盖；CREG 为 0/2/3 时，即使 CEREG=1 也不采用。
`5gmodem.sh:1944` 据此生成 REGOK。
`root/usr/share/5gmodem/modem/usb/2c7c0801:32` 把 QENG/QCAINFO 等详细指标查询整体放在 REGOK=1 内。
现场数据连接成功，CREG=3，导致 registration=3、REGOK=0，RSSI/RSRP/RSRQ/SINR 和频段缺失。
这一条件还影响 `5gdetail.js:2034` 的简洁视图和 `:2087` 的连接成功判定。

实机原始查询片段：

```text
+QENG: "servingcell","NOCONN","LTE","TDD",460,15,111CB1E,44,36275,34,4,4,10DE,-86,-10,-56,11,8,-30,-
+QCAINFO: "PCC",36275,75,"LTE BAND 34",1,44,-86,-10,-57,2
```

使用本地原始 profile、模拟 sms_tool 只返回上述采集回复进行离线回放，无实机写入：

```text
REGOK=0 RSSI=- RSRP=- RSRQ=- SINR=- PBAND=-
REGOK=1 RSSI=-57 RSRP=-86 RSRQ=-10 SINR=2 PBAND=B34 @15 MHz
```

该回放确认采集条件是本次缺失的直接原因；SINR=2 是现有 profile 对原始字段的换算结果，本次未另行认证不同固件的 SINR 单位约定。

### 3. 删除 network 接口后，常驻检测缺少触发条件

- `modemswitch.sh:1168` 的 autosetup 本身能发现被引用的 network section 不存在。
- `sessionwatch.sh:775` 只检查物理模组对应的 5gmodem section 是否存在；它不检查 section 中 network 引用是否失效。
- `msw/iface.sh:38` 遇到 network section 不存在直接返回。
- `modemswitch.sh:1562` 又会把非空的失效引用复制到全局 network 字段。
- 安装的 postinst 和 USB hotplug 会调用 autosetup，但手动删除 network section 不会产生同样的 USB 事件。

因此“模组记录仍在、network section 已删除”在没有其他触发时会漏掉自动配置。此项为源码确认；本轮没有重新删除实机接口来复现。

### 4. 手动停用和失败停止的处理不统一

`sessionwatch.sh:265` 把 autostart=false 一律视为手动停止；QMI 的 SIM_ILLEGAL_STATE 也通过 proto_block_restart 产生同样状态。
`health.sh:923` 有进一步区分，但现场 health/healing 都关闭。
相反 `msw/iface.sh:199` 只看 up/pending，未检查用户的 auto/disabled 意图便可能 ifup。
本次插卡后的恢复由 autoapn 完成，不能据此断言普通监测已覆盖所有失败恢复情形；APN 不变或手动 APN 模式尤其需要回归测试。

### 5. auto 选择、后台回退和创建结果之间缺少统一协调

`mkiface.sh:670` 在 REQ=auto 时优先采用旧的 iface_proto；现场日志证实点击 auto 后先使用旧 MM 协议。
`mm-inhibit.sh:435` 以 qmihint/qmiswitch 标记进行后台回退，调用 mkiface 重建接口，并在自动回退时清除保存的 iface_proto。
手动入口、autosetup、后台回退之间没有共享的 mkiface 创建锁；resolve 自己的锁并不能覆盖它们。
`mkiface.sh:934` 删除并重写 network section，`:980` 提交并 reload，后面才完成归属/排除标志等处理；异步准备和拨号最后继续运行。
成功 JSON 只表示配置流程结束，并不表示拨号成功。更早启动的后台等待者也没有检查接口操作代次，可能对后续重建的同名接口执行 ifup。

### 6. 前端存在性判断是一次性的 UCI 快照

`5gdebug.js:843` 的 mIfExists 只判断加载时的 network section，不查询 netifd。
`:1382` 调用 mkiface；成功后刷新协议徽标/部分 profile 卡片，未重载用于整个表单的 UCI 快照。
后台换协议或其他页面删除/停用接口后，按钮、APN 和认证相关字段可能继续使用旧状态。

### 7. 次要但明确的误导日志与配置保留问题

`lib.sh:1302` 对 QMI 主动跳过代理，`:1341` 却仍打印 proxy not responding；该日志不能作为代理故障证据。
`mkiface.sh:934` 重写接口只保存有限选项，auto/disabled、MTU、部分路由/DNS策略等手工设置不在该保留列表。
`lib.sh:273` 的 note_foreign_uci 仅记录共享暂存区变化，不能阻止提交其他未完成的 network/firewall 修改。

## 尚不能确认的部分

现存日志没有找到 `cannot create interface` 或 rpcd 的对应失败条目，本轮也未点击重建或删除接口。
因此不能把用户看到的概率性“创建失败”具体判定为某一次 RPC 超时、空 JSON、控制节点暂时消失或并发 UCI 写入。
已证实现场存在短时间连续重建及后台准备失败；它们提供了重点调查方向，但不等于已复现按钮失败。
此外缓存 operator_name 出现 `N-V^u5`，疑似独立的中文运营商名称编码/来源处理问题，尚未完成原始字符串取证。

## 补充：切换网络优先级后，子网设备无法上网

用户确认受影响的是路由器下游设备。11:32–11:39 的只读检查确认：

- UCI 和内核 IPv4 路由均为 modem 优先：`default via 10.1.253.4 dev wwan0 metric 100`，有线 eth1 为 metric 110；`ip route get 1.1.1.1` 正确选择 wwan0。
- IPv4 policy rules 只有 local/main/default，没有额外策略表劫持本次测试。netifd 内存中的 modem/动态子接口 metric 仍为 110，符合 netpri 直接改内核路由、不 reload netifd 的实现，不能把该差异直接判定为断网原因。
- 路由器绑定 wwan0 和不绑定接口的 ping 均 2 发 2 收；绑定 wwan0 的百度 HTTPS HEAD 返回 HTTP 200；本机 DNS 查询成功。
- UCI WAN 区包含 `wan wan6 mifi modem`，masq=1，存在 lan→wan forwarding。
- **实际 nftables 的 `accept_to_wan` 和 `srcnat` 仅匹配 eth1、eth2，不含 wwan0。** LAN 发出的蜂窝新连接无法匹配 WAN 放行，最终走 reject；蜂窝出口也没有对应的 masquerade 跳转。这是当前子网断网的明确阻断点，与路由器自身可用不矛盾。
- `/var/run/fw4.state` 时间仍为 10:43，保存的 modem 为 up=false、device=null；`fw4 -q network modem` 和 `modem_4` 均退出 1。
- 实机 `/etc/hotplug.d/iface/20-firewall` 先调用该查询判断归属，失败后再看接口 data.zone；当前父/子接口均没有 data.zone。因此会在 has_zone 门槛退出，不触发 reload。日志中也没有本次 modem 插卡连通后的 firewall reload。注意：`fw4 network` 实际遍历缓存的 `zone.network[].device`，不是直接检查 up 值；查询失败说明缓存缺少逻辑区域关联，不能简单归因于 up=false。`state.networks` 中有 modem 也不等于 zone.network 已纳入它。
- **只读执行 `fw4 print` 后，新生成的规则正确包含 wwan0 的 forward、NAT 和 MSS 规则。** 未将预览结果应用到系统，确认问题是配置/运行态未同步，不是 UCI 根本缺少 modem。

源码链路：

1. `mkiface.sh:69` 的 `_fw_zone_add()` 只做 UCI 修改和 commit，没有应用防火墙；QMI 路径 `:992` 先 reload netifd，`:1028` 才添加 WAN 区关联，存在顺序窗口。
2. fw4 的 hotplug 查已加载的逻辑区域关联，而不是直接查最新 UCI；新增关联只 commit、不应用，会导致旧区域快照无法在本现场触发自更新。这不是“所有 down 接口都无法触发 fw4”的一般性结论。
3. `netpri.sh:1340`/`:1511` 只改 metric 与实时路由，不验证出口是否已纳入生效的 forwarding/NAT。于是优先级切换暴露了此前隐藏的蜂窝转发缺口。

实机 netpri.sh SHA-256 为 `3782c5142fde7762e4d20538d27b199eaaf29dce7d7aa184560580a34dbffcfa`，与本地相同。
短时仅采集报文头的 LAN 抓包窗口没有捕获测试 SYN/ICMP，故本轮没有下游端到端重放结果；上述阻断判断来自完整的生效链规则。
恢复后的端到端验证仍待执行，不能声称重载已经解决现场问题。

## 补充：USB modem 的 PPE/HNAT 状态

当前只能确认加速基础通道已就绪，**尚不能验收 USB 蜂窝硬件加速正常**：

| 检查项 | 实机结果 |
| --- | --- |
| 蜂窝驱动/模式 | qmi_wwan，wwan0，raw_ip=Y，USB 2-1:1.4 |
| HNAT 驱动 | mtkhnat 已加载 |
| 外部设备注册 | external_interface 明确列出 wwan0，以及 ra0、rax0 |
| 内部注入通道 | hnat_ppd_if：preferred=ppe0 active=ppe0；ppe0 UP、LOWER_UP |
| 通道计数 | 两次 ppe0 采样 RX 16201→18716 包、TX 18280→20795 包；不是蜂窝专属计数 |
| 硬件绑定 | 多次 hnat_stats 均 BIND_PPE0=0、BIND_PPE1=0；all_entry 的 BIND 计数也为 0 |

流表见到以蜂窝地址为目标的 UNBIND 条目，只能说明相关数据进入了学习路径，不能当成硬件转发成功。UNBIND 中未初始化的改写地址也不能当作生效 NAT 映射。
当前 LAN→蜂窝在防火墙处已经被阻断，且抓包窗口没有下游测试流；不能把 BIND=0 单独归因于 raw-IP 驱动不支持或 PPE 损坏。
本机 ICMP 不在该驱动 `is_ppe_support_type()` 所接受的 TCP/UDP 类型中，也不能用 ping 成功证明 PPE 工作。
实机采用厂商 mtkhnat 路径，不能单凭 nft flowtable 列表为空就推断硬件加速关闭。

下一步需同步防火墙运行态，再由 LAN/Wi-Fi 终端产生持续、直连、双向 TCP/UDP 流，关联蜂窝 NAT 地址与 PPE BIND 条目及包/字节增量；必要时分别验收有线 LAN 和 Wi-Fi。不需要先改 APN、重拨或关闭硬件加速。

### 后续授权与现场变化

用户已明确允许重载一次现有防火墙配置并继续验收。11:41:32 重载前基线仍为规则缺失 wwan0、BIND 全为 0。附加脚本及规则预检期间连接中断；**尚未执行 firewall reload**。用户随后确认自行断电重启，且设备仍在启动中。重启后的现场必须重新采样；即使之后恢复，也不能归因于本次尚未执行的重载。重启前的故障证据与待确认项保留如上。

### 第一次重启后的采样与再次暂停

11:47:03 恢复连接，uptime 约 2 分钟；modem 为 QMI、up=true，蜂窝地址更新为 `10.1.121.238/30`，默认路由 `via 10.1.121.237 dev wwan0 metric 100`，有线 metric 110。

- 生效 nftables 的 accept_to_wan、srcnat 均已包含 wwan0，故没有再执行重载。
- 后续 conntrack 中多条 `src=10.0.1.182` 的 TCP 连接已 ASSURED，回复方向的 NAT 地址为 `10.1.121.238`，双向包/字节均增长。这是子网蜂窝转发已恢复的实机证据，不只是路由器本机 ping。
- HNAT hook_toggle=enabled、external_interface 仍列出 wwan0、ppd active=ppe0。
- 11:49:30–11:49:42 每 3 秒共 5 次采样 BIND 均为 0。流表出现终端上下行 UNBIND 条目，其中一个下行条目已填入 NAT 改写和终端 MAC，并有 bytes/packets；**填表或历史计数不等于当前已 BIND**。
- 11:50:34–11:50:50 收到 5 个采样：wwan0 RX 14,227,991→14,256,558 字节，仅约 28.6 KB/16 秒，BIND 仍全为 0。该窗口没有形成持续大流量测试，不能以它证明驱动在达到绑定阈值后仍失败。最后 SSH 未正常 EOF，不将其视为无缺失的完整实验。
- 插件重启后仍输出 registration=3、四项主信号及频段为空；状态解析缺陷没有被重启消除。

用户随后说明天线有问题，将再次断电重新连接，并要求先做本地取证。停止发起实机检查，待用户明确通知恢复后再继续。此前持续采样已结束，没有执行重载、重拨、加速开关或修改天线相关参数。

### 本地 USB raw-IP / HNAT 静态取证

核对 target 覆盖源码与当前本地 linux-6.6.133 构建树：hnat_nf_hook.c 校验值均为 `b9349b492578704c02851f337ab837e7d77f004157513532dcddd80e7359ba1d`，qmi_wwan.c 均为 `c6fdc6774f5a0319bebc799d2c546ecf6a50f0d431c31a71ff6b8a90efe24b1d`。此项确认本地编译源码一致，尚不是对实机已加载模块的二进制匹配认证。

1. `target/linux/mediatek/files-6.6/drivers/net/usb/qmi_wwan.c:312` 在 raw-IP 模式配置 ARPHRD_NONE、hard_header_len=0、addr_len=0、NOARP。`:567` 却将 RX 局部变量 rawip 固定为 0，并在 `:610` 起给收到的 IP 包补合成以太网头；因此本树已有 RX 帧格式适配，不能声称 raw-IP 完全没有适配。
2. `mtk_hnat/hnat_nf_hook.c:2491` 对非 Wi-Fi 外部出口且来源不是 FROM_WED 的报文提前返回，绕过后续绑定。对于原样到达此处的有线 LAN→wwan0 流量，该门槛本身就需要检查；Wi-Fi 与有线不能混为同一条验收路径。
3. IPv4 路由 postrouting 在 `:2777` 传入 hnat_ipv4_get_nexthop；该函数 `:1445` 查邻居，`:1454` 强制要求有效以太网 MAC。无 ARP、addr_len=0 的 raw-IP 出口没有对应豁免，构成上行绑定兼容性缺口。Wi-Fi 来源即使通过上一项，也仍面对这一条件。
4. `do_hnat_ge_to_ext():779` 对非 Wi-Fi 外部设备无条件 skb_push(ETH_HLEN) 后发送；qmi_wwan 的 ndo_start_xmit 指向 usbnet_start_xmit，driver_info 未提供 tx_fixup，usbnet 将 skb->data 直接送 USB。若仅绕过绑定门槛而不处理帧格式，可能把带以太网头的报文送给期望 raw-IP 的模组。因此不能用“删掉 return / 填假 ARP”作为安全修复。
5. 下行到 Wi-Fi 的 skb_to_hnat_info 在 `:2085` 起有意保持 UNBIND，等待厂商 Wi-Fi TX hook 填入 WDMA 信息并最终置 BIND（`:2289`）；只见 NAT/MAC 被填入并不证明这一步完成。后续应区分下行 Wi-Fi 最终绑定和上行 raw-IP 出口问题。
6. `mtk_hnat/hnat.c:365` 默认绑定阈值为每秒 30 包；现有低流量采样不能替代持续流测试。实机阈值是否被其他脚本改写，还需恢复后只读核对。

以上是本地代码路径证据及兼容性风险，不等于已经证明实机所有流量都在这些门槛失败。后续验收应分别记录方向、终端介质、持续流速率、BIND 状态及同一条目计数增量，不把天线调整、重启恢复、软件转发和硬件加速混为一项。

## 建议的修复与验收范围

1. 拆分 sim_state、CS/PS/EPS/5GS 注册、接口配置存在性、netifd 状态；SIM 错误不再被注册值覆盖，数据域成功注册可独立驱动数据业务判断。
2. 详细指标采集不以语音域注册成功作为前提；按端口可用、数据域注册和查询能力决定，并保留数据新鲜度。
3. 添加统一只读状态查询，供按钮、状态页和后台使用；覆盖缺接口、停用、pending、协议失败、已取地址等情况，并读取 QMI 的动态子接口。
4. 定义显式管理意图：用户停用/手动管理时不擅自拉起；启用自动管理且已绑定的接口缺失时执行受控恢复。
5. 创建流程加跨入口互斥和操作代次；在锁内重新检查真实目标，协调 MM/QMI 所有权后再启动拨号，避免旧后台任务作用到新配置。
6. 明确“用户重新选择 auto”和“后台沿用已选协议”的语义；后台回退应等待合理的初始化条件，并给 UI 可查询的进度和原因。
7. 创建后重读配置与实时状态；返回配置完成/连接中/缺 SIM/协议失败等结构化结果，而非泛化为创建成功或失败。
8. 回归覆盖：无卡→插卡、CREG=3+CEREG=1、删除接口但模组记录保留、auto=0、失败导致 autostart=false、APN 不变、手动 APN、手动重建与后台回退并发、多模组及动态 IPv4 子接口。
9. 创建/重建接口必须协调 netifd、WAN 区关联和防火墙应用；新出口启用后验证生效转发与 NAT，而不是只检查 UCI 中的区域归属。同步失败应返回明确阶段错误，不能继续将其当作已就绪出口。
10. 优先级调整回归需同时测试路由器自身和 LAN/Wi-Fi 子网新连接；恢复正常转发后再独立验收 USB PPE，避免把防火墙阻断误诊为加速失败。

本文件为调查结果，尚未实施或部署修复。
