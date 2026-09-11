# R3 Mini ModemManager 与 USB 驱动兼容性核查

本报告核对 USB 基线；后续最大驱动覆盖补充见 [modem-extra-drivers.md](modem-extra-drivers.md)。核对了当前 BPI-R3 Mini 设备树、Linux 6.6.133 源码、OpenWrt 内核包定义，以及 r7 采用的 ModemManager 1.24.2、libqmi 1.38.0、libmbim 1.32.0。核查结果已经写入 [modem-required.config](modem-required.config)。目标库、MM、驱动和完整 rootfs 已完成 AArch64 编译、镜像检查和 r7 实机启动；RG520N-CN 已实测由 `qmi_wwan`、`option1` 和 Quectel 插件枚举出 QMI/AT/GPS/net 端口。设备当前无 SIM，因此注册、信号和 bearer 仍须插卡验证。

结论是采用 Linux 主线 `qmi_wwan` 作为唯一 QMI WWAN 实现，并同时保留主线的 USB 串口、CDC ACM、MBIM、NCM、ECM、Huawei NCM、Sierra Net、RNDIS、Option HSO 和 Samsung Kalmia 模块。这样覆盖常见 Quectel、Fibocom、Sierra、Huawei、ZTE、Telit、u-blox、SIMCom、Qualcomm/Gobi 和旧式 Option 设备的 USB 工作模式。专用 Fibocom/Quectel QMI 模块虽然各自带有少量额外 ID 和厂商 raw-IP/QMAP 行为，但会与主线驱动争抢同一 USB 接口；在没有针对实际模块做选择性适配前，不把它们和主线一起装入镜像。

## 设备树与总线边界

`target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts` 将 `&ssusb` 设为 `okay`，挂接 `usb_ngff_pins`，并提供 `vusb33-supply` 与 `vbus-supply`（525–531 行）。同一组引脚明确标出 `ngff-gnss-off`、`ngff-wwan-off`、`ngff-pwr-off`、`ngff-rst` 与 `ngff-pe-rst`（403–428 行），这与板载 M.2/NGFF Key-B 蜂窝模块经 USB 枚举的路径一致。底层 `mt7986a.dtsi` 的 SSUSB 节点还列出 USB2/USB3 PHY（374–394 行）。片段因此把 USB 主机、USB WDM、USB 网络和 USB 串口作为实际硬件路径。

设备树也把 `&pcie` 与 `&pcie_phy` 设为 `okay`（261–269 行）。PCIe 端点可以自动枚举，无固定端点节点不能作为排除 PCIe modem 的理由。按用户追加的最大兼容要求，最终片段加入主线 MHI/WWAN、QRTR-MHI、T7xx 和 IOSM；这是为实际 PCIe/M-Key 转接设备预装驱动，不代表板载 USB Key-B 能传输 PCIe，也不保证任意转接板、电源、MSI/DMA 或缺失的模块固件都能工作。依据及边界见 [modem-extra-drivers.md](modem-extra-drivers.md)。

`kmod-wwan` 在 `package/kernel/linux/modules/netdevices.mk` 1946–1960 行只是通用 WWAN 框架，且 MHI 控制包显式依赖它（1978–2008 行）。本树的 `qmi_wwan` 和 `cdc_mbim` 包定义直接依赖 `kmod-usb-net`、`kmod-usb-wdm` 及 NCM/CDC 子模块，不依赖 `kmod-wwan`。因此当前 USB MM 路径不需要为了“完整”而启用 WWAN core。

## 选入的 USB 驱动

