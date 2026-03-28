FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm config set strict-ssl false
RUN npm install --include=dev
RUN npm install -g typescript
COPY . .
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache gettext
COPY --from=build /app/dist /usr/share/nginx/html
ENV MM_LOGIN_REDIRECT_MODE=off
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 3000
CMD ["/bin/sh", "-c", "envsubst '$$MM_LOGIN_REDIRECT_MODE' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
