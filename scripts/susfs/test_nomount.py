#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check imported NoMount provenance and native error/privilege paths on the host."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from build_test import ROOT
from test_selinux_adapter import function


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    out = ROOT / '.backport-context/audit/nomount-tests'
    out.mkdir(parents=True, exist_ok=True)
    pins = json.loads((ROOT / 'scripts/susfs/nomount-pins.json').read_text())
    assert pins['commit'] == '7046c7ad3ee0bf4ae66e80f6b93b1e30db0cb4e3'
    for name, expected in pins['kernel_files'].items():
        assert sha(ROOT / name) == expected, name
    patch = ROOT / pins['adapter_patch']
    assert sha(patch) == pins['adapter_sha256']
    makefile = (ROOT / 'fs/nomount/Makefile').read_text()
    assert '-fno-stack-protector' not in makefile and '-fno-sanitize' not in makefile
    assert not re.search(r'\b__nocfi\b', (ROOT / 'fs/nomount/nomount.c').read_text())
    with tempfile.TemporaryDirectory(prefix='devon-nomount-upstream-') as directory:
        original = Path(directory)
        for name in pins['original_files']:
            shutil.copyfile(ROOT / 'fs/nomount' / name, original / name)
        subprocess.run(['git', 'apply', '--reverse', '--check', str(patch)], cwd=original, check=True)
        subprocess.run(['git', 'apply', '--reverse', str(patch)], cwd=original, check=True)
        for name, expected in pins['original_files'].items():
            assert sha(original / name) == expected, name
        native = (ROOT / 'fs/nomount/nomount.c').read_text()
        upstream = (original / 'nomount.c').read_text()
        capability = function((ROOT / 'kernel/capability.c').read_text(), 'capable')
        assert 'ns_capable(&init_user_ns, cap)' in capability
        header = (ROOT / 'fs/nomount/nomount.h').read_text()
        abi = '\n'.join(re.search(r'struct ' + name + r' \{.*?\} __attribute__\(\(packed\)\);', header, re.S).group(0)
                        for name in ['nm_payload', 'nm_rule_hdr', 'nm_del_hdr'])
        runs = []
        for mode in ['adapted', 'upstream-lock', 'wrong-namespace-control']:
            bodies = capability.replace('&init_user_ns', '&container_user_ns') if mode == 'wrong-namespace-control' else capability
            bodies += function(upstream if mode == 'upstream-lock' else native, '__nomount_add_rule')
            bodies += function(native, 'nm_key_preparse')
            (out / 'native_nomount.h').write_text(abi + '\n' + bodies)
            binary = out / mode
            result = subprocess.run(['clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                                     '-Wno-unused-function', '-Wno-unused-parameter',
                                     '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined',
                                     '-I', str(out), str(ROOT / 'scripts/susfs/test_nomount.c'), '-o', str(binary)],
                                    capture_output=True, text=True)
            (out / (mode + '-compile.log')).write_text(result.stdout + result.stderr)
            assert result.returncode == 0, result.stderr
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            (out / (mode + '.log')).write_text(result.stdout + result.stderr)
            assert (result.returncode == 0) == (mode == 'adapted'), (mode, result.stdout, result.stderr)
            runs.append({'mode': mode, 'exit': result.returncode, 'expected_rejection': mode != 'adapted'})
    (out / 'results.json').write_text(json.dumps({'status': 'passed', 'scope': __doc__,
        'commit': pins['commit'], 'runs': runs, 'kernel_runtime': 'not executed'}, indent=2) + '\n')
    print('PASS: NoMount provenance, native fault/privilege paths and two failing controls')


if __name__ == '__main__':
    main()
