# File ke sabse upar jaha imports hain, waha ye line update kar do:
import re, uuid, aiohttp, random, string, asyncio
from urllib.parse import quote
from typing import List, Dict
from apps.base import BaseApp

class ClassplusApp(BaseApp):
    BASE = "https://api.classplusapp.com"
    
    # Is function se har user ke liye naya Device ID generate hoga
    def get_headers(self):
        random_device_id = ''.join(random.choices(string.digits + string.ascii_lowercase, k=16))
        return {
            'host': 'api.classplusapp.com',
            'accept-language': 'EN',
            'api-version': '18',
            'app-version': '1.4.73.2',
            'build-number': '35',
            'connection': 'Keep-Alive',
            'content-type': 'application/json',
            'device-details': 'Xiaomi_Redmi 7_SDK-32',
            'device-id': random_device_id,
            'region': 'IN',
            'user-agent': 'Mobile-Android',
            'webengage-luid': str(uuid.uuid4()),
            'accept-encoding': 'gzip'
        }

    # ---------- OTP LOGIN ----------
    async def login_otp(self, org_code: str, mobile: str) -> Dict:
        headers = self.get_headers() # Dynamic headers call kiya
        async with aiohttp.ClientSession() as sess:
            async with sess.get(f"{self.BASE}/v2/orgs/{org_code}", headers=headers) as r:
                r.raise_for_status()
                org_data = await r.json()
            org_id = org_data['data']['orgId']
            org_name = org_data['data']['orgName']

            fingerprint_id = uuid.uuid4().hex

            # Step 3: OTP Payload (Email aur Mobile dono ke liye)
            otp_payload = {
                "countryExt": "91",
                "orgCode": org_code,
                "orgId": org_id,
                "otpCount": 0,
                "retry": 0,
            }
            
            if '@' in mobile:
                otp_payload["email"] = mobile
                otp_payload["viaEmail"] = "1"
                otp_payload["viaSms"] = "0"
            else:
                otp_payload["mobile"] = mobile
                otp_payload["viaEmail"] = "0"
                otp_payload["viaSms"] = "1"

            async with sess.post(f"{self.BASE}/v2/otp/generate", json=otp_payload, headers=headers) as r:
                r.raise_for_status()
                otp_resp = await r.json()
            session_id = otp_resp['data']['sessionId']

            # Step 4: OTP इनपुट (बॉट में यह कॉलबैक से आएगा, यहाँ हम रिटर्न करेंगे sessionId ताकि बाद में verify करें)
            return {
                'status': 'otp_sent',
                'org_id': org_id,
                'org_name': org_name,
                'session_id': session_id,
                'fingerprint_id': fingerprint_id,
                'mobile': mobile,
                'countryExt': '91'
            }

    async def verify_otp(self, org_id: int, mobile: str, session_id: int, otp: str, fingerprint_id: str) -> Dict:
        headers = self.get_headers()
        payload = {
            "otp": otp,
            "countryExt": "91",
            "sessionId": session_id,
            "orgId": org_id,
            "fingerprintId": fingerprint_id,
            "mobile": mobile
        }
        async with aiohttp.ClientSession() as sess:
            async with sess.post(f"{self.BASE}/v2/users/verify", json=payload, headers=headers) as r:
                r.raise_for_status()
                data = await r.json()
        token = data['data']['token']
        refresh_token = data['data'].get('refreshToken')
        user = data['data']['user']
        return {
            'token': token,
            'refresh_token': refresh_token,
            'user': user
        }

    # ---------- TOKEN LOGIN ----------
    async def login_token(self, token: str) -> Dict:
        import base64, json
        payload = token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        user = json.loads(base64.urlsafe_b64decode(payload))
        return {'token': token, 'user': user}

    # ---------- COURSES ----------
    async def get_courses(self, token: str) -> List[Dict]:
        headers = self.get_headers()
        headers['x-access-token'] = token
        url = f"{self.BASE}/v2/courses?tabCategoryId=1&categoryId=[]"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers=headers) as r:
                r.raise_for_status()
                data = await r.json()
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
                    'orgCode': None,  # बाद में सेट होगा
                    'expiresAt': c.get('expiresAt')
                })
        return courses

    # ---------- EXTRACT COURSE ----------
    async def extract_course(self, token: str, course_id: str) -> List[Dict]:
        items = []
        await self._recurse(token, course_id, 0, "", items)
        return items

    async def _recurse(self, token, course_id, folder_id, folder_path, items):
        headers = self.get_headers()
        headers['x-access-token'] = token
        params = {'courseId': course_id, 'folderId': folder_id, 'storeContentEvent': 'false'}
        url = f"{self.BASE}/v2/course/content/get"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, params=params, headers=headers) as r:
                r.raise_for_status()
                data = await r.json()
                
        # Server limits se bachne ke liye chhota sa delay
        await asyncio.sleep(0.5)
        
        for item in data['data']['courseContent']:
            itype = item.get('contentType')
            name = self._sanitize(item.get('name', 'unknown'))
            if itype == 1:
                await self._recurse(token, course_id, item['id'],
                                    f"{folder_path}/{name}" if folder_path else name, items)
            elif itype == 2:
                items.append({
                    'type': 'video',
                    'name': name,
                    'folder': folder_path,
                    'contentHashId': item.get('contentHashId')
                })
            elif itype == 3:
                items.append({
                    'type': 'pdf',
                    'name': name,
                    'folder': folder_path,
                    'url': item.get('url')
                })

    async def get_signed_url(self, token, content_hash_id):
        headers = self.get_headers() # <--- ISKO UPDATE KARO
        headers['x-access-token'] = token
        encoded = quote(content_hash_id, safe='')
        url = f"{self.BASE}/cams/uploader/video/jw-signed-url?contentId={encoded}"
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, headers=headers) as r:
                data = await r.json()
                if not data.get('url'):
                    raise Exception(f"Signed URL not found: {data}")
                return data['url']

    @staticmethod
    def _sanitize(name):
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()
