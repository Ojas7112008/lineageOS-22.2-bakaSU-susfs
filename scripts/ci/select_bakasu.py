#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Resolve the official SUSFS provider branch once, or use the validated pin."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/susfs'))
from bakasu_source import BASE, POLICY, URL, BRANCH, sha, git, build_pins, wire_provider


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['latest', 'validated'], default='latest')
    args = parser.parse_args()
    name = os.environ.get('BAKASU_SELECTION_FILE')
    if not name:
        raise ValueError('BAKASU_SELECTION_FILE must be set for every build/test/package step')
    manifest = Path(name).absolute()
    if not manifest.resolve().is_relative_to(ROOT / '.backport-context') or manifest.exists():
        raise ValueError('Selection must be a new file inside .backport-context')
    if args.mode == 'latest':
        row = git(ROOT, 'ls-remote', '--exit-code', URL, 'refs/heads/' + BRANCH).decode().strip()
        if not re.fullmatch(r'[0-9a-f]{40}\trefs/heads/' + BRANCH, row):
            raise ValueError('Unexpected upstream branch response')
        commit = row.split()[0]
        repo = ROOT / ('.backport-context/repos/bakasu-sync-susfs-' + commit)
        if not repo.exists():
            repo.parent.mkdir(parents=True, exist_ok=True)
            # Full official history keeps native BakaSU version calculation intact.
            subprocess.run(['git', 'clone', '--no-checkout', '--single-branch', '--branch',
                            BRANCH, URL, str(repo)], check=True)
            git(repo, 'checkout', '--detach', commit)
        if git(repo, 'remote', 'get-url', 'origin').decode().strip() != URL:
            raise ValueError('Unexpected upstream reference origin')
    else:
        commit = json.loads(BASE.read_text())['bakasu_commit']
    record = {'schema': 1, 'mode': args.mode, 'url': URL, 'branch': BRANCH, 'commit': commit,
              'baseline_sha256': sha(BASE), 'policy_sha256': sha(POLICY)}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open('x') as output:
        output.write(json.dumps(record, indent=2) + '\n')
    try:
        pins = build_pins()  # Strict ancestry, patch application and expected-blob checks.
        wire_provider(pins)
    except Exception:
        manifest.unlink()
        raise
    print('BakaSU ' + args.mode + ': ' + commit, flush=True)
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
            output.write('commit=' + commit + '\nshort_commit=' + commit[:12] + '\n')
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as output:
            output.write('BakaSU source: **' + args.mode + '**, [`' + commit + '`](' +
                         URL.removesuffix('.git') + '/commit/' + commit + ').\n\n' +
                         'The reviewed 4.19 patch and all build/ABI checks remain required.\n')


if __name__ == '__main__':
    main()
