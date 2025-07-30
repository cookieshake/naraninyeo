"""
Database 연결 관리 - Infrastructure Adapter
기존 core/database.py를 이동하고 약간 개선
"""
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from naraninyeo.core.config import settings

class DatabaseAdapter:
    """MongoDB 연결 관리"""
    
    def __init__(self):
        self.client: AsyncIOMotorClient = AsyncIOMotorClient(settings.MONGODB_URL)
        self._db: Database = self.client[settings.MONGODB_DB_NAME]

    async def disconnect(self):
        """데이터베이스 연결 해제"""
        if self.client:
            self.client.close()

    @property
    def db(self) -> Database:
        """데이터베이스 인스턴스 반환"""
        return self._db

# 전역 인스턴스 (기존 코드 호환성을 위해)
database_adapter = DatabaseAdapter()

# 기존 코드와의 호환성을 위한 별칭
mc = database_adapter
