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

## 4. Deploy on the VPS (Ubuntu, Node 20+)
```bash
git clone https://github.com/bawanallahbilyaminu/kasafi-bot.git /opt/kasafi && cd /opt/kasafi/web
cd client && cp .env.example .env && nano .env && npm ci || npm install && npm run build
cd ../server && cp .env.example .env && nano .env && npm ci || npm install
sudo npm i -g pm2 && pm2 start "npm start" --name kasafi-web && pm2 save && pm2 startup
```
nginx (`/etc/nginx/sites-available/kasafi`), then `sudo ln -s` it into `sites-enabled`, `sudo nginx -t && sudo systemctl reload nginx`:
```nginx
server {
    server_name kasafi.halalnumeriq.com.ng;          # your subdomain (A record -> VPS IP)
    client_max_body_size 10m;                        # voice notes
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;                         # live progress (Server-Sent Events)
        proxy_read_timeout 300s;
    }
}
```
HTTPS (the microphone only works on https): `sudo certbot --nginx -d kasafi.halalnumeriq.com.ng`

Update later: `cd /opt/kasafi && git pull && cd web/client && npm run build && pm2 restart kasafi-web`

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
