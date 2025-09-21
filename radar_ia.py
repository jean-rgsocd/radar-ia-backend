# radar_ia.py
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Any, Dict, List
import requests, time, traceback
from datetime import datetime

app = FastAPI(title="Radar IA Backend")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# coloque sua chave aqui (ou leia de env var)
API_KEY = "7baa5e00c8ae57d0e6240f790c6840dd"

API_CFG = {
    "football": {"base": "https://v3.football.api-sports.io", "host": "v3.football.api-sports.io"},
    "nba":      {"base": "https://v2.nba.api-sports.io",      "host": "v2.nba.api-sports.io"},
    "nfl":      {"base": "https://v2.nfl.api-sports.io",      "host": "v2.nfl.api-sports.io"}
}

def get_headers(sport):
    cfg = API_CFG.get(sport, API_CFG["football"])
    return {"x-rapidapi-key": API_KEY, "x-rapidapi-host": cfg["host"]}

def safe_get_json(url, headers, params=None, timeout=20):
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print("HTTP ERROR", url, params, e)
        return None

def normalize_stats_obj(stat_obj) -> Dict[str,int]:
    """Normalize structure variations into dict of simplified keys (best-effort)."""
    mapping = {
        "Shots on Goal":"shots_on_goal","Shots off Goal":"shots_off_goal","Total Shots":"total_shots",
        "Blocked Shots":"blocked_shots","Shots insidebox":"shots_insidebox","Shots outsidebox":"shots_outsidebox",
        "Fouls":"fouls","Corner Kicks":"corners","Offsides":"offsides","Ball Possession":"possession",
        "Yellow Cards":"yellow_cards","Red Cards":"red_cards","Goalkeeper Saves":"keeper_saves",
        "Total passes":"total_passes","Passes accurate":"passes_accurate","Passes %":"passes_pct"
    }
    out = {}
    # stat_obj may be {"Shots on Goal": {"home":"5","away":"2"}, ... } OR list-of-team-stats
    if isinstance(stat_obj, dict):
        for k,v in stat_obj.items():
            key = mapping.get(k, k.lower().replace(" ", "_"))
            # v could be {"home": "5", "away": "2"} or string number
            if isinstance(v, dict):
                out[key] = {"home": v.get("home"), "away": v.get("away")}
            else:
                out[key] = v
    return out

def parse_v3_statistics_response(resp_json):
    """
    Accept different shapes. We will try to return:
    stats_by_team = { 'home': {k:v}, 'away':{k:v} }
    and optionally halftime / first/second if present.
    """
    stats_by_team = {"home":{}, "away":{}}
    # Some older v3 responses are list-of-objects per team, others are dict map stat->home/away
    if not resp_json:
        return stats_by_team, {}
    # If response wrapper:
    # Try to find "response" key with array or dict
    data = resp_json.get("response") if isinstance(resp_json, dict) and "response" in resp_json else resp_json
    # case dict of stats -> { "Shots on Goal": {"home":"5","away":"2"}, ...}
    if isinstance(data, dict):
        normalized = normalize_stats_obj(data)
        # normalized keys map to dicts with home/away
        for k, val in normalized.items():
            if isinstance(val, dict):
                stats_by_team["home"][k] = try_int(val.get("home"))
                stats_by_team["away"][k] = try_int(val.get("away"))
            else:
                # fallback: treat as total
                stats_by_team["home"][k] = try_int(val)
                stats_by_team["away"][k] = try_int(val)
        return stats_by_team, {}
    # case response is list (some responses provide list per team)
    if isinstance(data, list):
        # search if items have 'team' and 'statistics' arrays
        for item in data:
            team = item.get("team") or {}
            side = None
            # item.team.id could be used to map later, but we don't know home/away here.
            stats_arr = item.get("statistics") or item.get("statistics", [])
            if isinstance(stats_arr, list) and team:
                # build map for this team
                tmp = {}
                for s in stats_arr:
                    k = (s.get("type") or s.get("name") or "").strip()
                    v = s.get("value")
                    # if v contains " / " or " / " etc - pick left part
                    if isinstance(v, str) and "/" in v:
                        try:
                            v0 = v.split("/")[0]
                            v = int(v0)
                        except:
                            try: v = int(float(v))
                            except: v = v
                    try:
                        v = int(v)
                    except:
                        v = v
                    tmp[k] = v
                # attach to a 'team' bucket, leave mapping to caller (we'll include team.id)
                stats_by_team[team.get("id")] = tmp
        # return dict keyed by team id; caller will match ids to home/away
        return stats_by_team, {}
    return stats_by_team, {}

