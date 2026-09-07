# R3 Mini 实机修复与验收（Autoneg-r5）

## 发布范围

保持原有 2 GiB 目标布局，只交付 sysupgrade FIT；不再制作 eMMC 上位机刷写包。
新包和镜像统一放到 `.r3mini-output/autoneg-r5`，旧镜像不覆盖。
基础版本仍为 24.10.2，发行标识升级为 `GLaDOS-R3Mini-Autoneg-r5`。

## 已定位并实机确认

- **5 GHz 连接失败**：r4 的双频 profile 合并向已有的空 `MacAddress1=` 后
  追加同名键。驱动读第一个匹配项，导致 ra0/rax0 最终使用相同 BSSID。
  修改真正的 C 合并函数，改用替换/插入，并排除未启用 VAP 的越界索引。
  重编译 mt_wifi 模块、备份后热更新；实机两频 BSSID 已不同，用户确认
  5 GHz 可以连接且 160 MHz 正常。HNAT、WARP 不因该修复而禁用。
- **无线灯**：旧 LED 配置绑定不存在的 phy0-ap0/phy1-ap0，改为真实的
  ra0/rax0；首次初始化与保留配置升级均覆盖，升级只迁移旧默认接口名。
  实机 brightness 均为 1，用户确认两灯均亮。
- **主题设置**：Kucat 3.x 上游明确不再支持 advancedplus 的旧整合配置，
  因此选独立 luci-app-kucat-config 与 luci-app-argon-config。
  实机安装时保留原有 Kucat conffile。另修复配置脚本空 preset 时的
  未引用 mode 比较及自动重置基础配色；对应包为 2.2.1-r20260907。
- **调制解调器菜单**：首次初始化/每次升级后，把 ModemManager 状态及
  mmconfig 频段设置迁移到 `admin/modem`，并安装父菜单；不依赖插入模块
  才生成这两个入口。
- **SSH banner**：LAN/WAN/Uptime、Time/OpenWrt/Build 两行及 Firmware、
  Board、Powered by 三行均按 Logo 的 128 列画布居中；底部三行不隔行。
  已采集真实交互 SSH 输出并渲染成等宽截图，逐行检查中心偏差不超过 1 列。

## PWM 风扇

新增专用 `luci-app-r3mini-fan`，位于系统菜单。此板反向 PWM 的 cooling-levels
为 255/128/80/0，不能使用把 255 当全速的通用风扇脚本。

插件调节内核 active trip（默认低/中/高 45/55/65°C），保留 step_wise 自动
温控、只读 2°C 回差及 hot=120°C/critical=125°C 保护，不引入常驻轮询守护进程。
实机逐档验证 PWM 为 128/80/0，对应输出 duty 5020/3137/0 ns（周期 10000 ns）。
进一步临时降低阈值后，内核自动进入 3 档；恢复默认阈值后回到 0 档。
用户确认测试期间风扇实际转动。没有 fan1_input，页面明确不显示虚构 RPM。

## PCIe 与 M.2 USB 的边界

空的外部控制器 `11280000.pcie` 没有绑定驱动。对该未绑定控制器做一次 probe
复现 `detect.quiet (0x1)`、link down 和 `-110`，与没有端点响应相符。
`lspci` 的 00:00.0 属于 `18000000.wbsys` 下的 WiFi RBUS 模拟 PCI 配置空间，
不是 M.2 设备。DTS 补上真实 x1 的 max-link-width，只修正缺少宽度属性的警告；
不会谎称它能解决空槽的链路超时，也不禁用控制器来隐藏错误。

USB xHCI 与相关 QMI/MBIM/NCM/RNDIS/usbnet 驱动已就绪；HNAT 已登记 usb、wwan、
rmnet 等外部网络前缀。源码具有 external-device 的 PPE 注入与返回路径，
但不能仅凭前缀登记推断所有 raw-IP 模式都可卸载。目前无 USB/M.2 外设，
尚不能验证真实协商速率、USB 网卡/Modem 的 PPE BIND 或吞吐。
USB 总线传输本身不是网络 HNAT；存储设备也不适用网络硬件加速概念。

