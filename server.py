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

from config import API_KEY, PAGE_LIMIT, MAX_PAGES

SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_PROGRAMS = (
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",   # SPL Token
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",   # Token-2022
)
PRICE_URL = "https://lite-api.jup.ag/price/v3?ids="
PRICE_CHUNK = 50          # mints per price request (keeps the URL short)
CACHE_TTL = 60            # seconds
ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")   # base58, Solana address length

_cache = {}               # address -> (expires_at, payload)
_cache_lock = threading.Lock()


class UserError(Exception):
    """An error whose message is safe to show to the visitor."""


# ── Upstream calls ───────────────────────────────────────────────────────────

def _http_json(url, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": "SolanaTracker/1.0"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def _rpc(method, params):
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    out = _http_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if "error" in out:
        raise RuntimeError(f"RPC {method}: {out['error']}")
    return out.get("result")


def _prices(mints):
    prices = {}
    for i in range(0, len(mints), PRICE_CHUNK):
        chunk = mints[i:i + PRICE_CHUNK]
        try:
            raw = _http_json(PRICE_URL + ",".join(chunk), timeout=6)
        except Exception:
            continue   # prices are best-effort; tokens just show "no price"
        for mint, info in (raw or {}).items():
            if info and info.get("usdPrice"):
                prices[mint] = float(info["usdPrice"])
    return prices


def _symbols(mints):
    """Symbol and name for each mint via Helius DAS getAssetBatch (one call instead of one per token)."""
    found = {}
    for i in range(0, len(mints), 1000):
        try:
            assets = _rpc("getAssetBatch", {"ids": mints[i:i + 1000]}) or []
        except Exception:
            continue
        for a in assets:
            if not a:
                continue
            meta = (a.get("content") or {}).get("metadata") or {}
            sym = (a.get("token_info") or {}).get("symbol") or meta.get("symbol")
            if sym:
                found[a["id"]] = {"symbol": sym.strip()[:16], "name": (meta.get("name") or "").strip()[:48]}
    return found


def get_holdings(wallet):
    sol = float((_rpc("getBalance", [wallet]) or {}).get("value", 0)) / 1e9

    balances = collections.defaultdict(float)
    for program_id in TOKEN_PROGRAMS:
        res = _rpc("getTokenAccountsByOwner", [wallet, {"programId": program_id}, {"encoding": "jsonParsed"}])
        for acct in (res or {}).get("value") or []:
            info = acct["account"]["data"]["parsed"]["info"]
            balances[info["mint"]] += float(info["tokenAmount"]["uiAmount"] or 0)

    entries = [{"mint": SOL_MINT, "symbol": "SOL", "name": "Solana", "amount": sol}]
    entries += [{"mint": m, "amount": a} for m, a in balances.items() if a > 0]

    meta = _symbols([e["mint"] for e in entries[1:]])
    for e in entries[1:]:
        m = meta.get(e["mint"], {})
        e["symbol"] = m.get("symbol") or (e["mint"][:4] + "…" + e["mint"][-4:])
        e["name"] = m.get("name", "")

    price_map = _prices([e["mint"] for e in entries])
    holdings = []
    for e in entries:
        price = price_map.get(e["mint"])
        usd = e["amount"] * price if price is not None else None
        if usd is not None and usd < 0.01 and e["mint"] != SOL_MINT:
            continue   # confirmed dust
        holdings.append({**e, "usd_value": usd, "price_per_token": price})

    holdings.sort(key=lambda h: (h["usd_value"] is None, -(h["usd_value"] or 0)))
    return holdings


def get_activity(wallet):
    """Transactions per UTC day across the wallet's most recent transactions."""
    from helius import fetch_transactions
    txns = fetch_transactions(wallet)
    days = collections.Counter()
    for t in txns:
        ts = t.get("timestamp")
        if ts:
            days[datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")] += 1
    return {"days": dict(days), "count": len(txns), "capped": len(txns) >= PAGE_LIMIT * MAX_PAGES}


def wallet_report(wallet):
    now = time.time()
    with _cache_lock:
        hit = _cache.get(wallet)
        if hit and hit[0] > now:
            return hit[1]

    with ThreadPoolExecutor(max_workers=2) as pool:
        holdings_f = pool.submit(get_holdings, wallet)
        activity_f = pool.submit(get_activity, wallet)
        holdings = holdings_f.result()
        try:
            activity = activity_f.result()
        except Exception:
            _log_error()
            activity = None   # still show holdings if history fails

    payload = {"address": wallet, "holdings": holdings, "activity": activity}
    with _cache_lock:
        if len(_cache) > 500:
            _cache.clear()
        _cache[wallet] = (now + CACHE_TTL, payload)
    return payload


def _log_error():
    """Print the traceback with the API key masked (request URLs carry it)."""
    text = traceback.format_exc()
    if API_KEY:
        text = text.replace(API_KEY, "***")
    print(text, flush=True)


# ── HTTP ─────────────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
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
