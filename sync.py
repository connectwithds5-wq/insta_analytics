import os
import sqlite3
from pathlib import Path
import requests

DB_PATH = Path(os.getenv('DB_PATH', 'instagram_analytics.db'))
API_VERSION = os.getenv('META_API_VERSION', 'v23.0')
GRAPH_URL = f'https://graph.facebook.com/{API_VERSION}'


def api_get(path, params):
    r = requests.get(f'{GRAPH_URL}/{path}', params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def init_db(con):
    con.executescript('''
    CREATE TABLE IF NOT EXISTS profile_snapshots (
      captured_at TEXT NOT NULL, followers INTEGER, follows INTEGER, media_count INTEGER,
      reach INTEGER, accounts_engaged INTEGER
    );
    CREATE TABLE IF NOT EXISTS reels (
      id TEXT PRIMARY KEY, caption TEXT, permalink TEXT, published_at TEXT,
      media_type TEXT, media_product_type TEXT, views INTEGER DEFAULT 0, reach INTEGER DEFAULT 0,
      likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0,
      saves INTEGER DEFAULT 0, interactions INTEGER DEFAULT 0
    );
    ''')


def main():
    token = os.getenv('INSTAGRAM_ACCESS_TOKEN'); user_id = os.getenv('INSTAGRAM_USER_ID')
    if not token or not user_id:
        raise SystemExit('Missing INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_USER_ID')
    con = sqlite3.connect(DB_PATH); init_db(con)
    fields = 'id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count'
    media = api_get(f'{user_id}/media', {'fields': fields, 'limit': 100, 'access_token': token}).get('data', [])
    for item in media:
        metrics = {}
        try:
            ins = api_get(f"{item['id']}/insights", {'metric':'reach,likes,comments,shares,saved,views,total_interactions','access_token':token})
            metrics = {x['name']: x.get('values',[{}])[-1].get('value',0) for x in ins.get('data',[])}
        except requests.HTTPError:
            pass
        con.execute('''INSERT INTO reels VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET caption=excluded.caption, permalink=excluded.permalink,
          published_at=excluded.published_at, views=excluded.views, reach=excluded.reach,
          likes=excluded.likes, comments=excluded.comments, shares=excluded.shares,
          saves=excluded.saves, interactions=excluded.interactions''',
          (item['id'],item.get('caption',''),item.get('permalink',''),item.get('timestamp',''),
           item.get('media_type',''),item.get('media_product_type',''),metrics.get('views',0),metrics.get('reach',0),
           metrics.get('likes',item.get('like_count',0)),metrics.get('comments',item.get('comments_count',0)),
           metrics.get('shares',0),metrics.get('saved',0),metrics.get('total_interactions',0)))
    con.commit(); con.close(); print(f'Synced {len(media)} media items')

if __name__ == '__main__': main()
