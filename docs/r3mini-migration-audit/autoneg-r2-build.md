# R3 Mini Autoneg-r2 交付构建与镜像核验

## 交付物

全量构建成功生成的 sysupgrade 镜像位于：

```text
.r3mini-output/autoneg-r2/targets/mediatek/filogic/
portalwrt-24.10.2-glados-r3mini-autoneg-r2-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb
```

- SHA-256：`c2c907c6c120a41d9ac2be7a8c11e64effab09b1993c182327cefe718e78359c`
- 文件大小：`255,198,292` bytes。
- 内置版本：`PortalWRT 24.10.2 / GLaDOS-R3Mini-Autoneg-r2`；修订号 `r33648+5-ec9ef10efc`。
- 新 GPT 的 production 分区从 64 MiB 开始，大小保持用户原有要求的 **2 GiB**（`2147483648` bytes）；并未改为 1.5 GiB。

镜像的功能性源码为提交 `61d6559300` 和 `fa805065cc`（后者修正铜口 carrier 事件不覆盖 HQoS）。完整构建在该功能性源码状态完成。随后提交的构建器隔离修复只改变 buildinfo 元数据的落盘位置，不改变 `.config`、DTS、内核/HNAT 源码、软件包选择或已生成镜像的任意 payload。

同一套已验证输入还生成了独立的 eMMC host-flash 包，位于 `.r3mini-output/autoneg-r2-hostflash/targets/mediatek/filogic/`：其中有未压缩 `emmc.img`、压缩 `emmc.img.gz`、独立的 `emmc-preloader.bin`、FIP、GPT、同一份 sysupgrade 和 `SHA256SUMS`。raw eMMC 用户区镜像 SHA-256 为 `4eec36f7d3a284637b6d4a5822c5773cb91c6a9d65268e42976b1058d6d06962`，压缩版本 SHA-256 为 `49e3df294a9bc174dcec92188e13292195dfffc3ef28b3301926c80ec0f44c41`。详见 [r3mini-emmc-host-flash.md](r3mini-emmc-host-flash.md)。

## 可复现构建记录

执行的全量构建命令如下：

```sh
python3 scripts/r3mini-build.py build \
  --log-dir logs/r3mini-build-autoneg-r2-run2 \
  --output-dir .r3mini-output/autoneg-r2
```

`logs/r3mini-build-autoneg-r2-run2/timing-summary.json` 记录 82/82 个阶段完成、无失败尝试；会话耗时 `4498.884` 秒（阶段墙钟合计 `4498.741` 秒）。其中 kernel、完整包安装、镜像、索引与校验和阶段均成功返回。

OpenWrt 顶层 `buildinfo` 包装目标会在递归前清空 `MAKEFLAGS`，因此会丢失命令行中的 `BIN_DIR`。这不会污染 sysupgrade payload，但会使 `config.buildinfo` 和 `version.buildinfo` 回写默认 `bin/`。构建器现改为在该逻辑阶段直接串行运行 `diffconfig buildversion feedsversion`，并将 `BIN_DIR` 明确指定为独立输出目录。实际验证后，以下三份文件均在新输出目录：

```text
config.buildinfo
version.buildinfo
feeds.buildinfo
```

构建前的完整旧输出已保存于 `.portalwrt-backups/pre-autoneg-20260907-bin/`。恢复这两份被 buildinfo 意外改写的元数据后，已执行：

```sh
diff -qr bin .portalwrt-backups/pre-autoneg-20260907-bin
```

该比对退出码为 0。原 sysupgrade 文件仍为原 SHA-256：`d0d7625b97bb6ce184f697a8621dc1e8e58716dcdd8fbf913b1cfdafb0f65b5a`。

## 已执行核验

```sh
python3 scripts/r3mini-autoneg-test.py
python3 scripts/r3mini-build-test.py
python3 scripts/r3mini-migrate.py --verify
sha256sum -c .r3mini-output/autoneg-r2/targets/mediatek/filogic/sha256sums
python3 scripts/r3mini-image-check.py \
  .r3mini-output/autoneg-r2/targets/mediatek/filogic/portalwrt-24.10.2-glados-r3mini-autoneg-r2-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb \
  --audit-dir .r3mini-checks/autoneg-r2-image-final-20260907
```

结果：

- 自动协商/PPD 实际 C 代码提取测试 8/8 通过（含 ASan/UBSan 状态转换检查）。
- 构建器测试 11/11 通过，包含 buildinfo 隔离路径、eMMC host-flash 产物声明及 GPT/FIP/FIT 偏移规则的命令级测试。
- 迁移配置核验通过：951 个选择的软件包，无缺失包、无禁止包；配置 SHA-256 为 `37779538af1f29a5a6bcf245c8514ab725903a3cbd8701e5ba6fb52dafc17d68`。
- 输出目录的 `sha256sums` 所列 6 个文件全部匹配。
- FIT 的 kernel、FDT、rootfs 位置、长度、CRC32 与 SHA-1 均匹配内嵌哈希；解出的 DTS 确认两颗 EN8811H 都以真实 `phy-handle` 连接、MAC 仍为 `2500base-x`、没有 `fixed-link`，并启用 `ppe0` 隔离回注。
- SquashFS 内确认包含 HNAT、mt_wifi、WARP/WARP proxy、conninfra、EN8811H 驱动、MT7986 WO/校准固件、`daed` 和 ModemManager。
- GPT 主头和分区表 CRC 均通过，production 分区是 2 GiB。DTB 反编译仅输出原有的地址/单元命名告警，未触发本修复相关断言。
- host-flash raw image 已逐段核验：GPT 位于 offset 0、FIP 位于 6656 KiB、剥离升级元数据后的 FIT 位于 64 MiB；`.img.gz` 解压后的长度和 SHA-256 与 raw image 完全一致，独立 BL2/preloader、FIP、GPT 与 sysupgrade 均与编译输出逐字节一致。
- 已在独立的 `OUTPUT_DIR` 实跑 `make target/install` 验证原生 device image recipe：它同时生成 sysupgrade、GPT、eMMC preloader、FIP 和 `emmc.img.gz`；解压后的 image 长度为 `322306052` bytes，且 GPT、FIP 和 offset `64 MiB` 的 FIT magic/位置均通过检查。该隔离规则测试不会覆盖这里列出的交付镜像。

## 尚需上板的验收

这份记录证明源码、全量编译、封包结构与静态加速路径均通过，不等同于真实硬件吞吐验收。刷写前请保留可启动备份；镜像元数据仍提示布局从兼容版本 1.0 升至 1.2，首次涉及该布局的升级须遵循板级 bootloader/GPT 迁移流程，普通 sysupgrade 不会自动扩分区。

在实际 BPI R3 Mini 上仍须按 [autoneg-fix.md](autoneg-fix.md) 的矩阵验证 100M/1G/2.5G 自协商、双铜口断链时 WiFi/蜂窝回注、PPE/WDMA/WARP 计数、HQoS、拔插、FE/WiFi SER 复位与 XDP 生命周期。只有这些实测与原成功固件对照通过后，才能宣称完整硬件加速无回归。
