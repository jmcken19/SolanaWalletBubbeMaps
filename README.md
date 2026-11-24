Solana Wallet Transaction Tracker<br>
From this

<img width="699" height="325" alt="sql" src="https://github.com/user-attachments/assets/05f9b033-57c7-44f2-934f-f5343fa46503" />
<br>To this with claude code
<img width="882" height="787" alt="image" src="https://github.com/user-attachments/assets/fb00a5c4-bf1b-4e7c-9316-b791ffc8046a" />

Tech Stack: Python 3.x · Helius REST API + RPC · Jupiter Lite Price API · Three.js · requests

Features: Live wallet holdings via Helius RPC · Token names via Helius DAS · Live USD prices via Jupiter · 3D bubble map of token holdings · Holdings table · 52-week trading activity heatmap (last 500 transactions) · Token detail panel · Shareable `?address=` links

## Run locally

```
pip install -r requirements.txt
echo HELIUS_API_KEY=your_key > .env
python server.py        # http://localhost:5000
```

`server.py` is the web app (one JSON endpoint: `/api/wallet?address=`). `main.py` / `runner.py` are the original Postgres CLI and need `DATABASE_URL`; the site doesn't use them.

MVP status and open questions: [docs/MVP-POLISH.md](docs/MVP-POLISH.md).
