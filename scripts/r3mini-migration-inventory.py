#!/usr/bin/env python3
"""Read existing package metadata/configs; emit an audit, never alter configs.

Classification is triage, not a build or runtime compatibility guarantee.
Run from the target tree after its package metadata has been generated.
"""
import argparse
import collections
import csv
import hashlib
import json
from pathlib import Path
import re


def config(path):
    return dict(re.findall(r'^(CONFIG_[^=]+)=(.*)$', path.read_text(), re.M))


def metadata(path):
    result, duplicates = {}, {}
    source = ''
    build_deps = ''
    for block in path.read_text().split('\n\n'):
        fields = dict(re.findall(r'^([\w-]+):[ \t]?(.*)$', block, re.M))
        if 'Source-Makefile' in fields:
            source = fields['Source-Makefile']
            build_deps = fields.get('Build-Depends', '')
        if 'Package' in fields:
            name = fields['Package']
            fields['Source-Makefile'] = source
            fields['Build-Depends'] = build_deps
            if name in result:
                duplicates.setdefault(name, [result[name]['Source-Makefile']]).append(source)
            result[name] = fields
    return result, duplicates


EXCLUDE_HW = set('''8139cp 8139too acpi-video amazon-ena amd-xgbe ata-ahci ata-core
b43 backlight bcma be2net bluetooth bnx2x bnxt-en brcmsmac brcmutil button-hotplug
cfg80211 dax dma-buf drm drm-amdgpu drm-buddy drm-display-helper drm-exec drm-i915
drm-kms-helper drm-suballoc-helper drm-ttm drm-ttm-helper dsa dsa-b53 dsa-b53-mdio
dwmac-intel e1000 e1000e fb fb-cfb-copyarea fb-cfb-fillrect fb-cfb-imgblt fb-sys-fops
fb-sys-ram fixed-phy forcedeth hid hid-generic i2c-algo-bit i2c-core i40e iavf ice
igb igbvf igc input-core input-evdev ixgbe ixgbevf lib-cordic lib-crc8 lib-objagg
lib-parman mac80211 mdio mdio-devres mhi-bus mhi-net mhi-pci-generic mhi-wwan-ctrl
mhi-wwan-mbim mlx4-core mlx5-core mlxfw mlxsw-core mlxsw-i2c mlxsw-minimal mlxsw-pci
mlxsw-spectrum mmc mtk-t7xx pcie_mhi pcnet32 pcs-xpcs phy-ax88796b phy-broadcom
phy-marvell phy-marvell-10g phy-microchip phy-realtek phylib-broadcom phylink
pps ptp qrtr qrtr-mhi r8101 r8125 r8126 r8168 r8169 random-core regmap-core sfp ssb
stmmac-core tg3 tpm tulip usb-hid vmxnet3 wwan'''.split())
MODEM = set('''luci-app-modem luci-proto-3g luci-proto-mbim luci-proto-qmi
luci-proto-ncm luci-proto-quectel quectel-cm quectel-CM-5G-M quectel-timesync
modemband modemmanager-rpcd sendat adb-enablemodem comgt comgt-directip comgt-ncm
uqmi umbim sms-tool'''.split())
STATEFUL = set('''qosmate UAmask ua3f nikki mihomo-meta banip geoip-shell
ipset-dns dnsforwarder dns-over-https dns2socks dns2tcp chinadns-ng smartdns smartdns-ui
adguardhome dhcp-forwarder dhcpcd ntpd ntpdate rdnssd conntrackd igmpproxy omcproxy
avahi-dbus-daemon mdnsd mdnsresponder umdns openssh-server sshtunnel ntfs-3g ntfs3-mount
tc-tiny tc-full ethtool ethtool-full irqbalance miniupnpd-iptables miniupnpd-nftables
tailscale zerotier softethervpn5-server softethervpn5-client softethervpn5-bridge
autosamba rsyncd samba4-server nfs-kernel-server cups p910nd atftpd vsftpd memcached
netdata collectd zram-swap luci-app-advancedplus luci-app-poweroffdevice
luci-app-taskplan luci-app-athena-led'''.split())


