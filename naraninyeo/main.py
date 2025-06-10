from fastapi import FastAPI
from naraninyeo.api.routes import router
from naraninyeo.core.config import settings
from naraninyeo.core.database import db

app = FastAPI(title=settings.APP_NAME)

@app.on_event("startup")
async def startup_db_client():
    await db.connect_to_database()

@app.on_event("shutdown")
async def shutdown_db_client():
    await db.close_database_connection()

app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    ) 