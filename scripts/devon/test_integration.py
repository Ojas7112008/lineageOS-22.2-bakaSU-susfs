#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Read-only source/config checks and native BakaSU guard rejection tests."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from check_vendor_abi import compare, sha

ROOT = Path(__file__).resolve().parents[2]


def main():
    out = ROOT / 'artifacts/integration-tests'
    out.mkdir(parents=True, exist_ok=True)
    pins = json.loads((ROOT / 'scripts/devon/source-pins.json').read_text())
    for name, expected in pins['kernel_files'].items():
        assert sha(ROOT / name) == expected, name
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT / 'KernelSU', text=True).strip() == pins['bakasu_commit']
    assert subprocess.check_output(['git', 'rev-parse', '--is-shallow-repository'], cwd=ROOT / 'KernelSU', text=True).strip() == 'false'
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT / 'KernelSU')
    assert not (ROOT / 'fs/susfs.c').exists()
    manifest = ROOT / pins['vendor_manifest']
    required = {}
    for module in json.loads(manifest.read_text())['modules']:
        for name, crc in module['imports'].items():
            assert name not in required or required[name] == crc
            required[name] = crc
    assert len(json.loads(manifest.read_text())['modules']) == 66
    assert sum(len(m['imports']) for m in json.loads(manifest.read_text())['modules']) == 4306
    files = ['fs/exec.c', 'fs/open.c', 'fs/stat.c', 'fs/read_write.c',
             'kernel/reboot.c', 'security/selinux/hooks.c', 'security/security.c']
    cases = [('valid', None, None)]
    for name, file in [('ksu_handle_execveat', 'fs/exec.c'),
                       ('ksu_handle_faccessat', 'fs/open.c'), ('ksu_handle_stat', 'fs/stat.c'),
                       ('ksu_handle_newfstat_ret', 'fs/stat.c'), ('ksu_handle_fstat64_ret', 'fs/stat.c'),
                       ('ksu_handle_sys_reboot', 'kernel/reboot.c')]:
        cases.append(('missing-' + name, file, name))
    cases += [('legacy-read', 'fs/read_write.c', 'ksu_vfs_read_hook'),
              ('legacy-selinux', 'security/selinux/hooks.c', 'is_ksu_transition'),
              ('legacy-rename', 'security/security.c', 'ksu_handle_rename')]
    results = []
    with tempfile.TemporaryDirectory(prefix='bakasu-guard-tests-') as directory:
        temp = Path(directory)
        makefile = temp / 'Makefile'
        native = ROOT / 'KernelSU/kernel/tools/manual_hook_check.mk'
        makefile.write_text('REPO_NAME := BakaSU\nVERSION := 4\nPATCHLEVEL := 19\n' +
            ''.join('CONFIG_KSU_MANUAL_HOOK_AUTO_' + name + '_HOOK := y\n' for name in ['SETUID', 'INITRC', 'INPUT']) +
            f'include {native}\n.PHONY: all\nall:\n\t@:\n')
        for label, file, hook in cases:
            source = temp / label
            for name in files:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            if file:
                path = source / file
                if label.startswith('missing-'):
                    text = path.read_text()
                    assert hook in text
                    path.write_text(text.replace(hook, 'test_removed_hook'))
                else:
                    path.write_text(path.read_text() + '\n/* negative control: ' + hook + ' */\n')
            p = subprocess.run(['make', '--no-print-directory', '-f', str(makefile),
                                'srctree=' + str(source), 'all'], capture_output=True, text=True)
            (out / (label + '.log')).write_text(p.stdout + p.stderr)
            assert (p.returncode == 0) == (label == 'valid'), (label, p.stdout, p.stderr)
            results.append({'case': label, 'exit': p.returncode, 'expected_rejection': label != 'valid'})
        candidate = temp / 'Module.symvers'
        def write(values):
            candidate.write_text(''.join(f'{c}\t{n}\tvmlinux\tEXPORT_SYMBOL\n' for n, c in sorted(values.items())))
        write(required)
        assert compare(manifest, candidate)['status'] == 'passed'
        bad = dict(required); bad['module_layout'] = hex(int(bad['module_layout'], 16) ^ 1); write(bad)
        assert sum('module_layout' in m['mismatches'] for m in compare(manifest, candidate)['modules']) == 66
        bad = dict(required); del bad['__alloc_skb']; write(bad)
        assert compare(manifest, candidate)['status'] == 'rejected'
    (out / 'results.json').write_text(json.dumps({'status': 'passed', 'scope': __doc__,
        'native_hook_guards': results, 'vendor_import_refusals': 'missing and changed imports rejected',
        'boot_runtime': 'not executed'}, indent=2) + '\n')
    print('PASS: source pins, clean/full-history provider, six missing-hook and three legacy-hook refusals; vendor import gates')


if __name__ == '__main__':
    main()
