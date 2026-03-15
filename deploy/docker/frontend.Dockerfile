# =============================================================================
# FinMind Frontend — Production Multi-Stage Dockerfile
# =============================================================================
# Stage 1: Install deps + build the Vite/React app
# Stage 2: Serve static assets via hardened nginx
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1 — Builder
# ---------------------------------------------------------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Accept build-time API URL (baked into the JS bundle by Vite)
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=${VITE_API_URL}

# Install dependencies first (layer cache optimisation)
COPY app/package.json app/package-lock.json ./
RUN npm ci --ignore-scripts

# Copy source and build
COPY app/ .
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — Production nginx
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

LABEL org.opencontainers.image.title="finmind-frontend" \
      org.opencontainers.image.description="FinMind frontend SPA served by nginx" \
      org.opencontainers.image.source="https://github.com/rohitdash08/FinMind"

# Remove default nginx content
RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

# Copy our production nginx configuration
COPY deploy/docker/nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Create cache and temp directories with correct permissions for non-root
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown nginx:nginx /var/run/nginx.pid

EXPOSE 80

# Health check — verify nginx is serving content
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO /dev/null http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
