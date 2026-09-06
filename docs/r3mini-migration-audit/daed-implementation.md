# daed 1.27.0 实现与运行时适配

本次适配固定使用 `feeds/packages/net/daed` 和 `feeds/luci/applications/luci-app-daed`。历史 `daed-next` feed 仍然排除：它要求 Node/Next.js 构建和 target Node 运行时，与本固件选择的预编译网页嵌入路线不符。

## 源码与依赖

daed 已升级到 v1.27.0。源码、递归子模块和网页资源均固定校验：

| 项目 | 固定值 |
| --- | --- |
| daed tag/commit | `v1.27.0` / `06857f52c33cc3264aea9eb90431afbe8909073c` |
| dae-wing 子模块 | `6bb6a310ef3d98bea691fd5955cc703306835546` |
| dae-core 子模块 | `7e67e31e241a6d2cc5f2b5ff228b4fb5faf6d24a` |
| OpenWrt 源码归档 SHA-256 | `f848f70c6f1fb4fb43d6bfe14de81a5653ff6fa5e65ba0fd1f5970af97ed8739` |
| v1.27.0 `web.zip` SHA-256 | `da8755fb2cabfab392854e807e385b12d9e9842d6c8b5e347284d1ae0e582bfc` |

配方仍由 Go/BPF 源码构建后端，并把同版本官方 `web.zip` 嵌入后端；设备不需要 Node，LuCI 继续由 uhttpd 提供。daed 自己监听默认 `0.0.0.0:2023`，与 uhttpd 的管理端口分开。

daed 的包依赖闭包为：

| 包 | 作用 |
| --- | --- |
| `daed` | aarch64/musl 后端、网页、dae 和 eBPF 程序 |
| `daed-geoip` + `v2ray-geoip` | GeoIP 数据链接 |
| `daed-geosite` + `v2ray-geosite` | GeoSite 数据链接 |
| `ca-bundle` | 订阅、节点和资源下载的 CA 根证书 |
| `kmod-sched-core`, `kmod-sched-bpf` | tc/clsact 与 BPF filter |
| `kmod-xdp-sockets-diag` | XDP socket 诊断依赖 |
| `kmod-veth` | dae 的网络命名空间 veth |
| `golang/host`, `bpf-headers` | 构建期 Go 和 BPF 头文件 |
| `luci-app-daed` | LuCI 配置/状态/日志页面，依赖上述三个 daed 包 |

dae-core 的 v1.27.0 文档还要求内核启用 `BPF`、`BPF_SYSCALL`、`BPF_JIT`、`CGROUPS`、`KPROBES`、`KPROBE_EVENTS`、`BPF_EVENTS`、`BPF_STREAM_PARSER`、`NET_INGRESS`、`NET_EGRESS`、`NET_CLS_ACT`、`NET_CLS_BPF`、`NET_SCH_INGRESS`、`DEBUG_INFO` 和 `DEBUG_INFO_BTF`，并关闭 `DEBUG_INFO_REDUCED`。当前主配置已经选择 BPF host 工具链；构建时使用 feeds 中的 Go 1.23.12。daed-wing 声明 `go 1.22.0` 和 `toolchain go1.23.6`，因此该 feed 工具链满足它的最低版本。主机上另装的 Go 版本不代表固件使用的 Go 版本。共享 `include/bpf.mk` 里的 `BPF_KARCH=mips` 是当前 OpenWrt BPF 构建设计的一部分，应保持原样；它不表示 daed 用户态后端要按 MIPS 编译，也不能因为目标设备用户态是 ARM64 就直接改成 `arm64`。

## init、禁用状态和接口变化

默认 `/etc/config/daed` 保持 `option enabled '0'`。init 脚本现在有以下行为：

1. 禁用时 `start` 正常返回，不创建 procd 实例，也不触发 respawn；缺失或不可执行的后端只在启用时报告错误。
2. 每次 `reload` 先删除旧的 daed procd 实例，再按最新 UCI 配置重新创建。这样从启用改为禁用时不会因为原来的 init 逻辑只调用 `start_service()` 而留下一个仍在运行的进程。
3. 启动前创建 `/var/log/daed`，避免首次启动时 lumberjack 因父目录不存在而打不开日志。
4. `STOP=10` 让服务在网络拆除前停止。
5. init 不调用 `tc`, `nft`, `ip rule` 或全局清理命令。dae 只负责它自己的 BPF/tc 对象，停止时不会由包装脚本删除 QoSmate、HNAT 或其他代理创建的对象。

