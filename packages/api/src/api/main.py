from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api.config import ENVIRONMENT
from api.core.base import BaseService

# create router
router = APIRouter(prefix="/api")


# define health check endpoint at the service level
@router.get("/healthcheck", tags=["internal"], include_in_schema=False)
async def health_check():
    """
    Check service health status.

    Returns: Status text
    """
    return "Text to Code Service is running!"


@router.get("/process/{item}")
def read_item(item: str):
    """Dummy endpoint"""
    return {
        "code": "8887-0",
        "codeSystem": "LOINC",
        "displayName": "Measles virus genotype A vaccine strain N gene [Presence] in Specimen by NAA with probe detection",
        "time": datetime.now(ZoneInfo("America/New_York")),
    }


# Instantiate FastAPI via DIBBs' BaseService class
app = BaseService(
    service_name="DIBBs Text to Code",
    description="Please visit the repo for more info: https://github.com/CDCgov/dibbs-text-to-code",
    include_health_check_endpoint=False,
    openapi_url="/api/openapi.json",
).start()

# set service_path in app state
app.state.service_path = "/api"

# include the router in the app
app.include_router(router)

if ENVIRONMENT["ENV"] != "local":
    app.mount(
        "/dist/assets",
        StaticFiles(
            directory="dist/assets",
            html=True,
            check_dir=ENVIRONMENT["ENV"] == "prod",
        ),
        name="assets",
    )

    @app.get(
        "/{full_path:path}",
        response_class=HTMLResponse,
        tags=["internal"],
        include_in_schema=False,
    )
    async def serve_index(full_path: str) -> HTMLResponse:
        """
        Intercept incoming requests.

        Modifies the `dist/index.html` file to include the environment, and return the file.

        Args:
            full_path (str): incoming URL

        Returns:
            HTMLResponse: Modified `dist/index.html` file
        """

        index_file = Path("dist/index.html").read_text()
        app_env = ENVIRONMENT["ENV"]
        html = index_file.replace("%APP_ENV%", app_env)
        return HTMLResponse(content=html)

else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8081"],  # Client dev server
        allow_credentials=True,  # Allow sending session cookies
        allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
        allow_headers=["*"],  # Allow all headers (Authorization, Content-Type, etc.)
    )
