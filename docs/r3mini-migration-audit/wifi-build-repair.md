# R3 Mini 无线构建修复与性能保留检查

## 修复边界

本次修复保留仓库原有 MT7986 / MT7976 / AX4200 驱动、射频配置和新版固件，不替换为 mt76，不调整发射功率、空间流、带宽、速率控制、射频增益、温控阈值或 WARP ring 参数。

相对于 `defconfig/mt7986-ax4200-bpir3_mini.config`，当前 `CONFIG_MTK_*`、`CONFIG_WARP_*` 和 `CONFIG_WED_*` 配置没有削减原有启用功能。差异只有迁移时增加的 BAND_STEERING、DEFAULT_5G_PROFILE、MAC_REPEATER_SUPPORT、MULTI_PROFILE_SUPPORT、PCIE_ASPM_DYM_CTRL_SUPPORT 和 SNIFFER_RADIOTAP_SUPPORT。这些功能仍然保留；是否在运行时使用，由无线配置和实际工作模式决定。

## 旧校准选项误选

迁移片段曾错误地打开 `MTK_PRE_CAL_TRX_SET1_SUPPORT`、`MTK_PRE_CAL_TRX_SET2_SUPPORT` 和 `MTK_RLM_CAL_CACHE_SUPPORT`。它们在原 R3 Mini 配置中均为 `n`。厂商的 `src/mt_wifi/os/linux/Kconfig.mt_wifi` 也明确为这三个选项声明了 `depends on CHIP_MT7615E`，OpenWrt 包装层 `config.in` 却遗漏了芯片限制。

现已恢复包装层的 MT7615 依赖，并同时修正迁移片段、生成的 preset 和迁移请求清单。没有保留在 Kbuild 中按多个芯片静默屏蔽宏的临时 025 补丁，避免出现菜单勾选与实际生成代码不一致。

MT7986 的预校准由其 Kbuild 芯片块独立启用 `PRE_CAL_MT7986_SUPPORT`，不依赖上述三个旧宏。实际路径包括：

- `eeprom.c` 通过 EEPROM 的 `0x19a` indication 和芯片容量信息分块发送 Group pre-cal；
- `mt7986.c` 在切换信道时应用 native DPD flatness 数据；
- `ee_flash.c` 为 native Group、DPD、TSSI、TxDNL 和 RX gain 设置各自指针，MT7976 使用对应的专用 offset；
- `phy/rlm_cal_cache.c` 中的 `GroupPreCalInfoAlloc_7986()` 和 `DpdFlatnessCalInfoAlloc_7986()` 独立于旧 `RLM_CAL_CACHE_SUPPORT`；
- 原有 default-BIN 与芯片 EFUSE 加载路径继续保留，包括 `CAL_FREE_IC_SUPPORT`。

不能把“驱动包含 Factory 读取代码”等同于“这块板实际存在 Factory MTD”。当前 R3 Mini DTS 定义的是 NAND 的 bl2/ubi 分区，默认 EEPROM BIN 与 EFUSE 路径也参与初始化。本次没有修改这些来源或写入任何设备校准数据。板上实际采用哪一种来源、校准 indication 是否有效，需要启动日志确认。

`get_prek_image_file()` 的条件注册服务于旧 generic BIN helper；native Group/DPD 的 EEPROM image 读取并不以该指针为入口。没有为通过构建而伪造旧校准区大小、偏移或返回成功，也没有扩大这个指针的注册条件。

## Linux 6.6 抓包接口

026 只把三处 radiotap / monitor 数据包的 `netif_rx_ni()` 调用改为 `netif_rx()`。Linux commit `2655926aea9b` 在 5.18 删除了前者；6.6 的 `netif_rx()` 自行处理进程和中断上下文需要的 bottom-half 操作。参见 [Linux 网络 API 文档](https://www.kernel.org/doc/html/v5.18/networking/kapi.html)。

三个调用均在 monitor 帧提交函数中，普通 `announce_802_3_packet()`、HNAT 收发 hook 和 WARP proxy 的调用顺序没有变化。

## 构建缓存与自动检查

`mt_wifi/Makefile` 原先把 `CONFIG_MTK_*` 转成了不匹配的 `CONFIG_*` 依赖名。现已让 `PKG_CONFIG_DEPENDS` 跟踪完整的 OpenWrt 符号列表，包括未启用的选项，防止以后修改驱动配置时复用旧模块。

`scripts/r3mini-build.py` 增加以下验证：

- R3 Mini 编译前拒绝三个旧校准宏；
- 检查实际 `.mt7986.o.cmd` 含有 native pre-cal、EFUSE、802.11ax、DBDC、TXBF、WHNAT、WFDMA/WED、完整 cut-through 和 TX/RX header translation 定义；
- 检查链接模块中的 Group/DPD 函数及对 HNAT 收发 hook 的引用；
- 安装阶段检查 HNAT、conninfra、mt_wifi、WARP、WARP proxy 模块和 MT7986 Wi-Fi / WA / 两个 WO CPU 固件及 AX4200 EEPROM BIN。

重试调度保留成功阶段优先 24 并发的规则。配置 hash 不同时，只有经 hash 校验的历史配置快照能证明差异仅为上述三个旧校准选项，才允许 mt_wifi 阶段之前的已成功阶段使用该规则。修改过的 mt_wifi 及其后续汇总、安装、镜像阶段仍按首次构建上限执行，不继承完成标记，所有目标继续由 make 检查依赖。

已通过独立临时配置验证：故意把三个旧选项写成 `y`，Kconfig 在 MT7986 下会拒绝；运行中的 `.config` 未被这个测试修改。调度、失败重试、路径清理与配置快照检查的 8 项测试通过。

## 硬件加速验证边界

`mt7986a.dtsi` 的 HNAT v4 节点没有 `status = "disabled"`，其默认状态可用；紧邻的 disabled 声明属于 `ethernet@15100000`，由 R3 Mini 的 `&eth { status = "okay"; }` 覆盖。WED / WDMA / WO 相关节点也继续保留。不能将相邻节点的状态误判为 HNAT 被关闭。

源码、编译命令、ELF 符号和镜像检查可证明预期代码、固件和依赖存在，不能代替板上加载和吞吐实测。上板应检查两个频段、空间流/带宽、EEPROM/EFUSE 来源、Group/DPD 加载日志，以及 WARP/WO 初始化和 PPE 计数；在相同终端、距离、信道和温度条件下，对比双向吞吐和 CPU 占用。QoSmate 测试结束后还需确认 HNAT 状态恢复。没有这些运行证据时，不将 WiFi 性能零回退或全部硬件加速已实测作为结论。
