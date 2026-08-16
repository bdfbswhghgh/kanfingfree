import os, re, asyncio, json, random, traceback, aiohttp, asyncpg
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

TOKEN = os.getenv("BOT_TOKEN", "8519305274:AAEeacmOTiBCzHpDqr4Bk5D7ZPtlu49rzCY")
ADMIN = int(os.getenv("ADMIN_ID", "8248647747"))
TAPI = f"https://api.telegram.org/bot{TOKEN}"
DATABASE_URL = os.getenv("DATABASE_URL", "")
DEFCH = "@kanfingfree"
LOG_CH = "@starsdarkconfig"
NEEDREF = 10
REFPAY = 70000
TABCHI_PRICE = 150000
TABCHI_DAYS = 30
L1 = "---------------------"
L2 = "====================="
PLANS = [
    {"id": "P1", "name": "panel 500g", "size": "500GB", "price": 1300000, "pt": "1,300,000"},
    {"id": "P2", "name": "panel 700g", "size": "700GB", "price": 1800000, "pt": "1,800,000"},
    {"id": "P3", "name": "panel 1t", "size": "1TB", "price": 3500000, "pt": "3,500,000"},
]
db = None

async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=15)
    async with db.acquire() as c:
        await c.execute('''CREATE TABLE IF NOT EXISTS users(uid BIGINT PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '', refs BIGINT[] DEFAULT '{}', referred_by BIGINT, wallet BIGINT DEFAULT 0, total_earned BIGINT DEFAULT 0, orders_count INT DEFAULT 0, tabchi_exp BIGINT DEFAULT 0, verified BOOL DEFAULT FALSE, last_active BIGINT DEFAULT 0, created_at BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS channels(id SERIAL PRIMARY KEY, channel TEXT UNIQUE NOT NULL)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS missions(id SERIAL PRIMARY KEY, channel TEXT UNIQUE NOT NULL, reward BIGINT DEFAULT 70000)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS mission_done(uid BIGINT, channel TEXT, PRIMARY KEY(uid, channel))''')
        await c.execute('''CREATE TABLE IF NOT EXISTS orders(track TEXT PRIMARY KEY, uid BIGINT, username TEXT DEFAULT '', first_name TEXT DEFAULT '', plan_name TEXT DEFAULT '', plan_size TEXT DEFAULT '', plan_price BIGINT DEFAULT 0, status TEXT DEFAULT 'pending', created_at BIGINT DEFAULT 0, done_at BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS pending_refs(new_uid BIGINT PRIMARY KEY, ref_uid BIGINT, created_at BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS states(uid BIGINT PRIMARY KEY, state TEXT DEFAULT '', exp BIGINT DEFAULT 0)''')
        try:
            await c.execute("INSERT INTO channels(channel) VALUES($1) ON CONFLICT DO NOTHING", DEFCH)
        except:
            pass
    print("DB Ready")

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    if db:
        await db.close()

app = FastAPI(title="Bot", version="8.0", lifespan=lifespan)

