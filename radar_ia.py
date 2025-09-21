# radar_ia.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, os, traceback, time
from typing import List, Dict, Any

app = FastAPI(title="Radar IA")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_KEY = os.environ.get("API_SPORTS_KEY", "7baa5e00c8ae57d0e6240f790c6840dd")
API_CFG = {
    "football": {"base":"https://v3.football.api-sports.io", "host":"v3.football.api-sports.io"},
    "nba":      {"base":"https://v2.nba.api-sports.io",      "host":"v2.nba.api-sports.io"},
    "nfl":      {"base":"https://v2.nfl.api-sports.io",      "host":"v2.nfl.api-sports.io"}
}

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

def headers_for(sport):
    cfg = API_CFG.get(sport, API_CFG["football"])
    return {"x-rapidapi-key": API_KEY, "x-rapidapi-host": cfg["host"]}

def safe_get(url, headers, params=None, timeout=20):
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("safe_get error", url, params, e)
        return None

def _compute_sort_key(ev):
    try:
        elapsed = int(ev.get("time", {}).get("elapsed") or 0)
    except:
        elapsed = 0
    try:
        second = int(ev.get("time", {}).get("second") or 0)
    except:
        second = 0
    try:
        extra = int(ev.get("time", {}).get("extra") or 0)
    except:
        extra = 0
    return (elapsed + extra)*60 + second

def _format_display_time(ev):
    t = ev.get("time", {}) or {}
    elapsed = t.get("elapsed")
    second = t.get("second")
    extra = t.get("extra")
    if elapsed is None:
        return "-"
    sec_part = f'{int(second):02d}"' if second is not None else ""
    if extra:
        return f"{elapsed}+{extra}'{sec_part}"
    return f"{elapsed}'{sec_part}"

def classify_event(ev):
    t = (ev.get("type") or "").lower()
    d = (ev.get("detail") or "").lower()
    if "goal" in t or "goal" in d: return "Goal"
    if "card" in t or "card" in d:
        if "yellow" in d: return "Yellow Card"
        if "red" in d: return "Red Card"
        return "Card"
    if "substitution" in t or "substitution" in d or "sub" in d: return "Substitution"
    if "corner" in t or "corner" in d: return "Corner"
    if "foul" in t or "foul" in d: return "Foul"
    if "shot" in t or "shot" in d or "on target" in d: return "Shot"
    return ev.get("type") or ev.get("detail") or "Other"

@app.get("/ligas")
def ligas():
    ck = "radar_ligas_live"
    c = _cache_get(ck)
    if c is not None: return c
    cfg = API_CFG["football"]
    resp = safe_get(f"{cfg['base']}/fixtures", headers_for("football"), params={"live":"all"})
    if not resp: return []
    data = resp.get("response") if isinstance(resp, dict) and "response" in resp else resp
    leagues = {}
    for f in data:
        l = f.get("league") or {}
        leagues[l.get("id")] = {"id": l.get("id"), "name": l.get("name"), "country": l.get("country")}
    out = list(leagues.values())
    _cache_set(ck, out)
    return out

@app.get("/jogos-aovivo")
def jogos_aovivo(league: int = Query(None)):
    ck = f"radar_jogos_live_{league or 'all'}"
    c = _cache_get(ck)
    if c is not None: return c
    cfg = API_CFG["football"]
    params = {"live":"all"}
    if league: params["league"] = league
    resp = safe_get(f"{cfg['base']}/fixtures", headers_for("football"), params=params)
    if not resp: return []
    data = resp.get("response") if isinstance(resp, dict) and "response" in resp else resp
    out = []
    for f in data:
        out.append({
            "game_id": f.get("fixture",{}).get("id"),
            "title": f"{f.get('teams',{}).get('home',{}).get('name')} vs {f.get('teams',{}).get('away',{}).get('name')} ({f.get('league',{}).get('name')})",
            "league": f.get("league"),
            "teams": f.get("teams"),
            "fixture": f.get("fixture"),
            "status": f.get("fixture",{}).get("status")
        })
    _cache_set(ck, out)
    return out

