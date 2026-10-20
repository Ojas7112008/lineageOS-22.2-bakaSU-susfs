#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run maintained host models and target ABI probes; no device safety claim."""
import json
from bakasu_source import pins_bytes
import hashlib
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TESTS = [
    'test_exec_filename_lifetime.py', 'test_selinux_autohooks.py',
    'test_access_stat.py', 'test_init_rc.py', 'test_reboot_input.py',
    'test_setresuid_task_state.py', 'test_fuse_path_index.py',
    'test_path_consumers.py', 'test_path_overlay.py', 'test_overlay_readdir.py',
    'test_feature_abi.py', 'test_identity_features.py', 'test_open_redirect.py',
    'test_susfs_kstat.py', 'test_susfs_map.py', 'test_susfs_mount.py',
    'test_statx_mount_abi.py',
    'test_nomount.py',
    'test_nomount_susfs.py',
    'test_lineage22_preparation.py',
]


def main():
    pins_digest = hashlib.sha256(pins_bytes()).hexdigest()
    out = ROOT / '.backport-context/audit/ci-host-checks'
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for name in TESTS:
        p = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/susfs' / name)],
                           cwd=ROOT, capture_output=True, text=True)
        (out / (name + '.log')).write_text(p.stdout + p.stderr)
        results.append({'test': name, 'exit': p.returncode})
        print(('PASS ' if p.returncode == 0 else 'FAIL ') + name, flush=True)
        if p.returncode:
            print((p.stdout + p.stderr)[-3500:], flush=True)
    if hashlib.sha256(pins_bytes()).hexdigest() != pins_digest:
        raise ValueError('Build pins changed while host tests were running')
    (out / 'results.json').write_text(json.dumps({'scope': __doc__, 'checks': results,
        'build_pins_sha256': pins_digest, 'test_scripts': {name: hashlib.sha256(
            (ROOT / 'scripts/susfs' / name).read_bytes()).hexdigest() for name in TESTS}}, indent=2) + '\n')
    if any(r['exit'] for r in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
