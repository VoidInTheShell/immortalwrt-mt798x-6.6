#!/usr/bin/env python3
"""Plan, download and run the R3 Mini build with bounded parallelism and timing.

No compilation is performed by `plan`. `build` is the explicit compile action.
The package DAG is evaluated by GNU make from OpenWrt's generated metadata.
"""
import argparse
import csv
import datetime as dt
import hashlib
import functools
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'logs/r3mini-build'
TIME_RE = re.compile(r'time: (.+)#([\d.]+)#([\d.]+)#([\d.]+)')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def config():
    return dict(re.findall(r'^(CONFIG_[^=]+)=(.*)$', (ROOT / '.config').read_text(), re.M))


def resources():
    affinity = sorted(os.sched_getaffinity(0))
    mem = {k: int(v) * 1024 for k, v in re.findall(r'^(\w+):\s+(\d+) kB', Path('/proc/meminfo').read_text(), re.M)}
    available = mem['MemAvailable']
    total = mem['MemTotal']
    cpus = len(affinity)
    # cgroup v2 limits can be lower than /proc's host totals.
    cgroup_path = next((l[3:] for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::')), '/')
    cg = Path('/sys/fs/cgroup') / cgroup_path.lstrip('/')
    for parent in [cg, *cg.parents]:
        if not str(parent).startswith('/sys/fs/cgroup'):
            break
        try:
            maximum = (parent / 'memory.max').read_text().strip()
            if maximum != 'max':
                total = min(total, int(maximum))
                available = min(available, int(maximum) - int((parent / 'memory.current').read_text()))
            quota, period = (parent / 'cpu.max').read_text().split()
            if quota != 'max':
                cpus = min(cpus, max(1, math.floor(int(quota) / int(period))))
        except (OSError, ValueError):
            pass
    budget_gib = max(0, available / 2**30 - 4)
    def cap(max_jobs, gib_per_job):
        return max(1, min(cpus, max_jobs, math.floor(budget_gib / gib_per_job)))
    caps = {'light': cap(cpus, .55), 'kernel': cap(cpus, .6),
            'toolchain': cap(12, 1.25), 'go': cap(8, 1.5),
            'rust': cap(4, 3), 'rust-host': cap(2, 4),
            'chromium': cap(6, 3), 'cpp': cap(8, 1.5), 'mtk': cap(8, 1),
            'images': cap(4, 2), 'download': min(8, cpus)}
    return {'cpus': cpus, 'affinity': affinity, 'memory_total': total,
            'memory_available': available, 'disk_available': shutil.disk_usage(ROOT).free,
            'reserve_gib': 4, 'caps': caps}


def evaluate_graph():
    deps = (ROOT / 'tmp/.packagedeps').read_text()
    names = sorted(set(re.findall(r'^(\$\(curdir\)/\S+/compile)\s*\+=', deps, re.M)))
    script = 'include .config\ncurdir:=package\ninclude tmp/.packagedeps\n'
    script += '$(info SELECTED $(sort $(package-y) $(package-m)))\n'
    script += '\n'.join('$(info GRAPH ' + n + ' $('+n+'))' for n in names)
    script += '\n.PHONY: audit\naudit:\n\t@:\n'
    proc = subprocess.run(['make', '-rR', '--no-print-directory', '-f', '-', 'audit'],
                          cwd=ROOT, input=script, text=True, capture_output=True, check=True)
    graph, selected = {}, []
    for line in proc.stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == 'SELECTED':
            selected = ['package/' + p + '/compile' for p in fields[1:]]
        elif fields and fields[0] == 'GRAPH':
            graph[fields[1]] = set(fields[2:])
    if not selected:
        raise RuntimeError('No selected package targets in generated metadata')
    needed = set()
    def visit(node):
        if node in needed:
            return
        if not re.fullmatch(r'package/[\w.+/-]+/compile', node):
            raise RuntimeError('Unexpected dependency target: ' + node)
        needed.add(node)
        for dependency in graph.get(node, ()):
            visit(dependency)
    for node in selected:
        visit(node)
    return {node: graph.get(node, set()) for node in sorted(needed)}


def classify(node):
    directory = node.removeprefix('package/').removesuffix('/compile').removesuffix('/host')
    recipe = ROOT / 'package' / directory / 'Makefile'
    text = recipe.read_text() if recipe.exists() else ''
    name = Path(directory).name.lower()
    host = '/host/' in node
    parallel_flag = 'HOST_BUILD_PARALLEL' if host else 'PKG_BUILD_PARALLEL'
    match = re.search(r'^' + parallel_flag + r'\s*:?=\s*([^\n]+)', text, re.M)
    internal = match.group(1).strip() if match else 'upstream default (serial unless framework changes it)'
    if name == 'rust' and host:
        kind = 'rust-host'
    elif 'naiveproxy' in name or 'chromium' in name:
        kind = 'chromium'
    elif name == 'rust' or name.startswith('rust-') or name.endswith('-rust') or 'rust-package.mk' in text or 'cargo ' in text:
        kind = 'rust'
    elif 'golang' in name or 'golang-package.mk' in text or 'golang-host.mk' in text:
        kind = 'go'
    elif name in {'samba4', 'boost', 'icu', 'qtbase', 'llvm', 'clang', 'protobuf', 'webkitgtk', 'nmap'}:
        kind = 'cpp'
    elif '/mtk/drivers/' in node:
        kind = 'mtk'
    else:
        kind = 'light'
    return {'class': kind, 'upstream_parallel': internal,
            'recipe': str(recipe.relative_to(ROOT)), 'host': host}


def package_stages(graph, caps):
    pending = set(graph)
    done, result = set(), []
    while pending:
        ready = sorted(n for n in pending if graph[n] <= done)
        if not ready:
            raise RuntimeError('Dependency cycle: ' + ', '.join(sorted(pending)[:20]))
        light = [n for n in ready if classify(n)['class'] == 'light']
        targets = light[:48] if light else ready[:1]
        kind = classify(targets[0])['class']
        result.append({'name': 'packages-' + kind, 'class': kind,
                       'jobs': caps[kind], 'targets': targets})
        done.update(targets)
        pending.difference_update(targets)
    return result


def make_plan():
    res = resources()
    graph = evaluate_graph()
    stages = [{'name': 'tools', 'class': 'light', 'jobs': res['caps']['light'], 'targets': ['tools/install']},
              {'name': 'toolchain', 'class': 'toolchain', 'jobs': res['caps']['toolchain'], 'targets': ['toolchain/install']},
              {'name': 'kernel', 'class': 'kernel', 'jobs': res['caps']['kernel'], 'targets': ['target/compile']}]
    stages += package_stages(graph, res['caps'])
    stages += [{'name': 'package-completion', 'class': 'light', 'jobs': res['caps']['light'], 'targets': ['package/compile']},
               {'name': 'package-install', 'class': 'images', 'jobs': 1, 'targets': ['package/install']},
               {'name': 'images', 'class': 'images', 'jobs': res['caps']['images'], 'targets': ['target/install']},
               {'name': 'buildinfo', 'class': 'images', 'jobs': 1, 'targets': ['buildinfo']},
               {'name': 'index', 'class': 'images', 'jobs': res['caps']['images'], 'targets': ['package/index']},
               {'name': 'overview', 'class': 'images', 'jobs': 1, 'targets': ['json_overview_image_info']},
               {'name': 'checksum', 'class': 'images', 'jobs': 1, 'targets': ['checksum']}]
    for i, stage in enumerate(stages, 1):
        stage['id'] = f'{i:04d}-' + stage['name'] + '-' + digest(' '.join(stage['targets']).encode())[:8]
    return {'resources': res, 'stages': stages,
            'components': {n: {**classify(n), 'dependencies': sorted(ds)} for n, ds in graph.items()}}


def fingerprint(plan):
    h = hashlib.sha256((ROOT / '.config').read_bytes())
    h.update(json.dumps(plan['stages'], sort_keys=True).encode())
    # Include selected recipes, source revisions and all tracked local patches.
    # For untracked packages include their nested git diff, not just the recipe.
    repos = {ROOT}
    for info in plan['components'].values():
        path = ROOT / info['recipe']
        if path.exists():
            h.update(path.read_bytes())
            for parent in path.resolve().parents:
                if (parent / '.git').exists():
                    repos.add(parent)
                    break
    for repo in sorted(repos):
        for cmd in (['git', 'rev-parse', 'HEAD'], ['git', 'diff', 'HEAD', '--binary']):
            p = subprocess.run(cmd, cwd=repo, capture_output=True, check=True)
            h.update(str(repo.relative_to(ROOT)).encode() if repo.is_relative_to(ROOT) else str(repo).encode())
            h.update(p.stdout)
        untracked = subprocess.run(['git', 'ls-files', '--others', '--exclude-standard', '-z'],
                                   cwd=repo, capture_output=True, check=True).stdout.decode().split('\0')
        for name in sorted(filter(None, untracked)):
            if repo == ROOT and not name.startswith(('package/', 'target/', 'scripts/r3mini', 'files/', 'patches/')):
                continue
            path = repo / name
            if path.is_file():
                h.update(name.encode()); h.update(path.read_bytes())
    for directory in ('files', 'package/r3mini-defaults', 'patches/r3mini', 'patches/r3mini-local'):
        for path in sorted((ROOT / directory).rglob('*')):
            if path.is_file():
                h.update(str(path.relative_to(ROOT)).encode()); h.update(path.read_bytes())
    return h.hexdigest()


def validate_config():
    cfg = config()
    required = {'CONFIG_TARGET_mediatek_filogic_DEVICE_bananapi_bpi-r3-mini': 'y',
                'CONFIG_R3MINI_FULL_EMMC': 'y', 'CONFIG_TARGET_ROOTFS_PARTSIZE': '2048',
                'CONFIG_PACKAGE_modemmanager': 'y', 'CONFIG_PACKAGE_modemmanager-rpcd': 'y',
                'CONFIG_PACKAGE_luci-proto-modemmanager': 'y',
                'CONFIG_PACKAGE_luci-app-mmconfig': 'y', 'CONFIG_PACKAGE_luci-app-sms-manager': 'y',
                'CONFIG_PACKAGE_luci-mod-network': 'y', 'CONFIG_PACKAGE_luci-mod-status': 'y',
                'CONFIG_PACKAGE_kmod-mediatek_hnat': 'y', 'CONFIG_PACKAGE_kmod-warp': 'y',
                'CONFIG_PACKAGE_kmod-mt_wifi': 'y', 'CONFIG_PACKAGE_luci-app-turboacc-mtk': 'y',
                'CONFIG_PACKAGE_daed': 'y', 'CONFIG_BPF_TOOLCHAIN_HOST': 'y',
                'CONFIG_KERNEL_DEBUG_INFO_BTF': 'y', 'CONFIG_VERSION_DIST': '"PortalWRT"'}
    errors = [f'{k}: expected {v}, got {cfg.get(k, "n")}' for k, v in required.items() if cfg.get(k) != v]
    forbidden = {'node', 'ts-node', 'dns-over-https', 'luci-app-athena-led', 'UAmask', 'ua3f',
                 'daed-next', 'luci-app-daed-next', 'luci-app-modem', 'qmodem', 'quectel-cm',
                 'quectel-CM-5G', 'quectel-CM-5G-M', 'nginx', 'nginx-ssl'}
    for symbol, value in cfg.items():
        package = symbol.removeprefix('CONFIG_PACKAGE_')
        if value in ('y', 'm') and (package in forbidden or package.startswith('node-')):
            errors.append('Forbidden target package: ' + package)
    if cfg.get('CONFIG_TARGET_ROOTFS_INITRAMFS') == 'y':
        errors.append('Full eMMC profile must not build a full-feature 32 MiB recovery image')
    return errors


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def save_plan(logdir, plan):
    save_json(logdir / 'plan.json', plan)
    with (logdir / 'component-jobs.csv').open('w') as handle:
        fields = ['stage', 'target', 'class', 'jobs', 'upstream_parallel', 'recipe', 'dependencies']
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for stage in plan['stages']:
            for target in stage['targets']:
                info = plan.get('components', {}).get(target, {})
                writer.writerow({'stage': stage['id'], 'target': target, 'class': stage['class'],
                                 'jobs': stage['jobs'], 'upstream_parallel': info.get('upstream_parallel', 'framework'),
                                 'recipe': info.get('recipe', ''), 'dependencies': ' '.join(info.get('dependencies', []))})


def memory_group(pgid):
    """Sample sum of RSS for the complete build process group (shared pages count twice)."""
    rss = 0
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[2]) == pgid:
                rss += int(fields[21]) * os.sysconf('SC_PAGE_SIZE')
        except (OSError, ValueError, IndexError):
            pass
    return rss


def validate_artifacts(stage_name):
    """Check actual build outputs before advancing to the next expensive stage."""
    if stage_name == 'kernel':
        paths = list((ROOT / 'build_dir').glob('target-*/linux-mediatek_filogic/linux-6.6.*/.config'))
        if len(paths) != 1:
            return ['Expected one generated R3 Mini kernel .config, found ' + str(len(paths))]
        cfg = dict(re.findall(r'^(CONFIG_[^=]+)=(.*)$', paths[0].read_text(), re.M))
        builtins = ('BPF BPF_SYSCALL BPF_JIT CGROUPS CGROUP_BPF DEBUG_INFO_BTF BPF_EVENTS '
                    'BPF_STREAM_PARSER XDP_SOCKETS NET_CLS_ACT USB_SERIAL_GENERIC NET_DEVLINK RELAY').split()
        modules = ('NET_MEDIATEK_HNAT NET_CLS_BPF NET_ACT_BPF NET_SCH_INGRESS '
                   'WWAN MHI_BUS MHI_BUS_PCI_GENERIC MHI_NET MHI_WWAN_CTRL MHI_WWAN_MBIM '
                   'MTK_T7XX IOSM QRTR QRTR_MHI USB_SERIAL_OPTION USB_SERIAL_QUALCOMM '
                   'USB_SERIAL_SIERRAWIRELESS USB_SERIAL_IPW USB_SERIAL_TI USB_HSO '
                   'USB_NET_KALMIA USB_NET_QMI_WWAN USB_NET_CDC_MBIM').split()
        errors = [f'Generated kernel lacks CONFIG_{name}=y' for name in builtins if cfg.get('CONFIG_' + name) != 'y']
        errors += [f'Generated kernel lacks CONFIG_{name}=y/m' for name in modules if cfg.get('CONFIG_' + name) not in ('y', 'm')]
        return errors
    if stage_name == 'package-install':
        roots = list((ROOT / 'build_dir').glob('target-*/root-mediatek'))
        if len(roots) != 1:
            return ['Expected one populated root-mediatek filesystem, found ' + str(len(roots))]
        rootfs = roots[0]
        required = ['lib/modules/*/mtkhnat.ko*', 'lib/modules/*/mt_wifi.ko*',
                    'lib/modules/*/mtk_warp.ko*', 'lib/modules/*/conninfra.ko*',
                    'lib/firmware/7986_WOCPU0_RAM_CODE_release.bin',
                    'lib/firmware/7986_WOCPU1_RAM_CODE_release.bin',
                    'usr/bin/daed', 'usr/sbin/ModemManager', 'usr/bin/mmcli',
                    'lib/netifd/proto/modemmanager.sh', 'usr/libexec/rpcd/modemmanager',
                    'usr/share/luci/menu.d/luci-proto-modemmanager.json',
                    'usr/share/rpcd/acl.d/luci-proto-modemmanager.json',
                    'www/luci-static/resources/modemmanager_helper.js',
                    'www/luci-static/resources/protocol/modemmanager.js',
                    'www/luci-static/resources/view/modemmanager/status.js',
                    'www/luci-static/resources/view/mmconfig/bands.js',
                    'usr/libexec/mm-ui-bands',
                    'usr/share/luci/menu.d/luci-app-mmconfig.json',
                    'usr/share/rpcd/acl.d/luci-app-mmconfig.json',
                    'usr/share/luci/menu.d/luci-app-sms-manager.json',
                    'usr/share/rpcd/acl.d/luci-app-sms-manager.json',
                    'usr/libexec/rpcd/sms_manager_send',
                    'www/luci-static/resources/view/modem/sms_manager_readsms.js',
                    'www/luci-static/resources/view/modem/sms_manager_sendsms.js',
                    'www/luci-static/resources/view/modem/sms_manager_sendussd.js',
                    'www/luci-static/resources/view/modem/sms_manager_sendat.js',
                    'www/luci-static/resources/view/turboacc.js',
                    'etc/portalwrt-build-date', 'etc/init.d/turboacc', 'sbin/mtkhqos']
        required += ['lib/modules/*/' + name + '.ko*' for name in
                     ('qmi_wwan cdc_mbim cdc_ncm cdc-wdm option qcserial sierra '
                      'hso kalmia ipw ti_usb_3410_5052 wwan mhi mhi_pci_generic '
                      'mhi_net mhi_wwan_ctrl mhi_wwan_mbim qrtr qrtr-mhi mtk_t7xx iosm').split()]
        errors = ['Missing installed firmware component: ' + pattern for pattern in required if not list(rootfs.glob(pattern))]
        for relative in ('usr/bin/daed', 'usr/sbin/ModemManager'):
            path = rootfs / relative
            if path.exists():
                with path.open('rb') as handle:
                    header = handle.read(20)
                if len(header) < 20 or header[:6] != b'\x7fELF\x02\x01' or int.from_bytes(header[18:20], 'little') != 183:
                    errors.append(relative + ' is not a Linux AArch64 ELF64 executable')
        return errors
    return []


@functools.lru_cache(maxsize=1)
def make_parallel_flags():
    result = subprocess.run(['make', '--version'], cwd=ROOT, text=True, capture_output=True)
    match = re.search(r'GNU Make (\d+)\.(\d+)', result.stdout)
    # This tree's Ninja 1.12 jobserver patch parses pipe file descriptors, not
    # GNU make 4.4's default fifo:/path. A FIFO would silently lose the shared
    # job budget in concurrent Meson/CMake packages.
    if match and tuple(map(int, match.groups())) >= (4, 4):
        return ['--jobserver-style=pipe']
    return []


def run_stage(stage, logdir, cpus):
    jobs = stage['jobs']
    log = logdir / (stage['id'] + f"-attempt-{stage.get('attempt', 1):02d}.log")
    cmd = ['make', *make_parallel_flags(), f'-j{jobs}', f'R3MINI_BUILD_JOBS={jobs}', 'V=s', *stage['targets']]
    # Restrict nproc and Go runtime defaults used by upstream sub-builds as well.
    def setup():
        os.sched_setaffinity(0, set(cpus[:jobs]))
    start = time.monotonic()
    row = {**stage, 'command': cmd, 'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'log': str(log)}
    peak = 0
    with log.open('w') as output:
        p = subprocess.Popen(cmd, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True, preexec_fn=setup)
        try:
            while p.poll() is None:
                peak = max(peak, memory_group(p.pid))
                time.sleep(.5)
        except BaseException:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL); p.wait()
            raise
    row.update(exit_code=p.returncode, wall_seconds=round(time.monotonic()-start, 3),
               sampled_process_group_rss_bytes=peak)
    return row


def report(state, logdir):
    rows = []
    for stage in state['attempts']:
        log = Path(stage['log'])
        if log.exists():
            with log.open(errors='replace') as handle:
                for line in handle:
                    m = TIME_RE.search(line)
                    if m:
                        rows.append({'stage': stage['id'], 'component': m[1], 'user_seconds': float(m[2]),
                                     'system_seconds': float(m[3]), 'wall_seconds': float(m[4]),
                                     'stage_exit_code': stage['exit_code']})
    if rows:
        with (logdir / 'component-times.csv').open('w') as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    summary = {'stage_wall_seconds_including_failed_attempts': sum(r['wall_seconds'] for r in state['attempts']),
               'session_wall_seconds': sum(state.get('session_wall_seconds', [])),
               'completed_stages': len(state['completed']), 'attempts': state['attempts'],
               'note': 'Component wall times overlap and must not be summed to claim elapsed total. RSS samples count shared pages per process and can miss short peaks.'}
    save_json(logdir / 'timing-summary.json', summary)
    return summary


def execute(plan, logdir, resume):
    logdir.mkdir(parents=True, exist_ok=True)
    statepath = logdir / 'state.json'
    if resume and statepath.exists():
        # Available RAM can cross a job-cap threshold between sessions. Keep
        # the original ceilings while still checking the actual graph/layout;
        # each attempt below is reduced against current RAM and CPU affinity.
        saved = json.loads((logdir / 'plan.json').read_text())
        layout = lambda p: [{k: v for k, v in s.items() if k != 'jobs'} for s in p['stages']]
        if layout(saved) != layout(plan):
            raise RuntimeError('Build stage layout changed; use a new log directory')
        plan = {**plan, 'stages': saved['stages']}
    mark = fingerprint(plan)
    if statepath.exists():
        if not resume:
            raise RuntimeError('Existing run: use --resume or a new --log-dir')
        state = json.loads(statepath.read_text())
        if state['fingerprint'] != mark:
            raise RuntimeError('Sources/config/plan changed; start a new log directory so stale completion flags are not reused')
    else:
        state = {'fingerprint': mark, 'completed': [], 'attempts': [], 'session_wall_seconds': []}
    save_plan(logdir, plan)
    start = time.monotonic()
    code = 0
    try:
        for stage in plan['stages']:
            if stage['id'] in state['completed']:
                continue
            current_resources = resources()
            if current_resources['memory_available'] < 4 * 2**30:
                raise RuntimeError('Less than 4 GiB available memory before stage; free memory and resume')
            # The saved plan gives ceilings. Other host workloads may consume
            # memory meanwhile; reduce this attempt's jobs and record the value.
            jobs = min(stage['jobs'], current_resources['caps'][stage['class']])
            print(f"[{stage['id']}] jobs={jobs} targets={len(stage['targets'])}", flush=True)
            attempt = 1 + sum(r['id'] == stage['id'] for r in state['attempts'])
            row = run_stage({**stage, 'jobs': jobs, 'attempt': attempt}, logdir, current_resources['affinity'])
            if not row['exit_code']:
                errors = validate_artifacts(stage['name'])
                if errors:
                    row['exit_code'] = 1
                    row['artifact_errors'] = errors
                    with Path(row['log']).open('a') as output:
                        output.write('\nArtifact validation failed:\n' + '\n'.join(errors) + '\n')
            state['attempts'].append(row)
            if not row['exit_code']:
                state['completed'].append(stage['id'])
            save_json(statepath, state)
            print(f"  exit={row['exit_code']} elapsed={row['wall_seconds']:.1f}s log={row['log']}", flush=True)
            if row['exit_code']:
                code = row['exit_code']; break
    finally:
        state['session_wall_seconds'].append(round(time.monotonic()-start, 3))
        save_json(statepath, state); report(state, logdir)
    return code


def main():
    local_python = ROOT / '.r3mini-host/python'
    if local_python.is_dir():
        os.environ['PYTHONPATH'] = str(local_python) + (os.pathsep + os.environ['PYTHONPATH'] if os.environ.get('PYTHONPATH') else '')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'preflight', 'download', 'build', 'report'])
    parser.add_argument('--log-dir', type=Path, default=OUT)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if args.action == 'report':
        print(json.dumps(report(json.loads((args.log_dir / 'state.json').read_text()), args.log_dir), indent=2)); return
    if args.action in ('build', 'download', 'preflight'):
        if os.uname().sysname != 'Linux' or os.uname().machine != 'x86_64':
            raise RuntimeError('This profile uses pinned Linux x86_64 host Go/Node SDKs; target remains ARM64')
        errors = validate_config()
        if errors:
            raise RuntimeError('\n'.join(errors))
        if resources()['disk_available'] < 100 * 2**30:
            raise RuntimeError('Less than 100 GiB free workspace storage for this large feature profile')
        subprocess.run([sys.executable, 'scripts/r3mini-migrate.py', '--verify'], cwd=ROOT, check=True)
        subprocess.run(['make', 'prereq'], cwd=ROOT, check=True)
        subprocess.run(['clang', '--version'], check=True, stdout=subprocess.DEVNULL)
    plan = make_plan()
    if args.action in ('plan', 'preflight'):
        save_plan(args.log_dir, plan)
        print(json.dumps({'stages': len(plan['stages']), 'components': len(plan['components']),
                          'resources': plan['resources'], 'plan': str(args.log_dir / 'plan.json')}, indent=2)); return
    if args.action == 'download':
        jobs = plan['resources']['caps']['download']
        plan['stages'] = [{'id': 'download', 'name': 'download', 'class': 'download', 'jobs': jobs, 'targets': ['download']}]
    raise SystemExit(execute(plan, args.log_dir, args.resume))


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
