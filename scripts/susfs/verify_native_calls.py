#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Verify real ARM64 call relocations, beyond upstream's textual hook checks."""
import hashlib
from pathlib import Path
import re
import subprocess


def verify(out, env=None):
    expected = {
        'fs/exec.o': ['ksu_handle_execveat', 'ksu_handle_post_execveat'],
        'fs/open.o': ['ksu_handle_faccessat'],
        'fs/stat.o': ['ksu_handle_stat', 'ksu_handle_vfs_fstat_file'],
        'fs/read_write.o': ['ksu_handle_sys_read_file', 'ksu_handle_initrc_iter_file',
                            'ksu_handle_initrc_read_result', 'ksu_handle_initrc_seek_file'],
        'fs/file_table.o': ['ksu_handle_initrc_file_release'],
        'kernel/sys.o': ['ksu_handle_setresuid'],
        'kernel/reboot.o': ['ksu_handle_sys_reboot'],
        'drivers/input/input.o': ['ksu_handle_input_handle_event'],
        'fs/nomount/nomount.o': ['register_key_type', 'vfs_getattr_nosec'],
    }
    results = []
    for name, symbols in expected.items():
        path = Path(out) / name
        data = subprocess.check_output(['llvm-readelf', '--relocations', '--wide', str(path)], text=True, env=env)
        calls = re.findall(r'R_AARCH64_CALL26\s+\S+\s+(\S+)\s', data)
        for symbol in symbols:
            if symbol not in calls:
                raise ValueError('Missing native ARM64 call: ' + name + ' -> ' + symbol)
        if name == 'fs/stat.o' and any(s in calls for s in ['ksu_handle_newfstat_ret', 'ksu_handle_fstat64_ret']):
            raise ValueError('Manual-only stat post hooks compiled into SUSFS mode')
        results.append({'object': name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'verified_call_targets': symbols})
    return {'status': 'passed', 'scope': __doc__ + '; call reachability at runtime remains untested',
            'objects': results}
