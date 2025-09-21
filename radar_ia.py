# radar_ia.py
# Radar IA - eventos ordenados decrescente + minuto/segundo + categorização
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
import requests, traceback
from datetime import datetime

app = FastAPI(title="Radar IA")

origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

API_SPORTS_KEY = "7baa5e00c8ae57d0e6240f790c6840dd"
API_HOST = "v3.football.api-sports.io"
API_URL = f"https://{API_HOST}"
HEADERS = {
    "x-rapidapi-key": API_SPORTS_KEY,
    "x-rapidapi-host": API_HOST
}

def _get(url: str, params: dict = None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("response", [])
    except requests.RequestException as e:
        print(f"Erro Radar GET {url} params={params}: {e}")
        print(traceback.format_exc())
        return []

def _compute_sort_key(event: dict) -> int:
    """
    Gera um número (segundos) para ordenar eventos.
    Usa time.elapsed (minutos), time.second (segundos) e time.extra (minutos adicionais)
    sort_key = (elapsed + extra) * 60 + second
    """
    t = event.get("time", {}) or {}
    try:
        elapsed = int(t.get("elapsed") or 0)
    except Exception:
        elapsed = 0
    try:
        second = int(t.get("second")) if t.get("second") is not None else 0
    except Exception:
        second = 0
    try:
        extra = int(t.get("extra") or 0)
    except Exception:
        extra = 0
    return (elapsed + extra) * 60 + second

def _format_display_time(event: dict) -> str:
    t = event.get("time", {}) or {}
    elapsed = t.get("elapsed")
    second = t.get("second")
    extra = t.get("extra")
    # Preferência: se existir second -> mostrar minuto'second" (ex: 80'23")
    try:
        if elapsed is None:
            return ""
        elapsed_i = int(elapsed)
    except Exception:
        return str(elapsed)
    sec_str = ""
    try:
        if second is not None:
            sec = int(second)
            sec_str = f"{sec:02d}\""
        else:
            sec = None
    except Exception:
        sec = None
    if extra:
        # ex: 90+3' ou 90+3'23"
        try:
            extra_i = int(extra)
        except Exception:
            extra_i = 0
        if sec is not None:
            return f"{elapsed_i}+{extra_i}'{sec_str}"
        return f"{elapsed_i}+{extra_i}'"
    else:
        if sec is not None:
            return f"{elapsed_i}'{sec_str}"
        return f"{elapsed_i}'"

def _classify_event(event: dict) -> str:
    t = (event.get("type") or "").lower()
    d = (event.get("detail") or "").lower()
    # Goals
    if "goal" in t or "goal" in d:
        return "Goal"
    # Cards
    if "card" in t or "card" in d:
        if "yellow" in d or "yellow" in t:
            return "Yellow Card"
        if "red" in d or "red" in t:
            return "Red Card"
        return "Card"
    # Shots
    if "shot" in t or "shoot" in d or "shot" in d:
        # on target / on goal
        if "on goal" in d or "on target" in d or "shot on target" in t:
            return "Shot on Target"
        return "Shot"
    # Foul
    if "foul" in t or "foul" in d:
        return "Foul"
    # Corner
    if "corner" in t or "corner" in d or "corner kick" in d:
        return "Corner"
    # Throw-in / lateral
    if "throw" in t or "throw" in d or "lateral" in d or "throw-in" in d:
        return "Throw-in"
    # Substitution
    if "substitution" in t or "substitution" in d or "sub" in t or "sub" in d:
        return "Substitution"
    # Attack / Dangerous Attack
    if "attack" in t or "attack" in d:
        if "dangerous" in d or "dangerous" in t:
            return "Dangerous Attack"
        return "Attack"
    # Penalty
    if "penalty" in t or "penalty" in d:
        return "Penalty"
    # Default fallback
    return (event.get("type") or event.get("detail") or "Other")

# listar ligas (a partir de fixtures ao vivo)
@app.get("/ligas")
def list_leagues(country: str = Query(None, description="Filtrar por país (opcional)")):
    params = {"live": "all"}
    data = _get(f"{API_URL}/fixtures", params)
    leagues = {}
    for f in data:
        league = f.get("league", {})
        if country and league.get("country") != country:
            continue
        leagues[league.get("id")] = {"id": league.get("id"), "name": league.get("name"), "country": league.get("country")}
    return list(leagues.values())

# jogos ao vivo (opcional filtro por liga)
@app.get("/jogos-aovivo")
def live_games(league: int = Query(None)):
    params = {"live": "all"}
    if league:
        params["league"] = league
    data = _get(f"{API_URL}/fixtures", params)
    results = []
    for f in data:
        results.append({
            "game_id": f["fixture"]["id"],
            "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})",
            "league": f["league"],
            "teams": f["teams"],
            "fixture": f["fixture"],
            "status": f["fixture"].get("status")
        })
    return sorted(results, key=lambda x: x["title"])

# estatísticas e dados completos do fixture (por game id)
@app.get("/stats-aovivo/{game_id}")
def live_stats(game_id: int):
    # buscar fixture completo
    fixture_data = _get(f"{API_URL}/fixtures", {"id": game_id})
    if not fixture_data:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    fixture = fixture_data[0]

    # eventos (todo o histórico disponível)
    events_raw = _get(f"{API_URL}/fixtures/events", {"fixture": game_id})
    processed_events = []
    for ev in events_raw:
        sort_key = _compute_sort_key(ev)
        display_time = _format_display_time(ev)
        category = _classify_event(ev)
        # manter raw copy para referência
        processed_events.append({
            **ev,
            "_sort_key": sort_key,
            "display_time": display_time,
            "category": category,
            "raw": ev
        })

    # ordenar do mais recente para o mais antigo
    events_desc = sorted(processed_events, key=lambda x: x["_sort_key"], reverse=True)

    # estatísticas por fixtures (se disponível)
    statistics = _get(f"{API_URL}/fixtures/statistics", {"fixture": game_id})
    # opcional: players / lineups
    players = _get(f"{API_URL}/players", {"fixture": game_id})

    # heurística simples de estimativa de acréscimos (pode ser substituída por lógica mais avançada)
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
    estimated_extra = None
    if elapsed is not None:
        try:
            elapsed_i = int(elapsed)
            if elapsed_i <= 45 and elapsed_i >= 35:
                estimated_extra = {"minimal": 1, "expected": 3, "maximal": 6}
            elif elapsed_i > 45 and elapsed_i >= 80:
                estimated_extra = {"minimal": 2, "expected": 4, "maximal": 7}
        except Exception:
            estimated_extra = None

    response = {
        "fixture": fixture.get("fixture"),
        "league": fixture.get("league"),
        "teams": fixture.get("teams"),
        "goals": fixture.get("goals"),
        "score": fixture.get("score"),
        "statistics": statistics,
        "players": players,
        "events": events_desc,
        "events_count": len(events_desc),
        "estimated_extra": estimated_extra
    }
    return response
