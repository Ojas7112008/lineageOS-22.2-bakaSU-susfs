#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Package only boot.img and its checksum after source, ABI and AVB checks."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/susfs'))
from axion_boot_layout import parse_boot, repack_bytes
from build_test import check_source, check_dependency, verify_config
from run_host_checks import TESTS


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def download(url, maximum):
    require(url.startswith('https://'), 'Build resources require HTTPS')
    request = urllib.request.Request(url, headers={'User-Agent': 'devon-lineage22-build'})
    with urllib.request.urlopen(request, timeout=30) as stream:
        data = stream.read(maximum + 1)
    require(len(data) <= maximum, 'Build resource exceeds pinned size limit')
    return data


def checked_base(path):
    pins = json.loads((ROOT / 'scripts/ci/boot-base.json').read_text())
    require(path.stat().st_size == pins['boot_bytes'] and digest(path) == pins['boot_sha256'],
            'Expected the unmodified October 11, 2025 LineageOS 22.2 boot image')
    data = path.read_bytes()
    return data, parse_boot(data)


def fetch_base(directory):
    target = directory / 'boot.img'
    if target.exists():
        checked_base(target)
        return target
    pins = json.loads((ROOT / 'scripts/ci/boot-base.json').read_text())
    directory.mkdir(parents=True, exist_ok=True)
    data = download(pins['url'], pins['compressed_bytes'])
    require(len(data) == pins['compressed_bytes'] and hashlib.sha256(data).hexdigest() == pins['compressed_sha256'],
            'Compressed boot resource checksum mismatch')
    with tempfile.TemporaryDirectory(prefix='lineage22-base-', dir=directory) as temporary:
        archive = Path(temporary) / 'boot.img.zst'
        unpacked = Path(temporary) / 'boot.img'
        archive.write_bytes(data)
        subprocess.run(['zstd', '-d', '--quiet', str(archive), '-o', str(unpacked)], check=True)
        checked_base(unpacked)
        unpacked.rename(target)
    return target


def fetch_tools(directory):
    pins = json.loads((ROOT / 'scripts/ci/boot-tools.json').read_text())
    directory.mkdir(parents=True, exist_ok=True)
    for name, pin in pins.items():
        require(name in ['avbtool.py', 'unpack_bootimg.py'], 'Unexpected validation tool')
        target = directory / name
        if not target.exists():
            data = base64.b64decode(download(pin['url'], 2 * 1024 * 1024))
            require(hashlib.sha256(data).hexdigest() == pin['sha256'], 'AOSP tool download checksum mismatch')
            target.write_bytes(data)
        require(digest(target) == pin['sha256'], 'AOSP validation tool checksum changed')
    return directory


