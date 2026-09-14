from fastapi import FastAPI
from app.config import settings
from app.auth.routes import router as auth_router
from app.github.routes import router as github_router
from app.projects.routes import router as projects_router
from app.git.credentials import git_credential_router
from app.deployments.routes import router as deployments_router

app = FastAPI(
    title="Cloud IDE Backend",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.include_router(auth_router)
app.include_router(github_router)
app.include_router(projects_router)
app.include_router(git_credential_router)
app.include_router(deployments_router)


@app.get("/")
async def root():
    return {
        "service": "cloud-ide-api",
        "status": "ok",
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
    }
