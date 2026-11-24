# Solana Wallet Bubble Map

Live: https://solanawallettransactions.onrender.com

Paste a Solana wallet: see its holdings as a 3D bubble map, its value, and a year of trading activity.<br>
From this

<img width="699" height="325" alt="sql" src="https://github.com/user-attachments/assets/05f9b033-57c7-44f2-934f-f5343fa46503" />
<br>To this with claude code
<img width="882" height="787" alt="image" src="https://github.com/user-attachments/assets/fb00a5c4-bf1b-4e7c-9316-b791ffc8046a" />

Tech Stack: Python 3.x · Helius DAS (`searchAssets`) + Enhanced Transactions API · Jupiter Price API v3 · Three.js

Features: Live holdings, names and USD prices in one Helius call (Jupiter fills in prices Helius lacks) · 3D bubble map of token holdings · Clickable token detail panel · Stats: Total Value, SOL Balance, Token Balance · 52-week trading activity heatmap (last 500 transactions)

## Run locally

```
pip install -r requirements.txt
echo HELIUS_API_KEY=your_key > .env
echo JUPITER_API_KEY=your_key >> .env   # optional, free at portal.jup.ag
python server.py        # http://localhost:5000
```

`server.py` is the web app (one JSON endpoint: `/api/wallet?address=`). `main.py` / `runner.py` are the original Postgres CLI and need `DATABASE_URL`; the site doesn't use them.

MVP status and open questions: [docs/MVP-POLISH.md](docs/MVP-POLISH.md).
