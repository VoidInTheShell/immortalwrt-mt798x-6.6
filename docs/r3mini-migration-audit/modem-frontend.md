# R3 Mini ModemManager 与完整 LuCI 前端选型

核查及适配日期：2026-09-09。Autoneg-r7 采用上游最新稳定版 ModemManager
1.24.2、libqmi 1.38.0 和 libmbim 1.32.0，并把 `luci-app-5gmodem` 2.4.60
作为主功能界面。官方 `luci-proto-modemmanager`、纯 MM 的
`luci-app-mmconfig` 与 `luci-app-sms-manager` 继续保留，既提供标准接口/状态页，
也为第三方综合页面提供故障时的独立入口。

## 版本辨析

x86 页面上看到的 `v25.341.088611.22.0` 不是一个 ModemManager 版本，而是页面把
LuCI 包版本 `25.341.08861~9973412` 与 MM 核心版本 `1.22.0` 连续显示造成的视觉拼接。
x86 实际安装的是 MM 1.22.0-r20；检查时 R3 Mini r6 已是 1.22.0-r21，核心并不比
x86 旧。两边信息量差异主要来自 x86 上另装的旧 `luci-app-modem` 1.4.4，而不是
ModemManager 核心版本。

上游 ModemManager 标签和 NEWS 已核对：1.24.2 是 2025-07-28 发布的稳定版；
1.25.95 属开发序列，因此 r7 选择 1.24.2，不用开发快照。1.24 系列要求
libmbim 至少 1.32、libqmi 至少 1.36，本树分别升到 1.32.0 和 1.38.0。OpenWrt
master 当前包仍为 MM 1.24.0，所以 r7 的 1.24.2 是经过本树交叉编译验证的上游
稳定更新，并非简单照抄 24.10 feed。

参考：[ModemManager tags](https://gitlab.freedesktop.org/mobile-broadband/ModemManager/-/tags)、
[ModemManager 1.24.2 NEWS](https://gitlab.freedesktop.org/mobile-broadband/ModemManager/-/raw/1.24.2/NEWS)、
[OpenWrt ModemManager 包](https://github.com/openwrt/packages/blob/master/net/modemmanager/Makefile)。

## r7 最终组合

| 包 | 页面/后端功能 | 固定版本或来源 |
| --- | --- | --- |
| `modemmanager` | QMI、MBIM、QRTR、AT-over-D-Bus、内建通用及厂商插件 | 1.24.2-r1 |
| `libqmi` / `libmbim` | 完整 QMI message collection、QMI-over-MBIM、QRTR、诊断 CLI | 1.38.0-r1 / 1.32.0-r1 |
| `luci-app-5gmodem` | 模组/驱动/端口、信号与小区、CA、频段/制式、SIM/eSIM、SMS、USSD、AT、诊断、统计、复位和多模组 | 2.4.60-r1，提交 `02b063db804b8d57dd480f8690bacd13439ceee6` |
| `luci-proto-modemmanager` + `modemmanager-rpcd` | Network 接口编辑、Status 蜂窝页、MM JSON 桥接 | 当前固定 LuCI feed及本地健壮性修复 |
| `luci-app-mmconfig` | 只经 MM 设置频段和制式的轻量备用页 | 0.1.2-r4 |
| `luci-app-sms-manager` | 只经 MM 操作 SMS/USSD/AT 的轻量备用页 | 1.0.9 |

综合页面的入口为 **Modem → 5G Modem**，包含 Network、eSIM、Modem
diagnostics、Alignment、Inbox、Outbox、USSD、AT、Buttons、Statistics 和
Settings 十一个子页面。相较 x86 的旧 1.4.4 页面，它不仅恢复通用/USB 驱动和
端口信息，还提供多模组档案、SIM/eSIM、邻区、聚合、诊断与统计等现代功能。
源码固定和本地补丁由 [sources.json](../../patches/r3mini-sources/sources.json) 管理；
上游项目见 [fildunsky/luci-app-5gmodem](https://github.com/fildunsky/luci-app-5gmodem)。

## 连接管理策略

功能完整不等于允许所有拨号器同时占用控制口。r7 的策略是：

- 自动发现的新 QMI/MBIM 模组默认创建 `proto=modemmanager` 接口；MM 是控制口和
  数据会话的默认所有者。
- 管理员此前保存的显式协议选择优先。`qmi`、`mbim`、`qmiraw` 及 vendor AT
  路径连同 uqmi/umbim/comgt 仍随完整 UI 安装，作为特定模组不兼容时的手动救援路径。
- 切到内核直连协议时，页面按单模组设置 inhibit，避免 MM 与 uqmi/umbim 争抢
  同一个 cdc-wdm；切回 MM 时解除 inhibit。
- 不选 QModem、Quectel-CM、旧 `luci-app-modem` 及会重叠绑定的
  `qmi_wwan_f`/`qmi_wwan_q`。它们不是“缺少的通用驱动”，并装会让控制口归属和
  USB 绑定随启动/插拔时序变化。

综合页面带健康检查、故障切换、模组复位、USB 电源循环和 Wi-Fi 修复能力。
PortalWRT 默认把这些自动恢复动作设为关闭，由管理员在页面中逐项启用；信息读取、
手动控制和 ModemManager 拨号功能不因此裁剪。这样在主路由上安装完整界面时，首次
启动不会仅因页面默认值就自动改路由、重置模组或循环 USB 供电。

## 权限和能力边界

`luci-app-5gmodem` 的 ACL 按设计允许执行任意 AT 命令、切频段/制式、复位模组并
修改 network/firewall UCI，属于 root-equivalent 管理权限。该 ACL 只能授予完整
管理员，不能下放给受限 LuCI 角色；公网也不应直接暴露 LuCI。

页面能显示的字段仍取决于模组当前 USB composition、SIM 状态、运营商网络、固件
AT 指令和 MM 插件实际报告。没有 SIM、尚未注册或模组不提供相应指标时，注册、信号、
CA/邻区字段为空是正常结果，不能靠升级 UI 凭空产生。频段、eSIM、USSD、SMS 和复位
操作也必须由管理员主动触发，并可能短暂中断数据会话。

## r7 实机结果

R3 Mini 已用普通保留配置 `sysupgrade` 刷入 r7；设备端在刷前报告 compat 1.2，签名、
设备匹配、有效性和允许备份检查全部通过，全程未使用 `-F` 或 `-n`。刷后 `mmcli
--version` 返回 1.24.2，三个核心包和 5gmodem 版本均与上表一致。uhttpd 对
`5gdetail.js` 实际返回 HTTP 200，11 个主页面文件全部存在。

自动发现为 `network.modem.proto='modemmanager'`，证明 MM-first 路径已生效；MM 识别
RG520N-CN 的 `cdc-wdm0 (qmi)`、`ttyUSB2/ttyUSB3 (at)`、`ttyUSB1 (gps)` 与
`wwan0 (net)`，驱动仍是主线 `qmi_wwan`/`option1`，插件为 `quectel`。当前
`sim-missing`，所以 netifd 的 modem 接口不建立 bearer 并报告 `NO_DEVICE` 是待插卡条件，
不是 USB 枚举失败。健康检查、故障切换、模组恢复和 Wi-Fi 修复四项均实测保持 0。
