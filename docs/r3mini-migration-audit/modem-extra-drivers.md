# R3 Mini ModemManager 驱动补充核查

核查日期：2026-09-06。

本报告专门补充 `modem-driver-compatibility.md` 中遗漏的 PCIe WWAN、MHI、
MediaTek T7xx、Intel IOSM 和旧式 USB 串口 modem 驱动。核查使用了工作区的
Linux 6.6.133 打补丁源码（`.r3mini-checks/linux-6.6.133`）、当前 OpenWrt
内核包定义和 ModemManager 1.22.0 源码。这里只做了 Kconfig、驱动 ID、依赖和
静态源码核查，没有启动完整固件编译，也没有在 R3 Mini 或任何实际蜂窝模组上
运行 `mmcli`、PCIe 枚举、拨号或 suspend/resume 测试。

## 结论

在“尽量覆盖以后可能接入的模组，同时只保留 ModemManager 一套管理路径”的
约束下，PCIe 侧可以加入主线 MHI 栈、`kmod-mtk-t7xx` 和 Intel IOSM；USB
侧应补上 `kmod-usb-serial-ipw`、`kmod-usb-serial-ti-usb`。这些模块都是按
PCI/USB ID 或 MHI 通道匹配的可选驱动，没有匹配硬件时不会接管 R3 Mini 的
USB modem、MT7986 PCIe 根端口或 NVMe 设备。

建议由配置片段选择下列包：

```text
kmod-wwan
kmod-mhi-bus
kmod-mhi-pci-generic
kmod-mhi-net
kmod-mhi-wwan-ctrl
kmod-mhi-wwan-mbim
kmod-qrtr
kmod-qrtr-mhi
kmod-mtk-t7xx
kmod-iosm
kmod-usb-serial-ipw
kmod-usb-serial-ti-usb
```

`ti-3410-firmware` 和 `ti-5052-firmware` 可以与 `kmod-usb-serial-ti-usb`
一起编入，以支持处于 boot/无固件状态的 TI 3410/5052 设备；Multi-Tech
MTS modem 使用的 `mts_*.fw` 在当前树中没有对应固件包，不能把它们误报成已
经完整覆盖。主线 MHI PCI 驱动中的 Qualcomm/Quectel/Foxconn/Thales 固件路径
同样没有在当前树中找到配套的闭源固件包，设备如果停留在可下载固件的启动状态，
仍需另外提供与模组型号匹配的固件。

不要把以下包作为“增加覆盖率”的手段加入：

```text
kmod-pcie_mhi
kmod-pcie_mhi_fb
kmod-qmi_wwan_f
kmod-qmi_wwan_m
kmod-qmi_wwan_q
kmod-qmi_wwan_s
kmod-qmi_wwan_nss
kmod-usb-net-qmi-wwan-fibocom
kmod-usb-net-qmi-wwan-quectel
kmod-qrtr-smd
```

前两类是厂商拨号/侧带实现，可能带入 `quectel-CM-5G`、`fibocom-dial` 或
其它独立连接服务；vendor QMI 实现会和主线 `qmi_wwan.ko` 对同一 USB
interface 竞争；`qrtr-smd` 是 Qualcomm SoC 的 SMD/RPMSG 路径，不是 R3
Mini 的 PCIe modem 必需组件。这些选择会破坏“ModemManager 单一控制者”或
增加没有实际硬件依据的 SoC 专用代码。

## R3 Mini 的 PCIe 与 Key-B 边界

当前 `target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts` 只把
`&ssusb` 和相关 USB PHY、供电、复位/电源 GPIO 置为 `okay`（525–531 行，
`usb_ngff_pins` 在 403–434 行）。这对应板载 Key-B/NGFF 蜂窝模组通过 USB
枚举的实际路径。

