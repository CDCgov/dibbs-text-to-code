import os
from typing import Literal

from config import DIBBS_CONTACT
from config import LICENSES
from fastapi import FastAPI


class BaseService:
    """
    Base service class for DIBBs FastAPI applications.

    This reusable class provides common functionality for DIBBs services including:
    - FastAPI application setup with standard metadata
    - Optional health check endpoint
    - License and OpenAPI configuration
    """

    def __init__(
        self,
        service_name: str,
        description: str,
        include_health_check_endpoint: bool = True,
        license_info: Literal["CreativeCommonsZero", "MIT"] = "CreativeCommonsZero",
        openapi_url: str = "/openapi.json",
    ):
        """
        Initialize a BaseService instance.

        Args:
            service_name: Name of the service.
            service_path: Path used to access the service from a gateway.
            description: Service description.
            lifespan: A Starlette `Lifespan` object
            include_health_check_endpoint: Whether to add standard DIBBs health
                check endpoint. Defaults to True.
            license_info: License to use for the service. Options:
                - "CreativeCommonsZero" (default): CC0 v1.0 Universal
                - "MIT": MIT License
            openapi_url: URL for OpenAPI.json used by FastAPI for /redoc.
                For services behind gateways, use "/{service-name}/openapi.json".
                Defaults to "/openapi.json".
        """
        description = description
        self.include_health_check_endpoint = include_health_check_endpoint
        self.app = FastAPI(
            title=service_name,
            version=os.getenv("APP_VERSION", "0.1.0"),
            contact=DIBBS_CONTACT,
            license_info=LICENSES[license_info],
            description=description,
            openapi_url=openapi_url,
        )

    def start(self) -> FastAPI:
        """
        Initialize and return the configured FastAPI instance.

        Returns:
            FastAPI: Configured FastAPI instance with DIBBs metadata.
        """
        return self.app
