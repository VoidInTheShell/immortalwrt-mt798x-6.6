#!/usr/bin/env python3
"""Prepare the saved full eMMC profile; does not build or flash firmware."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SETUPTOOLS_VERSION = '80.9.0'
SETUPTOOLS_HASH = '062d34222ad13e0cc312a4c02d73f059e86a4acbfbdea8f8f76b28c99f306922'


def host_python():
    destination = ROOT / '.r3mini-host/python'
    wheel = ROOT / f'dl/r3mini-host/setuptools-{SETUPTOOLS_VERSION}-py3-none-any.whl'
    if not wheel.exists():
        wheel.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(f'https://pypi.org/pypi/setuptools/{SETUPTOOLS_VERSION}/json', timeout=30) as response:
            metadata = json.load(response)
        entry = next(x for x in metadata['urls'] if x['filename'] == wheel.name and x['digests']['sha256'] == SETUPTOOLS_HASH)
        with urllib.request.urlopen(entry['url'], timeout=60) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != SETUPTOOLS_HASH:
            raise RuntimeError('Setuptools download hash mismatch')
        wheel.write_bytes(content)
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != SETUPTOOLS_HASH:
        raise RuntimeError('Setuptools cache hash mismatch')
    if not (destination / 'setuptools/__init__.py').exists():
        destination.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(wheel) as archive:
            for member in archive.namelist():
                if not (destination / member).resolve().is_relative_to(destination.resolve()):
                    raise RuntimeError('Unsafe wheel member')
            archive.extractall(destination)
    os.environ['PYTHONPATH'] = str(destination) + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
    python = ROOT / 'staging_dir/host/bin/python3'
    if python.exists():
        subprocess.run([str(python), '-c', 'import setuptools; print("Host setuptools:", setuptools.__version__)'], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bootstrap', action='store_true', help='Fetch missing pinned sources and install their feed links for a fresh checkout')
    parser.add_argument('--restore-config', action='store_true', help='Back up .config and restore the saved full eMMC preset')
    args = parser.parse_args()
    if args.bootstrap:
        subprocess.run([sys.executable, 'scripts/r3mini-sources.py', 'checkout'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'scripts/r3mini-sources.py', 'apply'], cwd=ROOT, check=True)
    host_python()
    if args.bootstrap:
        lock = json.loads((ROOT / 'patches/r3mini-sources/sources.json').read_text())
        feeds = [Path(s['path']).name for s in lock['sources'] if s['path'].startswith('feeds/')]
        # -i only rebuilds indexes: never move a pinned feed to a branch tip.
        subprocess.run(['scripts/feeds', 'update', '-i', *feeds], cwd=ROOT, check=True)
        for feed in feeds:
            subprocess.run(['scripts/feeds', 'install', '-a', '-p', feed], cwd=ROOT, check=True)
    if args.restore_config:
        if (ROOT / '.config').exists():
            content = (ROOT / '.config').read_bytes()
            backup = ROOT / '.portalwrt-backups' / ('before-prepare-' + hashlib.sha256(content).hexdigest()[:12] + '.config')
            backup.parent.mkdir(parents=True, exist_ok=True)
            if not backup.exists(): backup.write_bytes(content)
        shutil.copy2(ROOT / 'defconfig/portalwrt-bpi-r3-mini-full.config', ROOT / '.config')
    # Package additions / removed duplicate BuildPackage statements can change
    # the scan list without changing its cookie. Refresh only derived indexes.
    for pattern in ('.files-packageinfo-*', '.overrides-packageinfo-*'):
        for path in (ROOT / 'tmp/info').glob(pattern):
            path.unlink()
    subprocess.run(['make', 'defconfig'], cwd=ROOT, check=True)
    subprocess.run([sys.executable, 'scripts/r3mini-build.py', 'preflight'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
