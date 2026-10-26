"""python -m offline_app : http://localhost for this laptop, https on the Wi-Fi address for phones."""
import asyncio

import uvicorn

from . import config, net


async def serve() -> None:
    net.ensure_cert(net.lan_ips())
    servers = [
        uvicorn.Server(uvicorn.Config("offline_app.main:app", host="127.0.0.1", port=config.HTTP_PORT)),
        # lifespan runs once, in the first server, so the sync thread starts once.
        uvicorn.Server(uvicorn.Config(
            "offline_app.main:app", host="0.0.0.0", port=config.HTTPS_PORT, lifespan="off",
            ssl_certfile=str(net.CERT), ssl_keyfile=str(net.KEY),
        )),
    ]
    tasks = [asyncio.create_task(s.serve()) for s in servers]
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for s in servers:  # if one stops (Ctrl+C, port in use), stop both
        s.should_exit = True
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(serve())
