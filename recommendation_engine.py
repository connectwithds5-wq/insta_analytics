import json
import math
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(__import__('os').getenv('DB_PATH', ROOT / 'instagram_analytics.db'))
TREND_PATH = ROOT / 'trend_data.json'
NICHE_PATH = ROOT / 'niche_config.json'
OUT_PATH = ROOT / 'recommendations.json'


def load_json(path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def load_reels():
    if not DB_PATH.exists():
        return pd.DataFrame()
    con = sqlite3.connect(DB_PATH)
    try:
        df = pd.read_sql_query('SELECT * FROM reels', con)
    finally:
        con.close()
    if df.empty:
        return df
    for col in ['views', 'reach', 'likes', 'comments', 'shares', 'saves', 'interactions']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        else:
            df[col] = 0
    df['published_at'] = pd.to_datetime(df.get('published_at'), errors='coerce', utc=True)
    df['caption'] = df.get('caption', '').fillna('').astype(str)
    df['engagement_rate'] = ((df.likes + df.comments + df.shares + df.saves) / df.reach.replace(0, pd.NA) * 100).fillna(0)
    df['performance_score'] = (df.views * .35 + df.reach * .25 + df.shares * 2 + df.saves * 2 + df.likes * .5 + df.comments).fillna(0)
    return df


def account_signals(df, niche):
    terms = niche.get('account_signal_terms', [])
    if df.empty:
        return {'sample_size': 0, 'best_hours': [], 'best_days': [], 'top_captions': [], 'baseline_reach': 0, 'baseline_views': 0, 'baseline_engagement': 0, 'niche_signal_hits': 0, 'niche_confidence': 0}
    work = df.copy()
    # Instagram timestamps are normalized to UTC by the API; recommendations must use India local time.
    local_time = work.published_at.dt.tz_convert('Asia/Kolkata')
    work['day'] = local_time.dt.day_name()
    work['hour'] = local_time.dt.hour
    best_hours = work.groupby('hour')['performance_score'].mean().sort_values(ascending=False).head(3)
    best_days = work.groupby('day')['performance_score'].mean().sort_values(ascending=False).head(3)
    top = work.sort_values('performance_score', ascending=False).head(5)
    text = ' '.join(work.caption.str.lower().tolist())
    hits = sum(text.count(term.lower()) for term in terms)
    niche_confidence = min(100, round((hits / max(3, len(df))) * 100 + (25 if hits else 0), 1))
    return {
        'sample_size': int(len(work)),
        'best_hours': [{'hour': int(k), 'score': round(float(v), 1)} for k, v in best_hours.items()],
        'best_days': [{'day': str(k), 'score': round(float(v), 1)} for k, v in best_days.items()],
        'top_captions': [str(x)[:100] for x in top.caption if str(x).strip()],
        'baseline_reach': round(float(work.reach.mean()), 1),
        'baseline_views': round(float(work.views.mean()), 1),
        'baseline_engagement': round(float(work.engagement_rate.mean()), 2),
        'niche_signal_hits': int(hits),
        'niche_confidence': niche_confidence,
    }


def normalize_title(text):
    return re.sub(r'[^a-z0-9]+', ' ', str(text).lower()).strip()


def account_track_signal(df, track):
    if df.empty:
        return {'matched_reels': 0, 'score': 0}
    title = normalize_title(track.get('title', ''))
    tokens = [t for t in title.split() if len(t) >= 3]
    if not tokens:
        return {'matched_reels': 0, 'score': 0}
    mask = df.caption.str.lower().map(normalize_title).apply(lambda s: sum(t in s.split() for t in tokens) >= max(1, math.ceil(len(tokens) * .45)))
    matched = df[mask]
    if matched.empty:
        return {'matched_reels': 0, 'score': 0}
    baseline = max(1.0, float(df.performance_score.mean()))
    relative = min(100, (float(matched.performance_score.mean()) / baseline) * 50)
    return {'matched_reels': int(len(matched)), 'score': round(relative, 1)}


def discovery_score(track):
    views = track.get('observed_views')
    if views is None:
        return 45.0
    return round(min(100, max(0, math.log10(max(views, 1)) / 7 * 100)), 1)


def score_track(track, df, signals, niche):
    if track.get('lane') != 'Retro Bollywood':
        return -1
    if niche.get('hard_exclude_new_releases') and not track.get('era'):
        return -1
    niche_fit = float(track.get('niche_score', 100))
    discovery = discovery_score(track)
    account = account_track_signal(df, track)
    current_signal = 80.0 if 'currently ranked' in str(track.get('current_signal', '')).lower() else 55.0
    account_niche = float(signals.get('niche_confidence', 0))
    score = niche_fit * .45 + discovery * .25 + current_signal * .10 + account['score'] * .10 + account_niche * .10
    return round(min(99, score), 1)


def build_recommendations():
    df = load_reels()
    niche = load_json(NICHE_PATH, {'mode': 'retro_bollywood', 'name': 'Retro Bollywood', 'hard_exclude_new_releases': True})
    trend_data = load_json(TREND_PATH, {'tracks': []})
    signals = account_signals(df, niche)
    ranked = []
    for track in trend_data.get('tracks', []):
        item = dict(track)
        score = score_track(track, df, signals, niche)
        if score < 0:
            continue
        item['match_score'] = score
        item['account_track_signal'] = account_track_signal(df, track)
        item['discovery_score'] = discovery_score(track)
        ranked.append(item)
    ranked.sort(key=lambda x: x['match_score'], reverse=True)

    top = ranked[:6]
    primary = None
    if top:
        p = top[0]
        hour = signals['best_hours'][0]['hour'] if signals['best_hours'] else 20
        primary = {
            'song': p['title'], 'artist': p['artist'], 'movie': p.get('movie', ''), 'era': p.get('era', ''),
            'why': f"Retro-niche fit {p.get('niche_score', 100)}/100 + discovery signal {p.get('discovery_score', 0)}/100 + account fit.",
            'reel_format': p.get('formats', ['nostalgia'])[0],
            'hook': '0–1 sec: पुराने गाने की एक ऐसी feeling जो viewer को अपनी याद याद दिला दे',
            'structure': ['0–2s nostalgic hook', '2–6s relatable memory', '6–10s emotional turn', '10–13s lyric/payoff', '13–15s seamless loop'],
            'posting_hour_local': hour,
            'audio_note': 'Use the official Instagram audio page and confirm the original/official sound is available for this account before publishing.'
        }

    experiments = [{
        'song': x['title'], 'artist': x['artist'], 'score': x['match_score'], 'format': x.get('formats', ['nostalgia'])[0], 'era': x.get('era', ''),
        'test': 'Keep the visual/story quality constant; test only the retro song + opening hook so reach can be attributed.'
    } for x in top[:4]]

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model': 'retro-bollywood niche-aware deterministic ranking',
        'niche': niche, 'sample': signals, 'primary_recommendation': primary,
        'trending_audio_ranked': ranked, 'experiments': experiments,
        'rules': {
            'niche_priority': 'Retro Bollywood niche is a hard filter. Generic new songs are not eligible.',
            'ranking_priority': 'niche fit > account performance/history > public discovery signal > generic trendiness',
            'new_song_guard': 'Do not recommend a current new release unless explicitly classified as a retro remix/revival crossover.',
            'reach_priority': 'shares + reach + views, not likes alone',
            'trend_guard': 'Public trend signals are discovery inputs, not a guarantee of reach.',
            'account_learning': 'When a song title is present in account captions, its historical performance gets an additional account-fit signal.',
            'timezone': 'Best posting hours are calculated in Asia/Kolkata, not UTC.'
        }
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"Wrote {OUT_PATH}: niche={niche.get('mode')} reels={len(df)} candidates={len(ranked)}")
    return payload


if __name__ == '__main__':
    build_recommendations()
