#!/usr/bin/env bash
set -euo pipefail

PLUGIN_NAME="native_illustration_compiler"
KRITA_RESOURCE_ROOT="${KRITA_RESOURCE_ROOT:-$HOME/Library/Application Support/Krita}"
PYKRITA_DIR="${KRITA_RESOURCE_ROOT}/pykrita"
DESKTOP_TARGET="${PYKRITA_DIR}/${PLUGIN_NAME}.desktop"
PLUGIN_TARGET="${PYKRITA_DIR}/${PLUGIN_NAME}"

remove_if_symlink() {
  local target="$1"
  if [ -L "${target}" ]; then
    rm -f "${target}"
    echo "Removed symlink: ${target}"
    return
  fi
  if [ -e "${target}" ]; then
    echo "Skipping non-symlink target: ${target}" >&2
    return
  fi
  echo "Not present: ${target}"
}

remove_if_symlink "${DESKTOP_TARGET}"
remove_if_symlink "${PLUGIN_TARGET}"

