#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
# Current branch: LineageOS 22.2 BakaSU + SUSFS + NoMount. No device commands.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $# -eq 0 ]]; then
    set -- --build --profile all
fi
exec bash "$ROOT/build-susfs-nomount.sh" "$@"
