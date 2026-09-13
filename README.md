# WeatherGPT

A conversational weather assistant: real live weather data (Open-Meteo),
Claude as the conversational AI with tool-calling, a small trained
scikit-learn "risk index" model, and a farmer crop-advisory feature — all
in English / Hindi / Bangla.

## Fastest way to run it (zero setup)

**Mac/Linux:** double-click `start.sh`, or run `./start.sh` in a terminal.
**Windows:** double-click `start.bat`.

That's it. The script creates the Python environment, installs everything,
starts the backend, serves the frontend, and opens your browser
automatically. **No API key is required to try it** — until you add one,
the app runs on a built-in local rule-based engine (see "Two ways to run
the AI" below) using 100% real live weather data, just with simpler
conversational replies than Claude gives.

If you do want the full Claude-powered conversation (better replies, and
it can hold context across follow-up questions), paste a key from
https://console.anthropic.com/ into `backend/.env` (the script creates this
file for you on first run) and restart `start.sh` / `start.bat`. No other
code changes needed — the backend detects the key automatically.

The little "engine:" badge in the top-right of the app tells you which
mode you're currently in.

This is a full split of your original single-file prototype into a proper
**frontend + backend**, so:
- Your Anthropic API key never sits in browser JavaScript (the prototype
  called `api.anthropic.com` directly from the client, which leaks the key
  and would be blocked by CORS on any real deployment).
- Location lookups now disambiguate properly: if a place name matches
  more than one real location, WeatherGPT asks **which state** first, and
  **which district** next if the state alone still isn't enough — instead
  of silently guessing (which is what a bare geocoding lookup does).
- There's a real trained machine-learning model (not just prompt text)
  contributing an extra "AI risk index" signal alongside the deterministic
  hazard advisories.

```
weathergpt/
├── start.sh / start.bat       One-command launcher (installs + runs everything)
├── backend/                   FastAPI server (Python)
│   ├── app/
│   │   ├── main.py            API routes + Claude tool-calling orchestration
│   │   ├── claude_service.py  Anthropic API calls (key stays server-side)
│   │   ├── local_nlu.py       Zero-key fallback engine (rule-based, real weather data)
│   │   ├── geocode_service.py Location resolution + state/district disambiguation
│   │   ├── weather_service.py Open-Meteo forecast fetch + hazard advisory rules
│   │   ├── crop_advisory.py   Farmer advisory (season + crop + care, 3 languages)
│   │   ├── ml_model.py        Loads the trained risk model for scoring
│   │   └── config.py          Env var loading
│   ├── models/
│   │   ├── weather_risk_model.pkl        Pre-trained model (ships ready to run)
│   │   ├── model_meta.json               Feature/label schema for the model
│   │   ├── train_synthetic_baseline.py   Regenerates the baseline model (offline)
│   │   └── train_on_live_history.py      Retrains on REAL historical weather data (needs internet)
│   ├── requirements.txt
│   ├── .env.example
│   └── run.py
└── frontend/                  Static site (no build step)
    ├── index.html
    ├── style.css
    ├── config.js               <- set your backend URL here
    └── app.js
```

## Manual setup (if you'd rather not use the start script)

### 1. Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# optional: edit .env and paste a real ANTHROPIC_API_KEY (from https://console.anthropic.com/)
# leave it blank and the app still works, using the local rule-based engine

python run.py
```

The API now runs at `http://localhost:8000`. Check `http://localhost:8000/api/health`.

A pre-trained ML model is already included (`models/weather_risk_model.pkl`),
so you don't have to train anything to get started.

### Retraining the ML model on real historical data (optional, recommended)

The included model is trained on a synthetic-but-domain-informed dataset
(30,000 rows) so the app works immediately with zero setup. For a stronger
model trained on **real observed weather history**, run, once you have
internet access:

```bash
cd backend/models
python train_on_live_history.py
```

This pulls ~6 years of real daily weather for 15 Indian cities across
different climate zones from Open-Meteo's free historical archive, labels
each day's hazard level with the same rules used for the live advisories,
and trains a fresh `RandomForestClassifier` on that real data — no code
changes needed elsewhere, it just overwrites the `.pkl` file in place.

### 2. Frontend setup

No build step — it's plain HTML/CSS/JS.

1. Open `frontend/config.js` and set `API_BASE_URL` to wherever your
   backend is running (defaults to `http://localhost:8000` for local dev).
2. Serve the folder with any static file server, for example:

```bash
cd frontend
python -m http.server 5500
```

3. Open `http://localhost:5500` in your browser.

(Opening `index.html` directly via `file://` also works for a quick look,
but a real static server avoids some browsers' `fetch` restrictions on
`file://` pages.)

## Two ways to run the AI

| | Local engine (default, no key) | Claude (with API key) |
|---|---|---|
| Setup | None | Paste key into `backend/.env` |
| Weather data | Real, live (Open-Meteo) | Real, live (Open-Meteo) |
| Location disambiguation | Full state → district flow | Full state → district flow |
| Farmer/crop advisory | Full, multilingual | Full, multilingual |
| Conversation quality | Template replies, single-turn | Natural, holds context, handles phrasing you didn't anticipate |
| Cost | Free | Anthropic API usage cost |

Both modes are wired into the exact same `/api/chat` endpoint — the
frontend doesn't know or care which one answered. If a configured Claude
key ever fails mid-session (bad key, no internet, rate limit), the backend
automatically drops back to the local engine for that turn instead of
showing an error.

## How the location disambiguation works

Try asking about a place name that isn't unique (there are many villages
and small towns in India that share a name). The flow is:

1. Claude calls the `get_weather` tool with just the place name.
2. The backend's `geocode_service.resolve_location()` checks how many real
   places match that name.
   - Exactly one → resolved immediately, weather is fetched.
   - More than one, in different states → the tool returns
     `status: "need_state"` with the list of states; Claude asks you which
     state, in the chat, and the frontend also shows clickable state chips.
   - You answer/click a state; if that state alone still has more than one
     match, the tool returns `status: "need_district"` and the same thing
     happens for district.
   - Once state (+ district if needed) narrows it to one place, the
     forecast is fetched for that exact location.

You can test this by asking about a common Indian place name and watching
it ask for the state, then (if needed) the district, before answering.

## Notes on the "AI model"

Two AI components work together, deliberately kept separate:

- **Claude** (via the Anthropic API, server-side) is the conversational
  layer: it understands the user's question, decides when to fetch live
  weather, and writes the natural-language reply plus farmer advisory in
  the right language. No training is needed or possible here — it's a
  general-purpose foundation model used through the API.
- **The scikit-learn `RandomForestClassifier`** in `backend/models/` is a
  genuinely trained model on a genuine dataset, producing the "risk index"
  badge shown in the UI. It's retrainable on real historical weather data
  with the included script, which is the honest way to describe an "AI
  model with proper dataset training" for a weather app — real, hard hazard
  forecasting from raw atmospheric data is a much bigger research problem
  than a single script can responsibly claim to solve, so this model adds a
  genuine but scoped ML signal on top of Open-Meteo's own (very good)
  numerical weather forecast, rather than pretending to replace it.
