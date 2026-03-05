#!/usr/bin/env bash
set -euo pipefail

PASS="\033[32m✓\033[0m"
FAIL="\033[31m✗\033[0m"
WARN="\033[33m!\033[0m"
errors=0

echo "=== BlessDog Environment Check ==="
echo ""

# Python
if command -v python3 &>/dev/null; then
    py_version=$(python3 --version 2>&1)
    echo -e "$PASS Python3: $py_version"
else
    echo -e "$FAIL Python3 not found"
    ((errors++))
fi

# python-osc
if python3 -c "import pythonosc" 2>/dev/null; then
    echo -e "$PASS python-osc installed"
else
    echo -e "$FAIL python-osc not installed (pip install python-osc)"
    ((errors++))
fi

# AbletonOSC
ABLETONOSC_DIR="$HOME/Music/Ableton/User Library/Remote Scripts/AbletonOSC"
if [ -d "$ABLETONOSC_DIR" ]; then
    echo -e "$PASS AbletonOSC found at Remote Scripts"
else
    echo -e "$WARN AbletonOSC not found — run: bash scripts/install_abletonosc.sh"
fi

# Port 11000 (Ableton listens)
if lsof -i :11000 &>/dev/null; then
    echo -e "$PASS Port 11000 in use (Ableton likely listening)"
else
    echo -e "$WARN Port 11000 not in use (Ableton not running or AbletonOSC not active)"
fi

# Port 11001 (our listener)
if lsof -i :11001 &>/dev/null; then
    echo -e "$WARN Port 11001 already in use (another BlessDog instance?)"
else
    echo -e "$PASS Port 11001 available for response listener"
fi

echo ""
if [ $errors -gt 0 ]; then
    echo -e "$FAIL $errors error(s) found. Fix them before proceeding."
    exit 1
else
    echo -e "$PASS Environment looks good."
fi