@app.get("/stats-aovivo/{game_id}")
def stats_aovivo(game_id: int, sport: str = Query("football", enum=["football","nba","nfl"])):
    ck = f"radar_stats_{sport}_{game_id}"
    cached = _cache_get(ck)
    if cached is not None: return cached
    try:
        cfg = API_CFG[sport]; base = cfg["base"]; headers = headers_for(sport)
        if sport == "football":
            fixture_resp = safe_get(f"{base}/fixtures", headers, params={"id": game_id})
            if not fixture_resp: raise HTTPException(status_code=404, detail="Fixture not found")
            fixture_data = fixture_resp.get("response") if isinstance(fixture_resp, dict) and "response" in fixture_resp else fixture_resp
            fixture = fixture_data[0] if isinstance(fixture_data, list) and fixture_data else (fixture_data if isinstance(fixture_data, dict) else {})
            stats_resp = safe_get(f"{base}/fixtures/statistics", headers, params={"fixture": game_id, "half":"true"})
            stats_wrapper = stats_resp or {}
            full_stats = {"home":{}, "away":{}}
            try:
                stats_list = stats_wrapper.get("response") if isinstance(stats_wrapper, dict) and "response" in stats_wrapper else stats_wrapper
                if isinstance(stats_list, list) and len(stats_list)>0:
                    for team_stats in stats_list:
                        team = team_stats.get("team") or {}
                        tid = team.get("id")
                        home_id = fixture.get("teams",{}).get("home",{}).get("id")
                        away_id = fixture.get("teams",{}).get("away",{}).get("id")
                        side = "home" if tid==home_id else ("away" if tid==away_id else None)
                        stats_entries = team_stats.get("statistics") or []
                        tmp = {}
                        for s in stats_entries:
                            k = (s.get("type") or s.get("name") or "").strip()
                            v = s.get("value")
                            try:
                                if isinstance(v, str) and "/" in v:
                                    v = int(v.split("/")[0])
                                else:
                                    v = int(v)
                            except:
                                try: v = int(float(v))
                                except: v = v
                            tmp[k] = v
                        if side: full_stats[side].update(tmp)
                        else:
                            if not full_stats["home"]: full_stats["home"].update(tmp)
                            else: full_stats["away"].update(tmp)
                else:
                    if isinstance(stats_list, dict):
                        for k,v in stats_list.items():
                            if isinstance(v, dict):
                                full_stats["home"][k] = try_int(v.get("home"))
                                full_stats["away"][k] = try_int(v.get("away"))
            except Exception as e:
                print("parse stats error", e)
            events_resp = safe_get(f"{base}/fixtures/events", headers, params={"fixture": game_id})
            events = events_resp.get("response") if events_resp and isinstance(events_resp, dict) and "response" in events_resp else (events_resp or [])
            processed = []
            for ev in events:
                processed.append({
                    "display_time": _format_display_time(ev),
                    "category": classify_event(ev),
                    "type": ev.get("type"),
                    "detail": ev.get("detail"),
                    "player": ev.get("player",{}).get("name") if ev.get("player") else None,
                    "team": ev.get("team",{}).get("name") if ev.get("team") else None,
                    "raw": ev,
                    "_sort": _compute_sort_key(ev)
                })
            processed.sort(key=lambda x: x["_sort"], reverse=True)
            home_id = fixture.get("teams",{}).get("home",{}).get("id")
            away_id = fixture.get("teams",{}).get("away",{}).get("id")
            period_agg = events_to_period_stats(events, home_id, away_id)
            for side in ("home","away"):
                if not full_stats.get(side): full_stats[side] = {}
                if full_stats[side].get("total_shots") in (None,0):
                    full_stats[side]["total_shots"] = period_agg["full"][side].get("shots",0)
                if full_stats[side].get("shots_on_goal") in (None,0):
                    full_stats[side]["shots_on_goal"] = period_agg["full"][side].get("shots_on_target",0)
                if full_stats[side].get("corners") in (None,0):
                    full_stats[side]["corners"] = period_agg["full"][side].get("corners",0)
                if full_stats[side].get("fouls") in (None,0):
                    full_stats[side]["fouls"] = period_agg["full"][side].get("fouls",0)
                if full_stats[side].get("yellow_cards") in (None,0):
                    full_stats[side]["yellow_cards"] = period_agg["full"][side].get("yellow",0)
                if full_stats[side].get("red_cards") in (None,0):
                    full_stats[side]["red_cards"] = period_agg["full"][side].get("red",0)
            lineups_resp = safe_get(f"{base}/fixtures/lineups", headers, params={"fixture": game_id})
            lineups = lineups_resp.get("response") if lineups_resp and isinstance(lineups_resp, dict) and "response" in lineups_resp else (lineups_resp or [])
            players_resp = safe_get(f"{base}/fixtures/players", headers, params={"fixture": game_id})
            players = players_resp.get("response") if players_resp and isinstance(players_resp, dict) and "response" in players_resp else (players_resp or [])
            estimated_extra = None
            try:
                elapsed = fixture.get("fixture",{}).get("status",{}).get("elapsed") or fixture.get("fixture",{}).get("status",{}).get("elapsed")
                if elapsed is not None:
                    # heurística: contar subs/cards/injuries nos últimos 20 minutos
                    recent_count = 0
                    for p in processed:
                        rv = p.get("raw",{})
                        et = rv.get("time",{}).get("elapsed") or 0
                        if (int(elapsed) - int(et)) <= 20:
                            cat = p.get("category","").lower()
                            if "substitution" in cat or "sub" in cat: recent_count += 1
                            if "card" in cat: recent_count += 1
                            if "injury" in cat or "injury/interruption" in cat: recent_count += 2
                    minutes = round(recent_count * 0.8) if recent_count>0 else None
                    if not minutes:
                        if 40 <= int(elapsed) <= 45: minutes = 3
                        elif 80 <= int(elapsed) <= 90: minutes = 4
                    if minutes:
                        estimated_extra = max(1, min(7, minutes))
            except:
                estimated_extra = None
            result = {
                "fixture": fixture,
                "teams": fixture.get("teams", {}),
                "score": fixture.get("goals") or fixture.get("score") or {},
                "status": fixture.get("status") or fixture.get("fixture",{}).get("status",{}),
                "statistics": {"full": full_stats, "firstHalf_derived": period_agg.get("first"), "secondHalf_derived": period_agg.get("second")},
                "events": processed,
                "lineups": lineups,
                "players": players,
                "estimated_extra": estimated_extra
            }
            _cache_set(ck, result)
            return result
        else:
            # NBA/NFL fallback
            game_resp = safe_get(f"{base}/games", headers, params={"id": game_id})
            game_data = game_resp.get("response") if game_resp and isinstance(game_resp, dict) and "response" in game_resp else (game_resp or [])
            game = game_data[0] if isinstance(game_data, list) and game_data else (game_data if isinstance(game_data, dict) else {})
            players_resp = safe_get(f"{base}/players/statistics", headers, params={"game": game_id})
            players_stats = players_resp.get("response") if players_resp and isinstance(players_resp, dict) and "response" in players_resp else (players_resp or [])
            result = {"fixture": game, "teams": game.get("teams", {}), "score": game.get("scores") or game.get("score") or {}, "status": game.get("status", {}), "players_stats": players_stats}
            _cache_set(ck, result)
            return result
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

