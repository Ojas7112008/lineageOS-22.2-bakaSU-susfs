#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Offline negative controls for selected source history and patch provenance."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts/susfs'))
import bakasu_source as source
import build_test


def rejected(action):
    try:
        action()
    except ValueError:
        return
    raise AssertionError('Unsafe selection was accepted')


def main():
    with tempfile.TemporaryDirectory(prefix='bakasu-selection-test-') as directory:
        root = Path(directory)
        repo = root / 'upstream'
        repo.mkdir()

        def git(*args):
            return source.git(repo, *args).decode().strip()

        git('init', '--quiet')
        git('config', 'user.name', 'Source selection test')
        git('config', 'user.email', 'test@example.invalid')
        (repo / 'kernel').mkdir()
        (repo / 'kernel/core.c').write_text('before\n' * 12)
        git('add', '.')
        git('commit', '--quiet', '-m', 'Base')
        base = git('rev-parse', 'HEAD')
        (repo / 'kernel/core.c').write_text('adapted\n' + 'before\n' * 11)
        reviewed = root / '.github/patches/reviewed.patch'
        reviewed.parent.mkdir(parents=True)
        reviewed.write_bytes(source.git(repo, 'diff', '--full-index'))
        hashes = {'kernel/core.c': source.sha(repo / 'kernel/core.c')}
        git('restore', 'kernel/core.c')
        (repo / 'unrelated').write_text('new upstream feature\n')
        git('add', '.')
        git('commit', '--quiet', '-m', 'Unrelated update')
        descendant = git('rev-parse', 'HEAD')
        actual_index = (repo / '.git/index').read_bytes()
        assert source.patched_hashes(repo, descendant, reviewed, hashes) == hashes
        assert (repo / '.git/index').read_bytes() == actual_index
        assert not git('status', '--porcelain')
        rejected(lambda: source.patched_hashes(repo, 'not-a-sha', reviewed, hashes))
        rejected(lambda: source.patched_hashes(repo, descendant, reviewed, {}))

        # A local edit cannot bless itself by becoming the expected source hash.
        source.git(repo, 'apply', str(reviewed))
        with (repo / 'kernel/core.c').open('a') as output:
            output.write('unreviewed local edit\n')
        assert source.patched_hashes(repo, descendant, reviewed, hashes) == hashes
        effective = {'bakasu_commit': descendant, 'provider_files': hashes,
                     'provider_patch': str(reviewed.relative_to(root))}
        with patch.object(build_test, 'ROOT', root):
            rejected(lambda: build_test.check_dependency(repo, effective))
        git('restore', 'kernel/core.c')

        # Conflicting upstream source must fail strict application, not auto-merge.
        (repo / 'kernel/core.c').write_text('conflicting upstream interface\n')
        git('add', '.')
        git('commit', '--quiet', '-m', 'Incompatible upstream change')
        conflict = git('rev-parse', 'HEAD')
        rejected(lambda: source.patched_hashes(repo, conflict, reviewed, hashes))
        git('checkout', '--quiet', '--detach', descendant)

        pins_path = root / 'scripts/susfs/build-pins.json'
        pins_path.parent.mkdir(parents=True)
        baseline = {'bakasu_commit': base, 'dependency_directory': '.backport-context/build/validated'}
        pins_path.write_text(json.dumps(baseline))
        policy_path = root / 'scripts/ci/bakasu-source-policy.json'
        policy_path.parent.mkdir(parents=True)
        policy = {'schema': 1, 'upstream_url': source.URL, 'branch': source.BRANCH,
                  'latest_base_commit': base, 'provider_patch': str(reviewed.relative_to(root)),
                  'provider_sha256': source.sha(reviewed), 'provider_files': hashes}
        policy_path.write_text(json.dumps(policy))
        reference = root / ('.backport-context/repos/bakasu-sync-susfs-' + descendant)
        reference.parent.mkdir(parents=True)
        reference.symlink_to(repo, target_is_directory=True)
        # Production references are ordinary clones; the fixture link stays in its temp tree.
        record = {'schema': 1, 'mode': 'latest', 'url': source.URL, 'branch': source.BRANCH,
                  'commit': descendant, 'baseline_sha256': source.sha(pins_path),
                  'policy_sha256': source.sha(policy_path)}
        manifest = root / '.backport-context/selection.json'

        def save(value):
            manifest.write_text(json.dumps(value))

        with patch.multiple(source, ROOT=root, BASE=pins_path, POLICY=policy_path), \
                patch.dict(os.environ, BAKASU_SELECTION_FILE=str(manifest)):
            save(record)
            assert source.build_pins()['bakasu_commit'] == descendant
            assert source.build_pins()['provider_files'] == hashes
            link = root / 'drivers/kernelsu'
            link.parent.mkdir()
            link.symlink_to('../.backport-context/build/validated/kernel')
            selected_pins = source.build_pins()
            source.wire_provider(selected_pins)
            assert link.readlink() == Path('../' + selected_pins['dependency_directory'] + '/kernel')
            source.wire_provider(selected_pins)  # Idempotent for the same selection.
            link.unlink()
            link.symlink_to('../user-owned-provider')
            rejected(lambda: source.wire_provider(selected_pins))
            link.unlink()
            link.mkdir()
            (link / 'keep').write_text('user source')
            rejected(lambda: source.wire_provider(selected_pins))
            assert (link / 'keep').read_text() == 'user source'
            for field, value in [('url', 'https://example.invalid/untrusted'),
                                 ('branch', 'main'), ('commit', '../escape'),
                                 ('mode', 'arbitrary-ref'), ('baseline_sha256', '0' * 64),
                                 ('policy_sha256', '0' * 64)]:
                bad = copy.deepcopy(record)
                bad[field] = value
                save(bad)
                rejected(source.build_pins)
            save(record)
            reviewed.write_bytes(reviewed.read_bytes() + b'\n')
            rejected(source.build_pins)
            reviewed.write_bytes(reviewed.read_bytes()[:-1])
            bad = dict(record, mode='validated')
            save(bad)
            rejected(source.build_pins)
            save(dict(bad, commit=base))
            assert source.build_pins() == baseline
            assert source.pins_bytes() == pins_path.read_bytes()
            save(record)
            (repo / 'unrelated').write_text('dirty reference')
            rejected(source.build_pins)
            git('restore', 'unrelated')
            git('checkout', '--quiet', '--orphan', 'unrelated-history')
            git('commit', '--quiet', '-m', 'Unrelated root')
            unrelated = git('rev-parse', 'HEAD')
            reference.unlink()
            reference = reference.with_name('bakasu-sync-susfs-' + unrelated)
            reference.symlink_to(repo, target_is_directory=True)
            save(dict(record, commit=unrelated))
            rejected(source.build_pins)

        shallow = root / 'shallow'
        subprocess.run(['git', 'clone', '--quiet', '--depth=1', repo.as_uri(), str(shallow)], check=True)
        rejected(lambda: source.patched_hashes(shallow, unrelated, reviewed, hashes))
    print('PASS: validated/latest selections, unchanged index and exact reviewed blobs; '
          'conflicts, tampering, dirty/unrelated/shallow histories rejected')


if __name__ == '__main__':
    main()