## daed / HNAT 临时全直连实测

源码不设置两者互斥，保留 QoSmate 的独立接口队列冲突保护。
LuCI 显示服务与 HNAT hook 的独立状态，并注明已卸载流可能绕过软件分类。
初查的确只有空配置服务，不能视为转发验收。得到用户明确授权后，在独立的
临时数据库运行相同 daed 二进制，API 仅监听 127.0.0.1。配置为 LAN=br-lan、
WAN=eth1、dial_mode=ip、fallback=direct；53 端口 must_direct 保留原有 DNS。
原数据库、UCI 均未改写，所需临时 sysctl 先备份后恢复。

2026-09-07 实机结果：

- LAN ingress/egress 与 WAN ingress/egress 四个 eBPF 程序实际挂载，且通过
  BPF_PROG_GET_FD_BY_ID / BPF_OBJ_GET_INFO_BY_FD 只读工具确认执行计数增长。
  结束采样时四个程序的 run_count 分别为 2740、2574、10862、3890。
- HNAT 全程 enabled，preferred=ppe0、active=ppe0。初始两 PPE 的 BIND 数
  都为零，随后 5 GHz 手机的新连接在 PPE0/PPE1 双向建立 BIND，排除了只看到
  开启 dae 之前旧卸载连接的解释。
- 同一 443 端口连接在 3 秒内：上传硬件计数从 21262 bytes/305 packets
  增至 53506/750；下载从 762367/504 增至 1729911/1146。
  结束采样同时还观测到另一条 8080 端口连接的双向 BIND。
- NETSYS_V2 表项 info2：上行为 0xf08400，即 dp=2（GMAC2）；下行为
  0xfa9000，即 dp=8（WDMA0）、winfoi=1。结合无线客户端 MAC，确认回程
  使用无线硬件 DMA 目标，而非仅仅记录 CPU 转发。
- tc 输出中的 not_in_hw 描述的是 **eBPF 分类程序本身**在 CPU 执行，
  不能拿这个字段否定后续独立的 MTK PPE/WDMA 卸载。

结论：**当前固件的临时全直连配置下，daed 与 HNAT 可以共存；5 GHz 客户端
经有线 WAN 的 IPv4 双向直连流量确实进入硬件加速。** 不把这个结论扩大到
未配置的真实代理节点、domain/domain++ 嗅探、动态分流切换、IPv6、空闲未接线
的 eth0 LAN 口或没有外设的 USB/Modem 路径。规则改变时已有硬件流可能仍绕过
软件重新分类，需要单独验收；本次没有关闭 HNAT或清空全表。

测试结束已退出临时实例，恢复 sysctl 和 BPF accounting 原值，原 UCI 经 cmp
完全一致；原数据库用户/配置/节点/订阅计数仍全部为零。原 daed 服务恢复运行，
但保持其原来的空配置，不遗留临时全直连策略。HNAT 仍为 enabled。

## 固件产物

- 源码提交：`2cda333a73`（本节实测记录属于后续文档提交，不改变固件载荷）。
- 10 个构建阶段全部成功；37 项回归测试通过，配置验证为 956 包无缺项/冲突。
- 文件：`.r3mini-output/autoneg-r5/targets/mediatek/filogic/portalwrt-24.10.2-glados-r3mini-autoneg-r5-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb`
- 大小：255198293 bytes；production 分区仍为 2147483648 bytes（2 GiB）。
- SHA-256：`1087f0fa31e5ebe605c94edb2616d31b8c41dafdfca45573b0b9e7d50751e97d`。
- FIT 内各段哈希、GPT、版本、实际 squashfs 包/脚本检查全部通过。
- 新镜像 mt_wifi.ko 与实机已验证模块 SHA-256 相同：
  `f7a5ea5a1763f763fb435ec3dca59b6910c3dcbfac45db2e4fe694c385376afe`。
