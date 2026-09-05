from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request
import os
import json
import datetime
import collections

MINT_TO_SYMBOL = {
    "So11111111111111111111111111111111111111112":  "SOL",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": "USDT",
    "USDH1Hdt8P7qTQKDSpeZDnDRKqTucBM5ciqMP2kYtAf":  "USDH",
    "DezXAZ8z7PnrnRJjz3Fh4Cz9WcbQTUk2e37hTd5C59w": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN":  "JUP",
    "J1toso1uCk3RLmjorhTtrVwY9HJ7X8V9yYac6Y7kGCPn": "JitoSOL",
    "mSoLzYCxNqgBJwTfMxKWR7fmDjnZ7HepfsSwnYwbsR":   "mSOL",
    "bSo13r4TkiE4G6HUPZepS9z6E6T8Jq3EqW3eJ5W2RCP":  "bSOL",
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R": "RAY",
    "orcaEKTdK7LKz57vaAYfXqXbUQmNEw4RkY7qR9VYkq":   "ORCA",
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm": "WIF",
    "HhJpBhZc3L4QxrzBFW91tYYQJgWPs2F7GQZpkz7g5Xtg": "MYRO",
    "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgTL":  "SAMO",
}

# In-memory cache — replaced on each /run call
_cache = {"rows": [], "wallet": ""}


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self._serve_file("index.html", "text/html; charset=utf-8")
        elif parsed.path == "/run":
            params = parse_qs(parsed.query)
            wallet = params.get("wallet", [""])[0].strip()
            self._stream_run(wallet)
        elif parsed.path == "/tokens":
            self._get_tokens()
        elif parsed.path == "/token_detail":
            params = parse_qs(parsed.query)
            token = params.get("token", [""])[0].strip()
            self._get_token_detail(token)
        elif parsed.path == "/prices":
            self._get_prices()
        elif parsed.path == "/summary":
            self._get_summary()
        elif parsed.path == "/trend":
            self._get_trend()
        elif parsed.path == "/holdings":
            params = parse_qs(parsed.query)
            wallet = params.get("wallet", [""])[0].strip()
            self._get_holdings(wallet)
        else:
            self.send_error(404)

    def _serve_file(self, filename, content_type):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, filename)
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except FileNotFoundError:
            self.send_error(404)

    def _stream_run(self, wallet):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        if not wallet:
            self._send_event("Error: no wallet address provided")
            self._send_event("[DONE]")
            return

        try:
            from helius import fetch_transactions
            from parser import parse_transactions

            raw = fetch_transactions(wallet)
            rows = parse_transactions(raw)

            _cache["rows"] = rows
            _cache["wallet"] = wallet
        except Exception as e:
            self._send_event(f"Error: {e}")
        finally:
            self._send_event("[DONE]")

    def _get_tokens(self):
        try:
            rows = _cache["rows"]
            counter = collections.Counter()
            amount_sums = collections.defaultdict(float)

            for r in rows:
                if r.get("type") == "SWAP":
                    if r.get("token_in"):
                        counter[r["token_in"]] += 1
                        amount_sums[r["token_in"]] += r.get("amount_in", 0) or 0
                    if r.get("token_out"):
                        counter[r["token_out"]] += 1
                        amount_sums[r["token_out"]] += r.get("amount_out", 0) or 0

            result = [
                {"token": t, "count": c, "total_amount": amount_sums[t]}
                for t, c in counter.most_common(20)
            ]

            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_token_detail(self, token):
        try:
            rows = _cache["rows"]
            count_in = count_out = 0
            total_in = total_out = 0.0
            times = []
            type_counter = collections.Counter()

            for r in rows:
                txn_type = r.get("type", "")
                matched = False
                if r.get("token_in") == token:
                    count_in += 1
                    total_in += r.get("amount_in", 0) or 0
                    matched = True
                if r.get("token_out") == token:
                    count_out += 1
                    total_out += r.get("amount_out", 0) or 0
                    matched = True
                if matched:
                    if r.get("block_time"):
                        times.append(r["block_time"])
                    type_counter[txn_type] += 1

            first_seen = (
                datetime.datetime.utcfromtimestamp(min(times)).strftime("%Y-%m-%d %H:%M:%S")
                if times else ""
            )
            last_seen = (
                datetime.datetime.utcfromtimestamp(max(times)).strftime("%Y-%m-%d %H:%M:%S")
                if times else ""
            )
            types = [{"type": t, "count": c} for t, c in type_counter.most_common()]

            result = {
                "token":      token,
                "count_in":   count_in,
                "count_out":  count_out,
                "total_in":   total_in,
                "total_out":  total_out,
                "first_seen": first_seen,
                "last_seen":  last_seen,
                "types":      types,
            }

            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_summary(self):
        try:
            rows = _cache["rows"]
            total_txns = len(rows)
            total_fees = sum(r.get("fee", 0) or 0 for r in rows) / 1e9

            block_times = [r["block_time"] for r in rows if r.get("block_time")]
            first_txn = (
                datetime.datetime.utcfromtimestamp(min(block_times)).strftime("%Y-%m-%d %H:%M:%S")
                if block_times else ""
            )
            last_txn = (
                datetime.datetime.utcfromtimestamp(max(block_times)).strftime("%Y-%m-%d %H:%M:%S")
                if block_times else ""
            )
            active_days = (
                len({datetime.datetime.utcfromtimestamp(bt).date() for bt in block_times})
                if block_times else 0
            )

            tokens = []
            for r in rows:
                if r.get("token_in"):  tokens.append(r["token_in"])
                if r.get("token_out"): tokens.append(r["token_out"])
            unique_tokens = len(set(tokens))
            counter = collections.Counter(tokens)
            top_token = counter.most_common(1)[0][0] if counter else ""

            result = {
                "total_txns":    total_txns,
                "first_txn":     first_txn,
                "last_txn":      last_txn,
                "total_fees":    total_fees,
                "active_days":   active_days,
                "unique_tokens": unique_tokens,
                "top_token":     top_token,
            }
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_trend(self):
        try:
            rows = _cache["rows"]
            STABLES = {"USDC", "USDT", "USDH"}
            months = collections.defaultdict(lambda: {"txn_count": 0, "usd_in": 0.0, "usd_out": 0.0})

            for r in rows:
                bt = r.get("block_time")
                if not bt:
                    continue
                month = datetime.datetime.utcfromtimestamp(bt).strftime("%Y-%m")
                months[month]["txn_count"] += 1
                if r.get("token_in") in STABLES:
                    months[month]["usd_in"] += r.get("amount_in", 0) or 0
                if r.get("token_out") in STABLES:
                    months[month]["usd_out"] += r.get("amount_out", 0) or 0

            result = [
                {"month": m, **v}
                for m, v in sorted(months.items())
            ]

            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _get_prices(self):
        try:
            mints = ",".join(MINT_TO_SYMBOL.keys())
            url = f"https://lite-api.jup.ag/price/v3?ids={mints}"
            req = urllib.request.Request(url, headers={"User-Agent": "SolanaTracker/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read())

            prices = {}
            for mint, info in raw.items():
                symbol = MINT_TO_SYMBOL.get(mint)
                if symbol and info and info.get("usdPrice"):
                    prices[symbol] = float(info["usdPrice"])

            data = json.dumps(prices).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            # Return empty object on failure — frontend handles gracefully
            empty = json.dumps({}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(empty)))
            self.end_headers()
            self.wfile.write(empty)

    def _get_holdings(self, wallet_param=""):
        try:
            from config import API_KEY, WALLET as CONFIG_WALLET
            wallet = wallet_param or CONFIG_WALLET

            SOL_MINT = "So11111111111111111111111111111111111111112"
            RPC_URL  = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"

            def rpc(method, params):
                body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
                req  = urllib.request.Request(RPC_URL, data=body, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read()).get("result", {})

            # 1. Native SOL balance
            sol_lamports = rpc("getBalance", [wallet]).get("value", 0)
            sol_amount   = float(sol_lamports) / 1e9

            # 2. SPL token accounts — both legacy Token program and Token-2022
            SPL_PROGRAM    = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
            TOKEN22_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"

            all_accounts = []
            for program_id in (SPL_PROGRAM, TOKEN22_PROGRAM):
                result = rpc("getTokenAccountsByOwner", [
                    wallet,
                    {"programId": program_id},
                    {"encoding": "jsonParsed"},
                ])
                all_accounts.extend(result.get("value") or [])

            entries = [{"mint": SOL_MINT, "symbol": "SOL", "amount": sol_amount}]

            for acct in all_accounts:
                info   = acct["account"]["data"]["parsed"]["info"]
                mint   = info["mint"]
                ui_amt = float(info["tokenAmount"]["uiAmount"] or 0)
                symbol = MINT_TO_SYMBOL.get(mint) or (
                    mint[:6] + "\u2026" + mint[-4:] if len(mint) > 10 else mint
                )
                entries.append({"mint": mint, "symbol": symbol, "amount": ui_amt})

            # 3. Filter: must hold more than 1 token (drops dust/airdrops)
            entries = [e for e in entries if e["amount"] > 1]

            # 3b. Lookup proper names for unknown tokens via Helius DAS getAsset
            for e in entries:
                if e["mint"] in MINT_TO_SYMBOL:
                    continue
                try:
                    asset  = rpc("getAsset", {"id": e["mint"]})
                    symbol = ((asset.get("token_info") or {}).get("symbol") or
                              (asset.get("content", {}).get("metadata") or {}).get("symbol"))
                    if symbol:
                        e["symbol"] = symbol
                except Exception:
                    pass  # keep shortened mint as fallback

            # 4. Fetch prices only for non-zero mints (avoids 414 on large wallets)
            all_mints = [e["mint"] for e in entries]
            price_url = "https://lite-api.jup.ag/price/v3?ids=" + ",".join(all_mints)
            price_req = urllib.request.Request(price_url, headers={"User-Agent": "SolanaTracker/1.0"})
            try:
                with urllib.request.urlopen(price_req, timeout=5) as presp:
                    price_raw = json.loads(presp.read())
                price_map = {
                    mint: float(info["usdPrice"])
                    for mint, info in price_raw.items()
                    if info and info.get("usdPrice")
                }
            except Exception:
                price_map = {}

            # 5. Compute USD values — only keep tokens with a known price >= $0.01
            holdings = []
            for e in entries:
                price     = price_map.get(e["mint"])
                usd_value = e["amount"] * price if price is not None else None

                if usd_value is None:
                    continue
                if usd_value < 0.01:
                    continue

                holdings.append({
                    "mint":            e["mint"],
                    "symbol":          e["symbol"],
                    "amount":          e["amount"],
                    "usd_value":       usd_value,
                    "price_per_token": price,
                })

            # Sort: largest USD value first
            holdings.sort(key=lambda h: (h["usd_value"] is None, -(h["usd_value"] or 0)))

            data = json.dumps(holdings).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        except Exception as e:
            import traceback
            traceback.print_exc()
            err = json.dumps({"error": str(e)}).encode()
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)

    def _send_event(self, text):
        try:
            self.wfile.write(f"data: {text}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, OSError):
            pass

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Listening on port {port}")
    server.serve_forever()
