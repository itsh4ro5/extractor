import asyncio, aiohttp, re, os
from urllib.parse import quote
from yarl import URL
from apps.base import BaseExtractor
from core.crypto import encrypt_url

MAX_CONCURRENT_REQUESTS = 20

# APNE PW TOKENS YAHAN UPDATE KAREIN
SESSION_COOKIE = ".eJwVk8eOo1oABf_FW0_LZMNIb0E28ZLTpgWYYDBwiQZG79-nR7U9m5JO_bl8w2Lq0r7ol8vvZVqLX5c0z4t5_l6Gtugvvy-LFggA8HxR0FwKufnpYcn1YM9kBrELDvuqsBT78AoJTWrDV4JrnyZWzkX1scShBvRFcWL3aiJsPluhhdbwo0HVmjtgvyv7jtUEkCgRcp59lt7CjY5eYLjHvw2uYSMbTUBAEFR600uULbJsIkdldIxsXkfLT3QS0PABzei0HmbZV1CC6NUvvY0ZI52bTkCy-slwHlL3_pzSa74kO2MzHi5fsYgvZBS3ieQ6v8npkwPj8Pu6HaXo5r184jaEeV5iwbuxm6KqOKRq8S2YBVrFMvhMj-VxjsMaWbuWyNpdGfhK0xbmuWHXnH7nDZhiIrTTlj46jPFpESP2CCKMrdSF9gjXeBVLCzMrgE67SiMe_qK7lpP95fbcHfluWVJk3vjlOnRLm74n7vQR1Bm44-kIFq2Sm6Gc_aDDQoRmDPQA8dr3DfHG1qBnGnnVXfkxFtFW-Jj5YRG8jSITsytndEpI6IxQVxtWke6b0S4a5VqCVI8vsDFx_sQYD6syJ2m6wJmy_ecLn13GlEES2Qyo60gQ2VTeU5nw2E0kCSzQTk7LSFj5IfIhEiJLRt9AbILAcnFmjwrTVBMluXmJfUHUdXg3Gs2jI-ZT-MwSkfg9qlMHrcp0LqZQfCt5-9CCGhqBD4lojpfbZ_pxNI3QII6Wv9agPS1xaHN0cranIqI4FpJSAYJcIF2TG_km4DZNnRhfTmAYviTCLZ6zHBEvTD09wTMo0m-coCu7VahNaw_lnH0fJZCFQK8_Ona1W9YTip8NJq9JsBtZAqetqrP4HJE8smZ3NMMlbD_ChgOrsd0eDVj3zTK7ZXQqTlq-AJTY6G2Gop5C0bSbvgPeWR6Uqi1wRYPe0F_ih9ceOiL21TVv6kixs6lTwsQb_rv8ukzz9_yT32v4195mbJ5oiYR8jpJL5IO7DkPsI-pGBhWKl_jjcYQsNcf1wMmuPr47XWDKV05CqCZh7JZ1hwD69V3gVjoumg5HijdRYtyfH6MynTLYmuG-Jprqa97d15wyPDRsSOYlnzd3e0oqXNumpBVE5fbvkqpzDgjvdNJ0yQK9A9p4wrU-kiuyhPzXhB6l_VVEQkPCr9yxKOpzXP7_C_mCd9o.ajkUkQ.ba3nBaLZXTYlvAMm_0nKrxykAOU"
JWT_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJleHAiOjE3ODI3MjE5NTMuODk2LCJkYXRhIjp7Il9pZCI6IjY0NDE4NWU2MzBjYmM2MDAxOGY4ZDcxYSIsInVzZXJuYW1lIjoiOTEyMjE2MzAxMyIsImZpcnN0TmFtZSI6Ik1vbnUgS3VtYXIiLCJsYXN0TmFtZSI6IkJyYW5kIiwib3JnYW5pemF0aW9uIjp7Il9pZCI6IjVlYjM5M2VlOTVmYWI3NDY4YTc5ZDE4OSIsIndlYnNpdGUiOiJwaHlzaWNzd2FsbGFoLmNvbSIsIm5hbWUiOiJQaHlzaWNzd2FsbGFoIn0sImVtYWlsIjoibml0aXNoa3VtYXJ5YWRhdjkyNjQyNkBnbWFpbC5jb20iLCJyb2xlcyI6WyI1YjI3YmQ5NjU4NDJmOTUwYTc3OGM2ZWYiXSwiY291bnRyeUdyb3VwIjoiSU4iLCJ0eXBlIjoiVVNFUiJ9LCJqdGkiOiJYUG8tQVBTRVJQdTRaa2wwVHRLLUV3XzY0NDE4NWU2MzBjYmM2MDAxOGY4ZDcxYSIsImlhdCI6MTc4MjExNzE1M30.0tZN68aei0b23v9WYQstEoqmcGAgpozf2xbrMSBlwQ4"
PW_HDR = {"authorization": f"Bearer {JWT_TOKEN}", "client-version": "538", "content-type": "application/json"}