DTS 同时把 `&pcie`、`&pcie_phy` 置为 `okay`（261–269 行），但没有把任何
蜂窝端点、MHI 控制器或 T7xx 设备写成设备树子节点。这里不能把“没有端点
节点”当成 PCIe 驱动绝对不可用：PCIe endpoint 是在链路训练后通过配置空间
自动枚举的，通用 PCI 驱动本来就依靠 VID/PID 匹配。但也不能把 Key-B USB
插槽说成 PCIe：只有板上实际连出的 PCIe 插槽或通过合适的 M-Key PCIe 转接
板、供电、PERST#/CLKREQ#/WAKE# 和天线条件，PCIe WWAN 模组才可能出现于
`lspci`。M-Key/NVMe 的物理链路不能由 USB Key-B 驱动替代。

所以这批 PCIe 包应作为“将来可插入的可选硬件支持”编入镜像，不应在默认
配置中宣称板载 Key-B 已获得 PCIe 5G 能力。驱动使用 `AutoProbe` 只会在
匹配端点出现时加载；没有端点时不会改变 USB ModemManager 路径，也不会
碰到 NVMe，因为匹配表不同。

## MHI、QRTR 和 T7xx 静态核查

Linux 6.6.133 的 Kconfig 依赖如下：

| 驱动/包 | 源码条件 | 对 R3 Mini 的结论 |
| --- | --- | --- |
| `kmod-mhi-bus` | `CONFIG_MHI_BUS`；没有 x86 或特定 SoC 限制 | 可选，作为所有 MHI 子驱动的公共总线。 |
| `kmod-mhi-pci-generic` | `CONFIG_MHI_BUS_PCI_GENERIC`，依赖 `MHI_BUS` 和 `PCI` | 可选，支持 PCIe 上的 Qualcomm/Quectel/Foxconn/Thales MHI 端点。 |
| `kmod-mhi-net` | `CONFIG_MHI_NET`，依赖 `MHI_BUS` | 可选，处理 `IP_HW0`/`IP_SW0` MHI 数据通道。 |
| `kmod-mhi-wwan-ctrl` | `CONFIG_MHI_WWAN_CTRL`，依赖 `MHI_BUS` | 可选，向 WWAN core 暴露 AT、MBIM、QMI、DIAG 等控制端口。 |
| `kmod-mhi-wwan-mbim` | `CONFIG_MHI_WWAN_MBIM`，依赖 `MHI_BUS` | 可选，处理 `IP_HW0_MBIM` 数据通道并注册 WWAN link。 |
| `kmod-qrtr` | `CONFIG_QRTR` | 可选，提供 Qualcomm IPC Router core。 |
| `kmod-qrtr-mhi` | `CONFIG_QRTR_MHI`，依赖 `MHI_BUS` 和 `QRTR` | 可选，给 MHI Qualcomm modem 提供 QRTR transport；不需要 `qrtr-smd`。 |
| `kmod-mtk-t7xx` | `CONFIG_MTK_T7XX`，依赖 `PCI`，WWAN debugfs 时选择 `RELAY` | 可选，只匹配 MediaTek `14c3:4d75` 和 Dell `14c0:4d75`。 |

MHI generic PCI 表在 `drivers/bus/mhi/host/pci_generic.c` 611–701 行，包含：

- Qualcomm `0304`、`0306`、`0308`、`0309` 及多个 subsystem 变体；
- Quectel `1eac:1001/1002/1004/1007/100d/2001`；
- Foxconn 多个 `e0xx` 设备；
- Thales/Cinterion `00b3/00b4/00ba/00bb`；
- HP 的 `03f0:0a6c` 变体。

这些 Kconfig 和源文件没有 `CONFIG_X86`、ACPI-only 或 Qualcomm-SoC-only
条件，ARM64 内核可以配置并生成模块。MHI 设备的实际可用性仍取决于端点的
PCI ID、BAR、MSI、DMA 地址宽度和模组固件。通用 MHI PCI 驱动针对不同设备
把 DMA 宽度配置为 32 位或 64 位；R3 Mini 的 PCIe 控制器是否对某个外接
适配器满足该模组的 DMA/中断要求，需要实机验证。

