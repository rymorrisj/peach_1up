#!/usr/bin/env bash
set -euo pipefail

# Vendored from https://github.com/xboxdev/extract-xiso
# Pinned tag: build-202505152050 (commit b72e5b6)
# extract-xiso.c and CMakeLists.txt above are unmodified upstream sources.
# See LICENSE.TXT for the exact license text (a modified 4-clause Berkeley
# license, not a standard MIT/BSD variant).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Building extract-xiso ..."
cmake -B "$SCRIPT_DIR/build" -S "$SCRIPT_DIR"
cmake --build "$SCRIPT_DIR/build" --config Release
echo "Built: $SCRIPT_DIR/build"
