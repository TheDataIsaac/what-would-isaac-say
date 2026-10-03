# Deploying on a small server

This guide puts the assistant on one cheap Linux server (a VPS) with automatic HTTPS. The server
can host several apps, so the setup has two parts:

* **The shared proxy** (`deploy/proxy`). One Caddy container owns ports 80 and 443, gets HTTPS
  certificates and routes each site name to the right app.
* **The app** (`docker-compose.prod.yml`). It publishes no public ports. The proxy reaches its web
  interface over a shared Docker network called `web`, and the API listens on the server's loopback
  address only, so the admin endpoints are never public. The Admin tab is hidden
  (`ENABLE_ADMIN_TAB=0`).

## Before you start: protect the OpenAI bill

Anyone who finds the site can spend your money, so set limits first.

1. In the OpenAI dashboard, set a **monthly spend limit** you are comfortable losing.
2. The app has its own caps: `RATE_LIMIT_PER_MINUTE` (per visitor, default 20) and
   `DAILY_QUESTION_LIMIT` (all visitors together, default 300, `0` turns it off). At about $0.0008
   a question, 300 questions a day is under $0.25.

## 1. Create the server

Any provider works. You need Ubuntu 24.04, at least 2 GB of RAM (4 GB leaves room for other apps)
and a public IPv4 address. Add your SSH public key when creating it, and note the IP address.

## 2. Prepare it

```bash
ssh root@SERVER_IP

# Docker and a basic firewall (SSH, HTTP, HTTPS only)
curl -fsSL https://get.docker.com | sh
apt-get install -y ufw rsync
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable
```

## 3. Start the shared proxy (once per server)

Copy `deploy/proxy` to `/opt/proxy` on the server. Then add a site file for this app. Use your
domain name, or `<ip with dashes>.sslip.io`, a free name that points at that address (for
`203.0.113.7` that is `203-0-113-7.sslip.io`):

```bash
cd /opt/proxy
sed 's/203-0-113-7.sslip.io/YOUR-ADDRESS/' isaac-says.caddy.example | sed '1,2d' > sites/isaac-says.caddy
docker compose up -d
```

## 4. Copy the app and configure it

Copy the project to `/opt/isaac-says` (for example `git ls-files -z | tar --null -T - -cf - | ssh
root@SERVER_IP 'tar -xf - -C /opt/isaac-says'`, which skips ignored files such as `.env`).

Create `/opt/isaac-says/.env` on the server (it stays there and is never committed) with mode 600:

```
OPENAI_API_KEY=...
ADMIN_API_KEY=...        # a long random string: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
DAILY_QUESTION_LIMIT=300
```

## 5. Start it

```bash
cd /opt/isaac-says
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps        # both services should be healthy
```

The first start builds the search index (about 20 seconds, under a cent). Then open
`https://YOUR-ADDRESS`. The certificate can take a minute to appear the first time.

## Adding another app later

Give its web container a unique `container_name`, attach it to the external `web` network, copy
`isaac-says.caddy.example` to `/opt/proxy/sites/<app>.caddy` with a new address and container name,
and reload Caddy:

```bash
docker compose -f /opt/proxy/docker-compose.yml exec caddy caddy reload --config /etc/caddy/Caddyfile
```

Cap each app's memory in its compose file (`mem_limit`) so one app cannot starve the others.

## Answering saved questions (admin)

The admin endpoints are not public. Open a tunnel from your machine, then use the API's built-in
docs page:

```bash
ssh -L 8000:127.0.0.1:8000 root@SERVER_IP
# then browse to http://localhost:8000/docs and press Authorize with your ADMIN_API_KEY
```

## Operating it

```bash
docker compose -f docker-compose.prod.yml logs -f --tail 100
docker compose -f docker-compose.prod.yml exec api isaac-says purge-threads   # delete idle conversations
docker compose -f docker-compose.prod.yml up -d --build                       # deploy a new version
```

Back up the `app-data` volume (it holds the database, conversations and search index) if you care
about the saved questions. Stopping the server loses nothing; deleting the volume does.

## Limits of this setup

One server, no redundancy, SQLite instead of a networked database, and an in-memory rate limiter
that resets on restart. That is right for a demo, and `docs/ARCHITECTURE.md` describes what scaling
out would need.
