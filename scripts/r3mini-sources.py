#!/usr/bin/env python3
"""Restore pinned sources and local patches without resetting existing work."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / 'patches/r3mini-sources'
LOCK = DIRECTORY / 'sources.json'


def git(repo, *args, check=True):
    return subprocess.run(['git', *args], cwd=repo, capture_output=True, check=check)


def sources():
    data = json.loads(LOCK.read_text())
    for source in data['sources']:
        repo = ROOT / source['path']
        patch = DIRECTORY / source['patch']
        if not repo.resolve().is_relative_to(ROOT.resolve()) or repo.resolve() == ROOT.resolve():
            raise RuntimeError('Source path escapes workspace: ' + source['path'])
        if not patch.resolve().is_relative_to(DIRECTORY.resolve()):
            raise RuntimeError('Patch path escapes lock directory: ' + source['patch'])
        if hashlib.sha256(patch.read_bytes()).hexdigest() != source['patch_sha256']:
            raise RuntimeError('Changed patch: ' + str(patch))
    return data['sources']


def check_revision(repo, source):
    if not (repo / '.git').exists():
        raise RuntimeError('Missing source checkout: ' + source['path'] +
                           '; run scripts/r3mini-sources.py checkout first')
    revision = git(repo, 'rev-parse', 'HEAD').stdout.decode().strip()
    if revision != source['revision']:
        raise RuntimeError('Source revision changed; review/rebase compatibility patches and refresh the lock: '
                           + source['path'] + '\nexpected ' + source['revision'] + '\nactual ' + revision)


def checkout():
    """Fetch only missing checkouts, using exact revisions and atomic publication."""
    entries = sources()
    # Refuse unexpected existing trees before doing any downloads.
    for source in entries:
        repo = ROOT / source['path']
        if repo.exists() or repo.is_symlink():
            check_revision(repo, source)
    for source in entries:
        repo = ROOT / source['path']
        if repo.exists():
            print('Checkout present: ' + source['path']); continue
        repo.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix='.r3mini-source-', dir=repo.parent))
        try:
            git(temporary, 'init', '--quiet')
            git(temporary, 'remote', 'add', 'origin', source['origin'])
            git(temporary, 'fetch', '--depth=1', 'origin', source['revision'])
            git(temporary, 'checkout', '--quiet', '--detach', 'FETCH_HEAD')
            check_revision(temporary, source)
            temporary.rename(repo)
            print('Restored checkout: ' + source['path'])
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)


def snapshot():
    spec = importlib.util.spec_from_file_location('build', ROOT / 'scripts/r3mini-build.py')
    build = importlib.util.module_from_spec(spec); spec.loader.exec_module(build)
    repositories = set()
    for node in build.evaluate_graph():
        recipe = ROOT / build.classify(node)['recipe']
        for parent in recipe.resolve().parents:
            if (parent / '.git').exists():
                if parent != ROOT:
                    repositories.add(parent)
                break
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    result = {'root_revision': git(ROOT, 'rev-parse', 'HEAD').stdout.decode().strip(), 'sources': []}
    for repo in sorted(repositories):
        rel = str(repo.relative_to(ROOT))
        patchname = rel.replace('/', '-') + '.patch'
        data = git(repo, 'diff', 'HEAD', '--binary').stdout
        names = git(repo, 'ls-files', '--others', '--exclude-standard', '-z').stdout.decode().split('\0')
        for name in sorted(filter(None, names)):
            if (repo / name).is_file():
                change = git(repo, 'diff', '--no-index', '--binary', '--', '/dev/null', name, check=False)
                if change.returncode not in (0, 1):
                    raise RuntimeError(change.stderr.decode())
                data += change.stdout
        (DIRECTORY / patchname).write_bytes(data)
        result['sources'].append({'path': rel,
            'origin': git(repo, 'remote', 'get-url', 'origin').stdout.decode().strip(),
            'revision': git(repo, 'rev-parse', 'HEAD').stdout.decode().strip(),
            'patch': patchname, 'patch_sha256': hashlib.sha256(data).hexdigest()})
    LOCK.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(f'Snapshotted {len(repositories)} selected source repositories: {LOCK}')


def apply():
    entries = sources()
    for source in entries:
        check_revision(ROOT / source['path'], source)
    for source in entries:
        repo = ROOT / source['path']
        patch = DIRECTORY / source['patch']
        content = patch.read_bytes()
        if not content:
            continue
        if git(repo, 'apply', '--reverse', '--check', str(patch), check=False).returncode == 0:
            print('Already applied: ' + source['path']); continue
        check = git(repo, 'apply', '--check', str(patch), check=False)
        if check.returncode:
            raise RuntimeError('Patch conflicts with current source; inspect instead of overwriting: '
                               + source['path'] + '\n' + check.stderr.decode())
        git(repo, 'apply', str(patch))
        print('Applied: ' + source['path'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'checkout', 'apply'])
    args = parser.parse_args()
    try:
        {'snapshot': snapshot, 'checkout': checkout, 'apply': apply}[args.action]()
    except (RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode(), file=sys.stderr)
        raise SystemExit(1)
