#!/usr/bin/env python3
"""Exercise offload rollback with mocked UCI/sysfs; never invoke router services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'package/qosmate/etc/init.d/qosmate'


class OffloadTests(unittest.TestCase):
    def test_disabled_stop_and_reload_do_not_remove_foreign_queues(self):
        source = SOURCE.read_text()
        stop = source[source.index('stop_service() {'):source.index('shutdown() {')]
        reload = source[source.index('reload_service() {'):source.index('# 1 - speedtest command')]
        with tempfile.TemporaryDirectory() as temp:
            stop = stop.replace('/tmp/qosmate_wan', temp + '/no-owned-wan')
            prelude = '''
restore_offload_state() { echo recovered; }
disable() { :; }
uci() { case "$*" in *get*) echo 0;; esac; }
restart() { echo unexpected-restart; exit 99; }
nft() { echo unexpected-nft; exit 99; }
tc() { echo unexpected-tc; exit 99; }
ip() { echo unexpected-ip; exit 99; }
'''
            for action in ['stop_service', 'reload_service']:
                result = subprocess.run(['sh', '-c', prelude + stop + reload + '\n' + action],
                                        check=True, text=True, capture_output=True)
                self.assertEqual(result.stdout.strip(), 'recovered')
                self.assertEqual(result.stderr, '')

    def test_persistent_rollback_and_user_choice(self):
        source = SOURCE.read_text()
        functions = source[source.index('hnat_hook_number() {'):source.index('create_hotplug_script() {')]
        self.assertIn('QOSMATE_OFFLOAD_STATE_DIR=${QOSMATE_D}/offload-state', source)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'bin').mkdir(); (root / 'hnat').mkdir()
            hook = root / 'hnat/hook_toggle'; hook.write_text('enabled\n')
            (root / 'hnat/hnat_setting').touch()
            uci = root / 'bin/uci'
            uci.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
p=Path(os.environ['MOCK_UCI']); d=json.loads(p.read_text()); a=[x for x in sys.argv[1:] if x!='-q']
op=a[0]
if op in ('get','show'):
 k=a[1]
 if op=='show' and any(x.startswith(k+'.') for x in d): print(k); sys.exit(0)
 if k not in d: sys.exit(1)
 print(d[k])
elif op=='set':
 k,v=a[1].split('=',1); d[k]=v; p.write_text(json.dumps(d))
elif op in ('delete','del'):
 d.pop(a[1],None); p.write_text(json.dumps(d))
elif op=='commit': pass
else: sys.exit(1)
''')
            uci.chmod(0o755)
            initial = {'firewall.@defaults[0].flow_offloading': '1',
                       'firewall.@defaults[0].flow_offloading_hw': '0',
                       'turboacc.config.fastpath': 'mediatek_hnat',
                       'turboacc.config.fastpath_mh_eth_hnat': '1',
                       'turboacc.config.fastpath_mh_eth_hnat_v6': '1'}
            db = root / 'uci.json'; db.write_text(json.dumps(initial))
            functions = functions.replace('/sys/kernel/debug/hnat', str(root / 'hnat'))
            functions = functions.replace('/etc/init.d/firewall reload', ': mock-firewall-reload')
            prelude = f"QOSMATE_OFFLOAD_STATE_DIR='{root}/persistent/offload'\ntry_mkdir() {{ mkdir \"$@\"; }}\nsync() {{ :; }}\n"
            script = root / 'functions.sh'; script.write_text(prelude + functions)
            env = {**os.environ, 'PATH': str(root / 'bin') + ':' + os.environ['PATH'], 'MOCK_UCI': str(db)}
            def run(action):
                subprocess.run(['sh', '-c', '. "$1"; ' + action, 'test', str(script)], env=env, check=True)
            run('prepare_offload_state')
            self.assertEqual(hook.read_text().strip(), '0')
            self.assertEqual(json.loads(db.read_text())['turboacc.config.fastpath'], 'disabled')
            self.assertTrue((root / 'persistent/offload/prepared').exists())
            # A hard reboot can recreate an enabled hardware hook while the
            # persistent snapshot remains. Preparing again must not overwrite it.
            hook.write_text('enabled\n')
            run('prepare_offload_state')
            self.assertEqual(hook.read_text().strip(), '0')
            # A fresh shell simulates losing volatile process state; debugfs
            # returns textual values, unlike a regular writable file.
            hook.write_text('disabled\n')
            run('restore_offload_state')
            self.assertEqual(json.loads(db.read_text()), initial)
            self.assertEqual(hook.read_text().strip(), '1')
            self.assertFalse((root / 'persistent/offload').exists())
            run('prepare_offload_state')
            changed = json.loads(db.read_text()); changed['turboacc.config.fastpath'] = 'user-custom'
            db.write_text(json.dumps(changed)); hook.write_text('disabled\n')
            run('restore_offload_state')
            self.assertEqual(json.loads(db.read_text())['turboacc.config.fastpath'], 'user-custom')
            self.assertEqual(hook.read_text().strip(), 'disabled')


if __name__ == '__main__':
    unittest.main()