| OpenWrt 包 | 内核模块 | 选择理由与边界 |
| --- | --- | --- |
| `kmod-usb-core`, `kmod-usb-net`, `kmod-usb-wdm` | USB core、`usbnet`、`cdc-wdm.ko` | 所有 USB modem 数据通路和 QMI/MBIM 控制节点的基础。`usb.mk` 558–586 行显示 ACM/WDM 包的实际文件和依赖。 |
| `kmod-usb-acm` | `cdc-acm.ko` | CDC ACM AT、诊断、GPS/NMEA 或 PPP 串口；内核 Kconfig 将其描述为 modem/ISDN controller 支持。 |
| `kmod-usb-serial`, `kmod-usb-serial-wwan` | `usbserial.ko`, `usb_wwan.ko` | `usbserial` 是串口核心；`usb_wwan` 是 `option`/`qcserial` 的隐藏公共依赖（`usb.mk` 625–643、991–1004 行）。 |
| `kmod-usb-serial-option` | `option.ko` | Linux 6.6 `option.c` 表覆盖 Option、Huawei、Novatel、Anydata、Qualcomm、Quectel、u-blox、ZTE、Telit、SIMCom、Fibocom 等大量 AT/串口组合。Kconfig 554–568 行确认这是 GSM/CDMA modem 驱动。 |
| `kmod-usb-serial-qualcomm` | `qcserial.ko` | Qualcomm/Gobi 1000/2000/3000、Sierra、Dell、Novatel、HP、Samsung 等旧式或 QDL/复合设备；Kconfig 484–492 行确认其为 Qualcomm modem 串口。 |
| `kmod-usb-serial-sierrawireless` | `sierra.ko` | Sierra Wireless 的 AT/控制串口；与 Sierra Net 数据接口是不同功能，可并存。 |
| `kmod-usb-net-qmi-wwan` | `qmi_wwan.ko` | 主线 QMI 数据面；包定义（`usb.mk` 1424–1436 行）自动带入 WDM。Linux 6.6 源码不仅覆盖 Huawei/Novatel/Dell/HP/MeigLink/Qualcomm，还包含 Quectel `2c7c:0122/0125/0306/0512/0620/0800/0801`，以及大量 `05c6` 复合接口。源码支持 raw-IP、QMAP mux 与 QMI WDM 控制，适合 MM 管理。 |
| `kmod-usb-net-cdc-mbim` | `cdc_mbim.ko` | 标准 MBIM 数据面；Kconfig 294–310 行说明它通过关联的 `/dev/cdc-wdm*` 暴露未过滤 MBIM 控制通道，正好交给 MM/libmbim。包同时依赖 WDM 与 NCM。 |
| `kmod-usb-net-cdc-ncm` | `cdc_ncm.ko` | 标准 NCM 数据面；Kconfig 259–277 行列出 ST-Ericsson M700、M5730、M570、M343 与 Ericsson F5521gw 等移动宽带设备。 |
| `kmod-usb-net-huawei-cdc-ncm` | `huawei_cdc_ncm.ko` | Huawei NCM 嵌入式 AT 通道；Kconfig 279–292 行点名 E3131/E3251，并选择 WDM/NCM。 |
| `kmod-usb-net-cdc-ether` | `cdc_ether.ko` | ECM/CDC Ethernet 设备；Kconfig 217–243 行明确列出 Dell Wireless 5530 HSPA、Ericsson Mobile Broadband、Toshiba F3507g/F3607gw 等移动宽带模块。 |
| `kmod-usb-net-sierrawireless` | `sierra_net.ko` | Sierra Wireless 的 USB-to-WWAN 数据面；Kconfig 590–597 行确认用途。 |
| `kmod-usb-net-rndis` | `rndis_host.ko` | 仅作为模块处于 RNDIS USB 模式时的兼容后备。`option.c` 识别 SIMCom SIM7500/SIM7600、SIM8230、SIM7070/SIM7080 及 ZTE RNDIS 组合；不把 RNDIS 当作默认拨号协议。内核 Kconfig 400–413 行也提醒 RNDIS 仅在没有更好协议时使用。 |
| `kmod-usb-net-hso` | `hso.ko` | Option HSDPA/HSUPA 旧式 HSO 卡；包定义 1252–1266 行额外带 RFKILL，片段同步启用 `CONFIG_USE_RFKILL`、`kmod-rfkill` 和 `kmod-input-core`，避免 `CONFIG_USB_HSO` 因缺少 RFKILL 而无法生成。 |
| `kmod-usb-net-kalmia` | `kalmia.ko` | Samsung Kalmia 旧式 LTE，内核 Kconfig 521–529 行以 GT-B3730 为例；这是明确的 modem 驱动，适合“最大兼容”目标。 |

