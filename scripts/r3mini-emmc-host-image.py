#!/usr/bin/env python3
"""Build a self-contained BPI R3 Mini eMMC host-flash bundle.

The normal sysupgrade FIT is intentionally kept for in-system upgrades.  This
tool creates the complementary raw eMMC *user-area* image used for an initial
flash from a NAND/rescue environment, plus the separate BL2 file for the eMMC
boot0 hardware area.  It never writes a block device or changes its input
artifacts.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / '.r3mini-output'
MIB = 1024 * 1024
EXPECTED_PARTITIONS = {
    'ubootenv': (4 * MIB, 512 * 1024),
    'factory': (4608 * 1024, 2 * MIB),
    'fip': (6656 * 1024, 4 * MIB),
    'recovery': (12 * MIB, 32 * MIB),
    'production': (64 * MIB, 2048 * MIB),
}


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
            require(chunk, 'Unexpected end of ' + str(path))
            digest.update(chunk)
            remaining -= len(chunk)
    return digest.hexdigest()


def gzip_uncompressed_digest(path):
    digest = hashlib.sha256()
    length = 0
    with gzip.open(path, 'rb') as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            length += len(chunk)
    return length, digest.hexdigest()


def gpt_partitions(path):
    data = path.read_bytes()
    require(len(data) >= 1024, 'Truncated GPT artifact')
    header = data[512:1024]
    require(header[:8] == b'EFI PART', 'Missing GPT signature')
    length, expected_crc = struct.unpack_from('<II', header, 12)
    require(92 <= length <= len(header), 'Invalid GPT header length')
    copy = bytearray(header[:length]); copy[16:20] = bytes(4)
    require(zlib.crc32(copy) == expected_crc, 'GPT header CRC mismatch')
    entries_lba, entry_count, entry_size, entries_crc = struct.unpack_from('<QIII', header, 72)
    entries = data[entries_lba * 512:entries_lba * 512 + entry_count * entry_size]
    require(len(entries) == entry_count * entry_size, 'Truncated GPT partition entries')
    require(zlib.crc32(entries) == entries_crc, 'GPT partition table CRC mismatch')
    partitions = {}
    for index in range(entry_count):
        entry = entries[index * entry_size:(index + 1) * entry_size]
        if entry[:16] == bytes(16):
            continue
        start, end = struct.unpack_from('<QQ', entry, 32)
        name = entry[56:128].decode('utf-16le').rstrip('\0')
        # ptgen leaves a non-named compatibility entry in this compact GPT
        # artifact.  It has no role in the named eMMC boot layout.
        if not name:
            continue
        require(name not in partitions, 'Duplicate GPT partition name')
        partitions[name] = ((start * 512), ((end - start + 1) * 512))
    for name, expected in EXPECTED_PARTITIONS.items():
        require(partitions.get(name) == expected,
                f'Unexpected GPT {name} partition: {partitions.get(name)!r}')
    return partitions


def strip_fwtool_metadata(source, destination):
    """Mirror OpenWrt's append-image filter without altering the FIT source."""
    fwtool = ROOT / 'staging_dir/host/bin/fwtool'
    require(fwtool.is_file(), 'Missing host fwtool; build host tools first')
    shutil.copyfile(source, destination)
    for arguments in (('-s', '/dev/null', '-t', destination),
                      ('-i', '/dev/null', '-t', destination)):
        process = subprocess.run([str(fwtool), *map(str, arguments)], text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        require(process.returncode == 0,
                'fwtool could not strip sysupgrade metadata: ' + process.stderr.strip())
    with destination.open('rb') as stream:
        require(stream.read(4) == b'\xd0\r\xfe\xed', 'Stripped payload is not FIT data')
    require(destination.stat().st_size <= source.stat().st_size,
            'Stripped FIT unexpectedly grew')


def pad_to(stream, offset):
    require(stream.tell() <= offset, 'Artifact overlaps its assigned eMMC partition')
    stream.seek(offset)


def binary_record(path):
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': sha256(path)}


def write_readme(path, manifest):
    components = manifest['components']
    raw = manifest['raw']['name']
    compressed = manifest['compressed']['name']
    preloader = components['emmc_preloader']['name']
    path.write_text(f'''# BPI R3 Mini eMMC host-flash bundle

This bundle complements the normal `squashfs-sysupgrade.itb` image.  It is for
an initial eMMC flash from a known-good SPI-NAND system or a board-specific RAM
rescue environment.  It does **not** write a device by itself.

## Files

- `{raw}` is the raw eMMC user-area image.  It contains the GPT at offset 0,
  the eMMC FIP at 6656 KiB, and the stripped system FIT at 64 MiB.
- `{compressed}` is a deterministic gzip copy of the same raw image.
- `{preloader}` must be written separately to the eMMC `mmcblk0boot0` hardware
  boot area; it is deliberately not present in `{raw}`.
- The included sysupgrade FIT remains available for later in-system upgrades.

The GPT production partition remains {manifest['layout']['production_size'] // MIB} MiB;
the raw image is compact and ends after the FIT payload, matching OpenWrt's
image construction convention.  A normal write leaves the unneeded tail of
that partition untouched, exactly as a normal sysupgrade does.

## Flashing route

**Factory-data warning:** this generic raw image contains zeros in the eMMC
`factory` partition (offset 4608 KiB, length 2048 KiB). It does not contain your
device's factory backup. A whole-user-area write also overwrites this range.
Before using it on an existing installation, save the current partition table,
factory data and configuration off-device; restore any verified factory backup
to its matching partition after flashing. The firmware's board-specific DT
EEPROM fallback is not a recovery of erased per-device factory calibration.
For an already working installation with the correct layout, prefer sysupgrade.

The BPI R3 Mini does not expose its eMMC as a generic USB mass-storage device.
Boot the board from a known-good NAND installation, or first load a
**board-specific RAM BL2/FIP rescue pair** with mtk_uartboot and reach a rescue
shell.  Do not use this bundle's eMMC preloader as an mtk_uartboot RAM payload.

On that rescue system, after checking the filenames and `lsblk` output, the
official-style sequence is:

```sh
sha256sum -c SHA256SUMS
echo 0 > /sys/block/mmcblk0boot0/force_ro
dd if={preloader} of=/dev/mmcblk0boot0 bs=1M conv=fsync
dd if={raw} of=/dev/mmcblk0 bs=4M conv=fsync
mmc bootpart enable 1 1 /dev/mmcblk0
sync
```

The last sequence destroys the current eMMC GPT, boot chain, firmware and
configuration.  It must run on the R3 Mini rescue system, never against a
desktop disk by guesswork.  If only `{compressed}` was transferred, verify it
first and decompress it before the write (or use a tool that explicitly accepts
gzip input).

Banana Pi's official guide similarly requires booting from NAND before writing
eMMC and writes BL2 to `mmcblk0boot0` separately from the user-area image:
https://wiki.banana-pi.org/Getting_Started_with_BPI-R3_MINI
''', encoding='utf-8')


def assemble(input_dir, output_dir):
    input_dir = input_dir.resolve()
    output_dir = output_dir.resolve()
    require(input_dir.is_relative_to(OUTPUT_ROOT), 'Input must be below .r3mini-output/')
    require(output_dir.is_relative_to(OUTPUT_ROOT), 'Output must be below .r3mini-output/')
    require(input_dir.is_dir(), 'Input directory does not exist')
    require(not output_dir.exists(), 'Refusing to overwrite existing host-flash output')
    sysupgrades = sorted(input_dir.glob('*-squashfs-sysupgrade.itb'))
    require(len(sysupgrades) == 1, 'Expected exactly one source sysupgrade ITB')
    sysupgrade = sysupgrades[0]
    suffix = '-squashfs-sysupgrade.itb'
    require(sysupgrade.name.endswith(suffix), 'Unexpected sysupgrade filename')
    prefix = sysupgrade.name.removesuffix(suffix)
    source = {
        'sysupgrade': sysupgrade,
        'emmc_gpt': input_dir / (prefix + '-emmc-gpt.bin'),
        'emmc_preloader': input_dir / (prefix + '-emmc-preloader.bin'),
        'emmc_fip': input_dir / (prefix + '-emmc-bl31-uboot.fip'),
    }
    for name, path in source.items():
        require(path.is_file(), 'Missing source ' + name + ': ' + str(path))
    partitions = gpt_partitions(source['emmc_gpt'])
    require(source['emmc_fip'].stat().st_size <= partitions['fip'][1], 'FIP exceeds GPT fip partition')
    require(source['emmc_preloader'].stat().st_size <= 4 * MIB,
            'Preloader exceeds the BPI R3 Mini 4 MiB boot0 area')
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.r3mini-hostflash-', dir=output_dir.parent) as temporary:
        stage = Path(temporary) / output_dir.name
        stage.mkdir()
        payload = stage / '.stripped-sysupgrade.itb'
        strip_fwtool_metadata(sysupgrade, payload)
        raw = stage / (prefix + '-emmc.img')
        with raw.open('wb') as stream:
            stream.write(source['emmc_gpt'].read_bytes())
            pad_to(stream, partitions['fip'][0])
            with source['emmc_fip'].open('rb') as fip_stream:
                shutil.copyfileobj(fip_stream, stream)
            pad_to(stream, partitions['production'][0])
            with payload.open('rb') as payload_stream:
                shutil.copyfileobj(payload_stream, stream)
        expected_raw_size = partitions['production'][0] + payload.stat().st_size
        require(raw.stat().st_size == expected_raw_size, 'Unexpected raw eMMC image length')
        require(sha256_range(raw, 0, source['emmc_gpt'].stat().st_size) == sha256(source['emmc_gpt']),
                'Raw image GPT differs from source')
        require(sha256_range(raw, partitions['fip'][0], source['emmc_fip'].stat().st_size)
                == sha256(source['emmc_fip']), 'Raw image FIP differs from source')
        require(sha256_range(raw, partitions['production'][0], payload.stat().st_size) == sha256(payload),
                'Raw image FIT differs from stripped source')
        compressed = stage / (raw.name + '.gz')
        with raw.open('rb') as source_stream, compressed.open('wb') as destination_stream:
            with gzip.GzipFile(filename='', mode='wb', fileobj=destination_stream, mtime=0) as output_stream:
                shutil.copyfileobj(source_stream, output_stream, length=1024 * 1024)
        uncompressed_size, uncompressed_hash = gzip_uncompressed_digest(compressed)
        require((uncompressed_size, uncompressed_hash) == (raw.stat().st_size, sha256(raw)),
                'Compressed host image does not reproduce raw image')
        copied = {}
        for name, source_path in source.items():
            destination = stage / source_path.name
            shutil.copy2(source_path, destination)
            copied[name] = binary_record(destination)
        stripped_fit = binary_record(payload)
        stripped_fit.pop('name')  # It is embedded at the production offset, not shipped as a file.
        manifest = {
            'format': 'bpi-r3-mini-emmc-host-flash-v1',
            'board': 'bananapi,bpi-r3-mini',
            'input_directory': str(input_dir.relative_to(ROOT)),
            'layout': {
                'gpt_offset': 0,
                'fip_offset': partitions['fip'][0],
                'fip_size_limit': partitions['fip'][1],
                'production_offset': partitions['production'][0],
                'production_size': partitions['production'][1],
                'boot0_preloader': copied['emmc_preloader']['name'],
            },
            'components': copied,
            'stripped_fit': stripped_fit,
            'raw': binary_record(raw),
            'compressed': binary_record(compressed),
            'writes_block_device': False,
        }
        payload.unlink()
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        write_readme(stage / 'FLASHING.md', manifest)
        checksums = [manifest['raw'], manifest['compressed'], *copied.values()]
        (stage / 'SHA256SUMS').write_text(''.join(
            f"{entry['sha256']} *{entry['name']}\n" for entry in sorted(checksums, key=lambda entry: entry['name'])),
            encoding='utf-8')
        stage.replace(output_dir)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True,
                        help='Existing target output holding one sysupgrade and eMMC artifacts')
    parser.add_argument('--output-dir', type=Path, required=True,
                        help='New, nonexistent directory for the portable host-flash bundle')
    args = parser.parse_args()
    print(json.dumps(assemble(args.input_dir, args.output_dir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error))
