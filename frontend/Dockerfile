# ARGUS FloodOps console (Next.js standalone). Build context: frontend/.
FROM node:22-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN npm ci
COPY . .
ENV ARGUS_STANDALONE=1 NEXT_TELEMETRY_DISABLED=1
ARG ARGUS_API_URL=http://backend:8000
ENV ARGUS_API_URL=$ARGUS_API_URL
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=3000 HOSTNAME=0.0.0.0
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
COPY --from=build /app/public ./public
USER node
EXPOSE 3000
CMD ["node", "server.js"]
