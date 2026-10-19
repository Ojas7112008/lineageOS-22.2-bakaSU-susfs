#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check preserved vendor module trust with signature enforcement kept on."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_modules(directory, pem, expected):
    checked = []
    magic = b'~Module signature appended~\n'
    with tempfile.TemporaryDirectory(prefix='devon-module-signatures-') as temporary:
        temporary = Path(temporary)
        for module in expected:
            data = (Path(directory) / module['name']).read_bytes()
            require(sha(data) == module['sha256'], 'Original module checksum changed: ' + module['name'])
            require(data.endswith(magic), 'Missing module signature: ' + module['name'])
            header = len(data) - len(magic) - 12
            require(header >= 0, 'Truncated module signature')
            _, _, kind, signer_len, key_len, length = struct.unpack_from('>5B3xI', data, header)
            require(kind == 2 and signer_len == key_len == 0 and 0 < length < header, 'Unsupported module signature')
            body, signature = temporary / 'module.bin', temporary / 'signature.der'
            body.write_bytes(data[:header - length])
            signature.write_bytes(data[header - length:header])
            result = subprocess.run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER',
                                     '-in', str(signature), '-content', str(body), '-nointern',
                                     '-certfile', str(pem), '-CAfile', str(pem), '-purpose', 'any',
                                     '-out', '/dev/null'], capture_output=True, text=True)
            require(result.returncode == 0, 'Vendor module signature rejected: ' + module['name'] + ': ' + result.stderr)
            checked.append(module['name'])
    return checked


def validate(root, out, modules_directory=None):
    root, out = Path(root), Path(out)
    manifest = json.loads((root / 'scripts/devon/vendor-signatures.json').read_text())
    abi = json.loads((root / 'scripts/devon/vendor-abi.json').read_text())
    signed = manifest['modules']
    require(len(signed) == 66 and len({m['module'] for m in signed}) == 66, 'Incomplete signature inventory')
    require(all(m['signature_verification'] == 'passed' for m in signed), 'Unverified original signature')
    require({m['module']: m['sha256'] for m in signed} == {m['name']: m['sha256'] for m in abi['modules']}, 'Signature and ABI inventories differ')
    certificate = manifest['certificate']
    require(certificate['path'] == 'certs/devon-lineage22.2-vendor.pem', 'Unexpected vendor trust file')
    pem = root / certificate['path']
    require(sha(pem.read_bytes()) == certificate['pem_sha256'], 'Vendor public certificate checksum changed')
    require(b'PRIVATE KEY' not in pem.read_bytes(), 'Vendor trust file must contain only a public certificate')
    der = subprocess.check_output(['openssl', 'x509', '-in', str(pem), '-outform', 'DER'])
    require(sha(der) == certificate['der_sha256'], 'Vendor public certificate identity changed')
    config = set((out / '.config').read_text().splitlines())
    for symbol in ['MODULE_SIG', 'MODULE_SIG_FORCE', 'MODULE_SIG_ALL', 'MODULE_SIG_SHA512', 'SYSTEM_TRUSTED_KEYRING']:
        require('CONFIG_' + symbol + '=y' in config, 'Stock module signature protection disabled: ' + symbol)
    require('CONFIG_SYSTEM_TRUSTED_KEYS="' + certificate['path'] + '"' in config, 'Stock vendor certificate not configured as trusted')
    require(der in (out / 'certs/x509_certificate_list').read_bytes(), 'Stock vendor certificate missing from generated trust list')
    require(der in (out / 'arch/arm64/boot/Image').read_bytes(), 'Stock vendor certificate missing from kernel Image')
    result = {'status': 'passed', 'certificate_der_sha256': sha(der), 'signature_enforcement': True,
              'trusted_certificate_embedded': True, 'expected_original_signed_modules': len(signed),
              'inventory': 'Cryptographically verified original modules, bound by SHA256 to vendor ABI inventory',
              'current_module_binaries_verified': 0}
    if modules_directory is not None:
        result['current_module_binaries_verified'] = len(verify_modules(modules_directory, pem, abi['modules']))
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path)
    parser.add_argument('--modules', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(Path(__file__).resolve().parents[2], args.out, args.modules), indent=2))
