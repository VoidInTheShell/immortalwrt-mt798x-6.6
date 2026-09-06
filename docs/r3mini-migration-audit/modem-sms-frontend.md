# ModemManager 短信前端适配

选择 `luci-app-sms-manager`，源目录为 [package/mm-ui-sms](../../package/mm-ui-sms)。上游当前提交固定为 [`322392909e046c172f06e8dfff8a956b9ede4bbb`](https://github.com/4IceG/luci-app-sms-manager/tree/322392909e046c172f06e8dfff8a956b9ede4bbb)，日期 2026-07-04；上游版本 1.0.9-r20260225，本地适配 release 为 **20260906**。这是静态 LuCI JavaScript 包，不需要目标 Node.js。

菜单为 **Modem → SMS Manager**，提供收件箱、发送、USSD、通过 MM 的 AT、通讯录及配置；状态概览可选显示短信通知。它补充官方 MM 联网/状态页面，所有模块控制都通过 mmcli/D-Bus，不直接打开串口，不选择 sms-tool、comgt、modemdata 或第二个拨号器。

显式依赖为 ModemManager、modemmanager-rpcd、luci-proto-modemmanager、rpcd-mod-file、jshn、uci、mailsend。MM 的 AT-over-D-Bus 开关已在最终片段选择；mailsend 为可选手动邮件转发功能提供后端，本身不启动收件或拨号服务。

## 修复内容

- 状态卡原先调用未声明的 `md_modemmanager`，现改用 MM JSON；没有 modemdata 配置时仍能显示短信状态。
- 原版把正文直接拼入 MM 的 key=value 字符串。MM 1.22 解析器不能转义同时包含单双引号的值，空格/逗号也会改变解析。新增受写权限保护的 `sms_manager_send.send` RPC，校验模块索引和号码，以 0600 临时文件传递 UTF-8 正文，使用上游已有的 `--messaging-create-sms-with-text`，完成或失败后清理文件。没有 shell 拼接执行正文。
- 群发按顺序等待每条结果，遇到失败停止并报告已发送数量；不会创建一批后台定时器后无条件报告成功。发送成功表示模块接受发送，不等于收件人已收到或获得投递回执。
- 只读 ACL 仅允许精确的发现/读取命令；删除、USSD、AT、发送及邮件转发均要求写权限。数字索引使用有长度边界的 glob，去掉 `[0-9]*` 允许尾随任意参数的问题。导入/配置需要的管理命令也移至写权限。
- 通知进程由 procd 管理，删除 `ps | grep | kill -9` 批量强杀与 cron 重启逻辑。修复 LED 查询丢弃 mmcli 标准输出、空变量判断、无效计时和后台重复运行。
- 默认国家前缀从固定 `+48` 改为空且关闭自动前缀。默认 `lednotify=0`，init 只注册配置 reload trigger，没有通知 worker；启用后由标准 Save & Apply 启动 worker。状态徽标和邮件转发也默认关闭。
- 收件箱计数更新不再执行无效的 `fs.exec('sleep 2')`，按顺序保存并只提交 `sms_manager`，不全局应用其他网络配置。

## 检查与边界

7 个 JS 文件、2 个 JSON 和 6 个 shell 文件通过语法检查。`tests/test-sms-manager.py` 的 4 个模拟测试通过：中文/空格/逗号/单双引号/换行正文原样传递、临时文件权限与清理、非法输入不调用 MM、发送失败返回错误、只读权限不能发送或执行 shell。测试没有连接真实 MM 或发出任何短信。

首次使用应在 Configuration 选择实际 MM 模块，避免在多模块系统中默认操作错误设备。该上游仍标为开发版本；收件箱详情仍解析 mmcli 文本，复杂厂商记录、完整 multipart 展示、投递回执、运营商不提供的 USSD 与厂商私有 AT 均不能宣称已经验证。MM 的模块固件和 SIM 能力决定这些功能是否可用。
