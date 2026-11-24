# MVP polish

State after the 2026-11-24 cleanup, and what is left before showing it to people.

## Done
- One endpoint, `/api/wallet?address=`, returns holdings + recent transactions. Each request stands alone,
  so two visitors never see each other's wallet (the old global cache mixed them up).
- Holdings come from one Helius DAS `searchAssets` call (SOL, tokens, names, prices for the
  top ~10K tokens). Jupiter Price API v3 only prices what Helius doesn't; it uses
  `api.jup.ag` when `JUPITER_API_KEY` is set, else the free `lite-api` host Jupiter is retiring.
- Threaded server, 60 s per-address cache, `/healthz` for Render.
- Address checked (base58, 32-44 chars) on both sides; plain errors shown to the user.
- API keys never reach the browser and are masked in server logs.
- Token names/symbols from chain metadata are escaped (they could carry HTML/script).
- Frontend bugs: click/resize listeners no longer pile up per search. (The activity calendar was removed 2026-11-24: busy wallets have more history than a lookup can count, so most days showed no data.)
- Colours and type from the salary repo's theme; layout, wording and features unchanged.
- Removed seven endpoints the page never called. The Postgres CLI (`main.py`, `runner.py`,
  `db.py`, `queries.py`) is untouched and not used by the site.

## Not verified yet
- Live Helius + Jupiter calls (the cloud session that made these changes could not reach
  them; tested against recorded response shapes). Run locally with real keys before deploying.

## Open questions (James)
- Rename the GitHub repo to `solana-wallet-bubble-map` (Settings > General > Repository name;
  old links redirect). The Render service is still named `solana-tracker` on purpose: renaming it in
  render.yaml makes Render create a new service with a new URL. For a new URL, add a custom domain
  or create a new service in the Render dashboard (and set the keys there).
- Who it's for and how it makes money (see the product brainstorm in Studio-Repository
  `ideas/bubble-map.md`).
- Keep or delete the Postgres CLI and `DATABASE_URL`.
- History depth: last 500 transactions (`MAX_PAGES` in `config.py`). More costs credits and time.
