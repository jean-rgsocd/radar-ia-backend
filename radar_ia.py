# Filename: radar_ia.py
# Versão 10.0 - FINAL (Autenticação Direta API-Sports)

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any
from datetime import datetime

app = FastAPI(title="Radar IA - API Definitiva V10.0")

# --- CORS ---
origins = ["*"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- CONFIGURAÇÃO DA API-SPORTS ---
API_SPORTS_KEY = "7baa5e00c8ae61790c6840dd"
API_HOST = "v3.football.api-sports.io"
API_URL = f"https://{API_HOST}"

# Cabeçalhos Corretos
HEADERS = {
    'x-rapidapi-key': API_SPORTS_KEY,
    'x-rapidapi-host': API_HOST
}

def get_current_season() -> str:
    return str(datetime.now().year)

# --- ENDPOINTS DA API ---
@app.get("/jogos-aovivo")
def get_live_games():
    params = {"live": "all"}
    try:
        response = requests.get(f"{API_URL}/fixtures", headers=HEADERS, params=params, timeout=20)
        response.raise_for_status()
        data = response.json().get("response", [])
        
        return sorted([
            {"game_id": f["fixture"]["id"], "title": f"{f['teams']['home']['name']} vs {f['teams']['away']['name']} ({f['league']['name']})"}
            for f in data if f.get("fixture") and f.get("teams") and f.get("league")
        ], key=lambda x: x["title"])
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
        return data[0]
    except requests.RequestException as e:
        print(f"ERRO CRÍTICO no Radar IA ao buscar estatísticas do jogo {game_id}: {e}")
        raise HTTPException(status_code=503, detail="A API de esportes não respondeu para as estatísticas do jogo.")
