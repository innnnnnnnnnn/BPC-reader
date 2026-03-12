#!/bin/bash
# BPC Mobile Reader — 啟動腳本
# Usage: ./start.sh [port]

PORT=${1:-8080}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║         BPC Mobile Reader Launcher           ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# Find python3
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)
if [ -z "$PYTHON" ]; then
  echo "❌ 錯誤：找不到 Python 3，請安裝 Python 3"
  exit 1
fi

echo "✓ Python: $PYTHON"
echo "✓ 工作目錄: $SCRIPT_DIR"
echo "✓ 端口: $PORT"
echo ""

# Get local IP for display
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo "查詢中...")
echo "📱 在手機上請連接同一 WiFi，然後開啟："
echo "   http://${LOCAL_IP}:${PORT}"
echo ""
echo "💻 本機電腦開啟："
echo "   http://localhost:${PORT}"
echo ""
echo "按 Ctrl+C 停止伺服器"
echo "─────────────────────────────────────────────"

cd "$SCRIPT_DIR"
PORT=$PORT $PYTHON server.py
