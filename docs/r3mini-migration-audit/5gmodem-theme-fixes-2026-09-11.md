# 5gmodem 与 KuCat / Argon 修复及验证（2026-09-11）

## 范围与证据边界

用户授权本地修复、实机测试及固化到固件。USB PPE 单独保留，本文不宣称修复或验证了 PPE 加速。
前期只读取证见 `5gmodem-runtime-investigation-2026-09-11.md`。
本次没有刷写实机固件；实机采用备份后热部署脚本及模板的方式验证。

## 确认的问题

1. **注册状态域混淆。** 主采集器用 CS 的 CREG 结果覆盖 SIM 状态，且只在少数 CREG 值下采用数据域结果。
   已有证据是 CREG=3、CEREG=1、QMI 有数据连接。不能根据 CS 拒绝注册认定 LTE/5G 数据未注册。
2. **信号查询被错误状态挡住。** Quectel `2c7c:0801` 的详细信号采集依赖上述 REGOK；温度查询不依赖它。
   因而“温度正常、始终初始化、RSSI/RSRP/RSRQ/SINR 空白”可来自同一条状态解析路径，不必由接口删除造成。
3. **检测对象不完整。** 守护进程检查 modem 配置节是否存在，却没有检查它引用的 `network` 接口是否仍存在。
   创建脚本、自动设置、后台延迟启动缺少一致的当前状态判断与创建互斥；显式自动检测还可能沿用旧协议选择。
4. **防火墙配置与运行态脱节。** 原创建流程只提交 WAN zone 的 UCI 关联，未确保 fw4 的缓存和运行规则同步。
   现场曾出现路由器自身可上网、LAN 转发无 wwan0 对应放行/NAT 的情况。用户重启后规则恢复，是已有证据，
   不能把“重启后正常”当成插件逻辑已经正确。
5. **实测新增：删除重建的 metric 冲突。** 原 `_def_metric()` 固定返回 110（mwan3 模式为 20）。
   原排序是 modem=100、wan=110；删除 modem 后重建会产生 modem=110、wan=110。
   实机两个接口均 up、有线 carrier=1，但曾只有 wwan0 默认路由。执行 `netpri.sh order modem wan` 后，
   wwan0=100、eth1=110 两条路由恢复。新接口现在按现有 metric 分配更低优先级的非冲突值。
6. **主题持久化链路不完整。** 背景 URL 未变不代表目标图片仍存在，包更新可覆盖 /www 下图片；
   主题切换不一定再次运行下载脚本。KuCat 启动脚本还会在无启用预设时覆盖背景颜色，安装脚本可能抢占当前主题。

## 修复内容

- 新增共享 `runtime-state.sh`：区分缺失、配置停用、手动停止、拨号中、协议错误及在线；区分 SIM 与 CS/数据域注册。
- 主采集器输出接口/SIM/数据注册状态，Quectel 在 SIM ready 时可采集详细信号，并补齐后续 C5GREG 结果。
- 前端显示具体状态；创建遇到共享锁占用返回可重试的 busy；成功后刷新 UCI 配置视图。
- 创建、自动回退和优先级设置使用同一创建锁；延迟工作执行前检查协议、设备及当前行政状态。
- 重建只清理协议相关字段，保留既有自动启动开关、DNS 列表、MTU、路由策略、认证及优先级等设置。
- 显式选择“自动检测”不再被旧选择或默认 ModemManager 偏好拦截；未作显式选择的首次安装仍保留固件原有兼容偏好。
- 守护进程发现 modem 配置节存在但网络接口缺失时，也能触发自动设置；尊重 `auto_setup=0`。
- sessionwatch、自动接管、ModemManager 恢复以及健康检查均保护行政停用/手动停止状态。
- 创建和优先级改变前后同步 fw4；先通过规则检查再重载，已同步时不重复重载。
- 新建接口 metric 不再与现存接口冲突；已有接口重建保留用户原 metric。
- 两个主题默认主色统一为 RGB `240,209,217` / `#f0d1d9`，包括配置、模板和 Argon CSS/表单默认值。
- 背景原件与 URL 放在 `/etc/portalwrt-background/`，有 sysupgrade 保留清单；目标图片被覆盖或删除时可以离线恢复。
- 启动时立即应用，后台每 60 秒核对；内容相同不重写，目标采用原子替换；两主题共享背景地址并带修改时间缓存参数。
- 默认值仅补缺或迁移旧默认色，不覆盖用户自选色、透明度和已选主题；两个主题的安装脚本仅登记主题，不强制切换。

## 实机记录

- 第一轮热部署后，快照显示注册成功、SIM ready、接口 up，信号读数示例：
  RSSI −51 dBm、RSRP −86 dBm、RSRQ −15 dB、SINR 9 dB，n41 / 100 MHz。
  这些是采集快照，不是保证恒定的无线指标。
