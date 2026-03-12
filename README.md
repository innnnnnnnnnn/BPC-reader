# BPC Mobile Reader ⚡

> 整合 **Bypass Paywalls Clean** 的手機閱讀器 — 可在 WiFi 上讓手機瀏覽付費牆網站

## 功能特色

| 功能 | 說明 |
|------|------|
| ⚡ **462 個網站規則** | 直接讀取 `bypass-paywalls-chrome-clean` 的完整規則 |
| 🤖 **智能 UA 偽裝** | 依網站規則自動選擇 Googlebot / Facebookbot / Mobile UA |
| 💉 **Bypass 腳本注入** | 自動移除 paywall overlay、解鎖被截斷內容、攔截計費請求 |
| 📖 **閱讀模式** | 精簡版面，移除廣告與側欄，適合長文閱讀 |
| 🔍 **自動補全** | 輸入時即時搜尋 BPC 支援的網站 |
| 🕐 **瀏覽歷史** | 本地儲存，可刪除 |
| 📱 **手機優先設計** | PWA 風格，全螢幕，深色主題 |

## 快速開始

```bash
cd bpc-mobile-reader
./start.sh
```

然後：
- **本機**：開啟 `http://localhost:8080`
- **手機**：連接同一 WiFi，開啟 `http://[Mac的IP]:8080`

## 專案結構

```
bpc-mobile-reader/
├── index.html          # 前端介面（單一檔案，含所有 CSS + JS）
├── server.py           # Python 後端代理伺服器
├── start.sh            # 啟動腳本（顯示本機 IP）
└── rules/
    └── bpc_sites.json  # 從 bypass-paywalls-chrome-clean 提取的 462 個網站規則
```

## 架構說明

```
手機瀏覽器
    ↓  HTTP
BPC Mobile Reader (localhost:8080)
    ├── index.html (前端 UI)
    └── /proxy?url=...  (後端代理)
            ↓  帶偽裝 UA 的 HTTPS 請求
        目標付費牆網站
            ↓  HTML 回應
        server.py 注入 bypass 腳本
            ↓  修改後的 HTML
        手機 iframe 顯示
```

## Bypass 技術說明

### 1. 代理層 (server.py)
- **UA 偽裝**：依 BPC 規則選擇 Googlebot / Facebookbot / 一般 UA
- **清除 Cookie**：防止網站追蹤已讀文章計數 (metering)
- **加 Referer**：模擬從 Google 搜尋結果點入
- **移除 HSTS**：防止強制 HTTPS 重定向循環

### 2. 注入腳本層 (BYPASS_SCRIPT)
- **DOM 移除**：移除 `.paywall`、`.piano`、`.tp-backdrop` 等元素
- **捲動解鎖**：強制 `overflow: auto`
- **高度解鎖**：移除 `max-height` 內容截斷
- **`fetch` 攔截**：偽造訂閱 API 回應 `{"access":true,"entitled":true}`
- **`localStorage` 清除**：移除文章計數記錄
- **Script 攔截**：阻止 `tinypass.com`、`piano.io`、`poool.fr` 等腳本載入

## 備用方案

當繞過失敗（403 / Cloudflare 擋）時，內建備用：
- [Freedium](https://freedium.cfd) — Medium 文章
- [Archive.is](https://archive.is) — 快照讀取
- [12ft.io](https://12ft.io) — 通用 paywall bypass

## 注意事項

- 本工具僅供個人學習研究使用
- 部分網站（NYT、Cloudflare 保護站）有強力反爬蟲，可能無法繞過
- 伺服器在本機運行，不儲存任何瀏覽資料
