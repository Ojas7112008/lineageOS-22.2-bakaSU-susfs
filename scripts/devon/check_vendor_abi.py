#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check the original LineageOS 22.2 vendor imports against native kernel exports."""
import argparse
import hashlib
import json
from pathlib import Path
import struct

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def exports(path):
    result = {}
    for line in path.read_text().splitlines():
        fields = line.split()
        if len(fields) < 4:
            raise ValueError('Invalid Module.symvers entry: ' + line)
        crc, name, provider, kind = fields[:4]
        if name in result:
            raise ValueError('Duplicate export: ' + name)
        result[name] = {'crc': int(crc, 16), 'kind': kind,
                        'namespace': fields[4] if len(fields) > 4 else ''}
    if not result or 'module_layout' not in result:
        raise ValueError('Missing native module_layout export')
    return result

def imports(path):
    data = path.read_bytes()
    if len(data) < 64 or data[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', data, 18)[0] != 183:
        raise ValueError('Expected little-endian ARM64 ELF module: ' + str(path))
    start = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 58)
    if stride < 64 or not count or names_index >= count or start + count * stride > len(data):
        raise ValueError('Invalid module section table')

    def section(index):
        offset = start + index * stride
        name = struct.unpack_from('<I', data, offset)[0]
        location, size = struct.unpack_from('<QQ', data, offset + 24)
        return name, location, size

    _, location, size = section(names_index)
    names = data[location:location + size]
    for index in range(count):
        name, location, size = section(index)
        if names[name:].split(b'\0', 1)[0] != b'__versions':
            continue
        if size % 64 or location + size > len(data):
            raise ValueError('Invalid __versions records')
        result = {}
        for offset in range(location, location + size, 64):
            crc = struct.unpack_from('<Q', data, offset)[0]
            symbol = data[offset + 8:offset + 64].split(b'\0', 1)[0].decode('ascii')
            if not symbol or symbol in result:
                raise ValueError('Invalid/duplicate module import')
            result[symbol] = crc
        if 'module_layout' not in result:
            raise ValueError('Module has no module_layout version')
        return result
    raise ValueError('Module has no __versions section')


def compare(manifest, candidate):
    pins = json.loads(manifest.read_text())
    available = exports(candidate)
    results = []
    for module in pins['modules']:
        required = module['imports']
        if 'module_layout' not in required:
            raise ValueError('Missing module_layout: ' + module['name'])
        bad = {name: {'stock': crc, 'candidate': hex(available[name]['crc']) if name in available else None}
               for name, crc in required.items()
               if name not in available or available[name]['crc'] != int(crc, 16)}
        results.append({'name': module['name'], 'sha256': module['sha256'],
                        'imports': len(required), 'mismatches': bad})
    return {'status': 'rejected' if any(m['mismatches'] for m in results) else 'passed',
            'scope': 'Original vendor versioned imports only; boot/runtime untested',
            'manifest_sha256': sha(manifest), 'candidate_sha256': sha(candidate),
            'checked_modules': len(results), 'checked_imports': sum(m['imports'] for m in results),
            'mismatches': sum(len(m['mismatches']) for m in results), 'modules': results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=Path(__file__).with_name('vendor-abi.json'))
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = compare(args.manifest, args.candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['status']}: {result['checked_modules']} modules, {result['checked_imports']} imports, {result['mismatches']} mismatches")
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
