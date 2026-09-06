# ModemManager 运行依赖与前端 RPC 修复

这是对当前 24.10 兼容分支的实际源码核查，不代表已经验证每一种物理模块。驱动范围见 `modem-driver-compatibility.md`，前端选择见 `modem-frontend.md`。

## 依赖关系

当前配套版本为 ModemManager 1.22.0、libqmi 1.34.0、libmbim 1.30.0。MM 1.22 要求的 QMI/MBIM 版本下限正好是 libqmi 1.34 / libmbim 1.30；本树匹配该要求。[上游依赖说明](https://modemmanager.org/docs/modemmanager/dependencies/)

MM 包显式依赖 glib2、dbus、ppp，以及启用协议对应的 libqmi/libmbim/libqrtr-glib。PPP 在这里是 MM 处理串口数据通路所需的底层后端，并不是额外的拨号管理器。netifd 的 modemmanager 协议脚本在缺少 mmcli 或 pppd 时直接退出，所以不能因“只用 5G”而随意删除 ppp。

本配置保留 QMI、MBIM、QRTR 和通过 MM 的 D-Bus AT 命令支持，libqmi 使用 FULL collection 和 QMI-over-MBIM；libqmi/qmi-utils、libmbim/mbim-utils 提供协议库、代理与诊断客户端。ModemManager 是唯一自动管理和拨号服务，其他管理器及 vendor CM 不选。

OpenWrt 使用 procd + D-Bus + netifd/hotplug 集成，MM 配置为 `udev=false`、`builtin_plugins=true`。不需要为了桌面版依赖清单引入 systemd/udev 守护进程；包内安装的规则由 OpenWrt 集成代码消费。内建插件沿上游默认集合构建，不限制为单一厂商。

## 实际修复

1. `modemmanager-rpcd` 原来仅写入裸 `modemmanager` 和 `lua-cjson` 依赖，Lua 解释器/rpcd 依赖声明不完整。现改为 `+modemmanager +lua +lua-cjson +rpcd`，单独选择 RPC 包也会正确拉入运行环境。
2. 加入 `PKG_CONFIG_DEPENDS`，让 QMI、MBIM、QRTR、AT-over-D-Bus 功能开关变化能够使构建缓存失效并重建。
3. 上游 FCC unlock available 目录使用可执行权限和 VID:PID 软链接，本树原 `INSTALL_DATA` 会把它们复制为普通不可执行文件。改为保留上游权限和链接的复制方式，并创建用户/软件包启用目录。可选脚本仍只处于 available 状态；没有对所有模块统一启用任何解锁动作。
4. RPC 原来把 mmcli JSON 当作 `string.format` 的格式串，运营商或设备字符串中的 `%` 会使解析失败。现直接 JSON 解码。
5. RPC 在模块没有可选 signal/location/3GPP 信息时不再索引空值，避免非 3GPP、初始化中或不支持该查询的模块导致整个信息接口报错。
6. SIM/bearer 对象缺省时不再把 nil 交给格式化函数；各对象路径先验证为 MM 的数字索引或规范 D-Bus 路径，解码结果也检查表类型。
7. 网络协议在启用模块后、创建 bearer 前调用可选的 mm-ui-bands prepare。只应用该设备明确保存的频段，空配置无动作；不覆盖制式或递归 ifup，使保存的选择可在重启和热插拔拨号后恢复。

`scripts/r3mini-mm-rpc-test.lua` 用模拟 mmcli 响应验证含 `%` 的运营商名称和缺少可选字段的模块，未执行实际 mmcli、模块控制或目标程序。前端能够取得信息的最终前提仍是 USB/串口驱动识别、MM 插件成功探测以及真实模块具备对应能力。
