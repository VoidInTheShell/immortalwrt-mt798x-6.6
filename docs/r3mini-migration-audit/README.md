# x86 → BPI-R3 Mini 功能迁移调查

> **本文件主体是迁移前调查快照，下面的“未选择/未修改”描述只适用于原始基线。迁移现已实施，最终选择、修复、QoS/ModemManager 收敛和编译准备请先读 [implementation.md](implementation.md)，实际配置核对结果见 [migration-verification.json](migration-verification.json)。不要用调查快照覆盖已迁移的配置，也不要重新生成覆盖冻结的 packages.tsv。**

核查日期：2026-09-06。结论针对本机两个工作目录及当前软件源，不代表所有同名 ImmortalWrt 分支。

**迁移功能选择，用目标架构重新编译最新兼容源码；不能复制 x86 的整份配置、软件二进制、内核模块或整个 feeds。当前配置未形成可确认完整的无线/HNAT 构建基线：已复核内建 PPE、别名、替代管理入口与 fw4 补丁，原因并非简单地“没选某个面板”。应先落实硬件基线，再增加用户软件；daed 是用户额外指定的必补功能。**

本次为调查和隔离配置检查，未应用迁移、未修改现有 `.config`、内核/设备树或共享客制化文件，未编译固件、未刷机。已有用户修改保留。

## 核查对象、完整清单和证据范围

- x86：`/home/beihai/x86_immortalwrt`，主树 `bb287fd576`，2025-12-07。
- R3 Mini：`/home/beihai/immortalwrt-mt798x-6.6`，主树 `ec9ef10efc`，2026-07-23。
- 当前 x86：1,129 个真实软件包选择，其中 `y=1082`、`m=47`；R3 Mini：`y=305`。
- `y` 为编入固件；`m` 为编译软件包但不预装，并不是运行时“安装但不启用”。
- [packages.tsv](packages.tsv)：全部 1,129 个 x86 包的处理类别、两边版本、目标 Makefile、运行/构建依赖、PROVIDES 和 CONFLICTS。
- [feature-differences.tsv](feature-differences.tsv)：SSH、dnsmasq、libqmi 等功能开关差异。`CONFIG_PACKAGE_dnsmasq_full_*` 等不是独立软件包，未混入包计数。
- [inventory.json](inventory.json)：数量、重复定义、输入文件 SHA-256；脚本 `scripts/r3mini-migration-inventory.py` 可重建清单。
- [source-revisions.tsv](source-revisions.tsv)：22 个已接入仓库的本地/远端完整提交号，全部核对一致；未把本地兼容补丁误当成上游提交。
- [acceleration-paths.md](acceleration-paths.md)：私有 HNAT 与内建 PPE 的替代关系、实际 kernel override、其他 UI 入口及 WAN 映射复核。
- [daed-adaptation.md](daed-adaptation.md)：现代 daed 升级、无 Node 构建路线、内核配置试验和完整功能验收要求。
- 分类是筛选建议，`generic-candidate` 表示目标有候选定义，不等于已经完成 aarch64 编译或实机验证。翻译包、依赖库跟随实际选择重算，不能机械复制全部库。

## 当前硬件基线有实际缺口

`.config` 选中了正确的 `mediatek/filogic/bananapi_bpi-r3-mini`，也保留了 EN8811H PHY、风扇、USB、eMMC/启动相关组件及此前的 ModemManager 支持。

但以下内容尚未构成可确认完整的无线/HNAT 镜像：

这里确有另一套内建 MediaTek PPE/WED 路径，且通用 LuCI 防火墙页面提供卸载开关；但当前 fw4 的 `002-forbid-using-flow-offload.patch` 删除了 `flags offload`，并使 `resolve_offload_devices()` 无条件返回空列表。另一方面，按真实 package-metadata 内核配置生成逻辑检查，私有 `NET_MEDIATEK_HNAT` 明确为未选，并没有借内建或别名偷偷补上。因此不能把通用面板/模块视为已正常接替私有 HNAT。详细证据见 [替代路径复核](acceleration-paths.md) 和 [kernel override](kernel-offload-selection.txt)。

