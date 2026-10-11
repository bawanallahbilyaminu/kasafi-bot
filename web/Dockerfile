# Kasafi web app (React client + Express server) in one image.
# Build: docker compose build   (VITE_CLERK_PUBLISHABLE_KEY is baked into the web page at build time)

# ---- 1. build the React client
FROM node:22-bookworm-slim AS client
WORKDIR /app/client
COPY client/package*.json ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund
COPY client/ ./
ARG VITE_CLERK_PUBLISHABLE_KEY
ENV VITE_CLERK_PUBLISHABLE_KEY=$VITE_CLERK_PUBLISHABLE_KEY
RUN test -n "$VITE_CLERK_PUBLISHABLE_KEY" || (echo "VITE_CLERK_PUBLISHABLE_KEY build arg is missing" && exit 1)
RUN npm run build

# ---- 2. server dependencies (better-sqlite3 is native: build tools in case no prebuilt binary matches)
FROM node:22-bookworm-slim AS server-deps
WORKDIR /app/server
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
COPY server/package*.json ./
RUN npm ci --omit=dev --no-audit --no-fund || npm install --omit=dev --no-audit --no-fund

# ---- 3. runtime
FROM node:22-bookworm-slim
ENV NODE_ENV=production PORT=3001 DB_PATH=/data/kasafi-web.sqlite CLIENT_DIST=/app/client/dist
WORKDIR /app/server
COPY --from=server-deps /app/server/node_modules ./node_modules
COPY server/ ./
COPY --from=client /app/client/dist /app/client/dist
RUN mkdir -p /data && chown -R node:node /data
USER node
EXPOSE 3001
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3001/api/ping').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
CMD ["node", "src/index.js"]
