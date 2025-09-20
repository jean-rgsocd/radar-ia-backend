# Filename: radar_ia.py
# Versão 2.0 - Conectado com API Real (API-Sports)

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from datetime import datetime, timedelta

app = FastAPI(title="Radar IA - V2.0 Real Time")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Configuração da API-Sports ---
API_SPORTS_KEY = "85741d1d66385996de506a07e3f527d1"
API_SPORTS_URL = "https://v3.football.api-sports.io"

# --- Cache Simples para evitar chamadas repetidas ---
cache: Dict[str, Dict[str, Any]] = {}

# --- Endpoints ---

@app.get("/jogos-aovivo")
def get_live_games():
    """Busca jogos de futebol que estão realmente acontecendo agora."""
    cache_key = "live_games"
    if cache_key in cache and datetime.now() < cache[cache_key]['expiry']:
        return cache[cache_key]['data']

    headers = {'x-apisports-key': API_SPORTS_KEY}
    params = {'live': 'all'}
    
    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get('response', [])
        
        live_games = sorted([
            {
                "game_id": fixture['fixture']['id'],
                "title": f"{fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']} ({fixture['league']['name']})"
            }
            for fixture in data
        ], key=lambda x: x['title'])
        
        cache[cache_key] = {'data': live_games, 'expiry': datetime.now() + timedelta(minutes=2)}
        return live_games
    except requests.RequestException as e:
        print(f"Erro ao buscar jogos ao vivo: {e}")
        raise HTTPException(status_code=500, detail="Erro ao contatar a API de esportes.")

@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    """Busca as estatísticas reais e calcula o índice de pressão para um jogo."""
    headers = {'x-apisports-key': API_SPORTS_KEY}
    params = {'id': game_id}

    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get('response', [])[0]
        
        fixture_data = data.get('fixture', {})
        teams_data = data.get('teams', {})
        goals_data = data.get('goals', {})
        stats_list = data.get('statistics', [])
        events_data = data.get('events', [])

        def get_stat(team_id, stat_name):
            for team_stats in stats_list:
                if team_stats['team']['id'] == team_id:
                    for stat in team_stats['statistics']:
                        if stat['type'] == stat_name:
                            return stat['value'] if stat['value'] is not None else 0
            return 0
        
        home_id = teams_data['home']['id']
        away_id = teams_data['away']['id']

        home_possession = str(get_stat(home_id, "Ball Possession")).replace('%', '')
        away_possession = str(get_stat(away_id, "Ball Possession")).replace('%', '')

        stats = {
            "possession": {"home": int(home_possession) if home_possession.isdigit() else 50, "away": int(away_possession) if away_possession.isdigit() else 50},
            "shots": {"home": get_stat(home_id, "Total Shots"), "away": get_stat(away_id, "Total Shots")},
            "corners": {"home": get_stat(home_id, "Corner Kicks"), "away": get_stat(away_id, "Corner Kicks")},
            "cards": {
                "yellow_home": get_stat(home_id, "Yellow Cards"), "red_home": get_stat(home_id, "Red Cards"),
                "yellow_away": get_stat(away_id, "Yellow Cards"), "red_away": get_stat(away_id, "Red Cards"),
            }
        }

        # --- Lógica do "Índice de Pressão" ---
        current_minute = fixture_data.get('status', {}).get('elapsed', 0)
        last_10_min_events = [e for e in events_data if e.get('time', {}).get('elapsed', 0) > (current_minute - 10)]
        home_pressure, away_pressure = 0, 0
        
        for event in last_10_min_events:
            if event.get('team', {}).get('id') == home_id:
                if "Shot" in event.get('type', ''): home_pressure += 2
                if "Corner" in event.get('type', ''): home_pressure += 1
            elif event.get('team', {}).get('id') == away_id:
                if "Shot" in event.get('type', ''): away_pressure += 2
                if "Corner" in event.get('type', ''): away_pressure += 1

        total_pressure = home_pressure + away_pressure
        pressure_index = (home_pressure / total_pressure * 100) if total_pressure > 0 else 50
        
        return {
            "minute": current_minute,
            "score": f"{goals_data.get('home', 0)} - {goals_data.get('away', 0)}",
            "stats": stats,
            "pressure_index": pressure_index,
            "events": sorted([
                {"minute": e.get('time', {}).get('elapsed', 0), "type": e.get('type', ''), "detail": f"{e.get('player', {}).get('name', '')} ({e.get('team', {}).get('name', '')})"}
                for e in events_data if e.get('time', {}).get('elapsed')
            ], key=lambda x: x['minute'], reverse=True)
        }
    except (requests.RequestException, IndexError) as e:
        print(f"Erro ao buscar stats para o jogo {game_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro ao buscar estatísticas do jogo.")

