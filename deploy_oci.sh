#!/bin/bash
# 🚀 部署 BPC Mobile Reader 到 OCI 雲端主機

# --- 配置區 (請確認以下資訊) ---
REMOTE_HOST="stockbot"  # 使用您 ~/.ssh/config 中的別名，或改為 ubuntu@170.9.12.217
REMOTE_DIR="~/bpc-mobile-reader"
PORT=8080
# ----------------------------

echo "📦 正在同步檔案到 OCI ($REMOTE_HOST)..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude '.DS_Store' \
    ./ "$REMOTE_HOST:$REMOTE_DIR/"

echo "🛠️ 正在遠端安裝必要套件 (Python3, Brotli, Chardet)..."
ssh "$REMOTE_HOST" "
    sudo apt-get update -y && \
    sudo apt-get install -y python3-pip && \
    pip3 install brotli chardet --break-system-packages 2>/dev/null || pip3 install brotli chardet
"

echo "⏳ 正在啟動伺服器 (背景執行)..."
ssh "$REMOTE_HOST" "
    cd $REMOTE_DIR
    kill \$(lsof -ti:$PORT) 2>/dev/null
    nohup python3 server.py > server.log 2>&1 &
    sleep 2
    ps aux | grep server.py | grep -v grep
"

echo ""
echo "✅ 部署完成！"
echo "🌐 您的 OCI 網址為：http://170.9.12.217:$PORT"
echo ""
echo "⚠️ 注意：如果無法連線，請確保您已在 OCI 後台開啟 TCP $PORT 埠："
echo "1. 登入 OCI Console > Networking > VCN > Security Lists"
echo "2. 新增 Ingress Rule: CIDR 0.0.0.0/0, TCP Port $PORT"
echo "3. 在 OCI 主機內執行以下指令開啟防火牆："
echo "   sudo ufw allow $PORT/tcp"
echo "------------------------------------------------"