def try_int(v):
    try:
        if v is None: return None
        if isinstance(v, str) and "%" in v:
            return int(v.replace("%","").strip())
        return int(v)
    except:
        try: return int(float(v))
        except: return v

def events_to_period_stats(events, home_id, away_id):
    agg = {
        "first": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},"away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "second": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},"away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "full": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},"away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}}
    }
    for ev in events:
        team = ev.get("team") or {}
        team_id = team.get("id")
        side = "home" if team_id == home_id else "away"
        elapsed = ev.get("time",{}).get("elapsed")
        period = "full"
        try:
            if elapsed is not None:
                e = int(elapsed)
                period = "first" if e <= 45 else "second"
        except:
            period = "full"
        typ = (ev.get("type") or "").lower()
        detail = (ev.get("detail") or "").lower()
        if "shot" in typ or "shot" in detail or "goal" in typ or "goal" in detail:
            agg[period][side]["shots"] += 1; agg["full"][side]["shots"] += 1
            if "on target" in detail or "goal" in typ or "goal" in detail:
                agg[period][side]["shots_on_target"] += 1; agg["full"][side]["shots_on_target"] += 1
        if "corner" in typ or "corner" in detail:
            agg[period][side]["corners"] += 1; agg["full"][side]["corners"] += 1
        if "foul" in typ or "foul" in detail:
            agg[period][side]["fouls"] += 1; agg["full"][side]["fouls"] += 1
        if "card" in typ or "yellow" in detail or "red" in detail:
            if "red" in detail:
                agg[period][side]["red"] += 1; agg["full"][side]["red"] += 1
            else:
                agg[period][side]["yellow"] += 1; agg["full"][side]["yellow"] += 1
    return agg
