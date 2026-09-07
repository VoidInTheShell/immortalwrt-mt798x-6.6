# R3 Mini ZeroTier 首次接入修复（Autoneg-r4）

## 问题范围

Autoneg-r3 的 ZeroTier 包中没有固定客户端私钥是正确的安全设计：镜像不能
携带所有设备共用的 `identity.secret`。但首次启动策略又同时做了三件会阻断
首次接入的事：

- `r3mini-defaults` 禁用了 `/etc/init.d/zerotier`，使 procd 不再注册 UCI
  reload trigger；
- 上游 `global.enabled` 默认是 `0`，仅新增网络不会进入启动路径；
- 默认 UCI 没有启用 `/etc/zerotier` 这个持久化目录，identity 只能在启动后
  由临时运行目录间接恢复。

因此 LuCI 里只新增并启用一个网络时，不会可靠地产生 identity，也不会启动
`zerotier-one`。这与硬件加速无关：ZeroTier 使用 TUN 虚拟接口，问题发生在
服务初始化之前。

## r4 行为

1. 固件仍然不包含任何预置或共享的客户端私钥。
2. 空配置启动时，ZeroTier init 会注册配置变更 trigger，但不启动 daemon，
   也不执行等待 daemon 的防火墙脚本。
3. 第一次保存一个 `enabled=1` 的网络时，init 将全局开关提升为启用状态并记录
   一次性初始化标记；之后管理员手动关闭全局开关不会被网络项重新覆盖。
4. 使用 `/usr/bin/zerotier-idtool` 在设备上生成唯一 private identity，先在
   临时文件验证，再原子写入 `/etc/zerotier/identity.secret`（0600）以及其匹配的
   `identity.public`（0644）。UCI 保存同一个 secret，供现有服务配置与升级恢复。
5. 每次服务启动都会从 private identity 重导出 public identity，修正旧逻辑只删除
   `identity.public`、让 daemon 被动重建的状态不一致问题。
6. r3 升级到 r4 的一次性迁移只重新启用 ZeroTier 的 init trigger，不重置其它
   服务选择、不自动加入网络，也不启用空配置的 daemon。

`/etc/zerotier` 与新的迁移标记均列为 conffile/保留项，正常 sysupgrade 会保持
该设备自己的 identity。若管理员故意要重新生成身份，应先退出网络并备份或删除
这对 identity 文件及 UCI 的 `zerotier.global.secret`，而不是复制其他设备的私钥。

## 验证边界

`scripts/r3mini-runtime-fixes-test.py` 以伪造的 `zerotier-idtool` 执行实际 init
函数，验证以下路径：首次已启用网络自动激活、私钥/公钥的持久化和权限、重启时
公钥重新匹配、以及无网络时没有 daemon/密钥/防火墙副作用。镜像检查还会验证
安装后的 init、默认配置、首次启动迁移脚本和包版本。

这项改动没有修改 MTK HNAT、PPE、WARP、WED、GMAC/PHY 或无线驱动。ZeroTier
只会在用户启用第一个网络后启动，因而不会降低已有有线或无线硬件加速能力。
