# Stage 1: build the static bundle
FROM node:20-alpine AS build
WORKDIR /app

COPY package.json package-lock.json* ./
# npm ci needs a lockfile; fall back to npm install when it is absent.
RUN npm ci || npm install

COPY . .
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
