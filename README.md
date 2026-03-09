# Agile Intelligence Platform

AI-powered risk intelligence for agile teams. Synthesizes Jira, Slack, and meeting transcripts into actionable coaching insights via a conversational chat interface.

## Stack

- **Backend**: Python 3.11 / FastAPI
- **Database**: PostgreSQL 16
- **Task Queue**: Redis + APScheduler
- **AI**: Claude API (Anthropic)
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Auth**: JWT (python-jose)
- **Migrations**: Alembic

## Quick Start

### Prerequisites
- Docker + Docker Compose
- Jira Cloud account (OAuth app credentials)
- Anthropic API key
- (Phase 3) Slack app token, Google OAuth credentials

### 1. Clone & configure
```bash
cp .env.example .env
# Fill in your credentials in .env
```

### 2. Start services
```bash
docker compose up --build
```

### 3. Run migrations
```bash
docker compose exec api alembic upgrade head
```

### 4. Seed a test user
```bash
docker compose exec api python -m app.scripts.seed
```

App runs at:
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost:5173

## Project Structure

```
agile-intel/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI route handlers
│   │   ├── core/         # Config, security, logging
│   │   ├── db/           # Database session, base
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── schemas/      # Pydantic request/response schemas
│   │   ├── pipelines/    # Jira / Slack / Transcript sync jobs
│   │   ├── services/     # Risk engine, AI synthesis, chat
│   │   └── scripts/      # CLI utilities
│   ├── alembic/          # DB migrations
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/             # React app (Phase 2)
├── docker-compose.yml
└── .env.example
```

## Environment Variables

See `.env.example` for all required variables.

## Phase Roadmap

| Phase | Description | Status |
|-------|-------------|--------|
| 1 | Core backend + Jira pipeline + Risk scoring | ✅ Built |
| 2 | React chat UI + AI synthesis | 🔜 Next |
| 3 | Slack + Google Meet pipelines | 🔜 Planned |
| 4 | Trend intelligence + Alerts | 🔜 Planned |
