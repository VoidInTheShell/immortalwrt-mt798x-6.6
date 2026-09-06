# 最终编译前检查记录

日期：2026-09-06。配置迁移、源码适配和编译前准备已完成；**没有启动正式固件编译，也没有刷机或进行目标硬件测试**。机器可读记录见 [final-validation.json](final-validation.json)。

## 配置结果

| 检查 | 结果 |
| --- | --- |
| 设备与存储 | BPI-R3 Mini / MT7986 / ARM64 / eMMC，production 2048 MiB |
| x86 原选择逐项决定 | 1129 项均有记录 |
| 真实软件包选择 | 951 项：948 个 y，3 个 m |
| 仅生成 IPK | hs20-client、hs20-common、hs20-server，维持原实验套件部署边界 |
| 要求缺项 / 禁选项回流 | 0 / 0 |
| 已选包声明冲突 / 重复定义 | 0 / 0 |
| HNAT 与 MM 必选片段 | 均存在，全部正向选择及相关功能开关通过检查 |
| 预设恢复与依赖展开 | 恢复 full.config 后得到同一规范化配置 |
| 源码锁与补丁 | 12 个选中 feeds/第三方仓库固定提交，补丁哈希检查及重复应用识别通过 |

最终 `.config` SHA-256：

```text
204e9db4352415b2b6056b5bec1644268fec45561a8d87394a85dcf26ede3e06
```

完整选择及排除原因见 [migration-decisions.tsv](migration-decisions.tsv)，依赖检查见 [migration-verification.json](migration-verification.json)。选包成功不能代替内核模块真正生成和安装到镜像的检查，后者已加入正式构建脚本。

## 已完成的验证

- Linux 6.6.133 归档 SHA-256 核对，84 个 generic 和 207 个 MTK 覆盖文件，完整 **917 个补丁全部应用成功**。125 个补丁有偏移或 fuzz，0 个拒绝项；最终复核使用已经验证的缓存树。PWM thermal 注册、板级置零条件、HNAT 的设备树 WAN 名称均通过源码检查，见 [kernel-preflight.md](kernel-preflight.md)。
- 主机构建依赖通过：Python 开发文件、固定 setuptools 80.9.0、swig、rsync 和 clang。最后一轮完整配置下载预检成功，8 线程，**21.534 秒**，主要命中此前已下载缓存；这不是编译耗时。
- 分组构建脚本 4 个测试通过，包括真实依赖图、环检测、失败停止、独立日志、续跑和资源变化时保留原计划上限。
- HNAT RPC、MTK HQoS 队列启停/恢复、QoSmate 持久加速状态恢复和关闭状态下不删除其他队列的模拟检查通过。
- MM RPC 的 `%`、缺失 SIM/bearer、可选和非 3GPP 字段检查通过。
- MM 短信的 4 个模拟测试通过，验证 Unicode/标点正文、0600 临时文件、失败清理、非法输入和只读/写权限分离。
- MM 频段检查通过，覆盖真实逗号制式字符串、匿名 UCI 节点、能力组合校验、自动频段复位、设备精确匹配及拨号前应用不递归 ifup。新增前端的 JS/JSON/shell 语法检查通过。

配置恢复和主机预检日志：[r3mini-final-prepare.log](../../logs/r3mini-final-prepare.log)。最后下载记录：[timing-summary.json](../../logs/r3mini-download-ready/timing-summary.json)。

提交前另做了独立目录恢复检查，见 [commit-recovery-validation.json](commit-recovery-validation.json)。使用 12 个固定上游提交的干净源码（Git 对象由本地缓存提供），仅应用提交内补丁、建立 feeds 链接并恢复预设，完整 `--bootstrap --restore-config` 及主机预检成功。恢复后的 951 个包及选择值、481 个组件的依赖图、82 个阶段与当前目录一致，所需功能开关全部通过。新目录不恢复未选中的 QModem/其他调查用源码，因此 `.config` 文本哈希不同；有效设置的差异仅为 QModem feed 标记和未选中应用的三个默认子选项。恢复无需原 x86 目录或个人初始化脚本；冻结输入重新生成预设、功能清单和迁移决策均逐字节一致。新增源码恢复测试 4 项通过，覆盖重复应用、已有修改保护、版本/哈希错误和下载失败清理。

第一次独立检查位于 `/tmp`，完成配置恢复后被构建脚本的 100 GiB 磁盘门槛拒绝；移至工作区构建文件系统后完整预检通过。没有放宽该资源检查，也没有启动正式固件编译。构建缓存、个人备份、原始下载资料和仓库外软链接不属于源码提交。

## 已生成的编译计划

真实包依赖图包含 **481 个组件目标、82 个阶段**。逐组件类别、依赖、线程上限和上游并行声明见 [build-component-jobs.csv](build-component-jobs.csv)；原始计划见 [plan.json](../../logs/r3mini-build/plan.json)。

本次主机可用 24 CPU、约 25 GiB 总内存，预留 4 GiB 后的计划为：普通 C/轻量组件和内核 24，工具链 12，Go/重 C++/MTK 驱动 8，Rust 应用 4，Rust host 2，NaiveProxy/Chromium 5，镜像 4，rootfs 安装 1。这是当前资源下的保守起始上限，不是已经压测证明的最大安全核数；每阶段重新读取资源并只向下调整。

使用 GNU make pipe jobserver，让本树 Ninja 子构建共享任务预算。脚本记录阶段和组件耗时、退出码、RSS 采样及总墙钟时间；没有开始的编译阶段没有虚构耗时。正式构建命令见 [完整预设说明](../../defconfig/README-bpi-r3-mini-full.md)。

## 留给正式构建与实机的检查

编译器/链接器执行、软件安装文件冲突、最终镜像体积尚未验证。构建脚本会在相应阶段检查实际生成的内核 BPF/BTF/HNAT/WWAN 配置、私有模块、两份 WO 固件、AArch64 daed/MM 程序，以及 MM 全套前端文件，缺失即停止。

HNAT 吞吐和 PPE、风扇调速、daed 截获路径、模块拨号/SMS/USSD/频段切换需要真实设备。部分 PCIe modem 的启动固件、厂商专用 USB ID/quirk 没有通用替代，范围见 [驱动补充](modem-extra-drivers.md)。

Go modules、npm/pnpm、Cargo 可能在编译阶段继续下载，因此不宣称完全离线可构建。当前仍有 Radicale3、QModem、rmnet-nss 的三条未选中包依赖警告；它们不在所选编译闭包内。基础库保留当前兼容分支配套版本，不能把这次更新描述为所有上游大版本均已升级。
