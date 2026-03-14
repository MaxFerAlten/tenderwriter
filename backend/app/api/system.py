"""
TenderWriter — System APIs

Internal monitoring and configuration APIs using Docker SDK.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import docker
import structlog
from typing import Dict, Any, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user, UserResponse
from app.db.database import get_db
from app.models.app_settings import AppSettings

logger = structlog.get_logger()
router = APIRouter()

try:
    docker_client = docker.from_env()
except Exception as e:
    logger.error(f"Failed to connect to Docker socket: {e}")
    docker_client = None


def admin_required(current_user: UserResponse = Depends(get_current_user)):
    """Dependency to check if user is admin."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current_user


class NginxConfigUpdate(BaseModel):
    read_timeout: int
    connect_timeout: int
    send_timeout: int


@router.get("/containers", dependencies=[Depends(admin_required)])
async def list_containers() -> List[Dict[str, Any]]:
    """List all TenderWriter related containers and their health status."""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker SDK not connected")
        
    try:
        containers = docker_client.containers.list(all=True, filters={"name": "tw-"})
        return [
            {
                "id": c.short_id,
                "name": c.name.replace("tw-", ""),
                "status": c.status,
                "health": c.attrs.get("State", {}).get("Health", {}).get("Status", "unknown")
            }
            for c in containers
        ]
    except Exception as e:
        logger.error(f"Error listing containers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/logs/{container_name}", dependencies=[Depends(admin_required)])
async def get_container_logs(container_name: str, tail: int = 100):
    """Retrieve the recent logs of a specific container."""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker SDK not connected")
        
    try:
        # Resolve internal name
        full_name = f"tw-{container_name}" if not container_name.startswith("tw-") else container_name
        container = docker_client.containers.get(full_name)
        logs = container.logs(tail=tail, stdout=True, stderr=True, timestamps=True).decode("utf-8")
        return {"logs": logs}
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        logger.error(f"Error getting logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats/{container_name}", dependencies=[Depends(admin_required)])
async def get_container_stats(container_name: str):
    """Retrieve realtime stats (CPU, Memory) for a container."""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker SDK not connected")
        
    try:
        full_name = f"tw-{container_name}" if not container_name.startswith("tw-") else container_name
        container = docker_client.containers.get(full_name)
        stats = container.stats(stream=False)
        
        # Calculate CPU %
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_cpu_delta = stats["cpu_stats"]["system_cpu_usage"] - stats["precpu_stats"]["system_cpu_usage"]
        num_cpus = stats["cpu_stats"]["online_cpus"]
        cpu_percent = 0.0
        if system_cpu_delta > 0.0 and cpu_delta > 0.0:
            cpu_percent = (cpu_delta / system_cpu_delta) * num_cpus * 100.0

        # Memory %
        mem_usage = stats["memory_stats"].get("usage", 0)
        mem_limit = stats["memory_stats"].get("limit", 1)
        mem_percent = (mem_usage / mem_limit) * 100.0
        
        return {
            "cpu_percent": round(cpu_percent, 2),
            "memory_usage_mb": round(mem_usage / (1024 * 1024), 2),
            "memory_limit_mb": round(mem_limit / (1024 * 1024), 2),
            "memory_percent": round(mem_percent, 2)
        }
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="Container not found")
    except Exception as e:
        logger.error(f"Error getting stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/nginx-timeout", dependencies=[Depends(admin_required)])
async def update_nginx_timeout(
    config: NginxConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update Nginx timeouts dynamically, reload the service, and persist to DB."""
    # Persist the timeout values in app_settings
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = AppSettings(data={})
        db.add(row)
    current_data = dict(row.data) if row.data else {}
    current_data["nginx_read_timeout"] = config.read_timeout
    current_data["nginx_connect_timeout"] = config.connect_timeout
    current_data["nginx_send_timeout"] = config.send_timeout
    row.data = current_data
    await db.flush()

    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker SDK not connected")
        
    try:
        frontend_container = docker_client.containers.get("tw-frontend")
        
        commands = [
            f"sed -i -E 's/proxy_read_timeout [0-9]+;/proxy_read_timeout {config.read_timeout};/' /etc/nginx/conf.d/default.conf",
            f"sed -i -E 's/proxy_connect_timeout [0-9]+;/proxy_connect_timeout {config.connect_timeout};/' /etc/nginx/conf.d/default.conf",
            f"sed -i -E 's/proxy_send_timeout [0-9]+;/proxy_send_timeout {config.send_timeout};/' /etc/nginx/conf.d/default.conf",
            "nginx -s reload"
        ]
        
        full_command = "sh -c \"" + " && ".join(commands) + "\""
        
        exit_code, output = frontend_container.exec_run(full_command)
        
        if exit_code != 0:
            raise Exception(f"Failed to reload nginx: {output.decode('utf-8')}")
            
        logger.info("Nginx timeout updated and reloaded successfully", timeouts=config.model_dump())
        return {"message": "Config updated and Nginx reloaded successfully"}
        
    except docker.errors.NotFound:
        raise HTTPException(status_code=404, detail="tw-frontend container not found")
    except Exception as e:
        logger.error(f"Error updating nginx configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── App Settings (generic key-value store) ──


class AppSettingsPayload(BaseModel):
    """Flexible payload — any key-value pair is accepted."""
    rag_model: str | None = None
    nginx_read_timeout: int | None = None
    nginx_connect_timeout: int | None = None
    nginx_send_timeout: int | None = None
    admin_enabled: bool | None = None


@router.get("/app-settings")
async def get_app_settings(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all saved app settings."""
    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if row and row.data:
        return row.data
    # Return defaults
    return {
        "rag_model": "Llama 3 (8b)",
        "nginx_read_timeout": 300,
        "nginx_connect_timeout": 300,
        "nginx_send_timeout": 300,
        "admin_enabled": True,
    }


@router.put("/app-settings")
async def update_app_settings(
    payload: AppSettingsPayload,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save app settings to the database."""
    # Only admins can save settings
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")

    result = await db.execute(select(AppSettings).limit(1))
    row = result.scalar_one_or_none()
    if not row:
        row = AppSettings(data={})
        db.add(row)

    current_data = dict(row.data) if row.data else {}
    # Merge only non-None values from the payload
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            current_data[key] = value
    row.data = current_data
    await db.flush()
    await db.refresh(row)
    logger.info("App settings updated", data=row.data)
    return row.data