`mhi_net` 与 `mhi_wwan_mbim` 的匹配通道不同：前者匹配 `IP_HW0`、`IP_SW0`
（`drivers/net/mhi_net.c` 389–395 行），后者匹配 `IP_HW0_MBIM`
（`drivers/net/wwan/mhi_wwan_mbim.c` 636–641 行）。二者可以同时安装，
不会因为同一个 MHI channel 互相覆盖；某一模组只会暴露其固件定义的通道。
`mhi_wwan_ctrl` 负责控制端口，不能替代 `mhi-net` 或 MBIM 数据面。

T7xx 驱动的 PCI 表在 `drivers/net/wwan/t7xx/t7xx_pci.c` 946–951 行，只有
MediaTek `0x14c3:0x4d75` 和 Dell `0x14c0:0x4d75`。其 probe 路径使用两个
BAR、MSI、PCI bus mastering 和 64 位 DMA mask（834–883 行），没有 ARM64
排除条件，也不依赖 MHI。R3 Mini 本身的 MT7986 PCIe 根端口不会因为 vendor
ID 不同而被 T7xx 接管；只有实际插入 T7xx PCIe modem 时才会匹配。

## IOSM 评估与新增 OpenWrt 包

Linux 6.6.133 的 `drivers/net/wwan/Kconfig` 95–106 行定义了 `IOSM`：只依赖
`PCI`，并在 `WWAN_DEBUGFS` 开启时选择 `RELAY`，没有 x86 限制。驱动由
`drivers/net/wwan/iosm/Makefile` 聚合为 `iosm.ko`，使用标准 PCI、WWAN
core、DMA、devlink 和 relay API；源码没有架构条件分支。ModemManager 1.22
的 Intel 插件允许 vendor `0x8086`、`net`/`wwan` 子系统和 AT/MBIM 探测，
因此 Intel IOSM 设备能够沿 MM 的标准 WWAN/MBIM/AT 路径进入管理流程。

IOSM 的硬件边界很窄：`iosm_ipc_pcie.c` 336–341 行只匹配 Intel device ID
`0x7560` 和 `0x7360`，并在 probe 中强制请求 64 位 DMA mask（297–300 行）。
它不是任意 PCIe modem 的通用驱动，也不适用于 Qualcomm MHI 或 MediaTek
T7xx。驱动还通过 BAR0/BAR2、MSI 和 Intel IOSM IPC 协议访问 modem；R3 Mini
即使成功枚举一个 Intel endpoint，也需要确认 PCIe 转接板供电、复位、链路和
64 位 DMA 条件。无匹配 Intel ID 时，模块完全不参与设备绑定。

基于这些直接证据，已在 `package/kernel/linux/modules/netdevices.mk` 的
WWAN 区域新增：

```make
define KernelPackage/iosm
  SUBMENU:=$(NETWORK_DEVICES_MENU)
  TITLE:=Intel IOSM M.2 WWAN driver
  DEPENDS:=@PCI_SUPPORT +kmod-wwan
  KCONFIG:=CONFIG_IOSM
  FILES:=$(LINUX_DIR)/drivers/net/wwan/iosm/iosm.ko
  AUTOLOAD:=$(call AutoProbe,iosm)
endef
```

`kmod-wwan` 的包定义已经把 `CONFIG_WWAN_DEBUGFS=y` 放入 Kconfig；filogic
目标已有 `CONFIG_NET_DEVLINK=y`。IOSM 的 `RELAY` 由内核 Kconfig 的 `select`
处理，不需要伪造一个不存在的 `kmod-relay` 包。这个新增只补真实存在的
上游 `iosm.ko`，没有复制厂商用户空间拨号器。

## 漏掉的旧式 USB modem 串口驱动

现有 USB 片段已选择 `usbserial`、`usb_wwan`、`option`、`qcserial` 和
`sierra`，但遗漏了下面两个 OpenWrt 中确实存在的包：

