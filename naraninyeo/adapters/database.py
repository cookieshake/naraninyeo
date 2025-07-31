"""
Database 연결 관리 - Infrastructure Adapter
기존 core/database.py를 이동하고 약간 개선
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from naraninyeo.core.config import Settings

class DatabaseAdapter:
    """MongoDB 연결 관리"""
    
    def __init__(self, settings: Settings):
        self.client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URL)
        self._db: Database = self.client[settings.MONGODB_DB_NAME]

    async def disconnect(self):
        """데이터베이스 연결 해제"""
        if self.client:
            self.client.close()
            self.client = None
            self._db = None

    @property
    def db(self) -> Database:
        """데이터베이스 인스턴스 반환"""
        if self._db is None:
            raise RuntimeError("Database is not connected. Call connect() first.")
        return self._db
