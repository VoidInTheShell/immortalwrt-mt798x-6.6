# ModemManager 频段/制式管理前端

核查及适配日期：2026-09-06。

本次为 R3 Mini 选用的补充前端是 `luci-app-mmconfig`，源码来自
`koshev-msk/modemfeed` 的提交
`8e4f19d8f11171872c99529166ca7344fe86080a`，日期为
2026-08-27；本树的包目录是
[`package/mm-ui-bands`](../../package/mm-ui-bands)。提交号按临时源目录的
完整 Git 记录固定，对应上游仓库
[`koshev-msk/modemfeed`](https://github.com/koshev-msk/modemfeed) 的
`luci/applications/luci-app-mmconfig` 路径；后续更新应重新核对上游提交和
兼容性。

## 选择与入口

`luci-proto-modemmanager` 提供 ModemManager 协议、Network → Interfaces 中的
拨号配置，以及 Status → Cellular Network 状态页；它本身没有频段选择器。
本包补上最新源中的现代 LuCI JavaScript 频段面板，支持 ModemManager 报告的
2G/GSM、3G/UMTS、4G/LTE 和 5G/NR 频段，并显示模块、运营商、当前制式及
对应的网络接口。

菜单入口固定为 **Network → ModemManager → Bands and modes**。菜单只依赖
本包 ACL，不依赖 `mmconfig` 中已有 section，因此没有开机时模块、配置文件
为空或模块刚热插拔时，页面仍然可打开。页面加载时调用官方
`modemmanager_helper.getModems()`；它通过 ModemManager 的 `mmcli -L -J` 和
`mmcli -m ID -J` 发现设备。没有 `/dev`、串口或独立 raw-port 扫描。

检测到尚未写入 `mmconfig` 的模块时，页面会在浏览器内建立一个待保存的
`modem` section，设备路径来自 ModemManager 的 `modem.generic.device`。按
**Discover ModemManager devices** 可执行一次受 ACL 保护的同步，持久化时只
提交 `mmconfig`；既有 section 的频段列表不会被覆盖。这样开机时不存在模块、
之后才热插拔的设备都能从同一页看到。

## 依赖与单一管理路径

Makefile 的运行依赖为 `luci-proto-modemmanager`、`modemmanager-rpcd`、
`jsonfilter` 和 `uci`（RPC 包带入 `modemmanager`、Lua/cjson 与 rpcd）。官方
ModemManager 状态页和本频段页共用 `modemmanager_helper` 与 mmcli JSON。包
没有 `luci-app-modeminfo` 依赖，也没有复制 `luci-app-modem`、QModem、
Quectel CM、`sms-tool`、`comgt`、`uqmi` 或其他拨号/管理服务；短信页由独立
的 ModemManager 前端包提供。

上游的 `70_luci-app-mmconfig` 会改写 netifd 协议脚本，把允许制式强制改为
`any`，与显式网络设置相冲突，因此没有搬入该文件。包只安装一个短时执行的
`/usr/libexec/mm-ui-bands` helper 和对应 init 薄封装，不增加守护进程。

## 频段和网络制式的行为

- `bands` 是 `mmconfig` 中唯一的频段持久化选项。页面只呈现
  `supported-bands` 中经过校验的值；输入必须属于该集合且不能重复。未设置
  或全部取消时，helper 不调用 `--set-current-bands`，保留 ModemManager/模块
  自己的默认策略，不在启动时把所有支持频段变成强制列表。需要撤销已有
  锁频时，页面的 **Automatic (all supported bands)** 会持久化 `bands=any`，
  helper 显式发送 `--set-current-bands=any`；这与空列表的启动惰性行为不同。
- 网络制式不另建一份 `preffer` 拼接字符串。页面的 Allowed/Preferred 两个
  控件直接读写与该设备路径完全相等且 `proto=modemmanager` 的 Network
  interface 的 `allowedmode`/`preferredmode`。只允许 netifd 支持的单制式或
  组合，并要求组合的 preferred mode 属于 allowed 集合。
- `mm-ui-bands apply` 再次校验 ModemManager 的 `supported-modes`、
  `current-modes`、`supported-bands` 和 `current-bands`。MM 返回的制式组合
  （例如 `allowed: 2g, 3g, 4g; preferred: 4g`）会按集合和稳定顺序解析，
  只接受完整的 allowed/preferred 组合，避免用各 token 的并集拼出模块没有
  声明的组合；频段输入拒绝空值、重复值、非法值或不属于支持集合的值。所有
  mmcli 参数均使用独立的已校验参数并加引号。
- 频段/制式发生实际变化后，helper 只对完整 device 值匹配的那个网络 section
  调用 `ifup`。没有匹配接口时只更新 ModemManager 设置；有多个完全匹配接口
  时拒绝制式写入并不重连它们。代码没有 `uci show network | grep`、子串匹配、
  `network restart` 或全局 `uci commit`。

保存页面设置会先提交必要的 `mmconfig`/Network UCI 修改，标准 LuCI
Save & Apply 通过 init 的 reload trigger 应用频段；页面内的 Apply 按钮也可
调用同一个一次性 helper。init 的 start 阶段只做受范围限制的 ModemManager
设备发现，绝不自动限制频段或制式。

频段设置是 ModemManager 的运行时属性，模块是否在 ModemManager 重启或 USB
重枚举后自行保留它，取决于具体插件和固件。设备重新出现后，init 的发现阶段
只补充 section；只有 `mmconfig` 中保存了具体频段或显式 `any`，reload/apply
才会再次写入，空的默认配置不会悄悄锁频。

## 校验、ACL 与限制

ACL 放行官方 helper 所需的两种 JSON 读取命令、网络/mmconfig UCI 读写，以及
页面显式使用的 `mm-ui-bands discover`/`apply` 一次性命令。helper 自身再次
校验设备路径、section 名、频段和制式，不能因为 LuCI 请求参数被改写就把
任意内容拼进 shell 或 mmcli。

在没有匹配的 ModemManager Network interface 时，频段仍可保存，制式控件会
只读；应先到 Network → Interfaces 创建官方 `ModemManager` 接口。模块不支
持频段写入、尚未完成初始化、被另一接口占用或 ModemManager 拒绝某个值时，
页面只报告失败并保留 UCI 选择，实际是否可用仍取决于 USB/串口驱动、MM 插件
和模块固件。应用制式或频段可能使当前数据会话短暂重连。

### 最终复核与重启后的应用

根代理补充核对了真实 MM 格式：supported/current modes 使用逗号分隔的代际集合，
supported-modes 的每个字符串都是完整 allowed/preferred 组合。现在先规范化集合和
顺序，再检查完整支持组合；不以代际 token 的并集替代实际能力。UCI 匿名的
`@modem[0]` 节点也能被正确处理。所有输入在修改前校验，非法模式不会先改变频段；
仅模式改变时也会重连唯一匹配接口。

新增 `prepare DEVICE` 入口，配合 MM netifd 协议在启用模块后、创建 bearer 前的
显式可选调用。它仅处理完整 device 值相等且已保存非空 bands 的节点，不发现其他设备、
不修改制式、不调用 ifup；空配置甚至不执行额外 mmcli 查询。这样已保存的频段可在
重启/热插拔后的拨号中重新应用。此处是构建时的明确适配，不是开机用 sed 把整个
netifd allowedmode 强制改成 any。失败会返回 MM_BANDS_FAILED，避免假装已应用。

界面提供明确的 Automatic/any 选项，用于撤销已经设置的频段限制；空列表仍表示不干预。
只读 ACL 的数字索引改为精确的 1–5 位匹配，不能夹带额外 mmcli 操作。

最终执行 `tests/test-mm-ui-bands.sh` 通过，覆盖普通/逗号制式、匿名节点、发现、any
复位、空频段、非法频段、非法模式、仅匹配设备以及拨号 prepare 不递归/不改变模式。
1 个 JS、2 个 JSON 和 7 个 shell（含测试）通过语法检查，另验证只读 ACL 拒绝额外参数。

本包的静态检查应包括 `sh -n`、LuCI JavaScript 语法、菜单/ACL JSON 解析，
以及用模拟 mmcli/JSON/UCI 响应覆盖：空配置发现、匿名 UCI section、设备路径精确
匹配、非法频段拒绝、显式频段提交、`any` 复位、逗号制式解析、模式完整组合校验和只重连匹配
interface。没有执行真实模块控制，也没有为了验证而扫描宿主机 `/dev` 或编译固件。
