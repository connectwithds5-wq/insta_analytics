import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from recommendation_engine import build_recommendations

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('DB_PATH', ROOT / 'instagram_analytics.db'))
REC_PATH = ROOT / 'recommendations.json'
TREND_PATH = ROOT / 'trend_data.json'

st.set_page_config(page_title='Retro Bollywood Growth Command Center', page_icon='🎞️', layout='wide')

st.markdown('''<style>
.block-container{padding-top:1.5rem;max-width:1400px}
[data-testid="stMetric"]{border:1px solid rgba(128,128,128,.18);padding:12px;border-radius:14px}
</style>''', unsafe_allow_html=True)


def db():
    return sqlite3.connect(DB_PATH)


def init_db():
    con = db()
    con.executescript('''
    CREATE TABLE IF NOT EXISTS profile_snapshots(captured_at TEXT NOT NULL, followers INTEGER, follows INTEGER, media_count INTEGER, reach INTEGER, accounts_engaged INTEGER);
    CREATE TABLE IF NOT EXISTS reels(id TEXT PRIMARY KEY, caption TEXT, permalink TEXT, published_at TEXT, media_type TEXT, media_product_type TEXT, views INTEGER DEFAULT 0, reach INTEGER DEFAULT 0, likes INTEGER DEFAULT 0, comments INTEGER DEFAULT 0, shares INTEGER DEFAULT 0, saves INTEGER DEFAULT 0, interactions INTEGER DEFAULT 0);
    ''')
    con.commit(); con.close()


def load_reels():
    con = db()
    try:
        df = pd.read_sql_query('SELECT * FROM reels ORDER BY published_at DESC', con)
    finally:
        con.close()
    if df.empty:
        return df
    for c in ['views','reach','likes','comments','shares','saves','interactions']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)
    df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce', utc=True)
    df['engagement_rate'] = ((df.likes + df.comments + df.shares + df.saves) / df.reach.replace(0, pd.NA) * 100).fillna(0)
    df['performance_score'] = (df.views*.35 + df.reach*.25 + df.shares*2 + df.saves*2 + df.likes*.5 + df.comments).round(1)
    return df


def load_profile():
    con = db()
    try:
        df = pd.read_sql_query('SELECT * FROM profile_snapshots ORDER BY captured_at DESC', con)
    finally:
        con.close()
    return df


def load_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return fallback


def human(n):
    n = float(n or 0)
    if n >= 1_000_000: return f'{n/1_000_000:.1f}M'
    if n >= 1_000: return f'{n/1_000:.1f}K'
    return f'{int(n):,}'


init_db()
reels = load_reels()
profile = load_profile()
rec = load_json(REC_PATH, {})
trend = load_json(TREND_PATH, {'tracks': []})

st.title('🎞️ Retro Bollywood Growth Command Center')
st.caption('Niche locked: Old Hindi Bollywood • 70s/80s/90s/early-2000s • nostalgia • romance • heartbreak. Generic new songs are excluded.')

with st.sidebar:
    st.header('Controls')
    if st.button('🔄 Rebuild recommendations', use_container_width=True):
        build_recommendations()
        st.rerun()
    st.divider()
    st.write('**Data pipeline**')
    st.write('Instagram API → SQLite → niche detection → account scoring → Retro Bollywood discovery → recommendation')
    if profile.empty:
        st.warning('Profile history is not available yet. Run the Analytics Sync once more after the latest update.')

if reels.empty:
    st.info('No Reel rows are stored yet. Run **Instagram Analytics Sync** from GitHub Actions, then refresh this dashboard.')
    st.stop()

views = reels.views.sum(); reach = reels.reach.sum(); shares = reels.shares.sum(); avg_eng = reels.engagement_rate.mean()
c1,c2,c3,c4,c5 = st.columns(5)
c1.metric('Reels', len(reels)); c2.metric('Total views', human(views)); c3.metric('Total reach', human(reach)); c4.metric('Shares', human(shares)); c5.metric('Avg engagement', f'{avg_eng:.2f}%')

if not profile.empty:
    p = profile.iloc[0]
    p1,p2,p3 = st.columns(3)
    p1.metric('Followers', human(p.get('followers', 0))); p2.metric('Following', human(p.get('follows', 0))); p3.metric('Profile media', human(p.get('media_count', 0)))

st.divider()
tab1, tab2, tab3, tab4 = st.tabs(['🎯 What to Post', '🎵 Retro Songs', '📊 Account Analytics', '🧪 Experiments'])

