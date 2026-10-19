#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Reject stale or incomplete build evidence before publishing a boot artifact."""
import argparse
import json
from pathlib import Path
import shutil
import tempfile

import yaml

import boot_image

ROOT = Path(__file__).resolve().parents[2]


def rejected(action, expected):
    try:
        action()
    except ValueError as error:
        assert expected in str(error), str(error)
    else:
        raise AssertionError('Expected rejection: ' + expected)


def workflow_contract():
    workflow = yaml.load((ROOT / '.github/workflows/build-lineage22-boot.yml').read_text(),
                         Loader=yaml.BaseLoader)
    assert list(workflow['on']) == ['workflow_dispatch']
    assert workflow['permissions'] == {'contents': 'read'}
    pins = json.loads((ROOT / 'scripts/susfs/build-pins.json').read_text())
    steps = workflow['jobs']['build']['steps']
    actions = [step['uses'] for step in steps if 'uses' in step]
    assert actions == ['actions/checkout@' + pins['actions']['checkout'],
                       'actions/upload-artifact@' + pins['actions']['upload-artifact']]
    upload = steps[-1]['with']
    assert upload['path'].splitlines() == ['dist/boot.img', 'dist/boot.img.sha256']
    assert upload['if-no-files-found'] == 'error'
    base = json.loads((ROOT / 'scripts/ci/boot-base.json').read_text())
    assert base['boot_bytes'] == 96 * 1024 * 1024
    assert base['boot_sha256'] == '1ef066a7db9dcf1844d573c36693ed115ce8cfbd31505b126c38d32f1137033d'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--base', type=Path, help='Also exercise the complete local repacker')
    parser.add_argument('--tools-directory', type=Path,
                        default=ROOT.parent / '.toolchains/boot-validation')
    args = parser.parse_args()
    artifacts = args.artifacts.resolve(strict=True)
    workflow_contract()
    boot_image.checked_build(artifacts)
    with tempfile.TemporaryDirectory(prefix='lineage22-ci-check-') as temporary:
        work = Path(temporary)
        fixture = work / 'artifacts'
        fixture.mkdir()
        # Large, immutable outputs are shared read-only; edited evidence is copied.
        editable = {'result.json', 'SHA256SUMS.json', 'vendor-abi-result.json',
                    'baseline-exports-result.json'}
        for source in artifacts.iterdir():
            if source.is_file():
                target = fixture / source.name
                if source.name in editable:
                    shutil.copyfile(source, target)
                else:
                    target.symlink_to(source)

        def restore():
            for name in editable:
                shutil.copyfile(artifacts / name, fixture / name)

        def change_json(name, key, value, update_checksum=False):
            path = fixture / name
            record = json.loads(path.read_text())
            record[key] = value
            path.write_text(json.dumps(record))
            if update_checksum:
                sums = json.loads((fixture / 'SHA256SUMS.json').read_text())
                sums[name] = boot_image.digest(path)
                (fixture / 'SHA256SUMS.json').write_text(json.dumps(sums))

        change_json('result.json', 'profile', 'core')
        rejected(lambda: boot_image.checked_build(fixture), 'all-feature build')
        restore()
        change_json('vendor-abi-result.json', 'checked_imports', 0)
        rejected(lambda: boot_image.checked_build(fixture), 'Build artifact changed')
        restore()
        change_json('vendor-abi-result.json', 'checked_imports', 0, True)
        rejected(lambda: boot_image.checked_build(fixture), 'Incomplete original-driver validation')
        restore()
        change_json('baseline-exports-result.json', 'changed_or_missing', ['changed_export'], True)
        rejected(lambda: boot_image.checked_build(fixture), 'Original export versions differ')
        restore()
        sums = json.loads((fixture / 'SHA256SUMS.json').read_text())
        sums.pop('vendor-signature-result.json')
        (fixture / 'SHA256SUMS.json').write_text(json.dumps(sums))
        rejected(lambda: boot_image.checked_build(fixture), 'Required build evidence is missing')

        wrong_base = work / 'wrong-base.img'
        wrong_base.write_bytes(b'not the original boot image')
        rejected(lambda: boot_image.checked_base(wrong_base), 'unmodified October 11')
        if args.base:
            destination = work / 'download'
            checksum = boot_image.package(artifacts, args.base.resolve(strict=True),
                                          args.tools_directory.resolve(strict=True),
                                          destination, work / 'evidence')
            assert {path.name for path in destination.iterdir()} == {'boot.img', 'boot.img.sha256'}
            assert (destination / 'boot.img.sha256').read_text() == checksum + '  boot.img\n'
    print('PASS: pinned manual workflow; incomplete/tampered ABI evidence and wrong boot base rejected')


if __name__ == '__main__':
    main()