`CONFIG_USB_SERIAL_GENERIC=y` 由 `target/linux/generic/config-6.6` 提供。它是内核 `USB_SERIAL` 菜单中的 bool，不是 OpenWrt 顶层可选项，因此最终片段不写入这个无效顶层符号，也不伪造 `kmod-usb-serial-generic` 包。选择 `kmod-usb-serial` 后，用户可通过 sysfs 动态 ID 处理没有专用表项的串口接口，但实际 AT 协议和端口布局仍取决于设备。

## 明确排除的驱动

`kmod-usb-net-cdc-eem` 与 `kmod-usb-net-cdc-subset` 是通用 USB 链路/主机到主机实现；内核 Kconfig 245–257、419–432 行没有把它们定义为蜂窝 modem 数据面。`kmod-usb-net-ipheth` 是 Apple iPhone tethering，并且需要 `usbmuxd`（Kconfig 580–588 行）。`kmod-usb-serial-simple` 主要覆盖 Motorola 手机、Novatel GPS、刷写接口等“very simple devices”（Kconfig 55–77 行），不能替代 `option`/`qcserial` 的 modem 端口。它们均在片段中显式设为 `not set`，以免把无关 USB 设备目录带进目标镜像。

Linux 6.6 的 Kconfig 还包含 `USB_CDC_PHONET` 和 `USB_VL600`。前者依赖额外的 PHONET 子系统，后者需要通过 ACM 端口发送专用命令；当前 `package/kernel/linux/modules/usb.mk` 没有对应的 `kmod-usb-net-cdc-phonet` 或 `kmod-usb-net-vl600` 定义，因而不能在配置片段中伪造包名。若未来确实要支持这两个旧设备，应先补齐 OpenWrt 包定义和 MM 端口测试。

最终片段已补选主线 PCIe WWAN 栈，并新增内核已有、原包目录遗漏的 `kmod-iosm` 定义；USB 另补 `kmod-usb-serial-ipw`、`kmod-usb-serial-ti-usb` 和 TI 3410/5052 固件。它们按总线 ID/通道匹配，不与板载 USB modem 的主线驱动争抢接口。

## 主线与厂商 QMI 驱动的取舍

当前树有两个专用包：

* `feeds/packages/kernel/fibocom-qmi-wwan/Makefile` 17–23 行生成 `qmi_wwan_f.ko`，自动加载优先级 82；源码设备表包含 Fibocom `2cb7:0104` interface 4、`2cb7:0109` interface 2、`2cb7:0113` interface 0、`1508:1000` interface 2、`1508:1001` interface 4 和 `05c6:9025` interface 4。
* `feeds/packages/kernel/quectel-qmi-wwan/Makefile` 17–23 行生成 `qmi_wwan_q.ko`，自动加载优先级 81；源码包含 Quectel 常见的 `2c7c:0121/0125/0191/0195/0296/0306/030b/030e/0435/0512/0620/0700/0800/0801`，以及 `05c6:9003/9215`。`100-add-more-usb-ids.patch` 又添加 Foxconn `05c6:90d5`、SIM8200 `05c6:90db`、MeiG `02dee:4d22`、gm800 `305a:1421/1403`、`05c6:9025` 和 `05c6:9091`。

两个厂商源码的模块名分别是 `qmi_wwan_f` 与 `qmi_wwan_q`，所以它们不会按文件名直接覆盖 `qmi_wwan.ko`；问题在于三个驱动都声明 QMI WWAN USB 接口，且包的 `Conflicts:` 元数据为空。厂商源码随附的使用/安装逻辑会先 `modprobe -r qmi_wwan_f`、`modprobe -r qmi_wwan` 再加载厂商模块，这正说明它们预期替换主线绑定，不能把三者当作可叠加的“全覆盖”插件。自动加载顺序也会让同一模块在不同插拔时序下获得接口，造成不可重复的 MM 端口关联。

主线 `qmi_wwan.c` 的显式表已经包括 Quectel `2c7c:0122/0125/0306/0512/0620/0800/0801`、Qualcomm `05c6:9003`、`05c6:9025`、`05c6:9091`、`05c6:90db` 等条目，以及按 USB interface class 匹配的大量设备。`option.c` 还覆盖很多 Quectel/Fibocom 的 AT、MBIM、ECM、RNDIS 接口，因此标准工作模式在不装厂商 QMI 模块时仍有较大的覆盖面。