def try_int(v):
    try:
        if v is None: return None
        if isinstance(v, str) and "%" in v:
            return int(v.replace("%","").strip())
        return int(v)
    except:
        try:
            return int(float(v))
        except:
            return v

def events_to_period_stats(events, home_id, away_id):
    """Aggregate events into simple counts per team & period (first/second/full)."""
    agg = {
        "first": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                  "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "second": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                   "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}},
        "full": {"home":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0},
                 "away":{"shots":0,"shots_on_target":0,"corners":0,"fouls":0,"yellow":0,"red":0}}
    }
    for ev in events:
        t = ev.get("team",{}) or {}
        team_id = t.get("id")
        side = "home" if team_id == home_id else "away"
        time = ev.get("time") or {}
        elapsed = ev.get("time",{}).get("elapsed")
        # decide period (use elapsed and event.period if available)
        period = "full"
        if elapsed is not None:
            try:
                e = int(elapsed)
                period = "first" if e <= 45 else "second"
            except:
                period = "full"
        typ = (ev.get("type") or "").lower()
        detail = (ev.get("detail") or "").lower()
        # classify
        if "shot" in typ or "goal" in typ or "shot" in detail:
            # shot; further check 'on target' in detail
            agg[period][side]["shots"] += 1
            agg["full"][side]["shots"] += 1
            if "on target" in detail or "goal" in typ or "goal" in detail:
                agg[period][side]["shots_on_target"] += 1
                agg["full"][side]["shots_on_target"] += 1
        if "corner" in typ or "corner" in detail:
            agg[period][side]["corners"] += 1
            agg["full"][side]["corners"] += 1
        if "card" in typ or "yellow" in detail:
            if "red" in detail:
                agg[period][side]["red"] += 1
                agg["full"][side]["red"] += 1
            else:
                agg[period][side]["yellow"] += 1
                agg["full"][side]["yellow"] += 1
        if "foul" in typ or "foul" in detail:
            agg[period][side]["fouls"] += 1
            agg["full"][side]["fouls"] += 1
    return agg

