import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / 'instagram_analytics.db'
OUT = ROOT / 'dashboard' / 'dashboard_data.json'


def read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    reels, profile = [], []
    if DB.exists():
        con = sqlite3.connect(DB)
        try:
            cur = con.execute('SELECT id,caption,permalink,published_at,media_type,media_product_type,views,reach,likes,comments,shares,saves,interactions FROM reels ORDER BY published_at DESC')
            cols = [d[0] for d in cur.description]
            reels = [dict(zip(cols, row)) for row in cur.fetchall()]
            cur = con.execute('SELECT captured_at,followers,follows,media_count,reach,accounts_engaged FROM profile_snapshots ORDER BY captured_at DESC LIMIT 30')
            cols = [d[0] for d in cur.description]
            profile = [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()
    recommendations = read_json(ROOT / 'recommendations.json', {})
    trends = read_json(ROOT / 'trend_data.json', {'updated_at': '', 'region': '', 'tracks': []})
    payload = {
        'generated_at': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'reels': reels,
        'profile': profile,
        'recommendations': recommendations,
        'trend_data': trends,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(f'Wrote {OUT} ({len(reels)} reels, {len(profile)} profile snapshots)')


if __name__ == '__main__':
    main()
