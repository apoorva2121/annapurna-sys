# syntax=docker/dockerfile:1
# Frontend image, two useful endpoints:
#   --target dev  → vite dev server, used by docker-compose.yml
#   (default)     → static bundle served by nginx, which is what ADR 0005 ships to Cloudflare
#                   Pages or any container host.

# ---------------------------------------------------------------- deps
FROM node:20-alpine AS deps
WORKDIR /app
# package-lock.json is copied deliberately: `npm ci` refuses to run without it, and refusing is
# the point — a dev container must install the locked tree, never resolve a fresh one.
COPY package.json package-lock.json ./
RUN npm ci

# ---------------------------------------------------------------- dev (compose)
FROM deps AS dev
COPY . .
EXPOSE 5173
# --host binds 0.0.0.0 so the port is reachable from the Windows host, not just from inside the
# container. Compose repeats this command; it is here so the stage is runnable on its own.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---------------------------------------------------------------- build
FROM deps AS build
COPY . .
# `npm run build` = tsc -b && vite build. Type errors fail the image, not just CI.
RUN npm run build

# ---------------------------------------------------------------- runtime
FROM nginx:alpine AS runtime

# React Router owns the URL space: every path that is not a real file has to return index.html,
# or a refresh on /orders/42 is a 404. Written inline so the deploy needs no sidecar config file.
RUN printf '%s\n' \
    'server {' \
    '  listen 80;' \
    '  server_name _;' \
    '  root /usr/share/nginx/html;' \
    '  index index.html;' \
    '  location /assets/ {' \
    '    expires 1y;' \
    '    add_header Cache-Control "public, immutable";' \
    '  }' \
    '  location / {' \
    '    try_files $uri $uri/ /index.html;' \
    '  }' \
    '}' \
    > /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --spider http://127.0.0.1/ || exit 1
