#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Select a real upstream revision without changing the validated source pins."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'scripts/susfs/build-pins.json'
POLICY = ROOT / 'scripts/ci/bakasu-source-policy.json'
URL = 'https://github.com/Baka-SU/BakaSU.git'
BRANCH = 'sync-susfs'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo, *args, env=None):
    result = subprocess.run(['git', *args], cwd=repo, env=env, capture_output=True)
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace').strip())
    return result.stdout


def patched_hashes(repo, commit, patch, expected_paths):
    """Derive expected blobs from Git + the reviewed patch, never local source."""
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Invalid upstream commit')
    if git(repo, 'rev-parse', '--is-shallow-repository').strip() != b'false':
        raise ValueError('Full BakaSU history is required for the native version')
    with tempfile.TemporaryDirectory(prefix='bakasu-review-index-') as directory:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(directory) / 'index'))
        git(repo, 'read-tree', commit, env=env)
        git(repo, 'apply', '--cached', '--check', '--whitespace=error-all', str(patch), env=env)
        git(repo, 'apply', '--cached', '--whitespace=error-all', str(patch), env=env)
        paths = git(repo, 'diff', '--cached', '--name-only', commit, env=env).decode().splitlines()
        if set(paths) != set(expected_paths):
            raise ValueError('Reviewed provider path list differs')
        result = {}
        for path in paths:
            blob = git(repo, 'show', ':' + path, env=env)
            result[path] = hashlib.sha256(blob).hexdigest()
        return result


def selection():
    name = os.environ.get('BAKASU_SELECTION_FILE')
    if not name:
        return None
    path = Path(name).resolve(strict=True)
    if not path.is_relative_to(ROOT / '.backport-context'):
        raise ValueError('Source selection must be inside .backport-context')
    record = json.loads(path.read_text())
    if (record.get('schema') != 1 or record.get('mode') not in ('latest', 'validated') or
            record.get('url') != URL or record.get('branch') != BRANCH or
            not re.fullmatch('[0-9a-f]{40}', record.get('commit', ''))):
        raise ValueError('Invalid BakaSU source selection')
    if record.get('baseline_sha256') != sha(BASE) or record.get('policy_sha256') != sha(POLICY):
        raise ValueError('Source selection is stale: reviewed inputs changed')
    return record


def reference_dir():
    selected = selection()
    suffix = '-' + selected['commit'] if selected and selected['mode'] == 'latest' else ''
    return ROOT / ('.backport-context/repos/bakasu-sync-susfs' + suffix)


def build_pins():
    pins = json.loads(BASE.read_text())
    selected = selection()
    if not selected:
        return pins
    if selected['mode'] == 'validated':
        if selected['commit'] != pins['bakasu_commit']:
            raise ValueError('Validated selection differs from the reviewed revision')
        return pins
    policy = json.loads(POLICY.read_text())
    if policy['schema'] != 1 or policy['upstream_url'] != URL or policy['branch'] != BRANCH:
        raise ValueError('Invalid upstream policy')
    patch = ROOT / policy['provider_patch']
    if not patch.resolve().is_relative_to(ROOT / '.github/patches') or sha(patch) != policy['provider_sha256']:
        raise ValueError('Reviewed latest provider patch changed')
    repo = reference_dir()
    if git(repo, 'rev-parse', 'HEAD').decode().strip() != selected['commit']:
        raise ValueError('Selected upstream reference HEAD differs')
    if git(repo, 'status', '--porcelain').strip():
        raise ValueError('Selected upstream reference has local changes')
    git(repo, 'merge-base', '--is-ancestor', policy['latest_base_commit'], selected['commit'])
    expected = patched_hashes(repo, selected['commit'], patch, policy['provider_files'])
    if selected['commit'] == policy['latest_base_commit'] and expected != policy['provider_files']:
        raise ValueError('Latest base differs from its reviewed source hashes')
    pins.update(bakasu_commit=selected['commit'], provider_patch=policy['provider_patch'],
                provider_sha256=policy['provider_sha256'], provider_files=expected,
                dependency_directory='.backport-context/build/bakasu-core-' + selected['commit'] +
                '-' + policy['provider_sha256'][:12])
    return pins


def pins_bytes():
    if not selection() or selection()['mode'] == 'validated':
        return BASE.read_bytes()
    return (json.dumps(build_pins(), indent=2) + '\n').encode()


def source_pins():
    result = json.loads((ROOT / 'scripts/susfs/source-pins.json').read_text())
    pins = build_pins()
    result.update(bakasu=pins['bakasu_commit'], bakasu_patch=pins['provider_patch'],
                  bakasu_patch_files=len(pins['provider_files']))
    return result


def wire_provider(pins):
    """Switch only the known provider symlink; never replace a user directory."""
    link = ROOT / 'drivers/kernelsu'
    baseline = json.loads(BASE.read_text())
    expected = os.path.relpath(ROOT / pins['dependency_directory'] / 'kernel', link.parent)
    original = os.path.relpath(ROOT / baseline['dependency_directory'] / 'kernel', link.parent)
    if not link.is_symlink() or os.readlink(link) not in (original, expected):
        raise ValueError('Unexpected drivers/kernelsu link; refusing replacement')
    if os.readlink(link) != expected:
        link.unlink()
        link.symlink_to(expected)
