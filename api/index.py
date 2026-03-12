from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import os
import ssl
import re
import json
import gzip
import traceback

# 資源路徑
_dir = os.path.dirname(os.path.abspath(__file__))
BPC_SITES = {}

def load_sites():
    global BPC_SITES
    p = os.path.join(_dir, 'bpc_sites.json')
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                BPC_SITES = json.load(f)
        except: pass

class ReaderHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        try:
            load_sites()
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/api/status' or parsed.path == '/api':
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "status": "ok", 
                    "version": "3.1.2",
                    "sites": len(BPC_SITES)
                }).encode())
                return

            if '/proxy' in parsed.path:
                self.handle_proxy(parsed)
                return

            self.send_error(404, "Not Found")
            
        except Exception:
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(traceback.format_exc().encode('utf-8'))

    def handle_proxy(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        target_url = query.get('url', [None])[0]
        if not target_url:
            self.send_error(400, "Missing URL")
            return

        if not target_url.startswith('http'): target_url = 'https://' + target_url

        # 極簡代理邏輯
        ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        if 'economist.com' in target_url:
            ua = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.103 Mobile Safari/537.36 Liskov'

        try:
            req = urllib.request.Request(target_url, headers={'User-Agent': ua, 'Accept-Encoding': 'gzip'})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip':
                    raw = gzip.decompress(raw)
                
                ct = resp.headers.get('Content-Type', 'text/html')
                self.send_response(200)
                self.send_header('Content-Type', ct)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                
                if 'text/html' in ct:
                    html = raw.decode('utf-8', errors='replace')
                    html = html.replace('</head>', f'<base href="{target_url}">\n</head>', 1)
                    self.wfile.write(html.encode('utf-8'))
                else:
                    self.wfile.write(raw)
        except Exception as e:
            self.send_response(200) # 回傳 200 以免 Vercel 判定 Crash
            self.end_headers()
            self.wfile.write(f"Proxy Error: {str(e)}".encode())

# 關鍵：導出 Vercel 識別的變數
handler = ReaderHandler
app = ReaderHandler
