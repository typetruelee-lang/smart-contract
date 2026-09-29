# 로컬 개발 블록체인 (Hardhat, chainId 31337) — 비용 없음, 재시작 시 초기화됨
FROM node:22-alpine
WORKDIR /chain
COPY contracts/package.json contracts/package-lock.json ./
RUN --mount=type=secret,id=extra_ca \
    if [ -s /run/secrets/extra_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/extra_ca; fi; \
    npm ci --no-audit --no-fund
COPY contracts/hardhat.config.cjs ./
EXPOSE 8545
CMD ["npx", "hardhat", "--config", "hardhat.config.cjs", "node", "--hostname", "0.0.0.0", "--port", "8545"]
