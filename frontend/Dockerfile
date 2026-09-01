# Multi-stage build for the React frontend.
# Stage 1: build the Vite production bundle.
# Stage 2: serve it with Nginx on port 80.

# ─── Stage 1: Builder ──────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (better layer caching)
COPY package*.json ./
RUN npm install

# Copy source and build
COPY . .
RUN npm run build

# ─── Stage 2: Runner ───────────────────────────────────────
FROM nginx:1.25-alpine

# Copy the built static files into Nginx's web root
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: serve SPA + proxy /api to the backend container
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
