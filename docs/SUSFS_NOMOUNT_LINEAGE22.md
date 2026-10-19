# LineageOS 22.2 BakaSU, SUSFS and NoMount

Local port started 2026-10-18 (Asia/Calcutta), on
`devon-bakasu-susfs-nomount-lineage22.2`. Compilation and host models do not establish bootability or
correct active hiding/redirection rules.

## Pinned components

| Component | Source |
| --- | --- |
| Official LineageOS 22.2 kernel | `6ee566fa01247d9c4c222601c2bd99534f9d66f9` |
| BakaSU SUSFS provider | Official `sync-susfs` commit `f308ed0936bdd31163cb53da3f42bc7a698f5512`, plus the rebased 16-file 4.19 provider patch |
| SUSFS reference | `82f08351fadb8b19dd6591bd14634d02ad832145`, actual v2.3.0 |
| Reviewed SUSFS kernel port | The 55-file committed integration in the local 23.2 tree at `076d737f4086`, including the mount ABI repair |
| NoMount | `7046c7ad3ee0bf4ae66e80f6b93b1e30db0cb4e3`, plus the independently pinned 4.19 adaptation |
| Compiler | Original ROM's Android Clang r536225, build 12701618 / 19.0.1 |

The tested BakaSU-only revision `b2c595dd` still has an explicit SUSFS build
restriction. Its source/submodule remains intact. The SUSFS build selects a
separate pinned provider through `drivers/kernelsu`; it does not remove that
restriction, edit the provider's compatibility fragment, falsify a version or
pretend this is still the same BakaSU revision. Native history-derived version
for the selected provider is 35233, `v4.2.0-rc3-f308ed09-dirty` (the dirty
suffix records the reviewed provider patch).

## Port boundaries

The transfer uses the committed SUSFS-only integration, rather than copying
the later dirty 23.2 working tree. Droidspaces, Lunaris public-type changes,
DRM changes, IPv6 changes and their config fragments are excluded. NoMount's
five kernel files, license, provenance manifest and adaptation patch are
transferred separately.

Three-way adaptation retains 22.2's native VFS, MM, procfs and fork behavior.
FUSE keeps 22.2's `dir.c` parsers and RCU destruction callback. The private
SUSFS index is initialized after allocating the native FUSE inode, updated
with its original inode number, and removed at eviction and destruction.
There is no FUSE BPF/DAX implementation imported from 23.2. The nonexistent
`vfs_iocb_iter_read` interface is not introduced; real 22.2 synchronous/vector
read paths carry the init.rc hooks.

The exec filename reference fix and success-only manual stat post hooks are
preserved from the boot-tested BakaSU-only tree. SUSFS inline hooks use owned
kernel filenames and held files. BakaSU's automatic SELinux provider route
is preserved, without adding obsolete inline SELinux hooks. The upstream
textual hook checker warns about retained manual-mode branches; actual host
tests and native object-call checks are required alongside it.

All eight SUSFS options are selected by `--profile all`: SUS_PATH, SUS_MOUNT,
SUS_KSTAT, uname, symbol hiding, command-line spoofing, open redirection and
SUS_MAP. The separate unsupported AVC-log command still returns EOPNOTSUPP.
NoMount is built in, and its global control remains gated by init-namespace
CAP_SYS_ADMIN. No userspace metamodule is installed or configured by this
build.

Public `struct kstat`, `struct mount`, `struct inode` and `struct vfsmount`
retain the native layouts. The mount ABI repair uses private mount storage
and a private statx mount-ID out-parameter. Original vendor signatures remain
mandatory, with the recovered original **public** certificate trusted alongside
the new build's signing certificate. No private signing key is imported.

## Local build and validation

```sh
./build.sh
# Equivalent explicit command:
bash build-susfs-nomount.sh --build --profile all --jobs 4
# Configure/check only, including native BakaSU Kbuild checks:
bash build-susfs-nomount.sh --prepare --profile all
python3 -B scripts/susfs/run_host_checks.py
```

Each fresh build records reviewed kernel hashes, provider patch/revision,
compiler integrity, config, logs, source inputs, Image, modules and device
trees under `artifacts/lineage22-susfs-nomount-all/`. A deliberate incremental
retry uses `--resume /absolute/output/path --build --profile all`; it verifies
compiler/provider/profile identity, retains prior evidence and reruns Kbuild
and artifact gates. A different compiler or profile cannot reuse that output.

The build must preserve all 12,489 baseline export CRCs/kinds/namespaces and
pass the original ROM's 66 signed modules and 4,306 versioned imports before
packaging. The baseline export manifest is frozen in source; genuine version
changes are rejected rather than overridden. A narrow susfs_path.h interface
keeps unrelated statfs/UTS definitions out of namei and readdir export graphs. CONFIG_MODULE_SIG_FORCE, MODVERSIONS and strong
stack protection remain enabled. Native stock LTO/CFI settings are retained:
LTO_NONE=y, LTO_CLANG=n, CFI_CLANG=n. This differs from the previous 23.2 ROM's
configuration; the port does not silently reuse its compiler or config.

