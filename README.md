const TIPSTER_API = "URL_DO_DEPLOY";

---

# 📌 `README.md` – **Radar IA (radar-ia-backend)**

```markdown
# 📡 Radar IA – Monitoramento de Jogos Ao Vivo

Backend em **FastAPI** que retorna **jogos ao vivo** e estatísticas em tempo real.

---

## 🚀 Endpoints

### Jogos ao Vivo
Retorna todos os jogos **em andamento**.  
Resposta contém:
- `game_id`
- `home`, `away`
- `league`
- `status` (tempo de jogo)

---

### Estatísticas ao Vivo
Retorna estatísticas atualizadas do jogo:
- Placar
- Ataques
- Remates
- Cantos
- Posse de bola
- Pressão ofensiva

---

## 🛠️ Execução Local

```bash
# Instalar dependências
pip install -r requirements.txt

# Rodar servidor local
uvicorn radar_ia:app --reload
http://127.0.0.1:8000