daed 1.27.0 自带 `InterfaceManager`，直接订阅 netlink link 事件；配置的 LAN/WAN 接口不存在时会延迟绑定，接口重新创建后会重新添加自己的 clsact 和 BPF filter。因此外部接口热插拔重启默认关闭：

```uci
config daed 'config'
	option enabled '0'
	option hotplug '0'
```

如果某个 R3 Mini 的 ModemManager/USB WAN 场景经过实机验证仍需要重启整个 daed，可以显式开启并列出 netifd 逻辑网络：

```uci
config daed 'config'
	option enabled '1'
	option hotplug '1'
	list hotplug_network 'wan'
	list hotplug_network 'wan6'
	list hotplug_network 'wwan'
```

只有 `enabled=1` 且 `hotplug=1` 时才注册 `procd_add_interface_trigger`。空列表不会注册接口触发器。即使旧触发器在禁用操作前已经存在，`reload_service()` 也会杀掉旧实例并重新提交只含配置触发器的服务定义，后续接口事件不会重新拉起 disabled 服务。由于热插拔重启会重新加载 dae、重建网络命名空间并短暂中断连接，默认应优先依赖 dae 自身的 netlink 重绑定。

## LuCI 检查

现有 LuCI 应用使用现代 `form`, `uci`, `rpc`, `poll` 和 `fs` 模块，菜单、ACL、配置和日志视图与当前 LuCI 分支接口一致。它没有 nginx 或 Node 依赖；daed Web/API 仍从状态页的独立 2023 端口打开。

同时修正了状态页读取错误的 UCI 字段：原页面读取不存在的 `address`，所以自定义监听端口仍会生成 2023 链接；现在读取 init 使用的 `listen_addr`。页面额外显示 `hotplug` 开关和 `hotplug_network` 动态列表，列表仅在开关打开时显示。

## 可重复补丁

由于 `feeds/packages` 和 `feeds/luci` 是独立 git checkout，根仓库不会自然记录它们的修改。已将嵌套 feed 修改保存为：

- `patches/r3mini/0001-packages-daed-v1.27-runtime.patch`
- `patches/r3mini/0002-luci-app-daed-runtime-options.patch`

在重新更新 feed 后，从固件根目录执行：

```sh
git -C feeds/packages apply ../../patches/r3mini/0001-packages-daed-v1.27-runtime.patch
git -C feeds/luci apply ../../patches/r3mini/0002-luci-app-daed-runtime-options.patch
```

用 `git -C feeds/packages apply --reverse --check ...` 和 `git -C feeds/luci apply --reverse --check ...` 可检查当前修改是否与补丁一致。补丁不触碰主 `.config`、`feeds.conf.default` 或 MTK/第三方包。

## 已做检查与剩余限制

已完成源码归档、递归子模块、网页资源的 SHA-256 复核；v1.24.0 归档哈希也按同一 OpenWrt rawgit 流程复现过，确认哈希计算方式一致。已对 init 执行 `sh -n`，对 LuCI 两个视图执行 `node --check`，并对两个嵌套 feed 的补丁执行 reverse `git apply --check`。

当前没有进行完整固件编译或设备验证。合入前仍需在目标固件完成：

1. `make package/feeds/packages/daed/prepare` 和 daed aarch64/musl 后端、control/trace BPF 生成；确认 `CONFIG_BPF_TOOLCHAIN_HOST`、BTF、BPF_EVENTS 和 BPF 相关模块实际落入最终 kernel 配置。
2. 首次启动、enabled 开关、UCI reload、进程崩溃 respawn、日志轮转以及升级后 `/etc/daed/wing.db` 持久化。
3. LuCI 自定义 `listen_addr`、状态链接、登录、配置编辑、订阅/资源更新、WebSocket、日志和 trace 页面。
4. 有线 LAN、Wi-Fi LAN、普通 WAN、`wwan`/ModemManager 重拨、USB 拔插、WAN 接口重建，以及 `hotplug=0` 时 dae 自身 InterfaceManager 的重新绑定。
5. daed 与 MTK HNAT、QoSmate、Nikki/PassWall 同时安装时，分别检查普通直连、被代理流量和 QoS 流量的 tc/BPF/HNAT 路径；停止 daed 后确认其他服务的 clsact/filter 没有被删除。

在这些实机检查完成前，只能把 daed 标记为“已完成源码和构建前适配”，不能标记为所有运行时功能已验证。
