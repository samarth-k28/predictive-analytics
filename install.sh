#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

BOLD="$(printf '\033[1m')"
ACCENT="$(printf '\033[38;5;166m')"
DIM="$(printf '\033[2m')"
RESET="$(printf '\033[0m')"
if [ ! -t 1 ]; then
	BOLD=""
	ACCENT=""
	DIM=""
	RESET=""
fi

step() { printf '%s▸%s %s\n' "$ACCENT" "$RESET" "$*"; }
note() { printf '%s  %s%s\n' "$DIM" "$*" "$RESET"; }
fail() {
	printf '\n%sError:%s %s\n' "$ACCENT" "$RESET" "$*" >&2
	exit 1
}

PYTHON_VERSION="3.12"
DATA_URL="https://archive.ics.uci.edu/static/public/560/seoul+bike+sharing+demand.zip"
DATA_FILE="data/SeoulBikeData.csv"

case "$(uname -s)" in
Linux) PLATFORM="Linux" ;;
Darwin) PLATFORM="macOS" ;;
*) fail "Supported platforms: Linux and macOS. Found $(uname -s)." ;;
esac

command -v curl >/dev/null 2>&1 || fail "curl is required. Install it and run make install again."

if ! command -v uv >/dev/null 2>&1; then
	step "Installing uv (user-local)"
	curl -LsSf https://astral.sh/uv/install.sh | sh
	export PATH="$HOME/.local/bin:$PATH"
fi
command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on PATH. Open a new shell and run make install again."

step "Platform: ${PLATFORM} $(uname -m)"
step "Using $(uv --version)"

step "Installing Python ${PYTHON_VERSION}"
uv python install "${PYTHON_VERSION}" >/dev/null

if [ -x .venv/bin/python ] && .venv/bin/python -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)' 2>/dev/null; then
	step "Reusing .venv"
else
	step "Creating .venv"
	uv venv --clear --python "${PYTHON_VERSION}" .venv >/dev/null
fi

step "Installing dependencies"
uv pip install --python .venv/bin/python -r requirements-dev.txt >/dev/null

if [ ! -f "${DATA_FILE}" ]; then
	step "Downloading the Seoul bike dataset"
	mkdir -p data .cache
	curl -fsSL "${DATA_URL}" -o .cache/seoul-bike.zip
	.venv/bin/python - <<'PY'
from pathlib import Path
import zipfile

archive = Path(".cache/seoul-bike.zip")
with zipfile.ZipFile(archive) as bundle:
    name = next(name for name in bundle.namelist() if name.endswith("SeoulBikeData.csv"))
    with bundle.open(name) as source, open("data/SeoulBikeData.csv", "wb") as target:
        target.write(source.read())
print("  extracted data/SeoulBikeData.csv")
PY
else
	note "Dataset already present at ${DATA_FILE}"
fi

step "Checking the dataset"
.venv/bin/python - <<'PY'
import csv
from pathlib import Path

path = Path("data/SeoulBikeData.csv")
if not path.exists():
    raise SystemExit("data/SeoulBikeData.csv is missing")

with path.open(encoding="latin1", newline="") as handle:
    reader = csv.reader(handle)
    header = next(reader, [])
    rows = sum(1 for _ in reader)

if "Rented Bike Count" not in header:
    raise SystemExit("unexpected dataset header")
if rows != 8760:
    raise SystemExit(f"expected 8,760 hourly rows, found {rows}")
print(f"  {rows:,} rows, {len(header)} columns")
PY

if command -v docker >/dev/null 2>&1; then
	note "Docker found. Use make docker to run the container."
else
	note "Docker not found. Local install still works with make run."
fi

printf '\n%sReady.%s\n' "$BOLD" "$RESET"
printf '  Run:   make run\n'
printf '  Open:  http://localhost:8000\n'
printf '  Tests: make test\n'
printf '\n'
