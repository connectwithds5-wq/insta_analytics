import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(__import__('os').getenv('DB_PATH', ROOT / 'instagram_analytics.db'))
TREND_PATH = ROOT / 'trend_data.json'
OUT_PATH = ROOT / 'recommendations.json'

LANES = {
    'Hindi/Indian': ['emotional story', 'cinematic text', 'romantic reveal', 'relationship POV', 'sad story', 'emotional twist', 'breakup', 'relatable text', 'rain mood', 'nostalgia', 'love story', 'deep emotion', 'memory', 'cinematic', 'POV'],
    'Global': ['quick reveal', 'playful transition', 'lifestyle', 'dreamy aesthetic', 'romantic', 'soft cinematic', 'fast cuts', 'transition', 'high energy', 'emotional reveal', 'relationship', 'storytime', 'fun POV'],
}


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
    for col in ['views','reach','likes','comments','shares','saves','interactions']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    df['published_at'] = pd.to_datetime(df['published_at'], errors='coerce', utc=True)
    df['engagement_rate'] = ((df.likes + df.comments + df.shares + df.saves) / df.reach.replace(0, pd.NA) * 100).fillna(0)
    df['performance_score'] = (df.views * .35 + df.reach * .25 + df.shares * 2 + df.saves * 2 + df.likes * .5 + df.comments).fillna(0)
    return df


def load_trends():
    if not TREND_PATH.exists():
        return []
    return json.loads(TREND_PATH.read_text(encoding='utf-8')).get('tracks', [])


def norm(value, low, high):
    if high <= low:
        return 50.0
    return round(max(0, min(100, (value - low) / (high - low) * 100)), 1)


def account_signals(df):
    if df.empty:
        return {'sample_size': 0, 'best_hours': [], 'best_days': [], 'top_captions': [], 'baseline_reach': 0, 'baseline_views': 0, 'baseline_engagement': 0}
    work = df.copy()
    work['day'] = work.published_at.dt.day_name()
    work['hour'] = work.published_at.dt.hour
    best_hours = work.groupby('hour')['performance_score'].mean().sort_values(ascending=False).head(3)
    best_days = work.groupby('day')['performance_score'].mean().sort_values(ascending=False).head(3)
    top = work.sort_values('performance_score', ascending=False).head(5)
    return {
        'sample_size': int(len(work)),
        'best_hours': [{'hour': int(k), 'score': round(float(v),1)} for k,v in best_hours.items()],
        'best_days': [{'day': str(k), 'score': round(float(v),1)} for k,v in best_days.items()],
        'top_captions': [str(x)[:100] for x in top.caption.fillna('') if str(x).strip()],
        'baseline_reach': round(float(work.reach.mean()), 1),
        'baseline_views': round(float(work.views.mean()), 1),
        'baseline_engagement': round(float(work.engagement_rate.mean()), 2),
    }


def score_track(track, signals, sample_size):
    trend = float(track.get('trend_score', 0))
    lane_bonus = 0
    # Hindi/Indian is the primary recommendation lane for this account's emotional-reel use case.
    if track.get('lane') == 'Hindi/Indian':
        lane_bonus = 8
    freshness = max(0, 10 - int(track.get('rank', 20)) * .3)
    confidence = min(15, sample_size * 1.5)
    score = trend * .62 + lane_bonus + freshness + confidence
    return round(min(99, score), 1)


def build_recommendations():
    df = load_reels()
    trends = load_trends()
    signals = account_signals(df)
    ranked = []
    for t in trends:
        item = dict(t)
        item['match_score'] = score_track(t, signals, signals['sample_size'])
        ranked.append(item)
    ranked.sort(key=lambda x: x['match_score'], reverse=True)

    top = ranked[:6]
    if top:
        primary = top[0]
        format_name = primary.get('formats', ['emotional story'])[0]
        hour = signals['best_hours'][0]['hour'] if signals['best_hours'] else 20
        concept = {
            'song': primary['title'],
            'artist': primary['artist'],
            'why': f"Trend score {primary['trend_score']}/100 + account-fit score {primary['match_score']}/100.",
            'reel_format': format_name,
            'hook': '0–1 sec: एक ऐसी line जो viewer को अपनी कहानी लगे',
            'structure': ['0–2s hook', '2–6s relatable setup', '6–10s emotional turn', '10–13s payoff', '13–15s loop/CTA'],
            'posting_hour_local': hour,
            'audio_note': 'Use the official Instagram audio page and confirm the sound is available for this account before publishing.'
        }
    else:
        concept = None

    experiments = []
    for t in top[:4]:
        experiments.append({
            'song': t['title'],
            'artist': t['artist'],
            'score': t['match_score'],
            'format': t.get('formats', ['emotional story'])[0],
            'test': 'Same story quality, change only audio + opening hook so the result is attributable.'
        })

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'model': 'account-aware deterministic ranking',
        'sample': signals,
        'primary_recommendation': concept,
        'trending_audio_ranked': ranked,
        'experiments': experiments,
        'rules': {
            'reach_priority': 'shares + reach + views, not likes alone',
            'anti_overfitting': 'do not repeat the same audio more than twice in the top experiment set',
            'trend_guard': 'trending audio is a discovery signal, not a guarantee of reach',
            'cold_start': 'until enough account data exists, use trend score + format fit; after 10+ reels, weight account history more heavily'
        }
    }
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Wrote {OUT_PATH} using {len(df)} reels and {len(trends)} trend candidates')
    return payload


if __name__ == '__main__':
    build_recommendations()
