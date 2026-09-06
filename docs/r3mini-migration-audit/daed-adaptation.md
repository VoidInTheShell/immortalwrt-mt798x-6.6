# daed 补选与 R3 Mini 适配要求

用户明确要求后续补选 daed，即使 x86 原配置未选。它是新增功能，不能因不在 x86 差异表中而漏掉。此文件记录实现依据和验收条件；当前生产 `.config` 未修改，尚未完成目标编译或实机功能验证。

## 选择现代 daed，排除旧 daed-next

| 来源 | 当前实现 | 结论 |
| --- | --- | --- |
| 历史 `feeds/daed`，sbwml/luci-app-daed-next（已从 feeds 配置移除） | 仓库 HEAD 停在 2024-01-15；后端包 daed-next 构建依赖 node/host、node-yarn/host，运行依赖 node，另起 Next.js 服务 | 不选，违反暂缓 Node 的要求 |
| `feeds/packages/net/daed` + `feeds/luci/applications/luci-app-daed` | 当前包版本已固定为 1.27.0；Go/BPF 后端从源码编译，将同版本官方 release 的 web.zip 嵌入后端，不依赖 target Node 或 host Node | 以此打包方式为基础升级适配 |
| 上游 daed 主程序 | 截至 2026-09-06，主程序稳定 tag 最新为 v1.27.0，提交 `06857f52c33cc3264aea9eb90431afbe8909073c` | 该版本已由构建脚本固定；更新源码、子模块、网页资源和两类哈希，并验证构建接口 |

