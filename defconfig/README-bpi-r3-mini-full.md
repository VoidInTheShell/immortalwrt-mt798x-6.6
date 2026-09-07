# PortalWRT BPI-R3 Mini 完整功能 eMMC 配置

使用 `portalwrt-bpi-r3-mini-full.config`。这是以原 R3 Mini / ModemManager 基线为基础，按功能迁移 x86 选择后生成的配置；保留 ARM64、MT7986、AX4200、私有 HNAT/WARP/WO 和板级启动组件。

完整实施记录和运行冲突说明见 [implementation.md](../docs/r3mini-migration-audit/implementation.md)。原始调查保留在同目录的审计文件中，最终选择以 `migration-verification.json` 和根 `.config` 为准。

当前自定义版本为 `24.10.2 / GLaDOS-R3Mini-Autoneg-r2`，网口修复、独立输出构建与硬件验收要求见 [autoneg-fix.md](../docs/r3mini-migration-audit/autoneg-fix.md)。它保留 MAC 侧 2.5G 并恢复铜口自动协商，通过独立内部接口 `ppe0` 将 HNAT 回注与双铜口 carrier 解耦，保留无网线场景的硬件学习路径。尚需上板验证，不代表已经完成吞吐及复位测试。

本次准备结果见 [final-validation.md](../docs/r3mini-migration-audit/final-validation.md)：948 个内置包、3 个仅生成 IPK 的 HS20 实验包，MM 官方前端、短信/USSD/AT 和频段扩展均选中。

在仓库根目录执行：

```sh
# 新检出的仓库首次使用：获取固定提交、应用补丁并建立 feeds 链接
python3 scripts/r3mini-prepare.py --bootstrap --restore-config

# 恢复兼容补丁、检查本地主机依赖，并恢复完整配置；不编译固件
python3 scripts/r3mini-prepare.py --restore-config

# 输出每个构建目标的顺序、依赖、并行上限
python3 scripts/r3mini-build.py plan

# 下载 OpenWrt 管理的源码/工具归档；不编译固件
python3 scripts/r3mini-build.py download --log-dir logs/r3mini-download-new

# 只有此命令启动正式编译
python3 scripts/r3mini-build.py build --log-dir logs/r3mini-build-run1

# 同一源码、配置和线程计划下，从失败阶段继续
python3 scripts/r3mini-build.py build --log-dir logs/r3mini-build-run1 --resume
```

当前主机支持 Linux x86_64 版的固定 Go/Node 主机 SDK；固件目标仍是 ARM64。主机 Node 使用预编译工具，固件不安装 Node.js。不要通过共享 `custom_package.sh` 重新初始化本配置：它是指向仓库外的旧客制化流程，可能重置包选择或覆盖本地兼容修改。重放选中源的修改使用 `scripts/r3mini-sources.py apply`，发生冲突时脚本停止，不覆盖当前修改。

提交包含 PortalWRT 的 `files/` 覆盖文件、板级修改、完整预设，以及 12 个选中外部仓库的提交锁和全部本地补丁。`--bootstrap` 只补建缺失的固定版本仓库，已有目录或提交不符合预期时停止；不会重置已有工作。默认恢复无需原来的 x86 仓库或个人 `custom_package.sh`。重新生成迁移预设时使用仓库内冻结的 R3 基线和功能清单；只有显式提供 `r3mini-migrate.py --x86-config PATH` 才读取另一份 x86 配置。

eMMC 完整配置使用 **2048 MiB production 分区**，产物为带升级元数据的 `sysupgrade.itb` 和 eMMC GPT/引导组件。它不生成装有全部软件的 NAND factory 或 32 MiB recovery 镜像。现有 eMMC 的 production 分区必须能容纳最终镜像；普通 sysupgrade 不等于自动重分区。此配置不提供对现有设备进行破坏性重分区的脚本。

预装不等于启动。初次启动保留 dnsmasq、Dropbear、ModemManager 和 MTK 加速/无线服务；会争抢 DNS、SSH、流量规则或产生额外常驻负担的可选服务默认关闭。用户后续保存的启用状态在保留配置升级时不会被首启脚本重置。QoS 只保留 MTK 专用 `mtkhqos_util` 和 QoSmate，两者默认均不启用整形。

`plan.json`、`component-jobs.csv` 是计划；`component-times.csv`、`timing-summary.json` 是实际执行记录。没有开始编译的阶段不会产生虚构耗时。线程数是按当前 CPU/可用内存保守估算的上限，不是已经实测的最大安全核数。
