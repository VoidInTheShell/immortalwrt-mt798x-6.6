#!/usr/bin/env python3
"""Exercise fresh source recovery and local-work protection with local Git repos."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sources', Path(__file__).with_name('r3mini-sources.py'))
sources = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sources)


class RecoveryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='r3mini-sources-test-')
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.origin = base / 'upstream'
        self.origin.mkdir()
        self.git(self.origin, 'init', '--quiet')
        self.git(self.origin, 'config', 'user.name', 'Source recovery test')
        self.git(self.origin, 'config', 'user.email', 'source-test@example.invalid')
        (self.origin / 'recipe').write_text('upstream\n')
        self.git(self.origin, 'add', 'recipe')
        self.git(self.origin, 'commit', '--quiet', '-m', 'fixture')
        revision = self.git(self.origin, 'rev-parse', 'HEAD').strip()
        (self.origin / 'recipe').write_text('compatible\n')
        patch = self.git(self.origin, 'diff', '--binary').encode()
        sources.ROOT = base / 'workspace'
        sources.DIRECTORY = sources.ROOT / 'patches/r3mini-sources'
        sources.DIRECTORY.mkdir(parents=True)
        sources.LOCK = sources.DIRECTORY / 'sources.json'
        (sources.DIRECTORY / 'fixture.patch').write_bytes(patch)
        self.entry = {'path': 'package/fixture', 'origin': str(self.origin), 'revision': revision,
                      'patch': 'fixture.patch', 'patch_sha256': hashlib.sha256(patch).hexdigest()}
        sources.LOCK.write_text(json.dumps({'sources': [self.entry]}))
        self.repo = sources.ROOT / self.entry['path']

    def git(self, repo, *args):
        return subprocess.check_output(['git', *args], cwd=repo, stderr=subprocess.PIPE).decode()

    def test_fresh_checkout_apply_and_idempotence(self):
        sources.checkout()
        self.assertEqual((self.repo / 'recipe').read_text(), 'upstream\n')
        sources.apply()
        sources.checkout()
        sources.apply()
        self.assertEqual((self.repo / 'recipe').read_text(), 'compatible\n')
        self.assertEqual(self.git(self.repo, 'rev-parse', 'HEAD').strip(), self.entry['revision'])

    def test_existing_nonrepo_or_local_conflict_is_preserved(self):
        self.repo.mkdir(parents=True)
        (self.repo / 'personal').write_text('keep me\n')
        with self.assertRaisesRegex(RuntimeError, 'Missing source checkout'):
            sources.checkout()
        self.assertEqual((self.repo / 'personal').read_text(), 'keep me\n')
        (self.repo / 'personal').unlink()
        self.repo.rmdir()
        sources.checkout()
        (self.repo / 'recipe').write_text('local work\n')
        with self.assertRaisesRegex(RuntimeError, 'conflicts'):
            sources.apply()
        self.assertEqual((self.repo / 'recipe').read_text(), 'local work\n')

    def test_wrong_revision_is_rejected(self):
        sources.checkout()
        self.entry['revision'] = '0' * 40
        sources.LOCK.write_text(json.dumps({'sources': [self.entry]}))
        with self.assertRaisesRegex(RuntimeError, 'Source revision changed'):
            sources.checkout()

    def test_hash_and_failed_fetch_do_not_publish_partial_source(self):
        (sources.DIRECTORY / 'fixture.patch').write_text('damaged')
        with self.assertRaisesRegex(RuntimeError, 'Changed patch'):
            sources.checkout()
        self.assertFalse(self.repo.exists())
        (sources.DIRECTORY / 'fixture.patch').write_bytes(b'')
        self.entry.update(patch_sha256=hashlib.sha256(b'').hexdigest(), revision='0' * 40)
        sources.LOCK.write_text(json.dumps({'sources': [self.entry]}))
        with self.assertRaises(subprocess.CalledProcessError):
            sources.checkout()
        self.assertFalse(self.repo.exists())
        self.assertEqual(list(self.repo.parent.glob('.r3mini-source-*')), [])


if __name__ == '__main__':
    unittest.main()
