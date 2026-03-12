#!/usr/bin/env python3
"""
BPC Mobile Reader — Advanced Server v3.0
深度整合 Bypass Paywalls Clean 的實際技術：
1. 真實瀏覽器 Header 指紋 (TLS fingerprint simulation)
2. Archive.is fallback 自動化
3. BPC content script 注入 (完整版)
4. 反 bot-detection 技術
"""

import http.server
import socketserver
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

PORT = int(os.environ.get('PORT', 8080))
_script_dir = os.path.dirname(os.path.abspath(__file__))

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
def load_sites():
    global BPC_SITES
    # Try multiple common relative paths in Vercel/Local
    paths = [
        os.path.join(_script_dir, '..', 'rules', 'bpc_sites.json'),
        os.path.join(_script_dir, 'rules', 'bpc_sites.json'),
        os.path.join(os.getcwd(), 'rules', 'bpc_sites.json')
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

# ua_type → profile key
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
    rule = BPC_SITES.get(clean, {})
    ua_type = ua_override if ua_override and ua_override != 'auto' else rule.get('useragent')
    return UA_PROFILES.get(UA_MAP.get(ua_type, 'chrome_mobile'), UA_PROFILES['chrome_mobile'])

try:
    import brotli
    HAS_BROTLI = True
except ImportError:
    HAS_BROTLI = False

def build_request(url, profile, extra_headers=None):
    encodings = ['gzip', 'deflate']
    if HAS_BROTLI:
        encodings.append('br')
    
    headers = {
        'User-Agent': profile['ua'],
        'Accept': profile.get('accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'),
        'Accept-Language': profile.get('accept_language', 'en-US,en;q=0.9,zh-TW;q=0.8'),
        'Accept-Encoding': ', '.join(encodings),
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Cache-Control': 'max-age=0',
        # Kill cookies to reset metering
        'Cookie': '',
    }
    if 'referer' in profile:
        headers['Referer'] = profile['referer']
    if 'x_forwarded_for' in profile:
        headers['X-Forwarded-For'] = profile['x_forwarded_for']
    if profile.get('sec_fetch'):
        headers['Sec-Fetch-Dest'] = 'document'
        headers['Sec-Fetch-Mode'] = 'navigate'
        headers['Sec-Fetch-Site'] = 'cross-site'
        headers['Sec-Fetch-User'] = '?1'
    if extra_headers:
        headers.update(extra_headers)
    return urllib.request.Request(url, headers=headers)

# ── BPC Bypass Script — full client-side implementation ─────────────────────
#    This is the core of what the Chrome extension does, adapted for injection.
BPC_CORE_SCRIPT = r"""
<script id="bpc-mobile-bypass">
(function() {
'use strict';

// ── Detect current domain ─────────────────────────────────────────
const hostname = location.hostname.replace(/^www\./, '');

// ── 1. Remove paywall UI elements ─────────────────────────────────
const PAYWALL_SELECTORS = [
  // Generic
  '.paywall', '#paywall', '[class*="paywall"]', '[id*="paywall"]',
  '.gateway', '#gateway', '[class*="gateway"]',
  '.subscription-required', '.subscriber-only', '.subscriber-wall',
  '.article-paywall', '.content-locked', '.content-premium',
  '.metered-content', '.article-metered-wall',
  // Piano / TinyPass
  '.tp-backdrop', '.tp-modal', '.tp-iframe-wrapper', '[data-tpid]',
  '.piano-inline-offer', '#piano-id',
  // Poool
  '.poool-widget', '#poool-widget',
  // Sophi
  '[class*="sophi"]',
  // Zephr
  '.zephr-registration', '.zephr-paywall', '[class*="zephr"]',
  // Generic fade/blur paywalls
  '.fade-paywall', '.article-body-fade', '.truncation-gradient',
  '[style*="background-image: linear-gradient"][style*="rgba(255"]',
  // Registration walls
  '.registration-wall', '.reg-wall', '#reg-wall',
  '.login-required', '.sign-in-required',
  // Specific
  'div#dynamic-paywall-overlay',
  '.leaky_paywall_message', '#leaky_paywall_message',
  '.pw-container', '.pw-overlay',
  '.article__restricted',
  '#cx-snippet', '.cx-snippet',
  'div[class*="_gate"]', 'div[class*="Gate"]',
  '.SubscriberContent', '.subscriber-content',
  'div#bp_paywall_content',
  // Bloomberg
  '[class*="paywall-barrier"]', '[class*="BarrierPage"]',
  // WSJ
  '#cx-region-article-paywall',
  // NYT
  '#gateway-content', '#meter-paywall',
];

const BLUR_FIXES = [
  '[style*="filter: blur"]',
  '[style*="filter:blur"]',
  '[class*="blur"]',
];

const SCROLL_LOCKS = [
  'html[style*="overflow: hidden"]',
  'body[style*="overflow: hidden"]',
  'html[style*="overflow:hidden"]',
  'body[style*="overflow:hidden"]',
];

const CONTENT_REVEAL = [
  // Remove max-height truncation
  '[style*="max-height: 150px"]',
  '[style*="max-height:150px"]',
  '[style*="max-height: 200px"]',
  '[class*="article-body"][style*="max-height"]',
  '[class*="story-body"][style*="max-height"]',
];

function removePaywalls() {
  // Remove paywall overlays
  PAYWALL_SELECTORS.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => el.remove());
    } catch(e) {}
  });

  // Remove blur effects
  BLUR_FIXES.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => {
        el.style.filter = 'none';
        el.style.webkitFilter = 'none';
      });
    } catch(e) {}
  });

  // Fix scroll locks
  try {
    document.body.style.overflow = 'auto';
    document.documentElement.style.overflow = 'auto';
    document.body.style.position = 'relative';
    document.documentElement.removeAttribute('style');
  } catch(e) {}
  SCROLL_LOCKS.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => el.removeAttribute('style'));
    } catch(e) {}
  });

  // Fix content truncation
  CONTENT_REVEAL.forEach(sel => {
    try {
      document.querySelectorAll(sel).forEach(el => {
        el.style.maxHeight = 'none';
        el.style.height = 'auto';
        el.style.overflow = 'visible';
      });
    } catch(e) {}
  });
}

// ── 2. Block paywall scripts BEFORE they load ─────────────────────
const BLOCKED_SCRIPT_PATTERNS = [
  'tinypass.com', 'piano.io',
  'poool.fr',
  'sophi.io',
  'wallkit.net',
  'cxense.com',
  'pelcro.com',
  'blueconic.net',
  'zephr.com',
  'axate.io',
  '/paywall', 'paywall.js',
  'subscriber.js',
  'metering', 'meter.js',
  '.cm.bloomberg.com/',
  'assets.bwbx.io/s3/javelin/',  // bloomberg transporter
  '/evercookie',
  '/access.js',
];

// Override appendChild to block paywall scripts
const _origHeadAppend = Document.prototype.createElement;
try {
  const origAppend = Element.prototype.appendChild;
  Element.prototype.appendChild = function(node) {
    if (node && node.tagName === 'SCRIPT') {
      const src = node.src || '';
      if (BLOCKED_SCRIPT_PATTERNS.some(p => src.includes(p))) {
        console.log('[BPC] Blocked:', src);
        return node;
      }
    }
    return origAppend.call(this, node);
  };
} catch(e) {}

// ── 3. Override fetch to spoof subscription APIs ──────────────────
const SUBSCRIPTION_PATTERNS = [
  '/api/meter', '/api/entitlement', '/api/access',
  'metering', 'paywall', 'subscription-status',
  'user_access', 'article_access', 'content_access',
  '/check-subscription', '/subscription-check',
  'tinypass', 'piano', 'cxense',
  '.sophi.io/access',
  'wallkit.net',
];

const _origFetch = window.fetch;
window.fetch = function(input, init) {
  const url = (typeof input === 'string') ? input : (input.url || '');
  if (SUBSCRIPTION_PATTERNS.some(p => url.toLowerCase().includes(p.toLowerCase()))) {
    console.log('[BPC] Spoofing fetch:', url);
    return Promise.resolve(new Response(JSON.stringify({
      access: true, entitled: true, subscribed: true,
      metered: false, remaining: 999, allowed: true,
      hasAccess: true, isSubscriber: true,
      status: 'authenticated', premium: false,
      data: { access: true, subscribed: true }
    }), {
      status: 200,
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      }
    }));
  }
  return _origFetch.apply(this, arguments);
};

// ── 4. Override XHR ───────────────────────────────────────────────
const _origXHROpen = XMLHttpRequest.prototype.open;
const _origXHRSend = XMLHttpRequest.prototype.send;
const _blockedXhrs = new WeakSet();
XMLHttpRequest.prototype.open = function(method, url) {
  if (typeof url === 'string' && SUBSCRIPTION_PATTERNS.some(p => url.toLowerCase().includes(p.toLowerCase()))) {
    console.log('[BPC] Blocking XHR:', url);
    _blockedXhrs.add(this);
  }
  return _origXHROpen.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function() {
  if (_blockedXhrs.has(this)) {
    Object.defineProperty(this, 'readyState', { get: () => 4 });
    Object.defineProperty(this, 'status', { get: () => 200 });
    Object.defineProperty(this, 'responseText', { get: () => '{"access":true,"entitled":true,"subscribed":true}' });
    setTimeout(() => {
      try { this.onreadystatechange && this.onreadystatechange(); } catch(e) {}
      try { this.onload && this.onload(); } catch(e) {}
    }, 10);
    return;
  }
  return _origXHRSend.apply(this, arguments);
};

// ── 5. Clear metering data from storage ──────────────────────────
function clearMeteringStorage() {
  const METER_PATTERNS = [
    'articlecount', 'freeread', 'freeviews', 'freearticle',
    'meter', 'paywall', 'subscription', 'premium',
    'piano_', 'tp_', 'blaize_', 'cxense', 'hitcount',
    'articlesleft', 'remainingarticle',
  ];
  try {
    [...Object.keys(localStorage)].forEach(k => {
      if (METER_PATTERNS.some(p => k.toLowerCase().includes(p))) {
        localStorage.removeItem(k);
      }
    });
    [...Object.keys(sessionStorage)].forEach(k => {
      if (METER_PATTERNS.some(p => k.toLowerCase().includes(p))) {
        sessionStorage.removeItem(k);
      }
    });
  } catch(e) {}
}

// ── 6. Site-specific fixes ────────────────────────────────────────
function siteSpecificFix() {
  // Bloomberg: reset content restrictions
  if (hostname.includes('bloomberg.com')) {
    try {
      // Clear localStorage keys that track free articles
      ['freeReads', 'freeReadData', 'pgFreeRead'].forEach(k => localStorage.removeItem(k));
    } catch(e) {}
  }

  // Medium: remove metered content class
  if (hostname.includes('medium.com') || document.querySelector('head > link[href*=".medium.com/"]')) {
    const paywall = document.querySelector('article.meteredContent');
    if (paywall) {
      paywall.removeAttribute('class');
    }
  }

  // The Economist: clear paywall data
  if (hostname.includes('economist.com')) {
    try {
      Object.keys(localStorage).filter(k => k.includes('ec_')).forEach(k => localStorage.removeItem(k));
    } catch(e) {}
  }

  // WSJ / Barron's: spoof Dow Jones user object
  if (['wsj.com', 'barrons.com'].some(d => hostname.includes(d))) {
    try {
      window.DJ = window.DJ || {};
      window.DJ.User = { authenticated: true, subscribed: true };
    } catch(e) {}
  }

  // NYTimes
  if (hostname.includes('nytimes.com')) {
    try {
      // Remove metering cookie
      document.cookie = 'NYT-S=; expires=Thu, 01 Jan 1970 00:00:01 GMT';
    } catch(e) {}
  }

  // FT.com: clear ft.com article count
  if (hostname.includes('ft.com')) {
    try {
      Object.keys(localStorage).filter(k => k.match(/^(ft[-_]|next[-_])/i)).forEach(k => localStorage.removeItem(k));
    } catch(e) {}
  }

  // Fusion/Arc CMS (Washington Post, many US papers)
  if (window.Fusion) {
    try {
      if (window.Fusion.globalContent) {
        window.Fusion.globalContent.content_restrictions = {};
        window.Fusion.globalContent.isPremium = false;
        window.Fusion.globalContent._id = 0;
      }
    } catch(e) {}
  }
}

// ── 7. MutationObserver to re-run on dynamic content ─────────────
let observer;
function startObserver() {
  if (observer) return;
  observer = new MutationObserver(function(mutations) {
    let significant = false;
    for (const m of mutations) {
      if (m.addedNodes.length > 0) {
        significant = true;
        break;
      }
    }
    if (significant) removePaywalls();
  });
  observer.observe(document.documentElement, {
    childList: true, subtree: true
  });
}

// ── 8. Anti-redirect: prevent paywall redirects ───────────────────
const _origPushState = history.pushState;
history.pushState = function(state, title, url) {
  if (url && typeof url === 'string' && url.match(/\/(subscribe|signin|login|register)\b/i)) {
    console.log('[BPC] Blocked redirect to:', url);
    return;
  }
  return _origPushState.apply(this, arguments);
};

// ── Run ───────────────────────────────────────────────────────────
clearMeteringStorage();
removePaywalls();
siteSpecificFix();

// Run at multiple intervals to catch dynamic paywall injection
[0, 200, 500, 1000, 2000, 4000].forEach(t => {
  setTimeout(() => {
    removePaywalls();
    siteSpecificFix();
  }, t);
});

// Start observer
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', startObserver);
} else {
  startObserver();
}

console.log('[BPC Mobile Reader v3] Active on:', hostname);
})();
</script>
"""

# ── Archive.is fetcher ──────────────────────────────────────────────────────
ARCHIVE_DOMAINS = ['archive.ph', 'archive.is', 'archive.today', 'archive.fo', 'archiveofourown.org']

def fetch_archive(url):
    """Try to get article from archive.ph"""
    archive_url = f'https://archive.ph/newest/{url}'
    profile = UA_PROFILES['chrome_desktop']
    try:
        req = build_request(archive_url, profile)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            raw = resp.read()
            if resp.headers.get('Content-Encoding') == 'gzip':
                raw = gzip.decompress(raw)
            return raw.decode('utf-8', errors='replace')
    except Exception:
        return None

# ── Threading server ────────────────────────────────────────────────────────
class ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class handler(http.server.BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if not BPC_SITES: load_sites()
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/proxy':
            self.handle_proxy(parsed)
        elif parsed.path == '/api/sites':
            self.serve_json(BPC_SITES)
        elif parsed.path == '/api/status':
            self.serve_json({'status': 'ok', 'sites': len(BPC_SITES), 'version': '3.1v'})
        else:
            self.send_error(404)

    def serve_json(self, data):
        out = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def handle_proxy(self, parsed):
        query = urllib.parse.parse_qs(parsed.query)
        if 'url' not in query:
            self.send_error(400, 'Missing url parameter')
            return

        url = query['url'][0]
        ua_override = query.get('ua', [None])[0]
        reader_mode = query.get('reader', ['0'])[0] == '1'
        use_archive = query.get('archive', ['0'])[0] == '1'

        if not url.startswith('http'):
            url = 'https://' + url

        try:
            domain = urllib.parse.urlparse(url).hostname or ''
        except Exception:
            domain = ''

        # ── Try archive.is first if requested ──────────────────────
        if use_archive:
            archive_html = fetch_archive(url)
            if archive_html:
                out = self.transform_html(archive_html, url, reader_mode, is_archive=True)
                if isinstance(out, str):
                    out = out.encode('utf-8')
                self._send_html(out)
                return

        # ── Normal proxy request ────────────────────────────────────
        profile = get_profile(domain, ua_override)
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        try:
            req = build_request(url, profile)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                headers = resp.headers
                raw = resp.read()
                ct = headers.get('Content-Type', 'text/html; charset=utf-8')
                enc = headers.get('Content-Encoding', '')

                if enc == 'gzip':
                    try:
                        raw = gzip.decompress(raw)
                    except Exception: pass
                elif enc == 'br':
                    if HAS_BROTLI:
                        try:
                            raw = brotli.decompress(raw)
                        except Exception: pass

                if 'text/html' in ct:
                    # Detect charset from Content-Type header
                    charset = None
                    c_match = re.search(r'charset=([\w-]+)', ct, re.IGNORECASE)
                    if c_match:
                        charset = c_match.group(1)
                    
                    if not charset:
                        try:
                            import chardet
                            det = chardet.detect(raw)
                            charset = det.get('encoding')
                        except: pass
                    
                    if not charset: charset = 'utf-8'
                    
                    try:
                        decoded = raw.decode(charset, errors='replace')
                    except Exception:
                        decoded = raw.decode('utf-8', errors='replace')
                        
                    html = self.transform_html(decoded, url, reader_mode)
                    out = html.encode('utf-8')
                    ct = 'text/html; charset=utf-8'
                else:
                    out = raw

                self._send_html(out, ct)

        except urllib.error.HTTPError as e:
            # On 403, try alternative UA or archive
            if e.code == 403:
                # Auto-retry with Googlebot
                try:
                    req2 = build_request(url, UA_PROFILES['googlebot'])
                    with urllib.request.urlopen(req2, timeout=12, context=ctx) as resp2:
                        h2 = resp2.headers
                        raw2 = resp2.read()
                        enc2 = h2.get('Content-Encoding', '')
                        ct2 = h2.get('Content-Type', 'text/html; charset=utf-8')
                        
                        if enc2 == 'gzip':
                            try: raw2 = gzip.decompress(raw2)
                            except: pass
                        elif enc2 == 'br' and HAS_BROTLI:
                            try: raw2 = brotli.decompress(raw2)
                            except: pass
                            
                        # Detect charset
                        charset2 = 'utf-8'
                        c_match2 = re.search(r'charset=([\w-]+)', ct2, re.IGNORECASE)
                        if c_match2: charset2 = c_match2.group(1)
                        
                        try: decoded2 = raw2.decode(charset2, errors='replace')
                        except: decoded2 = raw2.decode('utf-8', errors='replace')
                            
                        html2 = self.transform_html(decoded2, url, reader_mode)
                        out2 = html2.encode('utf-8')
                        self._send_html(out2)
                        return
                except Exception:
                    pass
                # Fallback to error page with options
                out = self.error_page(url, f'403 Forbidden — Bot detected', domain).encode('utf-8')
                self._send_html(out)
            elif e.code == 429:
                out = self.error_page(url, '429 Rate Limited', domain).encode('utf-8')
                self._send_html(out)
            else:
                try:
                    self.send_error(e.code, str(e.reason))
                except Exception:
                    pass
        except Exception as e:
            try:
                out = self.error_page(url, str(e)[:200], domain).encode('utf-8')
                self._send_html(out)
            except Exception:
                pass

    def _send_html(self, content_bytes, ct='text/html; charset=utf-8'):
        self.send_response(200)
        self.send_header('Content-Type', ct)
        self.send_header('Content-Length', str(len(content_bytes)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('X-Frame-Options', 'ALLOWALL')
        self.send_header('Content-Security-Policy',
            "frame-ancestors *; script-src 'self' 'unsafe-inline' 'unsafe-eval' *;")
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        self.wfile.write(content_bytes)

    def transform_html(self, html, original_url, reader_mode=False, is_archive=False):
        """
        Transform proxied HTML:
        1. Fix relative URLs
        2. Inject BPC bypass script
        3. Remove known paywall scripts (server-side)
        4. Optional reader mode CSS
        """
        parsed = urllib.parse.urlparse(original_url)
        base_origin = f"{parsed.scheme}://{parsed.netloc}"

        # ── Strip known paywall scripts (server-side blocking) ──────
        BLOCKED_SRC = [
            'tinypass.com', 'piano.io', 'poool.fr',
            'sophi.io', 'wallkit.net', 'cxense.com',
            'pelcro.com', 'blueconic.net', 'zephr.com',
            '.cm.bloomberg.com/', 'assets.bwbx.io/s3/javelin/',
            'evercookie', 'newsmemory.com',
            'economist.com/latest/wall-ui', 'zephr/feature',
        ]
        def strip_paywall_scripts(m):
            src = m.group(0)
            if any(b in src for b in BLOCKED_SRC):
                return '<!-- [BPC] blocked script -->'
            return src
        html = re.sub(r'<script[^>]+src=["\'][^"\']*["\'][^>]*/?>(?:</script>)?', strip_paywall_scripts, html)

        # ── Fix relative URLs ────────────────────────────────────────
        def fix_url(m):
            attr = m.group(1)
            path = m.group(2).strip()
            if path.startswith('//'):
                return f'{attr}="{parsed.scheme}:{path}"'
            if path.startswith('/') and not path.startswith('//'):
                return f'{attr}="{base_origin}{path}"'
            return m.group(0)
        html = re.sub(r'(src|href|action)="(\s*/[^"]*)"', fix_url, html)
        html = re.sub(r"(src|href|action)='(\s*/[^']*)'", fix_url, html)

        # ── Build head injections ────────────────────────────────────
        base_tag = f'<base href="{base_origin}/">\n'
        viewport = '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
        # Remove CSP headers that might block our scripts
        html = re.sub(r'<meta[^>]+http-equiv=["\']Content-Security-Policy["\'][^>]*/>', '', html, flags=re.IGNORECASE)
        html = re.sub(r'<meta[^>]+http-equiv=["\']X-Frame-Options["\'][^>]*/>', '', html, flags=re.IGNORECASE)

        head_extra = base_tag + viewport

        # ── Reader mode CSS ──────────────────────────────────────────
        if reader_mode:
            head_extra += """<style id="bpc-reader-mode">
  body { max-width: 740px !important; margin: 20px auto !important;
         font: 18px/1.8 Georgia,serif !important;
         color: #1a1a1a !important; background: #fff !important;
         padding: 16px !important; }
  h1,h2,h3 { font-family: -apple-system,sans-serif !important; line-height:1.3!important; }
  img,video { max-width: 100% !important; height: auto !important; }
  /* Kill ads and junk */
  [class*="ad-"],[class*="-ad-"],[id*="-ad-"],
  [class*="banner"],[class*="promo"],[class*="popup"],
  [class*="modal"]:not([class*="article"]),
  nav:not([aria-label*="article"]), .nav, header .ads,
  .sidebar, aside, footer > * { display: none !important; }
  /* Make article full width */
  article, [class*="article-body"], [class*="story-body"],
  [class*="post-content"], .entry-content {
    max-width: 100% !important; float: none !important; width: 100% !important;
  }
</style>\n"""

        # ── Inject into <head> ───────────────────────────────────────
        if re.search(r'<head\b', html, re.IGNORECASE):
            html = re.sub(r'(<head\b[^>]*>)', r'\1\n' + head_extra, html, count=1, flags=re.IGNORECASE)
        else:
            html = head_extra + html

        # ── Inject BPC script before </body> ────────────────────────
        # Also add archive fallback button
        archive_btn = f'''<div id="bpc-toolbar" style="position:fixed;bottom:0;left:0;right:0;background:rgba(13,17,23,.95);border-top:1px solid #30363d;padding:8px 16px;display:flex;gap:8px;z-index:999999;align-items:center;font-family:system-ui,sans-serif">
  <span style="font-size:11px;color:#888;flex:1;">BPC Mobile Reader</span>
  <a href="https://archive.ph/newest/{original_url}" target="_parent" style="padding:5px 12px;background:#1f6feb;color:white;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600">🗄 Archive</a>
  <a href="https://freedium.cfd/{original_url}" target="_parent" style="padding:5px 12px;background:#238636;color:white;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600">📖 Freedium</a>
  <button onclick="this.closest('#bpc-toolbar').remove()" style="background:none;border:none;color:#888;font-size:18px;cursor:pointer;padding:0 4px">✕</button>
</div>'''

        body_inject = BPC_CORE_SCRIPT + '\n' + archive_btn

        if re.search(r'</body>', html, re.IGNORECASE):
            html = re.sub(r'</body>', body_inject + '</body>', html, count=1, flags=re.IGNORECASE)
        else:
            html += body_inject

        return html

    def error_page(self, url, error, domain):
        encoded_url = urllib.parse.quote(url, safe='')
        freedium = f"https://freedium.cfd/{url}"
        archive = f"https://archive.ph/newest/{url}"
        twelve_ft = f"https://12ft.io/{url}"
        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>無法載入</title>
<style>
  body {{ font-family:-apple-system,sans-serif; padding:30px;
          background:#0d1117; color:#c9d1d9; text-align:center; min-height:100vh;
          display:flex; flex-direction:column; align-items:center; justify-content:center; }}
  h2 {{ color:#ff7b72; margin-bottom:8px; }}
  .domain {{ color:#58a6ff; font-size:1.1em; margin-bottom:6px; }}
  .err {{ background:rgba(255,123,114,.1); border:1px solid rgba(255,123,114,.3);
          border-radius:8px; padding:10px 16px; font-size:13px; color:#ff7b72;
          margin-bottom:24px; max-width:480px; word-break:break-all; }}
  .btn-grid {{ display:flex; flex-wrap:wrap; gap:10px; justify-content:center; margin-top:20px; }}
  a.btn {{ padding:11px 20px; border-radius:10px; color:white; text-decoration:none;
           font-weight:700; font-size:14px; transition:.2s; }}
  a.green  {{ background:#238636; }}
  a.blue   {{ background:#1f6feb; }}
  a.purple {{ background:#6e40c9; }}
  a.gray   {{ background:transparent; border:1px solid #6e7681; color:#c9d1d9; }}
  .tip {{ font-size:12px; color:#6e7681; margin-top:20px; max-width:400px; line-height:1.6; }}
</style>
</head>
<body>
  <h2>⚠️ 無法載入頁面</h2>
  <div class="domain">🌐 {domain}</div>
  <div class="err">{error}</div>
  <p style="color:#8b949e;font-size:13px;max-width:400px">
    此網站可能有 Cloudflare 保護或 IP 封鎖。<br>
    請嘗試以下備用方案讀取文章：
  </p>
  <div class="btn-grid">
    <a href="{archive}" class="btn blue" target="_parent">🗄️ Archive.ph</a>
    <a href="{freedium}" class="btn green" target="_parent">📖 Freedium</a>
    <a href="{twelve_ft}" class="btn purple" target="_parent">📏 12ft.io</a>
    <a href="https://web.archive.org/web/*/{url}" class="btn blue" target="_parent">🏛️ Wayback Machine</a>
    <a href="/proxy?url={encoded_url}&ua=googlebot" class="btn gray" target="_parent">🤖 Retry as Googlebot</a>
    <button onclick="window.parent.history.back()" class="btn gray" style="border:1px solid #6e7681;cursor:pointer">← 返回</button>
  </div>
  <div class="tip">
    💡 <strong>提示</strong>：Archive.ph 存有大多數主流媒體的快照，成功率最高。
    Freedium 適合 Medium 及部分英文媒體。
  </div>
</body>
</html>"""


if __name__ == '__main__':
    os.chdir(_script_dir)
    with ThreadingTCPServer(("0.0.0.0", PORT), BPCHandler) as httpd:
        print(f"╔══════════════════════════════════════════════╗")
        print(f"║   BPC Mobile Reader v3.0  port:{PORT}         ║")
        print(f"║   {len(BPC_SITES):>4} 個網站規則已載入                  ║")
        print(f"╚══════════════════════════════════════════════╝")
        httpd.serve_forever()
