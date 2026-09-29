# Deploy OmniOps on one Ubuntu VM

This profile runs Caddy on ports 80 and 443, Next.js, FastAPI, a background worker, PostgreSQL with pgvector, and the authenticated sandbox runner. Only Caddy publishes public ports. Use a fresh Ubuntu VM with enough memory and disk for the Docker images, PostgreSQL, and uploaded files.

## Install Docker and clone

Run as a sudo-capable user.

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git openssl ufw
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
git clone https://github.com/sohaib-0897/OmniOps.git omniops
cd omniops
```

## Configure secrets and public IP

Use hexadecimal secrets so the password needs no URL escaping. This command does not print them. Replace `PUBLIC_IP` with the VM's actual public IPv4 address. Keep `.env` private; it is ignored by Git. Provider keys are optional, but provider-dependent features need valid keys.

```bash
cp .env.example .env
chmod 600 .env
PUBLIC_IP=YOUR_PUBLIC_IPV4
DB_PASSWORD=$(openssl rand -hex 32)
JWT_SECRET=$(openssl rand -hex 32)
RUNNER_TOKEN=$(openssl rand -hex 32)
cat >> .env <<EOF
POSTGRES_PASSWORD=$DB_PASSWORD
DATABASE_URL=postgresql+asyncpg://omniops:$DB_PASSWORD@postgres:5432/omniops_db
SECRET_KEY=$JWT_SECRET
SANDBOX_RUNNER_TOKEN=$RUNNER_TOKEN
CORS_ORIGINS=["http://$PUBLIC_IP"]
ALLOW_INSECURE_HTTP=true
COOKIE_SECURE=false
EOF
unset DB_PASSWORD JWT_SECRET RUNNER_TOKEN
```

The last definitions in `.env` take precedence for Compose. Set `OPENAI_API_KEY` and/or `GEMINI_API_KEY` there if needed. `NEXT_PUBLIC_API_URL` stays `/api/v1`; the browser calls the same origin. Avoid inserting spaces around Compose variable values.

## Build and start

Build the backend first because the sandbox and runner images inherit it. The one-shot `migrate` service upgrades PostgreSQL before backend and worker start. Do not use `down -v` during normal operations.

```bash
docker compose -f docker-compose.ubuntu.yml config --quiet
docker compose -f docker-compose.ubuntu.yml build backend frontend
docker compose -f docker-compose.ubuntu.yml build sandbox-image sandbox-runner
docker compose -f docker-compose.ubuntu.yml up -d
docker compose -f docker-compose.ubuntu.yml run --rm migrate alembic -c alembic.ini current
docker compose -f docker-compose.ubuntu.yml ps -a
docker compose -f docker-compose.ubuntu.yml logs --tail=100 backend worker sandbox-runner caddy migrate
curl -i "http://$PUBLIC_IP/api/v1/health"
curl -i "http://$PUBLIC_IP/api/v1/readiness"
curl -I "http://$PUBLIC_IP/"
docker compose -f docker-compose.ubuntu.yml exec -T postgres psql -U omniops -d omniops_db -c "SELECT extname FROM pg_extension WHERE extname='vector';"
```

`readiness` should report database, pgvector, migrations, and sandbox runner as ready. The `migrate` container exits successfully after migration; this is expected. To apply migrations manually before starting application services:

```bash
docker compose -f docker-compose.ubuntu.yml up -d postgres
docker compose -f docker-compose.ubuntu.yml run --rm migrate
docker compose -f docker-compose.ubuntu.yml up -d
```

## Firewall

Configure the VM provider firewall to permit inbound TCP 22, 80, and 443. On the VM:

```bash
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable
sudo ufw status verbose
```

Do not open 3000, 8000, 5432, or 9100. Docker publishes only Caddy ports 80 and 443. The Docker socket grants the runner powerful host control; keep SSH access restricted, protect `.env`, patch the VM, and prefer a separate/rootless runner host when available.

## Operations

```bash
docker compose -f docker-compose.ubuntu.yml ps -a
docker compose -f docker-compose.ubuntu.yml logs -f --tail=100
docker compose -f docker-compose.ubuntu.yml stop
docker compose -f docker-compose.ubuntu.yml start
docker compose -f docker-compose.ubuntu.yml down
git pull --ff-only
docker compose -f docker-compose.ubuntu.yml build backend frontend
docker compose -f docker-compose.ubuntu.yml build sandbox-image sandbox-runner
docker compose -f docker-compose.ubuntu.yml up -d
```

Back up PostgreSQL and application storage. The dump command creates a local file; move it to secure off-VM storage. Keep a copy of `.env` in a separate secret store.

```bash
mkdir -p backups
docker compose -f docker-compose.ubuntu.yml exec -T postgres pg_dump -U omniops -d omniops_db -Fc > "backups/omniops-$(date +%F).dump"
docker run --rm -v omniops-ubuntu_app_storage:/data:ro -v "$PWD/backups:/backup" alpine tar -czf /backup/app-storage-$(date +%F).tgz -C /data .
```

## Production hostname and HTTPS

Use a hostname whose A record points to the VM. A free DuckDNS hostname is supported; for example, `omniops.duckdns.org` should resolve to the VM's public IPv4 address before Caddy starts requesting a certificate. Allow inbound TCP 80 and 443 at the cloud firewall and with UFW. Caddy listens for the hostname and obtains/renews a publicly trusted certificate automatically. TCP 443 is published; UDP 443 for HTTP/3 is optional and is not required for HTTPS.

Set the production transport values in `.env` (do not commit the file):

```dotenv
CORS_ORIGINS=["https://omniops.duckdns.org"]
ALLOW_INSECURE_HTTP=false
COOKIE_SECURE=true
PASSWORD_RESET_BASE_URL=https://omniops.duckdns.org
```

Keep `COOKIE_SAMESITE=lax`, SMTP configuration, and Caddy's named `caddy_data` and `caddy_config` volumes. Recreate backend and worker to apply environment changes, and Caddy to apply the hostname and port mapping. PostgreSQL and the frontend do not need recreation for these changes. The API path remains `/api/v1`; no frontend rebuild is needed. Caddy redirects hostname HTTP to HTTPS automatically and redirects raw-IP HTTP to the canonical hostname.

## HTTP security limit

The production hostname should be used for browser access. Caddy redirects hostname HTTP to HTTPS. App rate limits and sandbox isolation remain active. PostgreSQL, backend, Ollama, and the runner have no published host ports.
