FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./

RUN if [ -f package-lock.json ]; then \
      npm ci --verbose --no-audit --no-fund; \
    else \
      npm install --verbose --no-audit --no-fund; \
    fi

COPY . .

RUN npm run build

FROM nginx:1.27-alpine

RUN apk add --no-cache nodejs npm
WORKDIR /app

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
COPY --from=build /app /app

EXPOSE 80
