#!/usr/bin/env python3
"""Exercise scheduling, failure handling and timing without firmware compilation."""
import importlib.util
import gzip
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
        buildinfo = next(stage for stage in plan['stages'] if stage['name'] == 'buildinfo')
        self.assertEqual(buildinfo['targets'], ['diffconfig', 'buildversion', 'feedsversion'])
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
            plan = {'resources': {'affinity': sorted(os.sched_getaffinity(0))},
                    'output_dir': str(root / 'isolated-output'),
                    'stages': [stage, {**stage, 'id': 'next'}]}
            environment = {'PATH': str(bindir) + ':' + os.environ['PATH'], 'FAKE_EXIT': '7'}
            with patch.object(runner, 'ROOT', root), patch.object(runner, 'fingerprint', return_value='fixed'), patch.dict(os.environ, environment):
                self.assertEqual(runner.execute(plan, logs, False), 7)
                state = json.loads((logs / 'state.json').read_text())
                self.assertEqual(len(state['attempts']), 1)
                self.assertEqual(state['completed'], [])
                self.assertIn('OUTPUT_DIR=' + plan['output_dir'], state['attempts'][0]['command'])
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

    def test_isolated_buildinfo_overrides_simply_expanded_bin_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.config').write_text('CONFIG_TARGET_BOARD="mediatek"\n'
                                         'CONFIG_TARGET_SUBTARGET="filogic"\n')
            bindir = root / 'bin'; bindir.mkdir()
            make = bindir / 'make'
            make.write_text('#!/bin/sh\nexit 0\n')
            make.chmod(0o755)
            output = root / 'isolated-output'
            logs = root / 'logs'; logs.mkdir()
            stage = {'id': 'buildinfo', 'name': 'buildinfo', 'class': 'images', 'jobs': 1,
                     'targets': ['diffconfig', 'buildversion', 'feedsversion'],
                     'output_dir': str(output)}
            environment = {'PATH': str(bindir) + ':' + os.environ['PATH']}
            with patch.object(runner, 'ROOT', root), patch.dict(os.environ, environment):
                row = runner.run_stage(stage, logs, sorted(os.sched_getaffinity(0)))
            self.assertEqual(row['exit_code'], 0)
            self.assertIn('OUTPUT_DIR=' + str(output), row['command'])
            self.assertIn('BIN_DIR=' + str(output / 'targets/mediatek/filogic'), row['command'])

    def test_image_stage_requires_r3mini_host_flash_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / '.config').write_text('CONFIG_TARGET_BOARD="mediatek"\n'
                                         'CONFIG_TARGET_SUBTARGET="filogic"\n')
            output = root / 'isolated-output'
            with patch.object(runner, 'ROOT', root):
                errors = runner.validate_artifacts('images', output_dir=str(output))
                self.assertEqual(errors, ['Expected one compressed R3 Mini eMMC host-flash image, found 0'])
                directory = output / 'targets/mediatek/filogic'; directory.mkdir(parents=True)
                image = directory / 'portalwrt-test-bananapi_bpi-r3-mini-emmc.img.gz'
                fip = directory / 'portalwrt-test-bananapi_bpi-r3-mini-emmc-bl31-uboot.fip'
                fip.write_bytes(b'test-fip')
                def pad(stream, amount):
                    while amount:
                        chunk = min(amount, 1024 * 1024)
                        stream.write(b'\0' * chunk)
                        amount -= chunk
                with image.open('wb') as compressed:
                    with gzip.GzipFile(filename='', mode='wb', fileobj=compressed, mtime=0) as stream:
                        stream.write(b'\0' * 512 + b'EFI PART')
                        pad(stream, 6656 * 1024 - 520)
                        stream.write(fip.read_bytes())
                        pad(stream, 64 * 1024 * 1024 - 6656 * 1024 - fip.stat().st_size)
                        stream.write(b'\xd0\r\xfe\xed')
                self.assertEqual(runner.validate_artifacts('images', output_dir=str(output)), [])
                output.rename(root / 'bin')
                image = root / 'bin/targets/mediatek/filogic' / image.name
                self.assertEqual(runner.validate_artifacts('images'), [])
                image.write_bytes(b'not-gzip')
                self.assertEqual(runner.validate_artifacts('images'),
                                 ['R3 Mini eMMC host-flash image is not valid gzip data'])

    def test_r3mini_image_recipe_builds_host_flash_at_gpt_offsets(self):
        image_make = (Path(__file__).resolve().parents[1]
                      / 'target/linux/mediatek/image/filogic.mk').read_text()
        block = image_make.split('define Device/bananapi_bpi-r3-mini', 1)[1].split('endef', 1)[0]
        self.assertIn('emmc.img.gz', block)
        self.assertIn('mt798x-gpt emmc | pad-to 6656k', block)
        self.assertIn('mt7986-bl31-uboot bananapi_bpi-r3-mini-emmc', block)
        self.assertIn('pad-to 64M | append-image squashfs-sysupgrade.itb | check-size | gzip', block)

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
