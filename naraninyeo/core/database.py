from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from naraninyeo.core.config import settings

class Database:
    client: AsyncIOMotorClient = None
    db: AsyncIOMotorDatabase = None

    async def connect_to_database(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB_NAME]

    async def close_database_connection(self):
        if self.client:
            self.client.close()

    @property
    def get_db(self) -> AsyncIOMotorDatabase:
        if self.db is None:
            raise RuntimeError("Database not initialized")
        return self.db

db = Database() 