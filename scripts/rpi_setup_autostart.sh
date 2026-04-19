#!/bin/bash
# rpi_setup_autostart.sh
# Run this ONCE on the Raspberry Pi to register the autostart entry.
# Usage (from the project root):
#   bash scripts/rpi_setup_autostart.sh

set -e

PROJECT_DIR="/home/pi/yvnalv/projects/Training-Project"
AUTOSTART_DIR="/home/pi/.config/autostart"

echo "=== VialVision autostart setup ==="

# ── 1. Make all scripts executable ───────────────────────────────
chmod +x "$PROJECT_DIR/scripts/rpi_start_server.sh"
chmod +x "$PROJECT_DIR/scripts/rpi_autostart.sh"
chmod +x "$PROJECT_DIR/scripts/rpi_setup_autostart.sh"
echo "✓ Scripts marked executable."

# ── 2. Ensure scripts have Unix (LF) line endings ─────────────────
# Needed when the project was edited on Windows.
if command -v dos2unix &> /dev/null; then
    dos2unix "$PROJECT_DIR/scripts/rpi_start_server.sh"  2>/dev/null
    dos2unix "$PROJECT_DIR/scripts/rpi_autostart.sh"     2>/dev/null
    dos2unix "$PROJECT_DIR/scripts/vialvision.desktop"   2>/dev/null
    echo "✓ Line endings converted to Unix (LF)."
else
    # dos2unix not installed — use sed as fallback
    sed -i 's/\r//' "$PROJECT_DIR/scripts/rpi_start_server.sh"
    sed -i 's/\r//' "$PROJECT_DIR/scripts/rpi_autostart.sh"
    sed -i 's/\r//' "$PROJECT_DIR/scripts/vialvision.desktop"
    echo "✓ Line endings converted (sed fallback)."
fi

# ── 3. Install the XDG autostart entry ────────────────────────────
mkdir -p "$AUTOSTART_DIR"
cp "$PROJECT_DIR/scripts/vialvision.desktop" "$AUTOSTART_DIR/vialvision.desktop"
echo "✓ Autostart entry installed to $AUTOSTART_DIR/vialvision.desktop"

# ── 4. Create an empty log file so it is always writable ──────────
touch "$PROJECT_DIR/server.log"
echo "✓ Log file ready: $PROJECT_DIR/server.log"

echo ""
echo "Setup complete. Reboot the Pi to test:"
echo "  sudo reboot"
echo ""
echo "To watch server logs live after reboot:"
echo "  tail -f $PROJECT_DIR/server.log"
