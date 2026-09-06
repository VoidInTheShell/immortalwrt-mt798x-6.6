// Compile Markdown and local illustrations into a standalone offline HTML report.
// Usage: pandoc --from=gfm --to=html5 report.md --output=/tmp/bpi-r3-body.html
//        node build-report.mjs /tmp/bpi-r3-body.html
import {readFileSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, resolve, extname} from 'node:path';

const root = dirname(fileURLToPath(import.meta.url));
if (!process.argv[2]) throw new Error('Pass the HTML body compiled by pandoc as the first argument.');
let body = readFileSync(resolve(process.argv[2]), 'utf8');
body = body.replace(/<img src="([^"]+)"([^>]*)\/?\s*>/g, (_, src, attributes) => {
  const file = resolve(root, src);
  if (extname(file) === '.svg') return '<figure class="diagram">' + readFileSync(file, 'utf8') + '</figure>';
  const data = readFileSync(file).toString('base64');
  return `<img src="data:image/jpeg;base64,${data}"${attributes}>`;
});
function pageClass(content, i) {
  if (i === 0) return 'p-cover';
  const names = [['主器件与高速外设','p-board'],['网络路径与速率含义','p-network'],['供电、调试与控制连接图','p-power'],['电源轨和低速外设参数','p-rails'],['扩展接口、完整性与待确认项','p-expansion'],['官方实物接口定位','p-photo'],['板级证据索引','p-sources'],['SoC / CPU 文档与源码证据','p-evidence']];
  for (const [name, cls] of names) if (content.includes(name)) return cls;
  return content.includes('<svg') ? 'p-diagram' : 'p-detail';
}
const sheets = body.split(/<!--\s*page\s*-->/).map((content, i, arr) =>
  `<section class="sheet ${pageClass(content,i)}" data-page="${i+1}"><div class="running">BPI-R3 MINI <span>硬件 / 加速 / 无线架构 · 2026-09-07 · v2.0</span></div>${content}<footer>${String(i+1).padStart(2,'0')} / ${String(arr.length).padStart(2,'0')}<span>功能架构 · 能力 / 配置 / 实测分列</span></footer></section>`
).join('\n');

