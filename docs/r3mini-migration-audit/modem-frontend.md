# ModemManager LuCI 前端选型与适配

核查日期：2026-09-06。最终采用官方联网/状态页面，加上通过 MM 操作的短信和频段扩展。它们共用一个 ModemManager 后台，满足功能互补；不另外运行拨号器或直接抢占模块串口。此处是通用模块配置，不把整套驱动和界面限定为某一款 RG520 或 L850 模块。

## 最终选择

| 包 | 页面功能 | 来源与版本 |
| --- | --- | --- |
| `luci-proto-modemmanager` | 状态 → 蜂窝网络；网络 → 接口 → ModemManager | 同步 OpenWrt LuCI `4beb8db7d68dd823d446d197903a62ca1af697d2`（2026-08-18）的页面与 ACL 修复 |
| `modemmanager-rpcd` | MM 状态到 LuCI 的桥接，配套 Lua/cjson/rpcd | 目标 feed 配套后端，加上本地依赖和解析修复 |
| `luci-app-sms-manager` | 收发 SMS、USSD、通过 MM 执行 AT、通讯录和配置 | 4IceG 上游 1.0.9，提交 `322392909e046c172f06e8dfff8a956b9ede4bbb`（2026-07-04），做 R3/MM 集成适配 |
| `luci-app-mmconfig` | MM 发现设备、显示能力、选择频段/制式 | koshev-msk/modemfeed 的 0.1.2，源提交 `8e4f19d8f11171872c99529166ca7344fe86080a`（2026-08-27），移除额外管理器依赖并修复配置处理 |

官方页面负责设备、制造商、型号、固件、IMEI、SIM、运营商、注册状态、信号和小区信息；接口编辑器负责 APN、PIN、认证、允许/首选制式、IPv4/IPv6、MTU、路由跃点和 EPS bearer。保留 `luci-mod-network`、`luci-mod-status`、LuCI、rpcd、uhttpd 和 ubus，使页面有导航入口和可执行后端。

官方前端已同步数组判断、认证字段动态依赖、IP 默认值和 mmcli 索引 ACL 修复。后端另外修复把 `%` 当格式符解析、缺失可选字段导致异常、对象路径校验及 Lua/rpcd 依赖。详见 [modemmanager-runtime.md](modemmanager-runtime.md)。

短信包选择的是 **sms-manager**，不是 **sms-tool-js**。前者明确通过 ModemManager 工作；后者上游明确不与 MM 配合。短信通知、自动转发和 LED 轮询不默认启用，普通浏览器内的读取与用户主动操作仍可使用。SMS-manager 上游将它标为开发版本，因此不能声称每种模块的 SMS/USSD 都已经经过实机验证。[上游说明](https://github.com/4IceG/luci-app-sms-manager)

频段页沿用 MM 的设备发现和能力报告。原包依赖 `luci-app-modeminfo`，并通过 uci-defaults 改写 `/lib/netifd/proto/modemmanager.sh`，这些行为已移除；不会因为多一个页面就拉入 comgt/raw AT 或改变整个网络协议脚本。只对匹配的 MM 网络接口操作，默认空配置不限制频段。实际实现和模拟检查见 [modem-bands-frontend.md](modem-bands-frontend.md)。

## 其他候选的取舍

| 候选 | 不采用的原因 |
| --- | --- |
| `luci-app-sms-tool-js` | 使用 sms_tool/直接端口，与 MM 的端口所有权不一致；其上游推荐 MM 用户使用 sms-manager |
| 原样的 `luci-app-mmconfig` | 功能有价值，但额外 modeminfo 依赖和全局 netifd 改写不适合本配置；采用经过适配的版本 |
| `luci-app-modeminfo`、`luci-app-modemband` | 常用后端直接访问 AT 串口，不能当成无冲突的 MM 插件 |
| QModem、`luci-app-modem`、`luci-app-wwand` | 自带扫描、端口管理或拨号后台；与用户要求的单一 MM 管理重叠 |
| `luci-app-5gmodem` | 功能多，但混合 vendor CM、comgt、sms-tool 等多套控制路径，需要整体改变管理方案 |
| `luci-app-L850GL-MM` | L850-GL 专用命令/桥接器及 expert MM 替换，不适合作为任意 USB/PCIe 模块的通用前端 |

没有证据表明存在一个能对所有厂商模块完整提供联网、锁小区、短信、eSIM 下载和邻区扫描，并直接兼容本树 MM 1.22 的单一通用应用。这里选取的是已核对的 MM 功能组合；厂商私有能力、eSIM 和网络不提供的 USSD 不能靠安装页面变成可用。

## 构建与实机边界

配置验证要求上述四个包及 MM/QMI/MBIM/AT 依赖都被选中。正式构建的软件安装阶段还检查 rootfs 中真实存在官方状态/协议 JS、菜单、ACL、MM 后端、短信和频段页面，避免“后台存在，界面漏装”。静态 JS/JSON/shell 和模拟后端检查不等于在真实模块上成功收发短信或切换频段。

首次使用仍需在 LuCI 的 MM 接口页配置运营商 APN，选择实际模块。没有插入模块时应显示空状态；不能假设索引永远是 0。收发短信、USSD、AT 与频段修改必须由用户主动操作，结果取决于 SIM、运营商、模块固件和 MM 插件所报告的能力。

源码参考：[官方 LuCI](https://github.com/openwrt/luci/tree/4beb8db7d68dd823d446d197903a62ca1af697d2/protocols/luci-proto-modemmanager)、[MM 频段页](https://github.com/koshev-msk/modemfeed/tree/8e4f19d8f11171872c99529166ca7344fe86080a/luci/applications/luci-app-mmconfig)、[SMS-manager](https://github.com/4IceG/luci-app-sms-manager/tree/322392909e046c172f06e8dfff8a956b9ede4bbb)、[SMS-tool-js](https://github.com/4IceG/luci-app-sms-tool-js)、[L850-GL 专用页面](https://github.com/As-tsaqib/luci-app-L850GL-MM)。
