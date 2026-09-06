// Authored vector diagrams. No raster generation or external dependencies.
import {writeFileSync} from 'node:fs';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root = dirname(fileURLToPath(import.meta.url));
const esc = s => String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
const colors = {blue:'#21789f',green:'#237e70',orange:'#aa6729',gray:'#748696',purple:'#7760a5'};
const labelWidth=(s,size)=>[...s].reduce((n,c)=>n+(c.charCodeAt(0)>127?1:0.64)*size,0)+16;
function diagram(id,title,subtitle,height,draw){
  let shapes = [], links = [];
  const t=(x,y,s,size=20,color='#183c51',weight=400,anchor='start')=>`<text x="${x}" y="${y}" font-size="${size}" fill="${color}" font-weight="${weight}" text-anchor="${anchor}">${esc(s)}</text>`;
  const api={
    text(x,y,s,size=20,color='#183c51',weight=400,anchor='start'){shapes.push(t(x,y,s,size,color,weight,anchor));},
    frame(x,y,w,h,label,color='blue'){shapes.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="16" fill="${colors[color]}05" stroke="${colors[color]}" stroke-width="2" stroke-dasharray="9 5"/><rect x="${x+12}" y="${y+7}" width="${Math.min(w-24,labelWidth(label,23))}" height="29" rx="4" fill="white"/>`,t(x+18,y+29,label,23,colors[color],700));},
    box(x,y,w,h,title,lines=[],color='blue'){
      shapes.push(`<g data-box="${esc(title)}"><rect x="${x}" y="${y}" width="${w}" height="${h}" rx="12" fill="${colors[color]}0b" stroke="${colors[color]}" stroke-width="1.8"/>`,t(x+15,y+31,title,22,colors[color],700));
      lines.forEach((s,i)=>shapes.push(t(x+15,y+61+i*27,s,19)));
      shapes.push('</g>');
    },
    wire(d,color='blue'){links.push(`<path d="${d}" fill="none" stroke="${colors[color]}" stroke-width="2.6"/>`);},
    link(d,color='blue',both=true,dash=false){links.push(`<path d="${d}" fill="none" stroke="${colors[color]}" stroke-width="2.6" ${dash?'stroke-dasharray="7 5"':''} ${both?`marker-start="url(#${id}-${color})"`:''} marker-end="url(#${id}-${color})"/>`);},
    label(x,y,s,color='blue',size=18){const w=labelWidth(s,size);shapes.push(`<rect x="${x-w/2}" y="${y-size}" width="${w}" height="${size+6}" rx="4" fill="white"/>`,t(x,y,s,size,colors[color],400,'middle'));}
  };
  draw(api);
  const markers=Object.entries(colors).map(([k,c])=>`<marker id="${id}-${k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0 0L10 5L0 10Z" fill="${c}"/></marker>`).join('');
  const svg=`<svg xmlns="http://www.w3.org/2000/svg" id="${id}" width="1180" height="${height}" viewBox="0 0 1180 ${height}" role="img" aria-labelledby="${id}-title ${id}-desc"><title id="${id}-title">${esc(title)}</title><desc id="${id}-desc">${esc(subtitle)}</desc><defs>${markers}</defs><style>#${id} text{font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif}#${id} path{stroke-linejoin:round}</style><rect width="1180" height="${height}" fill="white"/>${t(18,34,title,28,'#183c51',700)}${t(18,67,subtitle,18,'#547084')}${links.join('')}${shapes.join('')}</svg>`;
  writeFileSync(resolve(root,'assets',id+'.svg'),svg);
  console.log(id+'.svg');
}

diagram('soc-modules','模块级架构 · SoC 内外边界与通信关系','功能拓扑，不代表芯片 floorplan；蓝色＝数据，灰虚线＝控制，紫色＝共享内存访问。',995,g=>{
  g.frame(15,90,1150,700,'MT7986A / Filogic 830 · 四个主要片内功能域');
  g.box(40,145,340,166,'MCUSYS · CPU 集群',['4× Cortex-A53 / 最高 2GHz','每核 L1I 32KiB + L1D 32KiB','SCU + 共享 L2 512KiB','GICv3 / Timer / Debug'],'blue');
  g.box(425,145,340,166,'NETSYS v2 · 网络加速域',['PSE 包交换 + PPE0 / PPE1','PDMA / QDMA / WDMA0/1','GMAC0/1 → 两路 2.5G PHY','WED v2 ×2 + WO0 / WO1'],'green');
  g.box(810,145,330,166,'CONNSYS · 无线数字域',['WM / WA 固件与控制逻辑','WFDMA + UMAC PSE / PLE','Wi-Fi MAC / 基带 / 安全处理','RF 接口 → 外部 MT7976C'],'green');
  g.link('M765 267H810','green');g.label(787,333,'WED ↔ WFDMA','green',17);
  g.box(40,405,1100,96,'片内系统互连 / EMI / DRAMC',['CPU 与 DMA master 共享 DDR；高速事务走片内总线，低速寄存器经总线桥 / APB 等访问。'],'purple');
  [210,595,975].forEach(x=>g.link(`M${x} 311V405`,'purple'));
  g.label(210,365,'集群 master 接口','purple');g.label(595,365,'报文 / 描述符 / FOE','purple');g.label(975,365,'报文 / 固件 / 描述符','purple');
  g.box(40,568,340,176,'通用 I/O 与存储域',['PCIe 2.0 RC ×2 lanes','USB3 / USB2 Host + DMA','MSDC / SPI-NAND / I²C','UART / PWM / GPIO / Audio']);
  g.box(425,568,340,176,'系统服务与独立加速',['EIP97 加密引擎 + DMA','CQ_DMA / AP_DMA','Boot ROM / SYSRAM','Clock / Reset / WDT / Thermal']);
  g.box(810,568,330,176,'控制与中断关系',['CPU → MMIO 配置所有子域','IRQ → GIC → A53','AP ↔ WO：CCIF 消息','AP ↔ Wi-Fi：命令 / 事件环'],'gray');
  [210,595,975].forEach(x=>g.link(`M${x} 501V568`,x===975?'gray':'purple',true,x===975));
  g.box(40,842,340,116,'板外 / 板载扩展终点',['NVMe / 蜂窝 USB / eMMC','NAND / EEPROM / 调试口']);
  g.box(425,842,340,116,'板载 2GB DDR4',['SoC 控制器 16-bit','DDR4-3200 平台上限'],'purple');
  g.box(810,842,330,116,'板载网络模拟 / 物理层',['EN8811H ×2 → RJ45 ×2','MT7976C → 2G/5G 天线'],'green');
  g.link('M210 744V842');g.link('M790 501V816H595V842','purple');
  g.wire('M595 145V132H1155V236','green');
  g.link('M1140 236H1155V817H975V842','green');
  g.text(18,987,'NETSYS、CONNSYS、I/O 均在 SoC 内，但不在 Cortex-A53 核心内；内部链路不能直接套用外部端口的 Gb/s。',18);
});

diagram('cpu-cluster','CPU 架构 · 单核执行逻辑、四核缓存与系统接口','A53 IP 固有结构与 MT7986 实际配置分开标注；箭头为功能访问关系，不是逐周期流水线。',1050,g=>{
  g.frame(15,95,1150,304,'单个 Cortex-A53 核心 · ARMv8-A / AArch64 + AArch32');
  g.box(40,152,252,113,'取指 / 分支预测',['L1 I-cache + 指令 µTLB','顺序执行 / 双发射']);
  g.box(335,152,220,113,'译码 / 发射',['双指令译码','8 级基本流水线']);
  g.box(600,152,240,113,'执行资源',['整数 / 分支 / Load-Store','NEON / FP / Crypto']);
  g.box(884,152,255,113,'数据 / 地址翻译',['L1 D-cache / Store buffer','MMU / 主 TLB / 预取']);
  g.link('M292 210H335','blue',false);g.link('M555 210H600','blue',false);g.link('M840 210H884','blue',false);
  g.box(40,302,515,71,'每核 L1I：32KiB / 2-way / 64B line',[],'purple');
  g.box(600,302,539,71,'每核 L1D：32KiB / 4-way / 64B line',[],'purple');
  g.link('M165 265V302','purple');g.link('M1010 265V302','purple');
  g.frame(15,433,1150,360,'MT7986A MCUSYS · 单个四核集群');
  [40,325,610,895].forEach((x,i)=>g.box(x,487,245,115,`CPU${i} · Cortex-A53`,['L1I 32KiB + L1D 32KiB','MMU / TLB / PMU']));
  [162,447,732,1017].forEach(x=>g.wire(`M${x} 602V625`,'purple'));
  g.wire('M162 625H1017','purple');g.link('M380 625V650','purple');
  g.box(40,650,680,110,'SCU + 共享统一 L2：512KiB',['16-way / 64B line；SCU 保持核心间数据缓存一致性','L2 未命中、非缓存事务 → 集群外部 master 接口'],'purple');
  g.box(765,650,375,110,'GICv3 / Timer / Debug',['外设中断送往 A53；PMU 性能计数','PSCI / SMC 管理 CPU 启停'],'gray');
  g.link('M380 760V845','purple');g.text(410,822,'A53 IP：128-bit 系统 master 接口',18,'#7760a5');
  g.box(40,845,680,110,'SoC 互连 → EMI / DRAMC → 板载 DDR4',['16-bit DDR4；最高 3200MT/s 为控制器平台能力','实际内存训练频率、互连频率、仲裁效率须实机确认'],'purple');
  g.box(765,845,375,110,'NETSYS / CONNSYS / I/O DMA',['并行访问共享 DDR；不是 A53 执行单元','缓存同步和内存屏障由驱动处理'],'green');
  g.link('M765 900H720','purple');g.link('M953 845V760','gray',false,true);
  g.text(18,994,'A53 IP 可选 ACE / CHI 与 ACP；MT7986 文档出现 AXI / ACP 标记，但未公开核定全部端口的实例化和连接。',18);
  g.text(18,1024,'不能据此断言所有 DMA 经 ACP 直达 L2，也不能把 CPU 2GHz 当作片内总线时钟。',18);
});

diagram('netsys-acceleration','NETSYS v2 · PSE 交换、PPE 流处理与 DMA','PSE 是内部包交换节点；PPE 是流查找 / 改写引擎；两者都不属于 A53 的指令执行或 CPU cache。',1050,g=>{
  g.frame(15,95,1150,695,'MT7986A · NETSYS / Frame Engine + 无线卸载接口','green');
  g.box(40,154,315,126,'GMAC0/1 + GDMA',['两路 MAC 数据端口','↔ EN8811H ×2 ↔ RJ45 ×2','每口 100 / 1000 / 2500Mb/s'],'green');
  g.box(424,154,330,126,'PPE0 / PPE1 · 两个实例',['解析 / 哈希 / FOE 查找 / 改写','流缓存：驱动定义 128 项','另有 MIB counter cache'],'green');
  g.box(823,154,317,126,'PDMA / QDMA',['PDMA：包描述符 DMA','QDMA：队列 / 调度 / DMA','连接 CPU 的 DDR 数据路径'],'blue');
  [197,589,981].forEach(x=>g.link(`M${x} 280V374`,'green'));
  g.label(197,332,'PSE port 1 / 2','green');g.label(589,332,'PSE port 3 / 4','green');g.label(981,332,'PSE port 0 / 5','green');
  g.box(40,374,1100,120,'NETSYS PSE · Packet Switch Engine',['内部包转接 / 端口队列 / 缓冲与流控；连接 GMAC、PPE、PDMA/QDMA 和 WDMA。','片内包缓冲字节容量未公开核定；PSE 的 MMIO 地址窗口大小不等于缓冲 SRAM 容量。'],'green');
  g.link('M245 494V568','green');g.label(245,537,'PSE port 8 / 9','green');
  g.box(40,568,410,177,'WDMA0 / WDMA1 → WED v2 ×2',['WDMA：NETSYS 侧无线 DMA 接口','WED：环 / token / 缓冲衔接','↔ Wi-Fi WFDMA（CONNSYS）','TX / RX 卸载依驱动与固件启用'],'green');
  g.box(510,568,285,177,'WO0 / WO1',['无线卸载控制固件','接收卸载 / RRO 协作','AP ↔ WO：CCIF','不是 Wi-Fi WM / WA'],'orange');
  g.box(855,568,285,177,'AP / CPU 接口',['PDMA/QDMA 上送异常','MMIO 配置 / IRQ 通知','CCIF ↔ AP 固件控制','A53 核心不在 NETSYS 内'],'gray');
  g.link('M450 649H510','orange');g.link('M795 699H855','gray',true,true);
  g.link('M1013 494V568','gray',true,true);
  g.box(40,850,755,140,'板载 DDR4 · 共享内存，不是片内 cache',['FOE：默认 16K×96B/PPE ≈ 1.5MiB/PPE（条目区）','另有 MIB / 描述符 / packet pool / 固件 / RRO 队列','卸载降低 CPU 逐包负担，不代表不访问 DDR。'],'purple');
  g.box(855,850,285,140,'A53 / Linux',['NAPI / 网络栈 / 首包策略','绑定 FOE / 固件管理','本体位于 MCUSYS'],'blue');
  g.link('M997 745V850','gray',true,true);g.link('M855 922H795','purple');
  g.link('M1140 234H1155V805H760V850','purple');g.link('M589 154V132H1173V823H615V850','purple');g.link('M245 745V850','purple');g.link('M651 745V850','purple');
  g.text(18,1030,'端口编号来自本工程 NETSYS v2 HNAT 定义；不是 Linux 接口编号。图中只表达功能关系，不声称物理串接顺序。',18);
});

diagram('wireless-subsystem','无线架构 · WFDMA、MAC / 基带、RF 与 WED / WO','蓝色 / 绿色＝数据与功能通路，灰虚线＝固件控制；Wi-Fi PSE 与 NETSYS PSE 是两个不同模块。',1080,g=>{
  g.box(25,102,340,139,'A53 / Linux 无线驱动',['当前工程：mt_wifi + warp','上游路线：mt76 / mt7915 + WED','命令 / 事件 / 状态 / 普通报文']);
  g.box(418,102,342,139,'NETSYS：PSE ↔ WDMA',['PPE 决定流改写 / 出口','WED v2：缓冲 / 描述符衔接','WO0/1：卸载固件与 RRO'],'green');
  g.box(813,102,342,139,'共享 DDR4',['Host packet / descriptor rings','WM / WO 固件保留区','缓存同步：驱动 DMA API'],'purple');
  g.frame(15,302,1150,492,'MT7986A · CONNSYS / 集成 Wi-Fi 数字子系统','green');
  g.box(40,360,340,138,'Wi-Fi WM / WA 固件域',['WM 管理 / WA 协作固件','资料：Andes 处理器带 I/D cache','具体型号 / cache 容量未公开'],'orange');
  g.box(425,360,340,138,'WFDMA / Host DMA',['主机 TX / RX 描述符环','DMA ring + token / completion','连接 AP、DDR、WED'],'blue');
  g.box(810,360,330,138,'UMAC：Wi-Fi PSE / PLE',['PSE：包页 / 缓冲 / 端口','PLE：队列 / 链表调度','DMASHDL / WTBL 状态'],'green');
  g.link('M195 241V360','gray',true,true);g.link('M589 241V360','green');g.link('M984 241V274H721V360','purple');
  g.link('M380 433H425','gray',true,true);g.link('M765 433H810','green');
  g.box(40,577,725,157,'双频 MAC / LMAC + Baseband / PHY 数字处理',['802.11ax MAC：聚合 / Block ACK / 队列 / 重传 / 硬件安全处理','基带：OFDM/OFDMA、MIMO、调制编码、波束成形相关处理','2.4GHz 与 5GHz 逻辑无线链；调度、速率控制依固件配置','这里的 PHY 是无线数字基带，不是 EN8811H 以太网 PHY。'],'green');
  g.box(810,577,330,157,'RF 接口与时序 / 校准',['AFE I/Q 模拟信号','WF / HB / TOP 控制信号','射频校准 / 芯片协作','不是 PCIe 或 USB Wi-Fi 卡'],'green');
  g.link('M975 498V539H647V577','green');g.link('M210 498V577','gray',true,true);g.link('M765 655H810','green');
  g.box(40,855,600,144,'外部 MT7976C · 射频 / 模拟收发',['基带 I/Q ↔ 射频收发 / 频率转换等模拟处理','板级：2.4GHz 2×2 + 5GHz 3×3','完整 RF 原理图未公开：不细画未经确认的 PA/LNA/FEM 分配'],'green');
  g.box(710,855,430,144,'天线 / 无线空口',['2GA / 2GB；5GA / 5GB / 5GC','802.11 a/b/g/n/ac/ax 按频段使用','空口 PHY 速率取决于 NSS / BW / MCS / GI'],'green');
  g.link('M975 734V818H340V855','green');g.link('M640 927H710','green');
  g.text(18,1040,'WFDMA ≠ WDMA；WM/WA ≠ WO；Wi-Fi PSE/PLE 的 page buffer ≠ A53 L1/L2 ≠ PPE FOE cache。',19);
});

diagram('software-datapaths','技术栈与转发路径 · 控制面始终由软件参与','两套驱动路线用于解释同一硬件；当前构建选择厂商栈，不表示上游驱动同时接管该无线设备。',1020,g=>{
  g.box(25,100,1130,99,'应用 / 配置层',['LuCI / UCI / netifd / 路由与防火墙配置；用户业务：上网、存储、蜂窝网络、VPN 等。']);
  g.box(25,248,540,182,'当前工程：厂商技术栈',['Linux 6.6 / mtk_eth_soc','mt_wifi + mtwifi-cfg / Wi-Fi 固件','mtk_hnat → PPE / FOE','warp → WED / WDMA / WO 固件'],'green');
  g.box(615,248,540,182,'上游 OpenWrt 常见路线（对照）',['Linux / mac80211 / cfg80211','mt76 / mt7915 → Wi-Fi MAC / MCU','nft flowtable → mtk_ppe → PPE','mtk_wed / mtk_wed_wo → WED / WO'],'blue');
  g.link('M295 199V248','gray',false,true);g.link('M885 199V248','gray',false,true);
  g.box(25,490,1130,105,'共享硬件：NETSYS v2 + CONNSYS + DDR4',['CPU 通过 MMIO、DMA 描述符和固件消息配置；IRQ / completion / event 返回软件。','PPE 只处理能表达并已绑定的流，未命中、异常和不支持业务仍交给 CPU。'],'green');
  g.link('M295 430V490','gray',true,true);g.link('M885 430V490','gray',true,true);
  g.frame(15,647,1150,314,'业务数据路径（简化双向功能表达）');
  g.box(40,704,270,208,'入口 / 出口外设',['有线：PHY ↔ GMAC','无线：RF ↔ MAC','快路径仅用于合格网络流','USB 接入需软件协作','存储另走块 I/O 路径']);
  g.box(380,704,360,92,'普通软件 / 慢路径',['DMA ↔ DDR ↔ A53 网络栈']);
  g.box(380,841,360,92,'硬件流卸载 / 快路径',['PSE ↔ PPE；无线再经 WED'],'green');
  g.box(810,704,330,229,'出口、限速和回退',['命中流：硬件改写 / 转发','首包 / miss / exception：CPU','Wi-Fi：WFDMA / MAC / RF','Ethernet：GMAC / PHY','卸载不等于绕过全部内存','硬件路径可能绕过 SQM'],'orange');
  g.link('M310 750H380');g.link('M310 887H380','green');g.link('M740 750H810');g.link('M740 887H810','green');
  g.text(18,997,'EIP97 独立加密加速器和 A53 Crypto 指令是另外两条加速路线；它们不会因启用 NAT/WED 而自动接管 VPN。',18);
});
