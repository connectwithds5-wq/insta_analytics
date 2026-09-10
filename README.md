# Instagram Growth Command Center

Analytics + recommendation dashboard for Instagram Reels. It does **not** upload or publish content.

## What it does

- Reel views, reach, likes, comments, shares and saves when exposed by the Instagram API
- Profile/follower snapshots when the connected API exposes them
- Performance scoring weighted toward reach, views and shares
- Best posting day/hour from your own historical performance
- Trending audio shortlist for India + global Reels
- Account-fit score combining trend strength with your historical performance
- Reel format, hook, structure and posting-time recommendations
- Controlled experiments so audio and hook changes can be measured
- `recommendations.json` generated automatically after each analytics sync
- SQLite history so analytics accumulates over time
- GitHub Actions sync every 6 hours

## Architecture

`Instagram API → SQLite → account signals → trend intelligence → recommendation engine → dashboard`

The recommendation engine is intentionally deterministic and transparent: reach, views and shares matter more than likes, and trend signals never guarantee viral reach.

## Local setup

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Set:

```text
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_USER_ID=...
META_API_VERSION=v23.0
DB_PATH=instagram_analytics.db
```

## GitHub Actions

Secrets:

- `INSTAGRAM_ACCESS_TOKEN`
- `INSTAGRAM_USER_ID`
- `META_API_VERSION` (optional)

The workflow syncs every 6 hours, rebuilds account-aware recommendations and persists the database plus `recommendations.json`.

## Trend data

`trend_data.json` is a dated trend seed. Before publishing, always confirm the audio is available/licensed for the connected Instagram account inside Instagram. Trend data is a discovery input, not a promise of reach.

## Important

Instagram/Meta API availability varies by account type, permissions and API version. The dashboard only displays metrics that the connected API actually returns. No Instagram password is stored in this repository.
