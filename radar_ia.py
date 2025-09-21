# radar_ia.py
# Radar IA - somente ao vivo, eventos com display_time e category, estatísticas resumidas, cache simples
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, traceback, time
from typing import List, Dict, Any

app = FastAPI(title="Radar IA")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_SPORTS_KEY = "7baa5e00c8ae57d0e6240f790c6840dd"
API_HOST = "v3.football.api-sports.io"
API_URL = f"https://{API_HOST}"
HEADERS = {"x-rapidapi-key": API_SPORTS_KEY, "x-rapidapi-host": API_HOST}

CACHE_TTL = 8
_cache = {}

def _cache_get(key):
    rec = _cache.get(key)
    if not rec: return None
    if time.time() - rec["ts"] > CACHE_TTL:
        _cache.pop(key, None)
        return None
    return rec["data"]

def _cache_set(key, data):
    _cache[key] = {"ts": time.time(), "data": data}

def _get(endpoint: str, params: dict = None):
    try:
        r = requests.get(f"{API_URL}/{endpoint}", headers=HEADERS, params=params, timeout=25)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"[Radar GET] {endpoint} {params} -> {e}")
        print(traceback.format_exc())
        return []

def _compute_sort_key(ev: dict) -> int:
    t = ev.get("time", {}) or {}
    try:
        elapsed = int(t.get("elapsed") or 0)
    except:
        elapsed = 0
    try:
        sec = int(t.get("second")) if t.get("second") is not None else 0
    except:
        sec = 0
    try:
        extra = int(t.get("extra") or 0)
    except:
        extra = 0
    return (elapsed + extra) * 60 + sec

def _format_display_time(ev: dict) -> str:
    t = ev.get("time", {}) or {}
    elapsed = t.get("elapsed")
    second = t.get("second")
    extra = t.get("extra")
    if elapsed is None: return "-"
    try:
        elapsed_i = int(elapsed)
    except:
        return str(elapsed)
    sec_part = f"{int(second):02d}\"" if second is not None else ""
    if extra:
        return f"{elapsed_i}+{extra}'{sec_part}"
    return f"{elapsed_i}'{sec_part}"

def _classify(ev: dict) -> str:
    t = (ev.get("type") or "").lower()
    d = (ev.get("detail") or "").lower()
    if "goal" in t or "goal" in d: return "Goal"
    if "card" in t or "card" in d:
        if "yellow" in d or "yellow" in t: return "Yellow Card"
        if "red" in d or "red" in t: return "Red Card"
        return "Card"
    if "substitution" in t or "substitution" in d or "sub" in d: return "Substitution"
    if "shot" in t or "shot" in d or "shoot" in d:
        if "on goal" in d or "on target" in d: return "Shot on Target"
        return "Shot"
    if "corner" in t or "corner" in d: return "Corner"
    if "foul" in t or "foul" in d: return "Foul"
    if "penalty" in t or "penalty" in d: return "Penalty"
    if "injury" in d or "injury" in t or "break" in d: return "Injury/Interruption"
    # fallback
    return ev.get("type") or ev.get("detail") or "Other"

@app.get("/ligas")
def list_leagues():
    cache_key = "ligas_live"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    data = _get("fixtures", {"live": "all"})
    leagues = {}
    for f in data:
        l = f.get("league", {}) or {}
        leagues[l.get("id")] = {"id": l.get("id"), "name": l.get("name"), "country": l.get("country")}
    out = list(leagues.values())
    _cache_set(cache_key, out)
    return out

@app.get("/jogos-aovivo")
def live_games(league: int = Query(None)):
    cache_key = f"jogos_live_{league or 'all'}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    params = {"live": "all"}
    if league:
        params["league"] = league
    data = _get("fixtures", params)
    results = []
    for f in data:
        results.append({
            "game_id": f["fixture"]["id"],
            "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})",
            "league": f.get("league"),
            "teams": f.get("teams"),
            "fixture": f.get("fixture"),
            "status": f.get("fixture", {}).get("status")
        })
    _cache_set(cache_key, results)
    return results

@app.get("/stats-aovivo/{game_id}")
def stats_aovivo(game_id: int):
    cache_key = f"stats_{game_id}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    fixture_data = _get("fixtures", {"id": game_id})
    if not fixture_data:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    fixture = fixture_data[0]

    # eventos -> processar, ordenar decrescente (mais recente primeiro)
    events_raw = _get("fixtures/events", {"fixture": game_id})
    processed = []
    for ev in events_raw:
        display_time = _format_display_time(ev)
        category = _classify(ev)
        player_name = ev.get("player", {}).get("name") if ev.get("player") else None
        team_name = ev.get("team", {}).get("name") if ev.get("team") else None
        processed.append({
            "display_time": display_time,
            "category": category,
            "type": ev.get("type"),
            "detail": ev.get("detail"),
            "player": player_name,
            "team": team_name,
            "raw": ev,
            "_sort": _compute_sort_key(ev)
        })
    processed.sort(key=lambda x: x["_sort"], reverse=True)

    # estatísticas (resumir por team)
    stats_raw = _get("fixtures/statistics", {"fixture": game_id})
    # API returns a list with each team's statistics:
    # [{ "team": {...}, "statistics": [ {"type":"Shots on Goal", "value": 2}, ... ] }, ... ]
    stats = {"home": {}, "away": {}}
    try:
        for team_stats in stats_raw:
            team = team_stats.get("team", {})
            team_id = team.get("id")
            # map team id to home/away by comparing fixture's teams
            home_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_id = fixture.get("teams", {}).get("away", {}).get("id")
            side = "home" if team_id == home_id else "away"
            for s in team_stats.get("statistics", []):
                key = s.get("type") or s.get("name") or ""
                val = s.get("value")
                # normalize some keys to simpler names
                key_norm = key.lower().replace(" ", "_").replace("(", "").replace(")", "")
                stats[side][key_norm] = val
    except Exception:
        pass

    # estimativa de acréscimos simplificada: contar eventos recentes
    extra = None
    try:
        elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
        if elapsed is not None:
            elapsed_i = int(elapsed)
            # heurística simples:
            # contar subs & cards & injuries in last 15 minutes -> seconds
            recent_seconds = 0
            for e in processed:
                # consider events in last 20 minutes (~1200s) by elapsed
                ev_elapsed = e["raw"].get("time", {}).get("elapsed") or 0
                if (elapsed_i - int(ev_elapsed)) <= 20:
                    cat = e.get("category","").lower()
                    if "substitution" in cat or "sub" in cat:
                        recent_seconds += 30
                    if "card" in cat:
                        recent_seconds += 30
                    if "injury" in cat or "injury/interruption" in cat:
                        recent_seconds += 60
            minutes = round(recent_seconds / 60) if recent_seconds > 0 else None
            if minutes:
                if minutes < 1: minutes = 1
                if minutes > 7: minutes = 7
            # fallback simple rule near half ends
            if not minutes:
                if 40 <= elapsed_i <= 45:
                    minutes = 3
                elif 80 <= elapsed_i <= 90:
                    minutes = 4
            extra = minutes
    except Exception:
        extra = None

    response = {
        "fixture": fixture.get("fixture"),
        "league": fixture.get("league"),
        "teams": fixture.get("teams"),
        "goals": fixture.get("goals"),
        "score": fixture.get("score"),
        "statistics": stats,
        "events": processed,
        "events_count": len(processed),
        "estimated_extra": extra
    }
    _cache_set(cache_key, response)
    return response
