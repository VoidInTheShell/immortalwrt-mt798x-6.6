# R3 Mini EN8811H 自动协商修复（Autoneg-r2）

## 根因与边界

原 DTS 将两个 GMAC 写成 `fixed-link / 2500`，没有把真实 EN8811H PHY 接到 phylink。用户看到的是 MAC 侧固定链路，ethtool 无法操作实际铜口 PHY。

2.5G MAC–PHY 串行接口本身不是错误。仓库内 EN8811H v2.0.7 驱动通过 `RATE_MATCH_PAUSE` 做铜口速率适配，应保留 `2500base-x` 并恢复铜口 100/1000/2500 Mbps 自动协商。驱动明确拒绝关闭自动协商；本修复恢复自动协商及能力通告，不承诺 `autoneg off` 强制速率模式。

原 HNAT 又借用 GMAC netdev 做 CPU/PPE 回注，将返回包送到 br-lan 的某个下层接口。固定链路掩盖了内部 DMA 发送和桥接入口对物理接口状态的依赖。仅删除 fixed-link，会导致无网线场景无法继续硬件学习。先前 Autoneg-r1 的软件回退方案未满足用户要求，没有作为交付固件。

根目录文档是 MT7988A，本机为 MT7986A。本修复没有据此推测或移植寄存器定义。

## 实现

- R3 Mini DTS 恢复两颗 PHY 的 phy-handle、地址 14/15、中断及厂商初始化属性，保留 2500base-x 和 RX 极性设置。
- 板级显式启用内部 `ppe0` 接口及 HNAT 隔离回注模式；其他板卡不创建该接口。它不是第三个硬件 MAC，不配置 IP、不加入网桥。
- ppe0 有独立软件发送队列、BQL/完成身份及共享 DMA 引用。包括分片在内的发送描述符指向原 PPE0 通路，不伪造 eth0/eth1 carrier。
- 驱动启动 ppe0 后，即使双铜口无网线或物理接口 administratively down，内部 DMA 仍有使用者。实际 DMA 故障、关闭 ppe0/HNAT 时停止回注，与铜口拔线不同。
- FE 复位、XDP RX 缓冲重建包含内部 DMA 使用者；失败重开不重复释放引用。卸载先注销接口、停止 DMA/NAPI，再释放对象。
- HNAT 专用 RX handler 在普通接收路径清理未知 VLAN 前处理内部 VLAN/流表标记；其注册、注销和模块开关使用 RTNL/RCU 保护。
- 外部接口回注沿用原 ifindex/VLAN 还原逻辑。CPU→WiFi 的标记 1234 返回 br-lan 发送路径，经既有 HNAT 桥钩子和 WiFi TX 钩子学习 WDMA 目标，不依赖有线桥端口在线。
- RATE_MATCH_PAUSE 保留 DMA 初始化时与原 2.5G 固定链路相同的 QDMA 队列预算，铜口链路通知不再重写队列：既避免百兆铜口误限内部流量，也避免拔插覆盖用户硬件 QoS 设置。铜口掉线只清相关物理出口流表。
- 同时修复 PPD RX 标记跨描述符串用、共享设备指针生命周期，以及部分 skb 已释放后的错误返回值。

未关闭 HNAT、WED/WARP、PPE/WDMA 学习、TSO/SG/校验和能力，未修改 WiFi 校准或 WO 固件，未裁减完整配置包选择。这里描述的是代码保留的路径；**编译及主机测试不能证明实际硬件吞吐、时序或所有加速场景已通过验收**。

## 版本与产物隔离

自定义版本为 **PortalWRT 24.10.2 / GLaDOS-R3Mini-Autoneg-r2**，不表示上游发行版或内核升级。

- 原成功构建基线归档提交：`6e8bfa89ee`，此前构建修复：`3c4f1cd24f`。详见 [successful-build-baseline.md](successful-build-baseline.md)。
- 原 `bin/` 不用于新构建，另有 `.portalwrt-backups/pre-autoneg-20260907-bin/` 备份。
- 原 sysupgrade SHA256：`d0d7625b97bb6ce184f697a8621dc1e8e58716dcdd8fbf913b1cfdafb0f65b5a`。
- 新固件、软件包仓库、元数据输出至 `.r3mini-output/autoneg-r2/`；构建器给 make 阶段显式传入绝对 OUTPUT_DIR。`buildinfo` 例外地直接串行调用其三个原始 recipe，并传入绝对 BIN_DIR：上游递归包装器会清空 MAKEFLAGS，导致仅传 OUTPUT_DIR 时那三份元数据回写旧 `bin/`。
- 新目录仅复用软件包缓存，不复制旧固件冒充新产物。构建中间目录允许正常重建。
- 新 VERSION_CODE 使文件名包含 `glados-r3mini-autoneg-r2` 标识。保留 r1 失败/中止日志。
- 完整构建后的旧 `bin/` 已与构建前备份逐文件比对一致；新输出目录中保存独立的 `config.buildinfo`、`version.buildinfo` 和 `feeds.buildinfo`。详见 [autoneg-r2-build.md](autoneg-r2-build.md)。

```sh
python3 scripts/r3mini-autoneg-test.py
python3 scripts/r3mini-build-test.py
python3 scripts/r3mini-migrate.py --verify
python3 scripts/r3mini-build.py build \
  --log-dir logs/r3mini-build-autoneg-r2-run2 \
  --output-dir .r3mini-output/autoneg-r2
```

主机测试从实际 C 函数提取并编译运行 PPD 选择、handler 生命周期、DMA 引用和完成身份检查（ASan/UBSan），另有设备树与补丁结构断言，不是硬件仿真。完整构建和镜像校验另记交付构建报告。

## 必须上板验收

1. 先备份配置和可启动镜像；确认 eMMC production 分区能容纳完整固件。普通 sysupgrade 不自动扩分区，本次不自动刷机或重分区。
2. 两口分别连接 100M、1G、2.5G 对端，检查 ethtool 支持/通告、自动协商、实际速度及拔线 carrier。限制速率应限制 advertised modes 并保持 autoneg on，不能从唯一管理链路冒险重协商。
3. 双铜口断开及单 WAN 在线时，测试本机→WiFi、USB/PCIe 蜂窝↔WiFi。检查 ppe0 UP、HNAT BIND、PPE/WDMA/WARP 计数增长，同时比较 CPU 占用和吞吐，不能仅凭接口存在判断加速成功。
4. 有线 WAN↔LAN/WiFi 的 IPv4/IPv6、TCP/UDP、多流、VLAN/PPPoE、硬件 QoS 开关及限速，与原成功固件同环境对照，尤其检查百兆/千兆下 PAUSE 速率适配。
5. 反复拔插、ifdown/ifup、桥成员变更、HNAT 关/开、网络重载、FE/WiFi SER 复位、XDP 装载/卸载（若使用），确认队列恢复，无 refcount/RCU/DMA/流表错误。
6. 检查双频校准及 WARP/WO 初始化；完成矩阵后才能称为稳定版或宣称完整硬件加速已验证无回归。