const css = `
:root{color-scheme:light;--ink:#142e43;--muted:#547084;--accent:#146586}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#e8eef3;color:var(--ink);font-family:"Microsoft YaHei","Noto Sans CJK SC","PingFang SC",sans-serif;font-size:10.3pt;line-height:1.56}
.toolbar{position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;padding:12px 24px;background:#123d56;color:#fff;box-shadow:0 3px 15px #123d5620}.toolbar span{font-size:12px;color:#b9d9e8}.toolbar button{font:inherit;border:1px solid #7eaabd;border-radius:6px;padding:6px 14px;background:transparent;color:white;cursor:pointer}
.sheet{position:relative;width:210mm;min-height:297mm;margin:20px auto;padding:12mm 13mm 14mm;background:#fff;box-shadow:0 5px 30px #133b5310}
.running{font-size:8pt;letter-spacing:.12em;color:#3f738d;border-bottom:1px solid #bfd2de;padding-bottom:6px;margin-bottom:18px;font-weight:700}.running span{float:right;letter-spacing:0;font-weight:400;color:#637e8f}
h1{font-size:25pt;line-height:1.3;margin:0 0 7px;letter-spacing:-.03em}h2{font-size:18pt;margin:0 0 16px;line-height:1.4}h3{font-size:11.7pt;margin:17px 0 6px;color:#155570}p{margin:9px 0}strong{font-weight:700}.subtitle{font-size:12pt;color:#3d7893;margin:0 0 9px}.meta{font-size:8pt;color:var(--muted);border-left:3px solid #297b98;padding-left:9px;margin:10px 0 14px}
a{color:#146586;text-decoration:none;overflow-wrap:anywhere}a:hover{text-decoration:underline}code{font-family:"DejaVu Sans Mono",monospace;font-size:.87em;background:#f1f5f8;padding:1px 3px;border-radius:3px;overflow-wrap:anywhere}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:9.1pt;line-height:1.5}th{text-align:left;background:#eaf2f7;color:#1b546e;font-weight:700;border-top:1px solid #a9c1d1}th,td{padding:7px 8px;vertical-align:top;border-bottom:1px solid #dce5eb}tr:nth-child(even) td{background:#f8fafc}thead{display:table-header-group}tr{break-inside:avoid}
figure{margin:12px 0}figure svg{display:block;width:100%;height:auto}img{display:block;max-width:100%;height:auto;margin:10px auto}.caption{font-size:8.3pt;color:var(--muted);line-height:1.55}
footer{display:flex;justify-content:space-between;color:#7490a2;font-size:8pt;border-top:1px solid #d9e5ec;margin-top:18px;padding-top:7px}
.p-cover .diagram{margin:14px 0 4px}.p-cover p{font-size:9.2pt}.p-cover .subtitle{font-size:11.5pt}.p-cover .meta{font-size:8pt}
.p-board td:first-child{width:23%}.p-board td:nth-child(2){width:29%}.p-board table{font-size:9.3pt}.p-network table{font-size:8.9pt}.p-power .diagram{margin-top:10px}.p-rails table{font-size:8.6pt;line-height:1.42}.p-rails th,.p-rails td{padding:5.5px 7px}.p-rails p{font-size:9.2pt}.p-expansion table{font-size:8.9pt}.p-expansion p{font-size:9.5pt}.p-photo img{max-height:220mm;width:auto}.p-sources table{font-size:8.8pt}
.p-detail{font-size:9.5pt;line-height:1.5}.p-detail table{font-size:8.6pt;line-height:1.43}.p-detail th,.p-detail td{padding:5.5px 6.5px}.p-detail td:first-child{width:20%}.p-detail h3{margin-top:13px}.p-diagram p{font-size:9.2pt}.p-diagram .diagram{margin:10px 0}.p-evidence{font-size:8.8pt;line-height:1.4}.p-evidence table{font-size:8pt;line-height:1.4;margin:9px 0}.p-evidence th,.p-evidence td{padding:4px 5px}.p-evidence h3{margin-top:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f1f5f8;border:1px solid #dce5eb;padding:9px;font-size:8.2pt;line-height:1.5}pre code{padding:0;background:none;font-size:inherit}
@media(max-width:850px){.sheet{width:100%;min-height:0;margin:0 0 16px;padding:20px 18px 24px;overflow-x:auto}.running span{float:none;display:block;margin-top:4px}.toolbar{padding:9px 12px}.toolbar span{display:none}h1{font-size:23px}h2{font-size:21px}table{min-width:600px}.diagram{min-width:660px}.p-photo img{max-height:none;width:100%}}
@page{size:A4;margin:0}
@media print{body{background:#fff;font-size:10.3pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}.toolbar{display:none}.sheet{width:210mm;min-height:0;margin:0;padding:12mm 13mm 11mm;box-shadow:none;break-after:page;overflow:visible}.sheet:last-child{break-after:auto}.running span{float:right;display:inline;margin:0}h1{font-size:25pt}h2{font-size:18pt}h2,h3{break-after:avoid}.diagram{break-inside:avoid;min-width:0}a{color:#146586}footer{break-inside:avoid}.p-network{font-size:9.8pt;line-height:1.47}.p-network th,.p-network td{padding:6px 7px}.p-expansion{line-height:1.47}.p-expansion table{line-height:1.4;margin:9px 0}.p-expansion th,.p-expansion td{padding:5px 7px}.p-expansion h3{margin-top:12px}.p-photo img{max-height:205mm;width:auto}}
`;
const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="description" content="BPI-R3 Mini 板级连接、SoC 模块、CPU 缓存与总线、NETSYS PPE/PSE 加速、无线 WED/WFDMA 架构与技术栈报告"><title>BPI-R3 Mini 硬件架构与连接报告 v2.0</title><style>${css}</style></head><body><nav class="toolbar"><strong>BPI-R3 Mini · 硬件报告 v2.0</strong><span>7 张矢量架构图 + 官方照片 · 可离线浏览</span><button type="button" onclick="window.print()">打印 / 保存 PDF</button></nav><main>${sheets}</main></body></html>`;
writeFileSync(resolve(root, 'report.html'), html);
console.log(`Built report.html: ${Buffer.byteLength(html)} bytes; ${body.split(/<!--\s*page\s*-->/).length} sections; images embedded.`);
