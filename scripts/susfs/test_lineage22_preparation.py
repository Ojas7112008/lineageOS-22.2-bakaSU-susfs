#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Reject driver-trust, compiler-mode and hook configuration regressions."""
import copy
import json
from pathlib import Path
import tempfile
from build_test import verify_config, check_dependency, ROOT
from check_kernel_exports import compare


def main():
    pins = json.loads((ROOT / 'scripts/susfs/build-pins.json').read_text())
    latest = sorted((ROOT / 'artifacts/lineage22-susfs-nomount-all').glob('*/kernel.config'))[-1]
    text = latest.read_text()
    verify_config(text, pins, 'all')
    tests = []
    for symbol in ['MODULE_SIG_FORCE', 'MODVERSIONS', 'STACKPROTECTOR_STRONG',
                   'NOMOUNT', 'KSU_SUSFS', 'KSU_DEVON_SELINUX_POLICY']:
        bad = text.replace('CONFIG_' + symbol + '=y', '# CONFIG_' + symbol + ' is not set')
        assert bad != text
        try: verify_config(bad, pins, 'all')
        except ValueError: tests.append(symbol)
        else: raise AssertionError('Accepted disabled ' + symbol)
    for symbol in ['KSU_MANUAL_HOOK', 'KSU_TRACEPOINT_HOOK', 'CFI_CLANG', 'LTO_CLANG']:
        try: verify_config(text + '\nCONFIG_' + symbol + '=y\n', pins, 'all')
        except ValueError: tests.append(symbol)
        else: raise AssertionError('Accepted incompatible ' + symbol)
    try: verify_config(text.replace('certs/devon-lineage22.2-vendor.pem', ''), pins, 'all')
    except ValueError: tests.append('original-vendor-certificate')
    else: raise AssertionError('Accepted missing original trust anchor')
    provider = ROOT / pins['dependency_directory']
    check_dependency(provider, pins)
    wrong = copy.deepcopy(pins)
    wrong['provider_files']['kernel/core/init.c'] = '0' * 64
    try: check_dependency(provider, wrong)
    except ValueError: tests.append('provider-source-change')
    else: raise AssertionError('Accepted changed provider')
    candidate = latest.parent / 'Module.symvers'
    baseline = ROOT / pins['baseline_exports_manifest']
    assert compare(baseline, candidate)['status'] == 'passed'
    with tempfile.TemporaryDirectory(prefix='devon-export-rejection-') as directory:
        bad = Path(directory) / 'Module.symvers'
        rows = candidate.read_text().splitlines(True)
        for index, row in enumerate(rows):
            if row.split()[1] == 'vfs_path_lookup':
                fields = row.split()
                fields[0] = '0x00000000'
                rows[index] = '\t'.join(fields) + '\n'
                break
        else: raise AssertionError('Missing native VFS export')
        bad.write_text(''.join(rows))
        assert compare(baseline, bad)['status'] == 'rejected'
        tests.append('native-vfs-export-change')
    out = ROOT / '.backport-context/audit/lineage22-preparation'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'results.json').write_text(json.dumps({'status': 'passed', 'scope': __doc__,
        'configuration': str(latest), 'rejected_controls': tests}, indent=2) + '\n')
    print('PASS: valid configuration/provider and ' + str(len(tests)) + ' rejected regressions')


if __name__ == '__main__':
    main()
