#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Run the pinned build and expose its exact output directory to GitHub Actions."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parent = ROOT / 'artifacts/lineage22-susfs-nomount-all'
    if parent.exists() and any(parent.iterdir()):
        raise ValueError('CI requires an empty build artifact directory')
    jobs = int(os.environ.get('BUILD_JOBS', '4'))
    if not 1 <= jobs <= 4:
        raise ValueError('BUILD_JOBS must be between one and four')
    result = subprocess.run(['bash', 'build-susfs-nomount.sh', '--build', '--profile', 'all',
                             '--jobs', str(jobs)], cwd=ROOT)
    candidates = list(parent.glob('*/result.json')) if parent.exists() else []
    if result.returncode:
        for log in sorted(parent.glob('*/*.log')):
            print('\n--- ' + log.name + ' ---', flush=True)
            print('\n'.join(log.read_text(errors='replace').splitlines()[-100:]), flush=True)
        raise SystemExit(result.returncode)
    if len(candidates) != 1:
        raise ValueError('Expected exactly one completed build')
    artifact = candidates[0].parent
    record = json.loads(candidates[0].read_text())
    if record['status'] != 'compiled-and-linked':
        raise ValueError('Kernel did not complete validation')
    if 'GITHUB_OUTPUT' in os.environ:
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('artifacts=' + str(artifact) + '\n')
    print('Validated build: ' + str(artifact), flush=True)


if __name__ == '__main__':
    main()
