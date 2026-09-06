#!/usr/bin/env python3
"""Validate the R3 Mini Linux 6.6.133 source/patch stack without compiling.

The OpenWrt kernel prepare step copies generic and MediaTek ``files`` trees
into the pristine kernel tree and applies patches in this order:

    generic backport -> generic pending -> generic hack -> platform

This script mirrors that bounded source preparation in ``.r3mini-checks``.
It deliberately does not call any make target, alter ``.config``, or execute a
target binary.  It is intended to catch patch drift and board-specific source
mistakes before a real firmware build.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
CHECK_ROOT = ROOT / ".r3mini-checks"
DEFAULT_ARCHIVE = ROOT / "dl" / "linux-6.6.133.tar.xz"
DEFAULT_TREE = CHECK_ROOT / "linux-6.6.133"
DEFAULT_REPORT = ROOT / "docs" / "r3mini-migration-audit" / "kernel-preflight.md"


class CheckError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], *, cwd: Path | None = None, stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def read_series(directory: Path) -> list[Path]:
    series = directory / "series"
    if series.is_file():
        names: list[str] = []
        for line in series.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
        return [directory / name for name in names]
    return sorted(directory.glob("*.patch"))


def files_in(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())


def content_fingerprint(paths: Iterable[Path], *, base: Path) -> str:
    """Hash a deterministic list of relative paths and file contents."""
    digest = hashlib.sha256()
    for path in sorted(paths):
        relative = path.relative_to(base).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        if path.is_symlink():
            digest.update(b"link\0" + os.readlink(path).encode("utf-8"))
        else:
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        digest.update(b"\0")
    return digest.hexdigest()


def patch_stack_fingerprint() -> str:
    directories = [
        ROOT / "target/linux/generic/backport-6.6",
        ROOT / "target/linux/generic/pending-6.6",
        ROOT / "target/linux/generic/hack-6.6",
        ROOT / "target/linux/mediatek/patches-6.6",
    ]
    paths: list[Path] = []
    for directory in directories:
        paths.extend(read_series(directory))
    return content_fingerprint(paths, base=ROOT)


def overlay_fingerprint() -> str:
    paths: list[Path] = []
    for directory in (
        ROOT / "target/linux/generic/files",
        ROOT / "target/linux/mediatek/files-6.6",
    ):
        paths.extend(files_in(directory))
    return content_fingerprint(paths, base=ROOT)


def copy_overlay(source: Path, tree: Path) -> tuple[int, list[str]]:
    if not source.is_dir():
        return 0, []
    copied: list[str] = []
    for item in files_in(source):
        relative = item.relative_to(source)
        destination = tree / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        if item.is_symlink():
            destination.symlink_to(os.readlink(item))
        else:
            shutil.copy2(item, destination)
        copied.append(str(relative))
    return len(copied), copied


def safe_extract(archive: Path, destination: Path) -> None:
    """Extract the known kernel archive while rejecting path traversal."""
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, mode="r:xz") as stream:
        members = stream.getmembers()
        for member in members:
            candidate = (destination / member.name).resolve()
            if candidate != destination.resolve() and destination.resolve() not in candidate.parents:
                raise CheckError(f"archive path escapes extraction directory: {member.name}")
        # Python 3.11 has no extraction filter; the explicit path check above
        # covers this archive, whose entries are all under linux-6.6.133/.
        try:
            stream.extractall(destination, filter="data")
        except TypeError:  # Python < 3.12 has no extraction filter argument.
            stream.extractall(destination)


def prepare_tree(archive: Path, tree: Path, *, fresh: bool) -> tuple[str, bool]:
    if not archive.is_file():
        raise CheckError(f"kernel archive is missing: {archive}")
    archive_hash = sha256(archive)
    marker = tree / ".r3mini-kernel-extracted.json"
    reused = False
    if fresh and tree.exists():
        shutil.rmtree(tree)
    if marker.is_file() and tree.is_dir():
        try:
            record = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            record = {}
        if record.get("archive_sha256") == archive_hash and (tree / ".clang-format").is_file():
            reused = True
    if not reused:
        if tree.exists():
            raise CheckError(
                f"refusing to reuse an unmarked/partial tree: {tree}; rerun with --fresh"
            )
        tree.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        safe_extract(archive, tree.parent)
        extracted_root = tree.parent / "linux-6.6.133"
        if extracted_root != tree and extracted_root.exists():
            # This branch is kept for clarity if the archive layout changes.
            if tree.exists():
                shutil.rmtree(tree)
            shutil.move(str(extracted_root), str(tree))
        if not (tree / ".clang-format").is_file():
            raise CheckError(f"archive did not produce expected source tree: {tree}")
        marker.write_text(
            json.dumps(
                {
                    "archive": str(archive),
                    "archive_sha256": archive_hash,
                    "extracted_at_epoch": time.time(),
                    "extract_seconds": round(time.monotonic() - started, 3),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return archive_hash, reused


def apply_patch_stack(tree: Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    directories = [
        ("generic-backport", ROOT / "target/linux/generic/backport-6.6"),
        ("generic-pending", ROOT / "target/linux/generic/pending-6.6"),
        ("generic-hack", ROOT / "target/linux/generic/hack-6.6"),
        ("mediatek-platform", ROOT / "target/linux/mediatek/patches-6.6"),
    ]
    results: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    # The normal prepare path uses patch-kernel.sh, which invokes patch -f -p1
    # for each directory in this exact order.  Keep the one-patch-at-a-time
    # records so an eventual drift points to a concrete patch.
    for group, directory in directories:
        patches = read_series(directory)
        for patch_file in patches:
            if not patch_file.is_file():
                result = {
                    "group": group,
                    "patch": str(patch_file.relative_to(ROOT)),
                    "status": "missing",
                    "output": "series entry does not name a file",
                }
                results.append(result)
                failures.append(result)
                return results, failures
            started = time.monotonic()
            process = run(
                [
                    "patch", "-f", "-p1", "--batch",
                    "--no-backup-if-mismatch", "-d", str(tree),
                ],
                stdin=patch_file.read_bytes(),
            )
            output = process.stdout.decode("utf-8", errors="replace")
            fuzz = bool(re.search(r"with fuzz|offset -?[0-9]+ line", output, re.I))
            status = "ok" if process.returncode == 0 else "failed"
            result = {
                "group": group,
                "patch": str(patch_file.relative_to(ROOT)),
                "status": status,
                "returncode": process.returncode,
                "fuzz_or_offset": fuzz,
                "seconds": round(time.monotonic() - started, 3),
                "output": output[-4000:],
            }
            results.append(result)
            if process.returncode != 0:
                failures.append(result)
                # Subsequent patches depend on the failed hunk and cannot
                # establish source readiness, so stop at the first failure.
                return results, failures
    return results, failures


def load_patch_results() -> list[dict[str, object]]:
    path = CHECK_ROOT / "patch-results.jsonl"
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            return []
        if isinstance(value, dict):
            records.append(value)
    return records


def patch_marker_path(tree: Path) -> Path:
    return tree / ".r3mini-kernel-patched.json"


def read_matching_patch_marker(tree: Path, archive_hash: str) -> dict[str, object] | None:
    marker = patch_marker_path(tree)
    if not marker.is_file():
        return None
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    if (
        record.get("archive_sha256") == archive_hash
        and record.get("patch_stack_sha256") == patch_stack_fingerprint()
        and record.get("overlay_sha256") == overlay_fingerprint()
    ):
        return record
    return None


def write_patch_marker(tree: Path, archive_hash: str, elapsed: float) -> None:
    patch_marker_path(tree).write_text(
        json.dumps(
            {
                "archive_sha256": archive_hash,
                "patch_stack_sha256": patch_stack_fingerprint(),
                "overlay_sha256": overlay_fingerprint(),
                "patched_at_epoch": time.time(),
                "patch_seconds": round(elapsed, 3),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def config_map(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        # OpenWrt package symbols retain package names, which may contain
        # hyphens (for example CONFIG_PACKAGE_kmod-mediatek_hnat).
        match = re.match(r"^(CONFIG_[A-Za-z0-9_-]+)=(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2)
        else:
            match = re.match(r"^# (CONFIG_[A-Za-z0-9_-]+) is not set$", line)
            if match:
                values[match.group(1)] = "n"
    return values


def fragment_map(paths: Iterable[Path]) -> dict[str, str]:
    values: dict[str, str] = {}
    for path in paths:
        values.update(config_map(path))
    return values


def source_checks(tree: Path) -> dict[str, object]:
    checks: dict[str, object] = {}
    checks["patch_artifacts"] = {
        "reject_files": [str(path.relative_to(tree)) for path in sorted(tree.rglob("*.rej"))],
        "original_files": [str(path.relative_to(tree)) for path in sorted(tree.rglob("*.orig"))],
    }

    pwm = tree / "drivers/hwmon/pwm-fan.c"
    pwm_text = pwm.read_text(encoding="utf-8", errors="replace") if pwm.is_file() else ""
    checks["pwm_fan_source"] = {
        "exists": pwm.is_file(),
        "thermal_cooling_registration": "devm_thermal_of_cooling_device_register" in pwm_text,
        "initial_zero_property": '"mediatek,initial-pwm-zero"' in pwm_text,
        "initial_zero_sets_state": "ctx->pwm_fan_state = 0" in pwm_text,
    }

    r3_dts = ROOT / "target/linux/mediatek/dts/mt7986a-bananapi-bpi-r3-mini.dts"
    wh_dts = ROOT / "target/linux/mediatek/dts/mt7981b-huasifei-wh3000-pro.dts"
    r3_text = r3_dts.read_text(encoding="utf-8", errors="replace") if r3_dts.is_file() else ""
    wh_text = wh_dts.read_text(encoding="utf-8", errors="replace") if wh_dts.is_file() else ""
    checks["board_device_trees"] = {
        "r3_mini_exists": r3_dts.is_file(),
        "r3_mini_pwm_fan": "compatible = \"pwm-fan\"" in r3_text,
        "r3_mini_has_opt_in_initial_zero": "mediatek,initial-pwm-zero" in r3_text,
        "r3_mini_has_cooling_levels": "cooling-levels" in r3_text,
        "wh3000pro_exists": wh_dts.is_file(),
        "wh3000pro_has_opt_in_initial_zero": "mediatek,initial-pwm-zero" in wh_text,
    }

    hnat = tree / "drivers/net/ethernet/mediatek/mtk_hnat/hnat.c"
    hnat_text = hnat.read_text(encoding="utf-8", errors="replace") if hnat.is_file() else ""
    wan_read = 'of_property_read_string(np, "mtketh-wan", &name)' in hnat_text
    wan_copy = "strscpy(hnat_priv->wan, name" in hnat_text
    # A few legacy datapath paths intentionally use eth0/eth1 as MediaTek
    # port names.  The check specifically guards the board selection field:
    # it must come from mtketh-wan rather than an unconditional eth0 value.
    hardcoded_wan_assignment = bool(
        re.search(r"(?:strncpy|strscpy)\s*\(\s*hnat_priv->wan\s*,\s*[\"']eth0", hnat_text)
    )
    checks["hnat_wan_selection"] = {
        "source_exists": hnat.is_file(),
        "reads_mtketh_wan": wan_read,
        "copies_dt_name_to_wan": wan_copy,
        "hardcoded_eth0_wan_assignment": hardcoded_wan_assignment,
        "legacy_eth_port_references": len(re.findall(r"[\"']eth[01][\"']", hnat_text)),
    }

    # The repository DTS/HNAT overlay is copied by the Mediatek target build,
    # while the generic and files-6.6 overlays above are copied into this test
    # tree.  Include a small manifest of the latter for auditability.
    checks["overlay_files_present"] = {
        "generic_files": (tree / "drivers/net/phy").is_dir(),
        "mediatek_hnat": (tree / "drivers/net/ethernet/mediatek/mtk_hnat/Makefile").is_file(),
        "mediatek_wifi_utility": (tree / "drivers/net/wireless/wifi_utility/Makefile").is_file(),
    }
    return checks


def config_checks() -> dict[str, object]:
    root = config_map(ROOT / ".config")
    generic = config_map(ROOT / "target/linux/generic/config-6.6")
    filogic = config_map(ROOT / "target/linux/mediatek/filogic/config-6.6")
    # CONFIG_KERNEL_* values are OpenWrt root configuration requests.  They
    # become the corresponding Linux symbols during kernel configuration.
    root_kernel = {
        key.removeprefix("CONFIG_KERNEL_"): value
        for key, value in root.items()
        if key.startswith("CONFIG_KERNEL_")
    }
    required_generic = {
        "CONFIG_BPF": "y",
        "CONFIG_BPF_SYSCALL": "y",
        "CONFIG_BPF_JIT": "y",
    }
    effective_fragments = dict(generic)
    effective_fragments.update(filogic)
    daed_kernel_requests = {
        "DEBUG_INFO": root_kernel.get("DEBUG_INFO", "n"),
        "DEBUG_INFO_BTF": root_kernel.get("DEBUG_INFO_BTF", "n"),
        "BPF_EVENTS": root_kernel.get("BPF_EVENTS", "n"),
        "CGROUP_BPF": root_kernel.get("CGROUP_BPF", "n"),
        "BPF_STREAM_PARSER": root_kernel.get("BPF_STREAM_PARSER", "n"),
        "XDP_SOCKETS": root_kernel.get("XDP_SOCKETS", "n"),
    }
    generic_results = {
        symbol.removeprefix("CONFIG_"): {"value": generic.get(symbol, "n"), "expected_base": expected}
        for symbol, expected in required_generic.items()
    }
    private_packages = {
        key: root.get(key, "n")
        for key in (
            "CONFIG_PACKAGE_kmod-mediatek_hnat",
            "CONFIG_PACKAGE_kmod-conninfra",
            "CONFIG_PACKAGE_kmod-mt_wifi",
            "CONFIG_PACKAGE_kmod-warp",
            "CONFIG_PACKAGE_luci-app-turboacc-mtk",
        )
    }
    return {
        "root_config": {
            "target": root.get("CONFIG_TARGET_PROFILE", ""),
            "subtarget": root.get("CONFIG_TARGET_SUBTARGET", ""),
            "rootfs_partsize": root.get("CONFIG_TARGET_ROOTFS_PARTSIZE", ""),
            "bpf_toolchain_host": root.get("CONFIG_BPF_TOOLCHAIN_HOST", "n"),
            "kernel_debug_info_btf_request": root.get("CONFIG_KERNEL_DEBUG_INFO_BTF", "n"),
            "kernel_cgroups_request": root.get("CONFIG_KERNEL_CGROUPS", "n"),
            "kernel_cgroup_bpf_request": root.get("CONFIG_KERNEL_CGROUP_BPF", "n"),
        },
        "generic_kernel_base": generic_results,
        "base_fragments_before_root_config_and_package_selections": {
            symbol.removeprefix("CONFIG_"): effective_fragments.get(symbol, "n")
            for symbol in (
                "CONFIG_CGROUPS", "CONFIG_NET_INGRESS", "CONFIG_NET_EGRESS",
                "CONFIG_NETFILTER", "CONFIG_NF_CONNTRACK", "CONFIG_NF_FLOW_TABLE",
                "CONFIG_MTK_THERMAL", "CONFIG_MTK_LVTS_THERMAL",
                "CONFIG_NET_MEDIATEK_SOC", "CONFIG_NET_MEDIATEK_SOC_WED",
            )
        },
        "daed_kernel_requests": daed_kernel_requests,
        "private_hardware_package_selection": private_packages,
        "interpretation": (
            "The generic 6.6 fragment supplies BPF/JIT/BPF_SYSCALL; the filogic "
            "fragment supplies the MediaTek/WED/netfilter base.  CGROUP_BPF, "
            "NET_CLS_BPF/ACT, ingress and related options may be dependency or "
            "root CONFIG_KERNEL_* results, so their final values must be checked "
            "in the generated build_dir kernel .config after a real prepare step."
        ),
    }


def stack_ok(results: list[dict[str, object]]) -> bool:
    return bool(results) and all(result.get("status") == "ok" for result in results)


def write_report(
    report_path: Path,
    *,
    archive: Path,
    archive_hash: str,
    tree: Path,
    reused: bool,
    overlays: dict[str, object],
    patch_results: list[dict[str, object]],
    failures: list[dict[str, object]],
    checks: dict[str, object],
    configs: dict[str, object],
    elapsed: float,
) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    group_counts: dict[str, dict[str, int]] = {}
    adjusted_count = 0
    for result in patch_results:
        group = str(result["group"])
        group_counts.setdefault(group, {"total": 0, "ok": 0, "failed": 0, "adjusted": 0})
        group_counts[group]["total"] += 1
        if result.get("status") == "ok":
            group_counts[group]["ok"] += 1
        else:
            group_counts[group]["failed"] += 1
        if result.get("fuzz_or_offset"):
            group_counts[group]["adjusted"] += 1
            adjusted_count += 1

    pwm = checks.get("pwm_fan_source", {})
    boards = checks.get("board_device_trees", {})
    hnat = checks.get("hnat_wan_selection", {})
    patch_artifacts = checks.get("patch_artifacts", {})
    source_stack_pass = stack_ok(patch_results) and not patch_artifacts.get("reject_files") and not patch_artifacts.get("original_files")
    lines = [
        "# R3 Mini 内核源代码预检",
        "",
        f"检查时间（本机 epoch）：`{time.time():.3f}`",
        "",
        "这份检查只展开并检查 Linux 6.6.133 源码与 OpenWrt 内核补丁栈，没有调用固件、内核或目标架构程序编译。",
        "",
        "## 输入与可复现路径",
        "",
        f"- 源码归档：`{archive.relative_to(ROOT)}`",
        f"- 归档 SHA-256：`{archive_hash}`",
        f"- 检查树：`{tree.relative_to(ROOT)}`",
        f"- 是否复用已标记展开树：`{'是' if reused else '否'}`",
        f"- 本次检查耗时：`{elapsed:.3f}` 秒（不含之后真正编译）",
        "- 补丁顺序与 `include/quilt.mk` / `scripts/patch-kernel.sh` 一致：`generic-backport/` → `generic/`（本仓库为 `pending-6.6`）→ `generic-hack/` → `platform/`（`mediatek/patches-6.6`）。",
        "",
        "## 覆盖文件",
        "",
        "| 覆盖目录 | 文件数 |",
        "|---|---:|",
    ]
    for name, value in overlays.items():
        lines.append(f"| `{name}` | {value} |")
    lines.extend(["", "## 补丁结果", "", "| 阶段 | 总数 | 成功 | 失败 | 有偏移/模糊 |", "|---|---:|---:|---:|---:|"])
    for group, count in group_counts.items():
        lines.append(f"| `{group}` | {count['total']} | {count['ok']} | {count['failed']} | {count['adjusted']} |")
    lines.append(f"| 合计 | {len(patch_results)} | {sum(1 for item in patch_results if item.get('status') == 'ok')} | {len(failures)} | {adjusted_count} |")
    if failures:
        lines.extend(["", "首个失败补丁：", ""])
        first = failures[0]
        lines.append(f"- `{first.get('patch')}`，返回码 `{first.get('returncode')}`。")
        output = str(first.get("output", "")).strip()
        if output:
            lines.extend(["", "```text", output, "```"])
        lines.extend([
            "",
            "这个脚本在首个失败处停止，后续补丁不作成功推断。除专门新增的 `998-pwm-fan-fix.patch` 外，本预检不会自动修改补丁；失败应回到对应补丁和当前 6.6.133 源码定位。",
        ])
    else:
        lines.extend([
            "",
            f"全部列出的补丁均以 `patch -f -p1 --batch --no-backup-if-mismatch` 成功应用；其中 `{adjusted_count}` 个补丁报告了上下文偏移或 fuzz。它们没有被当作失败吞掉，但仍应在真正 kernel prepare/编译中复核。",
        ])
    lines.extend([
        "",
        "## PWM、设备树与 HNAT 源码检查",
        "",
        f"- `drivers/hwmon/pwm-fan.c` 存在：`{pwm.get('exists')}`；保留 thermal cooling-device 注册：`{pwm.get('thermal_cooling_registration')}`；支持 `mediatek,initial-pwm-zero`：`{pwm.get('initial_zero_property')}`；该属性会把初始状态设为 0：`{pwm.get('initial_zero_sets_state')}`。",
        f"- R3 Mini DTS 存在 pwm-fan 且有 cooling-levels：`{boards.get('r3_mini_pwm_fan')}` / `{boards.get('r3_mini_has_cooling_levels')}`；R3 Mini 误用 WH3000Pro 初始零输出属性：`{boards.get('r3_mini_has_opt_in_initial_zero')}`。",
        f"- WH3000Pro DTS 单独声明初始零输出属性：`{boards.get('wh3000pro_has_opt_in_initial_zero')}`。",
        f"- HNAT 读取 `mtketh-wan`：`{hnat.get('reads_mtketh_wan')}`；把 DT 名称复制到 WAN 字段：`{hnat.get('copies_dt_name_to_wan')}`；WAN 字段硬编码为 eth0：`{hnat.get('hardcoded_eth0_wan_assignment')}`。其余 datapath 中仍有 `{hnat.get('legacy_eth_port_references')}` 个 eth0/eth1 字面量，这是旧驱动端口分类逻辑，不能等同于 WAN 选择字段已经可配置。",
        f"- 补丁残留 `.rej` 文件数：`{len(patch_artifacts.get('reject_files', []))}`；`.orig` 文件数：`{len(patch_artifacts.get('original_files', []))}`。",
        "",
        "## BPF、daed 与私有硬件栈配置前置条件",
        "",
        "```json",
        json.dumps(configs, ensure_ascii=False, indent=2),
        "```",
        "",
        "通用 6.6 fragment 提供 BPF/JIT/BPF_SYSCALL，filogic fragment 提供 MediaTek/WED/netfilter 基础项；CGROUP_BPF、NET_CLS_BPF/ACT、ingress 及其依赖项可能由根配置或包依赖在内核配置阶段补入。daed 所需的 DEBUG_INFO/BTF/BPF_EVENTS、stream parser、XDP 等由根 `.config` 的 `CONFIG_KERNEL_*` 请求交给 OpenWrt 内核配置阶段。这里检查了 fragment 和请求，不能代替真正 prepare 后读取 `build_dir/target-*/linux-*/linux-6.6.133/.config`。",
        "",
        "## 结论",
        "",
        f"- 源码补丁栈：`{'通过' if source_stack_pass else '未通过'}`。",
        "- 本检查没有编译固件、内核、daed 或 BPF，也没有执行任何 ARM/aarch64 目标文件；因此不会伪造编译通过或运行时硬件加速结论。",
        "- 重新执行：`python3 scripts/r3mini-kernel-check.py --fresh`；不加 `--fresh` 时只复用归档、补丁栈和覆盖文件指纹一致的标记树。",
        "",
        "机器可读的逐补丁记录保存在 `.r3mini-checks/patch-results.jsonl`，配置与源检查保存在 `.r3mini-checks/kernel-check.json`。",
        "",
    ])
    report_path.write_text("\n".join(lines), encoding="utf-8")


def write_machine_records(
    patch_results: list[dict[str, object]],
    checks: dict[str, object],
    configs: dict[str, object],
    overlays: dict[str, object],
    archive: Path,
    archive_hash: str,
    tree: Path,
) -> None:
    CHECK_ROOT.mkdir(parents=True, exist_ok=True)
    with (CHECK_ROOT / "patch-results.jsonl").open("w", encoding="utf-8") as stream:
        for result in patch_results:
            stream.write(json.dumps(result, ensure_ascii=False) + "\n")
    (CHECK_ROOT / "kernel-check.json").write_text(
        json.dumps(
            {
                "archive": str(archive),
                "archive_sha256": archive_hash,
                "tree": str(tree),
                "overlays": overlays,
                "source_checks": checks,
                "config_checks": configs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--tree", type=Path, default=DEFAULT_TREE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--fresh", action="store_true", help="re-extract the archive into the owned check tree")
    args = parser.parse_args()
    archive = args.archive.resolve()
    tree = args.tree.resolve()
    report = args.report.resolve()
    started = time.monotonic()
    try:
        archive_hash, reused = prepare_tree(archive, tree, fresh=args.fresh)
        overlay_specs = [
            ("target/linux/generic/files", ROOT / "target/linux/generic/files"),
            ("target/linux/mediatek/files-6.6", ROOT / "target/linux/mediatek/files-6.6"),
        ]
        overlays: dict[str, object] = {}
        for name, source in overlay_specs:
            if reused:
                # Never overwrite a patched overlay file during a cached check.
                # Its pristine overlay content may itself be modified by patches.
                count = sum(1 for path in source.rglob('*') if path.is_file())
            else:
                count, _ = copy_overlay(source, tree)
            overlays[name] = count
        cached_marker = read_matching_patch_marker(tree, archive_hash)
        if cached_marker is not None and not args.fresh:
            patch_results = load_patch_results()
            expected_patches = sum(len(read_series(directory)) for directory in (
                ROOT / "target/linux/generic/backport-6.6",
                ROOT / "target/linux/generic/pending-6.6",
                ROOT / "target/linux/generic/hack-6.6",
                ROOT / "target/linux/mediatek/patches-6.6",
            ))
            if len(patch_results) != expected_patches or not stack_ok(patch_results):
                raise CheckError("patch marker exists but patch-results.jsonl is incomplete; rerun with --fresh")
            failures = []
            reused = True
        elif reused:
            raise CheckError(
                "extracted tree has no matching patch marker; rerun with --fresh"
            )
        else:
            patch_started = time.monotonic()
            patch_results, failures = apply_patch_stack(tree)
            if not failures:
                write_patch_marker(tree, archive_hash, time.monotonic() - patch_started)
        checks = source_checks(tree)
        configs = config_checks()
        write_machine_records(patch_results, checks, configs, overlays, archive, archive_hash, tree)
        write_report(
            report,
            archive=archive,
            archive_hash=archive_hash,
            tree=tree,
            reused=reused,
            overlays=overlays,
            patch_results=patch_results,
            failures=failures,
            checks=checks,
            configs=configs,
            elapsed=time.monotonic() - started,
        )
    except (CheckError, OSError, tarfile.TarError) as error:
        print(f"r3mini-kernel-check: ERROR: {error}", file=sys.stderr)
        return 2
    print(f"kernel source tree: {tree}")
    print(f"patches applied: {sum(1 for item in patch_results if item.get('status') == 'ok')}/{len(patch_results)}")
    print(f"report: {report}")
    if failures:
        print(f"first patch failure: {failures[0].get('patch')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
