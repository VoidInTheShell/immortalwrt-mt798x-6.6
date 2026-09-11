# PortalWRT R3 Mini 功能迁移实施记录

核查及实施日期：2026-09-06，蜂窝栈更新于 2026-09-09。本文件描述最终迁移方案；[README.md](README.md) 的主体是迁移前调查快照。r7 已完成全量构建、rootfs/FIT/GPT 镜像检查、r6 设备端 `sysupgrade -T`、保留配置刷写和刷后运行验收。现有 RG520N-CN 未插 SIM，故注册与 bearer 留待插卡验证；不能把这一个模组的枚举结果当成已经验证每一种物理模组。

最终选择数量、配置指纹、验证结果和编译计划汇总见 [final-validation.md](final-validation.md)。

## 配置、源码和可复现入口

- 完整配置：[portalwrt-bpi-r3-mini-full.config](../../defconfig/portalwrt-bpi-r3-mini-full.config)。配置基线备份位于 `.portalwrt-backups/r3mini-migration-20260906/`。
- [migration-decisions.tsv](migration-decisions.tsv) 为全部 1,129 个 x86 软件包逐项记录迁移、替代、排除或依赖解析决定。[migration-requested.json](migration-requested.json) 保存功能/硬件要求，[migration-verification.json](migration-verification.json) 记录配置展开后的实际数量、缺失、禁选项、重复定义及声明冲突检查。
- [hardware-required.config](hardware-required.config) 固定 MT7986、AX4200、EEPROM、WARP v2、新 WO 固件和全部配套包，不照搬 x86 驱动及内核配置。
- [sources.json](../../patches/r3mini-sources/sources.json) 和相邻补丁保存选中第三方仓库及 feeds 的提交、来源和本地修改。使用 `scripts/r3mini-sources.py apply` 重放；不会执行 git reset 或覆盖冲突。
- [准备/编译说明](../../defconfig/README-bpi-r3-mini-full.md) 给出完整命令。旧共享客制化脚本不是本次迁移的重放入口。

源码采用各已选兼容分支的已核对提交，并修复本地集成缺陷。**这不等于将所有基础库升级到上游最新大版本**：24.10 分支的 libubox、ucode、libudebug、libxml2 等与 x86 主线存在版本差异，直接跨分支替换可能破坏 rpcd/netifd/LuCI/私有驱动的 ABI。`source-revisions.tsv` 记录分支提交，`packages.tsv` 记录迁移前两端版本，不应把“分支已更新”宣传为“每个程序都是上游最新版本”。

## 功能迁移与明确排除

迁移通用终端、GNU/util-linux 工具、Python/Perl/Lua/PHP、存储/文件共享、网络诊断、SSH/SFTP、DNS 和 LuCI 功能。包从目标源码构建，不复制 x86 二进制。补入 Dropbear 的 zlib/askpass、完整 OpenSSH 客户端及 SFTP、dnsmasq-full 的 ipset/nftset 等补全；OpenSSH 服务端预装但默认关闭，避免与 Dropbear 同占 22。curl 的旧 `LIBCURL_NGHTTP2` 功能名映射到本分支 `LIBCURL_HTTP2`，所有迁移功能开关也一起核对，不能只数软件包。

Autoneg-r7 最终解析出 966 个真实软件包：其中 3 个 HS20 实验包仅生成 IPK，
其余编入固件。
原 x86 的 16 个 m 选择中，PHP/XML/SQLite/xxd/时区及通用库等 13 项已改为 y，
避免“编译了但固件里没有运行环境”。HS20 的 3 包维持原有 m：其示例 PHP 页会挂入
主 Web 目录，启用服务器时还会修改 uhttpd.main 证书，故不自动部署到常用管理环境。
这三包仍进入构建计划，并未假称它们已经内置。