| 组件 | 当前状况 | 依据与处理 |
| --- | --- | --- |
| `kmod-mediatek_hnat` | 未选择 | `package/kernel/linux/modules/netdevices.mk:2091` 定义；实际模块名 `mtkhnat.ko`，自动加载优先级 20 |
| `kmod-mt_wifi`、`kmod-conninfra` | 未选择 | 本分支 MTK 私有无线驱动组合 |
| `kmod-warp` | 未选择 | 依赖 HNAT；安装 `mtk_warp.ko` 和相应 WO 固件 |
| `wifi-profile`、`wifi-dats`、`mtwifi-cfg` | 未选择 | 驱动配置文件、启动/管理脚本也必须与驱动配套 |
| `luci-app-turboacc-mtk` | 未选择 | 管理 HNAT，但其 Makefile **没有自动依赖 HNAT 驱动**；仅勾页面不会补齐加速 |
| `kmod-mt7915e`、`kmod-mt7986-firmware`、`mt7986-wo-firmware` | 机型 DEFAULT 引用，但当前包索引无定义 | `target/linux/mediatek/image/filogic.mk:395` 仍引用主线 mt76 组合；`CONFIG_DEFAULT_…=y` 不代表包真正进入固件 |

该分支的 WARP 默认仍引用旧 target 名，并把 `WARP_CHIPSET` 默认设成 `mt7988`；`wifi-dats` 首卡默认 `MT7981`。因此“勾选驱动后接受所有默认值”也不可靠。应显式核对 MT7986、WARP v2、MT7986 WO 固件、AX4200/MT7976C 的 dat 与 EEPROM 路径，并验证编译后的设备树启用了匹配的 HNAT/WED/无线节点。

旧 `defconfig/mt7986-ax4200-bpir3_mini.config` 可以作为私有驱动参数参考，但带有旧内核/target 配置，不能整个覆盖当前 6.6/filogic 配置。主线 `mt76 + WED` 与本树 `mt_wifi + WARP + mtkhnat` 也不能靠混装包变成完整适配。

已进一步确认：HNAT 节点并非完全缺失，它来自 `target/linux/mediatek/files-6.6/arch/arm64/boot/dts/mediatek/mt7986a.dtsi:596`，配置 eth1/eth0、两个 PPE，并列出 usb/wwan/rmnet 等外部设备前缀。该文件也提供私有 WED/wbsys 节点；需要把它与正确驱动选择一起验证，不能只搜板级 `.dts` 中有没有 `&hnat`。USB 前缀支持是积极证据，但还不足以保证任意 raw-IP/QMI/MBIM 固件组合的实际加速效果。

同时发现 `hnat.c:702` 将内部 WAN 名硬编码为 eth0，与设备树/板级 WAN eth1 不一致。其 IS_WAN/IS_LAN 又都匹配两个 eth 口，故这是需要追踪和实测的映射风险，不宜直接断言 eth1 必然失败或只改一个字符串。

硬件验收至少包括：两个 2.5GbE 口、2.4/5GHz、风扇温控、USB 模块、eMMC/NAND 启动，以及真实转发时的 PPE/HNAT 绑定。管理界面显示“已加载”不足以证明流量在硬件中转发。

## 什么可以迁移

| 功能组 | 建议 |
| --- | --- |
| 完整终端工具 | Bash、Zsh、GNU coreutils/grep/sed、jq/yq、curl/wget-ssl、git、rsync、unzip、xxd 等，可用目标源迁移；保留 BusyBox 供启动和救援脚本使用 |
| 诊断 | htop/btop/atop、ip-full、tc-full、ethtool-full、tcpdump、conntrack、iperf3、nmap、nexttrace、socat、usbutils、存储诊断工具，按用途选择 |
| 编程/后端环境 | Python 3 及标准库、pip/venv/pipx、Perl、Lua、PHP 可以移植；OpenWrt 是 musl/procd 环境，不会因包多就等同 glibc/systemd 桌面发行版，第三方 wheel/二进制仍需对应架构和 ABI |
| 存储/共享 | Samba4、NFS、rclone、文件管理、exFAT/NTFS/Btrfs/F2FS 工具可按需加；选择一种 NTFS 自动挂载实现，核对服务、磁盘挂载和内存占用 |
| 通用 LuCI 应用 | DDNS、证书、文件管理、统计、任务计划等多数目标已有，迁移选择而非源码目录；不同应用的启动行为仍需检查 |
| 代理、DNS、VPN、QoS | 大多有 aarch64 源码，但须逐项配置默认关闭和规则互斥；存在包不等于任意组合可同时运行 |
| Node.js | 暂缓 `node`、18 个 `node-*` 包以及 `ts-node`，共 20 项。还要防止其他包的 target/host 构建依赖重新引入 Node |

