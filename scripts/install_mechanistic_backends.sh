#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")"/.. && pwd)"
REQUIREMENTS_FILE="$ROOT_DIR/backend/requirements-optional.txt"

if [[ ! -f "$REQUIREMENTS_FILE" ]]; then
  echo "Optional requirements file not found: $REQUIREMENTS_FILE" >&2
  exit 1
fi

pip install --upgrade pip setuptools wheel >/dev/null
pip install -r "$REQUIREMENTS_FILE"

OSPSUITE_VERSION="${OSPSUITE_VERSION:-}"
OSPSUITE_INDEX_URL="${OSPSUITE_INDEX_URL:-}"
OSPSUITE_WHEEL_URL="${OSPSUITE_WHEEL_URL:-}"
INSTALL_OSPSUITE="${INSTALL_OSPSUITE:-1}"

if [[ "$INSTALL_OSPSUITE" != "0" ]]; then
  if [[ -n "$OSPSUITE_WHEEL_URL" ]]; then
    pip install "$OSPSUITE_WHEEL_URL"
  elif [[ -n "$OSPSUITE_INDEX_URL" ]]; then
    if [[ -n "$OSPSUITE_VERSION" ]]; then
      pip install --extra-index-url "$OSPSUITE_INDEX_URL" "ospsuite==${OSPSUITE_VERSION}"
    else
      pip install --extra-index-url "$OSPSUITE_INDEX_URL" ospsuite
    fi
  else
    echo "[install_mechanistic_backends] OSPSuite not installed; set OSPSUITE_WHEEL_URL or OSPSUITE_INDEX_URL to fetch the official wheel." >&2
  fi
else
  echo "[install_mechanistic_backends] Skipping OSPSuite installation (INSTALL_OSPSUITE=0)." >&2
fi
