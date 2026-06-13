import re
import aiohttp
from urllib.parse import quote
from typing import List, Dict
from apps.base import BaseApp

class ClassplusApp(BaseApp):
    BASE = "https://api.classplusapp.com"
    HEADERS = {
        'host': 'api.classplusapp.com',
        'accept-language': 'EN',
        'api-version': '18',
        'app-version': '1.4.73.2',
        'build-number': '35',
        'connection': 'Keep-Alive',
        'content-type': 'application/json',
        'device-details': 'Xiaomi_Redmi 7_SDK-32',
        'device-id': 'c28d3cb16bbdac01',
        'region': 'IN',
        'user-agent': 'Mobile-Android',
        'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c',
        'accept-encoding': 'gzip'
    }

    async def login_otp(self, org_code: str, mobile: str) -> Dict:
        # orgId निकालने के लिए पहले orgCode से orgId लें (कई बार orgId = orgCode से मैपिंग)
        # यहाँ हम orgCode "iqvqn" से orgId 9183 लेकर चलेंगे (आपके डेटा से)
        # असल में API /v1/auth/send-otp अब शायद काम न करे, नया एंडपॉइंट खोजना होगा
        # हम टोकन लॉगिन को प्राथमिकता देते हैं, क्योंकि OTP एंडपॉइंट बदलता रहता है
        raise NotImplementedError("OTP login endpoint changed, use token login.")

    async def login_token(self, token: str) -> Dict:
        # token को verify करें (कोई API नहीं, बस उसे store करें)
        # user details token से decode करें
        import base64, json
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        user = json.loads(base64.urlsafe_b64decode(payload))
        return {'token': token, 'user': user}

    async def get_courses(self, token: str) -> List[Dict]:
        headers = self.HEADERS.copy()
        headers['x-access-token'] = token
        url = f"{self.BASE}/v2/courses?tabCategoryId=1&categoryId=[]"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        courses = []
        for c in data['data']['courses']:
            if c.get('isPurchased'):
                courses.append({
                    'id': c['id'],
                    'name': c['name'],
                    'price': c['price'],
                    'finalPrice': c['finalPrice'],
                    'resources': c['resources'],
                    'orgId': c['orgId'],
                    'expiresAt': c.get('expiresAt')
                })
        return courses

    async def extract_course(self, token: str, course_id: str) -> List[Dict]:
        items = []
        await self._recurse(token, course_id, 0, "", items)
        return items

    async def _recurse(self, token, course_id, folder_id, folder_path, items):
        headers = self.HEADERS.copy()
        headers['x-access-token'] = token
        url = f"{self.BASE}/v2/course/content/get"
        params = {'courseId': course_id, 'folderId': folder_id, 'storeContentEvent': 'false'}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
        for item in data['data']['courseContent']:
            itype = item.get('contentType')
            name = self._sanitize(item.get('name', 'unknown'))
            if itype == 1:  # folder
                await self._recurse(token, course_id, item['id'], f"{folder_path}/{name}" if folder_path else name, items)
            elif itype == 2:  # video
                items.append({
                    'type': 'video',
                    'name': name,
                    'folder': folder_path,
                    'contentHashId': item.get('contentHashId')
                })
            elif itype == 3:  # pdf
                items.append({
                    'type': 'pdf',
                    'name': name,
                    'folder': folder_path,
                    'url': item.get('url')
                })

    async def get_signed_url(self, token, content_hash_id):
        headers = self.HEADERS.copy()
        headers['x-access-token'] = token
        encoded = quote(content_hash_id, safe='')
        url = f"{self.BASE}/cams/uploader/video/jw-signed-url?contentId={encoded}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                data = await resp.json()
                if not data.get('url'):
                    raise Exception(f"Signed URL not found: {data}")
                return data['url']

    @staticmethod
    def _sanitize(name):
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()
