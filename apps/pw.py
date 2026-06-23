import asyncio, aiohttp, re, base64, time, os
from urllib.parse import quote
from yarl import URL
from core.crypto import encrypt_url

MAX_CONCURRENT_REQUESTS = 20

class PWExtractor:
    def __init__(self):
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

    # YAHAN CHANGE HUA HAI: user_name aur Counters add kiye hain
    async def extract(self, url: str, status_msg, jwt_token: str, session_cookie: str, choice: str, user_name: str) -> tuple[str, str]:
        jar = aiohttp.CookieJar()
        jar.update_cookies({"session": session_cookie}, URL("https://rarestudy.in"))
        pw_headers = {"authorization": f"Bearer {jwt_token}", "client-version": "538", "content-type": "application/json"}
        
        try:
            async with aiohttp.ClientSession(cookie_jar=jar, headers={"User-Agent": "Mozilla/5.0"}) as session:
                batch_id = await self.resolve_batch_id(session, url)
                details = await self._fetch_json(session, f"https://api.penpencil.co/v3/batches/{batch_id}/details", pw_headers)
                batch_name = self.safe_name(details.get("data", {}).get("name", batch_id))
                file_name = f"{batch_name}.txt" # Sirf batch name
                
                sem = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
                
                # Counters & Variables
                vid_count = 0
                pdf_count = 0
                all_links = []
                last_edit_time = time.time()

                async def update_status(current_sub):
                    nonlocal last_edit_time
                    if time.time() - last_edit_time > 10:
                        try:
                            await status_msg.edit_text(
                                f"⏳ **Extraction in Progress...**\n\n"
                                f"📘 **Subject:** `{current_sub}`\n"
                                f"🎥 **Videos Extracted:** `{vid_count}`\n"
                                f"📄 **PDFs Extracted:** `{pdf_count}`\n\n"
                                f"*(Live updating every 10 seconds)*"
                            )
                            last_edit_time = time.time()
                        except: pass

                # 1. MAIN CONTENT
                if choice in ['1', '3']:
                    for sub in details.get("data", {}).get("subjects", []):
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
                                        if res: 
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
                                        for res in link_list:
                                            all_links.append(res)
                                            if "TYPE: .pdf" in res: pdf_count += 1
                                    await update_status(sname)
                                    if len(items) < 20: break
                                    cpg += 1

                # 2. KHAZANA CONTENT
                prog_id = details.get("data", {}).get("khazanaProgramId")
                if prog_id and choice in ['2', '3']:
                    filters = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/filters?page=1&limit=20", pw_headers)
                    subjects = [{"_id": o["value"], "name": o["name"]} for f in filters.get("data",{}).get("filters",[]) if f.get("key") == "subjectId" for o in f.get("options",[])[1:]]
                    
                    for sub in subjects:
                        sid, sname = sub["_id"], self.safe_name(sub["name"])
                        await update_status(f"Khazana: {sname}")
                        ch_data = await self._fetch_json(session, f"https://api.penpencil.co/v2/programs/{prog_id}/subjects/{sid}/chapters/list?page=1&limit=20", pw_headers)
                        for ch in ch_data.get("data", []):
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
                                                async with sem:
                                                    html = await self._fetch_text(session, f"https://rarestudy.in/khazana-video?parentId={prog_id}&childId={d.get('_id','')}&videoUrl={quote(video_url)}&topicName={quote(title)}")
                                                    token = re.search(r'const MEDIA_TOKEN\s*=\s*"([^"]+)"', html)
                                                    if token:
                                                        v_data = await self._fetch_json(session, f"https://rarestudy.in/v1/videos/video-url-details?mediaToken={quote(token.group(1))}&videoContainerType=DASH")
                                                        mpd_url = v_data["data"]["url"]
                                                        key_hex = v_data["data"]["keys"][0].split(":")[1]
                                                        return f"KHAZANA | {sname} | {full_chap_name} | {title} | {encrypt_url(mpd_url)} | KEY: {key_hex} | TYPE: .mpd\n"
                                            except Exception: pass
                                        elif item["type"] == "NOTES":
                                            url = (item["data"].get("fileId", {}).get("baseUrl", "") + item["data"].get("fileId", {}).get("key", ""))
                                            if url: return f"KHAZANA | {sname} | {full_chap_name} | {self.safe_name(item['data'].get('title','DOC'))} | {encrypt_url(url)} | NONE | TYPE: .pdf\n"
                                        return None

                                    for res in await asyncio.gather(*[fetch_kz(i) for i in cont.get("data", [])]):
                                        if res:
                                            all_links.append(res)
                                            if "TYPE: .mpd" in res: vid_count += 1
                                            elif "TYPE: .pdf" in res: pdf_count += 1
                                    await update_status(f"Khazana: {sname}")
                
                # PREPARING FINAL TXT FILE WITH HEADER
                type_map = {'1': 'Main', '2': 'Khazana', '3': 'Main + Khazana'}
                ext_type = type_map.get(choice, 'Unknown')
                
                header_text = (
                    f"Batch Name - {batch_name}\n"
                    f"Type - {ext_type}\n"
                    f"Number of Video - {vid_count}\n"
                    f"Number of PDF - {pdf_count}\n"
                    f"Extracted By - {user_name}\n"
                    f"==================================================\n\n"
                )
                
                with open(file_name, "w", encoding="utf-8") as f:
                    f.write(header_text)
                    for link in all_links:
                        f.write(link)

                return file_name, None
        except Exception as e:
            return None, str(e)
