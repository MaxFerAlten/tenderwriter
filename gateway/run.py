import asyncio

import uvicorn


async def main() -> None:
    """Launch two uvicorn servers for tender (8080) and opencode (8081)."""
    config_tender = uvicorn.Config(
        "app:create_app_tender",
        host="0.0.0.0",
        port=8080,
        factory=True,
        log_level="info",
    )
    config_opencode = uvicorn.Config(
        "app:create_app_opencode",
        host="0.0.0.0",
        port=8081,
        factory=True,
        log_level="info",
    )

    server_tender = uvicorn.Server(config_tender)
    server_opencode = uvicorn.Server(config_opencode)

    await asyncio.gather(server_tender.serve(), server_opencode.serve())


if __name__ == "__main__":
    asyncio.run(main())