def classify(name, meta, current):
    if name == 'autocore':
        return 'replace', '使用目标仓库 autocore-arm；不能覆盖板级初始化'
    if name in {'bridger', 'kmod-nft-fullcone'}:
        return 'missing-special', '当前目标无此包；不是同名通用包迁移，见报告'
    if name == 'node' or name.startswith('node-') or name == 'ts-node':
        return 'exclude-node', '用户要求暂缓 Node.js；同时排除反向依赖'
    if current in {'y', 'm'}:
        return 'keep-target', '保留目标版本和硬件相关选择；已有包仍需检查服务配置'
    if name not in meta:
        return 'missing', '目标包索引不存在'
    m = meta[name]
    if (m.get('Category') == 'Firmware' or name.startswith('grub2')
            or name in {'amd64-microcode', 'intel-microcode', 'broadcom-43224-sprom'}
            or name.removeprefix('kmod-') in EXCLUDE_HW):
        return 'exclude-hardware', 'x86/外设驱动与固件不整体搬；板级包由 R3 Mini 选择'
    if name.startswith(('hostapd', 'wpad', 'wpa-supplicant', 'eapol-test')) or name in {
            'wifi-scripts', 'wireless-regdb', 'iw', 'wpa-cli', 'wifischedule', 'aircrack-ng'}:
        return 'wireless-review', '依赖主线无线栈，不能作为 MTK 私有驱动管理组件直接套用'
    if name in MODEM or name in {'kmod-usb-net-qmi-wwan-fibocom', 'kmod-usb-net-qmi-wwan-quectel'}:
        return 'modem-review', '保留 ModemManager 单一拨号管理；诊断工具可按需保留'
    if name.startswith('kmod-usb-'):
        return 'optional-peripheral', '按实际 USB 外设选取；不是主板必要适配'
    if name in {'luci-ssl', 'libustream-mbedtls', 'px5g-mbedtls'}:
        return 'tls-variant', '目标已用 libustream-openssl，优先 luci-ssl-openssl'
    if name.startswith(('lib', 'boost', 'perlbase-', 'python3-')) or m.get('Category') == 'Libraries':
        return 'dependency', '用目标构建系统重算依赖；Python/Perl 功能模块可按需补全'
    if name.startswith('luci-i18n-'):
        return 'translation', '跟随对应 LuCI 应用的迁移决策'
    if (name in STATEFUL or name.startswith(('luci-app-', 'iptables', 'ip6tables', 'kmod-ipt-', 'kmod-nft-', 'kmod-sched'))):
        return 'runtime-review', '可用源码候选；核对默认启动、端口、规则和卸载路径'
    if name.startswith('kmod-'):
        return 'generic-kernel-review', '通用内核功能；只用目标内核源码重编，依赖/用途逐项核对'
    if name in {'naiveproxy', 'hysteria', 'xray-core', 'sing-box', 'rclone', 'cups-filters'}:
        return 'heavy-build', '存在 aarch64 候选；关注工具链、下载和编译成本'
    return 'generic-candidate', '目标已有定义，可迁移功能选择；尚未完成目标架构编译验证'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--x86', type=Path, default=Path('/home/beihai/x86_immortalwrt'))
    parser.add_argument('--target', type=Path, default=Path.cwd())
    parser.add_argument('--out', type=Path, default=Path('docs/r3mini-migration-audit'))
    args = parser.parse_args()
    xconf, rconf = config(args.x86 / '.config'), config(args.target / '.config')
    xmeta, xdups = metadata(args.x86 / 'tmp/.packageinfo')
    rmeta, rdups = metadata(args.target / 'tmp/.packageinfo')
    selected = {s[15:]: v for s, v in xconf.items()
                if s.startswith('CONFIG_PACKAGE_') and v in {'y', 'm'} and s[15:] in xmeta}
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, value in sorted(selected.items()):
        cur = rconf.get('CONFIG_PACKAGE_' + name, 'n')
        category, note = classify(name, rmeta, cur)
        m = rmeta.get(name, {})
        rows.append([name, value, cur, category, note, xmeta[name].get('Version', ''),
                     m.get('Version', ''), m.get('Source-Makefile', ''),
                     m.get('Depends', ''), m.get('Provides', ''), m.get('Conflicts', ''),
                     m.get('Build-Depends', '')])
    with (args.out / 'packages.tsv').open('w') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['package', 'x86_selection', 'r3_selection', 'triage', 'note',
                         'x86_version', 'r3_version', 'r3_makefile', 'depends', 'provides', 'conflicts',
                         'build_depends'])
        writer.writerows(rows)
    feature_rows = [[s, v, rconf.get(s, 'n')] for s, v in sorted(xconf.items())
                    if s.startswith(('CONFIG_PACKAGE_', 'CONFIG_DROPBEAR_', 'CONFIG_OPENSSH_',
                                     'CONFIG_BUSYBOX_', 'CONFIG_LIBQMI_', 'CONFIG_MODEMMANAGER_'))
                    and s.removeprefix('CONFIG_PACKAGE_') not in xmeta
                    and v != rconf.get(s, 'n')]
    with (args.out / 'feature-differences.tsv').open('w') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(['symbol', 'x86_value', 'r3_value'])
        writer.writerows(feature_rows)
    summary = {'x86_packages': dict(collections.Counter(selected.values())),
               'target_packages': dict(collections.Counter(v for s, v in rconf.items()
                   if s.startswith('CONFIG_PACKAGE_') and s[15:] in rmeta and v in {'y', 'm'})),
               'triage': dict(collections.Counter(row[3] for row in rows)),
               'missing_real_packages': sorted(set(selected) - rmeta.keys()),
               'x86_duplicate_definitions': xdups, 'target_duplicate_definitions': rdups,
               'sha256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                   for root in (args.x86, args.target) for p in
                   (root / '.config', root / 'tmp/.packageinfo')},
               'scope': 'Existing metadata only; no configuration writes, downloads, builds or runtime tests.'}
    (args.out / 'inventory.json').write_text(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k not in {'sha256'}}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
