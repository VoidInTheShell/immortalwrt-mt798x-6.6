#!/usr/bin/env python3
"""Offline regression tests: execute the shipped shell helpers with fake UCI/I/O."""
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODEM = ROOT / 'package/5gmodem-feed/luci-app-5gmodem/root/usr/share/5gmodem'


class RuntimeTests(unittest.TestCase):
    def test_new_interface_metric_does_not_collide(self):
        script = (MODEM/'mkiface.sh').read_text()
        helper = re.search(r'^_def_metric\(\) \{.*?^\}', script, re.M | re.S).group()
        mock = '''
uci() { case "$*" in *mwan3_metrics) echo "$MWAN" ;; *'show network') printf '%s\n' "$NETWORK" ;; esac; }
_def_metric
'''
        cases = [('0', '', '110'), ('0', "network.wan.metric='110'", '120'),
                 ('0', "network.wan.metric='100'\nnetwork.backup.metric='120'", '130'),
                 ('1', "network.wan.metric='20'", '30')]
        for mwan, network, expected in cases:
            with self.subTest(network=network):
                p = subprocess.run(['sh','-c', helper+'\n'+mock], text=True, capture_output=True,
                                   env={**os.environ, 'MWAN': mwan, 'NETWORK': network})
                self.assertEqual(p.stdout.strip(), expected)

    def test_deferred_creator_respects_current_state(self):
        script = (MODEM/'mkiface.sh').read_text()
        guard = re.search(r'^_mk_may_start\(\) \{.*?^\}', script, re.M | re.S).group()
        mock = '''
uci() { case "$*" in *.proto) echo "$CURRENT_PROTO" ;; *.device) echo /dev/cdc-wdm0 ;; esac; }
iface_config_disabled() { [ "$DISABLED" = 1 ]; }
iface_runtime_state() { echo "$STATE"; }
IF=modem; PROTO=qmi; IDEV=/dev/cdc-wdm0
_mk_may_start; echo $?
'''
        for state in ('missing', 'disabled', 'stopped', 'up', 'pending', 'failed', 'down', 'unavailable'):
            for proto, disabled in (('qmi','0'), ('mbim','0'), ('qmi','1')):
                with self.subTest(state=state, proto=proto, disabled=disabled):
                    p = subprocess.run(['sh', '-c', guard+'\n'+mock], text=True, capture_output=True,
                                       env={**os.environ, 'CURRENT_PROTO': proto, 'DISABLED': disabled, 'STATE': state})
                    allowed = state in ('failed','down','unavailable') and proto == 'qmi' and disabled == '0'
                    self.assertEqual(p.stdout.strip(), '0' if allowed else '1')

    def shell(self, body, env=None):
        result = subprocess.run(['sh', '-c', '. ' + shlex.quote(str(MODEM / 'runtime-state.sh')) + '\n' + body],
                                text=True, capture_output=True, env={**os.environ, **(env or {})})
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_registration_domains(self):
        cases = [
            ('+CPIN: READY\n+CREG: 2,3\n+CEREG: 2,1,"10DE","040D53A",7', 'ready|1|3|1'),
            ('+CPIN: READY\n+CREG: 2,0\n+CEREG: 2,5', 'ready|5|0|5'),
            ('+CPIN: READY\n+CREG: 2,6\n+CEREG: 2,1', 'ready|1|6|1'),
            ('+CME ERROR: 10\n+CREG: 2,0\n+CEREG: 2,0', 'absent|SIM not inserted|0|0'),
            ('+CPIN: SIM PIN\n+CREG: 2,0', 'pin|SIM PIN required|0|'),
            ('+CPIN: SIM PUK\n+CREG: 2,0', 'puk|SIM PUK required|0|'),
            ('+CPIN: READY\n+CREG: 2,1', 'ready|1|1|'),
            ('+CPIN: READY\n+CEREG: 2,2\n+C5GREG: 2,1', 'ready|1||1'),
            ('+CPIN: READY\n+CREG: 2,3\n+CEREG: 1,"10DE","040D53A",7', 'ready|1|3|1'),
            ('+CPIN: READY\n+CREG: 2,3\n+CEREG: 2,3', 'ready|3|3|3'),
        ]
        for reply, expected in cases:
            with self.subTest(reply=reply):
                self.assertEqual(self.shell('modem_registration "$REPLY"; printf "%s|%s|%s|%s" "$SIM_STATE" "$REG" "$REG_CS" "$REG_DATA"', {'REPLY': reply}), expected)

    def test_interface_state(self):
        mock = '''
uci() { case "$*" in
  *network.modem.auto) [ -n "$AUTO" ] && echo "$AUTO" ;;
  *network.modem.disabled) [ -n "$DISABLED" ] && echo "$DISABLED" ;;
  *network.modem) [ "$EXISTS" = 1 ] && echo interface ;;
esac; }
ifstatus() { printf '%s' "$STATUS"; }
jsonfilter() {
 python3 -c 'import json,sys; d=json.load(sys.stdin); q=sys.argv[-1]; v=[e.get("code", "") for e in d.get("errors",[])] if q=="@.errors[*].code" else [d.get(q[2:], "")]; print("\\n".join(str(x).lower() if isinstance(x,bool) else str(x) for x in v))' "$@"
}
iface_runtime_state modem
'''
        cases = [
            ({'EXISTS': '0'}, {}, 'missing'),
            ({'AUTO': '0'}, {'up': True}, 'disabled'),
            ({'DISABLED': '1'}, {'up': True}, 'disabled'),
            ({}, {'up': True}, 'up'),
            ({}, {'up': False, 'pending': True}, 'pending'),
            ({}, {'autostart': False, 'errors': []}, 'stopped'),
            ({}, {'autostart': False, 'errors': [{'code': 'SIM_ILLEGAL_STATE'}]}, 'failed'),
            ({}, {'autostart': True, 'up': False}, 'down'),
        ]
        for config, state, expected in cases:
            with self.subTest(expected=expected):
                env = {'EXISTS': '1', 'AUTO': '', 'DISABLED': '', 'STATUS': json.dumps(state), **config}
                self.assertEqual(self.shell(mock, env), expected)

    def test_firewall_sync_checks_before_reload(self):
        mock = '''
ifstatus() { echo '{}'; }
jsonfilter() { cat >/dev/null; echo wwan0; }
fw4() {
 case "$2" in
 network) [ "$MAPPED" = 1 ] && echo wan ;;
 zone) [ "$DEVICE_MAPPED" = 1 ] ;;
 check) echo check >>"$LOG"; [ "$VALID" = 1 ] ;;
 reload) echo reload >>"$LOG" ;;
 esac
}
firewall_sync_iface modem; echo "exit=$?"
'''
        for mapped, dev, valid, expected in [('1','1','1',''), ('0','0','1','check\nreload\n'), ('1','0','1','check\nreload\n'), ('0','0','0','check\n')]:
            with tempfile.TemporaryDirectory() as tmp:
                log = Path(tmp)/'calls'
                out = self.shell(mock, {'MAPPED': mapped, 'DEVICE_MAPPED': dev, 'VALID': valid, 'LOG': str(log)})
                self.assertEqual(log.read_text() if log.exists() else '', expected)
                self.assertEqual(out, 'exit=' + ('0' if valid == '1' else '1'))


