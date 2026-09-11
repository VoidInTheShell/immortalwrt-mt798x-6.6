# PortalWRT R3 Mini Autoneg-r7 构建、升级与运行验收

验收日期：2026-09-09。本记录覆盖已经实际完成的构建、镜像检查、r6 设备端升级前
检查、保留配置刷写和 r7 刷后运行检查。没有 SIM 才能完成的运营商注册、bearer、短信
和真实射频指标仍明确留作待测。

## 最终产物

- 版本：`PortalWRT 24.10.2 GLaDOS-R3Mini-Autoneg-r7`
- 修订：`r33648+15-ec9ef10efc`
- 文件：`portalwrt-24.10.2-glados-r3mini-autoneg-r7-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb`
- 大小：256,509,013 字节
- SHA-256：`a308615624d3ca1c3f711a9c1a0f5d8358d28ff63a3a87856b0b9a1eaea33616`
- 构建：10/10 阶段成功，总墙钟时间 636.888 秒

全量构建验证了实际 rootfs，而不只是 `.config`：ModemManager 1.24.2-r1、
libqmi 1.38.0-r1、libmbim 1.32.0-r1、`luci-app-5gmodem` 2.4.60-r1、中文翻译包、
官方 ModemManager LuCI、mmconfig、sms-manager、QMI/MBIM 手动救援协议和全部选定
USB/PCIe 蜂窝驱动都存在。MM 构建启用了 QMI、MBIM、QRTR、AT-over-D-Bus 和完整
内建厂商插件；libqmi 启用了完整 message collection、QMI-over-MBIM 与 QRTR。

## 镜像级验证

`scripts/r3mini-image-check.py` 已解包并检查最终 sysupgrade FIT，结果位于
`.r3mini-checks/r7-modem-20260909/result.json`。通过项包括：

- FIT 内核、设备树和 squashfs rootfs 的内部哈希；
- BPI-R3 Mini supported-device、板级设备树和 PortalWRT r7 版本/修订；
- production GPT 2,147,483,648 字节容量约束；
- 选定的 USB serial/QMI/MBIM/NCM/ECM/RNDIS/Sierra/HSO/Kalmia 驱动，以及
  WWAN/MHI/QRTR-MHI/T7xx/IOSM PCIe 覆盖；
- Modem → 5G Modem 的 11 个菜单页、ACL、前后端脚本、中文包、MM-first 自动接口
  策略和默认关闭自动恢复/故障切换/USB 电源循环/Wi-Fi 修复的主路由安全策略。

镜像 metadata 含通用的 layout/compatibility 提示，因此不能仅凭离线解析决定是否强制
升级。实际 r6 的 `system.@system[0].compat_version` 为 `1.2`，与 r7 相同；设备端原生
验证才是刷写前门槛，本轮没有使用 `-F` 绕过它。

## r6 设备端预检

运行中的设备报告：Bananapi BPi-R3 Mini、Linux 6.6.133、PortalWRT 24.10.2、
`GLaDOS-R3Mini-Autoneg-r6`、修订 `r33648+13-ec9ef10efc`。它安装的是
ModemManager 1.22.0-r21、libqmi 1.34.0-r2、libmbim 1.30.0-r2，而非页面视觉拼接出的
所谓 `v25.341.088611.22.0`。

现网 MM 已识别 Quectel RG520N-CN（固件 `RG520NCNAAR03A01M4G`）：

- 插件：`quectel`
- 驱动：`qmi_wwan`、`option1`
- 端口：`cdc-wdm0 (qmi)`、`ttyUSB2/ttyUSB3 (at)`、`wwan0 (net)`
- 能力：GSM/UMTS、LTE、5G NR；QMI 支持 IPv4/IPv6/IPv4v6
- 状态：`sim-missing`，所以无运营商注册、实时信号、小区和 bearer 是预期行为

设备 `/tmp` 可用约 987 MiB，上传后的镜像由设备端重新计算 SHA-256，与构建端一致。
最后执行：

```text
sysupgrade -T /tmp/portalwrt-r3mini-autoneg-r7.itb
```

返回码为 0，无警告或错误输出。随后直接调用设备校验器，得到
`fwtool_signature=true`、`fwtool_device_match=true`、`valid=true`、`allow_backup=true`。
这些结果共同证明当前 r6 接受 r7，且允许保留配置升级，但不会写入 flash、不会重启，
也不等于已经完成 r7 的运行验收。真正刷写仍应使用普通保留配置升级，刷前另存配置备份；
若后续检查出现设备不匹配，禁止用 `-F` 强制绕过。

## 刷写与运行验收结果

刷前使用 `sysupgrade -b` 生成配置备份并复制到工作区隐藏备份目录；gzip 完整性检查
通过，路由器端和本地 SHA-256 均为
`3092a2b15d0487b8a3772d0b17bd82e37a12056304fb4fce4919694f5c1931f3`。随后执行普通
`sysupgrade -v`，没有 `-F`、`-n` 或其他绕过参数。设备完成写入、重启并恢复 HTTP/SSH。

刷后结果：

1. 系统报告 Autoneg-r7、修订 `r33648+15-ec9ef10efc`，核心三个蜂窝包分别为
   ModemManager 1.24.2-r1、libqmi 1.38.0-r1、libmbim 1.32.0-r1。
2. `luci-app-5gmodem` 2.4.60-r1 和中文包已安装；11 个主页面 JS 文件共 327,084 字节，
   uhttpd 对主详情页面实际返回 HTTP 200。官方 MM、mmconfig 和 sms-manager 均保留。
3. 自动创建的 `network.modem` 明确为 `proto='modemmanager'`，不是 QMI/MBIM 直连。
   5gmodem 配置的 `prefer_modemmanager=1` 与 `portalwrt_safe_defaults=1` 已生效。
4. RG520N-CN 仍由主线 `qmi_wwan`/`option1` 绑定，MM 使用 Quectel 插件并识别
   `cdc-wdm0 (qmi)`、`ttyUSB1 (gps)`、`ttyUSB2/ttyUSB3 (at)`、`wwan0 (net)`。
5. MM 明确报告 `sim-missing`。因此 netifd modem 接口当前 `NO_DEVICE`、没有运营商、信号、
   CA/邻区和 bearer 符合无 SIM 条件；插卡后再验证 PIN、注册、APN、IPv4/IPv6、
   SMS/USSD 和频段/制式读写。
6. 自动健康检查、故障切换、模组恢复和 Wi-Fi 修复均为 0，未因安装完整管理界面而自动
   重置模组、循环 USB 电源或修改主路由流量路径。
