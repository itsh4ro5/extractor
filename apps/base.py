from abc import ABC, abstractmethod
from typing import List, Dict, Optional

class BaseApp(ABC):
    @abstractmethod
    async def login_otp(self, org_code: str, mobile: str) -> Dict:
        """OTP लॉगिन → {'token': ..., 'user': {...}}"""
        pass

    @abstractmethod
    async def login_token(self, token: str) -> Dict:
        """टोकन से लॉगिन → {'token': ..., 'user': {...}}"""
        pass

    @abstractmethod
    async def get_courses(self, token: str) -> List[Dict]:
        """खरीदे गए कोर्स की लिस्ट [{id, name, price, ...}]"""
        pass

    @abstractmethod
    async def extract_course(self, token: str, course_id: str) -> List[Dict]:
        """पूरे कोर्स का आइटम लिस्ट [{type, name, folder, link/contentHashId}]"""
        pass
