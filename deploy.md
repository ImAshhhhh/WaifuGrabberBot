# 🚀 Deploying WaifuGrabberBot to a VPS

This guide covers a production deployment on a Linux VPS (Ubuntu 22.04 / Debian 12) using **Docker Compose** + **Nginx** (for HTTPS webhook) + **systemd** (for restart-on-failure).

Estimated time: **20 minutes**.

---

## 0. Prerequisites

- A VPS with at least **2 vCPU / 2 GB RAM** (Hetzner CX22, Contabo Cloud VPS S, DigitalOcean $12 droplet — all fine)
- Ubuntu 22.04+ or Debian 12+
- A domain name (or subdomain) pointing to your VPS IP — e.g. `bot.yourdomain.com`
- A bot token from [@BotFather](https://t.me/BotFather)

For 10k concurrent users, scale up to **4 vCPU / 8 GB RAM** and bump Postgres `max_connections` to 200+.

---

## 1. Initial Server Setup

SSH into your VPS as root:

```bash
ssh root@your.vps.ip

# Update system
apt update && apt upgrade -y

# Install Docker + Docker Compose
curl -fsSL https://get.docker.com | sh
apt install -y git nginx certbot python3-certbot-nginx ufw

# Firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

## 2. Clone the Repo

```bash
cd /opt
git clone https://github.com/YOUR_USERNAME/WaifuGrabberBot.git
cd WaifuGrabberBot
```

---

## 3. Configure `.env`

```bash
cp .env.example .env
nano .env
```

Set these critical values:

```ini
BOT_TOKEN=123456:ABC-your-actual-token-from-botfather
BOT_USERNAME=YourBotUsername

DATABASE_URL=postgresql://waifu:waifu_pass@postgres:5432/waifugrabber
REDIS_URL=redis://redis:6379/0

USE_WEBHOOK=true
WEBHOOK_URL=https://bot.yourdomain.com/bot
WEBHOOK_PATH=/bot
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8443

SPAWN_MSG_INTERVAL=100
SPAWN_TIME_FLOOR=300
SPAWN_CLAIM_WINDOW=90
GUESS_COOLDOWN=3
TRADE_WINDOW=60

OWNER_ID=123456789   # your Telegram user ID — get it from @userinfobot
LOG_LEVEL=INFO
```

> 💡 Note: when running inside Docker Compose, use the service names `postgres` and `redis` as hostnames (not `localhost`).

---

## 4. Get an SSL Certificate

```bash
# Stop nginx temporarily (port 80 free for certbot standalone)
systemctl stop nginx

# Get cert
certbot certonly --standalone -d bot.yourdomain.com --agree-tos -m you@yourdomain.com

# Start nginx
systemctl start nginx
```

---

## 5. Configure Nginx as Reverse Proxy

Create `/etc/nginx/sites-available/waifugrabber`:

```nginx
server {
    listen 80;
    server_name bot.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name bot.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/bot.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.yourdomain.com/privkey.pem;

    # Telegram webhook — only allow Telegram's IPs (optional hardening)
    location /bot {
        proxy_pass http://127.0.0.1:8443;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Telegram sends a secret token in this header
        proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
    }
}
```

Enable + reload:

```bash
ln -s /etc/nginx/sites-available/waifugrabber /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

Set up auto-renewal:

```bash
echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx'" | crontab -
```

---

## 6. Build + Launch with Docker Compose

```bash
cd /opt/WaifuGrabberBot
docker compose build
docker compose up -d
```

Check status:

```bash
docker compose ps
docker compose logs -f bot
```

You should see:

```
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Starting WaifuGrabberBot v1.0.0
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Postgres pool ready
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Redis ready
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Loaded 508 characters into memory
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Webhook set: https://bot.yourdomain.com/bot
waifugrabber-bot    | 2026-07-21 10:00:00 | INFO    | waifugrabber | Listening on 0.0.0.0:8443
```

---

## 7. Initialize the Database (one-time)

Run the schema + import the character CSV:

```bash
docker compose exec bot python -m bot.db.init_db
```

Output:

```
✓ Schema applied
✓ Imported 508 characters
```

---

## 8. Set the Webhook with Telegram

After Docker is up and Nginx is proxying, Telegram needs to know where to send updates. The bot does this automatically on startup (see `bot/__main__.py`), but you can verify:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo" | jq
```

The response should show `"url": "https://bot.yourdomain.com/bot"` and `"last_error_message": null`.

---

## 9. (Alternative) Run with systemd Instead of Docker

If you prefer bare-metal:

```bash
# Install deps
apt install -y python3.12 python3.12-venv postgresql redis-server

# Postgres setup
sudo -u postgres psql <<EOF
CREATE USER waifu WITH PASSWORD 'waifu_pass';
CREATE DATABASE waifugrabber OWNER waifu;
GRANT ALL PRIVILEGES ON DATABASE waifugrabber TO waifu;
EOF

# Redis
systemctl enable --now redis-server

# App
cd /opt/WaifuGrabberBot
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt

# Update .env: DATABASE_URL=postgresql://waifu:waifu_pass@localhost:5432/waifugrabber
#             REDIS_URL=redis://localhost:6379/0
python -m bot.db.init_db
```

Create `/etc/systemd/system/waifugrabber.service`:

```ini
[Unit]
Description=WaifuGrabberBot
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/WaifuGrabberBot
EnvironmentFile=/opt/WaifuGrabberBot/.env
ExecStart=/opt/WaifuGrabberBot/.venv/bin/python -m bot
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

Enable + start:

```bash
systemctl daemon-reload
systemctl enable --now waifugrabber
journalctl -u waifugrabber -f
```

---

## 10. Test the Bot

1. Open Telegram, search for your bot's username.
2. Send `/start` — should reply with the welcome Rich Message.
3. Add the bot to a test group as an **admin** (so it can read messages).
4. Send ~100 messages in the group → a character spawns.
5. Send `/guess <name>` → claim it.
6. Try `/collection`, `/topusers`, `/ctop`, `/stats`.

---

## 11. Scaling for 10k Concurrent Users

| Layer | Default | 10k users |
|---|---|---|
| Postgres `max_connections` | 100 | 300+ |
| Postgres `shared_buffers` | 128 MB | 2 GB |
| Redis `maxmemory` | 512 MB | 2 GB |
| Bot container CPU | 1 | 4+ |
| Bot container RAM | 1 GB | 4 GB |
| `PG_POOL_MAX` in `.env` | 30 | 100 |
| Webhook secret rotation | — | Monthly |

### Horizontal scaling

For >50k users, run **multiple bot workers** behind a load balancer with **sticky sessions** disabled (Telegram webhooks are stateless). Use a shared Redis for spawn state (already done) and Postgres for persistence (already done).

---

## 12. Updating the Bot

```bash
cd /opt/WaifuGrabberBot
git pull
docker compose build
docker compose up -d
```

Zero downtime isn't critical for a waifu bot — drops in <2s are fine. If you need zero-downtime, run two instances and use blue/green deploy via Nginx upstream switching.

---

## 13. Backup

Daily Postgres backup:

```bash
# Add to crontab
0 4 * * * docker compose -f /opt/WaifuGrabberBot/docker-compose.yml exec -T postgres pg_dump -U waifu waifugrabber | gzip > /backup/waifu_$(date +\%F).sql.gz
```

Keep 30 days:

```bash
find /backup -name "waifu_*.sql.gz" -mtime +30 -delete
```

---

## 14. Troubleshooting

| Symptom | Fix |
|---|---|
| Bot doesn't respond | `docker compose logs bot` — check for token errors |
| `/guess` always says "no active spawn" | Spawn counter not incrementing — check Redis: `docker compose exec redis redis-cli MONITOR` |
| Webhook returns 404 | Nginx location path doesn't match `WEBHOOK_PATH` in `.env` |
| `relation "characters" does not exist` | You forgot to run `python -m bot.db.init_db` |
| Bot can't send photos | Image URL is dead — replace `image_url` column in `data/waifu_characters.csv` with your own hosted images |
| Telegram flood ban | Reduce `/guess` reply rate — ensure Ephemeral Messages are working |

---

## 15. First Run Checklist

- [ ] VPS provisioned
- [ ] Domain DNS pointing to VPS
- [ ] SSL cert obtained via certbot
- [ ] Nginx reverse proxy configured
- [ ] `.env` filled in (BOT_TOKEN, OWNER_ID, WEBHOOK_URL)
- [ ] `docker compose up -d` succeeds
- [ ] `docker compose exec bot python -m bot.db.init_db` runs cleanly
- [ ] Bot replies to `/start` in DM
- [ ] Bot spawns a character after 100 group messages
- [ ] `/guess` works and adds to `/collection`
- [ ] Webhook info endpoint shows no errors

🎉 You're live. Add the bot to your group, share the link, and watch the chaos unfold.
