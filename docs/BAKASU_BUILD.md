# Moto G32: LineageOS 22.2 with BakaSU

This is the preserved BakaSU-only checkpoint. The current experimental branch
builds SUSFS and NoMount through `build.sh`; see
[the current port instructions](SUSFS_NOMOUNT_LINEAGE22.md). The original
tested source archive and image remain available for recovery.

This is a separate WSL checkout of the official LineageOS `lineage-22.2`
kernel branch. It integrates BakaSU only. No SUSFS backport, NoMount,
Droidspaces, or Lunaris ABI adapters are included in the kernel.

## Sources

- Kernel: <https://github.com/LineageOS/android_kernel_motorola_sm6225/tree/lineage-22.2>,
  pinned at `6ee566fa01247d9c4c222601c2bd99534f9d66f9`.
- Local branch: `devon-bakasu-lineage22.2`.
- BakaSU: <https://github.com/Baka-SU/BakaSU>, pinned as the full-history
  `KernelSU` submodule at `b2c595ddfa64b685e5a144ad37b7c95f912fb92a`.
  Its native version is `v4.2.0-rc3-b2c595dd`, code `35233`.
- Compiler: Android Clang r536225 / 19.0.1, build 12701618, matching the
  original ROM. Official prebuilt commit
  `7143812acf96c9af445b164656ae7f424a67a573` and the complete compiler content
  tree are pinned. Initial Clang20 outputs are retained as historical evidence.

The user confirmed `lineage-22.2-20251011-nightly-devon-signed.zip` as the
installed ROM. Its original kernel reports source commit
`b6546feecf29e914944b8a92a4faaf126f360f2c`. The newer branch tip differs only
in two private touchscreen driver files for a firmware-flashing fix. No
Lunaris source or compatibility configuration is used for this ROM.

## Integration

`drivers/kernelsu` is a relative link to `../KernelSU/kernel`. Driver Kconfig
and Makefile entries select the pinned provider. The separate
`devon-bakasu.config` fragment enables built-in manual hooks with BakaSU's
native automatic setuid/init.rc/input providers. The original Motorola
configuration fragments are unchanged.

Exec, access, stat and reboot callers use a shared typed header. The exec
wrapper retains an independent filename reference through the post callback,
including failure paths. Native fstat post callbacks run only after the
original result was copied successfully. This carries forward the reviewed
non-SUSFS integration's ownership fixes, rather than its older faulty wrapper.

The original ROM's extracted config has `LTO_NONE=y`, `LTO_CLANG=n`, and no
enabled Clang CFI. This checkout retains those stock settings. Module version
checks and strong stack protection remain enabled. The 23.2 build driver's
LTO/CFI assumptions were corrected to match this ROM; no BakaSU compatibility
check was removed or changed. The provider remains clean and derives its
version from its own complete Git history.

The original ROM also enforces module signatures. Each fresh kernel build
generates its own signing key, which cannot authenticate the installed vendor
modules by itself. `devon-vendor-trust.config` adds only the original public
certificate in `certs/devon-lineage22.2-vendor.pem` to the trusted keyring.
`MODULE_SIG_FORCE=y` remains enabled. All 66 original module signatures were
cryptographically verified against that certificate, recovered from the
checksum-verified original kernel; no original private key was recovered.
`vendor-signatures.json` binds those results to the same modules as the ABI
inventory. This certificate is tied to the confirmed October 11, 2025 ROM.

## Build in WSL

The exact stock compiler is installed under the shared `.toolchains` directory:

```sh
cd ~/projects/android_kernel_motorola_sm6225-lineage22.2-bakasu
JOBS=4 ./build.sh
```

`./build.sh --configure-only` stops after configuration. `--build-only` retries
against the prepared configuration. `CLANG_DIR`, `OUT_DIR`, `ARTIFACT_DIR`
and `JOBS` override the defaults. Changing the kernel or BakaSU revision is a
new validation target and requires reviewing the source pins.

Dependencies are the usual kernel build packages: build-essential, bc, bison,
flex, libssl-dev, libelf-dev, libncurses-dev, Python 3.11+, Perl,
gcc-aarch64-linux-gnu and gcc-arm-linux-gnueabi. Compiler installation and
integrity helpers live under `scripts/ci/`.

The driver validates the kernel ancestry, reviewed source hashes, provider
revision/cleanliness/full history and complete compiler content before
building `Image`, device trees and modules. It rejects SUSFS/NoMount/container
options and mismatched stock compilation settings. A successful collector
requires an ARM64 kernel, linked BakaSU symbols and all original vendor
imports to match the actual `Module.symvers`. It also requires signature
enforcement and the original public certificate in the generated trust list
and final Image. When the extracted original modules are available, it
cryptographically verifies their signatures again. Compiler identity stamps
prevent silently reusing objects from a different compiler.

