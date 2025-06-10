from fastapi import FastAPI
from naraninyeo.api.routes import router
from naraninyeo.core.config import settings

app = FastAPI(title=settings.APP_NAME)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    ) 