删除 Node.js 不等于消除全部长时间编译：NaiveProxy、Rust/Go 程序、Samba/CUPS/Python 等仍可能较重。编译预算应按构建依赖图评估。

还查到两个容易漏掉的 host Node 消费者：**filebrowser** 需要 node/host + node-pnpm/host；**smartdns-ui** 会条件性给 SmartDNS 的构建加入 node/host 和 rust-bindgen/host。即使固件完全不装 Node，仍可能在 PC 上编译 Node。当前 node recipe 提供 `CONFIG_NODEJS_HOST_BIN=y`，使用官方 Linux x64 主机二进制并跳过 Host/Compile；可以据此保留这些功能并减少构建时间，仍需验证前端版本兼容和下载。这里的 Linux x64 指构建机，不能拿该二进制装到 R3。另一条路线是暂缓独立 smartdns-ui/filebrowser，SmartDNS + LuCI 管理本身不要求这个独立 dashboard。

### SSH 与 dnsmasq 的补全

- 当前已经是 `dnsmasq-full`，DHCP/DHCPv6、DNSSEC、权威 DNS、nftset、conntrack、TFTP 等主要功能与 x86 相同。x86 多出来的是 `dnsmasq_full_ipset=y`；fw4 原生软件优先 nftset，仍使用传统 ipset 的插件才需要补该开关。
- 当前 Dropbear 与 x86 的额外差异是 `DROPBEAR_ZLIB`、`DROPBEAR_ASKPASS`。可以补，但不会因此替代 OpenSSH 的完整功能。
- 实用的 SSH 补全是 `openssh-client`、`openssh-client-utils`、`openssh-keygen`、`openssh-sftp-client`、`openssh-sftp-server`。SFTP 服务子程序可以配合 Dropbear，不要求再启动一套 sshd。
- 若需要 OpenSSH server 的功能，可预装并明确默认禁用，或制定替代 Dropbear 的方案。两者默认同占 TCP 22，不能都按默认设置启动。OpenSSH host key、sshd_config 与 Dropbear 的 UCI/密钥路径不同。
- `OPENSSH_LIBFIDO2=y` 适合确实需要安全密钥功能的场景，会增加依赖；不是 R3 Mini SSH 能用的前提。
- 两边 BusyBox 开启项没有发现 x86 独有补全；主要完整命令来自额外 GNU/util-linux 软件包。
- x86 使用 `LIBQMI_COLLECTION_FULL`，R3 当前是 BASIC。若希望 qmicli 提供更全面诊断，可以升级 collection，同时保留 ModemManager 的 QMI/MBIM/AT 支持；不要增加第二个拨号管理器。

## 必须剔除、替换或重新判定的项目

| 项目 | 原因 |
| --- | --- |
| bnx2x/bnxt、Intel/Realtek/Mellanox/虚拟机网卡驱动及固件 | 属于 x86 为广泛兼容而选择的外设集合；不会增强 R3 Mini 原生网口 |
| GRUB/EFI、CPU microcode、i915/amdgpu、ACPI 等 | 启动平台、CPU/显卡差异；保留 R3 的 U-Boot/TF-A/设备树 |
| 主线无线驱动、hostapd/wpad 多种构建变体 | 按最终 MTK 无线栈选择；x86 中不少是 `m`，不能全部变成 `y` |
| MHI/PCIe WWAN、t7xx、各种 vendor QMI 驱动和拨号工具 | 当前 Key-B 是 USB；保留已有 MM 路线，避免抢占同一控制口/USB interface。未来实际外设再增加驱动 |
| `autocore` | 目标没有这个名称，应保留已有 `autocore-arm`，并非原样复制 x86 的 init |
| `bridger` | 目标索引没有；主线桥卸载辅助与私有 HNAT 不同，不能当成缺失必需加速依赖补进来 |
| `kmod-nft-fullcone` | 目标索引没有；本树采用其他 Full Cone 实现，不能从 x86 只复制这个模块 |
| `luci-ssl` / `libustream-mbedtls` | 当前目标用 `libustream-openssl`；优先 `luci-ssl-openssl`，避免 libustream 变体互斥 |
| `ntfs-3g` 与 `ntfs3-mount` | 元数据明确声明冲突，应选择挂载策略 |
| `tc-tiny` 与 `tc-full` | 使用 alternatives，可共存但没有必要重复补齐；完整环境优先 full，不能把重复当编译冲突 |