| 范围 | 最终处理 |
| --- | --- |
| 蜂窝网络 | ModemManager 1.24.2 作为自动连接管理器，libqmi 1.38.0/libmbim 1.32.0 配套；完整 `luci-app-5gmodem` 主界面 + 官方 LuCI + 纯 MM 短信/频段备用页。补齐 USB modem 与主线 PCIe MHI/WWAN/T7xx/IOSM 驱动；QMI/MBIM 直连仅作显式救援，不安装独立 vendor CM 和争抢接口的 vendor QMI/MHI 实现 |
| QoS | 只保留 **MTK 专用硬件 QDMA QoS `mtkhqos_util`** 和 QoSmate；取消 EQOS、SQM、qos-scripts、qosify、nft-qos 及对应页面。tc-full、IFB、CAKE、HFSC、ctinfo 等是所保留功能的底层工具/模块，不是额外 QoS 管理器 |
| Web 管理 | uhttpd + ubus + OpenSSL TLS；不选 nginx。LuCI、CGI/ubus 页面不需要 nginx，daed 等独立后端继续使用自己的监听端口 |
| Node.js | 不安装目标 Node、node-*、ts-node；FileBrowser/SmartDNS 前端仍需主机 Node，选用官方主机二进制以避免编译整套 Node |
| 用户暂缓 | UA-Mask/UAmask、UA3F/ua3f、athena-led 均禁选 |
| 缺失/替代 | 不搬 bridger、kmod-nft-fullcone；保留 autocore-arm。libustream/luci-ssl 用 OpenSSL 变体；NTFS 挂载保留 ntfs3-mount；tc/ethtool 用 full 版本 |
| 硬件 | 排除 bnx2x、bnxt、Intel/Realtek/Mellanox、显卡、微码、GRUB/EFI 等 x86 扩展适配；保留 R3 的 EN8811H、USB、eMMC、风扇、U-Boot/TF-A 及板级设备树 |

用户提到的 53 端口问题已定位为 **`dns-over-https` 的 `doh-client`**：默认监听 `127.0.0.1:53` 和 `[::1]:53`，启动顺序早于 dnsmasq，可能导致 dnsmasq 整个服务启动失败，连带 DHCP 不可用。该包已取消选择。https-dns-proxy、SmartDNS、AdGuardHome、代理 DNS 是不同的软件；保留功能时默认关闭，启用前需分配不与 dnsmasq 冲突的监听端口并明确唯一上游链路。

### ModemManager 前端

`CONFIG_PACKAGE_luci-proto-modemmanager=y` 提供 **状态 → 蜂窝网络**实时状态页，
以及在 **网络 → 接口**中创建和编辑 ModemManager 接口的配置页；状态页通过
`modemmanager-rpcd` 的 `mmcli` 桥接读取模组、SIM、注册、信号和小区信息。
r7 另选 `luci-app-5gmodem` 2.4.60 作为主综合页面，补齐驱动/端口、CA、邻区、
SIM/eSIM、短信、USSD、AT、诊断、统计、多模组和手动恢复功能；纯 MM 的
`luci-app-sms-manager` 与经适配的 `luci-app-mmconfig` 继续作为独立备用入口。

前端候选、版本固定、权限和功能边界见
[`modem-frontend.md`](modem-frontend.md)。综合页面依赖的 sms-tool/comgt、
uqmi/umbim 和 QMI/MBIM netifd 协议随镜像安装，但自动接口策略已改为优先 MM；
只有管理员显式切换某个模组时才使用直连协议，并对该模组设置 inhibit。QModem、
Quectel-CM、旧 `luci-app-modem` 和重叠的 vendor QMI 内核驱动仍排除。

构建脚本的软件安装阶段会检查三套页面的菜单、ACL、静态 JS 和后端文件，并验证
MM 的 MBIM/QMI/QRTR/AT-over-D-Bus、libqmi FULL/QMI-over-MBIM/QRTR 选择，防止
出现“后台包存在但界面或协议能力漏装”。

驱动和依赖要求固定在 [modem-required.config](modem-required.config)，USB 核查见
[modem-driver-compatibility.md](modem-driver-compatibility.md)，最大覆盖补充见
[modem-extra-drivers.md](modem-extra-drivers.md)。除主线 USB 数据/串口驱动外，
加入 HSO、Kalmia、IPW、TI 3410/5052 及可用固件，并选择 MHI/WWAN、QRTR-MHI、
T7xx 与新增的 IOSM 包。PCIe 支持面向具备实际电气条件的 M-Key/转接设备，
不把 R3 Mini 的 USB Key-B 描述为 PCIe。尚缺部分厂商启动固件与专用 USB ID/quirk，
不能把驱动预装等同于所有市售模块均已测试成功。

