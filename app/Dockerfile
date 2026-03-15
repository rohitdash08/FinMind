# Frontend Dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci || npm install
COPY . .
ARG VITE_API_URL=""
ENV VITE_API_URL=${VITE_API_URL}
RUN npm run build

FROM nginx:alpine
# SPA nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf
# Built frontend assets
COPY --from=builder /app/dist /usr/share/nginx/html
# Runtime config entrypoint (can override API URL at container start)
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh
EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]