仅根据两边现有真实包索引，x86 已选中而 R3 不存在的包是上表的 `autocore`、`bridger`、`kmod-nft-fullcone` 三项。这个结论不表示所有剩余包都可无条件编译、同装、默认启动。

## fw4/nft 与 MTK 专属包、别名

不存在一个必须另装、名字类似 `firewall4-hnat` 或 `nftables-hnat` 的通用替换包。本树的组合是 **firewall4 + nftables-json + 配套内核/HNAT/WARP 驱动及配置**。

| 具体包/接口 | 含义 |
| --- | --- |
| `firewall4` → `uci-firewall` | 防火墙虚拟提供者 |
| `nftables-json` → `nftables` | nft 命令与 JSON 支持，不是 MTK 加速变种 |
| `kmod-mediatek_hnat` → 模块 `mtkhnat` | 包名与运行时模块名不同，是本树的 HNAT 核心 |
| `kmod-warp` → 模块 `mtk_warp` | 私有无线 WED/WO 配套；不是 Cloudflare WARP |
| `luci-app-turboacc-mtk` | MTK HNAT 控制页面/服务，与通用 turboacc 互斥 |
| `kmod-nft-offload` | 通用 nft flowtable offload，不等于私有 HNAT 驱动，不应据此替换私有加速链 |
| `miniupnpd-nftables` → `miniupnpd` | fw4 环境优先这个 UPnP 实现，避免拉入 iptables 版本 |
| `iptables-nft` → `iptables` | 兼容命令前端；不保证所有传统扩展都支持 nft 转译 |
| `iptables-zz-legacy` → `iptables`/`iptables-legacy` | 另一提供者；不能因为依赖写着 `+iptables` 就认为一定是 nft 版本 |
| `tc-full` → `tc`；`mihomo-meta` → `mihomo` | 依赖解析还存在这类虚拟名，清单已保存 PROVIDES |

Full Cone NAT 决定 NAT 映射行为，HNAT 决定转发执行路径，两者不是同一功能。`target/linux/generic/pending-6.6/682-add-bcm-fullconenat-support.patch` 在内核中提供 `nf_conntrack_nat_mode`，MTK turboacc 会写这个 sysctl；此外本树还有 `kmod-ipt-fullconenat`。这不能简单等价为 x86 的 nft FULLCONE 表达式，更不能从 x86 单独移入 `kmod-nft-fullcone` 就宣称配套。

`mtkhqos_util` 是硬件 QoS 相关工具，但不能把它视为 CAKE/HFSC 的等价物。`luci-app-eqos-mtk` 实际混合使用 HNAT QDMA 队列和 tc/IFB/legacy ebtables；部分客户端使用硬件队列，超出其分配范围的客户端通过 0x99 标记转入软件整形。这类包确实存在，但名称不能证明任意模式都与完整 HNAT 直通兼容。

## QoSmate：安装、启用、停用和恢复

本机 QoSmate 的 `etc/config/qosmate` 默认为 `enabled=1`。init 带 `START=99`，hotplug 可在接口上线后 enable/restart。`start_service()` 还会主动写回 `enabled=1`。因此真正的“预装停用”必须同时处理 UCI、启动链接、autorate、hotplug；只写 `enabled=0` 却仍允许开机调用 start，或只执行 service disable 而保留 enabled/hotplug，都不充分。

也不能因该包没有自定义 postinst 就认为不会自动启用：`package/base-files/files/lib/functions.sh:390-399` 的 default_postinst 对 init 服务执行 enable；设备在线安装时还会 start。应以最终安装脚本、rootfs 的 rc.d 状态和 hotplug 行为核对。

