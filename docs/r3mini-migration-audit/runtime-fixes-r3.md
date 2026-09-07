# R3 Mini 实机审查后修复（Autoneg-r3）

## 范围与版本

针对 Autoneg-r2 设备的只读验收结果修复无线配置/查询、Kucat 首次菜单、
ModemManager 空设备页面和 QoSmate 版本标识。设备上没有在线覆盖文件、
修改配置、重启网络或刷机。本次没有提交、覆盖用户另一个工作的文件。

版本为 `PortalWRT 24.10.2 / GLaDOS-R3Mini-Autoneg-r3`，保留 production
分区 **2048 MiB**。新输出在 `.r3mini-output/autoneg-r3/`，不使用旧 `bin/`
或 Autoneg-r2 目录。sysupgrade 和 eMMC 上位机刷写包都保留。

## 实机验收边界

r2 实机两颗 EN8811H 的自动协商已经开启，通告 100/1000/2500 Mbps；
WAN 实际协商为 1000 Mbps 全双工，LAN 未接线。`ppe0` 独立保持运行，
HNAT 的 `preferred/active` 均为 ppe0。WO Alive，无线 DMA 计数增长。
无持续客户端转发的采样期间，两组 PPE BIND 均为 0。

这证明当前 1G 自动协商与组件初始化正常，不证明全部硬件卸载通过。
仍需分别测有线、2.4 GHz、5 GHz 经 WAN 的 TCP/UDP、IPv4/IPv6 转发，
对照 BIND/PPE/WARP 计数、CPU 和吞吐；100M/2.5G、拔插和 SER 等矩阵未完成。
r3 尚未刷入设备，不能把主机回归测试称为实机验收。

## 根因与修复

### 无线排序和能力查询

实机 `ra0` 为 5 GHz、`rax0` 为 2.4 GHz，但 UCI/netifd 配置相反；
配置 HE160 的 5 GHz 实际以 HE40 运行。迁移片段启用了
`CONFIG_MTK_DEFAULT_5G_PROFILE`，驱动合并两个 dat 时倒置 profile 顺序，
而 wifi-dats / mtwifi-cfg 固定按 b0=2.4 GHz、b1=5 GHz。

恢复原 R3 Mini profile 的排序开关（DEFAULT_5G_PROFILE=n），同时保留
DBDC、MULTI_PROFILE、160 MHz、DFS、HNAT/WHNAT、WARP v2 等能力。
这不是关闭 5 GHz，不交换或重置用户保存的 SSID、密码和信道配置。

`iwinfo_mtk.c` 的 freqlist 结构未初始化新增 flags 字段，实机所有信道
被错误标为 NO_20/40/80/160MHz、NO_HE。现清零输入/输出结构、限制驱动
返回频率条目数和输出边界。hwmodelist/htmodelist 改为在释放 UCI 上下文
之前读取字符串，并按返回长度遍历频率条目。不添加越过驱动/地区限制的信道。

### EEPROM 读取

设备无 Factory/factory MTD，vendor 读取接口因此失败，回退通用 EEPROM BIN；
已有 DTS 的 mediatek,eeprom-data 没被这条路径使用。

为 R3 Mini 增加只读 DT 回退：真实 Factory MTD 仍优先；只在找不到 MTD
时读取该板 wifi 节点的 4096-byte 基础 EEPROM，检查 MT7986 magic 和长度。
首次 0x5000-byte 容器读取仅在没有 pre-cal indication 时允许尾部补零；
其它越界读失败，绝不伪造预校准数据。保留驱动原有运行时/EFUSE 校准路径。
没有添加对 eMMC、MTD 或 DT 的写入。此基础板级数据不等同于找回被擦除的
逐台出厂校准；仍需上板验证功率、空间流、频偏、带宽和稳定性。

eMMC raw 包会覆盖 factory 所在范围，因此 FLASHING.md 现明确说明其
factory 区为零填充，要求先离机备份并保留真实 factory 数据；已有正确分区
布局的运行设备优先使用 sysupgrade。

### 管理页面和版本

- Kucat 默认菜单由 basic 改为 allmenu；仍尊重浏览器显式保存的 basic/allmenu。
- mmconfig 的 actions/empty 改用不依赖持久化 UCI section 的 TypedSection；
  缺少模块时也显示发现/应用按钮和提示，不创建假 modem。修正已有 modem
  NamedSection 的类型与标题参数。频段/制式仍只展示实际模块报告的能力。
- QoSmate 后端包标识 `1.9.0+git.20260727.5a27872-r2`，前端为
  `1.9.0+git.20260727.6d2abc7-r1`。页面/服务使用相应完整 upstream SHA 和
  snapshot 通道，避免将已包含 v1.9.0 后续提交的源码显示成旧 release。
  版本解析兼容 LuCI 压缩后的一行 JS，也处理文件末行没有换行的情况；
  原 portalwrt-managed 在线覆盖保护和 QoS/HNAT 冲突处理保持不变。