- Argon 登录页实际生成主色 `#f0d1d9` 和共享背景；临时切换 KuCat 再切回 Argon，
  两个页面都使用共享背景，KuCat 原有透明度等值保留。测试后恢复原选中的 Argon。
- 缓存和三个发布目标的 SHA-256 一致，原图约 7.8 MB。
- 持有创建锁时真实调用 mkiface，收到 `{"result":"busy"}`，没有修改接口。
- 对已有接口显式自动检测重建，插件原有 native raw-IP 分支选择了 qmiraw；
  日志 12:51:32 开始设置，12:51:40 up；fw4 的逻辑接口与 wwan0 映射均可查询。
- 删除 `network.modem` 后，共享状态解释器立即返回 missing。
  首轮恢复测试发现热部署保留了源码 0644 模式，未执行包 postinst 的 chmod，导致 sessionwatch 未启动。
  **这是本次热部署的遗漏，不是对原始现场的根因认定。** 补齐包原有的执行权限后，
  日志 12:57:30 重新创建、12:57:35 autosetup 完成、12:57:38 接口 up。
- 删除恢复过程中还发现上述 metric 冲突；重新排序后实测两条默认路由和 modem 的 WAN zone 映射恢复。
- 创建返回 created 只表示配置创建完成，拨号在后台继续；本次单独检查了后续 up 状态，未把瞬时 down/pending 当作失败。
- 测试期间 ZeroTier 曾短暂不可达；在有线 WAN 优先且网关可达的条件下，用插件入口成功切回 QMI。
  最终已恢复原排序 modem=100、wan=110，两条默认路由均存在，modem 的 fw4 逻辑映射与设备映射均正常，
  绑定 `wwan0` 的 HTTP 测试返回 200。最终快照为 SIM ready、接口 up、registration=1、registration_data=1，
  RSSI −51、RSRP −84、RSRQ −14、SINR 10；sessionwatch 与 portal-background 均 running。
  metric 分配的最终补丁亦已热部署。原选中主题仍为 Argon。

## 回归与固化

- `scripts/r3mini-modem-theme-test.py`：9 个测试方法，含多组注册状态、接口状态、延迟启动保护、
  metric 分配、防火墙同步、首次下载/离线恢复/包覆盖/幂等写入、默认值保护和安装不抢主题子用例。
- 原有 runtime-fixes、r5、sources 测试分别 8、4、4 项通过；63 个 modem shell 文件语法检查通过。
- 4 个实机 ucode 模板编译通过；已检查修改的 JavaScript 语法。
- `scripts/r3mini-sources.py snapshot` 把选中嵌套仓库的改动固化成补丁与 SHA-256 锁；
  `apply` 已验证幂等，不重置或覆盖用户其它改动。
- `scripts/r3mini-image-check.py --modem-theme-fixes` 用于检查固件实际 rootfs 中的新脚本、主题配置与默认色，
  而非仅检查本地源码。最终构建记录目录为 `logs/r3mini-modem-theme-release-20260911/`。
- 最终 10 个构建阶段全部成功。镜像检查结果为 `.r3mini-checks/modem-theme-20260911-verified/result.json`，
  `modem_theme_payload_verified=true`，并确认镜像中的后台脚本具有执行权限；原始固件 SHA-256 保持不变。
- 固件副本：`.r3mini-output/modem-theme-20260911/portalwrt-24.10.2-glados-r3mini-autoneg-r7-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb`。
  大小 256,509,013 字节，SHA-256 `5a4461f790d1ed5df03ce4d8fc5c24bf30d37584f72ee4f76d45168df6314687`。
  注意仍沿用原配置的 r7 文件名，需按校验值识别本次构建，不要与旧 r7 混淆。
- 实机原文件和配置备份位于 `/root/modem-theme-backup.IBfDmC/`，包含 `originals.tar.gz` 与补充备份；
  没有通过安装整包覆盖用户的主题配置，也没有刷入上述新镜像。

## 尚需区分的验证层次

- 路由器自身出口、fw4 映射、LAN 终端端到端联网是不同验证项，不能互相替代。
  最后一次 conntrack 汇总没有观察到该 LAN 网段经 modem NAT 的现存会话（计数为 0），
  因而不能据此宣称 LAN 终端端到端验收通过；需要用户从下挂终端实际访问网页复核。
- 实际系统升级/整机重启尚未用新镜像执行；首次安装、离线恢复及文件覆盖场景先由回归测试覆盖。
- 原始“概率创建失败”的所有触发条件尚不能穷举；已修复并验证明确存在的状态、并发和优先级问题。
- 运营商名称编码异常单独保留；它与此次注册/信号缺失不等价。
- PPE 未做修改，也没有据上述结果宣称硬件加速已正常。