| 状态 | HNAT 结论 |
| --- | --- |
| 只安装 tc/CAKE/HFSC/IFB 等能力，服务确实停用且无规则/队列残留 | 没看到由这些包的存在自动永久禁用 HNAT 的机制 |
| 启用 QoSmate 对某条链路整形 | 该流量必须经过软件队列；硬件快路径会绕过分类/整形。不能承诺同一条流同时保留完整硬件直通与完整 CAKE/HFSC |
| 正常停止 QoSmate | 当前 stop 清理 nft 表、dscptag include、WAN/IFB qdisc、IFB、hotplug 并 reload network/firewall；有恢复路径 |
| 手工关闭 HNAT、普通 flow offload 后再停止 QoSmate | stop 不负责恢复之前的 MTK turboacc UCI 或 hook 状态，需要恢复自己的基线 |
| 异常退出、WAN 名称改变、同时运行另一 QoS、残留持久配置 | 可能留下软件路径或错误规则；需要逐项清理后重建连接/必要时重启，属于可恢复状态，不是烧坏/永久丢失硬件能力 |

其状态检查只看 firewall UCI 的软件/硬件 offload 标志，不能完整检测私有 HNAT 的 `hook_toggle`。在本树上必须增加对 MTK 加速状态的识别与互斥，不能仅相信 QoSmate 页面“offloading disabled”。

当前后端还有打包完整性问题：Makefile 仍标 `0.5.48`，只安装 4 个主要文件，而 init 已包含独立 autorate、组件完整性检测与联网修复流程。应将所选版本所需文件和依赖完整打包，避免首启临时安装/更新使行为偏离构建时审计。

建议后续实现两个清晰的运行模式：默认 HNAT 模式（QoSmate 完全停用）；用户明确启用 QoS 后切换整形模式，并保存/恢复原有加速配置。恢复必须恢复原值，而不是无条件把所有 offload 开关设为 1。

## 其他会影响加速或稳定性的组合

| 组合/软件 | 具体影响与迁移决策 |
| --- | --- |
| SQM、qosify、nft-qos、eqos、其他 CAKE/HFSC/tc 脚本 | 与 QoSmate 相同，需要逐包检查队列/规则；不能多套同时管理同一接口 |
| Nikki/PassWall、UA3F、UAmask | TPROXY、TUN、NFQUEUE 或内容改写流量需要经过软件；可保留未被接管流量的硬件加速，但须检查标记/旁路和实际绑定 |
| banIP、geoip-shell、动态黑名单、家长控制、按流统计 | 快路径可能绕过后续规则检查、计数或策略变化。既有连接与新连接分别测试；“规则存在”不代表硬件绑定流持续接受这些检查 |
| VPN/Tailscale/ZeroTier/SoftEther | 隧道和本机加解密不等同普通 NAT 转发；安装不代表全局禁用 HNAT，但接管流量不应预期普通 HNAT 吞吐 |
| 多 WAN/PBR/分流/连接标记 | 冲突取决于规则、路由、mark 和现有硬件流；不能靠卸载标志一概判断 |
| AdGuard Home、SmartDNS、dnsmasq-full、DNS 转发/代理 | 重点是 53 端口归属、回环转发、上游和 DHCP 分工；DNS 服务自身通常不是全局 HNAT 开关 |
| 多组 mDNS/组播代理、多个 NTP/DHCP 服务 | 需选一个责任主体和明确接口；可能发生 5353/123/67 端口冲突或重复响应 |
| `irqbalance` 与 `mtk-smp` | 可能争抢 IRQ 亲和性；保留 MTK 调优策略后再决定是否启用 irqbalance |
| advancedplus、定时任务、watchdog | 会改配置、重启网络/服务；检查默认动作。共享默认脚本已处理 advancedplus 向 profile 追加 zsh 的问题 |

本树 HNAT 有 `HNAT_EXCEPTION_TAG=0x99` 的排除检查，且 HQoS 会读取 skb mark 的部分位。代理、PBR/QoS 不应随意重用标记位；需要按实际规则集验证，不能从“支持 nft”推出“支持所有 HNAT 组合”。

`luci-app-turboacc-mtk` 自身也有副作用：AP Mode 填入有效地址时会删除 WAN/WWAN/WAN6、改桥和 DHCP，并提交网络配置；start 还会重启防火墙。它的 `stop_service()` 调用 `stop` 的写法也应修正/验证，不能直接把 stop 当作可靠的 HNAT 关闭接口。默认路由模式不要误填 AP Mode。

