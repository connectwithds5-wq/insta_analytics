import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

DB_PATH = Path(os.getenv("DB_PATH", "instagram_analytics.db"))
API_VERSION = os.getenv("META_API_VERSION", "v23.0")
# Instagram Login tokens use graph.instagram.com.
GRAPH_URL = f"https://graph.instagram.com/{API_VERSION}"


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS profile_snapshots (
      captured_at TEXT NOT NULL,
      followers INTEGER,
      follows INTEGER,
      media_count INTEGER,
      reach INTEGER,
      accounts_engaged INTEGER
    );
    CREATE TABLE IF NOT EXISTS reels (
      id TEXT PRIMARY KEY,
      caption TEXT,
      permalink TEXT,
      published_at TEXT,
      media_type TEXT,
      media_product_type TEXT,
      views INTEGER DEFAULT 0,
      reach INTEGER DEFAULT 0,
      likes INTEGER DEFAULT 0,
      comments INTEGER DEFAULT 0,
      shares INTEGER DEFAULT 0,
      saves INTEGER DEFAULT 0,
      interactions INTEGER DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_reels_published ON reels(published_at);
    """)
    con.commit(); con.close()


def api_get(path, params):
    r = requests.get(f"{GRAPH_URL}/{path}", params=params, timeout=30)
    if not r.ok:
        try:
            detail = r.json()
        except ValueError:
            detail = r.text[:1000]
        raise RuntimeError(f"Meta API {r.status_code} for {path}: {detail}")
    return r.json()


def token_and_user():
    return os.getenv("INSTAGRAM_ACCESS_TOKEN"), os.getenv("INSTAGRAM_USER_ID")


def fetch_and_store():
    token, user_id = token_and_user()
    if not token or not user_id:
        raise RuntimeError("Set INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_USER_ID in the environment.")

    fields = "id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count"
    media = api_get(f"{user_id}/media", {"fields": fields, "limit": 100, "access_token": token}).get("data", [])
    con = db()

    for item in media:
        metrics = {}
        try:
            ins = api_get(f"{item['id']}/insights", {"metric": "reach,likes,comments,shares,saved,views,total_interactions", "access_token": token})
            metrics = {x["name"]: x.get("values", [{}])[-1].get("value", 0) for x in ins.get("data", [])}
        except RuntimeError:
            metrics = {}
        con.execute("""
          INSERT INTO reels(id,caption,permalink,published_at,media_type,media_product_type,views,reach,likes,comments,shares,saves,interactions)
          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(id) DO UPDATE SET
            caption=excluded.caption, permalink=excluded.permalink, published_at=excluded.published_at,
            views=excluded.views, reach=excluded.reach, likes=excluded.likes, comments=excluded.comments,
            shares=excluded.shares, saves=excluded.saves, interactions=excluded.interactions
        """, (item["id"], item.get("caption",""), item.get("permalink",""), item.get("timestamp",""), item.get("media_type",""), item.get("media_product_type",""),
              metrics.get("views", 0), metrics.get("reach", 0), metrics.get("likes", item.get("like_count", 0)),
              metrics.get("comments", item.get("comments_count", 0)), metrics.get("shares", 0), metrics.get("saved", 0), metrics.get("total_interactions", 0)))

    con.commit(); con.close()
    return len(media)


def load_reels():
    return pd.read_sql_query("SELECT * FROM reels ORDER BY published_at DESC", db())


def score(df):
    if df.empty: return df
    base = df["reach"].replace(0, pd.NA)
    df["engagement_rate"] = ((df.likes + df.comments + df.shares + df.saves) / base * 100).fillna(0).round(2)
    df["performance_score"] = (df.views * 0.35 + df.reach * 0.25 + df.shares * 2 + df.saves * 2 + df.likes * 0.5 + df.comments).round(1)
    return df


def recommendation(df):
    if df.empty: return None
    d = df.copy(); d["published_at"] = pd.to_datetime(d.published_at, errors="coerce")
    d = d.dropna(subset=["published_at"])
    if d.empty: return None
    d["day"] = d.published_at.dt.day_name(); d["hour"] = d.published_at.dt.hour
    day = d.groupby("day")["performance_score"].mean().sort_values(ascending=False)
    hour = d.groupby("hour")["performance_score"].mean().sort_values(ascending=False)
    best_day = day.index[0]; best_hour = int(hour.index[0])
    recent = d.head(min(20, len(d)))
    return best_day, best_hour, recent.iloc[0].caption[:80] if not recent.empty else ""


st.set_page_config(page_title="Instagram Reels Analytics", page_icon="📊", layout="wide")
init_db()
st.title("📊 Instagram Reels Analytics")
st.caption("Analytics only — no uploading or publishing automation.")

with st.sidebar:
    st.header("Data")
    if st.button("🔄 Sync Instagram data", use_container_width=True):
        try:
            n = fetch_and_store(); st.success(f"Synced {n} media items.")
        except Exception as e:
            st.error(str(e))
    if st.button("Clear dashboard cache", use_container_width=True):
        st.cache_data.clear(); st.rerun()

_df = score(load_reels())
if _df.empty:
    st.info("No Reel data yet. Add your Meta/Instagram API secrets, then click Sync Instagram data.")
    st.stop()

followers = int(pd.to_numeric(_df.likes, errors="coerce").fillna(0).sum())
views = int(_df.views.sum()); reach = int(_df.reach.sum()); engagement = float(_df.engagement_rate.mean())

c1,c2,c3,c4 = st.columns(4)
c1.metric("Reels", len(_df)); c2.metric("Total views", f"{views:,}"); c3.metric("Total reach", f"{reach:,}"); c4.metric("Avg engagement", f"{engagement:.2f}%")

st.subheader("📈 Reel performance")
chart = _df.copy(); chart["published_at"] = pd.to_datetime(chart.published_at, errors="coerce"); chart = chart.dropna(subset=["published_at"]).sort_values("published_at").set_index("published_at")
st.line_chart(chart[["views","reach"]])

left,right = st.columns(2)
with left:
    st.subheader("🏆 Top Reels")
    cols=["published_at","views","reach","likes","comments","shares","saves","engagement_rate","performance_score"]
    st.dataframe(_df.sort_values("performance_score", ascending=False)[cols].head(10), use_container_width=True, hide_index=True)
with right:
    st.subheader("🕐 Best posting times")
    t = _df.copy(); t["published_at"] = pd.to_datetime(t.published_at, errors="coerce"); t["hour"] = t.published_at.dt.hour
    hourly=t.groupby("hour")["performance_score"].mean().sort_values(ascending=False).head(10).reset_index()
    st.dataframe(hourly, use_container_width=True, hide_index=True)

st.subheader("🤖 Next Reel Advisor")
rec = recommendation(_df)
if rec:
    day,hour,_ = rec
    a,b,c = st.columns(3)
    a.metric("Best day", day); b.metric("Best hour", f"{hour:02d}:00"); c.metric("Strategy", "Repeat top-performing pattern")
    st.info("Recommendation is based on your historical Reel performance. As more data is synced, the recommendation becomes more reliable.")

st.subheader("📋 All Reels")
show = _df[["id","published_at","caption","views","reach","likes","comments","shares","saves","engagement_rate","performance_score"]].copy()
st.dataframe(show, use_container_width=True, hide_index=True)