The 20 maintained host suites cover ownership, policy lifetime, path/FUSE and
overlay behavior, metadata/map/mount rules, native/compat statx layouts,
NoMount fault/privilege handling, nested NoMount/SUSFS getattr and preparation
refusals. Negative controls must fail. The nested-callback test models rule
matching and VFS/LSM inputs; it does not validate native races or Android's
active module overlays. FUSE host reclamation is immediate; the unchanged
real RCU callback is built and linked only in the native kernel.

## Recovery and remaining runtime work

The exact prior BakaSU-only dirty source/index is archived before the transfer
in `.backport-context/audit/lineage22-susfs-nomount/`. Existing compiled
BakaSU-only artifacts and the boot-tested image are preserved. Its boot SHA256
is `427772c36a443d3812cefcd48c3a9505e873362ddf7376048600284cbf8f71a8`.
The old `devon-resukisu` reference and the separate 23.2 working tree are not
modified by this port.

After offline gates, a separately approved temporary boot is still needed.
Check Android completion, exact running config, stock driver loading, enforcing
SELinux and BakaSU Manager/ksud/root grants before activating any rules. Then
test SUSFS and NoMount individually and together, including rule replacement,
directory pagination, bind mounts, app UID/namespace views, open/stat/readlink,
mmap, concurrent reads and rule deletion. Avoid conflicting rules for the
same path until their intended ordering has been verified. Long-term hardware
and stability tests remain separate from successful startup.

## Verified offline checkpoint — 2026-10-18

The all-feature build completed with 66 modules and four device trees. All
12,489 baseline exports match exactly, with five new SUSFS exports. All original
66 module signatures and 4,306 imports pass. Twenty maintained host suites
pass, including 13 preparation refusals. Nine actual ARM64 objects have the
required hook call relocations; manual-only stat post hooks are absent from
SUSFS mode. The initial header-visibility candidate is a saved 51-CRC failing
control. The final fix changes includes, without overriding any CRC or type.

The original LineageOS 22.2 boot was repacked and independently checked with
pinned AOSP unpack/AVB tools. Its ramdisk/header/settings are preserved. Final
boot SHA256: `ca083a8e8ff688261a4d11eb00037a8d12a42d6448f3ab7072bedbca65e56346`.
Image: `D:/Phone expriment/Moto G32/LineageOS/boot-lineage22.2-bakasu-susfs-nomount-test.img`.
The SHA256 sidecar is beside it. This image has not been booted or flashed.
This records the local checkpoint before publication.

## Manual GitHub workflow — 2026-10-19

The workflow builds the `all` profile from the selected source revision, using
the same pinned provider, compiler, vendor trust and export checks as the local
build. All 20 host suites must pass before packaging. The original boot input
is the unmodified October 11, 2025 LineageOS 22.2 image; both its compressed
download and its unpacked bytes have pinned SHA256 checksums.

Packaging independently verifies the result with checksum-pinned AOSP AVB and
unpack tools. The output contains only `boot.img` and `boot.img.sha256`.
Build logs remain in the Actions console; source and validation evidence are
kept on the runner, outside the downloadable artifact. The workflow does not
flash, boot or release generated kernel images.

CI checks the frozen signature inventory and the actual embedded trust
certificate. It reports zero freshly verified original module binaries when
those binaries are unavailable on the runner. The local checkpoint above
cryptographically verified all 66 original module files; the signed-module
inventory is bound to the ABI inventory by their file checksums.

## BakaSU provider update — 2026-10-19

The provider advances four commits from the first validated revision
`e1682a28` to `f308ed09` on the official `sync-susfs` branch. The upstream
change affects only `kernel/feature/selinux_hide.c`, chiefly removing the
separate Linux 6.6 implementation. Our final policy-lock helper hunk is rebased
onto the new file ending. The other 15 adapted files remain byte-identical.

Both patched SELinux implementations were preprocessed with the previous
build's actual ARM64 Clang command and native 4.19 configuration. With only
source path metadata normalized, the active code is byte-identical. The
upstream non-GKI rejection, compatibility fragments and version calculation
remain intact. The new full-history revision count is 4533, giving the native
version code 35233; the upstream release tag remains `v4.2.0-rc3`.

The previous provider checkout, build evidence and first Actions boot image
are retained locally. Source commit `0ab64859069b` is the previous successful
workflow checkpoint. A fresh local Image, 66 modules and four device trees
build successfully with the updated provider. All 12,489 baseline exports,
4,306 original imports, 66 original module signatures, native hook calls and
20 maintained host suites pass. Cloud validation is recorded in the Actions
run; boot and rule testing remain separate.
