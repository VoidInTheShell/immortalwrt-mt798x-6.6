# R3 Mini 自动协商修复前的成功构建基线

记录日期：2026-09-07（Asia/Shanghai）。此记录冻结已有工作，不代表已完成网口自动协商修复或上板验证。

- 源码基线：`3c4f1cd24f`，前序完整 eMMC 配置提交 `8d98145e9e`。
- 构建日志：`logs/r3mini-build-run7/`，82 个阶段、82 次执行全部成功，最后校验阶段开始于 `2026-09-06T20:15:20.718458Z`。
- 调度器记录本轮耗时：4315.46 秒；这是该轮增量构建耗时，不是从零全量编译耗时。
- 原版本：PortalWRT `24.10` / `GLaDOS-R3Mini`。
- 原输出目录：`bin/targets/mediatek/filogic/`。
- 原升级镜像：`portalwrt-24.10-glados-r3mini-mediatek-filogic-bananapi_bpi-r3-mini-squashfs-sysupgrade.itb`，255067218 字节。
- 原升级镜像 SHA-256：`d0d7625b97bb6ce184f697a8621dc1e8e58716dcdd8fbf913b1cfdafb0f65b5a`。
- 根 `.config` SHA-256：`8b73c8ef5f64f0650d5c63707a72ab8b22bfef389fabb4d22332517d36ae074d`。
- 完整 preset SHA-256：`42b1a6b89c43a9cb12707b5a2a9f95cbfdd4bdb285afea8ddea95f020a796fd6`。

本次同时归档已有的 `docs/reports/bpi-r3-mini-hardware/` 硬件报告及生成源。报告是修复前快照；其中源码行号与证据散列不会随后续驱动修改自动更新。

根目录的 MT7988 参考 PDF 不是本板 MT7986 / EN8811H 的规格资料，保留为本地参考文件。指向仓库外的 `custom_package.sh` 与未选中的第三方源码目录也保留原状，不作为可重放构建源码提交；选中外部源由 `patches/r3mini-sources/sources.json` 和配套补丁管理。

后续构建必须使用独立输出目录、不同版本标识，并在构建前后校验原 `bin/` 内全部文件，不能只依赖改名避免覆盖。
