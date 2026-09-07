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

## daed / HNAT 共存验收状态

源码不设置两者互斥，保留 QoSmate 的独立接口队列冲突保护。
LuCI 显示服务与 HNAT hook 的独立状态，并注明已卸载流可能绕过软件分类。
实机启动 daed 后 HNAT 仍为 enabled、专用 PPE0 路径仍在，且有真实 PPE BIND。
但进一步检查发现 dae 数据库没有用户、配置、节点或订阅，LAN/WAN 尚未
绑定 eBPF。因此这只能确认服务共存，**不能视为经过 dae 分流后的直连硬件
加速已经验收**。已请求用户确认临时全直连配置测试；真实代理验收还需要
用户自行配置可用节点。后续记录必须区分上述层次，不用进程状态冒充流量证据。

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
