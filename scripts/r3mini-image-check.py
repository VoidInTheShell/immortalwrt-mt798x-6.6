#!/usr/bin/env python3
"""Read-only validation of an Autoneg-r2 FIT/GPT and its original firmware.

Only extracted verification data is written, to a new audit directory.
No flashing, loop devices, mounts, or changes to firmware are performed.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'd0d7625b97bb6ce184f697a8621dc1e8e58716dcdd8fbf913b1cfdafb0f65b5a'
TOOLS = ROOT / 'staging_dir/host/bin'


def command(*args):
    return subprocess.check_output([str(arg) for arg in args])


def fdt(path, node, prop, kind='s'):
    return command('fdtget', '-t', kind, path, node, prop).decode().strip()


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def sha256_range(path, offset, length):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        stream.seek(offset)
        remaining = length
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            require(chunk, 'Truncated range in ' + str(path))
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def gzip_uncompressed_digest(path):
    digest, length = hashlib.sha256(), 0
    with gzip.open(path, 'rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            length += len(chunk)
    return length, digest.hexdigest()


def check_gpt(path):
    data = path.read_bytes()
    header = data[512:1024]
    require(header[:8] == b'EFI PART', 'Missing GPT signature')
    length, crc = struct.unpack_from('<II', header, 12)
    header_copy = bytearray(header[:length])
    header_copy[16:20] = bytes(4)
    require(zlib.crc32(header_copy) == crc, 'GPT header CRC mismatch')
    lba, count, size, crc = struct.unpack_from('<QIII', header, 72)
    entries = data[lba * 512:lba * 512 + count * size]
    require(len(entries) == count * size, 'Truncated GPT entries')
    require(zlib.crc32(entries) == crc, 'GPT entries CRC mismatch')
    partitions = []
    for index in range(count):
        entry = entries[index * size:(index + 1) * size]
        if entry[:16] == bytes(16):
            continue
        start, end = struct.unpack_from('<QQ', entry, 32)
        name = entry[56:128].decode('utf-16le').rstrip('\0')
        partitions.append({'name': name, 'start_bytes': start * 512,
                           'size_bytes': (end - start + 1) * 512})
    production = next(p for p in partitions if p['name'] == 'production')
    require(production['size_bytes'] == 2048 * 1024**2,
            'Production partition is not the requested original 2 GiB')
    require(production['start_bytes'] == 64 * 1024**2, 'Production offset changed')
    return partitions


def check_host_flash(directory, image):
    directory = directory.resolve()
    require(directory.is_relative_to(ROOT / '.r3mini-output'), 'Host bundle must be in isolated output')
    manifest_path = directory / 'manifest.json'
    checksum_path = directory / 'SHA256SUMS'
    require(manifest_path.is_file() and checksum_path.is_file(), 'Missing host-flash manifest or checksums')
    manifest = json.loads(manifest_path.read_text())
    require(manifest.get('format') == 'bpi-r3-mini-emmc-host-flash-v1', 'Wrong host-flash manifest type')
    require(manifest.get('board') == 'bananapi,bpi-r3-mini', 'Wrong host-flash board')
    components = manifest.get('components', {})
    for name in ('sysupgrade', 'emmc_gpt', 'emmc_preloader', 'emmc_fip'):
        entry = components.get(name, {})
        path = directory / entry.get('name', '')
        require(path.is_file() and path.stat().st_size == entry.get('bytes')
                and sha256(path) == entry.get('sha256'), 'Invalid host component ' + name)
    require(sha256(directory / components['sysupgrade']['name']) == sha256(image),
            'Host bundle sysupgrade does not match verified source image')
    for name in ('emmc_gpt', 'emmc_preloader', 'emmc_fip'):
        source = image.parent / components[name]['name']
        require(source.is_file() and sha256(source) == components[name]['sha256'],
                'Host bundle component does not match source output: ' + name)
    raw_entry, compressed_entry = manifest.get('raw', {}), manifest.get('compressed', {})
    raw = directory / raw_entry.get('name', '')
    compressed = directory / compressed_entry.get('name', '')
    for label, path, entry in (('raw', raw, raw_entry), ('compressed', compressed, compressed_entry)):
        require(path.is_file() and path.stat().st_size == entry.get('bytes')
                and sha256(path) == entry.get('sha256'), 'Invalid host ' + label + ' image')
    decompressed_length, decompressed_hash = gzip_uncompressed_digest(compressed)
    require((decompressed_length, decompressed_hash) == (raw.stat().st_size, sha256(raw)),
            'Compressed host image does not reproduce raw image')
    gpt = directory / components['emmc_gpt']['name']
    partitions = {entry['name']: entry for entry in check_gpt(gpt) if entry['name']}
    layout = manifest.get('layout', {})
    fip_offset = layout.get('fip_offset')
    production_offset = layout.get('production_offset')
    stripped = manifest.get('stripped_fit', {})
    require((fip_offset, layout.get('fip_size_limit'))
            == (partitions['fip']['start_bytes'], partitions['fip']['size_bytes']),
            'Host FIP offset disagrees with GPT')
    require((production_offset, layout.get('production_size'))
            == (partitions['production']['start_bytes'], partitions['production']['size_bytes']),
            'Host production offset disagrees with GPT')
    fip = directory / components['emmc_fip']['name']
    require(sha256_range(raw, 0, gpt.stat().st_size) == sha256(gpt), 'Raw host image GPT mismatch')
    require(sha256_range(raw, fip_offset, fip.stat().st_size) == sha256(fip), 'Raw host image FIP mismatch')
    require(raw.stat().st_size == production_offset + stripped.get('bytes'), 'Raw host image length mismatch')
    require(sha256_range(raw, production_offset, stripped.get('bytes')) == stripped.get('sha256'),
            'Raw host image FIT mismatch')
    with raw.open('rb') as stream:
        stream.seek(production_offset)
        require(stream.read(4) == b'\xd0\r\xfe\xed', 'Host production payload is not FIT')
    return {'directory': str(directory.relative_to(ROOT)), 'raw': raw_entry,
            'compressed': compressed_entry, 'layout': layout,
            'components': components, 'gpt': partitions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--audit-dir', type=Path, required=True)
    parser.add_argument('--host-flash-dir', type=Path,
                        help='Optional self-contained eMMC host-flash bundle to validate')
    args = parser.parse_args()
    image = args.image.resolve()
    audit = args.audit_dir.resolve()
    require(image.is_relative_to(ROOT / '.r3mini-output'), 'Expected isolated output')
    require(audit.is_relative_to(ROOT / '.r3mini-checks'), 'Audit must be in .r3mini-checks')
    audit.mkdir(parents=True, exist_ok=False)
    require('autoneg-r2' in image.name, 'Missing new filename suffix')
    data = image.read_bytes()
    require(len(data) < 2048 * 1024**2, 'Firmware exceeds production capacity')
    require(struct.unpack_from('>I', data)[0] == 0xd00dfeed, 'Not a FIT image')
    parts = {}
    for name, output in (('kernel-1', 'kernel.gz'), ('fdt-1', 'board.dtb'),
                         ('rootfs-1', 'rootfs.squashfs')):
        node = '/images/' + name
        size = int(fdt(image, node, 'data-size', 'u'))
        position = int(fdt(image, node, 'data-position', 'u'))
        payload = data[position:position + size]
        require(len(payload) == size, 'Truncated ' + name)
        hashes = {}
        for child in command('fdtget', '-l', image, node).decode().split():
            algorithm = fdt(image, node + '/' + child, 'algo')
            expected = bytes(int(value, 16) for value in
                             fdt(image, node + '/' + child, 'value', 'bx').split())
            actual = (struct.pack('>I', zlib.crc32(payload)) if algorithm == 'crc32'
                      else hashlib.new(algorithm, payload).digest())
            require(actual == expected, name + ' ' + algorithm + ' mismatch')
            hashes[algorithm] = actual.hex()
        (audit / output).write_bytes(payload)
        parts[name] = {'size': size, 'position': position, 'hashes': hashes}
    board = audit / 'board.dtb'
    tree = command('dtc', '-I', 'dtb', '-O', 'dts', board).decode()
    (audit / 'board.dts').write_text(tree)
    ethernet = '/soc/ethernet@15100000'
    require(fdt(board, ethernet, 'mediatek,hnat-ppd') == '', 'Missing internal PPE flag')
    for index, address in ((0, 'e'), (1, 'f')):
        mac = ethernet + '/mac@' + str(index)
        phy = ethernet + '/mdio-bus/ethernet-phy@' + address
        require(fdt(board, mac, 'phy-mode') == '2500base-x', 'Host interface changed')
        require(fdt(board, mac, 'phy-handle', 'x') == fdt(board, phy, 'phandle', 'x'),
                'GMAC is not attached to its real PHY')
        children = command('fdtget', '-l', board, mac).decode().split()
        require('fixed-link' not in children, 'GMAC still has fixed-link')
        require(fdt(board, phy, 'airoha,phy-handle') == '', 'Missing vendor PHY attach flag')
    require('mtketh-ppd = "ppe0"' in tree and 'mediatek,ppd-isolated;' in tree,
            'HNAT isolated endpoint not selected')
    metadata = audit / 'metadata.json'
    command(TOOLS / 'fwtool', '-i', metadata, image)
    meta = json.loads(metadata.read_text())
    buildinfo = {}
    for name in ('config.buildinfo', 'version.buildinfo', 'feeds.buildinfo'):
        path = image.parent / name
        require(path.is_file(), 'Missing isolated ' + name)
        buildinfo[name] = sha256(path)
    config_buildinfo = (image.parent / 'config.buildinfo').read_text()
    for setting in ('CONFIG_TARGET_ROOTFS_PARTSIZE=2048',
                    'CONFIG_VERSION_NUMBER="24.10.2"',
                    'CONFIG_VERSION_CODE="GLaDOS-R3Mini-Autoneg-r2"'):
        require(setting in config_buildinfo, 'Wrong isolated config buildinfo: ' + setting)
    require((image.parent / 'version.buildinfo').read_text().strip()
            == meta['version']['revision'], 'Image and isolated version buildinfo disagree')
    require((image.parent / 'feeds.buildinfo').read_text().strip(), 'Empty isolated feeds buildinfo')
    rootfs = audit / 'rootfs.squashfs'
    release = command(TOOLS / 'unsquashfs4', '-cat', rootfs, 'etc/openwrt_release').decode()
    require("DISTRIB_RELEASE='24.10.2'" in release, 'Wrong in-image release')
    require('glados-r3mini-autoneg-r2' in release.lower(), 'Wrong in-image codename')
    listing = command(TOOLS / 'unsquashfs4', '-ll', rootfs).decode()
    required = ('mtkhnat.ko', 'mt_wifi.ko', 'mtk_warp.ko', 'mtk_warp_proxy.ko',
                'conninfra.ko', 'air_en8811h.ko', '7986_WOCPU0_RAM_CODE_release.bin',
                '7986_WOCPU1_RAM_CODE_release.bin', 'WIFI_RAM_CODE_MT7986.bin',
                '7986_WACPU_RAM_CODE_release.bin', 'usr/bin/daed', 'usr/sbin/ModemManager')
    for component in required:
        require(component in listing, 'Missing image component ' + component)
    original = list((ROOT / 'bin/targets/mediatek/filogic').glob('*-squashfs-sysupgrade.itb'))
    require(len(original) == 1 and sha256(original[0]) == BASELINE, 'Original firmware changed')
    gpt = list(image.parent.glob('*autoneg-r2*emmc-gpt.bin'))
    require(len(gpt) == 1, 'Expected exactly one new GPT')
    result = {'image': str(image.relative_to(ROOT)), 'bytes': len(data),
              'sha256': hashlib.sha256(data).hexdigest(), 'fit_parts': parts,
              'metadata': meta, 'isolated_buildinfo_sha256': buildinfo,
              'release': release, 'gpt': check_gpt(gpt[0]),
              'required_components': list(required), 'old_sha256_unchanged': BASELINE,
              'hardware_runtime_tested': False}
    if args.host_flash_dir:
        result['host_flash'] = check_host_flash(args.host_flash_dir, image)
    (audit / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
