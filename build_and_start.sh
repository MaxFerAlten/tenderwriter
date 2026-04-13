#!/bin/bash

echo "========================================="
echo "Starting Docker build and startup process"
echo "========================================="
echo ""

echo "[Step 1/3] Building frontend..."
docker compose build frontend
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to build frontend. Exiting."
    exit 1
fi
echo "[SUCCESS] Frontend built successfully."
echo ""

echo "[Step 2/3] Building backend..."
docker compose build backend
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to build backend. Exiting."
    exit 1
fi
echo "[SUCCESS] Backend built successfully."
echo ""

echo "[Step 3/3] Starting services (profiles: keycloak, videochat)..."
docker compose --profile keycloak --profile videochat up -d
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to start services. Exiting."
    exit 1
fi

echo "[Wait] Waiting for containers to become healthy (this may take a minute)..."
ATTEMPTS=0
MAX_ATTEMPTS=60
while docker compose --profile keycloak --profile videochat ps | grep -qi "starting"; do
    if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
        echo "[ERROR] Timeout waiting for containers to start. Checking for unhealthy containers..."
        break
    fi
    sleep 2
    ATTEMPTS=$((ATTEMPTS+1))
done

if docker compose --profile keycloak --profile videochat ps | grep -qi "unhealthy"; then
    echo "[ERROR] Some containers are unhealthy:"
    docker compose --profile keycloak --profile videochat ps | grep -i "unhealthy"
    exit 1
fi

echo "[SUCCESS] All services started and are healthy."
echo ""
echo "Process completed!"
