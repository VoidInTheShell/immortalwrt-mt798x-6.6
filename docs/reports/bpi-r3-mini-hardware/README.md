# BPI-R3 Mini 硬件报告

- `report.pdf`：21 页 A4 排版版本，方便保存、阅读和打印。
- `report.html`：单文件离线报告，SVG 和实物照片均已内嵌，不依赖网络脚本；浏览器内可打印。
- `report.md`：报告正文源文件。
- `assets/architecture.svg`：功能级硬件架构 / 连接总图。
- `assets/power-debug.svg`：供电、调试与控制连接图。
- `assets/soc-modules.svg`：SoC 模块、片内互连与外部器件边界。
- `assets/cpu-cluster.svg`：单核执行结构、四核集群、L1/L2、SCU、MMU、中断与内存。
- `assets/netsys-acceleration.svg`：PSE / PPE / PDMA / QDMA / WDMA / WED / WO 与 DDR。
- `assets/wireless-subsystem.svg`：WM / WA、WFDMA、无线 PSE / PLE、MAC / 基带与 MT7976C。
- `assets/software-datapaths.svg`：当前厂商栈、上游对照与普通/硬件卸载路径。
- `assets/official-interface.jpg`：Banana Pi 官方实物接口图，原始链接及出处见正文。
- `build-report.mjs`：将 Markdown 转换结果与图片编译成单文件 HTML 的脚本。
- `build-diagrams.mjs`：生成新增五张矢量架构图的源码。
- `evidence-manifest.json`：本地源码证据索引、关键符号位置和 SHA-256；不包含完整用户配置。
- `build-evidence.mjs`：从当前工作树重新生成证据清单；需要报告使用的源码和已展开的内核目录。
- `visual-review.md`：最终 PDF 的七张架构图逐张视觉检查记录及校验范围。

报告版本 2.0，板级资料核对于 2026-09-06，CPU/加速/无线架构补充至 2026-09-07。共七张原创 SVG 架构图和一张官方照片；不是 PCB 接线施工图。容量、内部接口实例化、实时频率等未经证实的值均标明未知或配置条件，不借用 MT7988 参数。

## 修改并重新生成 HTML

需要 Node.js 和 Pandoc；在本目录执行：

```sh
node build-diagrams.mjs
pandoc --from=gfm --to=html5 report.md --output=/tmp/bpi-r3-body.html
node build-report.mjs /tmp/bpi-r3-body.html
```

然后打开 `report.html`，使用页面上的“打印 / 保存 PDF”。纸张使用 A4，缩放 100%，关闭浏览器额外页眉/页脚并启用背景图形。中文字体变化可能影响分页；已提供的 PDF 已嵌入生成时使用的字体。

文件中的 `<!-- page -->` 是章节分页标记；SVG 图片可用矢量工具或文本编辑器继续修改。页面正文中的参数已区分板卡标称、软件配置、理论换算和待确认项。
