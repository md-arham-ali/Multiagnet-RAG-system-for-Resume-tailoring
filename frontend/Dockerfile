# Frontend image, built in two stages. Decisions: context/final_docker_descision.md (section 5).
# Only this image publishes a port; the backend is reached through nginx's /api proxy.

# =============================================================================
# Stage 1: build the static bundle (node is used here and thrown away)
# =============================================================================
FROM node:20-alpine AS build
WORKDIR /app

# Layer 1: the dependency manifests ONLY. `npm ci` installs exactly what package-lock.json says
# (and fails if the lock and package.json disagree), so the build is reproducible. This layer is
# cached until one of the two files changes.
COPY package.json package-lock.json ./
RUN npm ci

# Layer 2: the sources. .dockerignore keeps node_modules, dist and the notes out.
COPY . .

# Layer 3: build into /app/dist.
RUN npm run build

# =============================================================================
# Stage 2: serve it with nginx. Nothing from stage 1 comes along except /app/dist.
# =============================================================================
FROM nginx:alpine

# Layer 4: the built site.
COPY --from=build /app/dist /usr/share/nginx/html

# Layer 5: the nginx config as a TEMPLATE. At start the image fills in ${BACKEND_URL} and writes
# /etc/nginx/conf.d/default.conf, so the backend address is a setting and not a rebuild.
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Layer 6: the default backend address, for the backend running on the host (`scripts/dev.py up --docker`).
# Compose overrides it with http://backend:8000; another machine gets its own URL.
ENV BACKEND_URL=http://host.docker.internal:8000
