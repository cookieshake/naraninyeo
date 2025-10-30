from fastapi import APIRouter, Response


core_router = APIRouter()

@core_router.get("/")
async def root():
    return Response(status_code=200, content="Naraninyeo API is running.")

@core_router.get("/health")
async def health_check():
    return Response(status_code=200, content="OK")