async def tg(method, body):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(TAPI + "/" + method, json=body, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except:
        return None

async def tg_del(cid, mid):
    try:
        await tg("deleteMessage", {"chat_id": cid, "message_id": mid})
    except:
        pass

_bun = None

async def bun():
    global _bun
    if _bun:
        return _bun
    r = await tg("getMe", {})
    if r and r.get("ok"):
        _bun = r["result"]["username"]
    return _bun or "bot"

def J(o):
    return json.dumps(o)

def F(n):
    if isinstance(n, int):
        return "{:,}".format(n)
    return str(n)

def esc(s):
    return str(s or "").replace("&", "+").replace("<", "(").replace(">", ")")

def now():
    return int(datetime.now().timestamp() * 1000)

def fD(ts):
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y/%m/%d")
    except:
        return "-"

def time_left(ts):
    d = ts - now()
    if d <= 0:
        return "expired"
    days = d // 86400000
    hrs = (d % 86400000) // 3600000
    if days > 0:
        return str(days) + "d " + str(hrs) + "h"
    return str(hrs) + "h"

def captcha():
    a = random.randint(1, 15)
    b = random.randint(1, 9)
    if random.random() > 0.5:
        return str(a) + " + " + str(b), a + b
    big = max(a, b)
    small = min(a, b)
    return str(big) + " - " + str(small), big - small

def gen_track():
    return "ORD-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=7))

async def get_user(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(r) if r else None

async def reg_user(uid, un, fn):
    async with db.acquire() as c:
        ex = await c.fetchrow("SELECT uid FROM users WHERE uid=$1", uid)
        if not ex:
            await c.execute("INSERT INTO users(uid,username,first_name,created_at,last_active) VALUES($1,$2,$3,$4,$4)", uid, un, fn, now())
        else:
            await c.execute("UPDATE users SET last_active=$2 WHERE uid=$1", uid, now())
            if un:
                await c.execute("UPDATE users SET username=$2 WHERE uid=$1", uid, un)
            if fn:
                await c.execute("UPDATE users SET first_name=$2 WHERE uid=$1", uid, fn)

async def refs_count(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT refs FROM users WHERE uid=$1", uid)
        return len(r["refs"] or []) if r else 0

async def get_wallet(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT wallet FROM users WHERE uid=$1", uid)
        return r["wallet"] if r else 0

async def add_wallet(uid, amt):
    async with db.acquire() as c:
        await c.execute("UPDATE users SET wallet=wallet+$2,total_earned=total_earned+$2 WHERE uid=$1", uid, amt)

async def remove_wallet(uid, amt):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT wallet FROM users WHERE uid=$1", uid)
        if not r or r["wallet"] < amt:
            return False
        await c.execute("UPDATE users SET wallet=wallet-$2 WHERE uid=$1", uid, amt)
        return True

async def set_verified(uid):
    async with db.acquire() as c:
        await c.execute("UPDATE users SET verified=TRUE WHERE uid=$1", uid)

async def is_verified(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT verified FROM users WHERE uid=$1", uid)
        return r["verified"] if r else False

async def all_uids():
    async with db.acquire() as c:
        rows = await c.fetch("SELECT uid FROM users")
        return [r["uid"] for r in rows]

async def count_users():
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT COUNT(*) as c FROM users")
        return r["c"]

async def reset_refs_all():
    async with db.acquire() as c:
        await c.execute("UPDATE users SET refs='{}',referred_by=NULL,wallet=0,total_earned=0,orders_count=0")
        await c.execute("DELETE FROM pending_refs")

async def reset_wallets_all():
    async with db.acquire() as c:
        await c.execute("UPDATE users SET wallet=0")

async def get_st(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT state,exp FROM states WHERE uid=$1", uid)
        if r:
            if r["exp"] > 0 and r["exp"] < now():
                await c.execute("DELETE FROM states WHERE uid=$1", uid)
                return ""
            return r["state"]
        return ""

async def set_st(uid, state):
    async with db.acquire() as c:
        await c.execute("INSERT INTO states(uid,state,exp) VALUES($1,$2,$3) ON CONFLICT(uid) DO UPDATE SET state=$2,exp=$3", uid, state, now() + 3600000)

async def clr_st(uid):
    async with db.acquire() as c:
        await c.execute("DELETE FROM states WHERE uid=$1", uid)

async def get_chs():
    async with db.acquire() as c:
        rows = await c.fetch("SELECT channel FROM channels")
        return [r["channel"] for r in rows] if rows else [DEFCH]

async def add_ch(ch):
    async with db.acquire() as c:
        await c.execute("INSERT INTO channels(channel) VALUES($1) ON CONFLICT DO NOTHING", ch)

async def rm_ch(ch):
    async with db.acquire() as c:
        await c.execute("DELETE FROM channels WHERE channel=$1", ch)

async def get_missions():
    async with db.acquire() as c:
        rows = await c.fetch("SELECT channel,reward FROM missions")
        return [{"ch": r["channel"], "pay": r["reward"]} for r in rows]

async def add_mission(ch, pay):
    async with db.acquire() as c:
        await c.execute("INSERT INTO missions(channel,reward) VALUES($1,$2) ON CONFLICT(channel) DO UPDATE SET reward=$2", ch, pay)

async def rm_mission(ch):
    async with db.acquire() as c:
        await c.execute("DELETE FROM missions WHERE channel=$1", ch)

async def is_done(uid, ch):
    async with db.acquire() as c:
        return await c.fetchrow("SELECT 1 FROM mission_done WHERE uid=$1 AND channel=$2", uid, ch) is not None

async def mark_done(uid, ch):
    async with db.acquire() as c:
        await c.execute("INSERT INTO mission_done(uid,channel) VALUES($1,$2) ON CONFLICT DO NOTHING", uid, ch)

async def set_pending(nuid, ruid):
    async with db.acquire() as c:
        await c.execute("INSERT INTO pending_refs(new_uid,ref_uid,created_at) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", nuid, ruid, now())

async def get_pending(nuid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT ref_uid FROM pending_refs WHERE new_uid=$1", nuid)
        return r["ref_uid"] if r else None

async def del_pending(nuid):
    async with db.acquire() as c:
        await c.execute("DELETE FROM pending_refs WHERE new_uid=$1", nuid)

async def create_order(track, uid, un, fn, plan):
    async with db.acquire() as c:
        await c.execute("INSERT INTO orders(track,uid,username,first_name,plan_name,plan_size,plan_price,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)", track, uid, un, fn, plan["name"], plan["size"], plan["price"], now())
        await c.execute("UPDATE users SET orders_count=orders_count+1 WHERE uid=$1", uid)

async def get_order(track):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM orders WHERE track=$1", track)
        return dict(r) if r else None

async def done_order(track):
    async with db.acquire() as c:
        await c.execute("UPDATE orders SET status='done',done_at=$2 WHERE track=$1", track, now())

async def get_orders(limit=20):
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM orders ORDER BY created_at DESC LIMIT $1", limit)
        return [dict(r) for r in rows]

async def log_order(order):
    try:
        bn = await bun()
        txt = "New Order!\n" + L1 + "\n\nPlan: " + order["plan_name"] + "\nSize: " + order["plan_size"] + "\nCode: " + order["track"] + "\n\n" + L1
        await tg("sendMessage", {"chat_id": LOG_CH, "text": txt, "disable_web_page_preview": True, "reply_markup": J({"inline_keyboard": [[{"text": "Bot", "url": "https://t.me/" + bn}]]})})
    except Exception as e:
        print("log err: " + str(e))async def check_join(uid):
    chs = await get_chs()
    nj = []
    for ch in chs:
        try:
            cid = ch
            if ch.startswith("https://t.me/+") or ch.startswith("https://t.me/joinchat/"):
                nj.append(ch)
                continue
            if ch.startswith("https://t.me/"):
                cid = "@" + ch.replace("https://t.me/", "").split("/")[0]
            r = await tg("getChatMember", {"chat_id": cid, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member", "administrator", "creator"]:
                nj.append(ch)
        except:
            nj.append(ch)
    return nj

async def send_join(cid, nj):
    btns = []
    for ch in nj:
        if ch.startswith("https://"):
            url = ch
            name = ch.replace("https://t.me/", "").replace("+", "")[:20]
        else:
            url = "https://t.me/" + ch.replace("@", "")
            name = ch
        btns.append([{"text": "Join " + name, "url": url}])
    btns.append([{"text": "Done", "callback_data": "CJ"}])
    await tg("sendMessage", {"chat_id": cid, "text": "Please join channels first:\n\n" + "\n".join(nj), "reply_markup": J({"inline_keyboard": btns})})

async def send_captcha(cid, uid):
    q, ans = captcha()
    await set_st(uid, "CAP:" + str(ans))
    await tg("sendMessage", {"chat_id": cid, "text": "Solve: " + q + " = ?", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})

async def process_ref(uid, fn):
    try:
        rid = await get_pending(uid)
        if not rid:
            return
        await del_pending(uid)
        user = await get_user(uid)
        if user and user.get("referred_by"):
            return
        async with db.acquire() as c:
            await c.execute("UPDATE users SET referred_by=$2 WHERE uid=$1", uid, rid)
            ru = await get_user(rid)
            if not ru:
                return
            refs = list(ru["refs"] or [])
            if uid in refs:
                return
            refs.append(uid)
            await c.execute("UPDATE users SET refs=$2 WHERE uid=$1", rid, refs)
            await c.execute("UPDATE users SET wallet=wallet+$2,total_earned=total_earned+$2 WHERE uid=$1", rid, REFPAY)
            cnt = len(refs)
            wallet = ru["wallet"] + REFPAY
            await tg("sendMessage", {"chat_id": rid, "text": "New ref confirmed!\n\nUser: " + fn + "\nTotal: " + str(cnt) + "\nReward: +" + F(REFPAY) + "\nWallet: " + F(wallet)})
    except Exception as e:
        print("ref err: " + str(e))

async def main_menu(cid, fn, uid):
    wallet = await get_wallet(uid)
    refs = await refs_count(uid)
    kb = [[{"text": "Buy Panel"}], [{"text": "Referrals"}, {"text": "Wallet"}], [{"text": "Profile"}, {"text": "Missions"}], [{"text": "Tabchi"}]]
    if uid == ADMIN:
        kb.append([{"text": "Admin"}])
    await tg("sendMessage", {"chat_id": cid, "text": "Hi " + fn + "!\n\nWallet: " + F(wallet) + "\nRefs: " + str(refs) + "\n\nEach ref = " + F(REFPAY), "reply_markup": J({"keyboard": kb, "resize_keyboard": True})})

async def admin_panel(cid):
    total = await count_users()
    await tg("sendMessage", {"chat_id": cid, "text": "Admin Panel\n\nUsers: " + str(total), "reply_markup": J({"inline_keyboard": [[{"text": "Broadcast", "callback_data": "AB"}], [{"text": "Search User", "callback_data": "SU"}], [{"text": "Orders", "callback_data": "ORDLIST"}], [{"text": "Add Mission", "callback_data": "MA"}], [{"text": "Del Mission", "callback_data": "MR"}], [{"text": "List Missions", "callback_data": "ML"}], [{"text": "Add Channel", "callback_data": "AA"}], [{"text": "Del Channel", "callback_data": "AR"}], [{"text": "List Channels", "callback_data": "AL"}], [{"text": "Stats", "callback_data": "AS"}], [{"text": "Reset Refs", "callback_data": "AX"}], [{"text": "Reset Wallets", "callback_data": "WX"}], [{"text": "Back", "callback_data": "MN"}]]})})

async def shop_page(cid, uid):
    wallet = await get_wallet(uid)
    bn = await bun()
    btns = [[{"text": p["name"] + " | " + p["pt"], "callback_data": "BUY:" + p["id"]}] for p in PLANS]
    btns.append([{"text": "Back", "callback_data": "MN"}])
    await tg("sendMessage", {"chat_id": cid, "text": "Shop\n\nWallet: " + F(wallet) + "\n\nPlans:\n\n" + "\n".join(p["name"] + " - " + p["size"] + " - " + p["pt"] for p in PLANS) + "\n\nFree: invite friends!\nEach ref = " + F(REFPAY) + "\nLink: https://t.me/" + bn + "?start=" + str(uid), "reply_markup": J({"inline_keyboard": btns})})

async def ref_page(cid, uid):
    c = await refs_count(uid)
    wallet = await get_wallet(uid)
    bn = await bun()
    await tg("sendMessage", {"chat_id": cid, "text": "Referrals\n\nLink: https://t.me/" + bn + "?start=" + str(uid) + "\n\nRefs: " + str(c) + "\nPer ref: " + F(REFPAY) + "\nEarned: " + F(c * REFPAY) + "\nWallet: " + F(wallet), "reply_markup": J({"inline_keyboard": [[{"text": "Share", "switch_inline_query": "https://t.me/" + bn + "?start=" + str(uid)}], [{"text": "Back", "callback_data": "MN"}]]})})

async def acc_page(cid, uid, un):
    user = await get_user(uid)
    if not user:
        return
    c = len(user.get("refs") or [])
    await tg("sendMessage", {"chat_id": cid, "text": "Profile\n\nID: " + str(uid) + "\nUsername: " + ("@" + un if un else "-") + "\nRefs: " + str(c) + "\nWallet: " + F(user.get("wallet", 0)) + "\nEarned: " + F(user.get("total_earned", 0)) + "\nOrders: " + str(user.get("orders_count", 0)), "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})

async def wallet_page(cid, uid):
    user = await get_user(uid)
    if not user:
        return
    await tg("sendMessage", {"chat_id": cid, "text": "Wallet\n\nBalance: " + F(user.get("wallet", 0)) + "\nEarned: " + F(user.get("total_earned", 0)) + "\nOrders: " + str(user.get("orders_count", 0)) + "\n\nPer ref: " + F(REFPAY), "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})

async def mission_page(cid, uid):
    ms = await get_missions()
    if not ms:
        await tg("sendMessage", {"chat_id": cid, "text": "No missions.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})
        return
    btns = []
    for m in ms:
        done = await is_done(uid, m["ch"])
        if done:
            btns.append([{"text": m["ch"] + " Done", "callback_data": "MN"}])
        else:
            btns.append([{"text": "Join " + m["ch"], "url": "https://t.me/" + m["ch"].replace("@", "")}])
            btns.append([{"text": "Verify +" + F(m["pay"]), "callback_data": "MS:" + m["ch"]}])
    btns.append([{"text": "Back", "callback_data": "MN"}])
    await tg("sendMessage", {"chat_id": cid, "text": "Missions - earn rewards!", "reply_markup": J({"inline_keyboard": btns})})

async def tabchi_page(cid, uid):
    user = await get_user(uid)
    if not user or (user.get("tabchi_exp", 0) or 0) < now():
        await tg("sendMessage", {"chat_id": cid, "text": "Tabchi - Locked\n\nPrice: " + F(TABCHI_PRICE) + "\nDays: " + str(TABCHI_DAYS) + "\n\nContact admin.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})
        return
    await tg("sendMessage", {"chat_id": cid, "text": "Tabchi Active!\nExpires: " + time_left(user["tabchi_exp"]), "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})

@app.post("/")
async def webhook(req: Request):
    try:
        body = await req.json()
        if "callback_query" in body:
            asyncio.create_task(on_cb(body["callback_query"]))
        elif "message" in body:
            asyncio.create_task(on_msg(body["message"]))
    except:
        pass
    return {"ok": True}

@app.get("/setup")
async def setup(req: Request):
    base = str(req.base_url).rstrip("/").replace("http://", "https://")
    return await tg("setWebhook", {"url": base + "/", "drop_pending_updates": True, "max_connections": 100})

@app.get("/health")
async def health():
    total = await count_users()
    return {"status": "ok", "version": "8.0", "users": total}async def on_msg(m):
    try:
        cid = m["chat"]["id"]
        uid = m["from"]["id"]
        txt = (m.get("text") or "").strip()
        un = m["from"].get("username", "")
        fn = m["from"].get("first_name", "user")
        await reg_user(uid, un, fn)

        if txt in ["Cancel", "/cancel", "/reset"]:
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Cancelled.", "reply_markup": J({"remove_keyboard": True})})
            await main_menu(cid, fn, uid)
            return

        if txt.startswith("/start"):
            await clr_st(uid)
            parts = txt.split(" ")
            if len(parts) > 1:
                try:
                    r = int(parts[1])
                    if r > 0 and r != uid:
                        user = await get_user(uid)
                        if not user or not user.get("referred_by"):
                            await set_pending(uid, r)
                            await tg("sendMessage", {"chat_id": r, "text": "New ref! Waiting for verification. Reward: " + F(REFPAY)})
                except:
                    pass
            nj = await check_join(uid)
            if nj:
                await send_join(cid, nj)
                return
            if not await is_verified(uid):
                await send_captcha(cid, uid)
                return
            await main_menu(cid, fn, uid)
            return

        st = await get_st(uid)

        if st and st.startswith("CAP:"):
            correct = int(st.split(":")[1])
            try:
                ans = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "Numbers only."})
                return
            if ans == correct:
                await set_verified(uid)
                await clr_st(uid)
                await tg("sendMessage", {"chat_id": cid, "text": "Verified!", "reply_markup": J({"remove_keyboard": True})})
                await process_ref(uid, fn)
                await main_menu(cid, fn, uid)
            else:
                await tg("sendMessage", {"chat_id": cid, "text": "Wrong!"})
                await send_captcha(cid, uid)
            return

        if st == "BC" and uid == ADMIN:
            await do_broadcast(cid, m)
            await clr_st(uid)
            return

        if st == "AC" and uid == ADMIN:
            inp = txt.strip()
            save = ""
            if inp.startswith("@"):
                save = inp
            elif inp.startswith("https://t.me/+") or inp.startswith("https://t.me/joinchat/"):
                save = inp
            elif inp.startswith("https://t.me/"):
                save = "@" + inp.replace("https://t.me/", "").split("/")[0]
            else:
                await tg("sendMessage", {"chat_id": cid, "text": "Invalid format."})
                return
            await add_ch(save)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Added: " + save, "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return

        if st == "RC" and uid == ADMIN:
            await rm_ch(txt)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Removed.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return

        if st and st.startswith("RP:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            if m.get("text"):
                await tg("sendMessage", {"chat_id": tid, "text": "Admin reply:\n\n" + m["text"]})
            elif m.get("photo"):
                await tg("sendPhoto", {"chat_id": tid, "photo": m["photo"][-1]["file_id"], "caption": m.get("caption", "")})
            elif m.get("video"):
                await tg("sendVideo", {"chat_id": tid, "video": m["video"]["file_id"], "caption": m.get("caption", "")})
            elif m.get("document"):
                await tg("sendDocument", {"chat_id": tid, "document": m["document"]["file_id"], "caption": m.get("caption", "")})
            else:
                await tg("forwardMessage", {"chat_id": tid, "from_chat_id": cid, "message_id": m["message_id"]})
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Sent to " + str(tid), "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return

        if st == "SU" and uid == ADMIN:
            try:
                sid = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "Number."})
                return
            user = await get_user(sid)
            if not user:
                await clr_st(uid)
                await tg("sendMessage", {"chat_id": cid, "text": "Not found.", "reply_markup": J({"remove_keyboard": True})})
                await admin_panel(cid)
                return
            refs = len(user.get("refs") or [])
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "User: " + str(user["uid"]) + "\nRefs: " + str(refs) + "\nWallet: " + F(user["wallet"]) + "\nOrders: " + str(user.get("orders_count", 0)), "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": cid, "text": "Actions:", "reply_markup": J({"inline_keyboard": [[{"text": "Add Wallet", "callback_data": "AW:" + str(sid)}], [{"text": "Tabchi", "callback_data": "TB" + str(sid)}], [{"text": "Back", "callback_data": "AP"}]]})})
            return

        if st and st.startswith("AW:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try:
                amt = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "Number."})
                return
            await add_wallet(tid, amt)
            nw = await get_wallet(tid)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Added " + F(amt) + " to " + str(tid) + ". New: " + F(nw), "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": "Gift: +" + F(amt) + "\nWallet: " + F(nw)})
            await admin_panel(cid)
            return

        if st == "MA" and uid == ADMIN:
            p = txt.split(" ")
            if len(p) < 2 or not p[0].startswith("@"):
                await tg("sendMessage", {"chat_id": cid, "text": "Format: @channel 70000"})
                return
            try:
                pay = int(p[1])
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "Number."})
                return
            await add_mission(p[0], pay)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Added: " + p[0] + " - " + F(pay), "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return

        if st == "MR" and uid == ADMIN:
            await rm_mission(txt.strip())
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Removed.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return

        if st and st.startswith("TB:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try:
                days = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "Number."})
                return
            exp = now() + (days * 86400000)
            async with db.acquire() as c:
                await c.execute("UPDATE users SET tabchi_exp=$2 WHERE uid=$1", tid, exp)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "Tabchi active for " + str(tid) + " - " + str(days) + "d", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": "Tabchi activated! " + str(days) + " days"})
            await admin_panel(cid)
            return

        menu = ["Buy Panel", "Referrals", "Profile", "Wallet", "Missions", "Tabchi"]
        if txt in menu:
            nj = await check_join(uid)
            if nj:
                await send_join(cid, nj)
                return
            if not await is_verified(uid):
                await send_captcha(cid, uid)
                return

        if txt == "Buy Panel":
            await shop_page(cid, uid)
            return
        if txt == "Referrals":
            await ref_page(cid, uid)
            return
        if txt == "Profile":
            await acc_page(cid, uid, un)
            return
        if txt == "Wallet":
            await wallet_page(cid, uid)
            return
        if txt == "Missions":
            await mission_page(cid, uid)
            return
        if txt == "Tabchi":
            await tabchi_page(cid, uid)
            return
        if txt == "Admin" and uid == ADMIN:
            await clr_st(uid)
            await admin_panel(cid)
            return

    except Exception as e:
        print("msg err: " + str(e))
        traceback.print_exc()


async def on_cb(q):
    try:
        cid = q["message"]["chat"]["id"]
        uid = q["from"]["id"]
        d = q.get("data", "")
        fn = q["from"].get("first_name", "user")
        mid = q["message"]["message_id"]
        un = q["from"].get("username", "")
        try:
            await tg("answerCallbackQuery", {"callback_query_id": q["id"]})
        except:
            pass

        if d == "CJ":
            nj = await check_join(uid)
            if nj:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "Not joined!", "show_alert": True})
                return
            await tg_del(cid, mid)
            if not await is_verified(uid):
                await send_captcha(cid, uid)
                return
            await main_menu(cid, fn, uid)
            return

        if d == "MN":
            await clr_st(uid)
            await tg_del(cid, mid)
            await main_menu(cid, fn, uid)
            return

        if d == "AP" and uid == ADMIN:
            await clr_st(uid)
            await tg_del(cid, mid)
            await admin_panel(cid)
            return

        if d == "DONE":
            return

        if d.startswith("BUY:"):
            plan_id = d.split(":")[1]
            plan = next((p for p in PLANS if p["id"] == plan_id), None)
            if not plan:
                return
            wallet = await get_wallet(uid)
            if wallet < plan["price"]:
                need = plan["price"] - wallet
                bn = await bun()
                await tg("sendMessage", {"chat_id": cid, "text": "Not enough!\nWallet: " + F(wallet) + "\nPrice: " + plan["pt"] + "\nNeed: " + F(need) + "\n\nLink: https://t.me/" + bn + "?start=" + str(uid), "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "MN"}]]})})
                return
            await tg("sendMessage", {"chat_id": cid, "text": "Confirm?\n\nPlan: " + plan["name"] + "\nSize: " + plan["size"] + "\nPrice: " + plan["pt"] + "\nWallet: " + F(wallet) + "\nAfter: " + F(wallet - plan["price"]), "reply_markup": J({"inline_keyboard": [[{"text": "Confirm", "callback_data": "CONFIRM:" + plan_id}], [{"text": "Cancel", "callback_data": "MN"}]]})})
            return

        if d.startswith("CONFIRM:"):
            plan_id = d.split(":")[1]
            plan = next((p for p in PLANS if p["id"] == plan_id), None)
            if not plan:
                return
            wallet = await get_wallet(uid)
            if wallet < plan["price"]:
                await tg("sendMessage", {"chat_id": cid, "text": "Not enough!"})
                return
            ok = await remove_wallet(uid, plan["price"])
            if not ok:
                return
            track = gen_track()
            await create_order(track, uid, un, fn, plan)
            nw = await get_wallet(uid)
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Order placed!\n\nCode: " + track + "\nPlan: " + plan["name"] + "\nSize: " + plan["size"] + "\nPrice: " + plan["pt"] + "\nWallet: " + F(nw), "reply_markup": J({"inline_keyboard": [[{"text": "Menu", "callback_data": "MN"}]]})})
            await tg("sendMessage", {"chat_id": ADMIN, "text": "NEW ORDER!\n\nCode: " + track + "\nUser: " + ("@" + un if un else str(uid)) + "\nUID: " + str(uid) + "\nName: " + fn + "\nPlan: " + plan["name"] + "\nSize: " + plan["size"] + "\nPrice: " + plan["pt"], "disable_web_page_preview": True, "reply_markup": J({"inline_keyboard": [[{"text": "Done", "callback_data": "ODONE:" + track}]]})})
            await log_order({"track": track, "plan_name": plan["name"], "plan_size": plan["size"]})
            return

        if d.startswith("ODONE:") and uid == ADMIN:
            try:
                track = d[6:]
                order = await get_order(track)
                if not order:
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "Not found!", "show_alert": True})
                    return
                if order["status"] == "done":
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "Already done!", "show_alert": True})
                    return
                await done_order(track)
                order_uid = int(order["uid"])
                await tg("sendMessage", {"chat_id": order_uid, "text": "Your order is ready!\n\nCode: " + track + "\nPlan: " + order["plan_name"] + "\nSize: " + order["plan_size"]})
                try:
                    await tg("editMessageReplyMarkup", {"chat_id": cid, "message_id": mid, "reply_markup": J({"inline_keyboard": [[{"text": "DONE", "callback_data": "DONE"}]]})})
                except:
                    pass
                await set_st(uid, "RP:" + str(order_uid))
                await tg("sendMessage", {"chat_id": cid, "text": "Sent! Now send panel info to user " + str(order_uid) + "\n\nCancel: type Cancel", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            except Exception as e:
                print("odone err: " + str(e))
            return

        if d == "ORDLIST" and uid == ADMIN:
            orders = await get_orders(20)
            if not orders:
                await tg("sendMessage", {"chat_id": cid, "text": "No orders.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
                return
            t = "Orders:\n\n"
            for o in orders[:15]:
                st = "OK" if o["status"] == "done" else "WAIT"
                t = t + st + " " + o["track"] + " " + o["plan_name"] + "\n"
            await tg("sendMessage", {"chat_id": cid, "text": t, "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d == "AB" and uid == ADMIN:
            await set_st(uid, "BC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Send message:", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "AA" and uid == ADMIN:
            await set_st(uid, "AC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Send channel:", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "AR" and uid == ADMIN:
            chs = await get_chs()
            if not chs:
                await tg("sendMessage", {"chat_id": cid, "text": "None."})
                return
            await set_st(uid, "RC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Remove:\n\n" + "\n".join(chs), "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "AL" and uid == ADMIN:
            chs = await get_chs()
            await tg("sendMessage", {"chat_id": cid, "text": "Channels:\n\n" + "\n".join(chs) if chs else "None.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d == "AS" and uid == ADMIN:
            total = await count_users()
            ms = await get_missions()
            chs = await get_chs()
            await tg("sendMessage", {"chat_id": cid, "text": "Stats\n\nUsers: " + str(total) + "\nChannels: " + str(len(chs)) + "\nMissions: " + str(len(ms)), "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d == "AX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": "Reset all refs+wallets?", "reply_markup": J({"inline_keyboard": [[{"text": "Yes", "callback_data": "DX"}], [{"text": "No", "callback_data": "AP"}]]})})
            return

        if d == "DX" and uid == ADMIN:
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Resetting..."})
            await reset_refs_all()
            total = await count_users()
            await tg("sendMessage", {"chat_id": cid, "text": "Done! " + str(total) + " users reset.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d == "WX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": "Reset wallets?", "reply_markup": J({"inline_keyboard": [[{"text": "Yes", "callback_data": "DW"}], [{"text": "No", "callback_data": "AP"}]]})})
            return

        if d == "DW" and uid == ADMIN:
            await tg_del(cid, mid)
            await reset_wallets_all()
            await tg("sendMessage", {"chat_id": cid, "text": "Wallets reset.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d == "SU" and uid == ADMIN:
            await set_st(uid, "SU")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "User ID:", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d.startswith("AW:") and uid == ADMIN:
            tid = d.split(":")[1]
            await set_st(uid, "AW:" + tid)
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Amount for " + tid + ":", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d.startswith("TB") and uid == ADMIN and not d.startswith("TB:"):
            tid = d[2:]
            await set_st(uid, "TB:" + tid)
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Days for " + tid + ":", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "MA" and uid == ADMIN:
            await set_st(uid, "MA")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Mission: @channel 70000", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "MR" and uid == ADMIN:
            ms = await get_missions()
            if not ms:
                await tg("sendMessage", {"chat_id": cid, "text": "None."})
                return
            await set_st(uid, "MR")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Remove:\n" + "\n".join(m["ch"] for m in ms), "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

        if d == "ML" and uid == ADMIN:
            ms = await get_missions()
            await tg("sendMessage", {"chat_id": cid, "text": "Missions:\n" + "\n".join(m["ch"] + " " + F(m["pay"]) for m in ms) if ms else "None.", "reply_markup": J({"inline_keyboard": [[{"text": "Back", "callback_data": "AP"}]]})})
            return

        if d.startswith("MS:"):
            ch = d[3:]
            ms = await get_missions()
            mi = next((m for m in ms if m["ch"] == ch), None)
            if not mi:
                return
            r = await tg("getChatMember", {"chat_id": ch, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member", "administrator", "creator"]:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "Join first!", "show_alert": True})
                return
            if await is_done(uid, ch):
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "Already done!", "show_alert": True})
                return
            await mark_done(uid, ch)
            await add_wallet(uid, mi["pay"])
            nw = await get_wallet(uid)
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Mission done!\n" + ch + "\n+" + F(mi["pay"]) + "\nWallet: " + F(nw), "reply_markup": J({"inline_keyboard": [[{"text": "Menu", "callback_data": "MN"}]]})})
            return

        if d.startswith("RP") and uid == ADMIN:
            tid = d[2:]
            await set_st(uid, "RP:" + tid)
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "Reply to " + tid + ":", "reply_markup": J({"keyboard": [[{"text": "Cancel"}]], "resize_keyboard": True})})
            return

    except Exception as e:
        print("cb err: " + str(e))
        traceback.print_exc()


async def do_broadcast(cid, m):
    try:
        uids = await all_uids()
        if not uids:
            await tg("sendMessage", {"chat_id": cid, "text": "No users.", "reply_markup": J({"remove_keyboard": True})})
            return
        total = len(uids)
        await tg("sendMessage", {"chat_id": cid, "text": "Sending to " + str(total) + "...", "reply_markup": J({"remove_keyboard": True})})
        ok = 0
        fail = 0
        async with aiohttp.ClientSession() as session:
            for i in range(0, total, 30):
                batch = uids[i:i + 30]
                tasks = []
                for u in batch:
                    try:
                        if m.get("text"):
                            tasks.append(session.post(TAPI + "/sendMessage", json={"chat_id": u, "text": m["text"]}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("photo"):
                            tasks.append(session.post(TAPI + "/sendPhoto", json={"chat_id": u, "photo": m["photo"][-1]["file_id"], "caption": m.get("caption", "")}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("video"):
                            tasks.append(session.post(TAPI + "/sendVideo", json={"chat_id": u, "video": m["video"]["file_id"], "caption": m.get("caption", "")}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("document"):
                            tasks.append(session.post(TAPI + "/sendDocument", json={"chat_id": u, "document": m["document"]["file_id"], "caption": m.get("caption", "")}, timeout=aiohttp.ClientTimeout(total=10)))
                    except:
                        pass
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            fail = fail + 1
                        else:
                            try:
                                data = await r.json()
                                if data.get("ok"):
                                    ok = ok + 1
                                else:
                                    fail = fail + 1
                            except:
                                fail = fail + 1
                await asyncio.sleep(1)
        await tg("sendMessage", {"chat_id": cid, "text": "Done! OK:" + str(ok) + " Fail:" + str(fail) + " Total:" + str(total), "reply_markup": J({"inline_keyboard": [[{"text": "Menu", "callback_data": "MN"}]]})})
    except Exception as e:
        await tg("sendMessage", {"chat_id": cid, "text": "Error: " + str(e), "reply_markup": J({"remove_keyboard": True})})