class PWExtractor(BaseExtractor):
    def __init__(self):
        super().__init__()
        self.platform_name = "PhysicsWallah"

    async def can_handle(self, url: str) -> bool:
        return "pw.live" in url

    def safe_name(self, s: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', str(s)).strip('.')[:200]

    async def _fetch_text(self, session, url, headers=None, retries=3):
        for i in range(retries):
            try:
                async with session.get(url, headers=headers, timeout=30) as r:
                    r.raise_for_status()
                    return await r.text()
            except Exception:
                if i == retries - 1: raise
                await asyncio.sleep(2)

    async def _fetch_json(self, session, url, headers=None, retries=5):
        for i in range(retries):
            try:
                async with session.get(url, headers=headers, timeout=30) as r:
                    r.raise_for_status()
                    return await r.json()
            except Exception:
                if i == retries - 1: raise
                await asyncio.sleep(2 ** i)

    async def resolve_batch_id(self, session, url):
        html = await self._fetch_text(session, url)
        b_ids = re.findall(r'(?i)batch[_\-]?id[^\w]+([a-f0-9]{24})', html) or re.findall(r'(?i)_id[^\w]+([a-f0-9]{24})', html)
        if b_ids:
            from collections import Counter
            return Counter(b_ids).most_common(1)[0][0]
        raise Exception("ID not found in URL")

    async def resolve_pdf_url(self, session, batch_id, subject_id, schedule_id, note_index, is_dpp):
        url = f"https://rarestudy.in/schedule-details?batchId={batch_id}&subjectId={subject_id}&scheduleId={schedule_id}&tap=note&noteIndex={note_index}&isDpp={'true' if is_dpp else 'false'}"
        async with session.get(url, allow_redirects=False) as resp:
            if resp.status in (301, 302, 303, 307, 308): return resp.headers.get("Location")
            return None

    async def extract(self, url: str, status_msg) -> tuple[str, str]:
        jar = aiohttp.CookieJar()
        jar.update_cookies({"session": SESSION_COOKIE}, URL("https://rarestudy.in"))
        
        try:
            async with aiohttp.ClientSession(cookie_jar=jar, headers={"User-Agent": "Mozilla/5.0"}) as session:
                batch_id = await self.resolve_batch_id(session, url)
                await status_msg.edit_text(f"[*] Platform: {self.platform_name}\n[*] ID Extracted: `{batch_id}`\n⏳ Scanning modules...")
                
                details = await self._fetch_json(session, f"https://api.penpencil.co/v3/batches/{batch_id}/details", PW_HDR)
                batch_name = self.safe_name(details.get("data", {}).get("name", batch_id))
                file_name = f"INDEX_{batch_name}.txt"
                sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
                
                with open(file_name, "w", encoding="utf-8") as f:
                    # MAIN CONTENT
                    for sub in details.get("data", {}).get("subjects", []):
                        sid, sname = sub["_id"], self.safe_name(sub["subject"])
                        topics = []; pg = 1
                        while True:
                            tdata = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/topics?page={pg}", PW_HDR)
                            if not tdata.get("data"): break
                            topics.extend(tdata.get("data", []))
                            if len(tdata.get("data", [])) < 20: break
                            pg += 1
                            
                        for top in topics:
                            tid, tname = top["_id"], self.safe_name(top["name"])
                            
                            # Videos
                            for ctype in ("videos", "DppVideos"):
                                cpg = 1
                                while True:
                                    cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/contents?page={cpg}&contentType={ctype}&tag={tid}", PW_HDR)
                                    items = cont.get("data", [])
                                    if not items: break
                                    
                                    async def fetch_vid(item):
                                        sched_id = item["_id"]
                                        title = self.safe_name(item.get("topic") or item.get("videoDetails", {}).get("name") or sched_id)
                                        try:
                                            async with sem:
                                                html = await self._fetch_text(session, f"https://rarestudy.in/schedule-details?batchId={batch_id}&subjectId={sid}&scheduleId={sched_id}&tap=video")
                                                token = re.search(r'const MEDIA_TOKEN\s*=\s*"([^"]+)"', html)
                                                if token:
                                                    v_data = await self._fetch_json(session, f"https://rarestudy.in/v1/videos/video-url-details?mediaToken={quote(token.group(1))}&videoContainerType=DASH")
                                                    mpd_url = v_data["data"]["url"]
                                                    key_hex = v_data["data"]["keys"][0].split(":")[1]
                                                    return f"MAIN | {sname} | {tname} | {title} | {encrypt_url(mpd_url)} | KEY: {key_hex} | TYPE: .mpd\n"
                                        except Exception: pass
                                        return None

                                    for res in await asyncio.gather(*[fetch_vid(i) for i in items]):
                                        if res: f.write(res); f.flush()
                                    if len(items) < 20: break
                                    cpg += 1
                                    
                            # PDFs
                            for ctype, is_dpp in [("notes", False), ("DppNotes", True)]:
                                cpg = 1
                                while True:
                                    cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/contents?page={cpg}&contentType={ctype}&tag={tid}", PW_HDR)
                                    items = cont.get("data", [])
                                    if not items: break
                                    
                                    async def fetch_pdf(item):
                                        sched_id = item["_id"]
                                        links = []
                                        if not is_dpp:
                                            for att_idx, att in enumerate(item.get("attachmentIds", [])):
                                                try:
                                                    async with sem:
                                                        pdf_url = await self.resolve_pdf_url(session, batch_id, sid, sched_id, att_idx, False)
                                                        if pdf_url: links.append(f"MAIN | {sname} | {tname} | {self.safe_name(att.get('name') or 'NOTE')} | {encrypt_url(pdf_url)} | NONE | TYPE: .pdf\n")
                                                except Exception: pass
                                        else:
                                            for hw_idx, hw in enumerate(item.get("homeworkIds", [])):
                                                for att_idx, att in enumerate(hw.get("attachmentIds", [])):
                                                    g_idx = sum(len(item["homeworkIds"][i].get("attachmentIds", [])) for i in range(hw_idx)) + att_idx
                                                    try:
                                                        async with sem:
                                                            pdf_url = await self.resolve_pdf_url(session, batch_id, sid, sched_id, g_idx, True)
                                                            if pdf_url: links.append(f"MAIN | {sname} | {tname} | {self.safe_name(att.get('name') or 'NOTE')} | {encrypt_url(pdf_url)} | NONE | TYPE: .pdf\n")
                                                    except Exception: pass
                                        return links

                                    for link_list in await asyncio.gather(*[fetch_pdf(i) for i in items]):
                                        for res in link_list: f.write(res); f.flush()
                                    if len(items) < 20: break
                                    cpg += 1

                    # KHAZANA (Simplified loop structure)
                    prog_id = details.get("data", {}).get("khazanaProgramId")
                    if prog_id:
                        filters = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/filters?page=1&limit=20", PW_HDR)
                        subjects = [{"_id": o["value"], "name": o["name"]} for f in filters.get("data",{}).get("filters",[]) if f.get("key") == "subjectId" for o in f.get("options",[])[1:]]
                        for sub in subjects:
                            sid, sname = sub["_id"], self.safe_name(sub["name"])
                            ch_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/list?page=1&limit=20", PW_HDR)
                            for ch in ch_data.get("data", []):
                                cid, cname = ch["_id"], self.safe_name(ch.get("name", "Ch"))
                                top_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/list?page=1&limit=20", PW_HDR)
                                for top in top_data.get("data", []):
                                    tid, tname = top["_id"], self.safe_name(top.get("name", "Top"))
                                    sub_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/{tid}/contents/sub-topic?page=1&limit=20", PW_HDR)
                                    for st in sub_data.get("data", []):
                                        stid, stname = st["_id"], self.safe_name(st.get("name", "Sub"))
                                        full_chap_name = f"{cname} -> {tname} -> {stname}"
                                        cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/{tid}/sub-topic/{stid}/contents?page=1&limit=50", PW_HDR)
                                        
                                        async def fetch_kz(item):
                                            if item["type"] == "LECTURE":
                                                d = item["data"]
                                                video_url = d.get("videoUrl") or d.get("videoDetails", {}).get("embedCode", "")
                                                title = self.safe_name(d.get("title") or d.get("name") or "VAULT_VID")
                                                try:
                                                    async with sem:
                                                        html = await self._fetch_text(session, f"https://rarestudy.in/khazana-video?parentId={prog_id}&childId={d.get('_id','')}&videoUrl={quote(video_url)}&topicName={quote(title)}")
                                                        token = re.search(r'const MEDIA_TOKEN\s*=\s*"([^"]+)"', html)
                                                        if token:
                                                            v_data = await self._fetch_json(session, f"https://rarestudy.in/v1/videos/video-url-details?mediaToken={quote(token.group(1))}&videoContainerType=DASH")
                                                            return f"KHAZANA | {sname} | {full_chap_name} | {title} | {encrypt_url(v_data['data']['url'])} | KEY: {v_data['data']['keys'][0].split(':')[1]} | TYPE: .mpd\n"
                                                except Exception: pass
                                            elif item["type"] == "NOTES":
                                                url = (item["data"].get("fileId", {}).get("baseUrl", "") + item["data"].get("fileId", {}).get("key", ""))
                                                if url: return f"KHAZANA | {sname} | {full_chap_name} | {self.safe_name(item['data'].get('title','DOC'))} | {encrypt_url(url)} | NONE | TYPE: .pdf\n"
                                            return None

                                        for res in await asyncio.gather(*[fetch_kz(i) for i in cont.get("data", [])]):
                                            if res: f.write(res); f.flush()
                return file_name, None
        except Exception as e:
            return None, str(e)
