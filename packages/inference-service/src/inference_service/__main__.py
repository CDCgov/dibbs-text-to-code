import logging
import os

import uvicorn


def main() -> None:
    """Runs the inference service with a single worker, so the models load once per GPU."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL") or "INFO",
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    uvicorn.run(
        "inference_service.app:app",
        host="0.0.0.0",  # noqa: S104 - the container is only reachable inside the VPC
        port=int(os.getenv("PORT") or 8080),
        workers=1,
        log_config=None,
    )


if __name__ == "__main__":
    main()
