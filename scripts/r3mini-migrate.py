#!/usr/bin/env python3
"""Build a reviewed R3 Mini feature preset; never import x86 target settings.

Reads the frozen audit inventory and original R3 baseline. --apply writes the
candidate .config; run make defconfig and --verify after metadata regeneration.
Every x86 package receives an explicit decision in migration-decisions.tsv.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/r3mini-migration-audit'
BASE = OUT / 'original-r3mini-baseline.config'
spec = importlib.util.spec_from_file_location('inventory', ROOT / 'scripts/r3mini-migration-inventory.py')
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)

EXCLUDED = {
    'autocore': '保留 R3 autocore-arm，不移入 x86 初始化',
    'bridger': '用户同意不移植缺失的主线桥卸载组件',
    'kmod-nft-fullcone': '用户同意不移植；使用目标 Full Cone/HNAT 配套',
    'luci-app-athena-led': '用户明确：不是 R3 Mini 的 LED 组件',
    'UAmask': '用户暂缓 UA-Mask', 'ua3f': '用户暂缓 UA3F',
    'dns-over-https': 'doh-client 默认先于 dnsmasq 占用 53；用户要求取消',
    'daed-next': '由现代 daed 1.27.0 替代，不引入设备 Node',
    'luci-app-daed-next': '由现代 luci-app-daed 替代',
    'quectel-cm': '用户统一使用 ModemManager，不安装重叠拨号管理器',
    'luci-proto-quectel': '依赖旧 quectel-cm 驱动集合；拨号功能由现有 MM 提供',
    'kmod-usb-net-qmi-wwan-fibocom': '避免覆盖/抢占现有通用 QMI 驱动',
    'kmod-usb-net-qmi-wwan-quectel': '避免覆盖/抢占现有通用 QMI 驱动',
    'kmod-ipt-offload': '本机卸载控制使用私有 MTK HNAT，不增加 legacy FLOWOFFLOAD 路径',
    'luci-app-eqos-mtk': '软件 EQOS 启停会全局清空 mangle PREROUTING；改用真实硬件队列工具，避免干扰代理/QoS',
}
# The user's modem policy is one complete ModemManager stack. mmcli, qmicli,
# mbimcli and its rpcd bridge remain available from the existing MM baseline.
for _name in '''luci-app-modem luci-i18n-modem-zh-cn luci-app-qmodem
luci-app-qmodem-mwan luci-proto-qmodem qmodem quectel-CM-5G quectel-CM-5G-M
luci-proto-3g luci-proto-mbim luci-proto-qmi luci-proto-ncm
comgt comgt-directip comgt-ncm uqmi umbim modemband quectel-timesync
adb-enablemodem sendat sms-tool fibocom-dial qmodem-next luci-app-qmodem-next
luci-app-modemband luci-app-modeminfo luci-app-sms-tool-js
kmod-pcie_mhi kmod-pcie_mhi_fb kmod-pcie_mhi_nss
kmod-qmi_wwan_f kmod-qmi_wwan_m kmod-qmi_wwan_q kmod-qmi_wwan_s kmod-qmi_wwan_q_nss'''.split():
    EXCLUDED[_name] = '用户统一使用 ModemManager；其 mmcli/QMI/MBIM 工具覆盖此功能'

for _name in '''qos-scripts sqm-scripts sqm-scripts-extra qosify nft-qos
luci-app-qos luci-app-sqm luci-app-qosify luci-app-nft-qos luci-app-eqos luci-app-eqos-mtk
luci-i18n-qos-zh-cn luci-i18n-sqm-zh-cn luci-i18n-qosify-zh-cn
luci-i18n-nft-qos-zh-cn luci-i18n-eqos-zh-cn luci-i18n-eqos-mtk-zh-cn'''.split():
    EXCLUDED[_name] = '用户仅保留 MTK 专用硬件 QoS 和 QoSmate；移除重叠的 QoS 管理引擎'

# Shared kernel facilities and the netifd Wi-Fi entry point are dependencies,
# not imported physical NIC drivers. Let the resolver select these when needed.
DEPENDENCY_ONLY = {'kmod-cfg80211', 'wireless-regdb', 'wifi-scripts',
                   'kmod-dax', 'kmod-random-core', 'kmod-tpm', 'wwan'}
REPLACED = {
    'luci-ssl': 'luci-ssl-openssl', 'libustream-mbedtls': 'libustream-openssl',
    'px5g-mbedtls': 'openssl-util', 'ntfs-3g': 'ntfs3-mount',
    'ethtool': 'ethtool-full', 'tc-tiny': 'tc-full',
    'miniupnpd-iptables': 'miniupnpd-nftables',
}
WIRELESS_TOOLS = {'iw', 'aircrack-ng', 'wifischedule'}
ADDITIONS = '''r3mini-defaults luci-ssl-openssl openssl-util uhttpd uhttpd-mod-ubus
luci-app-uhttpd luci-app-daed daed daed-geoip daed-geosite
luci-app-netspeedtest homebox ookla-speedtest autocore-arm
miniupnpd-nftables tc-full ethtool-full ntfs3-mount'''.split()
FEATURE_PREFIXES = (
    'CONFIG_DROPBEAR_', 'CONFIG_OPENSSH_', 'CONFIG_PHP8_', 'CONFIG_PERL_',
    'CONFIG_SQLITE3_', 'CONFIG_GNUTLS_', 'CONFIG_MBEDTLS_', 'CONFIG_LIBCURL_',
    'CONFIG_PCRE2_', 'CONFIG_RSYNC_', 'CONFIG_NFS_', 'CONFIG_RPCBIND_',
    'CONFIG_SAMBA4_', 'CONFIG_SOCAT_', 'CONFIG_PARTED_', 'CONFIG_AIRCRACK_NG_',
    'CONFIG_HTOP_', 'CONFIG_boost-', 'CONFIG_LUCI_',
)
FEATURE_RENAMES = {'CONFIG_LIBCURL_NGHTTP2': 'CONFIG_LIBCURL_HTTP2'}
# Upstream explicitly ships HS20 as a lab server: its defaults expose example
# PHP pages in the main webroot and startup changes uhttpd.main TLS credentials.
# Keep the original x86 build-only state, while embedding its useful runtime
# libraries/tools independently for the full system environment.
BUILD_ONLY = {'hs20-client', 'hs20-common', 'hs20-server'}


def render(values):
    return '\n'.join(f'# {k} is not set' if v == 'n' else f'{k}={v}'
                     for k, v in sorted(values.items())) + '\n'


def decisions(rows):
    output = []
    for row in rows:
        name, target = row['package'], row['package']
        action, reason = 'migrate', '迁移功能；使用目标源码和依赖，服务默认状态单独适配'
        if name in BUILD_ONLY:
            action, reason = 'build-only', '维持 x86 的仅生成 IPK 状态；HS20 实验套件的示例 Web 页面与主站证书修改不自动部署'
        elif name in EXCLUDED:
            action, reason, target = 'exclude', EXCLUDED[name], ''
        elif name == 'node' or name.startswith('node-') or name == 'ts-node':
            action, reason, target = 'exclude', '用户暂缓设备 Node.js', ''
        elif name in REPLACED:
            action, reason, target = 'replace', '使用已选目标实现，避免互斥构建变体', REPLACED[name]
        elif name in DEPENDENCY_ONLY:
            action, reason, target = 'dependency-only', '仅允许目标软件依赖解析器按需选择的通用基础组件', ''
        elif row['triage'] == 'exclude-hardware':
            action, reason, target = 'exclude', 'x86/其他外设驱动和固件，不属于本机硬件基线', ''
        elif row['triage'] == 'wireless-review' and name not in WIRELESS_TOOLS:
            action, reason, target = 'replace-hardware', '无线管理由 MTK 私有驱动及工具完整配套', ''
        elif row['triage'] == 'optional-peripheral' and name.startswith('kmod-usb-net-'):
            action, reason, target = 'exclude', '不复制 x86 为外接网卡选的额外驱动；本机 MM 驱动已保留', ''
        if target and row['x86_selection'] == 'm' and name not in BUILD_ONLY:
            reason += '；通用运行组件编入固件（x86 原为仅编译）'
        output.append(dict(package=name, x86_selection=row['x86_selection'],
                           action=action, target=target, reason=reason))
    for row in output:
        if row['package'].startswith('luci-i18n-'):
            # Most translations have a direct package dependency; custom ones
            # are resolved by the target Kconfig after this explicit removal.
            if any(word in row['package'] for word in ('athena-led', 'ua3f', 'uamask')):
                row.update(action='exclude', target='', reason='对应应用由用户明确排除')
    return output


def verify():
    """Verify the saved decision manifest without needing the original x86 tree."""
    manifest = json.loads((OUT / 'migration-requested.json').read_text())
    actual = inventory.config(ROOT / '.config')
    metadata, duplicates = inventory.metadata(ROOT / 'tmp/.packageinfo')
    requested = manifest['packages']
    expectations = {**requested, **manifest['features']}
    missing = {k: {'want': v, 'got': actual.get(k, 'n')} for k, v in expectations.items()
               if v != 'n' and actual.get(k, 'n') not in (('y', 'm') if v == 'm' else (v,))}
    forbidden = {k: actual[k] for k, v in expectations.items()
                 if v == 'n' and actual.get(k, 'n') != 'n' and k[15:] not in DEPENDENCY_ONLY}
    selected = {k[15:]: v for k, v in actual.items()
                if k.startswith('CONFIG_PACKAGE_') and k[15:] in metadata and v in ('y', 'm')}
    conflicts = sorted({tuple(sorted((p, q))) for p, v in selected.items() if v == 'y'
                        for q in metadata[p].get('Conflicts', '').split() if selected.get(q) == 'y'})
    duplicate_selected = {p: paths for p, paths in duplicates.items() if p in selected}
    result = {'missing': missing, 'forbidden_selected': forbidden, 'declared_conflicts': conflicts,
              'duplicate_selected_definitions': duplicate_selected,
              'automatic_shared_dependencies': sorted(DEPENDENCY_ONLY & selected.keys()),
              'selected_packages': len(selected),
              'hardware_fragment_present': manifest['hardware_fragment_present'],
              'modem_fragment_present': manifest.get('modem_fragment_present', False),
              'config_sha256': hashlib.sha256((ROOT / '.config').read_bytes()).hexdigest()}
    (OUT / 'migration-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if missing or forbidden or conflicts or duplicate_selected or not manifest['hardware_fragment_present'] or not manifest.get('modem_fragment_present'):
        raise SystemExit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--x86-config', type=Path, help='Refresh feature suboptions from an explicitly supplied x86 config; default: frozen reviewed feature manifest')
    args = ap.parse_args()
    if args.verify and not args.apply:
        return verify()
    if not BASE.exists():
        raise SystemExit('Missing original R3 baseline backup: ' + str(BASE))
    metadata, _ = inventory.metadata(ROOT / 'tmp/.packageinfo')
    rows = list(csv.DictReader((OUT / 'packages.tsv').open(), delimiter='\t'))
    choices = decisions(rows)
    values = inventory.config(BASE)
    requested = {}
    for row in choices:
        if row['target']:
            symbol = 'CONFIG_PACKAGE_' + row['target']
            value = 'm' if row['target'] in BUILD_ONLY else 'y'
            if values.get(symbol) == 'y' or requested.get(symbol) == 'y':
                value = 'y'
            requested[symbol] = value
        if row['target'] != row['package']:
            requested['CONFIG_PACKAGE_' + row['package']] = 'n'
    for name in ADDITIONS:
        requested['CONFIG_PACKAGE_' + name] = 'y'
    feature_requests = json.loads((OUT / 'migration-requested.json').read_text())['features'].copy()
    if args.x86_config:
        x86 = inventory.config(args.x86_config)
        feature_requests = {}
        for symbol, value in x86.items():
            is_feature = symbol.startswith(FEATURE_PREFIXES) or (
                symbol.startswith('CONFIG_PACKAGE_') and symbol[15:] not in metadata
                and symbol.startswith(('CONFIG_PACKAGE_dnsmasq_full_', 'CONFIG_PACKAGE_luci-app-passwall_')))
            if is_feature and not any(x in symbol for x in ('SSE2', 'X86', 'RFKILL')):
                feature_requests[FEATURE_RENAMES.get(symbol, symbol)] = value
    feature_requests.update({
        'CONFIG_LIBQMI_COLLECTION_FULL': 'y', 'CONFIG_LIBQMI_COLLECTION_BASIC': 'n',
        'CONFIG_LIBSODIUM_MINIMAL': 'n', 'CONFIG_OPENSSL_OPTIMIZE_SPEED': 'y',
        'CONFIG_DEVEL': 'y', 'CONFIG_BPF_TOOLCHAIN_HOST': 'y', 'CONFIG_BPF_TOOLCHAIN_NONE': 'n',
        'CONFIG_KERNEL_DEBUG_INFO': 'y', 'CONFIG_KERNEL_DEBUG_INFO_REDUCED': 'n',
        'CONFIG_KERNEL_DEBUG_INFO_BTF': 'y', 'CONFIG_KERNEL_BPF_EVENTS': 'y',
        'CONFIG_KERNEL_CGROUP_BPF': 'y', 'CONFIG_KERNEL_BPF_STREAM_PARSER': 'y',
        'CONFIG_KERNEL_XDP_SOCKETS': 'y', 'CONFIG_NODEJS_HOST_BIN': 'y',
        'CONFIG_NODEJS_24': 'y', 'CONFIG_NODEJS_20': 'n', 'CONFIG_NODEJS_22': 'n',
        'CONFIG_TARGET_ROOTFS_PARTSIZE': '2048', 'CONFIG_TARGET_ROOTFS_INITRAMFS': 'n',
        'CONFIG_R3MINI_FULL_EMMC': 'y', 'CONFIG_CCACHE': 'y',
        'CONFIG_MTK_DEFAULT_5G_PROFILE': 'n',
        'CONFIG_BUILD_LOG': 'y', 'CONFIG_AUTOREMOVE': 'n',
        'CONFIG_VERSION_DIST': '"PortalWRT"', 'CONFIG_VERSION_NUMBER': '"24.10.2"',
        'CONFIG_VERSION_CODE': '"GLaDOS-R3Mini-Autoneg-r4"', 'CONFIG_VERSION_HWREV': '"BPI-R3 Mini"',
        'CONFIG_VERSION_MANUFACTURER': '"APERTURE SCIENCE"',
        'CONFIG_VERSION_MANUFACTURER_URL': '"https://www.valvesoftware.com"',
        'CONFIG_VERSION_PRODUCT': '"APERTURE SCIENCE"',
        'CONFIG_IMAGEOPT': 'y', 'CONFIG_VERSIONOPT': 'y',
        'CONFIG_VERSION_FILENAMES': 'y', 'CONFIG_VERSION_CODE_FILENAMES': 'y',
    })
    for name in EXCLUDED:
        requested['CONFIG_PACKAGE_' + name] = 'n'
    hardware_path = OUT / 'hardware-required.config'
    if hardware_path.exists():
        hardware = inventory.config(hardware_path)
        hardware.update({k: 'n' for k in re.findall(r'^# (CONFIG_\S+) is not set$', hardware_path.read_text(), re.M)})
        requested.update(hardware)
    else:
        hardware = {}
    modem_path = OUT / 'modem-required.config'
    if not modem_path.exists():
        raise SystemExit('Missing reviewed ModemManager driver fragment: ' + str(modem_path))
    modem = inventory.config(modem_path)
    modem.update({k: 'n' for k in re.findall(r'^# (CONFIG_\S+) is not set$', modem_path.read_text(), re.M)})
    requested.update(modem)
    for row in choices:
        if row['action'] in ('exclude', 'replace-hardware') and modem.get('CONFIG_PACKAGE_' + row['package']) == 'y':
            row.update(action='migrate-modem-driver', target=row['package'],
                       reason='按最新要求补齐经 R3 Mini 总线、MM 协议和内核核对的蜂窝模块驱动')
    values.update(feature_requests)
    values.update(requested)
    for symbol in list(values):
        if symbol.startswith(('CONFIG_PACKAGE_luci-app-qmodem_', 'CONFIG_PACKAGE_qmodem_', 'CONFIG_PACKAGE_tom_modem_')):
            values[symbol] = 'n'
    for name in ('node', 'UAmask', 'ua3f', 'luci-app-athena-led', 'dns-over-https', 'daed-next', 'luci-app-daed-next'):
        values['CONFIG_PACKAGE_' + name] = 'n'
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'migration-decisions.tsv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(choices[0]), delimiter='\t')
        writer.writeheader(); writer.writerows(choices)
    preset = ROOT / 'defconfig/portalwrt-bpi-r3-mini-full.config'
    preset.write_text('# Generated by scripts/r3mini-migrate.py; reviewed feature migration.\n' + render(values))
    manifest = {'packages': requested, 'features': feature_requests, 'feature_replacements': FEATURE_RENAMES,
                'hardware_fragment_present': bool(hardware), 'modem_fragment_present': bool(modem)}
    (OUT / 'migration-requested.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if args.apply:
        shutil.copy2(preset, ROOT / '.config')
        print('Applied preset; next run make defconfig, then --verify.')
    if args.verify:
        verify()
    else:
        print(json.dumps({'x86_decisions': len(choices), 'requested_y': sum(v == 'y' for v in requested.values()),
                          'hardware_fragment_present': bool(hardware)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
