#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
PLUGIN_ID="io.github.mohuddle.overhead"
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/${PLUGIN_ID}"

mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/bin/overhead" "$BIN_DIR/overhead"
chmod +x "$ROOT/bin/overhead"

install_plugin() {
  mkdir -p "$(dirname "$PLUGIN_DIR")"
  if [[ -L "$PLUGIN_DIR" ]]; then
    echo "replacing plugin symlink with a real plugin folder"
    rm -f "$PLUGIN_DIR"
  fi
  if [[ -d "$PLUGIN_DIR" && -f "$PLUGIN_DIR/manifest.json" ]]; then
    if [[ "$PLUGIN_DIR" -ef "$ROOT" || -d "$PLUGIN_DIR/.git" ]]; then
      echo "plugin already lives at $PLUGIN_DIR"
      return
    fi
  fi
  echo "installing bar plugin into $PLUGIN_DIR"
  mkdir -p "$PLUGIN_DIR"
  cp -r "$ROOT/plugin/." "$PLUGIN_DIR/"
  touch "$PLUGIN_DIR" "$PLUGIN_DIR/BarWidget.qml" "$PLUGIN_DIR/PlaneIcon.qml"
}

install_plugin

if command -v omarchy >/dev/null; then
  omarchy plugin validate "$PLUGIN_DIR"
  omarchy plugin enable "$PLUGIN_ID" --section right >/dev/null 2>&1 || true
  omarchy restart shell >/dev/null 2>&1 || omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  echo "bar widget: omarchy bar move $PLUGIN_ID --section right"
fi

echo
echo "ready. open the TUI:"
echo "  overhead tui"
echo "press a to allow location, or m to type coordinates / a place name."