仍需诚实保留的缺口如下：主线 QMI 表没有 Fibocom 专用 `2cb7:0104/0109/0113`、`1508:1000/1001` 的 vendor raw-IP/QMAP 条目；Quectel 厂商驱动的 `2c7c:030b/0435/0316/0700` 以及 `05c6:90d5`、`02dee:4d22`、`305a:1421/1403` 等厂商新增组合也不能仅凭主线表宣称完全等价。对这些设备，如果标准 MBIM/ECM/NCM 或 AT 模式能够枚举，主线串口/CDC 驱动仍可能工作；如果模块只提供厂商 QMI raw-IP/QMAP 模式，应在获取真实 `lsusb -v` 与 interface 编号后，给主线 `qmi_wwan` 做一个有针对性的 ID/quirk 补丁，并单独回归 MM。当前选择主线的理由是它与 cdc-wdm、Linux hotplug、MM 的端口模型保持一致，且避免两个厂商实现共同抢占接口；不能把未测试的厂商专用行为写成已支持。

## ModemManager 与用户空间依赖

当前包定义（`feeds/packages/net/modemmanager/Makefile` 38–93 行）给出以下事实：MM 依赖 `glib2`、`dbus`、`ppp`，在开启协议时依赖 `libmbim`、`libqmi`、`libqrtr-glib`；Meson 参数固定 `-Dbuiltin_plugins=true`、`-Dudev=false`、`-Dmbim=true`、`-Dqmi=true`、`-Dqrtr=true`，并由 `CONFIG_MODEMMANAGER_WITH_AT_COMMAND_VIA_DBUS` 打开通过 D-Bus 执行 AT 命令的能力。上游 1.24.2 的各厂商插件选项均保持 `auto`，所以在协议依赖满足时按上游默认集合构建所有可用内建插件；树中不存在按插件拆分的 `CONFIG_PACKAGE_modemmanager-*` 选择项。实际编译摘要生成 488 个 target，并包含 Quectel、Fibocom、Foxconn、MediaTek、Sierra、Telit、u-blox、SimTech、QCOM SoC、generic 等内建插件。

`libqmi` 的包定义（`feeds/packages/libs/libqmi/Config.in` 4–31 行、Makefile 39–80 行）确认片段启用了 QMI-over-MBIM、QRTR GLib 和 `full` message collection；`libmbim` 1.32.0 的 Makefile提供 MBIM 库与 `mbim-utils`。当前版本组合为 MM 1.24.2、libqmi 1.38.0、libmbim 1.32.0，满足 MM 1.24 的构建下限。`qmi-utils`/`mbim-utils` 安装 `qmicli`/`qmi-network`/`qmi-firmware-update` 与 `mbimcli`/`mbim-network`，默认用于诊断；只有管理员显式把某个模组切换成 qmi/mbim rescue 协议时，它们才成为该模组的数据会话工具。

MM 的 OpenWrt 运行接线已经逐项核对：

* `files/etc/init.d/modemmanager` 第 4、23–35 行使用 `USE_PROCD=1` 并通过 procd 启动 MM 与监控包装器，所以需要 `procd`。
* `files/etc/hotplug.d/tty/25-modemmanager-tty` 第 14–16 行上报 tty；`net/25-modemmanager-net` 第 14–30 行上报 net 和关联的 cdc-wdm；`wwan/25-modemmanager-wwan` 第 13–15 行上报 WWAN 控制端口。这些路径不要求 systemd。
* `files/lib/netifd/proto/modemmanager.sh` 第 4–12 行在缺少 `mmcli` 或 `pppd` 时直接退出，并加载 netifd/PPP 公共脚本；所以即使采用 QMI/MBIM DHCP bearer，`ppp`、`netifd` 仍应保留。
* `modemmanager-rpcd` 与 LuCI 端分开打包。源码 Makefile 第 59–67 行将 RPC 包依赖声明为 `modemmanager`、`lua`、`lua-cjson`、`rpcd`；RPC 脚本第 1–4、149–169 行需要 Lua/cjson 并调用 `mmcli`。`luci-proto-modemmanager` 的 Makefile 只声明 `+modemmanager`（第 9–10 行），所以片段明确选择 `modemmanager-rpcd`、`rpcd`、`lua`、`lua-cjson` 与 `luci-base`，避免只装 LuCI 协议而缺 RPC 后端。