Default outputs are in `artifacts/lineage22.2-bakasu-clang19/`, with intermediate
compilation in `out-clang19/`. The original Clang20 `out/` is historical and
must not be reused for this compiler. Separate audited output overrides used
during diagnosis are recorded in their artifact metadata.
`Image` is the raw compiled kernel. The folder also retains configuration,
modules, device trees, hashes, source evidence and logs for diagnosis.
This build script performs no boot-image repacking or device operation.

## Validation

```sh
python3 -B scripts/devon/test_exec_filename_lifetime.py
python3 -B scripts/devon/test_integration.py
python3 -B scripts/ci/test_toolchain_integrity.py
```

The ownership test passes nine enabled-hook and nine disabled-hook cases with
ASan/UBSan; the historical wrapper fails with the expected use-after-free.
The guard test runs BakaSU's actual manual-hook checker against temporary
source copies: all six missing-hook cases and all three incompatible legacy
hook cases are rejected. It also checks import-version rejection and provider
provenance. Compiler tests reject altered libraries, executables, modes and
untrusted transport contents while allowing archive timestamp differences.

Only boot and vendor were extracted from the confirmed full OTA for read-only
comparison. The payload metadata/hash, each compressed operation and both
final partition hashes were checked using the saved official AOSP Android 15
payload schema. No partition was mounted or written to a phone. Original hashes:

- `boot.img`: `1ef066a7db9dcf1844d573c36693ed115ce8cfbd31505b126c38d32f1137033d`
- `vendor.img`: `305ad5a4f4ccff777d0efbf2e3bba26b2aaae8720adfb8fc7d03a41296aaff7c`

The vendor image contains 66 ARM64 modules with 4306 versioned imports.
`scripts/devon/vendor-abi.json` pins their hashes and imported versions.
`vendor-abi-result.json` and `build-result.json` record the completed native
build's outcome; `SHA256SUMS.txt` binds its saved artifacts. Full audit evidence
is retained in `.backport-context/audit/lineage22.2-integration/`.

## Initial WSL build — 2026-10-18 (startup failure reported)

The ARM64 Image, four device trees and 66 modules compiled and linked
successfully. The kernel has 233 linked BakaSU symbols. All 66 original vendor
modules and all 4306 versioned imports match, with zero mismatches. SUSFS is
disabled and no SUSFS backport is present.

Image: `artifacts/Image`, 31782936 bytes. SHA256:
`6f6e43d86e0e5b735fa98a6d816b2cdce7f54fb282fb144f5a78b0111bf5914f`.
All saved artifact checksums, source pins and the clean provider were rechecked.
The configuration differs from the original ROM only in BakaSU options and
compiler-version metadata. There is one existing host-tool const-qualification
warning in `scripts/mod/modpost.c:804`, and no target kernel compilation errors.

The first preflight stopped because the reused 23.2 runner expected LTO/CFI;
the confirmed stock 22.2 configuration resolved that assumption. The full
native compilation completed, then an edit to the running shell wrapper
interrupted artifact collection. Shell syntax was checked and the corrected,
unchanged wrapper completed an incremental Kbuild check and collection with
exit zero. The first full compilation log is retained at
`.backport-context/audit/lineage22.2-integration/full-compilation.log`;
`artifacts/build.log` records the final incremental check. The kernel sources
and selected configuration did not change between those invocations.

Matching symbol versions and successful compilation do not prove bootability,
root behavior, native lifetime safety or hardware stability. Boot and runtime
testing require a separate device-testing step. The existing 23.2 SUSFS
project and protected legacy branch are kept intact.

The initial image subsequently stalled at the startup animation. Both disabled
BakaSU controls lacked the original vendor signing certificate, even though
their symbol versions matched. The compiler change alone did not resolve this
missing trust anchor. The original stock image boots through fastboot boot.
After adding the original public certificate, the Clang19 control completed
startup and loaded all 62 drivers present in the stock running baseline, with
audio and Lineage charging services running and no signature/version errors.
The running configuration was checked to exclude a return to the stock kernel.
The BakaSU build with this trust fix also completed a temporary boot. Its exact
KSU-enabled running config was verified, BakaSU initialized as version 35233,
all 62 baseline drivers loaded, and SELinux remained enforcing. The installed
stock boot partition is checksum-unchanged. Manager/ksud setup and root grants
remain untested; no supported manager was recognized in the captured scan or
package queries. Detailed evidence and image hashes are in `docs/PORT_LOG.md`.