## MTK 专用 HNAT 与管理页面

本树没有另一个必须安装的 `firewall4-hnat` / `nftables-hnat` 替换包。完整组合为 **firewall4、nftables-json、kmod-mediatek_hnat、kmod-conninfra、kmod-mt_wifi、kmod-warp、wifi-dats、mtwifi-cfg、luci-app-mtwifi-cfg、luci-app-turboacc-mtk**，以及相应内核/固件配置。

迁移前并非“虽然未选 HNAT，但被别名完整替代”：本树 fw4 补丁禁用了通用硬件 flowtable 提交，实际内核 override 又未启用私有 HNAT。现在已明确选择配套私有栈；不能把通用防火墙的硬件卸载勾选框等同于本机私有 HNAT 状态。

TurboACC 是独立加速管理页，包含 HNAT、IPv6、绑定参数和 PPE 统计。已修复 RPC 一次调用输出两段 JSON、错误以 Wi-Fi 配置标记认定 HNAT 正在工作、PPE 文本空白解析问题；驱动加载、Wi-Fi 加速配置和实际 HNAT hook 分开显示。PPE 数量改为驱动读取的只读信息，删除写入 UCI 却无实际作用的伪调节项。页面反映现有驱动暴露的统计，**不声称具备完整逐连接字节计费**；tcpdump/nlbwmon 一类软件统计可能看不到全部卸载流量。

已修复 HNAT 初始化覆盖设备树 WAN 的问题，保持 R3 的 eth1 WAN / eth0 LAN；修复 WARP_NEW_FW 未传给构建/安装的缺口。具体改动见 [hardware-implementation.md](hardware-implementation.md)。

## QoS、代理与加速的兼容边界

| 组合或行为 | 检查结论与已做处理 |
| --- | --- |
| 仅预装 QoSmate | 配置、首启和 hotplug 均默认关闭；不创建 qdisc/IFB/nft 表，不关闭 HNAT。对从未运行的服务执行 stop/reload 也不删除别人的队列 |
| 启用 QoSmate | 软件整形必须经过 CPU；暂时关闭通用卸载和私有 HNAT，保存原 UCI 与运行状态 |
| 关闭 QoSmate | 恢复由它临时修改的加速设置，保留用户后来主动修改的值。驱动读回 enabled/disabled、写入只接受 1/0 的差异已处理 |
| 异常中断/断电 | 恢复日志存于 `/etc/qosmate.d/offload-state`，在提交临时禁用配置前写盘；增加启动恢复服务，在 QoSmate 已关闭且仍有日志时恢复，避免只把快照放在 /tmp 导致重启后丢失 |
| QoSmate 在线自更新 | 固件托管标记阻止上游脚本自更新覆盖本次适配；通过已适配的软件包/固件更新。补齐 autorate、TC 分布文件、RPC 和运行依赖，排除未使用的 x86 m_xt.so |
| MTK HQoS | 直接管理 QDMA 硬件队列，默认 `enabled=0,hqos=0`。修复匿名 global 读取、64 队列边界、参数验证、真实停止与恢复；HNAT 总开关仍由 TurboACC 管理 |
| MTK HQoS + QoSmate | 不允许同时启用；两者有相互检查。前者服务于硬件转发队列，后者要求卸载关闭，不能叠加后声称两种效果同时完整成立 |
| QoSmate + daed | 双向阻止同时启用。QoSmate 使用 WAN ingress/IFB 与 qdisc，daed 使用 TC eBPF；通用 stop 清理可能移除另一方挂载点 |
| daed + 私有 HNAT/HQoS | 配置不自动全局关闭 HNAT，预装/默认关闭不干扰加速。代理路径及 TC 截获流与 MTK 私有 hook 的完整共存必须实机验证；不能保证所有代理流继续硬件转发，也不能把 daemon 启动成功当作无绕过证明 |
| 其他代理/策略路由 | Nikki、Passwall、PBR、mwan3 等默认关闭；启用后会改变 mark/route/nft/DNS，避免多套透明代理同时接管相同流量。代理/VPN CPU 处理的流量不等同于普通 LAN/WAN NAT |
| IRQ 工具 | 保留 MTK smp 绑定，irqbalance 默认关闭，避免反复争抢中断亲和性 |