已用 `git ls-remote --tags --refs https://github.com/daeuniverse/daed.git 'refs/tags/v1.*'` 核对主程序 tags，并核对 [v1.27.0 发布页](https://github.com/daeuniverse/daed/releases/tag/v1.27.0)。不能直接依赖仓库 `/releases/latest`：该仓库也发布 dae-lang-core 等组件，latest 可能指向组件 release。

主程序 tag 还固定 `wing` 子模块（dae-wing），后者包含其配套 dae-core；更新时必须保留递归子模块版本关系，不能独立抓三个仓库的最新 HEAD 后拼装。网页也必须与选定主程序版本匹配。

已只读获取 v1.27.0 和其 wing 子模块到 `/tmp`，核实 wing 固定为 `6bb6a310ef3d98bea691fd5955cc703306835546`（2025-12-03），它又固定 dae-core 为 `7e67e31e241a6d2cc5f2b5ff228b4fb5faf6d24a`。wing/go.mod 仍为 go 1.22.0、toolchain go1.23.6。因此最新 daed release 不意味着每个嵌入依赖都追到各自最新 HEAD；若要越级更新核心，应作为单独兼容移植处理。

实际下载 v1.27.0 官方 web.zip 后，SHA-256 为 `da8755fb2cabfab392854e807e385b12d9e9842d6c8b5e347284d1ae0e582bfc`；归档有 `web/index.html` 和 497 个条目，目录符合现有嵌入方式，并包含浏览器 LSP/Monaco Worker。源码 `apps/web/src/monaco.ts:17,94` 使用 browser Worker，新编辑器功能不要求路由器再起一个 Node LSP 服务。见 [源码固定版本及网页核验](daed-1.27.0-source-web.json)。这里只验证了官方资源内容，尚未执行网页和后端联调。

当前 1.27.0 打包启用 `embedallowed,trace`，不只是装一个网页入口。独立 `dae` 服务无需与 daed 同时运行。预编译网页资源省去 Node 构建时间，但应明确它是官方构建的资源，并非本机把全部前端源码重编了一遍。

## 内核和构建工具链

6.6 内核版本满足 dae 的基础版本要求，但当前配置缺少 BTF、BPF_EVENTS 等能力，不能只补 `CONFIG_PACKAGE_daed=y`。

已用当前构建系统在 `/tmp` 隔离展开以下候选配置：

```text
CONFIG_PACKAGE_luci-app-daed=y
CONFIG_PACKAGE_daed=y
CONFIG_PACKAGE_daed-geoip=y
CONFIG_PACKAGE_daed-geosite=y
CONFIG_DEVEL=y
CONFIG_BPF_TOOLCHAIN_HOST=y
# CONFIG_BPF_TOOLCHAIN_NONE is not set
CONFIG_KERNEL_DEBUG_INFO=y
# CONFIG_KERNEL_DEBUG_INFO_REDUCED is not set
CONFIG_KERNEL_DEBUG_INFO_BTF=y
CONFIG_KERNEL_BPF_EVENTS=y
CONFIG_KERNEL_CGROUP_BPF=y
CONFIG_KERNEL_BPF_STREAM_PARSER=y
CONFIG_KERNEL_XDP_SOCKETS=y
# CONFIG_PACKAGE_luci-app-daed-next is not set
# CONFIG_PACKAGE_daed-next is not set
# CONFIG_PACKAGE_node is not set
```

17 项请求均保留，解析后 315 个真实软件包，无 Node 包、无原基线包被取消、无已选 y 包之间声明的冲突，见 [检查结果](daed-trial-normalization.json) 和 [日志](daed-trial-normalization.log)。这个结果针对当前 1.27.0 recipe 的配置依赖，不是 1.27.0 编译通过证明。

依赖自动补入 kmod-sched-bpf、veth、XDP 诊断等，并展开 KPROBES、KPROBE_EVENTS、PERF_EVENTS、FTRACE 和 BTF_MODULES 等内核项。最终 kernel `.config` 还需核对 BPF_SYSCALL、BPF_JIT、CGROUPS、NET_INGRESS/EGRESS、NET_CLS_ACT、NET_CLS_BPF、NET_SCH_INGRESS。要求依据：[dae 官方内核配置说明](https://github.com/daeuniverse/dae/blob/main/docs/en/README.md)，最终以所固定 dae-core 版本为准。

本机构建工具已有 clang/LLVM 18.1.8，可测试 BPF_TOOLCHAIN_HOST 以减少另编 LLVM 的成本；构建中的 bpf-headers、dwarves/pahole、BTF 生成仍须实测。不能靠默认展开的 MODULE_ALLOW_BTF_MISMATCH 掩盖 MTK 私有模块的 ABI/BTF 问题。

另复核了容易误判的 `include/bpf.mk:39` 中 `BPF_KARCH:=mips`：这与 [OpenWrt 24.10 上游 bpf.mk](https://github.com/openwrt/openwrt/blob/openwrt-24.10/include/bpf.mk) 和其 [bpf-headers 构建方式](https://github.com/openwrt/openwrt/blob/openwrt-24.10/package/kernel/bpf-headers/Makefile) 一致，属于这套 BPF 头文件/字节码生成流程，不能仅凭 mips 字样认定它把路由器目标架构设错。现代 daed recipe 自行通过 bpfel/bpfeb 生成控制程序，并将 trace target 设为 GO_ARCH；R3 应核对最终 arm64 trace 对象和 verifier。不要未经验证把共享 BPF_KARCH 全局替换为 arm64。

`CONFIG_NODEJS_20=y` 一类未激活的版本选择本身不表示 Node 被编译。应检查实际 `CONFIG_PACKAGE_node*` 和 host 构建依赖闭包；现代 daed recipe 不会因残留版本选择自动拉入 Node。

## 服务、Web 与持久数据

当前 `files/daed.init` 已检查 UCI enabled，默认值为 0；这比 QoSmate 的启动语义更容易保持预装停用。默认监听为 `0.0.0.0:2023`，须结合本机 WAN input/管理访问策略设定可访问范围。

daed 自带 Web/API 服务，与 LuCI 使用 uhttpd 或 nginx 无绑定关系。保留 uhttpd 管理 LuCI，daed 用独立端口即可；需要统一入口时另行配置反向代理，并验证 API、WebSocket、鉴权及上传。

当前 conffiles 保护 `/etc/daed/wing.db` 和 `/etc/config/daed`，geoip/geosite 由独立包链接到 v2ray geodata。升级至新版本时核对数据库迁移、实际文件路径、写入权限、持久空间和资源下载，不能只确认页面能打开。

当前 procd 只注册 UCI reload trigger，未见此 init 注册 WAN interface 变化 trigger。R3 的 MM 蜂窝重拨、USB 拔插、逻辑 WAN 与实际 wwan/USB 设备变化需要专门适配。终止进程后的 BPF link、tc filter、路由和接口清理由核心行为决定，必须用正常停止、崩溃和重启分别验证。

## 与 HNAT、QoS 和其他代理的关系

dae 的 eBPF 数据路径属于软件处理，不能称为 MTK HNAT 硬件加速。被代理或整形接管的流量不能承诺继续按照普通 NAT 硬件直通；直连流量是否可保留 HNAT，需要验证该私有驱动的绑定时机、mark、tc/BPF 挂载位置和绕过策略。

默认可预装 daed，但与 Nikki/PassWall/其他透明代理不应同时接管同一接口和同一批连接。QoSmate/SQM 与 dae 都使用 tc 相关能力，停止任一服务时必须只移除自己的对象，避免把另一方的 clsact/filter 一起删掉。

## 完整功能的验收清单

1. aarch64/musl 后端与 BPF 构建、加载和 verifier 日志正常；确认网页和 API 版本匹配。
2. Dashboard 登录、配置编辑/语法提示、节点/订阅、分组选择、测速、资源更新、日志和 trace；新版本新增的前端组件也需测试。
3. geoip/geosite、DNS 分流、防回环，IPv4/IPv6、TCP/UDP；按用户启用的协议逐项检查节点连通，不能用一种协议代替全部。
4. LAN 客户端流量与路由器本机流量分别测试；有线、Wi-Fi、MM 蜂窝 WAN、重拨/拔插/换接口均覆盖。
5. 数据库保存、重启持久、升级迁移、服务 reload/stop/crash 的 BPF/tc 清理，不影响基础联网。
6. HNAT 模式、代理模式、QoS 模式切换：检查普通直连和被接管流量各自路径，以及停止后新连接的硬件绑定恢复。

完成以上构建与实机验收后，才能标记为“全部要求的功能正常且可用”。本次已经把它作为明确迁移项，而没有把菜单可选误写成适配完成。
