#!/usr/bin/env bash
# GeneralsX @performance Claude 16/10/2026 Build and run the skin cache regression test and microbenchmark.
# Needs only a C++17 compiler; the engine is not built. Usage: run-skin-cache-bench.sh [units]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
CXX="${CXX:-c++}"
OUT_DIR="${TMPDIR:-/tmp}/generalsx-skin-cache-bench"
mkdir -p "${OUT_DIR}"

"${CXX}" -std=c++17 -O2 -ffp-contract=off \
	-I"${REPO_ROOT}/Core/Libraries/Source/WWVegas/WW3D2" \
	"${SCRIPT_DIR}/skin_cache_bench.cpp" -o "${OUT_DIR}/skin_cache_bench"

"${OUT_DIR}/skin_cache_bench" "$@"
