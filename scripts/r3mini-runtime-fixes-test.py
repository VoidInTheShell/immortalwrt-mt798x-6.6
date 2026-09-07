#!/usr/bin/env python3
"""Host regressions for the R3 Mini runtime-audit fixes; not RF/PPE emulation."""
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('autoneg', ROOT / 'scripts/r3mini-autoneg-test.py')
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)


class RuntimeFixes(unittest.TestCase):

    def test_r6_boot_log_fixes(self):
        defaults = (ROOT / 'package/r3mini-defaults/files/zzzz-r3mini-services').read_text()
        self.assertIn('/etc/init.d/sysntpd disable', defaults)
        self.assertIn('/etc/init.d/ntpd enable', defaults)
        self.assertIn('r3mini-ntp-service-applied', defaults)
        self.assertIn('mode health', defaults)
        self.assertIn('http-request return status 200', defaults)
        self.assertIn('r3mini-haproxy3-migration-applied', defaults)
        ntpd_package = (ROOT / 'feeds/packages/net/ntpd/Makefile').read_text()
        self.assertIn('rm -f "$${IPKG_INSTROOT}/usr/sbin/ntpd"', ntpd_package)
        self.assertIn('PROG=/sbin/ntpd', (ROOT / 'feeds/packages/net/ntpd/files/ntpd.init').read_text())

        haproxy = (ROOT / 'feeds/packages/net/haproxy/files/haproxy.cfg').read_text()
        self.assertIsNone(re.search(r'^\s*mode health\s*$', haproxy, re.M),
                          'Removed HAProxy mode returned')
        self.assertIn('http-request return status 200', haproxy)
        passwall = (ROOT / 'feeds/luci/applications/luci-app-passwall/Makefile').read_text()
        self.assertIn('+PACKAGE_$(PKG_NAME)_INCLUDE_Haproxy:haproxy', passwall)

        netns = (ROOT / 'target/linux/mediatek/patches-6.6/999-3005-netfilter-fix-vendor-sysctl-netns-safety.patch').read_text()
        self.assertIn('table[NF_SYSCTL_CT_QOS].data = &net->ct.sysctl_qos;', netns)
        self.assertIn('table[NF_SYSCTL_CT_NAT_MODE].mode = 0444;', netns)
        self.assertIn('table[NF_SYSCTL_CT_PROTO_TCP_NO_WINDOW_CHECK].mode = 0444;', netns)

        cfg = (ROOT / 'package/mtk/drivers/mt_wifi/src/mt_wifi/embedded/common/cmm_cfg.c').read_text()
        ack = cfg[cfg.index('INT32 set_datcfg_ack_cts_timeout '):
                  cfg.index('INT set_dst2acktimeout_proc')]
        self.assertLess(ack.index('ack_cts_enable[idx] == FALSE'), ack.index('distance[idx] > 0'))
        dts = (ROOT / 'target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts').read_text()
        self.assertRegex(dts, r'&wed2\s*\{\s*status = "disabled";\s*\};')

        advanced = (ROOT / 'package/luci-app-advancedplus/root/etc/init.d/advancedplus').read_text()
        function = helpers.function(advanced, 'setnetwizard')
        self.assertIn('local menu=/usr/share/luci/menu.d/luci-app-netwizard.json', function)
        self.assertIn('[ -f "$menu" ] || return 0', function)
        addhost = ROOT / 'package/luci-app-adguardhome/luci-app-adguardhome/root/usr/share/AdGuardHome/addhost.sh'
        self.assertTrue(os.stat(addhost).st_mode & 0o111)

    def test_profile_order_and_acceleration_selection(self):
        for name in ('.config', 'defconfig/portalwrt-bpi-r3-mini-full.config',
                     'docs/r3mini-migration-audit/hardware-required.config'):
            source = (ROOT / name).read_text()
            self.assertIn('# CONFIG_MTK_DEFAULT_5G_PROFILE is not set', source)
            for flag in ('MTK_DBDC_MODE', 'MTK_MULTI_PROFILE_SUPPORT',
                         'MTK_FAST_NAT_SUPPORT', 'MTK_WARP_V2'):
                self.assertIn('CONFIG_' + flag + '=y', source)
        source = (ROOT / 'package/mtk/applications/mtwifi-cfg/files/mtwifi.sh').read_text()
        self.assertRegex(source, r'if \[ \$idx -eq 1 \]; then\s+band="2g"')

    def test_actual_dt_eeprom_reader(self):
        source = (ROOT / 'target/linux/mediatek/files-6.6/drivers/net/wireless/wifi_utility/mt_wifi_mtd.c').read_text()
        dts = (ROOT / 'target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts').read_text()
        values = re.search(r'mediatek,eeprom-data = <(.*?)>;', dts, re.S)[1]
        blob = b''.join(int(v, 16).to_bytes(4, 'big') for v in values.split())
        self.assertEqual(len(blob), 0x1000)
        self.assertEqual(blob[0x19a], 0)
        self.assertEqual(blob[0x190:0x192], b'\x12\x5b')  # 2G 2x2, 5G 3x3
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
#include <sys/types.h>
typedef uint8_t u8;
struct device_node { int dummy; };
static struct device_node node;
static bool board = true, present = true, property = true;
static int blobsize = 0x1000, refs;
static u8 blob[] = { BLOB };
static bool of_machine_is_compatible(const char *s) {
    assert(!strcmp(s, "bananapi,bpi-r3-mini")); return board;
}
static struct device_node *of_find_node_by_path(const char *s) {
    assert(!strcmp(s, "/soc/wifi@18000000"));
    if (!present) return NULL;
    refs++; return &node;
}
static const void *of_get_property(struct device_node *n, const char *s, int *size) {
    assert(n == &node && !strcmp(s, "mediatek,eeprom-data"));
    *size = blobsize; return property ? blob : NULL;
}
static void of_node_put(struct device_node *n) { assert(n == &node); refs--; }
#define min(a,b) ((a) < (b) ? (a) : (b))
#define pr_info_once(...) ((void)0)
FUNCTION
int main(void) {
    u8 out[0x5000]; memset(out, 0xa5, sizeof(out));
    assert(!mt_wifi_read_r3mini_eeprom(0, sizeof(out), out));
    assert(!memcmp(out, blob, sizeof(blob)));
    for (unsigned i = sizeof(blob); i < sizeof(out); i++) assert(out[i] == 0);
    assert(!mt_wifi_read_r3mini_eeprom(0x190, 2, out));
    assert(out[0] == 0x12 && out[1] == 0x5b);
    assert(mt_wifi_read_r3mini_eeprom(-1, 1, out) == -ERANGE);
    assert(mt_wifi_read_r3mini_eeprom(0x1000, 1, out) == -ERANGE);
    assert(mt_wifi_read_r3mini_eeprom(0xfff, 2, out) == -ERANGE);
    assert(mt_wifi_read_r3mini_eeprom(0, 0x5001, out) == -ERANGE);
    blob[0x19a] = 1;
    assert(mt_wifi_read_r3mini_eeprom(0, sizeof(out), out) == -ENODATA);
    blob[0x19a] = 0;
    blobsize--;
    assert(mt_wifi_read_r3mini_eeprom(0, sizeof(out), out) == -ENODATA);
    blobsize++;
    blob[0] = 0;
    assert(mt_wifi_read_r3mini_eeprom(0, sizeof(out), out) == -ENODATA);
    property = false;
    assert(mt_wifi_read_r3mini_eeprom(0, 1, out) == -ENODATA);
    present = false;
    assert(mt_wifi_read_r3mini_eeprom(0, 1, out) == -ENODEV);
    board = false;
    assert(mt_wifi_read_r3mini_eeprom(0, 1, out) == -ENODEV);
    assert(refs == 0);
}
'''.replace('BLOB', ','.join(str(b) for b in blob))
        helpers.run_c(code.replace('FUNCTION', helpers.function(source, 'mt_wifi_read_r3mini_eeprom')))
        read = helpers.function(source, 'mt_mtd_read_nm_wifi')
        self.assertLess(read.index('get_mtd_device_nm'), read.index('mt_wifi_read_r3mini_eeprom'))
        self.assertNotIn('mt_wifi_read_r3mini_eeprom', helpers.function(source, 'mt_mtd_write_nm_wifi'))

    def test_actual_iwinfo_channels_and_uci_lifetime(self):
        source = (ROOT / 'package/network/utils/iwinfo/src/iwinfo_mtk.c').read_text()
        header = (ROOT / 'staging_dir/target-aarch64_cortex-a53_musl/usr/include/iwinfo.h').read_text()
        structure = re.search(r'struct iwinfo_freqlist_entry \{.*?\};', header, re.S)[0]
        functions = '\n'.join(helpers.function(source, n) for n in
                              ('mtk_get_freqlist', 'mtk_get_hwmodelist', 'mtk_get_htmodelist'))
        flags = sorted(set(re.findall(r'IWINFO_(?:HTMODE|80211)_\w+', functions)))
        defines = '\n'.join('#define %s (1U << %d)' % (flag, i) for i, flag in enumerate(flags))
        code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <linux/wireless.h>
#define IWINFO_BUFSIZE (24 * 1024)
#define IWINFO_BAND_24 1
#define IWINFO_BAND_5 2
DEFINES
STRUCTURE
static int fail, count = 3, band = IWINFO_BAND_5;
static const char *uci_band = "5g";
static char *allocation;
static void *uci_ctx;
struct uci_section { int unused; };
static struct uci_section section;
static const char *mtk_dev2phy(const char *s) { return s; }
static int mtk_is_ifup(const char *s) { (void)s; return !fail; }
static int mtk_get_op_band(const char *s) { (void)s; return band; }
static int wext_freq2mhz(const struct iw_freq *f) { return f->m; }
static int mtk_ioctl(const char *s, int cmd, struct iwreq *w) {
    (void)s; assert(cmd == SIOCGIWRANGE);
    struct iw_range *r = w->u.data.pointer;
    r->num_frequency = count;
    for (unsigned i=0; i<sizeof(r->freq)/sizeof(r->freq[0]); i++) {
        r->freq[i].i = band == IWINFO_BAND_24 ? 1 : 36 + i * 4;
        r->freq[i].m = band == IWINFO_BAND_24 ? 2412 : 5180 + i * 20;
    }
    return 0;
}
static struct uci_section *iwinfo_uci_get_radio(const char *d, const char *t) {
    (void)d; (void)t; return &section;
}
static const char *uci_lookup_option_string(void *ctx, struct uci_section *s, const char *k) {
    (void)ctx; (void)s; (void)k;
    allocation = uci_band ? strdup(uci_band) : NULL; return allocation;
}
static void iwinfo_uci_free(void) { free(allocation); allocation = NULL; }
FUNCTIONS
int main(void) {
    char out[IWINFO_BUFSIZE]; int len = 123, modes;
    memset(out, 0xa5, sizeof(out));
    assert(!mtk_get_freqlist("ra0", out, &len));
    assert(len == 3 * sizeof(struct iwinfo_freqlist_entry));
    struct iwinfo_freqlist_entry *e = (void *)out;
    for (int i=0;i<3;i++) assert(!e[i].flags && !e[i].restricted && e[i].band == IWINFO_BAND_5);
    count = 255;
    assert(!mtk_get_freqlist("ra0", out, &len));
    assert(len == IW_MAX_FREQUENCIES * sizeof(*e));
    fail = 1;
    assert(mtk_get_freqlist("ra0", out, &len) == -1 && len == 0);
    fail = 0; count = 3;
    assert(!mtk_get_hwmodelist("ra0", &modes) && (modes & IWINFO_80211_AC));
    assert(!mtk_get_htmodelist("ra0", &modes) && (modes & IWINFO_HTMODE_HE160));
    uci_band = "2g";
    assert(!mtk_get_hwmodelist("rax0", &modes) && (modes & IWINFO_80211_N));
    assert(!mtk_get_htmodelist("rax0", &modes) && !(modes & IWINFO_HTMODE_HE160));
    uci_band = NULL;
    assert(!mtk_get_htmodelist("ra0", &modes) && (modes & IWINFO_HTMODE_HE160));
    band = IWINFO_BAND_24;
    assert(!mtk_get_hwmodelist("rax0", &modes) && !(modes & IWINFO_80211_AC));
}
'''.replace('DEFINES', defines).replace('STRUCTURE', structure).replace('FUNCTIONS', functions)
        helpers.run_c(code)

    def test_luci_empty_state_and_kucat_preferences(self):
        script = r'''
const fs = require('fs'), assert = require('assert');
String.prototype.format = function(...args) { let i=0; return this.replace(/%s/g, () => args[i++]); };
function E(tag, attrs, children) {
    return { tag, attrs, children: children == null ? [] : Array.isArray(children) ? children : [children],
        appendChild(child) { this.children.push(child); } };
}
const dom = { bindClassInstance() {} };
const upstream = fs.readFileSync('feeds/luci/modules/luci-base/htdocs/luci-static/resources/form.js','utf8');
const start = upstream.indexOf('renderContents(cfgsections, nodes)');
let i=upstream.indexOf('{',start)+1, depth=1;
for (;depth;i++) depth += (upstream[i]=='{') - (upstream[i]=='}');
const renderTyped = new Function('E','dom','return ({'+upstream.slice(start,i)+'}).renderContents;')(E,dom);
let sections=[], calls=[];
const uci = { sections(c,t,cb) { const result=c=='mmconfig' ? sections : []; if(cb)result.forEach(cb); return result; },
    load() { return Promise.resolve(); }, get() { return null; },
    add() { throw Error('Empty UI must not create UCI sections'); } };
const form = { TypedSection:'typed', NamedSection:'named', Button:'button', DummyValue:'dummy',
    HiddenValue:'hidden', Value:{extend(x){return x;}} };
form.Map = function(config) { this.config=config; this.parts=[]; this.saved=0; };
form.Map.prototype.section = function(type,id,sectiontype,title) {
    const part = { type, sectiontype: type=='typed' ? id : sectiontype, title:type=='typed' ? sectiontype : title,
        section:id, map:this, children:[], option(type,name,title) { const o={type,name,title}; this.children.push(o); return o; },
        renderSectionAdd() { return E('div'); }, renderSectionPlaceholder() { return E('em'); } };
    this.parts.push(part); return part;
};
form.Map.prototype.save = function() { this.saved++; return Promise.resolve(); };
form.Map.prototype.render = function() {
    for(const p of this.parts) {
        if(p.type=='typed') p.dom=renderTyped.call(p,p.cfgsections(),[p.children]);
        else { assert(sections.some(s=>s['.name']==p.section)); assert.equal(p.sectiontype,'modem'); }
    }
    return Promise.resolve(this);
};
const api = new Function('form','fs','uci','ui','view','helper','document','window','E','_',
    fs.readFileSync('package/mm-ui-bands/htdocs/luci-static/resources/view/mmconfig/bands.js','utf8'))(
    form,{exec_direct(path,args){calls.push(args[0]);return Promise.resolve();}},uci,{addNotification(){}},
    {extend(x){return x;}},{getModems(){return Promise.resolve([]);}},
    {createElement(){return {};},head:{appendChild(){}}},{location:{reload(){calls.push('reload');}}},E,s=>s);
(async()=>{
    let map=await api.render(await api.load());
    assert.equal(map.parts.length,2);
    const actions=map.parts[0], empty=map.parts[1];
    assert.equal(actions.type,'typed'); assert.equal(empty.type,'typed');
    assert(actions.dom.children.some(n=>n && n.attrs && n.attrs['data-section-id']=='actions'));
    assert(empty.children[0].default.includes('No ModemManager device'));
    assert.equal(actions.children.length,2);
    await actions.children[0].onclick(); assert.deepEqual(calls,['discover','reload']);
    await actions.children[1].onclick(); assert.equal(calls[2],'apply');
    assert.equal(sections.length,0);
    sections=[{'.name':'saved', device:'/dev/cdc-wdm0'}];
    map=await api.render([null,null,[]]);
    assert.equal(map.parts[1].type,'named');
    assert(map.parts[1].children.some(o=>String(o.default).includes('not currently reported')));
    const source=fs.readFileSync('package/luci-theme-kucat/htdocs/luci-static/resources/menu-kucat.js','utf8');
    for(const saved of [null,'basic','allmenu','invalid']) {
        const menu=new Function('baseclass','localStorage','console',source)(
            {extend(x){return x;}},{getItem(){return saved;}},{warn(){},error(){},log(){},debug(){}});
        menu.loadSavedCategory(); assert.equal(menu.currentCategory,saved=='basic'?'basic':'allmenu');
    }
    console.log('Actual LuCI TypedSection renderer: empty/disconnected modem; Kucat preferences: OK');
})().catch(e=>{console.error(e);process.exit(1);});
'''
        subprocess.run(['node', '-e', script], cwd=ROOT, check=True)

    def test_qosmate_version_and_managed_policy(self):
        for name, commit in [('qosmate', '5a27872'), ('luci-app-qosmate', '6d2abc7')]:
            source = (ROOT / 'package' / name / 'Makefile').read_text()
            self.assertIn('PKG_VERSION:=1.9.0+git.20260727.' + commit, source)
        source = (ROOT / 'package/qosmate/Makefile').read_text()
        self.assertIn('portalwrt-managed', source)
        self.assertIn('VERSION="$(PKG_UPSTREAM_COMMIT)"', source)
        self.assertIn('UPD_CHANNEL="snapshot"', source)
        frontend = (ROOT / 'package/luci-app-qosmate/Makefile').read_text()
        self.assertIn("UI_VERSION = '$(PKG_UPSTREAM_COMMIT)'", frontend)
        self.assertIn("UI_UPD_CHANNEL = 'snapshot'", frontend)

    def test_qosmate_parses_minified_and_plain_frontend_versions(self):
        source = (ROOT / 'package/qosmate/etc/init.d/qosmate').read_text()
        function = helpers.function(source, 'get_frontend_spec')
        shell = "_NL_='\n'\nare_var_names_safe() { return 0; }\nerror_out() { echo \"$*\" >&2; }\n"
        shell += function + '\nget_frontend_spec version channel "$1" || exit 1\nprintf "%s %s" "$version" "$channel"\n'
        variants = ["const UI_VERSION = 'abc123';\nconst UI_UPD_CHANNEL = 'snapshot';",
                    "'use strict';'require fs';const UI_VERSION='abc123';const UI_UPD_CHANNEL='snapshot';var x='later';"]
        with tempfile.TemporaryDirectory(prefix='r3mini-version-test-') as temp:
            path = Path(temp) / 'settings.js'
            for text in variants:
                path.write_text(text)
                result = subprocess.run(['bash', '-c', shell, 'test', str(path)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'abc123 snapshot')
            path.write_text("const UI_VERSION='bad version';const UI_UPD_CHANNEL='snapshot';")
            self.assertNotEqual(subprocess.run(['bash', '-c', shell, 'test', str(path)],
                                               capture_output=True).returncode, 0)
            path.write_text("const UI_VERSION='abc123';")
            self.assertNotEqual(subprocess.run(['bash', '-c', shell, 'test', str(path)],
                                               capture_output=True).returncode, 0)


    def test_zerotier_first_network_generates_persistent_identity(self):
        init = ROOT / 'feeds/packages/net/zerotier/files/etc/init.d/zerotier'
        config = ROOT / 'feeds/packages/net/zerotier/files/etc/config/zerotier'
        defaults = ROOT / 'package/r3mini-defaults/files/zzzz-r3mini-services'
        package = ROOT / 'package/r3mini-defaults/Makefile'
        self.assertIn("option secret ''", config.read_text())
        self.assertIn("option config_path '/etc/zerotier'", config.read_text())
        self.assertIn('IDTOOL=/usr/bin/zerotier-idtool', init.read_text())
        self.assertIn('ensure_identity || return 1', init.read_text())
        self.assertIn('[ "${service_active}" -eq 1 ] || return 0', init.read_text())
        self.assertIn('/etc/init.d/zerotier enable', defaults.read_text())
        self.assertNotIn('tailscale zerotier softethervpnserver', defaults.read_text())
        self.assertIn('r3mini-zerotier-demand-start-applied', package.read_text())
        subprocess.run(['sh', '-n', str(init)], check=True)
        subprocess.run(['sh', '-n', str(defaults)], check=True)

        harness = r'''
source="$1"
root="$2"
secret_value='aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
config_load() { :; }
config_get_bool() {
	var="$1"; section="$2"; option="$3"; value="${4:-0}"
	case "$section.$option" in
	global.enabled) value="$GLOBAL_ENABLED" ;;
	global.initialized) value="$INITIALIZED" ;;
	global.copy_config_path) value=0 ;;
	testnet.enabled) value="$NETWORK_ENABLED" ;;
	testnet.allow_managed) value=1 ;;
	testnet.allow_global|testnet.allow_default|testnet.allow_dns) value=0 ;;
	esac
	eval "$var=\$value"
}
config_get() {
	var="$1"; section="$2"; option="$3"; value="${4:-}"
	case "$section.$option" in
	global.secret) value="$GLOBAL_SECRET" ;;
	global.config_path) value="$PERSIST" ;;
	global.port|global.local_conf_path) value='' ;;
	testnet.id) value='0123456789abcdef' ;;
	esac
	eval "$var=\$value"
}
config_foreach() { [ "$2" = network ] && "$1" testnet; }
uci() { printf '%s\n' "$*" >> "$root/uci.log"; }
procd_open_instance() { printf '%s\n' open >> "$root/procd.log"; }
procd_set_param() { printf '%s\n' "$*" >> "$root/procd.log"; }
procd_close_instance() { printf '%s\n' close >> "$root/procd.log"; }

. "$source"
IDTOOL="$root/idtool"

# A fresh image has no key and no global service toggle. Adding one enabled
# network must persist a newly generated identity and promote that first use.
RUNTIME="$root/first/runtime"; PERSIST="$root/first/persist"
CONFIG_PATH="$RUNTIME"; GLOBAL_ENABLED=0; INITIALIZED=0; GLOBAL_SECRET=''; NETWORK_ENABLED=1
start_service
[ -L "$RUNTIME" ] && [ "$(readlink "$RUNTIME")" = "$PERSIST" ] || exit 10
[ "$(cat "$PERSIST/identity.secret")" = "$secret_value" ] || exit 11
[ "$(cat "$PERSIST/identity.public")" = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' ] || exit 12
[ "$(stat -c '%a' "$PERSIST/identity.secret")" = 600 ] || exit 13
[ -f "$PERSIST/networks.d/0123456789abcdef.conf" ] || exit 14
grep -Fx 'set zerotier.global.enabled=1' "$root/uci.log" >/dev/null || exit 15
grep -Fx "set zerotier.global.secret=$secret_value" "$root/uci.log" >/dev/null || exit 16

# A restart derives a matching public identity instead of leaving the stale
# public key behavior that made the original implementation fragile.
printf '%s\n' stale > "$PERSIST/identity.public"
: > "$root/idtool.log"
GLOBAL_ENABLED=1; INITIALIZED=1; GLOBAL_SECRET="$secret_value"
start_service
! grep -Fx generate "$root/idtool.log" >/dev/null || exit 17
[ "$(cat "$PERSIST/identity.public")" = 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' ] || exit 18

# No enabled network must remain inert: no daemon instance, key generation,
# or firewall wait is allowed merely because the init trigger is registered.
RUNTIME="$root/idle/runtime"; PERSIST="$root/idle/persist"
CONFIG_PATH="$RUNTIME"; GLOBAL_ENABLED=0; INITIALIZED=0; GLOBAL_SECRET=''; NETWORK_ENABLED=0
: > "$root/idtool.log"; : > "$root/procd.log"; : > "$root/uci.log"
start_service
[ ! -e "$PERSIST/identity.secret" ] || exit 19
[ ! -s "$root/idtool.log" ] || exit 20
[ ! -s "$root/procd.log" ] || exit 21
[ ! -s "$root/uci.log" ] || exit 22
'''
        with tempfile.TemporaryDirectory(prefix='r3mini-zerotier-test-') as temp:
            root = Path(temp)
            idtool = root / 'idtool'
            idtool.write_text(textwrap.dedent('''\
                #!/bin/sh
                printf '%s\\n' "$1" >> "$ZT_IDTOOL_LOG"
                case "$1" in
                generate) printf '%s\\n' 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ;;
                validate) [ "$(cat "$2")" = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ] ;;
                getpublic) [ "$(cat "$2")" = 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' ] && printf '%s\\n' 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb' ;;
                *) exit 1 ;;
                esac
                '''))
            idtool.chmod(0o755)
            result = subprocess.run(['sh', '-c', textwrap.dedent(harness), 'test', str(init), temp],
                                    env={'PATH': '/usr/bin:/bin', 'ZT_IDTOOL_LOG': str(root / 'idtool.log')},
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
