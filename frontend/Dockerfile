# FinSight frontend — standalone Next.js image (Phase 7)
FROM node:20-alpine AS builder
WORKDIR /web
COPY package.json ./
RUN npm install
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM node:20-alpine
WORKDIR /web
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN addgroup -S finsight && adduser -S finsight -G finsight
COPY --from=builder /web/.next/standalone ./
COPY --from=builder /web/.next/static ./.next/static
COPY --from=builder /web/public ./public
USER finsight
EXPOSE 3000
CMD ["node", "server.js"]
