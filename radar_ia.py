# radar_ia.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, os, traceback, time

app = FastAPI(title="Radar IA")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

API_KEY = os.environ.get("API_SPORTS_KEY", "7baa5e00c8ae57d0e6240f790c6840dd")
API_CFG = {
    "football": {"base": "https://v3.football.api-sports.io", "host": "v3.football.api-sports.io"},
    "nba":      {"base": "https://v2.nba.api-sports.io",      "host": "v2.nba.api-sports.io"},
    "nfl":      {"base": "https://v2.nfl.api-sports.io",      "host": "v2.nfl.api-sports.io"}
}

CACHE_TTL = 8
_cache = {}

# ---------------- UTILS ----------------
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
    try: elapsed = int(ev.get("time", {}).get("elapsed") or 0)
    except: elapsed = 0
    try: second = int(ev.get("time", {}).get("second") or 0)
    except: second = 0
    try: extra = int(ev.get("time", {}).get("extra") or 0)
    except: extra = 0
    return (elapsed + extra) * 60 + second

def _format_display_time(ev):
    t = ev.get("time", {}) or {}
    elapsed = t.get("elapsed")
    second = t.get("second")
    extra = t.get("extra")
    if elapsed is None: return "-"
    sec_part = f'{int(second):02d}"' if second is not None else ""
    if extra: return f"{elapsed}+{extra}'{sec_part}"
    return f"{elapsed}'{sec_part}"

def classify_event(ev):
    t = (ev.get("type") or "").lower()
    d = (ev.get("detail") or "").lower()

    if "goal" in t or "goal" in d: 
        return "Goal"
    if "yellow" in d: 
        return "Yellow Card"
    if "red" in d: 
        return "Red Card"
    if "card" in t: 
        return "Card"
    if "corner" in t or "corner" in d: 
        return "Corner"
    if "foul" in t or "foul" in d: 
        return "Foul"
    if "substitution" in t or "sub" in d: 
        return "Substitution"
    if "shot" in t or "shot" in d: 
        return "Shot"
    # 👇 garantir que faltas e escanteios apareçam
    if "free kick" in d: 
        return "Foul"
    if "penalty" in d: 
        return "Shot (Penalty)"
    return ev.get("type") or ev.get("detail") or "Other"
    

# ---------------- PERIOD AGGREGATION ----------------
def events_to_period_stats(events, home_id, away_id, match_status=None):
    agg = {
        "first": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                  "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "second": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                   "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "full": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                 "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}}
    }

    for ev in events:
        team = ev.get("team") or {}
        team_id = team.get("id")
        side = "home" if team_id == home_id else "away"

        elapsed = ev.get("time", {}).get("elapsed")
        period = "full"
        try:
            if elapsed is not None:
                e = int(elapsed)
                if e <= 45:
                    period = "first"
                elif e >= 46:
                    # só entra no 2º tempo se status realmente indicar 2H
                    if match_status and match_status.get("short") == "2H":
                        period = "second"
        except:
            period = "full" 

        typ = (ev.get("type") or "").lower()
        detail = (ev.get("detail") or "").lower()

        # Shots
        if "shot" in typ or "shot" in detail or "goal" in typ or "goal" in detail:
            agg[period][side]["shots"] += 1
            agg["full"][side]["shots"] += 1
            if "on target" in detail or "goal" in typ or "goal" in detail:
                agg[period][side]["shots_on_target"] += 1
                agg["full"][side]["shots_on_target"] += 1

        # Corners
        if "corner" in typ or "corner" in detail:
            agg[period][side]["corners"] += 1
            agg["full"][side]["corners"] += 1

        # Fouls
        if "foul" in typ or "foul" in detail:
            agg[period][side]["fouls"] += 1
            agg["full"][side]["fouls"] += 1

        # Cards
        if "card" in typ or "yellow" in detail or "red" in detail:
            if "red" in detail:
                agg[period][side]["red"] += 1
                agg["full"][side]["red"] += 1
            elif "yellow" in detail:
                agg[period][side]["yellow"] += 1
                agg["full"][side]["yellow"] += 1

    return agg

