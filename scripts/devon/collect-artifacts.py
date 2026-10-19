#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Collect kernel-only build outputs; never reads or writes a boot image."""
import hashlib,json,os,shutil,subprocess,sys,tarfile
from pathlib import Path
from check_vendor_abi import compare
from check_vendor_signatures import validate as validate_signatures
root=Path(__file__).resolve().parents[2]
out,art=map(lambda s:Path(s).resolve(),sys.argv[1:]);art.mkdir(exist_ok=True,parents=True)
image=out/'arch/arm64/boot/Image'
with image.open('rb') as f: header=f.read(64)
assert header[56:60]==b'ARM\x64' and image.stat().st_size>1024*1024,'Invalid ARM64 Image'
shutil.copy2(image,art/'Image')
shutil.copy2(out/'.config',art/'kernel.config')
dtbs=sorted((out/'arch/arm64/boot/dts').rglob('*.dtb'))+sorted((out/'arch/arm64/boot/dts').rglob('*.dtbo'))
modules=sorted(out.rglob('*.ko'))
assert dtbs,'No compiled device trees'
assert modules,'No compiled kernel modules'
for name,files in [('dtbs.tar.gz',dtbs),('modules.tar.gz',modules)]:
    with tarfile.open(art/name,'w:gz') as tar:
        for f in files:tar.add(f,arcname=str(f.relative_to(out)))
(art/'kernel-integration.patch').write_bytes(subprocess.check_output(['git','diff',json.loads((root/'scripts/devon/source-pins.json').read_text())['kernel_commit'],'--binary'],cwd=root))
pins=json.loads((root/'scripts/devon/source-pins.json').read_text())
actual_bakasu=subprocess.check_output(['git','-C',str(root/'KernelSU'),'rev-parse','HEAD']).decode().strip()
assert actual_bakasu==pins['bakasu_commit'],'BakaSU revision changed during compilation'
assert not subprocess.check_output(['git','-C',str(root/'KernelSU'),'status','--porcelain']),'Modified BakaSU provider'
for name,expected in pins['kernel_files'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected,'Source changed during compilation: '+name
shutil.copyfile(root/pins['vendor_manifest'],art/'vendor-abi.json')
abi=compare(art/'vendor-abi.json',out/'Module.symvers')
(art/'vendor-abi-result.json').write_text(json.dumps(abi,indent=2)+'\n')
assert abi['status']=='passed','Original LineageOS vendor module imports do not match'
original_modules=root/'.backport-context/audit/lineage22.2-integration/vendor-extracted/modules'
signatures=validate_signatures(root,out,original_modules if original_modules.is_dir() else None)
(art/'vendor-signature-result.json').write_text(json.dumps(signatures,indent=2)+'\n')
with tarfile.open(art/'reviewed-inputs.tar.gz','w:gz') as bundle:
    names=set(pins['kernel_files']) | {'drivers/kernelsu','.gitmodules','build.sh',
        'scripts/devon/source-pins.json','scripts/devon/build-bakasu.sh',
        'scripts/devon/collect-artifacts.py','scripts/devon/check_vendor_abi.py',
        'scripts/ci/toolchain-pins.json','scripts/ci/toolchain_integrity.py'}
    for name in sorted(names):bundle.add(root/name,arcname=name,recursive=False)
pins['bakasu_validated_baseline']=pins['bakasu_commit']
pins['bakasu_commit']=actual_bakasu
pins['bakasu_selection']=os.environ.get('BAKASU_SELECTION','pinned')
(art/'source-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
for relative in ['System.map','Module.symvers','modules.order','modules.builtin',
                 'include/config/kernel.release','include/generated/compile.h',
                 'include/generated/utsrelease.h','include/generated/uapi/linux/version.h']:
    destination=art/'build-metadata'/relative
    destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(out/relative,destination)
symbols=subprocess.check_output(['llvm-nm','--defined-only',str(out/'vmlinux')]).decode()
ksu=[line for line in symbols.splitlines() if ' ksu_' in line]
assert ksu,'No linked BakaSU symbols in vmlinux'
assert not any(' susfs_' in line or ' nomount_' in line for line in symbols.splitlines()),'Unexpected SUSFS/NoMount symbols'
assert 'AArch64' in subprocess.check_output(['readelf','-h',str(out/'vmlinux')],text=True),'Expected ARM64 kernel'
(art/'bakasu-symbols.txt').write_text('\n'.join(ksu)+'\n')
manifest={'kernel_base':json.loads((root/'scripts/devon/source-pins.json').read_text())['kernel_commit'],
          'kernel_checkout':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root).decode().strip(),
          'bakasu':actual_bakasu,
          'image_bytes':image.stat().st_size,'device_trees':len(dtbs),'kernel_modules':len(modules),'linked_bakasu_symbols':len(ksu),
          'vendor_abi':abi['status'],'vendor_modules':abi['checked_modules'],'vendor_imports':abi['checked_imports'],
          'vendor_module_signatures':signatures,
          'validation':'Kernel Image/dtbs/modules compile and link; optional boot packaging recorded separately; no device test',
          'artifacts':{}}
for f in sorted(art.iterdir()):
    if f.is_file() and f.name not in ['build-result.json','SHA256SUMS.txt']:
        manifest['artifacts'][f.name]={'bytes':f.stat().st_size,'sha256':hashlib.file_digest(f.open('rb'),'sha256').hexdigest()}
for f in sorted((art/'build-metadata').rglob('*')):
    if f.is_file():
        with f.open('rb') as stream:
            manifest['artifacts'][str(f.relative_to(art))]={'bytes':f.stat().st_size,'sha256':hashlib.file_digest(stream,'sha256').hexdigest()}
(art/'build-result.json').write_text(json.dumps(manifest,indent=2)+'\n')
(art/'SHA256SUMS.txt').write_text(''.join(v['sha256']+'  '+k+'\n' for k,v in manifest['artifacts'].items()))
print(json.dumps({k:v for k,v in manifest.items() if k!='artifacts'},indent=2))
