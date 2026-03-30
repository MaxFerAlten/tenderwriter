FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm config set strict-ssl false
RUN npm install --include=dev
RUN npm install -g typescript
COPY . .
ARG VITE_AUTH_MODE=legacy
ARG VITE_KC_URL=http://localhost:8180
ARG VITE_KC_REALM=tenderwriter
ARG VITE_KC_CLIENT_ID=tw-frontend
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE
ENV VITE_KC_URL=$VITE_KC_URL
ENV VITE_KC_REALM=$VITE_KC_REALM
ENV VITE_KC_CLIENT_ID=$VITE_KC_CLIENT_ID
RUN npm run build

FROM nginx:alpine
RUN apk add --no-cache gettext
COPY --from=build /app/dist /usr/share/nginx/html
ENV MM_LOGIN_REDIRECT_MODE=off
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
EXPOSE 3000
CMD ["/bin/sh", "-c", "envsubst '$$MM_LOGIN_REDIRECT_MODE' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
