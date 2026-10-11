# Kasafi AI — web app

React (Vite) + Tailwind + Redux Toolkit front end, Express back end, Clerk sign-in (Google and other social logins),
chat history in SQLite. The models do not run here: the Express server forwards each question to the **Kasafi
engine** (N-ATLaS + Hausa-ASR + Hausa TTS) on the GPU machine (laptop or Colab) and streams its progress back.

```
browser ──► nginx (VPS, https://kasafi.<your-domain>) ──► Express :3001 ──► Kasafi engine :8080 /api (laptop/Colab)
                     serves client/dist                    Clerk auth           via Cloudflare tunnel or Tailscale
                                                           SQLite history
```

## 1. Engine side (laptop or Colab)
In the engine's `.env` add a long random key and restart the bot:
```
ENGINE_API_KEY=<long random string>
```
`python -m app.run_all` now also serves `/api` on port 8080 (next to the WhatsApp webhook).
Expose it with one of these:
- **Tailscale (stable, recommended for the laptop):** install Tailscale on the laptop and the VPS, sign in to
  both with the same account. `ENGINE_URL=http://<laptop-tailscale-ip>:8080`. Allow port 8080 on the laptop's
  firewall for the Tailscale network.
- **Cloudflare quick tunnel:** `cloudflared tunnel --url http://localhost:8080` (on Colab the notebook uses port 8765, because Colab's own Jupyter server is on 8080) and use the printed
  `https://….trycloudflare.com` as `ENGINE_URL`. The URL changes when the tunnel restarts. On Colab, cell 7 opens
  the tunnel and prints the URL when the `ENGINE_API_KEY` secret is set.

## 2. Clerk
1. https://dashboard.clerk.com → create an application → enable **Google** (and any others you want).
2. Copy the **publishable key** (`pk_…`) and **secret key** (`sk_…`).
3. Development keys work on any domain straight away (a small "development mode" badge shows). For production
   keys, add your domain in Clerk and create the DNS records it lists.

## 3. Local run (to try it)
```bash
cd web/server && cp .env.example .env   # fill in keys, ENGINE_URL, ENGINE_API_KEY
npm install && npm run dev               # http://localhost:3001
cd ../client && cp .env.example .env     # VITE_CLERK_PUBLISHABLE_KEY
npm install && npm run dev               # http://localhost:5173 (proxies /api to :3001)
```

## 4. Deploy on the VPS (Docker, one command from the laptop)
Files: `Dockerfile`, `docker-compose.yml`, `deploy/vps-deploy.sh` (runs on the VPS), `deploy/push.ps1` (Windows) or
`deploy/push.sh` (Git Bash/Linux).

The app listens on **127.0.0.1:52723** on the VPS (K-A-S-A-F on a phone keypad; only the server itself can reach
it). If that port is taken, the script moves to the next free one and remembers it.

```powershell
# once: an A record  ai.kasafi.halalnumeriq.com.ng -> your VPS IP   (at your DNS provider)
$env:KASAFI_VPS = "root@YOUR_VPS_IP"
git add -A; git commit -m "..."          # only committed files are deployed
.\web\deploy\push.ps1 -Check              # shows who owns ports 80/443, DNS, settings; changes nothing
.\web\deploy\push.ps1                     # first run creates /opt/kasafi-web/web.env on the VPS and stops
ssh $env:KASAFI_VPS "sudo nano /opt/kasafi-web/web.env"   # fill in Clerk keys, ENGINE_URL/KEY, ADMIN_EMAILS
.\web\deploy\push.ps1                     # build, start, health-check, publish the domain
.\web\deploy\push.ps1 -EngineUrl https://xxxx.trycloudflare.com   # after each Colab restart (no rebuild)
.\web\deploy\push.ps1 -Logs
```

How the domain is published depends on what already serves ports 80/443 (the script detects it):
- **mailcow's nginx**: writes `data/conf/nginx/kasafi-web.conf` in the mailcow folder, joins mailcow's Docker
  network, tests the config (removes it if mailcow's nginx rejects it), and, after asking you, adds the domain to
  mailcow's `ADDITIONAL_SAN` so mailcow's Let's Encrypt certificate covers it (mailcow.conf is backed up first).
  The upstream is resolved per request, so mailcow's nginx still starts if the Kasafi container is down.
- **nginx on the server**: writes a site in `/etc/nginx/sites-available/` and runs certbot (`LETSENCRYPT_EMAIL`).
- **another proxy (Traefik, Nginx Proxy Manager, Caddy…)**: prints the target to add there (`http://127.0.0.1:52723`).

Data (chat history, profiles, voice replies) lives in the Docker volume `kasafi-web-data` and survives redeploys.

## Admin page (/admin)
Put your sign-in email in `web/server/.env`: `ADMIN_EMAILS=you@example.com` (comma-separate several). After signing
in, an **Admin** link appears in the sidebar. It shows every interaction from Telegram, WhatsApp and the web (from the
engine's log): headline numbers, filters (problems, unreviewed, 👎, voice, channel, search), and for each one what was
heard, how N-ATLaS understood it, the facts it was given, the answer, why a check stepped in, and timings. Mark each
**OK / Issue / Fixed** with a note; marks are stored in the engine's log.

## What it stores
- `profiles`: Clerk user id, name, organisation, email
- `sessions` and `messages`: each user's chats (the sidebar), answers, feedback
- `data/audio/`: cached voice replies

The engine also logs each question in its interaction log (channel `web`, salted user hash) with the name and
organisation, so `/stats`, `/recent` and `export_evidence.py` include web users.
