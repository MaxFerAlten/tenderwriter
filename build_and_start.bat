@echo off
echo =========================================
echo Starting Docker build and startup process
echo =========================================
echo.

echo [Step 1/3] Building frontend...
docker compose build frontend
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to build frontend. Exiting.
    exit /b %ERRORLEVEL%
)
echo [SUCCESS] Frontend built successfully.
echo.

echo [Step 2/3] Building backend...
docker compose build backend
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to build backend. Exiting.
    exit /b %ERRORLEVEL%
)
echo [SUCCESS] Backend built successfully.
echo.

echo [Step 3/3] Starting services (profiles: keycloak, videochat)...
docker compose --profile keycloak --profile videochat up -d
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to start services. Exiting.
    exit /b %ERRORLEVEL%
)
echo [SUCCESS] All services started successfully.
echo.
echo Process completed!
