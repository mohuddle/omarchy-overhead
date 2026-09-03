#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
PLUGIN_ID="io.github.mohuddle.overhead"
PLUGIN_DIR="${HOME}/.config/omarchy/plugins/${PLUGIN_ID}"

mkdir -p "$BIN_DIR"
chmod +x "$ROOT/bin/overhead"
ln -sfn "$ROOT/bin/overhead" "$BIN_DIR/overhead"

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
  mkdir -p "$PLUGIN_DIR/bin" "$PLUGIN_DIR/overhead"
  cp -r "$ROOT"/manifest.json "$ROOT"/BarWidget.qml "$ROOT"/Panel.qml "$ROOT"/Service.qml \
    "$ROOT"/Model.js "$ROOT"/PlaneIcon.qml "$ROOT"/icon.svg "$ROOT"/preview.png "$PLUGIN_DIR/"
  cp "$ROOT/bin/overhead" "$PLUGIN_DIR/bin/"
  chmod +x "$PLUGIN_DIR/bin/overhead"
  cp -r "$ROOT/overhead/." "$PLUGIN_DIR/overhead/"
  find "$PLUGIN_DIR" -type d -name '__pycache__' -prune -exec rm -rf {} +
  touch "$PLUGIN_DIR" "$PLUGIN_DIR/BarWidget.qml" "$PLUGIN_DIR/Service.qml"
}

install_plugin

if command -v omarchy >/dev/null; then
  omarchy plugin validate "$PLUGIN_DIR"
  omarchy plugin enable "$PLUGIN_ID" --section right >/dev/null 2>&1 || true
  omarchy restart shell >/dev/null 2>&1 || omarchy-shell shell rescanPlugins >/dev/null 2>&1 || true
  echo "bar widget: omarchy bar move $PLUGIN_ID --section right"
fi

echo
echo "ready. GeoClue is not installed and is not required."
echo "  overhead tui"
echo "then m and a ZIP or city (72714, Santa Monica, 34.05 -118.24)."
echo
echo "optional — device location later:"
echo "  omarchy pkg add geoclue"
echo "  sudo cp $ROOT/scripts/geoclue-omarchy-overhead.conf /etc/geoclue/conf.d/"
