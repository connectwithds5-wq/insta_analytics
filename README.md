# Instagram Reels Analytics Dashboard

Analytics-only dashboard for Instagram Reels. It does **not** upload or publish content.

## Features

- Reel views, reach, likes, comments, shares and saves when exposed by the Instagram API
- Engagement rate and performance score
- Top-performing Reels
- Best posting day and hour from historical data
- Next Reel Advisor based on your own historical performance
- SQLite history so analytics can accumulate over time
- Optional GitHub Actions sync every 6 hours

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables:

```text
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_USER_ID=...
META_API_VERSION=v23.0
```

Run:

```bash
streamlit run app.py
```

## GitHub Actions

Add repository secrets:

- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`
- `META_API_VERSION` (optional)

The workflow in `.github/workflows/sync.yml` can then sync analytics every 6 hours. It stores the SQLite database in the repository so historical snapshots can accumulate.

## Important

Instagram/Meta API availability varies by account type, permissions and API version. The dashboard only displays metrics that the connected API actually returns. No Instagram password is stored in this repository.