## uhttpd 与 nginx

**本次功能集合建议以 uhttpd + uhttpd-mod-ubus + luci-ssl-openssl 为默认管理入口。**

uhttpd 是 LuCI 默认集成路径，已有 `luci-app-uhttpd` 和第三方应用可能直接写 `/etc/config/uhttpd`、重启 uhttpd、依赖 CGI 路由。更换 nginx 不能提升 HNAT；大部分网络后端也不依赖管理 Web 服务器。

nginx 更适合多个站点、大量静态文件、反向代理、统一 TLS 入口。确实需要时可以另设监听地址/端口，或在审计 CGI、ubus、文件上传、ttyd/WebSocket、PHP 和插件脚本后迁移 LuCI。不能让两个服务默认抢占 80/443，也不能把 nginx-mod-luci/uWSGI 等依赖漏掉。

依据：[OpenWrt uHTTPd 文档](https://openwrt.org/docs/guide-user/services/webserver/http.uhttpd)、[LuCI Web 服务器集成](https://openwrt.org/docs/guide-user/luci/luci.essentials)，并核对当前 `feeds/luci/collections/luci-nginx/Makefile`。

## 新源码与第三方源的处理

2026-09-06 使用 `git ls-remote` 只读核对：R3 主树、packages、LuCI、routing、QModem 当前 HEAD 与各自所用远端分支 HEAD 一致。packages 为 `0cb6db25`、LuCI `80ed8a44`、routing `00619bc7`、QModem `c1db0fe2`、主树 `ec9ef10e`。

随后核对了全部 22 个已接入仓库，包括 telephony、daed 及 15 个独立第三方仓库，均与所用远端分支/默认 HEAD 一致。因此本次没有必要为了“最新”再执行一次全量 feeds 更新。上游长期未维护的软件，即使 HEAD 最新，也不能据此认定兼容最新 LuCI/内核。

R3 的 packages/LuCI 已比本地 x86 的 2026-06-08 更新，例如 curl 8.19.0 对 8.12.1、OpenSSL 3.0.20 对 3.0.18、SmartDNS 48.4 对 48。主树某些核心库/工具仍较旧（例如 ucode、libubox、uqmi），不能仅凭仓库 HEAD 日期宣称每个组件版本都更新。

“所用分支源码最新”和“每个上游项目最新大版本”不同：24.10 feed 可能有意保持旧稳定系列。后续按功能生成源码版本清单、固定提交；需要越级升级的包，连同依赖和补丁检查，不能用盲目升级全部底层组件实现“最新”。

- netspeedtest 的旧地址 `sirpdboy/luci-app-netspeedtest` 不应继续使用；当前公开仓库是 [sirpdboy/netspeedtest](https://github.com/sirpdboy/netspeedtest)。其 README 仍包含旧 clone 地址，所以要按实际仓库内容核查。目录包含 `luci-app-netspeedtest`、`homebox`、`ookla-speedtest`。
- 新仓库的 [homebox Makefile](https://github.com/sirpdboy/netspeedtest/blob/main/homebox/Makefile) 与 [Ookla Makefile](https://github.com/sirpdboy/netspeedtest/blob/main/ookla-speedtest/Makefile) 都采用预编译程序，不能称为所有组件从源码编译。已实际下载 homebox 1.0.1 arm64 和 Ookla 1.2.0 aarch64：两个 SHA-256 均匹配 recipe，归档中的安装目标文件存在，均为 ELF64 AArch64、无 PT_INTERP/PT_DYNAMIC。见 [下载/架构结果](netspeedtest-aarch64-downloads.json)。已排除这两个当前 URL/哈希/架构问题，但尚未验证 LuCI、完整打包和实机测速功能，不能把这个结果当作整包编译测试。
- 当前共享源列表已注释旧 netspeedtest，本地 x86 实际选中的是通用 `speedtest-cli`；它与新仓库的 `ookla-speedtest` 不是同一个包。不能把之前“源获取失败”当成所有测速工具不可用。
- 旧 netspeedtest 还存在可追溯的同名覆盖问题：x86 `tmp/.packageinfo:233476` 中 Python speedtest-cli 2.1.3 带有 `Override: netspeedtest/speedtest-cli`；本地其他旧树的 netspeedtest 调用 `/usr/bin/speedtest --accept-gdpr --accept-license --progress=no` 并解析 Ookla 的 `Result URL`。Python 同名包无法直接满足这个接口。旧 homebox 还在 Build/Prepare 中无哈希 wget 下载；最新公开仓库已改为独立 ookla-speedtest 和标准归档哈希，后续使用新结构，不恢复旧目录来规避拉取问题。旧构建产物成功不代表当前源码或运行接口正确。
- `prepare_custom.py compat` 已对 QModem 同名 ndisc6 和 mihomo 双向 CONFLICTS 导致的递归依赖作过兼容处理；更新后须重新检查，不要 `feeds install -f` 覆盖 MTK 核心包。
- 当前索引中 athena-led、onliner、luci-app-qosmate 有同 Makefile 的重复包声明；应修正混用 luci.mk 与手工 BuildPackage 的构建方式。重复声明是缺陷信号，但不能未编译就称一定构建失败。
- **UA-Mask 路径错误已复现**：`openwrt/package/Makefile:3` 在 include rules.mk 后使用 lastword MAKEFILE_LIST，得到 include 目录，最终 UAMASK_SOURCE_DIR 错算为 `/home/beihai`。DUMP 报 `/home/beihai/VERSION` 不存在、版本为 1；Build/Prepare 后续也会从错误目录复制 core。命令行对照仅把 UAMASK_SOURCE_DIR 指向真实仓库后，版本恢复为 0.4.3-r1。见 [复现日志](uamask-path-reproduction.log)。这需要修正路径计算，不是 ARM 本身不支持。
- **UA3F 缺直接 host 工具依赖**：`package/UA3F/openwrt/Makefile:40` 在 Prepare 直接运行 po2lmo，但 `PKG_BUILD_DEPENDS` 只有 golang/host，应补 luci-base/host 或采用标准 LuCI 翻译构建方式。宿主恰好装有 po2lmo 或其他包先构建出来，会掩盖干净/并行构建中的顺序问题；这里确认的是依赖声明缺陷，未实际复现完整编译失败。
- `luci-app-modem` 所依赖的 quectel-CM-5G 在本树实际存在，不能误报缺依赖；但其版本 1.6.4 和 QModem 的 quectel-CM-5G-M 3.2.0 是不同包，且都不是现有 MM 之外需要默认启动的第二拨号器。
- 源码地址能访问、Kconfig 能展开、下载成功、编译成功、固件打包成功、实机可用是不同层次。此报告不会把前三者冒充后面结果。

并行审计覆盖了共享列表中的 15 个独立第三方源，没有再发现另一个与旧 homebox 相同的 Prepare 内直接无哈希 wget 模式；这不等于所有源码都已编译通过。其他联网更新、iStore/主题脚本、DNS 改写等属于运行阶段问题，需与明确的构建缺陷分开处理。

## daed：新增必选功能

采用现代 `luci-app-daed + daed + daed-geoip + daed-geosite` 路线，并同步补齐 BTF/BPF 内核支持。旧 feeds/daed 实际是 daed-next，会拉入 host/target Node；不采用它。现代 recipe 把同版本官方 web.zip 嵌入 Go 后端，不要求本机构建 Node，也不要求设备运行 Node。

24.10 packages feed 原始 recipe 仍为 1.24.0，而上游主程序已发布 1.27.0；构建脚本现在在 feeds 更新后固定 1.27.0，并同步源码和 web.zip 哈希。这保留了稳定分支的其他包版本，同时避免只改版本号而遗漏配套网页资源。仍需核对 Go/BPF 构建变化。

当前 1.27.0 recipe 的隔离配置试验中，17 项补全请求均保留、无 Node 被依赖引入、原基线包没有被取消。仍需实测 1.27.0 后端构建、网页/API、订阅与协议、DNS/IPv6/UDP、trace、数据库持久化、MM 重拨和 tc/BPF 清理。daed 与 HNAT/QoSmate 的组合按实际流量验证，不能把 eBPF 软件路径当作 HNAT。详见 [daed 适配方案](daed-adaptation.md)。

## 容量、默认服务和升级路线

R3 Mini 有 2GB RAM、8GB eMMC、128MB NAND；Key-B 使用 USB。依据：[板卡官方规格](https://wiki.banana-pi.org/Banana_Pi_BPI-R3_Mini)。x86 配置的 ROOTFS_PARTSIZE 为 2048，R3 当前为 160，不能复制 x86 分区参数；R3 的 image recipe 还包含 NAND factory、FIT 和 U-Boot 布局。

完整软件环境更适合 eMMC/NVMe；NAND 的恢复镜像应保留精简可救援能力。最终容量必须看实际 rootfs/IPK/镜像产物，不能用包数估算出精确体积，也不能只放大 IMAGE_SIZE 就认为 NAND 放得下。

源码带大量服务时应预装但默认停止非必要服务；这需要真正审计 init/postinst/uci-defaults/hotplug/cron，而不是仅把 LuCI 的 enabled 设为 0。比如 SSH、DNS、DHCP、NTP、共享、代理、QoS 的主服务需要明确。

当前共享 Portal 默认脚本有 WAN input=ACCEPT、取消 Dropbear/ttyd 接口限制的逻辑。新增后台会扩大这个现有策略的实际覆盖面，迁移时须按现有用户访问需求重新核对监听地址与端口，不能把它当作无关的主题文件整体复制。

当前 VERSION_REPO 指向官方 24.10-SNAPSHOT。私有 MTK 内核及本地构建 kmod 不能随意混装官方通用包库的 kmod；应保存自己同一构建的包索引/签名与 kernel ABI。普通用户态包也要满足 libc/libubox/ucode/OpenSSL 等 ABI。

## 实施和验收次序

1. 保留当前 MM/Portal 客制化，修复并验证 MTK 硬件/无线/HNAT 基线；用实际设备树和产物核验，不只比对 DEFAULT 包名。
2. 将所需用户功能整理为独立配置片段，使用已核对的最新兼容源；排除 Node、x86 驱动和多余变体，让依赖系统重算。
3. 修复三方源打包缺陷，明确每个服务的默认状态、端口、规则与恢复动作。
4. 隔离 defconfig 检查缺符号/递归依赖/静默取消选择；再逐组 download/compile，最后做完整镜像和容量检查。
5. 实机分别验证普通有线转发、Wi-Fi→有线、USB 5G→LAN、IPv4/IPv6、代理/VPN、QoS 启停和重启后恢复。USB 5G 能拨号不等于自动保证与原生以太网相同的 HNAT 路径。
6. 验证加速时让客户端通过路由器对外部服务器测速，检查 PPE/HNAT 绑定和 CPU；路由器自己运行 speedtest/iperf3 测到的是本机处理路径，不能单独证明转发加速成功或失败。

当前原始配置通过了隔离 Kconfig 展开，日志见 [current-normalization.log](current-normalization.log)，源 `.config` 的 SHA-256 未改变。Kconfig 成功不解决前述缺失 DEFAULT 驱动问题，也不是固件编译通过的证明。

另外完成了两组 `/tmp` 候选配置试验：

- 通用软件候选：403 项请求均保留，依赖展开为 875 个真实包，无 target Node；filebrowser/smartdns-ui 仍需要 host Node，不能漏算。ethtool 因 ethtool-full 从 y 变为 m，符合完整工具变体选择。但仍发现 ntfs-3g 与 ntfs3-mount 同选 y 的声明冲突，说明 conf 返回 0 不足以证明可以打包。见 [软件试验结果](software-trial-normalization.json)。
- daed 内核/应用候选：17 项请求均保留，315 个真实包，无 Node、无基线包丢失、无选中 y 包的声明冲突。见 [daed 试验结果](daed-trial-normalization.json)。

随后补做合并试验：保留 ntfs3-mount、取消 ntfs-3g，合并现代 daed/BPF 配置，并启用构建机 Node 24 官方二进制路线。22 项后续覆盖全部保留，展开为 880 个真实包；没有 target Node，已选 y 包之间的已声明冲突为零。见 [合并结果](combined-trial-normalization.json)。host Node 二进制路线只在配置层通过，仍需实际下载和构建验证；也不会自动修复 UA-Mask 路径、QoSmate 打包或 MTK 硬件基线。

以上都是审计候选，未作为正式 defconfig 应用，也没有把源代码缺陷或服务冲突当成配置展开能够验证的内容。
