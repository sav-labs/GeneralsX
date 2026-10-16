#!/usr/bin/env bash
# GeneralsX @feature Claude 16/10/2026 Build and run the skinned shadow geometry regression test and timings.
# Needs only a C++17 compiler; the engine is not built. Usage: run-skinned-shadow-test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CXX="${CXX:-c++}"
OUT_DIR="${TMPDIR:-/tmp}/generalsx-skinned-shadow-test"
mkdir -p "${OUT_DIR}"

"${CXX}" -std=c++17 -O2 -ffp-contract=off -Wall -Wextra \
	-I"${REPO_ROOT}/Core/Libraries/Source/WWVegas/WW3D2" \
	"${SCRIPT_DIR}/skinned_shadow_test.cpp" -o "${OUT_DIR}/skinned_shadow_test"

"${OUT_DIR}/skinned_shadow_test" "$@"
