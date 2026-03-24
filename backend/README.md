# Sadak Sathi — Backend

> Real-time road intelligence network powered by delivery riders.
> Automatically detects, confirms, and reports potholes — while holding contractors accountable.

---

## Architecture Overview

```
Mobile App (Rider)          Admin Panel
      │                          │
      └──────────┬───────────────┘
                 │
         FastAPI Gateway
         (auth · rate limit · WebSocket)
                 │
    ┌────────────┼────────────────────────────┐
    │            │            │               │
Detection   Hazard Map   Alert WS       Contractors
 Router      Router       Router          Router
    │            │            │               │
    └────────────┴────────────┴───────────────┘
                         │
              ┌──────────┼──────────┐
              │          │          │
         ML Service  Clustering  Accountability
         (YOLO+LSTM)  Engine      Engine
              │          │          │
    ┌─────────┴──────────┴──────────┴─────────┐
    │                                          │
PostgreSQL+PostGIS           Redis (cache + Celery broker)
    │                                          │
    └──────────────────────┬───────────────────┘
                           │
                    Celery Workers
              (satellite verify · scoring · alerts)
```

---

## Quick Start

### 1. Clone and configure

```bash
git clone <repo>
cd sadak_sathi_backend
cp .env.example .env
# Edit .env — set SECRET_KEY, DATABASE_URL, etc.
```

### 2. Place your ML model weights

```bash
cp /path/to/yolov8_pothole.pt ml_models/
cp /path/to/lstm_accelerometer.pt ml_models/
```

### 3. Start all services with Docker

```bash
docker-compose up --build
```

This starts:
- **FastAPI** on `http://localhost:8000`
- **PostgreSQL + PostGIS** on port 5432
- **Redis** on port 6379
- **Celery worker** (background tasks)
- **Celery beat** (periodic scheduler)
- **Flower** (task monitor) on `http://localhost:5555`

### 4. Run database migrations

```bash
docker-compose exec api alembic upgrade head
```

### 5. API docs

Open `http://localhost:8000/docs` for interactive Swagger UI.

---

## Development Setup (without Docker)

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Start PostgreSQL with PostGIS and Redis locally, then:
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# In another terminal — Celery worker:
celery -A app.workers.celery_app worker --loglevel=info

# In another terminal — Celery beat (periodic tasks):
celery -A app.workers.celery_app beat --loglevel=info
```

---

## API Reference

### Auth
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/auth/register` | Register a new rider |
| POST | `/api/v1/auth/login` | Login, get JWT token |
| GET | `/api/v1/auth/me` | Get current rider profile |
| PATCH | `/api/v1/auth/me/location` | Update last known location |

### Detection
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/detect/report` | Submit pothole detection (multipart with optional image) |
| GET | `/api/v1/detect/status/{id}` | Check pothole confirmation status |

**Detection payload (multipart/form-data):**
```
rider_id        string   required
latitude        float    required
longitude       float    required
detection_method string  camera | sensor | both
confidence      float    0.0–1.0
severity        string   S1 | S2 | S3
pothole_type    string   dry | water_filled | debris
speed_kmh       float    optional
sensor_json     string   JSON array of {x,y,z} accelerometer readings
image           file     optional JPEG/PNG
```

### Hazards (Live Map)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/hazards/` | Paginated hazard map (supports bbox filter) |
| GET | `/api/v1/hazards/nearby?lat=&lon=&radius_meters=` | Potholes near GPS point |
| GET | `/api/v1/hazards/stats?city=` | City-level summary stats |
| GET | `/api/v1/hazards/{id}` | Full pothole detail with image URL |

### Alerts (WebSocket)
```
WS  ws://host/api/v1/alerts/ws/{rider_id}
```

**Client → Server messages:**
```json
{"event": "location_update", "lat": 28.61, "lon": 77.20, "speed_kmh": 35}
{"event": "ack", "pothole_id": "uuid"}
{"event": "pong"}
```

**Server → Client messages:**
```json
{
  "event": "pothole_alert",
  "pothole_id": "uuid",
  "latitude": 28.61,
  "longitude": 77.20,
  "severity": "S3",
  "pothole_type": "water_filled",
  "distance_meters": 320,
  "eta_seconds": 45,
  "message": "Water-filled pothole ahead — depth unknown, extreme caution!",
  "priority": "HIGH"
}
```

REST fallback:
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts/active?lat=&lon=` | Confirmed potholes within radius |
| POST | `/api/v1/alerts/location` | Update location (non-WS) |
| GET | `/api/v1/alerts/stats` | Connected rider count |

### Routes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/routes/options` | Get fastest + safest route options |

**Request:**
```json
{
  "origin": {"latitude": 28.61, "longitude": 77.20},
  "destination": {"latitude": 28.70, "longitude": 77.10}
}
```

**Response:**
```json
{
  "fastest": {"type": "fastest", "duration_minutes": 18.5, "hazard_score": 12.0, "safety_rating": "Fair"},
  "safest":  {"type": "safest",  "duration_minutes": 21.0, "hazard_score": 2.0,  "safety_rating": "Good"},
  "recommended": "safest"
}
```

