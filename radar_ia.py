# radar_ia.py
# Radar IA - Somente jogos ao vivo + eventos invertidos + acréscimos simplificados
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests, traceback

app = FastAPI(title="Radar IA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"]
)

API_SPORTS_KEY = "7baa5e00c8ae57d0e6240f790c6840dd"
API_HOST = "v3.football.api-sports.io"
API_URL = f"https://{API_HOST}"
HEADERS = {
    "x-rapidapi-key": API_SPORTS_KEY,
    "x-rapidapi-host": API_HOST
}

def api_get(endpoint: str, params: dict = None):
    try:
        r = requests.get(f"{API_URL}/{endpoint}", headers=HEADERS, params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("response", [])
    except Exception as e:
        print(f"Erro Radar API {endpoint}: {e}")
        print(traceback.format_exc())
        return []

@app.get("/ligas")
def list_leagues():
    data = api_get("fixtures", {"live": "all"})
    leagues = {}
    for f in data:
        l = f.get("league", {})
        leagues[l["id"]] = {"id": l["id"], "name": l["name"], "country": l["country"]}
    return list(leagues.values())

@app.get("/jogos-aovivo")
def live_games(league: int = Query(None)):
    params = {"live": "all"}
    if league:
        params["league"] = league
    data = api_get("fixtures", params)
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
    return results

@app.get("/stats-aovivo/{game_id}")
def live_stats(game_id: int):
    # Fixture
    fixture_data = api_get("fixtures", {"id": game_id})
    if not fixture_data:
        raise HTTPException(status_code=404, detail="Jogo não encontrado")
    fixture = fixture_data[0]

    # Eventos
    events = api_get("fixtures/events", {"fixture": game_id})
    processed = []
    for ev in events:
        elapsed = ev.get("time", {}).get("elapsed")
        sec = ev.get("time", {}).get("second")
        extra = ev.get("time", {}).get("extra")
        # Montar tempo
        if elapsed is not None:
            if extra:
                display_time = f"{elapsed}+{extra}'"
            else:
                display_time = f"{elapsed}'"
            if sec is not None:
                display_time += f"{sec:02d}\""
        else:
            display_time = "-"
        processed.append({
            "display_time": display_time,
            "type": ev.get("type"),
            "detail": ev.get("detail"),
            "player": ev.get("player", {}).get("name"),
            "team": ev.get("team", {}).get("name"),
            "raw": ev
        })
    # Ordenar eventos mais recentes primeiro
    processed.sort(key=lambda x: x["raw"].get("time", {}).get("elapsed", 0), reverse=True)

    # Estatísticas
    stats = api_get("fixtures/statistics", {"fixture": game_id})

    # Acréscimos simplificados
    elapsed = fixture.get("fixture", {}).get("status", {}).get("elapsed")
    extra_est = None
    if elapsed is not None:
        if 40 <= elapsed <= 45:
            extra_est = 3
        elif 80 <= elapsed <= 90:
            extra_est = 4

    return {
        "fixture": fixture.get("fixture"),
        "league": fixture.get("league"),
        "teams": fixture.get("teams"),
        "goals": fixture.get("goals"),
        "score": fixture.get("score"),
        "statistics": stats,
        "events": processed,
        "estimated_extra": extra_est
    }
