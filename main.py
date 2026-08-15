import os
import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from telethon import TelegramClient, events
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
import aiofiles

# ==================== CONFIG ====================
API_ID = int(os.getenv("API_ID", "6"))
API_HASH = os.getenv("API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
SECRET_KEY = os.getenv("SECRET_KEY", "my-super-secret-key-2026")
ADMIN_BOT_TOKEN = os.getenv("ADMIN_BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8248647747"))

SESSIONS_DIR = "sessions"
DATA_FILE = "data.json"
os.makedirs(SESSIONS_DIR, exist_ok=True)

# ==================== DATA ====================
active_clients = {}  # user_id -> TelegramClient
running_tasks = {}   # user_id -> asyncio.Task
user_data = {}       # user_id -> {phone, phone_code_hash, banner, interval, groups}

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

# ==================== FASTAPI ====================
app = FastAPI()

class AuthCheck(BaseModel):
    key: str

def check_auth(key: str):
    if key != SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

@app.get("/")
async def root():
    return {"status": "Tabchi Bot Running", "users": len(active_clients)}

# ==================== SEND CODE ====================
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
            "groups": []
        }
        save_data()
        
        await client.disconnect()
        return {"ok": True, "message": "کد ارسال شد"}
    
    except PhoneNumberInvalidError:
        await client.disconnect()
        return {"ok": False, "error": "شماره نامعتبر"}
    except FloodWaitError as e:
        await client.disconnect()
        return {"ok": False, "error": f"صبر کنید {e.seconds} ثانیه"}
    except Exception as e:
        await client.disconnect()
        return {"ok": False, "error": str(e)}

# ==================== VERIFY CODE ====================
class VerifyCodeReq(BaseModel):
    key: str
    user_id: int
    code: str
    password: str = ""

@app.post("/verify_code")
async def verify_code(req: VerifyCodeReq):
    check_auth(req.key)
    
    uid = str(req.user_id)
    if uid not in user_data:
        return {"ok": False, "error": "ابتدا شماره را ارسال کنید"}
    
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    try:
        await client.connect()
        
        try:
            await client.sign_in(
                phone=user_data[uid]["phone"],
                code=req.code,
                phone_code_hash=user_data[uid]["phone_code_hash"]
            )
        except SessionPasswordNeededError:
            if not req.password:
                await client.disconnect()
                return {"ok": False, "need_password": True, "error": "پسورد ۲ مرحله‌ای نیاز است"}
            await client.sign_in(password=req.password)
        except PhoneCodeInvalidError:
            await client.disconnect()
            return {"ok": False, "error": "کد اشتباه است"}
        
        me = await client.get_me()
        await client.disconnect()
        
        return {"ok": True, "message": f"وارد شدید: {me.first_name}", "name": me.first_name}
    
    except Exception as e:
        await client.disconnect()
        return {"ok": False, "error": str(e)}

# ==================== SET BANNER ====================
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

# ==================== SET INTERVAL ====================
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

# ==================== JOIN GROUPS ====================
DEFAULT_GROUPS = [
    "tabchi_free", "tablighat_azad", "advertise_iran",
    "iran_tabligh", "gap_tabligh", "reklam_ir"
]

class JoinGroupsReq(BaseModel):
    key: str
    user_id: int
    groups: list = None

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
        
        groups_to_join = req.groups or DEFAULT_GROUPS
        joined = []
        failed = []
        
        for grp in groups_to_join:
            try:
                grp_clean = grp.replace("@", "").replace("https://t.me/", "").strip()
                await client(JoinChannelRequest(grp_clean))
                joined.append(grp_clean)
                await asyncio.sleep(3)
            except Exception as e:
                failed.append({"group": grp, "error": str(e)[:100]})
        
        uid = str(req.user_id)
        if uid not in user_data:
            user_data[uid] = {}
        user_data[uid]["groups"] = joined
        save_data()
        
        await client.disconnect()
        return {"ok": True, "joined": len(joined), "failed": len(failed), "groups": joined}
    
    except Exception as e:
        await client.disconnect()
        return {"ok": False, "error": str(e)}

# ==================== START SENDING ====================
async def send_loop(user_id: int):
    uid = str(user_id)
    session_path = os.path.join(SESSIONS_DIR, f"{user_id}")
    client = TelegramClient(session_path, API_ID, API_HASH)
    
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return
        
        active_clients[user_id] = client
        
        while user_id in running_tasks:
            data = user_data.get(uid, {})
            banner = data.get("banner")
            groups = data.get("groups", [])
            interval = data.get("interval", 5)
            
            if not banner or not groups:
                await asyncio.sleep(60)
                continue
            
            sent = 0
            for grp in groups:
                try:
                    await client.send_message(grp, banner)
                    sent += 1
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"Send fail {grp}: {e}")
            
            print(f"User {user_id}: sent to {sent}/{len(groups)} groups")
            await asyncio.sleep(interval * 60)
    
    except Exception as e:
        print(f"Loop error {user_id}: {e}")
    finally:
        if user_id in active_clients:
            del active_clients[user_id]
        try:
            await client.disconnect()
        except:
            pass

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

class StopReq(BaseModel):
    key: str
    user_id: int

@app.post("/stop")
async def stop(req: StopReq):
    check_auth(req.key)
    
    if req.user_id in running_tasks:
        task = running_tasks[req.user_id]
        del running_tasks[req.user_id]
        task.cancel()
        return {"ok": True, "message": "متوقف شد"}
    
    return {"ok": False, "error": "در حال اجرا نبود"}

# ==================== STATUS ====================
class StatusReq(BaseModel):
    key: str
    user_id: int

@app.post("/status")
async def status(req: StatusReq):
    check_auth(req.key)
    
    uid = str(req.user_id)
    data = user_data.get(uid, {})
    
    return {
        "ok": True,
        "logged_in": os.path.exists(os.path.join(SESSIONS_DIR, f"{req.user_id}.session")),
        "running": req.user_id in running_tasks,
        "banner": bool(data.get("banner")),
        "groups": len(data.get("groups", [])),
        "interval": data.get("interval", 5)
    }

# ==================== LOGOUT ====================
class LogoutReq(BaseModel):
    key: str
    user_id: int

@app.post("/logout")
async def logout(req: LogoutReq):
    check_auth(req.key)
    
    if req.user_id in running_tasks:
        task = running_tasks[req.user_id]
        del running_tasks[req.user_id]
        task.cancel()
    
    session_path = os.path.join(SESSIONS_DIR, f"{req.user_id}.session")
    if os.path.exists(session_path):
        os.remove(session_path)
    
    uid = str(req.user_id)
    if uid in user_data:
        del user_data[uid]
        save_data()
    
    return {"ok": True, "message": "خروج انجام شد"}