from contextlib import asynccontextmanager
from fastapi import FastAPI
from naraninyeo.api.routes import router
from naraninyeo.core.config import settings
from naraninyeo.core.database import db

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.connect_to_database()
    try:
        yield
    finally:
        db.close_database_connection()

app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    ) 