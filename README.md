# Moto G32 — LineageOS 22.2, BakaSU + SUSFS + NoMount

Kernel for Motorola Moto G32 (`devon`), based on official LineageOS 22.2
commit `6ee566fa01247d9c4c222601c2bd99534f9d66f9`.

- BakaSU's SUSFS-supported revision `f308ed09` (native version 35233), with
  the reviewed 4.19 provider patch and compatibility checks retained.
- SUSFS 2.3.0: all eight selected features; AVC-log spoofing remains unsupported.
- Built-in NoMount; no Droidspaces changes.
- Stock Clang 19 toolchain, native driver layouts, version checks and enforced
  original vendor signatures retained.

## Build a boot image on GitHub

1. Open **Actions**.
2. Select **LineageOS 22.2 BakaSU + SUSFS + NoMount boot.img**.
3. Select the `lineage-22.2` branch and choose **Run workflow**.
4. Download the artifact after a successful run.

The download contains exactly **`boot.img`** and **`boot.img.sha256`**.
The workflow uses the checksum-pinned, unmodified original boot image from
`lineage-22.2-20251011-nightly-devon-signed.zip`. It replaces the kernel while
preserving the original ramdisk, header settings and AVB verification flags.
It rejects other ROM images. It never flashes a device or publishes generated
kernels as releases. The release asset is only the original build input.

Each build checks all 12,489 baseline export versions, 66 original vendor-driver
inventories, the trusted signing certificate, native ARM64 hook calls and the
20 maintained host regression suites. Compilation and offline checks do not
establish bootability, active-rule compatibility or long-term stability.

## Build locally in Linux / WSL

```sh
bash build-susfs-nomount.sh --build --profile all --jobs 4
python3 -B scripts/susfs/prepare_test_references.py
python3 -B scripts/susfs/run_host_checks.py
```

The driver downloads and verifies the pinned compiler/provider when needed.
The SUSFS build uses `scripts/susfs/build-pins.json`, not a floating BakaSU
branch. The separate `KernelSU` gitlink records the earlier BakaSU-only
checkpoint; the actual patched SUSFS provider is prepared automatically at
the relative `drivers/kernelsu` link.

See [port details and validation limits](docs/SUSFS_NOMOUNT_LINEAGE22.md).
Original kernel and imported source licenses are retained in their respective
files; NoMount's kernel license is in `fs/nomount/LICENSE`.
