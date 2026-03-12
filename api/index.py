from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse
import os
import ssl
import re
import json
import gzip

# ── Globals ────────────────────────────────────────────────────────────────
BPC_SITES = {}
UA_PROFILES = {
    'googlebot': {'ua': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)', 'referer': 'https://www.google.com/', 'x_forwarded_for': '66.249.66.1'},
    'chrome_desktop': {'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36', 'referer': 'https://www.google.com/'},
    'chrome_mobile': {'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.6367.88 Mobile/15E148 Safari/604.1', 'referer': 'https://www.google.com/'},
    'economist': {'ua': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.103 Mobile Safari/537.36 Liskov', 'referer': 'https://www.google.com/'}
}

def load_sites():
    global BPC_SITES
    if BPC_SITES: return
    _dir = os.path.dirname(os.path.abspath(__file__))
    for p in [os.path.join(_dir, 'bpc_sites.json'), os.path.join(_dir, '..', 'rules', 'bpc_sites.json')]:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    BPC_SITES = json.load(f)
                    break
            except: pass

class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        load_sites()
        parsed = urllib.parse.urlparse(self.path)
        
        if parsed.path == '/api/status':
            return self.send_json({'status': 'ok', 'version': '3.1.1'})
        
        if '/proxy' in parsed.path:
            return self.handle_proxy(parsed)
            
        self.send_error(404)

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def handle_proxy(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        url = query.get('url', [None])[0]
        if not url: return self.send_error(400)
        if not url.startswith('http'): url = 'https://' + url
        
        # Simple profile selection
        domain = urllib.parse.urlparse(url).hostname or ''
        profile = UA_PROFILES['economist'] if 'economist.com' in domain else UA_PROFILES['chrome_mobile']
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': profile['ua'], 'Referer': profile.get('referer', ''), 'Accept-Encoding': 'gzip'})
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                raw = resp.read()
                if resp.headers.get('Content-Encoding') == 'gzip': raw = gzip.decompress(raw)
                
                ct = resp.headers.get('Content-Type', 'text/html')
                if 'text/html' in ct:
                    html = raw.decode('utf-8', errors='replace')
                    # Very basic injection
                    html = html.replace('</head>', f'<base href="{url}">\n</head>', 1)
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(html.encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', ct)
                    self.end_headers()
                    self.wfile.write(raw)
        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(e).encode())
