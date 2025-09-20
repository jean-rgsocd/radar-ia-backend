# Filename: radar_ia.py
# Versão 1.0 - Estrutura com Dados Simulados (Mock)

import random
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Any

app = FastAPI(title="Radar IA - Live Stats")

# --- CORS ---
origins = ["https://jean-rgsocd.github.io", "http://127.0.0.1:5500", "http://localhost:5500"]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# --- Dados Simulados (Mocks) ---
# Lista de jogos que estão "acontecendo agora"
MOCK_LIVE_GAMES = [
    {"game_id": 1001, "title": "Flamengo vs Vasco (AO VIVO)"},
    {"game_id": 1002, "title": "Manchester City vs Liverpool (AO VIVO)"},
    {"game_id": 1003, "title": "Los Angeles Lakers vs Boston Celtics (AO VIVO)"}
]

# --- Endpoints ---

@app.get("/jogos-aovivo")
def get_live_games():
    """Retorna a lista de jogos que estão acontecendo para o usuário escolher."""
    return MOCK_LIVE_GAMES

@app.get("/stats-aovivo/{game_id}")
def get_live_stats_for_game(game_id: int):
    """
    Este é o coração do Radar.
    Ele SIMULA as estatísticas de um jogo em tempo real.
    Os números mudam a cada chamada para imitar a dinâmica de uma partida.
    """
    # Simula o tempo de jogo
    minute = random.randint(1, 90)
    
    # Simula eventos aleatórios
    events = []
    if 40 < minute < 45:
        events.append({"minute": 41, "type": "Cartão Amarelo", "detail": "Jogador do Time da Casa"})
    if 70 < minute < 80:
        events.append({"minute": 75, "type": "Gol", "detail": "Gol do Time Visitante!"})

    # Retorna um dicionário com todas as estatísticas simuladas
    return {
        "game_id": game_id,
        "minute": minute,
        "score": f"{random.randint(0, 2)} - {random.randint(0, 2)}",
        "stats": {
            "possession": {
                "home": random.randint(30, 70),
                "away": 100 - random.randint(30, 70) 
            },
            "shots": {
                "home": random.randint(5, 20),
                "away": random.randint(3, 18)
            },
            "corners": {
                "home": random.randint(0, 8),
                "away": random.randint(1, 9)
            },
            "cards": {
                "yellow_home": random.randint(0, 4),
                "yellow_away": random.randint(1, 5),
                "red_home": random.choice([0, 1]),
                "red_away": random.choice([0, 1])
            }
        },
        "events": events
    }