| OpenWrt 包 | 内核模块/ID | 是否建议补选 | 原因与限制 |
| --- | --- | --- | --- |
| `kmod-usb-serial-ipw` | `ipw.ko`；`0x0bc3:0x0001` | 是 | Linux Kconfig 明确称为 IPWireless 3G UMTS TDD modem，源码使用 3GPP TS 27.007 AT 和 PPP 线路，包定义还自动带 `kmod-usb-serial-wwan`。这是专用旧 modem 驱动，不会和 `option`/`qcserial` 抢同一个 VID:PID。 |
| `kmod-usb-serial-ti-usb` | `ti_usb_3410_5052.ko`；包含 Multi-Tech GSM/CDMA/EDGE 的 `06e0:f108–f115` 等 ID | 是 | 驱动同时支持大量 TI/Moxa/IBM/Abbott/Honeywell 串口设备，但其 ID 表确实包含 Multi-Tech GSM、CDMA、EDGE modem。活动固件设备可直接产生串口；boot/无固件设备需要 `ti-3410-firmware`、`ti-5052-firmware` 或当前树未打包的 `mts_*.fw`。 |

`ipw` 驱动只有一个很老的 IPWireless ID，不能把它描述成对现代 LTE/5G
模组的补充；它的价值是覆盖用户明确要求检查的遗留 3G 设备。

`ti-usb` 的通用串口性质不会让它成为第二个 modem manager。它只注册 USB
serial driver，ModemManager 仍通过 tty/AT 探测；但它支持的普通串口适配器
不会自动变成可用 modem，且 MTS boot 模式的固件缺口必须保留在文档中。

以下“看起来像 modem”的驱动不应为了数量而加入：

- `kmod-usb-serial-qcaux` 主要暴露 Qualcomm DM/诊断辅助口，Kconfig 明确说
  这些端口通常不能用于 AT 或 PPP；它不增加 MM 的控制或数据面。
- `kmod-usb-serial-simple` 主要是 Motorola 手机、Novatel GPS、刷写器和
  Infineon modem flashloader 的简单串口，不是完整 modem 协议驱动。
- `kmod-usb-serial-ch341`、`cp210x`、`ftdi`、`pl2303`、`ch348` 等是通用
  USB-UART 适配器。除非用户把一个带 UART AT modem 的外接适配器接到其后，
  它们没有可识别的蜂窝 modem 身份；把全部串口桥都并入默认镜像会增加
  无关设备匹配和 MM 探测噪声。
- `kmod-usb-net-cdc-eem`、`cdc-subset`、手机 tethering 的 `ipheth` 是
  通用链路或手机网络功能，不能替代 QMI/MBIM/NCM modem 数据驱动。

当前 `package/kernel/linux/modules/usb.mk` 已有 `usb-serial-ipw` 和
`usb-serial-ti-usb` 的真实定义（796–804、781–793 行），所以配置片段应使用
上述精确包名，不要写成不存在的 `kmod-usb-serial-generic`。

## ModemManager 接线与实机边界

ModemManager 1.22 的 `mm-port-probe.c` 对 `wwan` 子系统创建 QMI、MBIM 或
串口端口；MHI control 驱动创建的 WWAN control port、MHI MBIM 注册的 WWAN
link 和 T7xx/IOSM 暴露的 tty/net 设备都能沿这个模型进入 MM。MM 源码本身
不需要为 MHI 另写一个 OpenWrt 管理器。现有 `modemmanager-rpcd`、官方
`luci-proto-modemmanager` 和补充的 MM SMS/频段前端仍是唯一用户空间管理面。

首次接入 PCIe modem 时，应按实际硬件执行以下检查，再决定是否提供该模组的
固件文件和默认 netifd 接口：

```text
lspci -nn
dmesg | grep -Ei 'pci|mhi|iosm|t7xx|wwan|dma|msi'
mmcli --list-modems
mmcli -m <实际索引> --output-keyvalue
ls -l /sys/class/wwan /dev/wwan* /dev/ttyUSB* /dev/ttyACM*
```

要特别确认：PCIe 端点是否来自真实 M-Key 链路、驱动是否取得所有所需 MSI、
DMA mask 是否被控制器接受、MHI 模组是否已经运行 mission firmware、MM 是否
发现 MBIM/QMI/AT 端口，以及 netifd bearer 是否能建立。静态选择所有上述
可移植驱动可以最大化镜像覆盖面，但不能把不存在的 Key-B PCIe 走线、未提供
的闭源 modem firmware 或尚未验证的电源/复位时序变成已支持功能。
