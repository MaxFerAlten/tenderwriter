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

echo [Wait] Waiting for containers to become healthy (this may take a minute)...
set ATTEMPTS=0

:waitloop
docker compose --profile keycloak --profile videochat ps | findstr /I "starting" >nul
if %ERRORLEVEL% neq 0 goto check_unhealthy

set /A ATTEMPTS=ATTEMPTS+1
if %ATTEMPTS% GEQ 60 (
    echo [ERROR] Timeout waiting for containers to start. Checking for unhealthy containers...
    goto check_unhealthy
)
timeout /t 2 /nobreak >nul
goto waitloop

:check_unhealthy
docker compose --profile keycloak --profile videochat ps | findstr /I "unhealthy" >nul
if %ERRORLEVEL% equ 0 (
    echo [ERROR] Some containers are unhealthy:
    docker compose --profile keycloak --profile videochat ps | findstr /I "unhealthy"
    exit /b 1
)

echo [SUCCESS] All services started and are healthy.
echo.
echo Process completed!
