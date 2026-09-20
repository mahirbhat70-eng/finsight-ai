# Deploy — Track A: Ubuntu VM + compose + Caddy (Phase 7)

Target: a 2GB VM (Lightsail / EC2 t3.small), reproducible from clean in
under 30 minutes.

## 1. Provision

1. Create the VM (Ubuntu 24.04), open 80/443 (and 22 for ops).
2. DNS A record: `finsight.example.com -> VM_IP`.
3. Bootstrap: `bash infra/bootstrap.sh` (docker install, ufw, secrets
   template) — or manually:
   ```bash
   curl -fsSL https://get.docker.com | sh
   sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw enable
   ```

## 2. Secrets

`data/../.env` on the VM (never committed):

```
DOMAIN=finsight.example.com
DB_PASSWORD=<random>
JWT_SECRET=<32+ random chars>
GEMINI_API_KEY=<key>
LLM_PROVIDER=gemini
EMBEDDING_PROVIDER=gemini
```

## 3. Ship

```bash
# on the VM
git clone <repo> && cd finsight-ai
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml exec backend \
    python /app/../scripts/seed.py   # demo data only, or upload real filings
curl https://$DOMAIN/api/v1/health   # {"status":"ok","db":"ok","redis":"ok"}
```

Caddy obtains TLS certificates automatically on first request.

## 4. Backups + restore drill

Cron on the VM:

```
30 2 * * * docker compose -f /opt/finsight/docker-compose.prod.yml exec -T db \
    pg_dump -U finsight finsight | gzip > /backups/finsight-$(date +\%F).sql.gz
```

Restore drill (executed once and documented here, per the playbook):

```bash
gunzip -c /backups/finsight-YYYY-MM-DD.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U finsight finsight
curl -s https://$DOMAIN/api/v1/companies | head   # data is back
```

## 5. CI/CD

GitHub Actions: on tag `v*` — build images, push to GHCR, SSH pull +
`docker compose up -d`, environment protection with manual approval.

## Track B (docs only)

ECS Fargate + RDS (pgvector via `aws:pgvector` engine or self-managed) +
ALB + ECR images; sketch in `docs/aws-alternative.md` — kept on paper:
VM+compose is the right TCO for a solo product; know the ECS path for the
interview.