### Accountability
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/contractors/leaderboard` | Public contractor ranking |
| GET | `/api/v1/contractors/` | List all contractors |
| POST | `/api/v1/contractors/` | Create contractor (admin only) |
| GET | `/api/v1/contractors/{id}` | Contractor dashboard + stats |
| GET | `/api/v1/contractors/{id}/potholes` | Potholes linked to contractor |
| POST | `/api/v1/contractors/claims` | Submit repair claim |
| GET | `/api/v1/contractors/claims/{id}` | Check claim + satellite verification status |
| PATCH | `/api/v1/contractors/{id}/suspend` | Suspend contractor (admin only) |

---

## Key Design Decisions

### Confirmation Engine
- Reports within **15m radius** are clustered to the same pothole
- Status: `candidate` (2+ reports) → `confirmed` (5+ reports)
- **Dual confirmation bonus**: camera + sensor both confirming adds +2 to effective count
- Centroid is recalculated as a **weighted average** using rider accuracy scores
- Duplicate nearby candidates are merged after confirmation

### Severity Escalation
- Severity always escalates — never downgrades
- `S1 → S2 → S3` based on worst report in the cluster
- `water_filled` type is sticky once detected

### Accountability Engine
- Confirmed potholes are spatially matched to road segments via PostGIS `ST_Contains`
- Damage formula: `base_damage_per_vehicle × daily_vehicles × days_exposed / 1000`
- Contractor score: starts at 100, penalised for unrepaired potholes, warranty violations, fraud; rewarded for verified repairs

### Satellite Fraud Detection
- Contractor submits repair claim → payment blocked
- Celery task calls **ISRO Bhuvan WMS** or **Google Earth Engine**
- Before/after imagery diff analyzed for road surface change
- Confidence ≥ 0.70 → payment released, pothole marked `repaired`
- Confidence < 0.70 → marked `fraud`, contractor score penalised -8 points

### WebSocket Alerts
- Persistent WS per rider, keyed by `rider_id`
- Location tracked in-memory (`ConnectionManager`) for zero-latency proximity queries
- On new confirmation → background task fans out alerts to all connected riders within **400m**
- Keepalive ping every 30s

---

## Celery Periodic Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| `update_days_unrepaired` | Every hour | Increments exposure counter + escalates damage estimate |
| `verify_pending_repair_claims` | Every 24h | Re-runs satellite check on stale unverified claims |
| `recalculate_all_contractor_scores` | Daily | Full score recalculation for all contractors |
| `refresh_rider_accuracy_scores` | Daily | Updates rider weights based on confirmed report ratio |

---

## Running Tests

```bash
pytest                          # all tests
pytest tests/test_all.py -v     # verbose
pytest --cov=app                # with coverage
pytest -k "test_clustering"     # filter by name
```

---

## Environment Variables

See `.env.example` for the full documented list.

**Required:**
- `SECRET_KEY` — JWT signing key (generate with `openssl rand -hex 32`)
- `DATABASE_URL` — PostgreSQL+PostGIS connection string
- `REDIS_URL` — Redis connection string

**Optional but recommended for production:**
- `YOLO_MODEL_PATH` / `LSTM_MODEL_PATH` — ML model weights
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `S3_BUCKET` — image storage
- `OSRM_BASE_URL` or `GOOGLE_MAPS_API_KEY` — routing engine
- `GEE_SERVICE_ACCOUNT_KEY` — Google Earth Engine for satellite verification

---

## Project Structure

```
sadak_sathi_backend/
├── app/
│   ├── main.py                  # FastAPI app + lifespan
│   ├── config.py                # All settings via pydantic-settings
│   ├── dependencies.py          # get_db, get_current_rider, get_current_admin
│   ├── api/v1/
│   │   ├── router.py            # Aggregates all routers
│   │   ├── auth.py              # Register, login, profile
│   │   ├── detection.py         # Main ingestion endpoint
│   │   ├── hazards.py           # Live map feed
│   │   ├── alerts.py            # WebSocket + REST alerts
│   │   ├── routes.py            # Safe vs fastest routing
│   │   └── contractors.py       # Accountability + repair claims
│   ├── core/
│   │   ├── security.py          # JWT + bcrypt
│   │   ├── websocket_manager.py # WS connection pool + location cache
│   │   └── geospatial.py        # PostGIS helpers + haversine
│   ├── models/                  # SQLAlchemy ORM models
│   ├── schemas/                 # Pydantic request/response schemas
│   ├── services/
│   │   ├── ml_inference.py      # YOLOv8 + LSTM wrappers
│   │   ├── clustering.py        # Confirmation engine
│   │   ├── alert_service.py     # Proximity alerts
│   │   ├── route_service.py     # Road condition scoring
│   │   ├── accountability.py    # Damage calc + contractor scoring
│   │   └── satellite_verify.py  # Repair fraud detection
│   ├── workers/
│   │   ├── celery_app.py        # Celery instance + beat schedule
│   │   └── tasks.py             # All background tasks
│   └── db/
│       ├── session.py           # Async engine + session factory
│       └── migrations/          # Alembic migrations
├── ml_models/                   # Model weights (gitignored)
├── tests/
│   ├── conftest.py              # Shared fixtures
│   └── test_all.py              # Full test suite
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
├── pytest.ini
└── .env.example
```