#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON_BIN=".venv/bin/python"
else
  PYTHON_BIN="python3"
fi

export PYTHONPATH="${ROOT_DIR}/src:${PYTHONPATH:-}"

echo "[1/2] doctor"
"${PYTHON_BIN}" -m novus.cli doctor

echo "[2/2] readiness"
if [[ -n "${NOVUS_BUNDLE_SIGNING_KEY:-}" ]]; then
  "${PYTHON_BIN}" -m novus.cli readiness \
    --output-dir .novus-bench \
    --signing-key "${NOVUS_BUNDLE_SIGNING_KEY}" \
    --report-json .novus-bench/readiness_report.json
else
  "${PYTHON_BIN}" -m novus.cli readiness \
    --output-dir .novus-bench \
    --report-json .novus-bench/readiness_report.json
fi

echo "Readiness checks complete."
