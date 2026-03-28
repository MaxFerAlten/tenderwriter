# Multi-stage build: compile the Go plugin and prepare the bundle
# for installation into Mattermost's /plugins directory.

# --- Stage 1: Build the Go server binary ---
FROM golang:1.23-alpine AS builder

RUN apk add --no-cache git

WORKDIR /build/server
COPY server/go.mod server/*.go ./
RUN go mod tidy && go mod download
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o /build/dist/plugin-linux-amd64 .

# --- Stage 2: Assemble the plugin bundle ---
FROM alpine:3.20

RUN mkdir -p /plugin/com.tenderwriter.oidc/server/dist

COPY plugin.json                          /plugin/com.tenderwriter.oidc/
COPY --from=builder /build/dist/plugin-linux-amd64 \
                                          /plugin/com.tenderwriter.oidc/server/dist/

# Default entrypoint: copy plugin to the mounted volume and exit
ENTRYPOINT ["sh", "-c", "rm -rf /mnt/plugins/com.tenderwriter.oidc && cp -r /plugin/com.tenderwriter.oidc /mnt/plugins/ && echo '[tw-oidc] Plugin installed to /mnt/plugins/com.tenderwriter.oidc'"]
