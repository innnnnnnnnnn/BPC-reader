from flask import Flask, request, Response, jsonify
import urllib.request
import urllib.parse
import ssl
import gzip
import os
import re
import json
import traceback

app = Flask(__name__)

# 資源定位
_dir = os.path.dirname(os.path.abspath(__file__))
BPC_SITES = {}

def get_sites():
    global BPC_SITES
    if BPC_SITES: return BPC_SITES
    p = os.path.join(_dir, 'bpc_sites.json')
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                BPC_SITES = json.load(f)
        except: pass
    return BPC_SITES

@app.route('/api/status')
def status():
    return jsonify({"status": "ok", "version": "Flask-3.2", "sites": len(get_sites())})

@app.route('/proxy')
def proxy():
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400
    
    if not url.startswith('http'): url = 'https://' + url
    
    # 決定 User-Agent
    ua = 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
    if 'economist.com' in url:
        ua = 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.103 Mobile Safari/537.36 Liskov'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': ua, 'Accept-Encoding': 'gzip'})
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            raw = resp.read()
            if resp.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            
            ct = resp.headers.get('Content-Type', 'text/html')
            
            if 'text/html' in ct:
                try:
                    html = raw.decode('utf-8', errors='replace')
                    # 基礎注入：修復相對路徑
                    base_origin = f"{urllib.parse.urlsplit(url).scheme}://{urllib.parse.urlsplit(url).netloc}"
                    html = html.replace('</head>', f'<base href="{base_origin}/">\n</head>', 1)
                    return html
                except:
                    return raw, 200, {'Content-Type': ct}
            
            return Response(raw, content_type=ct)
            
    except Exception as e:
        return f"Proxy Error: {str(e)}\n\n{traceback.format_exc()}", 500

# Vercel 需要導出 app
# app = app (Flask 物件本身就是 WSGI handler)
