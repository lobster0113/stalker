#!/usr/bin/env bash
# TexasSolver 콘솔(console_solver)을 고정 커밋에서 소스 빌드해 설치한다.
# 릴리스 바이너리(v0.2.0)는 GUI 빌드라 Linux 헤드리스에서 못 쓰므로 console 브랜치를 커밋으로 고정한다.
# 라이선스: AGPL-3.0, 개인 연구용(ADR 0002 결정 3). 바이너리는 리포에 넣지 않는다.
#
# 사용: scripts/install_texassolver.sh [설치경로]
#   설치경로 기본값: $STALKER_TEXASSOLVER_HOME 또는 ~/.cache/stalker/texassolver
#   결과: <설치경로>/console_solver, <설치경로>/resources/, <설치경로>/VERSION
set -euo pipefail

REPO_URL="https://github.com/bupticybee/TexasSolver"
COMMIT="6dfb65b4d7ed081da509e8d8c3d82138c4708267"  # console 브랜치, 2026-08-19

PREFIX="${1:-${STALKER_TEXASSOLVER_HOME:-$HOME/.cache/stalker/texassolver}}"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 2)}"

fail() { echo "install_texassolver: $1" >&2; exit 1; }

if [[ -x "$PREFIX/console_solver" && "$(cat "$PREFIX/VERSION" 2>/dev/null)" == "$COMMIT" ]]; then
    echo "install_texassolver: already installed at $PREFIX ($COMMIT)"
    exit 0
fi

for tool in git cmake make g++; do
    command -v "$tool" >/dev/null || fail "'$tool' not found — install build tools (e.g. apt-get install git cmake build-essential)"
done
echo 'int main(){}' | g++ -fopenmp -x c++ - -o /dev/null 2>/dev/null \
    || fail "g++ cannot link OpenMP — install libgomp (e.g. apt-get install libgomp1)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

git init -q "$WORK/src"
git -C "$WORK/src" remote add origin "$REPO_URL"
git -C "$WORK/src" fetch -q --depth 1 origin "$COMMIT" \
    || fail "cannot fetch $REPO_URL@$COMMIT — check network/proxy access to github.com"
git -C "$WORK/src" checkout -q FETCH_HEAD

# console_solver doesn't use the Python bindings, but the vendored pybind11 2.2 configure step imports
# distutils, which Python 3.12 removed (CI run 40171427531 failed here). Drop that subdirectory only.
sed -i '/^add_subdirectory(ext\/pybind11)/d' "$WORK/src/CMakeLists.txt"

# Vendored googletest/fmt declare cmake_minimum_required < 3.5, which CMake 4 rejects without this.
cmake -S "$WORK/src" -B "$WORK/build" -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    >"$WORK/cmake.log" 2>&1 \
    || { tail -20 "$WORK/cmake.log" >&2; fail "cmake configure failed (log above)"; }
cmake --build "$WORK/build" --target console_solver -j "$JOBS" >"$WORK/build.log" 2>&1 \
    || { tail -30 "$WORK/build.log" >&2; fail "build failed (log above)"; }

mkdir -p "$PREFIX"
rm -rf "$PREFIX/resources"
cp "$WORK/build/console_solver" "$PREFIX/console_solver"
cp -r "$WORK/src/resources" "$PREFIX/resources"
echo "$COMMIT" >"$PREFIX/VERSION"
echo "install_texassolver: installed $PREFIX/console_solver ($COMMIT)"
