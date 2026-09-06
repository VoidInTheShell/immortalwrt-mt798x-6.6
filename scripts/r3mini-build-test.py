#!/usr/bin/env python3
"""Exercise scheduling, failure handling and timing without firmware compilation."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('r3mini-build.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class BuildPlanTests(unittest.TestCase):
    def test_dependencies_finish_before_heavy_and_light_consumers(self):
        graph = {'base': set(), 'go': {'base'}, 'ui': {'go'}, 'lib': {'base'}}
        with patch.object(runner, 'classify', side_effect=lambda n: {'class': 'go' if n == 'go' else 'light'}):
            stages = runner.package_stages(graph, {'light': 24, 'go': 8})
        done = set()
        for stage in stages:
            for node in stage['targets']:
                self.assertTrue(graph[node] <= done)
            if 'go' in stage['targets']:
                self.assertEqual(stage['targets'], ['go'])
                self.assertEqual(stage['jobs'], 8)
            done.update(stage['targets'])
        self.assertEqual(done, set(graph))

    def test_dependency_cycle_stops_planning(self):
        with self.assertRaisesRegex(RuntimeError, 'cycle'):
            runner.package_stages({'a': {'b'}, 'b': {'a'}}, {'light': 24})

    def test_real_metadata_and_classification(self):
        graph = runner.evaluate_graph()
        dae = graph['package/feeds/packages/daed/compile']
        self.assertIn('package/feeds/packages/golang/host/compile', dae)
        self.assertIn('package/kernel/bpf-headers/compile', dae)
        self.assertEqual(runner.classify('package/boot/arm-trusted-firmware-mediatek/compile')['class'], 'light')
        self.assertEqual(runner.classify('package/feeds/packages/rust/host/compile')['class'], 'rust-host')
        plan = runner.make_plan()
        done = set()
        for stage in plan['stages']:
            for node in stage['targets']:
                if node in graph:
                    self.assertTrue(graph[node] <= done, node)
            done.update(stage['targets'])
        self.assertTrue(set(graph) <= done)

    def test_make_failure_timing_and_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bindir = root / 'bin'; bindir.mkdir()
            make = bindir / 'make'
            make.write_text('#!/bin/sh\necho "time: example/compile#1.2#0.3#0.7"\nexit "${FAKE_EXIT:-0}"\n')
            make.chmod(0o755)
            logs = root / 'logs'; logs.mkdir()
            stage = {'id': 'test', 'name': 'test', 'class': 'light', 'jobs': 1, 'targets': ['example/compile']}
            plan = {'resources': {'affinity': sorted(os.sched_getaffinity(0))}, 'stages': [stage, {**stage, 'id': 'next'}]}
            environment = {'PATH': str(bindir) + ':' + os.environ['PATH'], 'FAKE_EXIT': '7'}
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'fingerprint', return_value='fixed'), patch.dict(os.environ, environment):
                self.assertEqual(runner.execute(plan, logs, False), 7)
                state = json.loads((logs / 'state.json').read_text())
                self.assertEqual(len(state['attempts']), 1)
                self.assertEqual(state['completed'], [])
                self.assertIn('example/compile', (logs / 'component-times.csv').read_text())
                os.environ['FAKE_EXIT'] = '0'
                refreshed_plan = {**plan, 'stages': [{**s, 'jobs': 2} for s in plan['stages']]}
                self.assertEqual(runner.execute(refreshed_plan, logs, True), 0)
                state = json.loads((logs / 'state.json').read_text())
                self.assertEqual(state['completed'], ['test', 'next'])
                self.assertEqual(state['attempts'][1]['jobs'], 1)
                self.assertNotEqual(state['attempts'][0]['log'], state['attempts'][1]['log'])
                self.assertTrue(Path(state['attempts'][0]['log']).exists())
                with patch.object(runner, 'fingerprint', return_value='changed'):
                    with self.assertRaisesRegex(RuntimeError, 'changed'):
                        runner.execute(plan, logs, True)

    def test_build_environment_removes_wsl_windows_path_fragments(self):
        with patch.dict(os.environ, {'PATH': '/usr/bin:/mnt/c/Program:Files:(x86)/Git:/home/test/bin:C:\\Tools\\bin'}):
            environment = runner.build_environment()
        self.assertEqual(environment['PATH'], '/usr/bin:/home/test/bin')

    def test_prior_successful_stages_enable_warm_reuse_only_for_matching_layout(self):
        with tempfile.TemporaryDirectory() as temp:
            logs = Path(temp) / 'logs'; logs.mkdir()
            old = logs / 'r3mini-build-old'; old.mkdir()
            stage = {'id': 'warm', 'name': 'packages-light', 'class': 'light',
                     'targets': ['package/example/compile']}
            plan = {'config_sha256': 'same', 'stages': [stage]}
            (old / 'plan.json').write_text(json.dumps(plan))
            (old / 'state.json').write_text(json.dumps({'completed': ['warm']}))
            current = logs / 'r3mini-build-new'
            self.assertEqual(runner.prior_successful_stage_ids(current, plan), {'warm'})
            mismatched = {**plan, 'stages': [{**stage, 'targets': ['package/other/compile']}]}
            self.assertEqual(runner.prior_successful_stage_ids(current, mismatched), set())

    def test_warm_reuse_jobs_prefer_24_with_resource_fallback(self):
        self.assertEqual(runner.rerun_jobs({'cpus': 24, 'caps': {'light': 24}}), 24)
        self.assertEqual(runner.rerun_jobs({'cpus': 8, 'caps': {'light': 8}}), 8)

    def test_calibration_fix_preserves_only_unaffected_warm_stages(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = root / 'logs/r3mini-build-old'; old.mkdir(parents=True)
            base = b'CONFIG_MTK_CHIP_MT7986=y\nCONFIG_PACKAGE_kmod-mt_wifi=y\n'
            previous = base + b'CONFIG_MTK_PRE_CAL_TRX_SET1_SUPPORT=y\n'
            (root / '.config').write_bytes(base)
            stages = [{'id': name, 'name': name, 'class': 'light', 'targets': [target]}
                      for name, target in [('before', 'tools/install'), ('wifi', runner.WIFI_TARGET),
                                           ('after', 'package/install')]]
            old_plan = {'config_sha256': runner.digest(previous), 'stages': stages}
            (old / 'plan.json').write_text(json.dumps(old_plan))
            (old / 'state.json').write_text(json.dumps({'completed': ['before', 'wifi', 'after']}))
            (old / 'config.snapshot').write_bytes(previous)
            plan = {**old_plan, 'config_sha256': runner.digest(base)}
            with patch.object(runner, 'ROOT', root):
                self.assertEqual(runner.prior_successful_stage_ids(root / 'logs/new', plan), {'before'})
                (old / 'config.snapshot').write_bytes(base)  # A stale/tampered snapshot is rejected.
                self.assertEqual(runner.prior_successful_stage_ids(root / 'logs/new', plan), set())
            self.assertFalse(runner.calibration_only_change(previous, base + b'CONFIG_PACKAGE_daed=y\n'))
            self.assertFalse(runner.calibration_only_change(previous, base.replace(b'MT7986', b'MT7981')))


if __name__ == '__main__':
    unittest.main()
