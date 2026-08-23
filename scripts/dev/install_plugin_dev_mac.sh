#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PLUGIN_NAMES=("native_illustration_compiler" "nic_agent_bridge")
KRITA_RESOURCE_ROOT="${KRITA_RESOURCE_ROOT:-$HOME/Library/Application Support/Krita}"
PYKRITA_DIR="${KRITA_RESOURCE_ROOT}/pykrita"

mkdir -p "${PYKRITA_DIR}"

ensure_relinkable() {
  local target="$1"
  if [ -L "${target}" ]; then
    rm -f "${target}"
    return
  fi
  if [ -e "${target}" ]; then
    echo "Refusing to replace existing non-symlink target: ${target}" >&2
    echo "Remove it manually or rename it before installing dev mode." >&2
    exit 1
  fi
}

for PLUGIN_NAME in "${PLUGIN_NAMES[@]}"; do
  DESKTOP_SRC="${REPO_ROOT}/pykrita/${PLUGIN_NAME}.desktop"
  PLUGIN_SRC_DIR="${REPO_ROOT}/pykrita/${PLUGIN_NAME}"
  DESKTOP_TARGET="${PYKRITA_DIR}/${PLUGIN_NAME}.desktop"
  PLUGIN_TARGET="${PYKRITA_DIR}/${PLUGIN_NAME}"

  ensure_relinkable "${DESKTOP_TARGET}"
  ensure_relinkable "${PLUGIN_TARGET}"

  ln -s "${DESKTOP_SRC}" "${DESKTOP_TARGET}"
  ln -s "${PLUGIN_SRC_DIR}" "${PLUGIN_TARGET}"

  echo "Installed dev-mode Krita plugin symlinks:"
  echo "  desktop -> ${DESKTOP_TARGET}"
  echo "  plugin  -> ${PLUGIN_TARGET}"
done

echo
echo "Next steps:"
echo "  1. Start Krita"
echo "  2. Open Settings -> Configure Krita... -> Python Plugin Manager"
printf '  3. Enable %s\n' "${PLUGIN_NAMES[*]}"
echo "  4. Restart Krita"
echo
echo "Path summary:"
python "${REPO_ROOT}/scripts/dev/print_krita_dev_paths.py"