with tab1:
    st.subheader('🎯 What should I post next?')
    primary = rec.get('primary_recommendation')
    if primary:
        a,b,c = st.columns(3)
        a.metric('Recommended retro song', primary['song'])
        b.metric('Niche-fit score', f"{rec.get('trending_audio_ranked',[{}])[0].get('match_score',0)}/100")
        c.metric('Best posting hour', f"{primary.get('posting_hour_local',20):02d}:00 IST")
        st.success(f"**{primary['song']} — {primary['artist']}**  •  {primary['reel_format']}  •  {primary.get('era','')}")
        st.write(primary['why'])
        left,right = st.columns(2)
        with left:
            st.markdown('### Hook'); st.write(primary['hook'])
            st.markdown('### Structure')
            for x in primary['structure']: st.write('• ' + x)
        with right:
            st.markdown('### Execution')
            st.write('Old-song feeling → relatable memory → emotional twist → lyric/payoff → seamless loop.')
            st.warning(primary['audio_note'])
    else:
        st.info('Run the recommendation engine to generate the next Retro Bollywood recommendation.')

    st.markdown('### 🧠 Account signals')
    sample = rec.get('sample', {})
    s1,s2,s3 = st.columns(3)
    s1.metric('Training reels', sample.get('sample_size', 0)); s2.metric('Avg reel reach', human(sample.get('baseline_reach',0))); s3.metric('Avg reel views', human(sample.get('baseline_views',0)))
    if sample.get('niche_confidence') is not None: st.metric('Retro niche confidence', f"{sample.get('niche_confidence',0):.0f}%")
    if sample.get('best_hours'): st.write('**Strongest IST hours:** ' + ' • '.join(f"{x['hour']:02d}:00" for x in sample['best_hours']))
    if sample.get('top_captions'):
        st.write('**Top-performing caption patterns:**')
        for caption in sample['top_captions']: st.write('• ' + caption)

with tab2:
    st.subheader('🎵 Retro Bollywood audio shortlist')
    st.caption('This is deliberately NOT a generic Instagram trending-song list. Songs must pass the Retro Bollywood niche filter.')
    rows = rec.get('trending_audio_ranked', []) or trend.get('tracks', [])
    if rows:
        table = pd.DataFrame([{'Rank': i+1, 'Song': x.get('title'), 'Artist': x.get('artist'), 'Era': x.get('era'), 'Niche fit': x.get('match_score'), 'Discovery': x.get('discovery_score'), 'Observed views': x.get('observed_views')} for i,x in enumerate(rows[:15])])
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.markdown('**Best current experiments:**')
        for x in rows[:6]: st.write(f"🎧 **{x.get('title')} — {x.get('artist')}** · {x.get('era','')} · {', '.join(x.get('formats',[])[:2])}")
    st.info('Before using any song, open the audio inside Instagram and confirm the official/original sound is available for your account.')

with tab3:
    st.subheader('📊 What is actually driving reach?')
    chart = reels.copy().dropna(subset=['published_at']).sort_values('published_at').set_index('published_at')
    if not chart.empty: st.line_chart(chart[['views','reach']])
    left,right = st.columns(2)
    cols=['published_at','caption','reach','views','shares','saves','likes','comments','engagement_rate','performance_score']
    with left:
        st.markdown('### 🏆 Top 10 by reach'); st.dataframe(reels.sort_values('reach', ascending=False)[cols].head(10), use_container_width=True, hide_index=True)
    with right:
        st.markdown('### 🔁 Top 10 by shares'); st.dataframe(reels.sort_values('shares', ascending=False)[cols].head(10), use_container_width=True, hide_index=True)
    timing = reels.dropna(subset=['published_at']).copy()
    if not timing.empty:
        local = timing.published_at.dt.tz_convert('Asia/Kolkata')
        timing['hour'] = local.dt.hour; timing['day'] = local.dt.day_name()
        h = timing.groupby('hour')['performance_score'].mean().sort_values(ascending=False).head(8).reset_index()
        d = timing.groupby('day')['performance_score'].mean().sort_values(ascending=False).head(7).reset_index()
        x,y = st.columns(2)
        x.markdown('### ⏰ Best IST hours'); x.dataframe(h, use_container_width=True, hide_index=True)
        y.markdown('### 📅 Best days'); y.dataframe(d, use_container_width=True, hide_index=True)

with tab4:
    st.subheader('🧪 Controlled Retro Bollywood experiments')
    st.write('Test one variable at a time: song + opening hook, while keeping visual/story quality consistent.')
    for i,x in enumerate(rec.get('experiments', []), 1):
        with st.container(border=True):
            st.markdown(f"### Test {i}: {x['song']} — {x['artist']}")
            st.write(f"**Score:** {x['score']}/100  •  **Era:** {x.get('era','')}  •  **Format:** {x['format']}")
            st.write(x.get('test',''))
    st.markdown('### Scoring policy')
    st.write('• Retro niche is a hard filter. • Reach/shares matter more than likes. • Account history beats generic trends. • Public discovery signals are secondary. • No recommendation guarantees viral reach.')
