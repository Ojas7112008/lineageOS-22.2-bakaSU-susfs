#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Preserve every baseline export CRC, kind and namespace; allow new exports."""
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'devon'))
from check_vendor_abi import exports


def compare(manifest, candidate):
    baseline = json.loads(Path(manifest).read_text())
    expected = baseline['exports']
    actual = exports(Path(candidate))
    changed = {name: {'baseline': value, 'candidate': actual.get(name)}
               for name, value in expected.items() if actual.get(name) != value}
    return {'status': 'rejected' if changed else 'passed', 'scope': __doc__,
            'baseline_exports': len(expected), 'candidate_exports': len(actual),
            'baseline_symvers_sha256': baseline['module_symvers_sha256'],
            'candidate_symvers_sha256': hashlib.sha256(Path(candidate).read_bytes()).hexdigest(),
            'changed_or_missing': changed, 'new_exports': sorted(actual.keys() - expected.keys())}
