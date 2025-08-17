"""Main API router."""

from fastapi.routing import APIRouter

from trae_api.api.agent.endpoints import views as agent_views
from trae_api.api.echo.endpoints import views as echo_views
from trae_api.api.health.router import router as health_router
from trae_api.api.monitoring.endpoints import views as monitoring_views
from trae_api.api.monitoring.middleware_health import router as middleware_health_router
from trae_api.api.tasks.endpoints import views as task_views

api_router = APIRouter()

# Include health checks
api_router.include_router(health_router)

# Include monitoring endpoints
api_router.include_router(monitoring_views.router, tags=["monitoring"])
api_router.include_router(middleware_health_router, tags=["monitoring"])

# Include echo endpoints
api_router.include_router(echo_views.router, prefix="/echo", tags=["echo"])

# Include task endpoints
api_router.include_router(task_views.router, prefix="/tasks", tags=["tasks"])

# Include agent endpoints
api_router.include_router(agent_views.router, prefix="/agent", tags=["agent"])
