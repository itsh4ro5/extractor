import asyncio, aiohttp, re, time, os, logging, traceback
from urllib.parse import quote
from yarl import URL
from core.crypto import encrypt_url

MAX_CONCURRENT_REQUESTS = 30 

logger = logging.getLogger("PWExtractor")

class PWExtractor:
    def __init__(self):
        self.platform_name = "PhysicsWallah"
        self.stop_flags = {}
        self.last_error = "Running smoothly... 🟢"

    def set_stop(self, user_id: int):
        self.stop_flags[user_id] = True
        self.last_error = "🛑 STOP COMMAND RECEIVED!"

    def _should_stop(self, user_id: int) -> bool:
        return self.stop_flags.get(user_id, False)

    async def can_handle(self, url: str) -> bool:
        return "pw.live" in url

    def safe_name(self, s: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', str(s)).strip('.')[:200]

    async def _fetch_text(self, session, url, headers=None, retries=3):
    default_headers = {
        "Referer": "https://rarestudy.in/",
        "Origin": "https://rarestudy.in",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
    }
    if headers:
        default_headers.update(headers)
    for i in range(retries):
        try:
            async with session.get(url, headers=default_headers, timeout=15) as r:
                r.raise_for_status()
                return await r.text()
        except Exception as e:
            if i == retries - 1: raise
            await asyncio.sleep(1)

    # _fetch_json को भी इसी तरह
    async def _fetch_json(self, session, url, headers=None, retries=3):
        default_headers = {
            "Referer": "https://rarestudy.in/",
            "Origin": "https://rarestudy.in",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:152.0) Gecko/20100101 Firefox/152.0"
        }
        if headers:
            default_headers.update(headers)
        for i in range(retries):
            try:
                async with session.get(url, headers=default_headers, timeout=15) as r:
                    r.raise_for_status()
                    return await r.json()
            except Exception as e:
                if i == retries - 1: raise
                await asyncio.sleep(1)

    async def resolve_batch_id(self, session, url):
        html = await self._fetch_text(session, url)
        b_ids = re.findall(r'(?i)batch[_\-]?id[^\w]+([a-f0-9]{24})', html) or re.findall(r'(?i)_id[^\w]+([a-f0-9]{24})', html)
        if b_ids:
            from collections import Counter
            return Counter(b_ids).most_common(1)[0][0]
        raise Exception("ID not found in URL")

    async def resolve_pdf_url(self, session, batch_id, subject_id, schedule_id, note_index, is_dpp):
        url = f"https://rarestudy.in/schedule-details?batchId={batch_id}&subjectId={subject_id}&scheduleId={schedule_id}&tap=note&noteIndex={note_index}&isDpp={'true' if is_dpp else 'false'}"
        try:
            async with session.get(url, allow_redirects=False, timeout=15) as resp:
                if resp.status in (301, 302, 303, 307, 308): return resp.headers.get("Location")
                return None
        except: return None

    async def _process_in_batches(self, tasks, batch_size=MAX_CONCURRENT_REQUESTS):
        results = []
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i:i+batch_size]
            res = await asyncio.gather(*batch, return_exceptions=True)
            for item in res:
                if not isinstance(item, Exception) and item is not None:
                    if isinstance(item, list): results.extend(item)
                    else: results.append(item)
                elif isinstance(item, Exception):
                    logger.debug(f"Task Error: {item}")
        return results

    # Returns (file_name, caption_text, error_message)
    async def extract(self, url: str, status_msg, jwt_token: str, session_cookie: str, choice: str, user_name: str, user_id: int) -> tuple[str, str, str]:
        self.stop_flags[user_id] = False
        self.last_error = "Starting Extraction... 🟢"
        
        jar = aiohttp.CookieJar()
        jar.update_cookies({"session": session_cookie}, URL("https://rarestudy.in"))
        pw_headers = {"authorization": f"Bearer {jwt_token}", "client-version": "538", "content-type": "application/json"}
        
        conn = aiohttp.TCPConnector(limit=MAX_CONCURRENT_REQUESTS)
        
        try:
            async with aiohttp.ClientSession(cookie_jar=jar, headers={"User-Agent": "Mozilla/5.0"}, connector=conn) as session:
                batch_id = await self.resolve_batch_id(session, url)
                details = await self._fetch_json(session, f"https://api.penpencil.co/v3/batches/{batch_id}/details", pw_headers)
                batch_name = self.safe_name(details.get("data", {}).get("name", batch_id))
                file_name = f"{batch_name}.txt"
                
                vid_count = 0
                pdf_count = 0
                all_links = []
                last_edit_time = time.time()

                async def update_status(current_sub):
                    nonlocal last_edit_time
                    if time.time() - last_edit_time > 5:
                        try:
                            await status_msg.edit_text(
                                f"⏳ **Extraction in Progress...** ⚡\n\n"
                                f"📘 **Subject:** `{current_sub}`\n"
                                f"🎥 **Videos Extracted:** `{vid_count}`\n"
                                f"📄 **PDFs Extracted:** `{pdf_count}`\n\n"
                                f"📝 **Live Log:** `{self.last_error}`\n\n"
                                f"*(Running... Send /stop_extract to halt)*"
                            )
                            last_edit_time = time.time()
                        except: pass

                # ================= MAIN CONTENT =================
                if choice in ['1', '3']:
                    for sub in details.get("data", {}).get("subjects", []):
                        if self._should_stop(user_id): break
                        sid, sname = sub["_id"], self.safe_name(sub["subject"])
                        await update_status(sname)
                        
                        topics = []; pg = 1
                        while True:
                            tdata = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/topics?page={pg}", pw_headers)
                            if not tdata.get("data"): break
                            topics.extend(tdata.get("data", []))
                            if len(tdata.get("data", [])) < 20: break
                            pg += 1
                            
                        for top in topics:
                            if self._should_stop(user_id): break
                            tid, tname = top["_id"], self.safe_name(top["name"])
                            
                            for ctype in ("videos", "DppVideos"):
                                cpg = 1
                                while True:
                                    cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/contents?page={cpg}&contentType={ctype}&tag={tid}", pw_headers)
                                    items = cont.get("data", [])
                                    if not items: break
                                    
                                    async def fetch_vid(item):
                                        sched_id = item["_id"]
                                        title = self.safe_name(item.get("topic") or item.get("videoDetails", {}).get("name") or sched_id)
                                        try:
                                            html = await self._fetch_text(session, f"https://rarestudy.in/schedule-details?batchId={batch_id}&subjectId={sid}&scheduleId={sched_id}&tap=video")
                                            token = re.search(r'const MEDIA_TOKEN\s*=\s*"([^"]+)"', html)
                                            if token:
                                                v_data = await self._fetch_json(session, f"https://rarestudy.in/v1/videos/video-url-details?mediaToken={quote(token.group(1))}&videoContainerType=DASH")
                                                mpd_url = v_data["data"]["url"]
                                                key_hex = v_data["data"]["keys"][0].split(":")[1]
                                                return f"MAIN | {sname} | {tname} | {title} | {encrypt_url(mpd_url)} | KEY: {key_hex} | TYPE: .mpd\n"
                                            else:
                                                self.last_error = f"❌ API Blocked / Cookie Expired!"
                                        except Exception as e:
                                            self.last_error = f"⚠️ Vid Fetch Error: {str(e)[:30]}"
                                        return None

                                    tasks = [fetch_vid(i) for i in items]
                                    results = await self._process_in_batches(tasks)
                                    for res in results:
                                        all_links.append(res)
                                        if "TYPE: .mpd" in res: vid_count += 1
                                        
                                    await update_status(sname)
                                    if len(items) < 20: break
                                    cpg += 1
                                    
                            for ctype, is_dpp in [("notes", False), ("DppNotes", True)]:
                                cpg = 1
                                while True:
                                    cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/batches/{batch_id}/subject/{sid}/contents?page={cpg}&contentType={ctype}&tag={tid}", pw_headers)
                                    items = cont.get("data", [])
                                    if not items: break
                                    
                                    async def fetch_pdf(item):
                                        sched_id = item["_id"]
                                        links = []
                                        if not is_dpp:
                                            for att_idx, att in enumerate(item.get("attachmentIds", [])):
                                                pdf_url = await self.resolve_pdf_url(session, batch_id, sid, sched_id, att_idx, False)
                                                if pdf_url: links.append(f"MAIN | {sname} | {tname} | {self.safe_name(att.get('name') or 'NOTE')} | {encrypt_url(pdf_url)} | NONE | TYPE: .pdf\n")
                                        else:
                                            for hw_idx, hw in enumerate(item.get("homeworkIds", [])):
                                                for att_idx, att in enumerate(hw.get("attachmentIds", [])):
                                                    g_idx = sum(len(item["homeworkIds"][i].get("attachmentIds", [])) for i in range(hw_idx)) + att_idx
                                                    pdf_url = await self.resolve_pdf_url(session, batch_id, sid, sched_id, g_idx, True)
                                                    if pdf_url: links.append(f"MAIN | {sname} | {tname} | {self.safe_name(att.get('name') or 'NOTE')} | {encrypt_url(pdf_url)} | NONE | TYPE: .pdf\n")
                                        return links

                                    tasks = [fetch_pdf(i) for i in items]
                                    results = await self._process_in_batches(tasks)
                                    for res in results:
                                        all_links.append(res)
                                        if "TYPE: .pdf" in res: pdf_count += 1
                                        
                                    await update_status(sname)
                                    if len(items) < 20: break
                                    cpg += 1

                # ================= KHAZANA CONTENT =================
                prog_id = details.get("data", {}).get("khazanaProgramId")
                if prog_id and choice in ['2', '3'] and not self._should_stop(user_id):
                    filters = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/filters?page=1&limit=20", pw_headers)
                    subjects = [{"_id": o["value"], "name": o["name"]} for f in filters.get("data",{}).get("filters",[]) if f.get("key") == "subjectId" for o in f.get("options",[])[1:]]
                    
                    for sub in subjects:
                        if self._should_stop(user_id): break
                        sid, sname = sub["_id"], self.safe_name(sub["name"])
                        await update_status(f"Khazana: {sname}")
                        ch_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/list?page=1&limit=20", pw_headers)
                        for ch in ch_data.get("data", []):
                            if self._should_stop(user_id): break
                            cid, cname = ch["_id"], self.safe_name(ch.get("name", "Ch"))
                            top_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/list?page=1&limit=20", pw_headers)
                            for top in top_data.get("data", []):
                                tid, tname = top["_id"], self.safe_name(top.get("name", "Top"))
                                sub_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/{tid}/contents/sub-topic?page=1&limit=20", pw_headers)
                                for st in sub_data.get("data", []):
                                    stid, stname = st["_id"], self.safe_name(st.get("name", "Sub"))
                                    full_chap_name = f"{cname} -> {tname} -> {stname}"
                                    cont = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/{cid}/topics/{tid}/sub-topic/{stid}/contents?page=1&limit=50", pw_headers)
                                    
                                    async def fetch_kz(item):
                                        if item["type"] == "LECTURE":
                                            d = item["data"]
                                            video_url = d.get("videoUrl") or d.get("videoDetails", {}).get("embedCode", "")
                                            title = self.safe_name(d.get("title") or d.get("name") or "VAULT_VID")
                                            try:
                                                html = await self._fetch_text(session, f"https://rarestudy.in/khazana-video?parentId={prog_id}&childId={d.get('_id','')}&videoUrl={quote(video_url)}&topicName={quote(title)}")
                                                token = re.search(r'const MEDIA_TOKEN\s*=\s*"([^"]+)"', html)
                                                if token:
                                                    v_data = await self._fetch_json(session, f"https://rarestudy.in/v1/videos/video-url-details?mediaToken={quote(token.group(1))}&videoContainerType=DASH")
                                                    mpd_url = v_data["data"]["url"]
                                                    key_hex = v_data["data"]["keys"][0].split(":")[1]
                                                    return f"KHAZANA | {sname} | {full_chap_name} | {title} | {encrypt_url(mpd_url)} | KEY: {key_hex} | TYPE: .mpd\n"
                                            except Exception as e: self.last_error = f"⚠️ KZ Error: {str(e)[:30]}"
                                        elif item["type"] == "NOTES":
                                            url = (item["data"].get("fileId", {}).get("baseUrl", "") + item["data"].get("fileId", {}).get("key", ""))
                                            if url: return f"KHAZANA | {sname} | {full_chap_name} | {self.safe_name(item['data'].get('title','DOC'))} | {encrypt_url(url)} | NONE | TYPE: .pdf\n"
                                        return None

                                    tasks = [fetch_kz(i) for i in cont.get("data", [])]
                                    results = await self._process_in_batches(tasks)
                                    for res in results:
                                        all_links.append(res)
                                        if "TYPE: .mpd" in res: vid_count += 1
                                        elif "TYPE: .pdf" in res: pdf_count += 1
                                        
                                    await update_status(f"Khazana: {sname}")
                
                type_map = {'1': 'Main', '2': 'Khazana', '3': 'Main + Khazana'}
                ext_type = type_map.get(choice, 'Unknown')
                
                # 🔥 YEH CAPTION BOT KO RETURN HOGA (FILE ME NAHI LIKHEGA) 🔥
                caption_text = (
                    f"**Batch Name -** `{batch_name}`\n"
                    f"**Batch ID -** `{batch_id}`\n"
                    f"**Type -** `{ext_type}`\n"
                    f"**Number of Video -** `{vid_count}`\n"
                    f"**Number of PDF -** `{pdf_count}`\n"
                    f"**Extracted By -** {user_name}"
                )
                
                if self._should_stop(user_id):
                    caption_text = "⚠️ **EXTRACTION STOPPED (INCOMPLETE DATA)** ⚠️\n\n" + caption_text

                # 🔥 FILE ME SIRF LINKS LIKHE JAYENGE 🔥
                with open(file_name, "w", encoding="utf-8") as f:
                    for link in all_links:
                        f.write(link)

                return file_name, caption_text, None
            
        except Exception as e:
            err_log = traceback.format_exc()
            return None, None, err_log
