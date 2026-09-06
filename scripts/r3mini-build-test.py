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


if __name__ == '__main__':
    unittest.main()
