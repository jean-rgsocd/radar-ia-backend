# Filename: radar_ia.py
# Versão 3.0 - Índice de Pressão Melhorado (real time)

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any
from datetime import datetime, timedelta

app = FastAPI(title="Radar IA - V3.0 Real Time")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Configuração da API-Sports ---
API_SPORTS_KEY = "85741d1d66385996de506a07e3f527d1"
API_SPORTS_URL = "https://v3.football.api-sports.io"

# --- Cache Simples ---
cache: Dict[str, Dict[str, Any]] = {}

# --- Jogos ao vivo ---
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
            {
                "game_id": fixture["fixture"]["id"],
                "title": f"{fixture['teams']['home']['name']} vs {fixture['teams']['away']['name']} ({fixture['league']['name']})"
            }
            for fixture in data if fixture.get("fixture") and fixture.get("teams")
        ], key=lambda x: x["title"])

        cache[cache_key] = {"data": live_games, "expiry": datetime.now() + timedelta(minutes=2)}
        return live_games
    except requests.RequestException as e:
        print(f"Erro ao buscar jogos ao vivo: {e}")
        raise HTTPException(status_code=500, detail="Erro ao contatar a API de esportes.")

# --- Estatísticas ao vivo + Índice de Pressão ---
@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    headers = {"x-apisports-key": API_SPORTS_KEY}
    params = {"id": game_id}

    try:
        response = requests.get(f"{API_SPORTS_URL}/fixtures", headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json().get("response", [])[0]

        fixture_data = data.get("fixture", {})
        teams_data = data.get("teams", {})
        goals_data = data.get("goals", {})
        stats_list = data.get("statistics", [])
        events_data = data.get("events", [])

        def get_stat(team_id, stat_name):
            for team_stats in stats_list:
                if team_stats.get("team", {}).get("id") == team_id:
                    for stat in team_stats.get("statistics", []):
                        if stat.get("type") == stat_name:
                            return stat.get("value") or 0
            return 0

        home_id = teams_data.get("home", {}).get("id")
        away_id = teams_data.get("away", {}).get("id")

        # Stats básicos
        home_possession = str(get_stat(home_id, "Ball Possession")).replace("%", "")
        away_possession = str(get_stat(away_id, "Ball Possession")).replace("%", "")

        stats = {
            "possession": {
                "home": int(home_possession) if home_possession.isdigit() else 50,
                "away": int(away_possession) if away_possession.isdigit() else 50,
            },
            "shots": {
                "home": get_stat(home_id, "Total Shots"),
                "away": get_stat(away_id, "Total Shots"),
            },
            "corners": {
                "home": get_stat(home_id, "Corner Kicks"),
                "away": get_stat(away_id, "Corner Kicks"),
            },
            "cards": {
                "yellow_home": get_stat(home_id, "Yellow Cards"),
                "red_home": get_stat(home_id, "Red Cards"),
                "yellow_away": get_stat(away_id, "Yellow Cards"),
                "red_away": get_stat(away_id, "Red Cards"),
            },
        }

        # --- Índice de Pressão ---
        current_minute = fixture_data.get("status", {}).get("elapsed", 0)
        last_10_min_events = [e for e in events_data if e.get("time", {}).get("elapsed", 0) > (current_minute - 10)]

        weights = {
            "shot on goal": 3,
            "shot off goal": 1,
            "corner kick": 2,
            "dangerous attack": 2,
            "goal": 5,
        }

        home_pressure, away_pressure = 0, 0
        for event in last_10_min_events:
            etype = (event.get("type") or "").lower() + " " + (event.get("detail") or "").lower()
            tid = event.get("team", {}).get("id")

            score = 0
            for k, w in weights.items():
                if k in etype:
                    score = w
                    break

            if tid == home_id:
                home_pressure += score
            elif tid == away_id:
                away_pressure += score

        total_pressure = home_pressure + away_pressure
        if total_pressure > 0:
            home_pct = round(home_pressure / total_pressure * 100)
            away_pct = 100 - home_pct
        else:
            home_pct, away_pct = 50, 50

        dominant = "home" if home_pct > away_pct else "away" if away_pct > home_pct else "neutral"

        return {
            "minute": current_minute,
            "score": f"{goals_data.get('home', 0)} - {goals_data.get('away', 0)}",
            "stats": stats,
            "indice_pressao": {"home": home_pct, "away": away_pct},
            "lado_dominante": dominant,
            "events": sorted([
                {
                    "minute": e.get("time", {}).get("elapsed", 0),
                    "type": e.get("type", ""),
                    "detail": f"{e.get('player', {}).get('name', '')} ({e.get('team', {}).get('name', '')})"
                }
                for e in events_data if e.get("time", {}).get("elapsed")
            ], key=lambda x: x["minute"], reverse=True),
        }
    except (requests.RequestException, IndexError) as e:
        print(f"Erro ao buscar stats para o jogo {game_id}: {e}")
        raise HTTPException(status_code=500, detail="Erro ao buscar estatísticas do jogo.")
