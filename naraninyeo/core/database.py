from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database
from naraninyeo.core.config import settings

class Database:
    client: AsyncIOMotorClient = None
    _db: Database = None

    async def connect_to_database(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self._db = self.client[settings.MONGODB_DB_NAME]

    async def close_database_connection(self):
        if self.client:
            self.client.close()

    @property
    def db(self) -> Database:
        if self._db is None:
            raise RuntimeError("Database not initialized")
        return self._db

mc = Database() 