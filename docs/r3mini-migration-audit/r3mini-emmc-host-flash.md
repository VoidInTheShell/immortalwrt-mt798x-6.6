# BPI R3 Mini eMMC 上位机／首刷包

## 为什么 sysupgrade 不够

`squashfs-sysupgrade.itb` 是供已经启动 OpenWrt/PortalWRT 的设备执行 in-system 升级的 FIT 文件，不包含 eMMC boot0 硬件区的 BL2/preloader，也不应直接被当作完整裸盘镜像写入 `mmcblk0`。

R3 Mini 的 eMMC 首刷需要两类数据：

| 写入位置 | 内容 | 交付文件 |
| --- | --- | --- |
| `/dev/mmcblk0boot0` 专用硬件 boot area | MT7986 BL2/preloader | `*-emmc-preloader.bin` |
| `/dev/mmcblk0` eMMC 用户区 | GPT、FIP 和 production 内的 FIT 系统 | `*-emmc.img` 或解压后的 `*-emmc.img.gz` |

这与 Banana Pi 的官方 eMMC 流程一致：先从 NAND 启动，再分别写入 boot0 BL2 与 eMMC 用户区镜像，并启用 eMMC boot partition。[官方 BPI R3 Mini 指引](https://wiki.banana-pi.org/Getting_Started_with_BPI-R3_MINI) 明确说明 R3 Mini 不能从 SD 启动，更新 eMMC 前应先切到 NAND 启动。

## 当前 Autoneg-r2 包

目录：

```text
.r3mini-output/autoneg-r2-hostflash/targets/mediatek/filogic/
```

其中包含：

- `portalwrt-24.10.2-glados-r3mini-autoneg-r2-…-squashfs-sysupgrade.itb`：已启动系统后的升级版本。
- `portalwrt-24.10.2-glados-r3mini-autoneg-r2-…-emmc.img`：上位机传输后可直接写入 eMMC 用户区的 raw 镜像，`322306052` bytes，SHA-256 `4eec36f7d3a284637b6d4a5822c5773cb91c6a9d65268e42976b1058d6d06962`。
- 同名 `emmc.img.gz`：raw 镜像的可分发压缩版，`255690291` bytes，SHA-256 `49e3df294a9bc174dcec92188e13292195dfffc3ef28b3301926c80ec0f44c41`。
- `emmc-preloader.bin`：必须单独写入 `mmcblk0boot0`。
- `emmc-bl31-uboot.fip` 和 `emmc-gpt.bin`：已嵌进 raw image，也单独提供给需要分区写入的工具。
- `SHA256SUMS`、`manifest.json`、`FLASHING.md`：用于校验与离线操作说明。

raw image 的布局已按本构建的 GPT 验证：GPT 在 offset 0，FIP 从 6656 KiB 开始，剥离 sysupgrade 外层 metadata 后的 FIT 从 64 MiB 开始。production GPT 分区仍为 **2048 MiB**；raw image 是紧凑镜像，FIT 之后不填充 2 GiB 的无用零数据，这与 OpenWrt 的 eMMC/SD image 构造方式一致。

## 建议的上位机刷写路径

R3 Mini 的 USB-C 并不会让 eMMC 自动成为电脑可见的 USB 磁盘。因此“上位机刷写”通常是上位机通过 USB 盘、TFTP 或 UART rescue 把上述文件送到板子，再由板上的 NAND／RAM rescue 系统写 eMMC。

1. 保留可启动 NAND，先把 boot switch 切到 NAND 并确认能够进入 shell；不要在正在从 eMMC 启动的系统中覆盖 eMMC。
2. 从上位机把 raw `emmc.img` 和 `emmc-preloader.bin` 传到 USB 盘、TFTP 或 rescue 系统。若只传输 `.img.gz`，先在目标端解压，或确认所用写入工具明确支持 gzip stream。
3. 在 **R3 Mini 的 rescue shell** 中先执行 `sha256sum -c SHA256SUMS`，再通过 `lsblk` 确认 `/dev/mmcblk0` 是板载 eMMC、`/dev/mmcblk0boot0` 是其 boot0 区。
4. 确认无误后执行：

```sh
echo 0 > /sys/block/mmcblk0boot0/force_ro
dd if=portalwrt-24.10.2-glados-r3mini-autoneg-r2-mediatek-filogic-bananapi_bpi-r3-mini-emmc-preloader.bin \
  of=/dev/mmcblk0boot0 bs=1M conv=fsync
dd if=portalwrt-24.10.2-glados-r3mini-autoneg-r2-mediatek-filogic-bananapi_bpi-r3-mini-emmc.img \
  of=/dev/mmcblk0 bs=4M conv=fsync
mmc bootpart enable 1 1 /dev/mmcblk0
sync
```

5. 断电，切换 boot jumper 到 eMMC，再启动并完成自动协商与加速路径的上板测试。

以上命令会销毁 eMMC 中原有 GPT、boot chain、系统和配置；它们不是在开发主机上对任意 `/dev/sdX` 执行的命令。若 NAND 和 eMMC 都不能启动，必须先使用**板级匹配的 RAM BL2/FIP rescue 组合**通过 `mtk_uartboot` 建立临时 U-Boot 或 Linux 环境。交付的 `emmc-preloader.bin` 是 boot0 介质 preloader，不可替代 RAM loader。

## 后续可复现构建

设备 image recipe 现在原生声明 `emmc.img.gz`，因此之后通过 `scripts/r3mini-build.py build --output-dir …` 进行的完整构建会与 sysupgrade、GPT、preloader、FIP 一起生成压缩 host-flash image。当前交付包则由 [r3mini-emmc-host-image.py](../../scripts/r3mini-emmc-host-image.py) 从已验证的完整构建输出无损组装，并额外提供未压缩 raw image 与校验/说明文件；它不会重编译、不会修改 sysupgrade，也不会写入任何块设备。
