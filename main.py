import os
import re
import asyncio
import json
import random
import traceback
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError,
    ChatWriteForbiddenError,
    UserBannedInChannelError,
    ChannelPrivateError,
    SlowModeWaitError,
    ChatAdminRequiredError,
    ChatRestrictedError,
    PeerFloodError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.types import Channel, Chat
import aiohttp

API_ID = int(os.getenv("API_ID", "6"))
API_HASH = os.getenv("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
SECRET_KEY = os.getenv("SECRET_KEY", "MySecret2026BotXYZ")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8248647747"))

SESSIONS_DIR = "sessions"
DATA_FILE = "data.json"
os.makedirs(SESSIONS_DIR, exist_ok=True)

active_clients = {}
running_tasks = {}
user_data = {}
stats_data = {}
broadcast_tasks = {}
reset_tasks = {}

def load_data():
    global user_data
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
        except:
            user_data = {}

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

load_data()
app = FastAPI(title="Bot API", version="3.0")

def check_auth(key: str):
    if key != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
async def root():
    return {
        "status": "Bot Running",
        "version": "3.0",
        "active_users": len(active_clients),
        "running_tasks": len(running_tasks),
        "broadcast_tasks": len(broadcast_tasks),
        "reset_tasks": len(reset_tasks)
    }

# ========== TABCHI - SEND CODE ==========
class SendCodeReq(BaseModel):
    key: str
    user_id: int
    phone: str

@app.post("/send_code")
async def send_code(req: SendCodeReq):
    check_auth(req.key)
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if await client.is_user_authorized():
            await client.disconnect()
            return {"ok": True, "already_authed": True}
        result = await client.send_code_request(req.phone)
        user_data[str(req.user_id)] = {
            "phone": req.phone,
            "phone_code_hash": result.phone_code_hash,
            "banner": None,
            "interval": 5,
            "groups": [],
            "groups_data": [],
            "group_names": []
        }
        save_data()
        await client.disconnect()
        return {"ok": True, "message": "کد ارسال شد"}
    except PhoneNumberInvalidError:
        try: await client.disconnect()
        except: pass
        return {"ok": False, "error": "شماره نامعتبر"}
    except FloodWaitError as e:
        try: await client.disconnect()
        except: pass
        return {"ok": False, "error": f"صبر کنید {e.seconds} ثانیه"}
    except Exception as e:
        try: await client.disconnect()
        except: pass
        return {"ok": False, "error": str(e)}

# ========== TABCHI - VERIFY CODE ==========
class VerifyCodeReq(BaseModel):
    key: str
    user_id: int
    code: str = ""
    password: str = ""

@app.post("/verify_code")
async def verify_code(req: VerifyCodeReq):
    check_auth(req.key)
    uid = str(req.user_id)
    if uid not in user_data and req.code:
        return {"ok": False, "error": "ابتدا شماره را ارسال کنید"}
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if req.code:
            try:
                await client.sign_in(
                    phone=user_data[uid]["phone"],
                    code=req.code,
                    phone_code_hash=user_data[uid]["phone_code_hash"]
                )
            except SessionPasswordNeededError:
                await client.disconnect()
                return {"ok": False, "need_password": True, "error": "پسورد ۲ مرحله‌ای نیاز است"}
            except PhoneCodeInvalidError:
                await client.disconnect()
                return {"ok": False, "error": "کد اشتباه است"}
        elif req.password:
            await client.sign_in(password=req.password)
        else:
            await client.disconnect()
            return {"ok": False, "error": "کد یا پسورد لازم است"}
        me = await client.get_me()
        await client.disconnect()
        return {"ok": True, "message": f"وارد شدید: {me.first_name}", "name": me.first_name}
    except Exception as e:
        try: await client.disconnect()
        except: pass
        return {"ok": False, "error": str(e)}

# ========== TABCHI - SET BANNER ==========
class SetBannerReq(BaseModel):
    key: str
    user_id: int
    banner: str

@app.post("/set_banner")
async def set_banner(req: SetBannerReq):
    check_auth(req.key)
    uid = str(req.user_id)
    if uid not in user_data:
        user_data[uid] = {}
    user_data[uid]["banner"] = req.banner
    save_data()
    return {"ok": True, "message": "بنر ذخیره شد"}

# ========== TABCHI - SET INTERVAL ==========
class SetIntervalReq(BaseModel):
    key: str
    user_id: int
    interval: int

@app.post("/set_interval")
async def set_interval(req: SetIntervalReq):
    check_auth(req.key)
    uid = str(req.user_id)
    if uid not in user_data:
        user_data[uid] = {}
    user_data[uid]["interval"] = max(1, req.interval)
    save_data()
    return {"ok": True, "message": f"زمان {req.interval} دقیقه تنظیم شد"}

# ========== TABCHI - JOIN GROUPS ==========
class JoinGroupsReq(BaseModel):
    key: str
    user_id: int

@app.post("/join_groups")
async def join_groups(req: JoinGroupsReq):
    check_auth(req.key)
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            return {"ok": False, "error": "ابتدا وارد شوید"}
        my_groups = []
        can_send = []
        cannot_send = []
        async for dialog in client.iter_dialogs():
            entity = dialog.entity
            group_info = None
            if isinstance(entity, Channel):
                if entity.megagroup:
                    is_banned = False
                    default_banned = getattr(entity, 'default_banned_rights', None)
                    if default_banned and default_banned.send_messages:
                        is_banned = True
                    group_info = {"id": entity.id, "title": entity.title, "username": entity.username, "type": "supergroup", "can_send": not is_banned}
            elif isinstance(entity, Chat):
                if not getattr(entity, 'deactivated', False):
                    group_info = {"id": entity.id, "title": entity.title, "username": None, "type": "chat", "can_send": True}
            if group_info:
                my_groups.append(group_info)
                if group_info["can_send"]:
                    can_send.append(group_info)
                else:
                    cannot_send.append(group_info)
        uid = str(req.user_id)
        if uid not in user_data:
            user_data[uid] = {}
        user_data[uid]["groups_data"] = my_groups
        user_data[uid]["groups"] = [g["id"] for g in my_groups if g["can_send"]]
        user_data[uid]["group_names"] = [g["title"] for g in my_groups]
        save_data()
        await client.disconnect()
        return {"ok": True, "joined": len(my_groups), "can_send": len(can_send), "cannot_send": len(cannot_send), "failed": 0, "groups": [g["title"] for g in my_groups[:20]]}
    except Exception as e:
        try: await client.disconnect()
        except: pass
        return {"ok": False, "error": str(e)}

# ========== AUTO JOIN HELPERS ==========
def extract_channels_from_text(text):
    if not text:
        return []
    channels = set()
    usernames = re.findall(r'@([a-zA-Z][a-zA-Z0-9_]{3,31})', str(text))
    for u in usernames:
        channels.add(u)
    tme_links = re.findall(r't\.me/(?:joinchat/|\+)?([a-zA-Z0-9_\-]+)', str(text))
    for link in tme_links:
        channels.add(link)
    return list(channels)

async def try_auto_join(client, error_msg):
    channels = extract_channels_from_text(error_msg)
    joined = []
    for ch in channels[:5]:
        try:
            if len(ch) > 15:
                try:
                    await client(ImportChatInviteRequest(ch))
                    joined.append(ch)
                    await asyncio.sleep(random.uniform(3, 6))
                    continue
                except:
                    pass
            try:
                await client(JoinChannelRequest(ch))
                joined.append(ch)
                await asyncio.sleep(random.uniform(3, 6))
            except:
                pass
        except:
            pass
    return joined

async def send_to_group(client, group_id, banner):
    try:
        entity = await client.get_entity(group_id)
        await client.send_message(entity, banner)
        return {"success": True, "auto_joined": []}
    except (ChatWriteForbiddenError, ChatRestrictedError) as e:
        err_msg = str(e)
        auto_joined = []
        try:
            entity = await client.get_entity(group_id)
            try:
                if isinstance(entity, Channel):
                    full = await client(GetFullChannelRequest(entity))
                    about = full.full_chat.about
                    if about:
                        joined = await try_auto_join(client, about)
                        if joined:
                            auto_joined.extend(joined)
            except:
                pass
            if not auto_joined:
                async for msg in client.iter_messages(entity, limit=20):
                    if msg.text:
                        joined = await try_auto_join(client, msg.text)
                        if joined:
                            auto_joined.extend(joined)
                            break
            if auto_joined:
                await asyncio.sleep(5)
                try:
                    await client.send_message(entity, banner)
                    return {"success": True, "auto_joined": auto_joined}
                except Exception as e2:
                    return {"success": False, "auto_joined": auto_joined, "error": str(e2)[:80]}
            return {"success": False, "auto_joined": [], "error": "فقط ادمین حق ارسال داره"}
        except Exception as ee:
            return {"success": False, "auto_joined": [], "error": str(ee)[:100]}
    except UserBannedInChannelError:
        return {"success": False, "auto_joined": [], "error": "بن شدید"}
    except ChatAdminRequiredError:
        return {"success": False, "auto_joined": [], "error": "نیاز به ادمین"}
    except PeerFloodError:
        return {"success": False, "auto_joined": [], "error": "PeerFlood", "critical": True}
    except FloodWaitError as e:
        return {"success": False, "auto_joined": [], "error": f"FloodWait {e.seconds}s", "wait": e.seconds}
    except SlowModeWaitError as e:
        return {"success": False, "auto_joined": [], "error": f"SlowMode {e.seconds}s"}
    except ChannelPrivateError:
        return {"success": False, "auto_joined": [], "error": "گروه خصوصی"}
    except Exception as e:
        return {"success": False, "auto_joined": [], "error": str(e)[:100]}

# ========== SEND LOOP ==========
async def send_loop(user_id: int):
    uid = str(user_id)
    session_path = os.path.join(SESSIONS_DIR, f"{user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return
        active_clients[user_id] = client
        print(f"✅ Loop started {user_id}")
        while user_id in running_tasks:
            data = user_data.get(uid, {})
            banner = data.get("banner")
            groups = data.get("groups", [])
            interval = data.get("interval", 5)
            if not banner or not groups:
                await asyncio.sleep(30)
                continue
            sent = 0
            failed = 0
            all_auto_joined = []
            errors = []
            critical_stop = False
            shuffled = groups.copy()
            random.shuffle(shuffled)
            for grp in shuffled:
                if user_id not in running_tasks:
                    break
                result = await send_to_group(client, grp, banner)
                if result["success"]:
                    sent += 1
                else:
                    failed += 1
                    errors.append({"group": str(grp), "error": result.get("error", "?")})
                    if result.get("critical"):
                        critical_stop = True
                        break
                if result.get("auto_joined"):
                    all_auto_joined.extend(result["auto_joined"])
                if result.get("wait"):
                    await asyncio.sleep(min(result["wait"] + 5, 120))
                else:
                    await asyncio.sleep(random.uniform(8, 20))
            stats_data[uid] = {
                "last_run": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "sent": sent, "failed": failed,
                "auto_joined": all_auto_joined,
                "errors": errors[:15],
                "total_groups": len(groups),
                "critical_stop": critical_stop
            }
            print(f"📊 {user_id}: sent={sent}, failed={failed}")
            if critical_stop:
                await asyncio.sleep(1800)
            elif user_id in running_tasks:
                await asyncio.sleep(interval * 60)
    except Exception as e:
        print(f"Loop error {user_id}: {e}")
    finally:
        if user_id in active_clients:
            del active_clients[user_id]
        try: await client.disconnect()
        except: pass

# ========== START/STOP/STATUS/LOGOUT ==========
class StartReq(BaseModel):
    key: str
    user_id: int

@app.post("/start")
async def start(req: StartReq):
    check_auth(req.key)
    if req.user_id in running_tasks:
        return {"ok": False, "error": "قبلاً در حال اجراست"}
    task = asyncio.create_task(send_loop(req.user_id))
    running_tasks[req.user_id] = task
    return {"ok": True, "message": "شروع شد"}

@app.post("/stop")
async def stop(req: StartReq):
    check_auth(req.key)
    if req.user_id in running_tasks:
        del running_tasks[req.user_id]
        return {"ok": True, "message": "متوقف شد"}
    return {"ok": False, "error": "در حال اجرا نبود"}

@app.post("/status")
async def status(req: StartReq):
    check_auth(req.key)
    uid = str(req.user_id)
    data = user_data.get(uid, {})
    stats = stats_data.get(uid, {})
    return {
        "ok": True,
        "logged_in": os.path.exists(os.path.join(SESSIONS_DIR, f"{req.user_id}.session")),
        "running": req.user_id in running_tasks,
        "banner": bool(data.get("banner")),
        "groups": len(data.get("groups", [])),
        "interval": data.get("interval", 5),
        "group_names": data.get("group_names", [])[:15],
        "last_sent": stats.get("sent", 0),
        "last_failed": stats.get("failed", 0),
        "total_groups": stats.get("total_groups", 0),
        "auto_joined_count": len(stats.get("auto_joined", [])),
        "errors": stats.get("errors", [])[:8],
        "last_run": stats.get("last_run", "-"),
        "critical_stop": stats.get("critical_stop", False)
    }

@app.post("/logout")
async def logout(req: StartReq):
    check_auth(req.key)
    if req.user_id in running_tasks:
        del running_tasks[req.user_id]
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}.session")
    if os.path.exists(session_path):
        os.remove(session_path)
    uid = str(req.user_id)
    if uid in user_data:
        del user_data[uid]
        save_data()
    return {"ok": True, "message": "خروج انجام شد"}

# ========== BROADCAST ==========
class BroadcastReq(BaseModel):
    key: str
    bot_token: str
    user_ids: list
    text: str = ""
    photo_id: str = ""
    video_id: str = ""
    doc_id: str = ""
    sticker_id: str = ""
    voice_id: str = ""
    caption: str = ""

async def send_one_bc(session, bot_token, uid, msg):
    try:
        uid = int(uid)
        if msg.get("text"):
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": uid, "text": msg["text"]}
        elif msg.get("photo_id"):
            url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            payload = {"chat_id": uid, "photo": msg["photo_id"], "caption": msg.get("caption", "")}
        elif msg.get("video_id"):
            url = f"https://api.telegram.org/bot{bot_token}/sendVideo"
            payload = {"chat_id": uid, "video": msg["video_id"], "caption": msg.get("caption", "")}
        elif msg.get("doc_id"):
            url = f"https://api.telegram.org/bot{bot_token}/sendDocument"
            payload = {"chat_id": uid, "document": msg["doc_id"], "caption": msg.get("caption", "")}
        elif msg.get("sticker_id"):
            url = f"https://api.telegram.org/bot{bot_token}/sendSticker"
            payload = {"chat_id": uid, "sticker": msg["sticker_id"]}
        elif msg.get("voice_id"):
            url = f"https://api.telegram.org/bot{bot_token}/sendVoice"
            payload = {"chat_id": uid, "voice": msg["voice_id"]}
        else:
            return False
        async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            data = await resp.json()
            return data.get("ok", False)
    except:
        return False

async def do_bc_task(bot_token, user_ids, msg, task_id):
    ok = 0
    fail = 0
    total = len(user_ids)
    broadcast_tasks[task_id] = {"total": total, "ok": 0, "fail": 0, "done": False}
    print(f"📨 BC {task_id}: {total} users")
    connector = aiohttp.TCPConnector(limit=50)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, total, 30):
            batch = user_ids[i:i+30]
            tasks = [send_one_bc(session, bot_token, uid, msg) for uid in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if r is True:
                    ok += 1
                else:
                    fail += 1
            broadcast_tasks[task_id]["ok"] = ok
            broadcast_tasks[task_id]["fail"] = fail
            await asyncio.sleep(1)
    broadcast_tasks[task_id]["done"] = True
    print(f"✅ BC {task_id}: ok={ok}, fail={fail}")

@app.post("/broadcast")
async def broadcast(req: BroadcastReq):
    check_auth(req.key)
    task_id = f"bc_{int(datetime.now().timestamp())}"
    msg = {"text": req.text, "photo_id": req.photo_id, "video_id": req.video_id, "doc_id": req.doc_id, "sticker_id": req.sticker_id, "voice_id": req.voice_id, "caption": req.caption}
    asyncio.create_task(do_bc_task(req.bot_token, req.user_ids, msg, task_id))
    return {"ok": True, "task_id": task_id, "total": len(req.user_ids)}

class BCStatusReq(BaseModel):
    key: str
    task_id: str

@app.post("/broadcast_status")
async def bc_status(req: BCStatusReq):
    check_auth(req.key)
    if req.task_id in broadcast_tasks:
        return {"ok": True, **broadcast_tasks[req.task_id]}
    return {"ok": False, "error": "not found"}

# ========== RESET ALL USERS ==========
class ResetReq(BaseModel):
    key: str
    bot_token: str
    user_ids: list

async def do_reset_task(bot_token, user_ids, task_id):
    total = len(user_ids)
    reset_tasks[task_id] = {"total": total, "done": 0, "status": "running"}
    print(f"🔄 Reset {task_id}: {total} users")
    
    connector = aiohttp.TCPConnector(limit=30)
    async with aiohttp.ClientSession(connector=connector) as session:
        done = 0
        for i in range(0, total, 50):
            batch = user_ids[i:i+50]
            tasks = []
            for uid in batch:
                try:
                    uid = int(uid)
                    # KV رو از Cloudflare Worker صفر میکنیم
                    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                    # فقط track میکنیم
                    done += 1
                except:
                    pass
            reset_tasks[task_id]["done"] = done
            await asyncio.sleep(0.5)
    
    reset_tasks[task_id]["status"] = "done"
    reset_tasks[task_id]["done"] = done
    print(f"✅ Reset {task_id}: {done} tracked")

@app.post("/reset_users")
async def reset_users(req: ResetReq):
    check_auth(req.key)
    task_id = f"rst_{int(datetime.now().timestamp())}"
    asyncio.create_task(do_reset_task(req.bot_token, req.user_ids, task_id))
    return {"ok": True, "task_id": task_id, "total": len(req.user_ids)}

@app.post("/reset_status")
async def reset_status(req: BCStatusReq):
    check_auth(req.key)
    if req.task_id in reset_tasks:
        return {"ok": True, **reset_tasks[req.task_id]}
    return {"ok": False, "error": "not found"}

# ========== HEALTH ==========
@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "time": datetime.now().isoformat(),
        "active_clients": len(active_clients),
        "running_tasks": len(running_tasks),
        "broadcast_tasks": len(broadcast_tasks),
        "reset_tasks": len(reset_tasks)
    }
