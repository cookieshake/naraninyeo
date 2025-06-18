from pymongo import MongoClient
from pymongo.database import Database
from naraninyeo.core.config import settings

class Database:
    client: MongoClient = None
    db: Database = None

    def connect_to_database(self):
        self.client = MongoClient(settings.MONGODB_URL)
        self.db = self.client[settings.MONGODB_DB_NAME]

    def close_database_connection(self):
        if self.client:
            self.client.close()

    @property
    def get_db(self) -> Database:
        if self.db is None:
            raise RuntimeError("Database not initialized")
        return self.db

db = Database() 