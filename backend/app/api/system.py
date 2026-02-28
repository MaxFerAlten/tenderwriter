"""
TenderWriter — System APIs

Internal monitoring and configuration APIs using Docker SDK.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import docker
import structlog
from typing import Dict, Any, List

from app.api.auth import get_current_user, UserResponse

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
async def update_nginx_timeout(config: NginxConfigUpdate):
    """Update Nginx timeouts dynamically and reload the service."""
    if not docker_client:
        raise HTTPException(status_code=503, detail="Docker SDK not connected")
        
    try:
        frontend_container = docker_client.containers.get("tw-frontend")
        
        # Generate the Nginx config snippet to write inside the container
        # Since tw-frontend uses a specific default.conf, we can overwrite it or use sed
        # For a robust approach, we write a shell script to do the replacement inside the container
        
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
