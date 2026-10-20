FROM node:24.20.0-alpine3.24 AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

FROM node:24.20.0-alpine3.24 AS build

WORKDIR /app

COPY --from=dependencies --chown=node:node /app/node_modules ./node_modules
COPY --chown=node:node . .
COPY --from=contracts /examples /contracts/examples
RUN chown node:node /app

USER node

ENV VITE_API_BASE_URL=""
ARG VITE_DIAGNOSTICS_ENABLED=false
ENV VITE_DIAGNOSTICS_ENABLED=${VITE_DIAGNOSTICS_ENABLED}
ARG VITE_AIOT_ENABLED=false
ENV VITE_AIOT_ENABLED=${VITE_AIOT_ENABLED}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.31-alpine3.24@sha256:884e0b7f42f303641b0f4e78755aea647521dca0b89ca3be7992ad78b5c07434 AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf

USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
