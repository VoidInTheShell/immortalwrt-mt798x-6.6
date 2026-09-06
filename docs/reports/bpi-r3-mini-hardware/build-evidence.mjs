// Record hashes and source symbols, without copying user configuration contents.
import {readFileSync,writeFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {dirname,resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=dirname(fileURLToPath(import.meta.url)), repo=resolve(root,'../../..');
const target='target/linux/mediatek/files-6.6/';
const kernel='build_dir/target-aarch64_cortex-a53_musl/linux-mediatek_filogic/linux-6.6.133/';
const eth='drivers/net/ethernet/mediatek/';
const wifi='package/mtk/drivers/mt_wifi/src/mt_wifi/';
const warp='package/mtk/drivers/warp/src/';
const definitions=[
 ['L1',target+'arch/arm64/boot/dts/mediatek/mt7986a.dtsi',['arm,gic-v3','wmcpu_emi:','wocpu0_emi:','wocpu1_emi:','wocpu_data:','mtketh-ppe-num','wocpu0_ilm:','wocpu_dlm:']],
 ['L2',target+eth+'mtk_hnat/hnat.h',['MAX_PPE_CACHE_NUM','DEF_ETRY_NUM\t','MAX_PPE_NUM','struct foe_entry','PPE_CAH_CTRL','PPE_MIB_CAH_CTRL','NR_WDMA0_PORT']],
 ['L2',target+eth+'mtk_hnat/hnat.c',['static int hnat_start','foe_table_sz =','dma_alloc_coherent','hnat_cache_ebl']],
 ['L3',wifi+'chips/mt7986.c',['WA_CPU','WM_CPU','hif_init_WFDMA']],
 ['L3',wifi+'chips/mt7986_dbg.c',['pg_sz =','Page Size','WF_PSE_TOP_PBUF_CTRL_ADDR','WF_PLE_TOP_PBUF_CTRL_ADDR']],
 ['L4',warp+'regs/reg_v2/warp_mt7986.c',['miod_entry_size','MIOD_CNT','FB_CMD_CNT','RRO_QUE_CNT']],
 ['L4',warp+'warp_hw.h',['MIOD_CNT','FB_CMD_CNT','RRO_QUE_CNT']],
 ['L4',warp+'mcu/warp_wo.c',['CCIF','woif']],
 ['L5',kernel+eth+'mtk_ppe.h',['MTK_FOE_ENTRY_V2_SIZE','MTK_PPE_ENTRIES_SHIFT']],
 ['L5',kernel+eth+'mtk_eth_soc.h',['MTK_QDMA_NUM_QUEUES']],
 ['L5',kernel+eth+'mtk_eth_soc.c',['mt7986_data','ppe_num = 2']],
 ['L6','.config',['CONFIG_TARGET_mediatek_filogic_DEVICE_bananapi_bpi-r3-mini','CONFIG_PACKAGE_kmod-mt_wifi','CONFIG_PACKAGE_kmod-warp','CONFIG_PACKAGE_kmod-mediatek_hnat','CONFIG_PACKAGE_kmod-mac80211','CONFIG_PACKAGE_kmod-crypto-hw-safexcel']],
 ['L6',kernel+'.config',['CONFIG_NET_MEDIATEK_SOC_WED','CONFIG_MEDIATEK_NETSYS_V2','CONFIG_MEDIATEK_NETSYS_V3','CONFIG_MEDIATEK_NETSYS_RX_V2','CONFIG_NET_MEDIATEK_HNAT','CONFIG_CRYPTO_DEV_SAFEXCEL']],
 ['L7',wifi+'embedded/plug_in/warp_proxy/chips/warp_wifi_mt7986.c',['WFDMA']],
 ['L8',kernel+'drivers/clk/mediatek/clk-mt7986-topckgen.c',['netsys_parents','netsys_500m_parents','netsys_mcu_parents','netsys_2x_parents','conn_mcusys_parents','sysaxi_parents','sysapb_parents']]
];
const files=definitions.map(([index,path,symbols])=>{
 const bytes=readFileSync(resolve(repo,path)), lines=bytes.toString('utf8').split('\n');
 return {index,path,sha256:createHash('sha256').update(bytes).digest('hex'),references:symbols.map(symbol=>({symbol,line_numbers:lines.flatMap((line,i)=>line.includes(symbol)?[i+1]:[])}))};
});
const manifest={report_version:'2.0',checked_date:'2026-09-07',git_head:execFileSync('git',['rev-parse','HEAD'],{cwd:repo,encoding:'utf8'}).trim(),scope_note:'Read-only source audit; dirty worktree; build selection is not runtime confirmation. Configuration content is intentionally not copied.',files};
writeFileSync(resolve(root,'evidence-manifest.json'),JSON.stringify(manifest,null,2)+'\n');
console.log(`Evidence manifest: ${files.length} files hashed.`);
