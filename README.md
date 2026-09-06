Solana Wallet Transaction Tracker
From this

<img width="699" height="325" alt="sql" src="https://github.com/user-attachments/assets/05f9b033-57c7-44f2-934f-f5343fa46503" />
To this with claude code
<img width="882" height="787" alt="image" src="https://github.com/user-attachments/assets/fb00a5c4-bf1b-4e7c-9316-b791ffc8046a" />

Tech Stack

Python 3.11+
SQLite3
Helius API 
requests, python-dotenv
Features

Paginates through up to 500 transactions (5 pages × 100)
Parses token swaps — resolves mint addresses to readable names (wSOL, USDC, etc.)
Converts lamport fees to SOL
Displays: Total value, SOL balance, Token balance
