#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Nested actual NoMount/SUSFS attribute callbacks under VFS/LSM/rule models.

No native dentries, RCU races, active Android modules or device are exercised.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from test_selinux_adapter import function


def main():
    root = Path(__file__).resolve().parents[2]
    out = root / '.backport-context/audit/nomount-susfs'
    out.mkdir(parents=True, exist_ok=True)
    source = (root / 'fs/nomount/nomount.c').read_text()
    begin = source.rindex('#if LINUX_VERSION_CODE', 0, source.index('static int nm_getattr('))
    end = source.index('static int nm_setattr(', begin)
    nomount = source[begin:end]
    stat = (root / 'fs/stat.c').read_text()
    bodies = ''.join(function(stat, name) for name in ['vfs_getattr_nosec_mnt_id',
        'vfs_getattr_nosec', 'vfs_getattr_mnt_id', 'vfs_getattr'])
    (out / 'susfs_getattr.h').write_text(bodies)
    (out / 'nomount_getattr.h').write_text(nomount)
    kstat = re.search(r'struct kstat \{.*?\n\};', (root / 'include/linux/stat.h').read_text(), re.S).group(0)
    macros = '\n'.join(re.findall(r'^#define STATX_.*', (root / 'include/uapi/linux/stat.h').read_text(), re.M))
    prefix = ('typedef unsigned int u32,model_dev_t; typedef unsigned short umode_t;\n'
              'typedef long long model_loff_t;\n#define loff_t model_loff_t\n'
              'typedef unsigned long long u64; typedef struct {u32 val;} kuid_t,kgid_t;\n'
              'struct timespec64 {long long tv_sec; long tv_nsec;};\n#define dev_t model_dev_t\n')
    (out / 'stat_payload.h').write_text(prefix + macros + '\n' + kstat + '\n')
    fixture = root / 'scripts/susfs/test_nomount_susfs.c'
    flags = ['clang', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
             '-Wno-unused-function', '-Wno-unused-parameter', '-fsanitize=address,undefined',
             '-fno-sanitize-recover=undefined', '-I', str(out)]
    runs = []
    for mount in [False, True]:
        for kstat_enabled in [False, True]:
            name = f'mount-{int(mount)}-kstat-{int(kstat_enabled)}'
            selected = ['-DCONFIG_KSU_SUSFS=1']
            if mount: selected.append('-DCONFIG_KSU_SUSFS_SUS_MOUNT=1')
            if kstat_enabled: selected.append('-DCONFIG_KSU_SUSFS_SUS_KSTAT=1')
            for label, body in [('native', bodies), ('lsm-bypass-control', bodies.replace(
                    'retval = security_inode_getattr(path);', 'retval = 0;'))]:
                assert label == 'native' or body != bodies
                (out / 'susfs_getattr.h').write_text(body)
                binary = out / (name + '-' + label)
                subprocess.run(flags + selected + [str(fixture), '-o', str(binary)], check=True)
                result = subprocess.run([str(binary)], capture_output=True, text=True)
                (out / (binary.name + '.log')).write_text(result.stdout + result.stderr)
                assert (result.returncode == 0) == (label == 'native'), result.stderr
                runs.append({'name': binary.name, 'exit': result.returncode,
                             'expected_rejection': label != 'native'})
            print('PASS ' + name + ' and rejected LSM-bypass mutation')
    (out / 'susfs_getattr.h').write_text(bodies)
    names = ['fs/nomount/nomount.c', 'fs/stat.c', 'include/linux/stat.h',
             'scripts/susfs/test_nomount_susfs.py', 'scripts/susfs/test_nomount_susfs.c']
    (out / 'results.json').write_text(json.dumps({'status': 'passed', 'scope': __doc__,
        'runs': runs, 'inputs': {n: hashlib.sha256((root / n).read_bytes()).hexdigest() for n in names}}, indent=2) + '\n')


if __name__ == '__main__':
    main()
