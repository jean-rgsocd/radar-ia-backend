# Filename: radar_ia.py
# Versão 4.0 - Análise por Tempo e Estimativa de Acréscimos

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from datetime import datetime, timedelta

app = FastAPI(title="Radar IA - V4.0 Detalhado")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Configuração da API-Sports ---
API_SPORTS_KEY = "85741d1d66385996de506a07e3f527d1"
API_SPORTS_URL = "https://v3.football.api-sports.io"
cache: Dict[str, Dict[str, Any]] = {}

# --- Endpoint de Jogos ao vivo ---
@app.get("/jogos-aovivo")
def get_live_games():
    cache_key = "live_games"
    if cache_key in cache and datetime.now() < cache[cache_key]['expiry']:
        return cache[cache_key]['data']
    
    headers = {"x-apisports-key": API_SPORTS_KEY}
    params = {"live": "all"}
    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("response", [])
        live_games = sorted([
            {"game_id": f["fixture"]["id"], "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})"}
            for f in data if f.get("fixture") and f.get("teams")
        ], key=lambda x: x["title"])
        cache[cache_key] = {"data": live_games, "expiry": datetime.now() + timedelta(minutes=2)}
        return live_games
    except requests.RequestException as e:
        raise HTTPException(status_code=500, detail="Erro ao contatar a API de esportes.")

# --- Lógica de Estimativa de Acréscimos ---
def estimate_stoppage_time(events: List[Dict[str, Any]], period: str) -> int:
    stoppage_seconds = 0
    start_minute, end_minute = (0, 45) if period == "1H" else (46, 90)
    
    period_events = [e for e in events if start_minute < e.get("time", {}).get("elapsed", 0) <= end_minute]
    
    goals = len([e for e in period_events if e.get("type") == "Goal"])
    substitutions = len([e for e in period_events if e.get("type") == "subst"])
    cards = len([e for e in period_events if e.get("type") == "Card"])
    
    # Heurística: 45s por gol, 30s por substituição, 15s por cartão
    stoppage_seconds += goals * 45
    stoppage_seconds += substitutions * 30
    stoppage_seconds += cards * 15
    
    if len(period_events) > 7: # Adiciona um pouco mais por "cera" se o jogo for muito parado
        stoppage_seconds += 60

    return round(stoppage_seconds / 60)

# --- Estatísticas ao vivo + Análise por Tempo ---
@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    headers = {"x-apisports-key": API_SPORTS_KEY}
    params = {"id": game_id}
    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("response", [])[0]

        fixture = data.get("fixture", {})
        teams = data.get("teams", {})
        goals = data.get("goals", {})
        stats_list = data.get("statistics", [])
        events = data.get("events", [])
        
        home_id = teams.get("home", {}).get("id")
        away_id = teams.get("away", {}).get("id")

        def get_stat_value(team_id, stat_name):
            for team_stats in stats_list:
                if team_stats.get("team", {}).get("id") == team_id:
                    for stat in team_stats.get("statistics", []):
                        if stat.get("type") == stat_name:
                            return stat.get("value") or 0
            return 0

        def calculate_stats_for_period(period_events):
            stats = {"shots_on_goal": {"home": 0, "away": 0}, "shots_off_goal": {"home": 0, "away": 0}, "total_shots": {"home": 0, "away": 0}, "corners": {"home": 0, "away": 0}, "fouls": {"home": 0, "away": 0}, "yellow_cards": {"home": 0, "away": 0}, "red_cards": {"home": 0, "away": 0}}
            for event in period_events:
                team_id = event.get("team", {}).get("id")
                team_key = "home" if team_id == home_id else "away"
                type, detail = (event.get("type") or "").lower(), (event.get("detail") or "").lower()
                if type == "goal" or detail == "shot on goal": stats["shots_on_goal"][team_key] += 1
                elif detail == "shot off goal" or detail == "missed penalty": stats["shots_off_goal"][team_key] += 1
                elif type == "corner": stats["corners"][team_key] += 1
                elif type == "foul": stats["fouls"][team_key] += 1
                elif type == "card" and detail == "yellow card": stats["yellow_cards"][team_key] += 1
                elif type == "card" and detail == "red card": stats["red_cards"][team_key] += 1
            stats["total_shots"]["home"] = stats["shots_on_goal"]["home"] + stats["shots_off_goal"]["home"]
            stats["total_shots"]["away"] = stats["shots_on_goal"]["away"] + stats["shots_off_goal"]["away"]
            return stats

        first_half_events = [e for e in events if e.get("time", {}).get("elapsed", 999) <= 45]
        second_half_events = [e for e in events if e.get("time", {}).get("elapsed", 0) > 45]

        full_game_stats = {"possession": {"home": int(str(get_stat_value(home_id, "Ball Possession")).replace('%', '') or 50), "away": int(str(get_stat_value(away_id, "Ball Possession")).replace('%', '') or 50)}, "shots_on_goal": {"home": get_stat_value(home_id, "Shots on Goal"), "away": get_stat_value(away_id, "Shots on Goal")}, "total_shots": {"home": get_stat_value(home_id, "Total Shots"), "away": get_stat_value(away_id, "Total Shots")}, "corners": {"home": get_stat_value(home_id, "Corner Kicks"), "away": get_stat_value(away_id, "Corner Kicks")}, "fouls": {"home": get_stat_value(home_id, "Fouls"), "away": get_stat_value(away_id, "Fouls")}, "yellow_cards": {"home": get_stat_value(home_id, "Yellow Cards"), "away": get_stat_value(away_id, "Yellow Cards")}, "red_cards": {"home": get_stat_value(home_id, "Red Cards"), "away": get_stat_value(away_id, "Red Cards")}}

        current_minute = fixture.get("status", {}).get("elapsed", 0)
        estimated_stoppage = {}
        if 40 <= current_minute < 55: estimated_stoppage["first_half"] = estimate_stoppage_time(events, "1H")
        if current_minute >= 85: estimated_stoppage["second_half"] = estimate_stoppage_time(events, "2H")

        return {
            "teams": {"home": teams.get("home", {}).get("name"), "away": teams.get("away", {}).get("name")},
            "minute": current_minute,
            "score": f"{goals.get('home', 0)} - {goals.get('away', 0)}",
            "stats": {"fullGame": full_game_stats, "firstHalf": calculate_stats_for_period(first_half_events), "secondHalf": calculate_stats_for_period(second_half_events)},
            "estimated_stoppage": estimated_stoppage,
            "events": sorted([
                {"minute": e.get("time", {}).get("elapsed", 0), "type": f"{e.get('type', '')} - {e.get('detail', '')}", "detail": f"{e.get('player', {}).get('name', '')} ({e.get('team', {}).get('name', '')})"}
                for e in events if e.get("time", {}).get("elapsed")
            ], key=lambda x: x["minute"], reverse=True),
        }
    except (requests.RequestException, IndexError) as e:
        raise HTTPException(status_code=500, detail="Erro ao buscar estatísticas do jogo.")
