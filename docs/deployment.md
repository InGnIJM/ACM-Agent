# ACM Agent Deployment Runbook

Last updated: 2026-06-13

---

## 1. Prerequisites

- **Docker** >= 24.x (with Docker Compose V2)
- **Git** (to clone the repo)
- Access to AI provider API keys (DeepSeek, OpenAI)

### Environment Variables

Copy the example file and fill in real values:

```bash
cp .env.example .env
```

| Variable | Required | Description |
|---|---|---|
| `DB_PASSWORD` | Yes | PostgreSQL password (default: `devpassword`) |
| `JWT_SECRET` | Yes | At least 32 random characters |
| `DEEPSEEK_API_KEY` | Yes | DeepSeek API key for AI agents |
| `DEEPSEEK_BASE_URL` | No | Default: `https://api.deepseek.com` |
| `OPENAI_API_KEY` | No | OpenAI API key (fallback provider) |

---

## 2. Clone and Setup

```bash
git clone <repo-url> acm-agent
cd acm-agent
cp .env.example .env
# Edit .env with real values
```

---

## 3. Start Services

```bash
docker compose up -d
```

Three containers start:
- `acm-agent-db` -- PostgreSQL 16 with pgvector extension
- `acm-agent-backend` -- NestJS API on port 3000
- `acm-agent-frontend` -- Nginx serving the React SPA on port 5173

Wait for the health checks to pass (DB ~30s, backend ~60s).

---

## 4. Initialize Database

```bash
# Run all pending Prisma migrations
docker compose exec backend npx prisma migrate deploy

# Verify vector extension (auto-enabled by init.sql on first start)
docker compose exec postgres psql -U acm -d acm_agent -c "SELECT * FROM pg_extension WHERE extname='vector';"

# Create recommended indexes
docker compose exec postgres psql -U acm -d acm_agent <<SQL
CREATE INDEX IF NOT EXISTS idx_users_username ON "User"(username);
CREATE INDEX IF NOT EXISTS idx_users_role ON "User"(role);
CREATE INDEX IF NOT EXISTS idx_users_deleted_at ON "User"(deleted_at);
CREATE INDEX IF NOT EXISTS idx_platform_accounts_platform ON "PlatformAccount"(platform, "platformUid");
CREATE INDEX IF NOT EXISTS idx_practice_records_user ON "PracticeRecord"("userId", "submitTime");
CREATE INDEX IF NOT EXISTS idx_team_members_team ON "TeamMember"("teamId");
CREATE INDEX IF NOT EXISTS idx_team_members_user ON "TeamMember"("userId");
CREATE INDEX IF NOT EXISTS idx_problems_platform ON "Problem"(platform, "platformProblemId");
SQL

# Seed initial data (admin user, sample problems)
docker compose exec backend npx prisma db seed
```

---

## 5. Access URLs

| Service | URL |
|---|---|
| Frontend (SPA) | http://localhost:5173 |
| API (REST) | http://localhost:3000/api |
| Swagger Docs | http://localhost:3000/api/docs |
| Health Check | http://localhost:3000/health |

---

## 6. Cron Schedule

The `CronService` (via `@nestjs/schedule`) runs these jobs in the backend container (local timezone):

| Job | Schedule | Description |
|---|---|---|
| `syncObservedUsers` | Daily at 02:00 | Trigger crawler for all observed users |
| `generateProfiles` | Daily at 04:00 | Generate/update profiles for users with new records |
| `dailyPush` | Daily at 08:00 | Send daily training report via bot |
| `weeklyPush` | Monday at 08:00 | Send weekly team progress report via bot |

> Cron jobs are implemented in `backend/src/task/cron.service.ts`. They use optional DI tokens (`CRAWLER_TRIGGER`, `PROFILE_AGENT_TRIGGER`, `BOT_SERVICE`) -- jobs silently skip if the corresponding provider is not registered.

---

## 7. Backup

### Database Backup

```bash
# Full dump
docker compose exec postgres pg_dump -U acm -d acm_agent > backup_$(date +%Y%m%d_%H%M%S).sql

# Restore
docker compose exec -T postgres psql -U acm -d acm_agent < backup_20260613_120000.sql
```

### Data Volume Backup

```bash
docker run --rm -v acm-agent_pgdata:/data -v $(pwd):/backup alpine tar czf /backup/pgdata_backup.tar.gz -C /data .
```

---

## 8. Troubleshooting

### Container won't start

```bash
# Check all container logs
docker compose logs          # all services
docker compose logs backend  # backend only
docker compose logs postgres # DB only

# Check container status
docker compose ps
```

### Database connectivity

```bash
# Test connection from backend
docker compose exec backend npx prisma db push --force-reset  # WARNING: drops data

# Verify PostgreSQL is accepting connections
docker compose exec postgres pg_isready -U acm -d acm_agent
```

### API key issues (DeepSeek / OpenAI)

- Verify `.env` values are set: `cat .env | grep API_KEY`
- Check backend logs for authentication errors: `docker compose logs backend | grep -i "unauthorized\|api.key\|401"`
- Test the health endpoint: `curl http://localhost:3000/health`

### Prisma client out of sync

```bash
# Re-generate Prisma client after schema changes
docker compose exec backend npx prisma generate

# If migrations are stuck
docker compose exec backend npx prisma migrate resolve --rolled-back <migration_name>
```

### Port conflicts

- Frontend default: `5173` -> set `FRONTEND_PORT` or edit `docker-compose.yml`
- Backend default: `3000` -> update `docker-compose.yml` port mapping
- PostgreSQL default: `5432` -> update `docker-compose.yml` port mapping

### Reset everything

```bash
docker compose down -v     # stops containers and removes volumes (DB data lost!)
docker compose up -d       # fresh start
# Then re-run Step 4 (Init DB)
```