@app.get("/stats-aovivo/{game_id}")
def stats_aovivo(game_id: int, sport: str = Query("football", enum=["football","nba","nfl"])):
    """
    Return aggregated richer stats for Radar.
    Uses v3 endpoints for football (fixtures/statistics, fixtures/events, fixtures/lineups, fixtures/players)
    and v2 endpoints for NBA/NFL where available.
    """
    try:
        cfg = API_CFG.get(sport, API_CFG["football"])
        headers = get_headers(sport)
        base = cfg["base"]

        if sport == "football":
            # get fixture detail
            fixture_raw = safe_get_json(f"{base}/fixtures", headers, params={"id": game_id})
            if not fixture_raw:
                raise HTTPException(status_code=404, detail="Fixture not found")
            # some responses are wrapper {response:[...]}
            data_list = fixture_raw.get("response") if isinstance(fixture_raw, dict) and "response" in fixture_raw else fixture_raw
            fixture = data_list[0] if isinstance(data_list, list) and data_list else (data_list if isinstance(data_list, dict) else {})
            # statistics (try halftime)
            stats_resp = safe_get_json(f"{base}/fixtures/statistics", headers, params={"fixture": game_id, "half":"true"})
            stats_map, _ = parse_v3_statistics_response(stats_resp or {})
            # events
            events_resp = safe_get_json(f"{base}/fixtures/events", headers, params={"fixture": game_id})
            events = events_resp.get("response") if events_resp and isinstance(events_resp, dict) and "response" in events_resp else (events_resp if events_resp else [])
            # lineups and players
            lineups_resp = safe_get_json(f"{base}/fixtures/lineups", headers, params={"fixture": game_id})
            players_resp = safe_get_json(f"{base}/fixtures/players", headers, params={"fixture": game_id})
            lineups = lineups_resp.get("response") if lineups_resp and isinstance(lineups_resp, dict) and "response" in lineups_resp else (lineups_resp or [])
            players = players_resp.get("response") if players_resp and isinstance(players_resp, dict) and "response" in players_resp else (players_resp or [])
            # build standardized statistics: if stats_map keyed by team id, map to home/away
            teams = fixture.get("teams", {})
            home_id = teams.get("home",{}).get("id")
            away_id = teams.get("away",{}).get("id")
            full_stats = {"home":{}, "away":{}}
            # stats_map might be dict of statname-> {home:.. away:..} or keyed by team id
            if isinstance(stats_map, dict):
                # handle both cases
                # if stats_map has keys 'home'/'away' as above:
                if 'home' in stats_map and 'away' in stats_map:
                    full_stats = stats_map
                else:
                    # keyed by team id
                    hid = stats_map.get(home_id, {})
                    aid = stats_map.get(away_id, {})
                    # combine common keys
                    keys = set(list(hid.keys()) + list(aid.keys()))
                    for k in keys:
                        full_stats["home"][k] = hid.get(k) if hid else None
                        full_stats["away"][k] = aid.get(k) if aid else None
            # fallback: compute from events
            period_agg = events_to_period_stats(events, home_id, away_id)
            # if API didn't provide certain stats, we can fill from aggregated events
            # e.g. if total_shots missing, use period_agg['full'][side]['shots']
            for side in ("home","away"):
                if not full_stats.get(side):
                    full_stats[side] = {}
                if full_stats[side].get("total_shots") in (None,0):
                    # map to integer
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
            # sort events descending by time elapsed
            def ev_key(e):
                try:
                    return int(e.get("time",{}).get("elapsed") or 0)
                except:
                    return 0
            events_sorted = sorted(events, key=lambda x: ev_key(x), reverse=True)
            # produce result
            return {
                "fixture": fixture,
                "teams": teams,
                "score": fixture.get("goals") or fixture.get("score") or {},
                "status": fixture.get("status", {}),
                "statistics": {
                    "full": full_stats,
                    "firstHalf_derived": period_agg.get("first"),
                    "secondHalf_derived": period_agg.get("second")
                },
                "events": events_sorted,
                "lineups": lineups,
                "players": players
            }

        else:
            # NBA / NFL (v2/v1): best-effort using games and players/statistics endpoints
            # games endpoint
            base = cfg["base"]
            game_resp = safe_get_json(f"{base}/games", get_headers(sport), params={"id": game_id})
            game_data = game_resp.get("response") if game_resp and isinstance(game_resp, dict) and "response" in game_resp else (game_resp or [])
            game = game_data[0] if isinstance(game_data, list) and game_data else (game_data if isinstance(game_data, dict) else {})
            # players stats
            players_stat_resp = safe_get_json(f"{base}/players/statistics", get_headers(sport), params={"game": game_id})
            players_stats = players_stat_resp.get("response") if players_stat_resp and isinstance(players_stat_resp, dict) and "response" in players_stat_resp else (players_stat_resp or [])
            # build simple normalized structure
            return {"fixture": game, "teams": game.get("teams", {}), "score": game.get("scores", {}), "status": game.get("status", {}), "players_stats": players_stats}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
