# 계약하자 웹 (web 런타임) — 빌드 후 nginx 로 정적 파일 서빙 + /api 프록시
FROM node:22-alpine AS build
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npx tsc -b && npx vite build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY frontend/security-headers.inc /etc/nginx/conf.d/security-headers.inc
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 80
