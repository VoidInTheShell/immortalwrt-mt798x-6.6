# R3 Mini 硬件 HQoS 实施说明

`mtkhqos_util` 现在只负责 MT7986 QDMA 硬件队列。HNAT 模块的加载、HNAT 选择和 `hook_toggle` 由 TurboACC 管理；HQoS 工具不会接管或修改这些配置。工具也不会创建或清理 nftables、iptables、tc、qdisc 或 IFB 对象。

## 默认行为和启停

安装后的 `/etc/config/mtkhqos` 使用具名的 `global` 段：

~~~uci
config global 'global'
	option enabled '0'
	option hqos '0'
	option txq_num '64'
~~~

`enabled=0` 或 `hqos=0` 时，启动、reload、stop 和网络 hotplug 触发的 one-shot 服务都直接返回。没有本工具留下的运行状态时，stop 不会写任何 debugfs、bridge sysctl、socket buffer 或 HNAT 开关。`/etc/init.d/mtkhqos` 通过 procd 注册一次性命令，并且不设置 `respawn`。

配置好符合实际链路的速率/队列后，把 `enabled` 和 `hqos` 都改为 `1`，执行 `/etc/init.d/mtkhqos restart` 才会申请硬件 HQoS。需要开机自动应用时还要执行 `/etc/init.d/mtkhqos enable`；完整固件的首启流程默认禁用了它的开机链接。启动前必须满足以下条件：

* `/sys/kernel/debug/hnat` 已经存在，HNAT `hook_toggle` 读数为 `enabled`，并且 HNAT 已由 TurboACC 开启。工具不会为了 HQoS 自动加载模块或打开 hook。
* QoSmate、EQOS 或其他软件整形 qdisc 没有运行。工具会拒绝 `qosmate.global.enabled=1`、EQOS enabled=1、QoSmate 运行时 nft/tc 状态以及检测到的 `cake`、`hfsc`、`htb` qdisc；用户需要先停用冲突的队列引擎。
* `txq_num` 在 1 到 64 之间，并且不超过当前驱动实际暴露的 QDMA queue 文件数。MT7986 的上限是 64。

stop 或把配置改回 disabled 后，工具先写 `qos_toggle=0`，由驱动的 `hnat_qos_disable()` 清除 HQoS shaper，再把可见的 QDMA queue 和 scheduler 设置成无整形基线。它只清除自己的状态文件和自己申请的 bridge netfilter sysctl；不会写 `hook_toggle`，不会重置 TurboACC 的 HNAT 选择，也不会全局 flush 防火墙或 tc 规则。

## 可逆的 bridge sysctl

真正启用 HQoS 时，工具只需要让 bridge 上的 mark 能够进入 HNAT 路径，因此最多临时把下面两个值设为 `1`：

* `net.bridge.bridge-nf-call-iptables`
* `net.bridge.bridge-nf-call-ip6tables`

启用前的值保存在 `/var/run/mtkhqos`。停止时只有在当前值仍是工具当时申请的值 `1` 时才恢复旧值；用户或其他服务在此期间改过的值会被保留。`bridge-nf-call-arptables`、VLAN/PPPoE 过滤开关以及 `net.core.rmem_max`/`wmem_max` 从未由该工具修改。

## 队列和输入校验

两个 scheduler 使用 `sch0_*` 和 `sch1_*`。mode 是 `0`（WRR）或 `1`（SP），带宽是 0 到 10,000,000 Kbps；scheduler enabled 时带宽必须大于零。queue 的 id 必须在 `0..txq_num-1`，每个 id 只能出现一次；`minrate`/`maxrate` 是 0 到 100 的百分比且 min 不得超过 max，weight 是 1 到 255，resv 是 0 到 255。所有值先进行十进制校验，再写入驱动，避免非法值经过 shell 算术表达式或驱动的寄存器字段。

默认文件只给出 0 到 15 的示例队列；用户可以增加 16 到 63 的 `queue` 段。工具会先清除 64 个队列的旧 shaper，再应用当前配置，所以删除一个旧 queue 段后 reload 不会留下隐形整形。

## 分类器边界和 mark 要求

这个包只配置 scheduler、QDMA queue 和 `qos_toggle=1`，不提供“按设备自动分配 QoS”的 classifier。要让连接进入指定队列，用户仍需用自己的 nftables/iptables 或其他受控 classifier 在 HNAT 首次学习流之前设置 mark，并且不能让 EQOS/QoSmate 同时管理同一条路径。

MT7986 HNAT 的硬件 queue 编号是 0 到 63。当前 HNAT 快速路径从 packet mark 的低 6 位取 queue id，使用掩码 `0x3f`；设置某个 queue 时应保留 mark 的其他位，例如 `mark = (mark & ~0x3f) | qid`。内核树中的 PPE flow-offload 路径还支持把方向相关的 queue 放在 mark 的第 16 到 21 位，即掩码 `0x3f0000`，实际使用哪一方向字段取决于流量经过的 HNAT/PPE 路径。不要把完整 mark 值直接覆盖成只含 queue 的值，以免破坏其他模块使用的标志位。

HNAT 会在 FOE/flow 首次 bind 时记录 queue。修改 classifier 后，已经 bind 的连接可能继续使用旧 queue；请用新建连接或等待旧流过期验证。若开启 HNAT 的 DSCP queue 映射，驱动可能按 DSCP 覆盖 mark 选择，需把该行为一并纳入 classifier 设计。

## 验证记录

在源码树中可以先运行：

~~~sh
sh -n package/mtk/applications/mtkhqos_util/files/mtkhqos
sh -n package/mtk/applications/mtkhqos_util/files/mtkhqos.init
package/mtk/applications/mtkhqos_util/tests/test-mtkhqos.sh
~~~

这个 smoke test 用临时普通文件模拟 debugfs 和 bridge sysctl，覆盖禁用状态的无副作用路径、带前导零的十进制配置（包括值 `0`）以及启用后停止时的恢复路径，不需要固件编译或 MT7986 硬件。上机时先保持默认 `enabled=0,hqos=0`，确认启动和 stop 不改变 HNAT、bridge sysctl 或 socket buffer；再确认 TurboACC 的 HNAT hook 已启用，停掉 QoSmate/EQOS，单独启用一组 QDMA queue。检查 `qos_toggle`、64 个 `qdma_txq*`、scheduler 读数和新建流的 mark/queue 绑定。