class ThemeTests(unittest.TestCase):
    def test_package_install_preserves_selected_theme(self):
        paths = [
            'feeds/luci/themes/luci-theme-argon/root/etc/uci-defaults/30_luci-theme-argon',
            'package/luci-theme-kucat/root/etc/uci-defaults/30_luci-kuacat',
            'package/luci-theme-kucat/root/etc/uci-defaults/30_luci-kucat',
        ]
        for path in paths:
            for upgrade in ('0', '1'):
                with self.subTest(path=path, upgrade=upgrade):
                    mock = '''
uci() {
 case "$*" in
 '-q get luci.main.mediaurlbase') echo /luci-static/custom ;;
 set*) echo "$*" ;;
 esac
}
rm() { :; }
chmod() { :; }
'''
                    p = subprocess.run(['sh', '-c', mock + '\n. ' + shlex.quote(str(ROOT/path))],
                                       env={**os.environ, 'PKG_UPGRADE': upgrade}, text=True, capture_output=True)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    self.assertNotIn('set luci.main.mediaurlbase=', p.stdout)

    def test_defaults_preserve_custom_settings_and_selected_theme(self):
        # Source the actual defaults helper; mock only the external UCI command.
        body = '''
uci() {
    case "$*" in
      '-q show kucat') echo 'kucat.basic=basic' ;;
      '-q show argon') echo 'argon.global=global' ;;
      '-q get system.portalwrt.theme_initialized') echo 1 ;;
      '-q get kucat.basic.primary_rgbm') echo '12,34,56' ;;
      '-q get kucat.basic.primary_rgbbody') echo '22,33,44' ;;
      '-q get argon.global.primary') echo '#123456' ;;
      '-q get argon.global.dark_primary') echo '#654321' ;;
      '-q get '*) echo existing ;;
      'set '*|'commit '*) printf '%s\\n' "$*" ;;
    esac
}
portal_theme
'''
        command='. '+shlex.quote(str(ROOT/'files/usr/lib/portalwrt/defaults.sh'))+'\n'+body
        p=subprocess.run(['sh','-c',command], text=True, capture_output=True)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertNotIn('set luci.main.mediaurlbase=',p.stdout)
        self.assertNotIn('set kucat.basic.primary_',p.stdout)
        self.assertNotIn('set argon.global.primary=',p.stdout)
        self.assertNotIn('set argon.global.dark_primary=',p.stdout)

    def test_both_templates_choose_shared_wallpaper(self):
        # This supplements execution tests; template compilation is tested on target.
        k=(ROOT/'package/luci-theme-kucat/ucode/template/themes/kucat/header.ut').read_text()
        a=(ROOT/'feeds/luci/themes/luci-theme-argon/ucode/template/themes/argon/sysauth.ut').read_text()
        for text in (k,a):
            self.assertIn('/luci-static/resources/background/portal.jpg',text)
            self.assertIn('?v=',text)
        keep=(ROOT/'files/lib/upgrade/keep.d/portal-theme').read_text()
        self.assertIn('/etc/portalwrt-background/',keep)
        self.assertIn('/etc/config/argon',keep)
        self.assertIn('/etc/config/kucat',keep)

    def test_wallpaper_lifecycle(self):
        with tempfile.TemporaryDirectory(prefix='portal-theme-test-') as tmp:
            root = Path(tmp)
            (root/'etc').mkdir(); (root/'bin').mkdir()
            (root/'etc/portalwrt.conf').write_text("PORTAL_THEME_BG_URL='https://example.test/background'\n")
            # Mocks perform no networking; sample is a PNG signature + payload.
            scripts = {
                'wget': '#!/usr/bin/env python3\nimport sys,os\nfrom pathlib import Path\np=Path(os.environ["PORTAL_TEST_ROOT"]); (p/"downloaded").touch()\nif (p/"offline").exists(): sys.exit(1)\nPath(sys.argv[sys.argv.index("-O")+1]).write_bytes(bytes.fromhex("89504e470d0a1a0a")+b"fixture")\n',
                'hexdump': '#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\nprint(Path(sys.argv[-1]).read_bytes()[:8].hex())\n',
                'logger': '#!/bin/sh\nexit 0\n',
            }
            for name, content in scripts.items():
                p=root/'bin'/name; p.write_text(content); p.chmod(0o755)
            env={**os.environ, 'PORTAL_TEST_ROOT': str(root), 'PATH': str(root/'bin')+':'+os.environ['PATH']}
            command=['sh', str(ROOT/'files/usr/libexec/portal-background')]
            def run():
                p=subprocess.run(command, env=env, capture_output=True, text=True)
                self.assertEqual(p.returncode, 0, p.stderr)
            run()  # first install/download
            targets=[root/'www'/p for p in ('luci-static/argon/img/bg1.jpg','luci-static/kucat/img/bg1.jpg','luci-static/resources/background/portal.jpg')]
            original=targets[0].read_bytes()
            self.assertTrue(all(p.read_bytes()==original for p in targets))
            (root/'offline').touch(); (root/'downloaded').unlink()
            targets[0].write_bytes(b'package update overwrote image'); targets[1].unlink()
            run()  # offline reboot/package upgrade, URL unchanged
            self.assertTrue(all(p.read_bytes()==original for p in targets))
            self.assertFalse((root/'downloaded').exists())
            mtimes=[p.stat().st_mtime_ns for p in targets]
            run()  # theme switch/periodic reconciliation is idempotent
            self.assertEqual(mtimes,[p.stat().st_mtime_ns for p in targets])
            (root/'etc/portalwrt-background/image').write_bytes(b'corrupt')
            (root/'offline').unlink()
            run()  # corrupt cache does not get trusted solely on URL marker
            self.assertEqual((root/'etc/portalwrt-background/image').read_bytes(),original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