# ---------------- ENDPOINTS ----------------
@app.get("/ligas")
def ligas():
    ck = "radar_ligas_live"
    c = _cache_get(ck)
    if c is not None: return c
    cfg = API_CFG["football"]
    resp = safe_get(f"{cfg['base']}/fixtures", headers_for("football"), params={"live":"all"})
    if not resp: return []
    data = resp.get("response") if isinstance(resp, dict) else resp
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
    data = resp.get("response") if isinstance(resp, dict) else resp
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
            fixture_data = fixture_resp.get("response") if isinstance(fixture_resp, dict) else fixture_resp
            fixture = fixture_data[0] if isinstance(fixture_data, list) else fixture_data

            # Estatísticas
            stats_resp = safe_get(f"{base}/fixtures/statistics", headers, params={"fixture": game_id})
            stats_wrapper = stats_resp or {}
            full_stats = {"home":{}, "away":{}}
            try:
                stats_list = stats_wrapper.get("response") if isinstance(stats_wrapper, dict) else stats_wrapper
                if isinstance(stats_list, list):
                    for team_stats in stats_list:
                        team = team_stats.get("team") or {}
                        tid = team.get("id")
                        home_id = fixture.get("teams",{}).get("home",{}).get("id")
                        away_id = fixture.get("teams",{}).get("away",{}).get("id")
                        side = "home" if tid==home_id else "away"
                        tmp = {}
                        for s in team_stats.get("statistics") or []:
                            k = (s.get("type") or "").strip()
                            v = s.get("value")
                            try:
                                if isinstance(v, str) and "%" in v: v = int(v.replace("%",""))
                                elif isinstance(v, str) and "/" in v: v = int(v.split("/")[0])
                                else: v = int(v)
                            except: pass
                            tmp[k] = v
                        full_stats[side].update(tmp)
            except: pass

            # Eventos
            events_resp = safe_get(f"{base}/fixtures/events", headers, params={"fixture": game_id})
            events = events_resp.get("response") if isinstance(events_resp, dict) else events_resp
            processed = []
            for ev in events:
                processed.append({
                    "display_time": _format_display_time(ev),
                    "category": classify_event(ev),
                    "type": ev.get("type"),
                    "detail": ev.get("detail"),
                    "player": ev.get("player",{}).get("name"),
                    "team": ev.get("team",{}).get("name"),
                    "raw": ev,
                    "_sort": _compute_sort_key(ev)
                })
            processed.sort(key=lambda x: x["_sort"], reverse=True)

            # Lineups e jogadores
            lineups_resp = safe_get(f"{base}/fixtures/lineups", headers, params={"fixture": game_id})
            lineups = lineups_resp.get("response") if isinstance(lineups_resp, dict) else lineups_resp
            players_resp = safe_get(f"{base}/fixtures/players", headers, params={"fixture": game_id})
            players = players_resp.get("response") if isinstance(players_resp, dict) else players_resp

            # Estatísticas derivadas (1T / 2T)
            home_id = fixture.get("teams", {}).get("home", {}).get("id")
            away_id = fixture.get("teams", {}).get("away", {}).get("id")
            period_agg = events_to_period_stats(events, home_id, away_id, fixture.get("fixture",{}).get("status"))

            # Estimativa de acréscimos
            estimated_extra = None
            try:
                elapsed = fixture.get("fixture",{}).get("status",{}).get("elapsed")
                if elapsed:
                    elapsed = int(elapsed)
                    if (35 <= elapsed <= 45) or (80 <= elapsed <= 90):
                        subs_cards = sum(1 for ev in processed if "substitution" in ev["category"].lower() or "card" in ev["category"].lower())
                        if subs_cards > 0: estimated_extra = min(7, max(1, subs_cards))
            except: pass

            result = {
                "fixture": fixture,
                "teams": fixture.get("teams", {}),
                "score": fixture.get("goals") or {},
                "status": fixture.get("fixture",{}).get("status"),
                "statistics": {
                    "full": full_stats,
                    "firstHalf_derived": period_agg.get("first"),
                    "secondHalf_derived": period_agg.get("second")
                },
                "events": processed,
                "lineups": lineups,
                "players": players,
                "estimated_extra": estimated_extra
            }
            _cache_set(ck, result)
            return result
        else:
            return {"message": "Radar detalhado apenas para futebol."}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



