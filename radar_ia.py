# Filename: radar_ia.py
# Versão 6.0 - Completo e Corrigido

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from datetime import datetime, timedelta

app = FastAPI(title="Radar IA - V6.0 Corrigido")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Configuração da API-Sports ---
API_SPORTS_KEY = "7baa5e00c8ae61790c6840dd"
API_SPORTS_URL = "https://api-football-v1.p.rapidapi.com/v3"
HEADERS = {"x-rapidapi-key": API_SPORTS_KEY}
cache: Dict[str, Dict[str, Any]] = {}

def get_current_season() -> str:
    """Retorna o ano atual como a temporada."""
    return str(datetime.now().year)

# --- Endpoint de Jogos ao vivo ---
@app.get("/jogos-aovivo")
def get_live_games():
    """Busca e armazena em cache todos os jogos de futebol que estão ao vivo."""
    cache_key = "live_games"
    if cache_key in cache and datetime.now() < cache[cache_key]['expiry']:
        return cache[cache_key]['data']
    
    # GARANTIA: Adicionando 'season' que pode ser um requisito implícito em alguns planos
    params = {"live": "all", "season": get_current_season()}
    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("response", [])
        
        live_games = sorted([
            {"game_id": f["fixture"]["id"], "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})"}
            for f in data if f.get("fixture") and f.get("teams") and f.get("league")
        ], key=lambda x: x["title"])
        
        cache[cache_key] = {"data": live_games, "expiry": datetime.now() + timedelta(minutes=2)}
        return live_games
    except requests.RequestException as e:
        print(f"ERRO CRÍTICO no Radar IA ao buscar jogos ao vivo: {e}")
        raise HTTPException(status_code=503, detail="A API de esportes não respondeu para jogos ao vivo.")

# --- Lógica de Estimativa de Acréscimos ---
def estimate_stoppage_time(events: List[Dict[str, Any]], period: str) -> int:
    """Heurística para estimar o tempo de acréscimo com base nos eventos do jogo."""
    stoppage_seconds = 0
    start_minute, end_minute = (0, 45) if period == "1H" else (46, 90)
    
    period_events = [e for e in events if start_minute < e.get("time", {}).get("elapsed", 0) <= end_minute]
    
    stoppage_seconds += len([e for e in period_events if e.get("type") == "Goal"]) * 45
    stoppage_seconds += len([e for e in period_events if e.get("type") == "subst"]) * 30
    stoppage_seconds += len([e for e in period_events if e.get("type") == "Card"]) * 15
    
    if len(period_events) > 7:
        stoppage_seconds += 60

    return round(stoppage_seconds / 60)

# --- Endpoint de Estatísticas ao vivo ---
@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    """Busca estatísticas detalhadas de um jogo ao vivo específico."""
    params = {"id": game_id}
    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("response", [])
        if not data:
            raise HTTPException(status_code=404, detail="Jogo não encontrado.")
        
        game_data = data[0]
        fixture = game_data.get("fixture", {})
        teams = game_data.get("teams", {})
        goals = game_data.get("goals", {})
        stats_list = game_data.get("statistics", [])
        events = game_data.get("events", [])
        
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")
        
        def get_stat_value(team_id, stat_name, default=0):
            """Busca um valor de estatística específico para um time."""
            for team_stats in stats_list:
                if team_stats.get("team", {}).get("id") == team_id:
                    for stat in team_stats.get("statistics", []):
                        if stat.get("type") == stat_name:
                            return stat.get("value") or default
            return default

        full_game_stats = {
            "possession": {
                "home": get_stat_value(home_id, "Ball Possession", "N/A"),
                "away": get_stat_value(away_id, "Ball Possession", "N/A")
            },
            "shots_on_goal": {
                "home": get_stat_value(home_id, "Shots on Goal"),
                "away": get_stat_value(away_id, "Shots on Goal")
            },
            "total_shots": {
                "home": get_stat_value(home_id, "Total Shots"),
                "away": get_stat_value(away_id, "Total Shots")
            },
            "corners": {
                "home": get_stat_value(home_id, "Corner Kicks"),
                "away": get_stat_value(away_id, "Corner Kicks")
            },
             "fouls": {
                "home": get_stat_value(home_id, "Fouls"),
                "away": get_stat_value(away_id, "Fouls")
            },
            "yellow_cards": {
                "home": get_stat_value(home_id, "Yellow Cards"),
                "away": get_stat_value(away_id, "Yellow Cards")
            },
            "red_cards": {
                "home": get_stat_value(home_id, "Red Cards"),
                "away": get_stat_value(away_id, "Red Cards")
            }
        }
        
        current_minute = fixture.get("status", {}).get("elapsed", 0)
        estimated_stoppage = {}
        if current_minute:
            if 40 <= current_minute < 55:
                estimated_stoppage["first_half"] = estimate_stoppage_time(events, "1H")
            if current_minute >= 85:
                estimated_stoppage["second_half"] = estimate_stoppage_time(events, "2H")

        return {
            "teams": {"home": teams.get("home", {}).get("name"), "away": teams.get("away", {}).get("name")},
            "minute": current_minute,
            "score": f"{goals.get('home', 0)} - {goals.get('away', 0)}",
            "stats": {"fullGame": full_game_stats},
            "estimated_stoppage": estimated_stoppage,
            "events": sorted([
                {
                    "minute": e.get("time", {}).get("elapsed", 0),
                    "type": f"{e.get('type', '')} - {e.get('detail', '')}",
                    "detail": f"{e.get('player', {}).get('name', '')} ({e.get('team', {}).get('name', '')})"
                }
                for e in events if e.get("time", {}).get("elapsed")
            ], key=lambda x: x["minute"], reverse=True),
        }
    except requests.RequestException as e:
        print(f"ERRO CRÍTICO no Radar IA ao buscar estatísticas do jogo {game_id}: {e}")
        raise HTTPException(status_code=503, detail="A API de esportes não respondeu para as estatísticas do jogo.")
