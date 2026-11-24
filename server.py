"""Web server: serves index.html and one JSON endpoint, /api/wallet?address=<base58>.

Each request is independent (no shared per-user state), so concurrent visitors never see
each other's wallet. Results are cached briefly per address to spare the Helius quota.
"""
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import collections
import datetime
import json
import os
import re
import threading
import time
import traceback
import urllib.request

from config import API_KEY, BASE_URL, JUPITER_API_KEY

SOL_MINT = "So11111111111111111111111111111111111111112"
PRICE_CHUNK = 50          # mints per price request (keeps the URL short)
CACHE_TTL = 60            # seconds
ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")   # base58, Solana address length

_cache = {}               # address -> (expires_at, payload)
_cache_lock = threading.Lock()


class UserError(Exception):
    """An error whose message is safe to show to the visitor."""


# ── Upstream calls ───────────────────────────────────────────────────────────

def _http_json(url, body=None, headers=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": "SolanaWalletBubbleMap/1.0", **(headers or {})}
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _rpc(method, params):
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    out = _http_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in out:
        raise RuntimeError(f"RPC {method}: {out['error']}")
    return out.get("result")


def _jupiter_prices(mints):
    """USD prices from Jupiter Price API v3. Best-effort: missing tokens just show "no price"."""
    if JUPITER_API_KEY:
        base, headers = "https://api.jup.ag/price/v3?ids=", {"x-api-key": JUPITER_API_KEY}
    else:
        base, headers = "https://lite-api.jup.ag/price/v3?ids=", {}   # free host, being retired
    prices = {}
    for i in range(0, len(mints), PRICE_CHUNK):
        try:
            raw = _http_json(base + ",".join(mints[i:i + PRICE_CHUNK]), headers=headers, timeout=6)
        except Exception:
            continue
        for mint, info in (raw or {}).items():
            if info and info.get("usdPrice"):
                prices[mint] = float(info["usdPrice"])
    return prices


def get_holdings(wallet):
    """SOL + every fungible token in one Helius DAS searchAssets call (with names and, for the
    top ~10K tokens, USD prices). Jupiter fills in prices Helius doesn't have."""
    items, native = [], {}
    for page in range(1, 6):   # up to 5,000 token accounts
        res = _rpc("searchAssets", {
            "ownerAddress": wallet, "tokenType": "fungible", "page": page, "limit": 1000,
            "displayOptions": {"showNativeBalance": True},
        }) or {}
        native = res.get("nativeBalance") or native
        batch = res.get("items") or []
        items += batch
        if len(batch) < 1000:
            break

    entries = [{
        "mint": SOL_MINT, "symbol": "SOL", "name": "Solana",
        "amount": float(native.get("lamports", 0)) / 1e9,
        "price": native.get("price_per_sol"),
    }]
    for a in items:
        ti = a.get("token_info") or {}
        amount = float(ti.get("balance") or 0) / 10 ** int(ti.get("decimals") or 0)
        if amount <= 0:
            continue
        meta = (a.get("content") or {}).get("metadata") or {}
        sym = (ti.get("symbol") or meta.get("symbol") or "").strip()[:16]
        entries.append({
            "mint": a["id"],
            "symbol": sym or a["id"][:4] + "\u2026" + a["id"][-4:],
            "name": (meta.get("name") or "").strip()[:48],
            "amount": amount,
            "price": (ti.get("price_info") or {}).get("price_per_token"),
        })

    # Tokens Helius can't price are mostly spam airdrops; exchange wallets hold thousands.
    # Ask Jupiter about the first 200 only (4 requests) so a lookup stays fast.
    missing = [e["mint"] for e in entries if e["price"] is None][:200]
    if missing:
        jup = _jupiter_prices(missing)
        for e in entries:
            if e["price"] is None:
                e["price"] = jup.get(e["mint"])

    holdings = []
    for e in entries:
        price = float(e.pop("price")) if e.get("price") is not None else None
        usd = e["amount"] * price if price is not None else None
        if usd is not None and usd < 0.01 and e["mint"] != SOL_MINT:
            continue   # confirmed dust
        holdings.append({**e, "usd_value": usd, "price_per_token": price})

    holdings.sort(key=lambda h: (h["usd_value"] is None, -(h["usd_value"] or 0)))
    return holdings


SIG_PAGES = 5            # getSignaturesForAddress pages of 1,000 (5,000 transactions max)
RECENT_TXNS = 100        # transactions listed with type and description


def get_activity(wallet):
    """Successful transactions per UTC day over the past year, from getSignaturesForAddress
    (every transaction that touched the wallet, not just trades). Busy wallets hit the page cap
    first: `since` says how far back the counts really go, `capped` says the cap was hit."""
    cutoff = time.time() - 366 * 86400
    days = collections.Counter()
    count, oldest, before, capped = 0, None, None, False
    for page in range(SIG_PAGES):
        opts = {"limit": 1000}
        if before:
            opts["before"] = before
        sigs = _rpc("getSignaturesForAddress", [wallet, opts]) or []
        reached_cutoff = False
        for x in sigs:
            bt = x.get("blockTime")
            if bt is None:
                continue
            if bt < cutoff:
                reached_cutoff = True
                break
            oldest = bt
            if x.get("err") is None:
                days[datetime.datetime.fromtimestamp(bt, datetime.timezone.utc).strftime("%Y-%m-%d")] += 1
                count += 1
        if reached_cutoff or len(sigs) < 1000:
            break
        before = sigs[-1]["signature"]
        capped = page == SIG_PAGES - 1
    since = datetime.datetime.fromtimestamp(oldest, datetime.timezone.utc).strftime("%Y-%m-%d") if oldest else None
    return {"days": dict(days), "count": count, "capped": capped, "since": since}


def get_recent(wallet):
    """The latest transactions with Helius's type and plain-English description."""
    url = f"{BASE_URL}/v0/addresses/{wallet}/transactions?api-key={API_KEY}&limit={RECENT_TXNS}"
    out = []
    for t in _http_json(url, timeout=15) or []:
        out.append({
            "signature": t.get("signature", ""),
            "time": t.get("timestamp"),
            "type": (t.get("type") or "UNKNOWN")[:32],
            "source": (t.get("source") or "")[:32],
            "description": (t.get("description") or "")[:240],
            "fee": (t.get("fee") or 0) / 1e9,
            "ok": t.get("transactionError") is None,
        })
    return out


def wallet_report(wallet):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(wallet)
        if hit and hit[0] > now:
            return hit[1]

    with ThreadPoolExecutor(max_workers=3) as pool:
        holdings_f = pool.submit(get_holdings, wallet)
        activity_f = pool.submit(get_activity, wallet)
        recent_f = pool.submit(get_recent, wallet)
        holdings = holdings_f.result()
        activity = recent = None   # still show holdings if history fails
        try:
            activity = activity_f.result()
        except Exception:
            _log_error()
        try:
            recent = recent_f.result()
        except Exception:
            _log_error()

    payload = {"address": wallet, "holdings": holdings, "activity": activity, "transactions": recent}
    with _cache_lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[wallet] = (now + CACHE_TTL, payload)
    return payload


def _log_error():
    """Print the traceback with API keys masked (request URLs carry it)."""
    text = traceback.format_exc()
    for secret in (API_KEY, JUPITER_API_KEY):
        if secret:
            text = text.replace(secret, "***")
    print(text, flush=True)


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        try:
            self._route()
        except Exception:
            _log_error()
            try:
                self._json(500, {"error": "Something went wrong on our side. Try again."})
            except Exception:
                pass   # client already gone

    def _route(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif parsed.path == "/api/wallet":
            address = parse_qs(parsed.query).get("address", [""])[0].strip()
            self._wallet(address)
        elif parsed.path == "/healthz":
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "Not found"})

    def _wallet(self, address):
        try:
            if not ADDRESS_RE.match(address):
                raise UserError("That doesn't look like a Solana wallet address. Paste the full address (32 to 44 characters).")
            if not API_KEY:
                raise UserError("The server has no Helius API key set, so it can't read wallets right now.")
            self._json(200, wallet_report(address))
        except UserError as e:
            self._json(400, {"error": str(e)})
        except Exception:
            _log_error()
            self._json(502, {"error": "Couldn't reach the Solana data provider. Try again in a moment."})

    def _serve_file(self, filename, content_type):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
        try:
            with open(path, "rb") as f:
                data = f.read()
        except FileNotFoundError:
            return self._json(404, {"error": "Not found"})
        self._send(200, content_type, data)

    def _json(self, status, obj):
        self._send(status, "application/json", json.dumps(obj).encode())

    def _send(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"Listening on port {port}", flush=True)
    server.serve_forever()
