#!/usr/bin/env bash
set -euo pipefail

REMOTE_SCRIPTS_DIR="$HOME/Music/Ableton/User Library/Remote Scripts"
ABLETONOSC_DIR="$REMOTE_SCRIPTS_DIR/AbletonOSC"

echo "=== AbletonOSC Installer ==="

if [ -d "$ABLETONOSC_DIR" ]; then
    echo "AbletonOSC already installed at: $ABLETONOSC_DIR"
    echo "To reinstall, remove it first: rm -rf \"$ABLETONOSC_DIR\""
    exit 0
fi

mkdir -p "$REMOTE_SCRIPTS_DIR"

echo "Cloning AbletonOSC into Remote Scripts..."
git clone https://github.com/ideoforms/AbletonOSC.git "$ABLETONOSC_DIR"

echo ""
echo "Installed successfully."
echo ""
echo "Next steps:"
echo "  1. Open Ableton Live"
echo "  2. Settings → Link, Tempo & MIDI"
echo "  3. Under Control Surface, select 'AbletonOSC'"
echo "  4. Input/Output: None"