ModemManager 的 `-Dudev=false` 是本树 OpenWrt 集成的有意选择：包安装自身的规则和 hotplug 脚本，但 MM 走通用 sysfs/kernel-device 路径，不链接桌面版 `libgudev`。当前树没有 `libgudev` 包；`libudev-zero` 是一个提供 `libudev` 的 drop-in 包，并与 `libudev`、`eudev`、`udev` 冲突。片段保留已选的 `libudev-zero` 供其他包使用，但不把它误写成 MM 的直接依赖，也不与真实 udev 系列并选。

r7 的自动路径仍只有 ModemManager。为支持综合页面的显式救援选择，片段改为安装 `luci-proto-qmi`、`luci-proto-mbim`、`uqmi`、`umbim`、`comgt` 和 `sms-tool`；自动建接口策略不会选择这些直连协议。管理员手动切换某一模组时，页面对该模组应用 MM inhibit，避免双重占用。`luci-proto-quectel`、`quectel-cm`、QModem、旧 `luci-app-modem`、`luci-app-modemband` 以及重叠的 vendor QMI 内核实现仍禁选。

## 静态核查记录

以下检查只读取源码、包元数据、设备树和当前配置，没有运行目标程序：

1. 从 `usb.mk` 的 KernelPackage 定义逐一映射了片段中的 USB 包、实际 `.ko` 文件和包依赖；确认 `hso`、`kalmia`、`qmi_wwan`、`cdc_mbim`、`cdc_ncm`、`huawei_cdc_ncm`、`sierra_net`、`rndis_host`、`cdc_ether` 均有实际 OpenWrt 包。确认没有 `kmod-usb-serial-generic`、`kmod-usb-net-cdc-phonet` 或 `kmod-usb-net-vl600` 包定义。
2. 用 Linux 6.6.133 源码检查了 `USB_SERIAL_GENERIC`、`USB_SERIAL_OPTION`、`USB_SERIAL_QUALCOMM`、`USB_SERIAL_SIERRAWIRELESS`、`USB_NET_QMI_WWAN`、`USB_NET_CDC_MBIM`、`USB_NET_CDC_NCM`、`USB_NET_HUAWEI_CDC_NCM`、`USB_NET_CDCETHER`、`USB_SIERRA_NET`、`USB_NET_KALMIA`、`USB_HSO` 的 Kconfig 依赖、模块名和移动宽带说明。
3. 扫描了 `qmi_wwan.c` 与 `option.c` 的 USB ID 表：`qmi_wwan.c` 包含多代 Qualcomm/Gobi、Huawei、Novatel、Dell、MeigLink、Quectel 和其他复合接口，`option.c` 还覆盖 ZTE、SIMCom、Fibocom、u-blox、Telit 与 Sierra 的大量 AT/串口组合；报告对厂商专用 QMI ID 只列为缺口，不把它们与主线重复选择。
4. 读取了 MM、libqmi、libmbim 的 Makefile/Config.in 以及 MM 的 init/hotplug/netifd/RPC 文件，验证了 QMI、MBIM、QRTR、AT-over-D-Bus、FULL collection、D-Bus、PPP、procd、netifd、rpcd、Lua/cjson 和 LuCI 的关系。
5. 对当前 `.config` 的相关项做了只读对照：目标已经选择主线 USB QMI/MBIM/NCM/ECM/Huawei/Sierra/RNDIS、串口选项、MM、libqmi FULL、libmbim、qmi-utils、mbim-utils、完整综合 LuCI 和纯 MM 备用页；片段新增 HSO/Kalmia 及 HSO 所需 RFKILL，明确保持两个 vendor QMI 包和独立拨号守护进程关闭。

最后仍有一个必须在真实模块上完成的边界：USB VID:PID、interface number、模块当前 USB 模式和电源/复位时序决定某一张卡究竟会落到 QMI、MBIM、ECM、NCM、RNDIS 或 AT 路径。静态表只能证明驱动与 MM 依赖完整，不能替代插入每种物理模块后的 `mmcli --list-modems`、控制端口识别和实际 bearer 测试。