关闭 QoS 不会物理损坏或永久移除 HNAT 硬件能力。此前可能表现为“加速永久没了”的原因是配置被提交为禁用、临时快照丢失、hook 恢复值不合法或共享规则被删除；本次针对这些实际路径修复。恢复逻辑已经通过模拟 UCI/debugfs 测试，真实路由器的驱动行为仍需上机验证。

## daed 1.27.0 与第三方源

固定 daed **1.27.0**，使用匹配的核心和 Web UI 归档及哈希，补入 geoip/geosite、现代 LuCI、BPF 工具链、内核 BTF/cgroup/BPF/stream parser 等依赖。监听配置使用当前 `listen_addr` 字段；默认关闭，按 procd 管理进程，网络 hotplug 默认不触发全局重启。详见 [daed-implementation.md](daed-implementation.md)。版本依据：[上游发布页](https://github.com/daeuniverse/daed/releases/tag/v1.27.0)。

FileBrowser 2.43.0 和 Mihomo 使用隔离的 Go 1.26.8 主机 SDK；daed 及现有旧 gVisor 消费者仍使用原兼容 Go 工具链，不做整条 Go feed 的盲目替换。新版 SDK 已从南京大学镜像下载，SHA-256 与固定官方值一致。详见 [go-compatibility.md](go-compatibility.md)。

NetSpeedTest 已切换到可用的新源并适配 ARM64，核验 Homebox musl/ARM64 和 Ookla AArch64 下载；修复 `/usr/bin/speedtest` 文件冲突、Bash 语法与 ash 不兼容、锁、ACL 和默认服务状态。QoSmate/Onliner 的重复 BuildPackage 已消除，并保留本仓库扫描器要求的标记。QoSmate 页面使用标准 LuCI 安装流程，视图放入菜单引用的 qosmate 子目录，两套 RPC 均安装。详见 [thirdparty-implementation.md](thirdparty-implementation.md)。

当前还存在未选中的 Radicale3、QModem、rmnet-nss 的外部依赖元数据警告；这些包不进入所选构建闭包。它们不是已验证可用的功能，也没有为消除警告而拉入不属于 R3 Mini 的驱动。

## PWM、品牌和 eMMC

风扇问题定位到 `998-pwm-fan-fix.patch` 为 Huasifei WH3000 Pro 引入的全局行为：删除 thermal cooling-device 注册并统一置零 PWM。已恢复 thermal 注册，将初始置零限定为该板显式声明的 `mediatek,initial-pwm-zero` 属性。R3 Mini 继续使用原 cooling maps 调速。补丁按实际 Linux 6.6.133 源码修正，完整补丁检查结果见 [kernel-preflight.md](kernel-preflight.md)。

PortalWRT 品牌、APERTURE SCIENCE、固件版本/构建日期和登录横幅已保留；型号、架构和内核从实际设备读取，版本标识为 GLaDOS-R3Mini / BPI-R3 Mini，不写死 x86。原客制化脚本中的 x86 网络处理保留架构条件，不在 R3 上套用。

完整 profile 仅面向 eMMC，production 为 2048 MiB，构建带 metadata 的 sysupgrade.itb 并进行分区容量校验，提供 eMMC GPT/引导组件。取消全功能 NAND factory / initramfs recovery 产物，避免超出 NAND/32 MiB recovery 分区。r7 sysupgrade 镜像为 256,509,013 字节，生产 GPT 容量检查为 2,147,483,648 字节；运行中的 r6 已用原生 `sysupgrade -T` 接受该镜像。普通升级不负责扩分区，仍不得绕过设备端校验使用 `-F`。

## 分组编译、线程与时间统计

`scripts/r3mini-build.py` 读取 GNU make 展开的真实包依赖图，包括 host 依赖，按依赖顺序生成阶段。`logs/r3mini-build/component-jobs.csv` 为逐组件线程/依赖清单。当前 24 CPU、约 25 GiB 内存的主机，预留 4 GiB 可用内存后采用下表；可用内存/cgroup/CPU affinity 更小时自动降低。

| 构建类别 | 当前起始并行上限 | 说明 |
| --- | ---: | --- |
| 轻量工具/普通 C 包 | 24 | 同时就绪的独立目标成组共享 make jobserver，不为每包再各开 24 |
| Linux 内核 | 24 | 与用户软件阶段分开 |
| GCC/工具链 | 12 | 限制较重编译器构建 |
| Go | 8 | 同时限制 CPU affinity、GOMAXPROCS 与 go -p |
| Rust 应用 | 4 | 较高单任务内存消耗 |
| Rust host 工具链 | 2 | 单独阶段，避免与其他重组件叠加 |
| NaiveProxy/Chromium | 5 | 配置最大上限为 6，本轮可用内存计算为 5；单独阶段并限制 nproc |
| Samba/Boost/ICU 等重 C++ | 8 | 单组件阶段 |
| MTK 私有驱动 | 8 | 遵守包原有并行声明，不强行解开上游串行约束 |
| 软件安装到 rootfs | 1 | 避免安装/文件数据库写入争用 |
| 镜像/索引 | 4 | 与编译阶段分开；校验信息部分串行 |

这些是基于当前资源和构建类型的保守起始值，不是数学意义上的最大安全线程。r7 全量增量构建按该调度完成 10/10 阶段，总墙钟时间 636.888 秒；这只证明本次源码、缓存和主机资源组合成功，不保证清空缓存后或不同资源限制下有相同时长。脚本遵守原 PKG/HOST_BUILD_PARALLEL，使用 CPU affinity 约束调用 nproc 的子构建，不全局强制 PKG_JOBS。若源码自身硬编码超额线程，仍需从真实编译日志识别。

主机 GNU make 4.4 默认使用 FIFO jobserver，而本树 Ninja 1.12.1 的补丁只解析管道文件描述符；构建脚本检测版本后显式使用 `--jobserver-style=pipe`，让并行 Meson/CMake/Ninja 子构建共享同一份任务预算。每个阶段开始前重新读取可用内存，只能向下调整该阶段计划线程数，实际线程数另写日志。

正式构建已经核验生成的内核配置包含 BTF、cgroup/BPF 和私有 HNAT；软件安装阶段也检查了实际 rootfs 中的 HNAT/WARP/无线模块、WO 固件、daed/MM 的 AArch64 ELF 文件、MM 菜单/ACL/JS 及品牌文件。r7 这些检查均通过；对应的运行时硬件行为仍要与镜像结构检查区分。

脚本记录每次阶段尝试的耗时、退出码、进程组 RSS 采样、完整日志，以及 OpenWrt `time:` 行提供的组件 user/system/wall 时间；总时长用单调时钟单独统计，不能将并行组件 wall 时间相加冒充总耗时。失败即停，保留独立 attempt 日志；`--resume` 核验配置、源码和计划指纹，不把旧成功标记套到新配置。

续跑保留原阶段的线程上限，避免仅因可用内存变化就失去续跑能力；实际执行仍按当前
资源向下调整，并使用当前 CPU affinity。依赖图、源码或配置改变仍会拒绝复用旧标记。

已做配置/依赖/归档下载/脚本回归、完整编译、最终文件冲突、rootfs 内容和镜像结构检查。`make download` 处理 OpenWrt 管理的归档；部分 Go modules、npm/pnpm 或 Cargo 依赖仍由上游构建阶段下载，因此不能据此声称任意空缓存环境都可完全离线重建。r7 的 FIT 哈希、设备树、rootfs、metadata、生产 GPT、固件版本和蜂窝组件均通过独立镜像检查，并已在现网 R3 Mini 上完成保留配置升级。刷后确认 MM 1.24.2、综合 WebUI、驱动绑定和 MM-first 配置；未插 SIM 的注册/拨号，以及 HNAT、风扇、daed 等非本轮目标的专项压力测试仍不能用镜像检查替代。