def checked_build(artifacts):
    record = json.loads((artifacts / 'result.json').read_text())
    require(record['status'] == 'compiled-and-linked' and record['profile'] == 'all',
            'Expected a completed all-feature build')
    checksums = json.loads((artifacts / 'SHA256SUMS.json').read_text())
    for name, expected in checksums.items():
        require(Path(name).name == name, 'Unexpected artifact path')
        require(digest(artifacts / name) == expected, 'Build artifact changed: ' + name)
    required = ['Image', 'kernel.config', 'build-pins.json', 'vendor-abi-result.json',
                'baseline-exports-result.json', 'vendor-signature-result.json', 'native-call-result.json']
    require(set(required) <= checksums.keys(), 'Required build evidence is missing')
    pins = json.loads((ROOT / 'scripts/susfs/build-pins.json').read_text())
    require(digest(artifacts / 'build-pins.json') == digest(ROOT / 'scripts/susfs/build-pins.json'),
            'Build and packaging source pins differ')
    check_source(pins)
    check_dependency(ROOT / pins['dependency_directory'], pins)
    verify_config((artifacts / 'kernel.config').read_text(), pins, 'all')
    require(record['features'] == pins['profiles']['all'], 'Unexpected feature selection')
    for name in required[3:]:
        require(json.loads((artifacts / name).read_text())['status'] == 'passed', 'Rejected build evidence: ' + name)
    abi = json.loads((artifacts / 'vendor-abi-result.json').read_text())
    require(abi['checked_modules'] == 66 and abi['checked_imports'] == 4306 and abi['mismatches'] == 0,
            'Incomplete original-driver validation')
    exports = json.loads((artifacts / 'baseline-exports-result.json').read_text())
    require(exports['baseline_exports'] == 12489 and not exports['changed_or_missing'],
            'Original export versions differ')
    host = json.loads((ROOT / '.backport-context/audit/ci-host-checks/results.json').read_text())
    require(host['build_pins_sha256'] == digest(ROOT / 'scripts/susfs/build-pins.json'),
            'Host tests used different build inputs')
    require(sorted(item['test'] for item in host['checks']) == sorted(TESTS) and
            all(item['exit'] == 0 for item in host['checks']), 'Host checks did not all pass')
    require(all(host['test_scripts'][name] == digest(ROOT / 'scripts/susfs' / name) for name in TESTS),
            'Host test scripts changed after validation')
    return artifacts / 'Image'


def package(artifacts, base_path, tools, destination, evidence):
    require(not destination.exists(), 'Output directory already exists')
    image = checked_build(artifacts)
    # Validate tool contents here too, including direct callers of package().
    fetch_tools(tools)
    original, layout = checked_base(base_path)
    kernel = image.read_bytes()
    packed = repack_bytes(original, kernel)
    destination.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='lineage22-output-', dir=destination.parent) as temporary:
        work = Path(temporary)
        payload = work / 'files'
        payload.mkdir()
        boot = payload / 'boot.img'
        boot.write_bytes(packed)
        for name, command in {
            'avb': [sys.executable, '-B', str(tools / 'avbtool.py'), 'verify_image', '--image', str(boot)],
            'unpack': [sys.executable, '-B', str(tools / 'unpack_bootimg.py'), '--boot_img', str(boot), '--out', str(work / 'unpacked')],
        }.items():
            result = subprocess.run(command, capture_output=True, text=True)
            (evidence / (name + '.log')).write_text(result.stdout + result.stderr)
            require(result.returncode == 0, 'Independent AOSP ' + name + ' check failed: ' + result.stderr)
        require((work / 'unpacked/kernel').read_bytes() == kernel, 'Repacked kernel differs')
        require((work / 'unpacked/ramdisk').read_bytes() == original[layout['ramdisk_start']:layout['ramdisk_end']],
                'Original ramdisk changed')
        checksum = digest(boot)
        (payload / 'boot.img.sha256').write_text(checksum + '  boot.img\n')
        require(sorted(f.name for f in payload.iterdir()) == ['boot.img', 'boot.img.sha256'],
                'Unexpected download contents')
        require(checked_base(base_path)[0] == original, 'Original boot changed during packaging')
        payload.rename(destination)
    (evidence / 'result.json').write_text(json.dumps({'status': 'passed', 'boot_sha256': checksum,
        'kernel_sha256': digest(image), 'base_sha256': digest(base_path),
        'ramdisk_header_and_avb_settings': 'preserved', 'runtime': 'not tested'}, indent=2) + '\n')
    print('Prepared boot.img and boot.img.sha256: ' + checksum)
    return checksum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--tools-directory', type=Path, default=ROOT / '.backport-context/ci-boot-tools')
    parser.add_argument('--output-directory', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    base = args.base or fetch_base(ROOT / '.backport-context/ci-boot-base')
    tools = fetch_tools(args.tools_directory)
    package(args.artifacts.resolve(strict=True), base.resolve(strict=True), tools.resolve(),
            args.output_directory.resolve(), ROOT / '.backport-context/ci-packaging')


if __name__ == '__main__':
    main()
