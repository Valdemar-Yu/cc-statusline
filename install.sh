#!/usr/bin/env bash
# Install cc-statusline into Claude Code.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/statusline.py"
DEST_DIR="${HOME}/.claude"
DEST="${DEST_DIR}/statusline.py"
SETTINGS="${DEST_DIR}/settings.json"

command -v python3 >/dev/null 2>&1 || { echo "❌ python3 not found"; exit 1; }
mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST"
echo "✅ Copied statusline.py -> $DEST"

SNIPPET='  "statusLine": {
    "type": "command",
    "command": "python3 '"$DEST"'"
  }'

if [ -f "$SETTINGS" ] && grep -q '"statusLine"' "$SETTINGS"; then
  echo "ℹ️  $SETTINGS already has a \"statusLine\" entry — not modifying it."
  echo "    If you want this one, set its command to: python3 $DEST"
elif [ -f "$SETTINGS" ]; then
  echo "ℹ️  $SETTINGS exists but has no statusLine. Add this block inside the top-level object:"
  echo ""
  echo "$SNIPPET"
else
  cat > "$SETTINGS" <<EOF
{
$SNIPPET
}
EOF
  echo "✅ Created $SETTINGS with the statusLine block."
fi

echo ""
echo "Done. Open a NEW Claude Code window to see the status line."
