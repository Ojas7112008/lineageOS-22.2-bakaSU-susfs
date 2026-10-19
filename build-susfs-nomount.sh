#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0
# Compile/validate only; no boot image or device operation.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 -B "$ROOT/scripts/susfs/build_test.py" "$@"
