# Steward web — production image (Next.js standalone output)
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:22-slim AS build
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
# Demo mode is never enabled in this image unless explicitly requested at build time.
ARG NEXT_PUBLIC_DEMO_MODE=false
ENV NEXT_PUBLIC_DEMO_MODE=$NEXT_PUBLIC_DEMO_MODE
# Rewrites are resolved at build time: the API's address on the private network.
ARG API_INTERNAL_URL=http://api:8000
ENV API_INTERNAL_URL=$API_INTERNAL_URL
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
RUN groupadd --system web && useradd --system --gid web web
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER web
EXPOSE 3000
CMD ["node", "server.js"]
