"""Start the offline assistant client server on localhost (127.0.0.1).

Runs completely offline without external backend or mobile connections.
"""
import uvicorn

from . import config


def main() -> None:
    uvicorn.run("offline_app.main:app", host="127.0.0.1", port=config.HTTP_PORT, log_level="info")


if __name__ == "__main__":
    main()
