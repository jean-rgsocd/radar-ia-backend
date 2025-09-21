# radar_ia.py
# Backend para Radar IA (jogos ao vivo, estatísticas por período, seleção por liga -> jogo)
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

def get(url: str, params: dict = None):
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("response", [])
    except requests.RequestException as e:
        print(f"Erro Radar GET {url}: {e}")
        print(traceback.format_exc())
        return []

# listar ligas (a partir de fixtures ao vivo + próximos dias para popular dropdown)
@app.get("/ligas")
def list_leagues(country: str = Query(None, description="Filtrar por país (opcional)")):
    params = {"live": "all"}
    data = get(f"{API_URL}/fixtures", params)
    leagues = {}
    for f in data:
        league = f.get("league", {})
        if country and league.get("country") != country:
            continue
        leagues[league["id"]] = {"id": league["id"], "name": league.get("name"), "country": league.get("country")}
    return list(leagues.values())

# jogos ao vivo (opcional filtro por liga)
@app.get("/jogos-aovivo")
def live_games(league: int = Query(None)):
    params = {"live": "all"}
    if league:
        params["league"] = league
    data = get(f"{API_URL}/fixtures", params)
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
    params = {"id": game_id}
    data = get(f"{API_URL}/fixtures", params)
    if not data:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    fixture = data[0]

    # estrutura: separar estatísticas por períodos, calcular estimativa de acréscimos
    # Estatísticas normalmente vêm em endpoints /statistics - vamos tentar buscar estatísticas também
    stats = get(f"{API_URL}/players", {"fixture": game_id})  # fallback; alguns planos/versões podem variar
    # também tentar /statistics
    statistics = get(f"{API_URL}/fixtures/statistics", {"fixture": game_id})
    events = get(f"{API_URL}/fixtures/events", {"fixture": game_id})
    # calcular acréscimos estimados (heurística simples):
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
    estimated_extra = None
    if elapsed is not None:
        if elapsed <= 45:
            # se está no final do 1º tempo, estimativa 2-5
            if elapsed >= 35:
                estimated_extra = {"minimal": 2, "expected": 4, "maximal": 6}
        else:
            # final do 2º tempo, estimativa 3-6
            if elapsed >= 80:
                estimated_extra = {"minimal": 3, "expected": 5, "maximal": 7}

    response = {
        "fixture": fixture.get("fixture"),
        "league": fixture.get("league"),
        "teams": fixture.get("teams"),
        "goals": fixture.get("goals"),
        "score": fixture.get("score"),
        "statistics": statistics,  # por período se disponível
        "events": events,
        "estimated_extra": estimated_extra
    }
    return response
