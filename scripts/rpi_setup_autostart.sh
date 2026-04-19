#!/bin/bash
# rpi_setup_autostart.sh
# Run this ONCE on the Raspberry Pi to register the autostart entry.
# Usage (from the project root):
#   bash scripts/rpi_setup_autostart.sh

set -e

PROJECT_DIR="/home/pi/yvnalv/projects/Training-Project"
AUTOSTART_DIR="/home/pi/.config/autostart"
WAYFIRE_INI="/home/pi/.config/wayfire.ini"

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

# ── 3. Install the XDG autostart entry (fallback method) ──────────
mkdir -p "$AUTOSTART_DIR"
cp "$PROJECT_DIR/scripts/vialvision.desktop" "$AUTOSTART_DIR/vialvision.desktop"
echo "✓ XDG autostart entry installed to $AUTOSTART_DIR/vialvision.desktop"

# ── 4. Register with Wayfire directly (primary method) ────────────
# Wayfire reads [autostart] entries from ~/.config/wayfire.ini at login.
# This is more reliable than XDG autostart on Wayfire/Wayland.
if [ -f "$WAYFIRE_INI" ]; then
    # Remove any previous vialvision entry to avoid duplicates
    sed -i '/^vialvision\s*=/d' "$WAYFIRE_INI"

    # Append under [autostart] section if it exists, else add the section
    if grep -q '^\[autostart\]' "$WAYFIRE_INI"; then
        sed -i '/^\[autostart\]/a vialvision = /bin/bash '"$PROJECT_DIR"'/scripts/rpi_autostart.sh' "$WAYFIRE_INI"
        echo "✓ Wayfire autostart entry added to existing [autostart] section."
    else
        printf '\n[autostart]\nvialvision = /bin/bash %s/scripts/rpi_autostart.sh\n' "$PROJECT_DIR" >> "$WAYFIRE_INI"
        echo "✓ Wayfire [autostart] section created and entry added."
    fi
else
    echo "⚠ $WAYFIRE_INI not found — only XDG autostart installed."
    echo "  If Wayfire autostart still does not work, manually add to wayfire.ini:"
    echo "  [autostart]"
    echo "  vialvision = /bin/bash $PROJECT_DIR/scripts/rpi_autostart.sh"
fi

# ── 5. Create an empty log file so it is always writable ──────────
touch "$PROJECT_DIR/server.log"
echo "✓ Log file ready: $PROJECT_DIR/server.log"

echo ""
echo "Setup complete. Reboot the Pi to test:"
echo "  sudo reboot"
echo ""
echo "To watch server logs live after reboot:"
echo "  tail -f $PROJECT_DIR/server.log"
