# BPI-R3 Mini / RG520N-CN 的 ModemManager 配置

`portalwrt-bpi-r3-mini-mm.config` 是独立的机型预设：保留 PortalWRT 标识和
KuCat，启用现有 ModemManager、官方 `luci-proto-modemmanager` LuCI 管理前端、
QMI/MBIM 及常见 USB 模块驱动。
不修改内核、设备树、HNAT 或 ModemManager 后端，不生成网络接口，不写入 APN、
锁频或运营商配置。LuCI 前端目录已同步上游针对数组解析、认证字段、IP 默认值、
状态文案和 ACL 的修复；保留当前 feeds 的其他版本，不额外升级依赖。

## 当前模块的支持依据

- 移远官方 Linux USB 驱动指南将 RG520N 系列列在 `2c7c:0801` 的 USB 设备组中。
- 本分支 `target/linux/mediatek/files-6.6/drivers/net/usb/qmi_wwan.c` 已有该 ID；
  Linux 6.6 的 `option` 串口驱动也已支持该 ID，代码中的注释/宏名可能写作 RM520N。
- ModemManager 的 Quectel 插件和 QMI/MBIM 协议栈负责探测设备与功能，
  不需要照搬 QModem 的逐型号 JSON 配置或硬编码频段。
- BPI-R3 Mini 原生 Key-B 插槽使用 USB；因此此预设没有为了该插槽加入
  PCIe MHI/t7xx/NSS 驱动。未来模块须确认其具体版本和固件支持 USB 数据连接。

这属于配置与静态支持核对；具体模块固件的枚举、拨号、重连和加速效果仍需实机验证。
如果模块处于 PCIe-only、恢复模式或非标准 USB 组合，安装这些包不会自动切换模块固件设置。

## 已选择的 MM 前端

该预设明确选择 `luci-proto-modemmanager`，它包含两部分页面，不会出现只装
ModemManager 后没有管理入口的情况：

完整的候选比较、上游提交固定和排除原因见
[`modem-frontend.md`](../docs/r3mini-migration-audit/modem-frontend.md)。工作区
已同步官方最新前端的数组解析、认证字段、IP 默认值、状态文案和 ACL 修复。

- **状态 → 蜂窝网络（Cellular Network）**：实时显示模组、SIM、注册状态、
  运营商、信号和小区信息。
- **网络 → 接口 → 添加新接口 → ModemManager**：选择 MM 发现的物理设备，
  填写 APN、PIN、认证、允许/首选制式、IP 类型和网关跃点。

`luci-app-modem`、QModem 旧版和 `luci-app-qmodem-next` 都是带自己拨号/扫描
服务的另一套模组管理栈，不是 ModemManager 的前端；把它们与 MM 同时装入会
让两个程序读取同一 AT 端口或抢占数据会话。因此本预设选择目标 LuCI 源码中与
MM 直接配套、并随目标分支维护的前端，同时保留 `modemmanager-rpcd` 供页面
读取状态。

## 装机后的 WebUI 设置

1. 打开 **网络 → 接口 → 添加新接口**，例如命名为 `cellular`，协议选择
   **ModemManager**。
2. 在“Modem device / 调制解调器设备”中选择检测到的移远模块。选择的是 MM
   识别的物理设备，不手填 `/dev/ttyUSB2` 或固定的 `wwan0`。
3. 填写 SIM 对应的 APN；如需 PIN，在同一页面填写。普通上网卡不要求认证时
   选择“无 / None”。IP 类型按运营商选择 IPv4/IPv6 或 IPv4。
4. 网络制式先保留 `any`。确认基础连接后，再选择设备实际支持的 4G/5G 组合；
   不在预设中强制 5G-only 或特定频段。
5. 在防火墙设置里把 `cellular` 加入现有 `wan` 区域，使用该区域的 NAT 和转发规则。
6. 要让模块优先，可把 `cellular` 的 **Gateway metric / 网关跃点**设为 `10`，
   有线 `wan` 和 `wan6` 的相应跃点设为 `100`。数值越小越优先；两条线路均启用
   默认路由。IPv4 和 IPv6 分别选路，需分别检查。

这种跃点设置在模块断开、默认路由撤销后使用有线 WAN。若模块仍显示连接但外网已
失效，需要额外的线路健康检测；此预设没有安装或预配置多 WAN 策略服务。

APN 留空不能保证自动匹配所有运营商。此预设按要求交由 WebUI 手动填写，
不添加四家运营商的自动 APN 表，也不覆盖有线 WAN 设置。

## 日后恢复构建配置

当前工作目录的 `.config` 已合入 MM 相关选择。日常可直接继续 `make menuconfig`。

`custom_package.sh config` / `init` 会重新生成原来的“机型 + KuCat”基础配置，
这是共享脚本已有行为，本次未修改该脚本。需要恢复 MM 预设时，在源码根目录执行：

```sh
cp .config .config.before-mm
cp defconfig/portalwrt-bpi-r3-mini-mm.config .config
make defconfig
```

这会恢复该预设；自行额外选择的软件包应从备份恢复或重新选择。
以上是日后使用说明，本次适配没有执行固件或软件包编译。

## 诊断工具

预设保留 `mmcli`、`lsusb`、`qmicli` 和 `mbimcli`。装机后可用这些只读检查：

```sh
lsusb -t
mmcli -L
mmcli -m 0
```

`0` 仅为示例，使用 `mmcli -L` 返回的实际索引。已开启通过 MM 发送 AT 命令的
构建选项，便于后续由 root 通过 `mmcli --command` 排查，避免另一个程序抢占 AT 口。
QMI/MBIM 工具是诊断工具，使用 MM 连接期间不要再用它们启动另一条拨号会话。

参考资料：

- [移远 Linux USB 驱动指南](https://quectel.com/content/uploads/2024/04/Quectel_UMTS_LTE_5G_Linux_USB_Driver_User_Guide_V3.2.pdf)
- [Linux 6.6 option 驱动](https://github.com/torvalds/linux/blob/v6.6/drivers/usb/serial/option.c)
- [ModemManager 1.22 发布说明](https://github.com/linux-mobile-broadband/ModemManager/blob/1.22.0/NEWS)
- [BPI-R3 Mini 官方使用指南](https://wiki.banana-pi.org/Getting_Started_with_BPI-R3_MINI)
