# MVP polish

State after the 2026-11-24 cleanup, and what is left before showing it to people.

## Done
- One endpoint, `/api/wallet?address=`, returns holdings + activity. Each request stands alone,
  so two visitors never see each other's wallet (the old global cache mixed them up).
- Threaded server (one slow wallet no longer blocks everyone), 60 s per-address cache.
- Address checked (base58, 32-44 chars) on both sides; plain-language errors, shown to the user.
- Helius key never reaches the browser: errors are generic, server logs mask the key.
- Token names/symbols from chain metadata are escaped (they could carry HTML/script).
- Token names fetched with one `getAssetBatch` call; prices fetched in chunks of 50 (no 414s).
- UI copied from the salary repo's design system: near-black ground, Archivo + IBM Plex,
  mono labels with the spectrum rule, orange `--signal` for data.
- Holdings table (works without WebGL, on phones, with a keyboard) linked to the bubble map;
  token panel with Solscan links; shareable `?address=` links; heatmap in UTC days, newest
  weeks visible first on phones; reduced-motion respected.
- Removed seven unused endpoints (`/run`, `/tokens`, `/token_detail`, `/summary`, `/trend`,
  `/token_pnl`, `/prices`). The SQL/Postgres CLI (`main.py`, `runner.py`, `db.py`,
  `queries.py`) is untouched and not used by the site.

## Not verified yet
- Live Helius + Jupiter calls (the cloud session that made these changes could not reach
  them). Run locally with a real `HELIUS_API_KEY` before deploying.
- Jupiter `lite-api.jup.ag/price/v3` is free but rate limited and may need an API key later.

## Open questions (James)
- Name, and whether it stays "Solana Tracker".
- Who it's for and how it makes money (free tool for the channel? paid tiers? none?).
- Hosting: keep Render (free tier sleeps), or move?
- Keep or delete the Postgres CLI and `DATABASE_URL`.
- History depth: today 500 most recent transactions (`MAX_PAGES` in `config.py`). More costs
  Helius credits and time per lookup.
- Next features worth it for an MVP: PnL per token, wallet compare, holder bubble map for a
  token (who holds a coin, Bubblemaps-style)?
