from pymongo import MongoClient
from datetime import datetime

class Database:
    def __init__(self, mongo_uri):
        self.client = MongoClient(mongo_uri)
        self.db = self.client["classplus_bot"]
        self.sessions = self.db["sessions"]  # user_id -> {token, app, org_code, ...}
        self.tasks = self.db["tasks"]        # download/extract tasks

    def save_session(self, user_id, app_name, data):
        self.sessions.update_one(
            {"user_id": user_id, "app": app_name},
            {"$set": {**data, "updated_at": datetime.utcnow()}},
            upsert=True
        )

    def get_session(self, user_id, app_name):
        return self.sessions.find_one({"user_id": user_id, "app": app_name})

    def add_task(self, user_id, task_type, data):
        self.tasks.insert_one({
            "user_id": user_id,
            "type": task_type,
            "data": data,
            "created_at": datetime.utcnow()
        })
