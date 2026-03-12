#!/bin/bash
# 啟動伺服器並產生公開網址

PORT=8080
PYTHON=$(which python3)

echo "🚀 正在啟動 BPC 伺服器..."
kill $(lsof -ti:$PORT) 2>/dev/null
PORT=$PORT $PYTHON server.py &

sleep 2

echo "🌐 正在產生公開網址..."
echo "------------------------------------------------"
npx localtunnel --port $PORT
