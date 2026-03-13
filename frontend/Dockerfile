FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm config set strict-ssl false
RUN npm install --include=dev
RUN npm install -g typescript
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY <<EOF /etc/nginx/conf.d/default.conf
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;

    # Use Docker's embedded DNS so nginx re-resolves after backend restarts
    resolver 127.0.0.11 valid=10s ipv6=off;

    location /api {
        set \$backend http://backend:8000;
        proxy_pass \$backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
        proxy_send_timeout 300;
    }

    location / {
        try_files \$uri \$uri/ /index.html;
    }
}
EOF
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
