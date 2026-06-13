from abc import ABC, abstractmethod
from typing import List, Dict

class BaseApp(ABC):
    @abstractmethod
    async def login_otp(self, org_code: str, mobile: str) -> Dict:
        pass
    @abstractmethod
    async def login_token(self, token: str) -> Dict:
        pass
    @abstractmethod
    async def get_courses(self, token: str) -> List[Dict]:
        pass
    @abstractmethod
    async def extract_course(self, token: str, course_id: str) -> List[Dict]:
        pass
