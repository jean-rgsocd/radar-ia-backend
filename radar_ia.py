# Filename: radar_ia.py
# Versão 8.0 - GOLD STANDARD (Autenticação Direta API-Sports)

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, List
from datetime import datetime

app = FastAPI(title="Radar IA - API Definitiva V8.0")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500", "*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURAÇÃO DA API-SPORTS (MÉTODO DE AUTENTICAÇÃO DIRETO) ---
# CORREÇÃO CRÍTICA: Usando o cabeçalho 'x-apisports-key' para acesso direto
API_SPORTS_KEY = "7baa5e00c8ae61790c6840dd"
HEADERS = {"x-apisports-key": API_SPORTS_KEY}

# CORREÇÃO CRÍTICA: Usando a URL direta da API-Sports
API_URL = "https://v3.football.api-sports.io"

def get_current_season() -> str:
    return str(datetime.now().year)

# --- Endpoint de Jogos ao vivo ---
@app.get("/jogos-aovivo")
def get_live_games():
    params = {"live": "all", "season": get_current_season()}
    try:
        response = requests.get(f"{API_URL}/fixtures", headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("response", [])
        
        live_games = sorted([
            {"game_id": f["fixture"]["id"], "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})"}
            for f in data if f.get("fixture") and f.get("teams") and f.get("league")
        ], key=lambda x: x["title"])
        
        return live_games
    except requests.RequestException as e:
        print(f"ERRO CRÍTICO no Radar IA ao buscar jogos ao vivo: {e}")
        raise HTTPException(status_code=503, detail="A API de esportes não respondeu para jogos ao vivo.")

@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    params = {"id": game_id}
    try:
        response = requests.get(f"{API_URL}/fixtures", headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("response", [])
        if not data:
            raise HTTPException(status_code=404, detail="Jogo não encontrado.")
        
        game_data = data[0]
        teams = game_data.get("teams", {})
        goals = game_data.get("goals", {})
        
        return {
            "teams": {"home": teams.get("home", {}).get("name"), "away": teams.get("away", {}).get("name")},
            "minute": game_data.get("fixture", {}).get("status", {}).get("elapsed", 0),
            "score": f"{goals.get('home', 0)} - {goals.get('away', 0)}",
            "stats": {"fullGame": game_data.get("statistics", [])},
            "events": sorted(game_data.get("events", []), key=lambda x: x.get("time", {}).get("elapsed", 0), reverse=True),
        }
    except requests.RequestException as e:
        print(f"ERRO CRÍTICO no Radar IA ao buscar estatísticas do jogo {game_id}: {e}")
        raise HTTPException(status_code=503, detail="A API de esportes não respondeu para as estatísticas do jogo.")