- 旧基线/r4 镜像校验值不变，旧 package 备份与 bin/packages 同名文件逐内容
  比较一致。该次构建验收尚未刷机；后续保留配置升级结果见下节。

## 后续实机保留配置升级（2026-09-07）

用户明确授权远程保留配置升级后，已完成 r4 → r5 的实际 sysupgrade。
刷写前在设备上核对镜像 SHA-256，`sysupgrade -T` 返回 0；使用标准保留配置
升级，不加 -n/-F，不刷 bootloader、不重分区。设备既有 production 分区此前
已经扩到接近整个 eMMC，因此保留的是约 7 GiB overlay，而非把现有分区缩回
镜像构建模板的 2 GiB。升级后通过原 ZeroTier 地址重新登录成功。

升级前后配置归档均保存到本地私有目录（目录 0700、文件 0600），只比较内容，
不输出密码或私钥。比对发现 LuCI 主题选择从 Argon 变为 Kucat、TurboACC
fullcone 从 2 变为 0；已依照升级前备份恢复两项配置，同时恢复运行时 NAT
模式为 2。恢复后 81 个 `/etc/config/` 文件中 80 个完全一致，唯一变化为
`uci-defaults-log.txt` 初始化日志。SSH 主机密钥、shadow、banner 脚本以及
自动恢复服务启停状态的脚本也完全一致。这两处首次启动默认值覆盖现象记录为
后续版本需要修正的保留配置迁移问题；本次设备配置已恢复，不宣称源码已修正。

冷启动后核验：版本确为 r5，ZeroTier 使用原身份在线；WAN 自协商为 1 Gbps
全双工；2.4 GHz 为 HE40，5 GHz 保留 HE160，两频 BSSID 不同；无线两灯均亮。
HNAT enabled、PPE0 专用路径正常，mt_wifi/mtk_warp/mtk_warp_proxy/mtkhnat
模块均已加载，Wi-Fi 模块哈希与构建验收一致。PWM 插件在启动时自动应用
45/55/65°C 阈值，CPU 约 40°C 时为 0 档，符合配置。两主题设置插件及 Modem
父/子菜单已安装，r5 的交互 SSH banner 截图再次通过视觉确认。

启动日志中不再出现缺失 max-link-width 的警告；空 PCIe 插槽仍出现
detect.quiet/-110，符合前述验证边界。早期时钟 -517 后有再次 probe，属于
初始化依赖尚未就绪的延迟探测。此次启动采样时没有无线终端关联，未把空闲
PPE 的 BIND=0 当作硬件故障，也未冒称升级后重复完成了流量/吞吐实测。

本地证据：`.r3mini-checks/r5-upgrade-20260907/postcheck.txt`、
`config-comparison-final.json`、`banner-r5.png`。配置归档包含设备私密信息，
不提交 Git，也不对外共享。

## 回归与证据

`scripts/r3mini-r5-test.py` 编译实际驱动 profile 解析/合并 C 函数，使用
ASAN/UBSAN 覆盖双频、多个 VAP、重复合并；同时验证 banner 格式、风扇只修改
active 阈值和拒绝非法配置，以及 Kucat 无 preset 的保留配置路径。
镜像验收脚本检查真正安装到 squashfs 的包版本与修复文件，不只检查源码。
实机采样与 banner 截图保存在 `.r3mini-checks/r5-live-20260907/`（不提交设备信息）。

上游参考：

- https://github.com/sirpdboy/luci-theme-kucat
- https://github.com/sirpdboy/luci-app-kucat-config
- https://github.com/jerrykuku/luci-theme-argon
- https://github.com/frank-w/BPI-Router-Linux/blob/6.12-main/arch/arm64/boot/dts/mediatek/mt7986a-bananapi-bpi-r3-mini.dts
- https://github.com/daeuniverse/dae/blob/main/docs/zh/how-it-works.md
