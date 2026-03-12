#!/usr/bin/env python3
import http.server
import urllib.request
import urllib.parse
import urllib.error
import os
import ssl
import re
import json
import gzip
import time
import random
import hashlib
from http.server import BaseHTTPRequestHandler

# ── User-Agent profiles ─────────────────────────────────────────────────────
UA_PROFILES = {
    'googlebot': {
        'ua': 'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'referer': 'https://www.google.com/',
        'x_forwarded_for': '66.249.66.1',
    },
    'googlebot_mobile': {
        'ua': 'Mozilla/5.0 (Linux; Android 6.0.1; Nexus 5X Build/MMB29P) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.7151.119 Mobile Safari/537.36 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
        'referer': 'https://www.google.com/',
        'x_forwarded_for': '66.249.66.1',
    },
    'bingbot': {
        'ua': 'Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)',
        'referer': 'https://www.bing.com/',
        'x_forwarded_for': '40.77.167.0',
    },
    'facebookbot': {
        'ua': 'facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)',
        'referer': 'https://www.facebook.com/',
    },
    'chrome_desktop': {
        'ua': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'referer': 'https://www.google.com/',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
        'accept_language': 'en-US,en;q=0.9',
        'sec_fetch': True,
    },
    'chrome_mobile': {
        'ua': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/124.0.6367.88 Mobile/15E148 Safari/604.1',
        'referer': 'https://www.google.com/',
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'accept_language': 'zh-TW,zh;q=0.9,en-US;q=0.8',
    },
    'economist': {
        'ua': 'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.6533.103 Mobile Safari/537.36 Liskov',
        'referer': 'https://www.google.com/',
    }
}

# ── Load BPC site rules ─────────────────────────────────────────────────────
BPC_SITES = {}
_script_dir = os.path.dirname(os.path.abspath(__file__))

def load_sites():
    global BPC_SITES
    paths = [
        os.path.join(_script_dir, 'bpc_sites.json'),
        os.path.join(_script_dir, '..', 'rules', 'bpc_sites.json')
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    BPC_SITES = json.load(f)
                    return True
            except: pass
    return False

load_sites()

UA_MAP = {
    'googlebot': 'googlebot',
    'bingbot': 'bingbot',
    'facebookbot': 'facebookbot',
    'desktop': 'chrome_desktop',
    'mobile': 'chrome_mobile',
    'economist': 'economist',
    None: 'chrome_mobile',
}

def get_profile(domain, ua_override=None):
    clean = domain.replace('www.', '')
    if 'economist.com' in clean:
        return UA_PROFILES['economist']
    rule = BPC_SITES.get(clean, {}) if BPC_SITES else {}
    ua_type = ua_override if ua_override and ua_override != 'auto' else rule.get('useragent')
    return UA_PROFILES.get(UA_MAP.get(ua_type, 'chrome_mobile'), UA_PROFILES['chrome_mobile'])

try:
    import brotli
    HAS_BROTLI = True
except:
    HAS_BROTLI = False

def build_request(url, profile, extra_headers=None):
    encodings = ['gzip', 'deflate']
    if HAS_BROTLI: encodings.append('br')
    headers = {
        'User-Agent': profile['ua'],
        'Accept': profile.get('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        'Accept-Language': profile.get('accept_language', 'en-US,en;q=0.9,zh-TW;q=0.8'),
        'Accept-Encoding': ', '.join(encodings),
        'Connection': 'keep-alive',
        'Cookie': '',
    }
    if 'referer' in profile: headers['Referer'] = profile['referer']
    if 'x_forwarded_for' in profile: headers['X-Forwarded-For'] = profile['x_forwarded_for']
    if extra_headers: headers.update(extra_headers)
    return urllib.request.Request(url, headers=headers)

BPC_CORE_SCRIPT = r"""
<script id="bpc-mobile-bypass">
(function() {
'use strict';
const hostname = location.hostname.replace(/^www\./, '');
const PAYWALL_SELECTORS = ['.paywall', '#paywall', '[class*="paywall"]', '[id*="paywall"]', '.gateway', '.subscription-required', '.piano-inline-offer'];
function removePaywalls() {
  PAYWALL_SELECTORS.forEach(sel => { try { document.querySelectorAll(sel).forEach(el => el.remove()); } catch(e) {} });
  try { document.body.style.overflow = 'auto'; document.documentElement.style.overflow = 'auto'; } catch(e) {}
}
removePaywalls();
setInterval(removePaywalls, 2000);
console.log('[BPC Vercel] Active on:', hostname);
})();
</script>
"""

def fetch_archive(url):
    archive_url = f'https://archive.ph/newest/{url}'
    try:
        req = build_request(archive_url, UA_PROFILES['chrome_desktop'])
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read()
            if resp.headers.get('Content-Encoding') == 'gzip': raw = gzip.decompress(raw)
            return raw.decode('utf-8', errors='replace')
    except: return None

class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass

    def do_GET(self):
        try:
            if not BPC_SITES: load_sites()
            parsed = urllib.parse.urlparse(self.path)
            
            if parsed.path == '/api/debug':
                self.serve_json({'cwd':os.getcwd(),'dir':_script_dir,'sites':len(BPC_SITES)})
                return

            if '/proxy' in parsed.path:
                self.handle_proxy(parsed)
            elif '/api/sites' in parsed.path:
                self.serve_json(BPC_SITES)
            elif '/api/status' in parsed.path:
                self.serve_json({'status':'ok','version':'3.1v3'})
            else:
                self.send_error(404)
        except Exception:
            import traceback
            self.send_response(500)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write(traceback.format_exc().encode('utf-8'))

    def serve_json(self, data):
        out = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(out)

    def handle_proxy(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        if 'url' not in query: return self.send_error(400)
        url = query['url'][0]
        if not url.startswith('http'): url = 'https://' + url
        profile = get_profile(urllib.parse.urlparse(url).hostname or '', query.get('ua',[None])[0])
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        try:
            req = build_request(url, profile)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                raw = resp.read()
                enc = resp.headers.get('Content-Encoding', '')
                if enc == 'gzip': raw = gzip.decompress(raw)
                elif enc == 'br' and HAS_BROTLI: raw = brotli.decompress(raw)
                
                ct = resp.headers.get('Content-Type', 'text/html')
                if 'text/html' in ct:
                    html = self.transform_html(raw.decode('utf-8', errors='replace'), url)
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
            self.wfile.write(str(e).encode('utf-8'))

    def transform_html(self, html, original_url):
        parsed = urllib.parse.urlparse(original_url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        html = re.sub(r'(src|href)="(/[^"]*)"', f'\\1="{base}\\2"', html)
        inject = f'<base href="{base}/">\n' + BPC_CORE_SCRIPT
        if '</head>' in html.lower():
            html = re.sub(r'(</head>)', inject + r'\1', html, flags=re.IGNORECASE)
        else:
            html = inject + html
        return html

# Export for Vercel
app = handler