- 嵌套源码改动已同步到 patches/r3mini-sources 及其校验清单，可从固定上游恢复。

## 验证与构建

```sh
python3 scripts/r3mini-runtime-fixes-test.py
python3 scripts/r3mini-autoneg-test.py
python3 scripts/r3mini-build-test.py
python3 scripts/r3mini-qosmate-test.py
python3 scripts/r3mini-sources-test.py
python3 scripts/r3mini-migrate.py --verify
python3 scripts/r3mini-build.py build --incremental \
  --log-dir logs/r3mini-build-autoneg-r3-final \
  --output-dir .r3mini-output/autoneg-r3
```

新增测试从实际 C 函数编译 ASan/UBSan 检查，使用实际 LuCI TypedSection
renderer 验证空状态，同时检查菜单偏好、排序和加速选项。现有测试继续覆盖
自动协商/PPD、构建隔离、QoSmate 策略和源码恢复；配置仍选择 951 个包。

首次构建在 fakeroot 创建本地 socket 时被沙箱拦截；内核已经编译成功。
run2 在允许本地 socket 的环境重跑，完成前五个阶段后主动停止逐包调度，
改用上述四任务上限的增量构建。增量模式仍调用完整 package/compile 依赖图，
以及全部内核、驱动、安装、镜像、索引和校验阶段；不跳过 make 的依赖检查。
首轮增量构建成功后，补充了从打包文件中发现的 QoSmate 压缩 JS 版本解析
修复，最终在 `logs/r3mini-build-autoneg-r3-final/` 完成 10/10 阶段、零失败。
最终这一轮耗时 294.302 秒（不含前述调试和先前构建轮次）。

## 交付核验结果

- 主机回归测试共 **32/32** 通过：本轮修复 6、自动协商/PPD 8、构建器 12、
  QoSmate 策略 2、源码恢复 4。C 测试使用 ASan/UBSan。
- 实际 MT7986 编译参数确认没有 DEFAULT_5G_PROFILE，仍含 MULTI_PROFILE、
  WHNAT、WFDMA/WED、CUT_THROUGH_FULL_OFFLOAD、原生校准和 CAL_FREE_IC；
  链接后的驱动仍引用 HNAT RX/TX 钩子。
- 镜像内版本 `r33648+7-ec9ef10efc / GLaDOS-R3Mini-Autoneg-r3`；全部修复的
  页面、QoSmate snapshot 标识、版本解析器及只读 EEPROM 读取代码已验证。
- FIT 各部分内嵌哈希、GPT CRC/2 GiB production、host raw 的 GPT/FIP/FIT
  偏移和 payload 对应关系、gzip 解压结果全部通过检查。
- 新目标输出 sha256sums 的 10 项和 host 包 SHA256SUMS 的 6 项全部匹配。
- 旧 `bin/` 与 `.portalwrt-backups/pre-autoneg-20260907-bin/` 逐文件一致。
  Autoneg-r2 的 sysupgrade 与 raw eMMC 原哈希保持不变。

产物共同前缀：
`portalwrt-24.10.2-glados-r3mini-autoneg-r3-mediatek-filogic-bananapi_bpi-r3-mini`。

| 产物 | 大小（bytes） | SHA-256 |
| --- | ---: | --- |
| sysupgrade.itb | 255198292 | `9eb61f1fa8e05fdf851605533556a120ee5efb19706cdbe2748437c13117495b` |
| emmc.img | 322306052 | `dfe990a22757f3adc2ff5e317f586103ef9484ef93c54382ff67bfae9c6690b6` |
| emmc.img.gz（host 包） | 255688837 | `6df39d9555ba733493163ce1a222c6c1ce09fcd4014ced0ba17761632b538338` |

sysupgrade 位于 `.r3mini-output/autoneg-r3/targets/mediatek/filogic/`；
完整上位机包位于 `.r3mini-output/autoneg-r3-hostflash/targets/mediatek/filogic/`，
包含 raw/gzip、独立 BL2、FIP、GPT、同一份 sysupgrade、FLASHING.md、manifest.json
和 SHA256SUMS。紧凑镜像文件小于 2 GiB 不表示 production 分区缩小。

机器可读验证报告：`.r3mini-checks/autoneg-r3-final-20260907/result.json`。
生成报告的命令如下（重跑时需要选择新的空 audit-dir）：

```sh
python3 scripts/r3mini-image-check.py \
  .r3mini-output/autoneg-r3/targets/mediatek/filogic/portalwrt-24.10.2-glados-r3mini-autoneg-r3-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb \
  --audit-dir .r3mini-checks/autoneg-r3-final-20260907 \
  --host-flash-dir .r3mini-output/autoneg-r3-hostflash/targets/mediatek/filogic
```

没有自动刷机。此固件完成编译和静态/主机验收，但硬件吞吐与射频结果仍需
上板确认。升级后先核对 ra0=2.4 GHz、rax0=5 GHz、实际带宽与 EEPROM 来源，
浏览器强制刷新，再执行上面的有线/无线硬件卸载测试。
