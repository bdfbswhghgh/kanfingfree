import os, re, asyncio, json, random, traceback, aiohttp, asyncpg
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional

# ══════════════ CONFIG ══════════════
TOKEN = os.getenv("BOT_TOKEN", "8519305274:AAEeacmOTiBCzHpDqr4Bk5D7ZPtlu49rzCY")
ADMIN = int(os.getenv("ADMIN_ID", "8248647747"))
TAPI = f"https://api.telegram.org/bot{TOKEN}"
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "MySecret2026BotXYZ")
DEFCH = "@kanfingfree"
LOG_CH = "@starsdarkconfig"
NEEDREF = 3
STARS_PER_REF = 1
TABCHI_PRICE = 150000
TABCHI_DAYS = 30
TABCHI_URL = os.getenv("TABCHI_URL", "")
TABCHI_KEY = os.getenv("TABCHI_KEY", "MySecret2026BotXYZ")

L1 = "━━━━━━━━━━━━━━━━━━━━━"
L2 = "══════════════════════"
STAR = "⭐"
SPARKLE = "✨"
FIRE = "🔥"
DIAMOND = "💎"
ROCKET = "🚀"

# ══════════════ DATABASE ══════════════
db = None

async def init_db():
    global db
    db = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=15)
    async with db.acquire() as c:
        await c.execute('''CREATE TABLE IF NOT EXISTS users(
            uid BIGINT PRIMARY KEY,
            username TEXT DEFAULT '',
            first_name TEXT DEFAULT '',
            refs BIGINT[] DEFAULT '{}',
            referred_by BIGINT,
            stars INT DEFAULT 0,
            total_earned INT DEFAULT 0,
            total_withdrawn INT DEFAULT 0,
            orders_count INT DEFAULT 0,
            tabchi_exp BIGINT DEFAULT 0,
            verified BOOL DEFAULT FALSE,
            is_banned BOOL DEFAULT FALSE,
            last_active BIGINT DEFAULT 0,
            created_at BIGINT DEFAULT 0
        )''')
        await c.execute('''CREATE TABLE IF NOT EXISTS channels(
            id SERIAL PRIMARY KEY, channel TEXT UNIQUE NOT NULL)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS missions(
            id SERIAL PRIMARY KEY, channel TEXT UNIQUE NOT NULL, reward INT DEFAULT 1)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS mission_done(
            uid BIGINT, channel TEXT, done_at BIGINT DEFAULT 0, PRIMARY KEY(uid,channel))''')
        await c.execute('''CREATE TABLE IF NOT EXISTS star_orders(
            track TEXT PRIMARY KEY, uid BIGINT, username TEXT DEFAULT '',
            first_name TEXT DEFAULT '', post_link TEXT DEFAULT '',
            amount INT DEFAULT 0, status TEXT DEFAULT 'pending',
            created_at BIGINT DEFAULT 0, done_at BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS pending_refs(
            new_uid BIGINT PRIMARY KEY, ref_uid BIGINT, created_at BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS states(
            uid BIGINT PRIMARY KEY, state TEXT DEFAULT '', exp BIGINT DEFAULT 0)''')
        await c.execute('''CREATE TABLE IF NOT EXISTS kv(
            k TEXT PRIMARY KEY, v TEXT DEFAULT '')''')
        await c.execute('''CREATE TABLE IF NOT EXISTS bot_stats(
            id INT PRIMARY KEY DEFAULT 1, total_stars_given INT DEFAULT 0,
            total_orders INT DEFAULT 0, total_orders_done INT DEFAULT 0)''')
        await c.execute("INSERT INTO bot_stats(id) VALUES(1) ON CONFLICT DO NOTHING")
        try:
            await c.execute("INSERT INTO channels(channel) VALUES($1) ON CONFLICT DO NOTHING", DEFCH)
        except:
            pass
    print("✅ DB Ready")

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    if db: await db.close()

app = FastAPI(title="Stars Bot", version="5.0", lifespan=lifespan)

# ══════════════ TELEGRAM API ══════════════
async def tg(method, body):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{TAPI}/{method}", json=body, timeout=aiohttp.ClientTimeout(total=15)) as r:
                return await r.json()
    except:
        return None

async def tg_del(cid, mid):
    try: await tg("deleteMessage", {"chat_id": cid, "message_id": mid})
    except: pass

_bun = None
async def bun():
    global _bun
    if _bun: return _bun
    r = await tg("getMe", {})
    if r and r.get("ok"): _bun = r["result"]["username"]
    return _bun or "bot"

def J(o): return json.dumps(o)
def F(n): return f"{n:,}" if isinstance(n, int) else str(n)
def esc(s): return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def now(): return int(datetime.now().timestamp() * 1000)

def fD(ts):
    try: return datetime.fromtimestamp(ts/1000).strftime("%Y/%m/%d %H:%M")
    except: return "-"

def fDate(ts):
    try: return datetime.fromtimestamp(ts/1000).strftime("%Y/%m/%d")
    except: return "-"

def time_left(ts):
    d = ts - now()
    if d <= 0: return "منقضی شده"
    days = d // 86400000
    hrs = (d % 86400000) // 3600000
    mins = (d % 3600000) // 60000
    if days > 0: return f"{days} روز و {hrs} ساعت"
    if hrs > 0: return f"{hrs} ساعت و {mins} دقیقه"
    return f"{mins} دقیقه"

def captcha():
    a, b = random.randint(1,15), random.randint(1,9)
    if random.random() > 0.5:
        return f"{a} + {b}", a + b
    big, small = max(a,b), min(a,b)
    return f"{big} - {small}", big - small

def track_code():
    return "STR-" + "".join(random.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=7))

def progress_bar(current, total, length=10):
    if total == 0: return "░" * length + " 0%"
    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    pct = round(current / total * 100)
    return f"{bar} {pct}%"

def mask_link(link, hide=12):
    parts = link.split("/")
    if len(parts) >= 2:
        ch = parts[-2] or ""
        if len(ch) > hide:
            parts[-2] = "*" * hide + ch[hide:]
        else:
            parts[-2] = ch[:1] + "*" * hide
    return "/".join(parts)

# ══════════════ DB FUNCTIONS ══════════════
async def get_user(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(r) if r else None

async def reg_user(uid, un="", fn=""):
    async with db.acquire() as c:
        ex = await c.fetchrow("SELECT uid FROM users WHERE uid=$1", uid)
        if not ex:
            await c.execute("INSERT INTO users(uid,username,first_name,created_at,last_active) VALUES($1,$2,$3,$4,$4)", uid, un, fn, now())
        else:
            updates = []
            if un: updates.append(("username", un))
            if fn: updates.append(("first_name", fn))
            updates.append(("last_active", now()))
            for col, val in updates:
                await c.execute(f"UPDATE users SET {col}=$2 WHERE uid=$1", uid, val)

async def get_refs(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT refs FROM users WHERE uid=$1", uid)
        return list(r["refs"] or []) if r else []

async def refs_count(uid):
    return len(await get_refs(uid))

async def get_stars(uid):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT stars FROM users WHERE uid=$1", uid)
        return r["stars"] if r else 0

async def add_stars(uid, amt):
    async with db.acquire() as c:
        await c.execute("UPDATE users SET stars=stars+$2, total_earned=total_earned+$2 WHERE uid=$1", uid, amt)
        await c.execute("UPDATE bot_stats SET total_stars_given=total_stars_given+$1 WHERE id=1", amt)

async def remove_stars(uid, amt):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT stars FROM users WHERE uid=$1", uid)
        if not r or r["stars"] < amt: return False
        await c.execute("UPDATE users SET stars=stars-$2, total_withdrawn=total_withdrawn+$2 WHERE uid=$1", uid, amt)
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
        rows = await c.fetch("SELECT uid FROM users WHERE is_banned=FALSE")
        return [r["uid"] for r in rows]

async def count_users():
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT COUNT(*) as c FROM users")
        return r["c"]

async def count_active():
    cutoff = now() - 7 * 86400000
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT COUNT(*) as c FROM users WHERE last_active>$1", cutoff)
        return r["c"]

async def reset_refs_all():
    async with db.acquire() as c:
        await c.execute("UPDATE users SET refs='{}', referred_by=NULL, stars=0, total_earned=0, total_withdrawn=0, orders_count=0")
        await c.execute("DELETE FROM pending_refs")
        await c.execute("UPDATE bot_stats SET total_stars_given=0, total_orders=0, total_orders_done=0 WHERE id=1")

async def reset_stars_all():
    async with db.acquire() as c:
        await c.execute("UPDATE users SET stars=0")

async def get_bot_stats():
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM bot_stats WHERE id=1")
        return dict(r) if r else {}

# State
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
        await c.execute("INSERT INTO states(uid,state,exp) VALUES($1,$2,$3) ON CONFLICT(uid) DO UPDATE SET state=$2,exp=$3", uid, state, now()+3600000)

async def clr_st(uid):
    async with db.acquire() as c:
        await c.execute("DELETE FROM states WHERE uid=$1", uid)

# Channels
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

# Missions
async def get_missions():
    async with db.acquire() as c:
        rows = await c.fetch("SELECT channel,reward FROM missions")
        return [{"ch":r["channel"],"pay":r["reward"]} for r in rows]

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
        await c.execute("INSERT INTO mission_done(uid,channel,done_at) VALUES($1,$2,$3) ON CONFLICT DO NOTHING", uid, ch, now())

# Pending
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

# Orders
async def create_order(track, uid, un, fn, link, amt):
    async with db.acquire() as c:
        await c.execute("INSERT INTO star_orders(track,uid,username,first_name,post_link,amount,created_at) VALUES($1,$2,$3,$4,$5,$6,$7)", track, uid, un, fn, link, amt, now())
        await c.execute("UPDATE users SET orders_count=orders_count+1 WHERE uid=$1", uid)
        await c.execute("UPDATE bot_stats SET total_orders=total_orders+1 WHERE id=1")

async def get_order(track):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT * FROM star_orders WHERE track=$1", track)
        return dict(r) if r else None

async def done_order(track):
    async with db.acquire() as c:
        await c.execute("UPDATE star_orders SET status='done',done_at=$2 WHERE track=$1", track, now())
        await c.execute("UPDATE bot_stats SET total_orders_done=total_orders_done+1 WHERE id=1")

async def get_orders(limit=20):
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM star_orders ORDER BY created_at DESC LIMIT $1", limit)
        return [dict(r) for r in rows]

# KV
async def kv_get(k):
    async with db.acquire() as c:
        r = await c.fetchrow("SELECT v FROM kv WHERE k=$1", k)
        return r["v"] if r else None

async def kv_set(k, v):
    async with db.acquire() as c:
        await c.execute("INSERT INTO kv(k,v) VALUES($1,$2) ON CONFLICT(k) DO UPDATE SET v=$2", k, v)# ══════════════ CHECK JOIN ══════════════
async def check_join(uid):
    chs = await get_chs()
    nj = []
    for ch in chs:
        try:
            cid = ch
            if ch.startswith("https://t.me/+") or ch.startswith("https://t.me/joinchat/"):
                nj.append(ch)
                continue
            if ch.startswith("https://t.me/"):
                cid = "@" + ch.replace("https://t.me/","").split("/")[0]
            r = await tg("getChatMember", {"chat_id": cid, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member","administrator","creator"]:
                nj.append(ch)
        except:
            nj.append(ch)
    return nj

async def send_join(cid, nj):
    btns = []
    for ch in nj:
        if ch.startswith("https://"):
            url = ch
            name = ch.replace("https://t.me/","").replace("+","")[:20]
        else:
            url = f"https://t.me/{ch.replace('@','')}"
            name = ch
        btns.append([{"text": f"📢 عضویت در {name}", "url": url}])
    btns.append([{"text": "✅ عضو شدم، تایید کن", "callback_data": "CJ"}])
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🔒 عضویت اجباری\n{L1}\n\n{DIAMOND} برای دسترسی به امکانات ربات، ابتدا در کانال‌های زیر عضو شوید:\n\n" + "\n".join(nj) + f"\n\n{L1}\n\n✅ پس از عضویت، دکمه تایید را بزنید.",
        "reply_markup": J({"inline_keyboard": btns})
    })

async def send_captcha(cid, uid):
    q, ans = captcha()
    await set_st(uid, f"CAP:{ans}")
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🔐 تایید هویت\n{L1}\n\n{DIAMOND} لطفاً ثابت کنید ربات نیستید!\n\n🧮 حاصل عبارت زیر چیست؟\n\n➤  <b>{q}</b>  = ?\n\n💡 فقط عدد پاسخ را ارسال کنید.\n\n⚠️ پاسخ اشتباه = کپچای جدید",
        "parse_mode": "HTML",
        "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})
    })

async def process_ref(uid, fn):
    try:
        rid = await get_pending(uid)
        if not rid: return
        await del_pending(uid)
        
        user = await get_user(uid)
        if user and user.get("referred_by"): return
        
        async with db.acquire() as c:
            await c.execute("UPDATE users SET referred_by=$2 WHERE uid=$1", uid, rid)
            
            ru = await get_user(rid)
            if not ru: return
            
            refs = list(ru["refs"] or [])
            if uid in refs: return
            refs.append(uid)
            
            old_s = ((len(refs)-1) // NEEDREF) * STARS_PER_REF
            new_s = (len(refs) // NEEDREF) * STARS_PER_REF
            gained = new_s - old_s
            
            await c.execute("UPDATE users SET refs=$2 WHERE uid=$1", rid, refs)
            if gained > 0:
                await c.execute("UPDATE users SET stars=stars+$2, total_earned=total_earned+$2 WHERE uid=$1", rid, gained)
                await c.execute("UPDATE bot_stats SET total_stars_given=total_stars_given+$1 WHERE id=1", gained)
            
            cnt = len(refs)
            need = NEEDREF - (cnt % NEEDREF)
            
            if gained > 0:
                await tg("sendMessage", {"chat_id": rid, "text": f"🎊 {SPARKLE} زیرمجموعه تایید شد!\n{L2}\n\n👤 کاربر: {fn}\n👥 مجموع زیرمجموعه: {cnt} نفر\n\n{STAR} +{gained} استارز کسب کردید!\n{STAR} موجودی جدید: {new_s} استارز\n\n{progress_bar(cnt % NEEDREF, NEEDREF)}\n\n✅ تمام مراحل انجام شد:\n• عضویت در کانال‌ها ✓\n• حل کپچا ✓\n• ثبت زیرمجموعه ✓\n\n{FIRE} ادامه بدید و بیشتر کسب کنید!"})
            else:
                await tg("sendMessage", {"chat_id": rid, "text": f"🎊 زیرمجموعه تایید شد!\n{L1}\n\n👤 کاربر: {fn}\n👥 مجموع: {cnt} نفر\n\n📊 پیشرفت تا استارز بعدی:\n{progress_bar(cnt % NEEDREF, NEEDREF)}\n\n📌 با {need} زیرمجموعه دیگر، {STARS_PER_REF} استارز کسب می‌کنید!"})
    except Exception as e:
        print(f"ref err: {e}")

async def log_order(order):
    try:
        masked = mask_link(order.get("post_link",""))
        bn = await bun()
        await tg("sendMessage", {
            "chat_id": LOG_CH,
            "text": f"{STAR} سفارش جدید ثبت شد\n{L1}\n\n📋 نوع سفارش: استارز رایگان\n\n🎯 مقصد سفارش:\n<b>{esc(masked)}</b>\n\n{STAR} تعداد: {order['amount']} استارز\n\n{L1}\n\n{FIRE} منتظر چی هستی؟\n{SPARKLE} همین الان استارز رایگانت رو بگیر!",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": J({"inline_keyboard": [[{"text": "🤖 ورود به ربات", "url": f"https://t.me/{bn}"}]]})
        })
    except Exception as e:
        print(f"log err: {e}")

# ══════════════ PAGES ══════════════
async def main_menu(cid, fn, uid):
    stars = await get_stars(uid)
    refs = await refs_count(uid)
    kb = [
        [{"text": f"{STAR} استارز رایگان {STAR}"}],
        [{"text": "👥 زیرمجموعه گیری"}, {"text": f"{STAR} کیف پول استارزی"}],
        [{"text": "👤 حساب کاربری"}, {"text": "🎯 انجام ماموریت"}],
        [{"text": "🛒 ساخت پنل"}, {"text": f"{ROCKET} تبچی"}]
    ]
    if uid == ADMIN:
        kb.append([{"text": "⚙️ پنل مدیریت"}])
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"👋 سلام <b>{esc(fn)}</b> عزیز!\n{L2}\n\n{SPARKLE} به ربات استارز رایگان خوش آمدید!\n\n📊 وضعیت شما:\n{STAR} استارز: <b>{stars}</b>\n👥 زیرمجموعه: <b>{refs}</b> نفر\n\n{L1}\n\n{FIRE} امکانات ویژه:\n\n{STAR} استارز رایگان - کاملاً رایگان!\n👥 سیستم دعوت هوشمند\n{STAR} کیف پول استارزی\n🎯 ماموریت‌های پاداش‌دار\n{ROCKET} تبچی هوشمند\n\n{DIAMOND} هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز رایگان\n\n💡 از منوی زیر شروع کنید:",
        "parse_mode": "HTML",
        "reply_markup": J({"keyboard": kb, "resize_keyboard": True})
    })

async def admin_panel(cid):
    total = await count_users()
    active = await count_active()
    stats = await get_bot_stats()
    orders = stats.get("total_orders", 0)
    done = stats.get("total_orders_done", 0)
    given = stats.get("total_stars_given", 0)
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"⚙️ پنل مدیریت پیشرفته\n{L2}\n\n👑 خوش آمدید، مدیر گرامی!\n\n📊 آمار کلی:\n\n👥 کل کاربران: <b>{total}</b>\n👥 فعال ۷ روز: <b>{active}</b>\n{STAR} کل استارز داده شده: <b>{given}</b>\n📋 کل سفارشات: <b>{orders}</b>\n✅ سفارشات انجام شده: <b>{done}</b>\n🟡 در انتظار: <b>{orders - done}</b>\n\n{L1}\n\n💡 برای لغو هر عملیات: «❌ لغو»",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [
            [{"text": "📨 ارسال پیام همگانی", "callback_data": "AB"}],
            [{"text": "🔍 جستجوی کاربر + عملیات", "callback_data": "SU"}],
            [{"text": f"{STAR} لیست سفارشات استارز", "callback_data": "STLIST"}],
            [{"text": "🎯 افزودن ماموریت", "callback_data": "MA"}],
            [{"text": "🗑 حذف ماموریت", "callback_data": "MR"}],
            [{"text": "📋 لیست ماموریت‌ها", "callback_data": "ML"}],
            [{"text": "➕ افزودن کانال جوین", "callback_data": "AA"}],
            [{"text": "➖ حذف کانال جوین", "callback_data": "AR"}],
            [{"text": "📋 لیست کانال‌ها", "callback_data": "AL"}],
            [{"text": "📊 آمار پیشرفته", "callback_data": "AS"}],
            [{"text": "🔄 صفر کردن زیرمجموعه‌ها", "callback_data": "AX"}],
            [{"text": f"{STAR} صفر کردن استارز", "callback_data": "STX"}],
            [{"text": "🔙 بازگشت به منو", "callback_data": "MN"}]
        ]})
    })

async def stars_page(cid, uid):
    stars = await get_stars(uid)
    refs = await refs_count(uid)
    bn = await bun()
    user = await get_user(uid)
    earned = user.get("total_earned", 0) if user else 0
    withdrawn = user.get("total_withdrawn", 0) if user else 0
    orders = user.get("orders_count", 0) if user else 0
    next_in = NEEDREF - (refs % NEEDREF)
    earned_from_refs = (refs // NEEDREF) * STARS_PER_REF
    
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"{STAR}{SPARKLE} پنل استارز رایگان {SPARKLE}{STAR}\n{L2}\n\n{DIAMOND} موجودی استارز شما:\n\n{STAR} <b>{stars}</b> استارز\n\n{L1}\n\n📊 آمار عملکرد شما:\n\n👥 زیرمجموعه‌ها: <b>{refs}</b> نفر\n{STAR} استارز کسب شده: <b>{earned_from_refs}</b>\n{STAR} کل دریافتی: <b>{earned}</b>\n💫 کل برداشتی: <b>{withdrawn}</b>\n📋 تعداد سفارشات: <b>{orders}</b>\n\n{L1}\n\n📈 پیشرفت تا استارز بعدی:\n{progress_bar(refs % NEEDREF, NEEDREF)}\n📌 با <b>{next_in}</b> زیرمجموعه دیگر، <b>{STARS_PER_REF}</b> استارز!\n\n{L1}\n\n💡 نحوه کسب استارز:\n\n1️⃣ لینک دعوت رو کپی کنید\n2️⃣ برای دوستان بفرستید\n3️⃣ هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز\n\n🔗 لینک دعوت:\n<code>https://t.me/{bn}?start={uid}</code>\n\n{L1}\n\n{FIRE} برای برداشت استارز، دکمه زیر رو بزنید:",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [
            [{"text": f"💫 برداشت استارز ({stars} {STAR})", "callback_data": "STARS_WD"}],
            [{"text": "📤 اشتراک لینک دعوت", "switch_inline_query": f"https://t.me/{bn}?start={uid}"}],
            [{"text": "📊 تاریخچه سفارشات", "callback_data": "MY_ORDERS"}],
            [{"text": "🔙 بازگشت به منو", "callback_data": "MN"}]
        ]})
    })

async def ref_page(cid, uid):
    c = await refs_count(uid)
    stars = await get_stars(uid)
    bn = await bun()
    next_in = NEEDREF - (c % NEEDREF)
    earned = (c // NEEDREF) * STARS_PER_REF
    
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"👥 پنل زیرمجموعه‌گیری هوشمند\n{L2}\n\n🔗 لینک دعوت اختصاصی شما:\n<code>https://t.me/{bn}?start={uid}</code>\n\n{L1}\n\n📊 آمار کامل:\n\n👥 زیرمجموعه: <b>{c}</b> نفر\n{STAR} استارز کسب شده: <b>{earned}</b>\n{STAR} موجودی: <b>{stars}</b>\n\n📈 پیشرفت تا استارز بعدی:\n{progress_bar(c % NEEDREF, NEEDREF)}\n📌 <b>{next_in}</b> زیرمجموعه دیگر = <b>{STARS_PER_REF}</b> {STAR}\n\n{L1}\n\n💡 قانون استارز:\n\n✅ هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز\n\n📌 شرایط ثبت زیرمجموعه:\n\n1️⃣ ورود از لینک شما\n2️⃣ عضویت در کانال‌ها\n3️⃣ حل کپچای امنیتی\n\n{FIRE} هر چه بیشتر دعوت، بیشتر استارز!",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [
            [{"text": "📤 اشتراک لینک", "switch_inline_query": f"https://t.me/{bn}?start={uid}"}],
            [{"text": "🔙 بازگشت", "callback_data": "MN"}]
        ]})
    })

async def acc_page(cid, uid, un):
    user = await get_user(uid)
    if not user: return
    c = len(user.get("refs") or [])
    stars = user.get("stars", 0)
    earned = user.get("total_earned", 0)
    withdrawn = user.get("total_withdrawn", 0)
    orders = user.get("orders_count", 0)
    created = fDate(user.get("created_at", 0))
    last = fD(user.get("last_active", 0))
    
    t = f"👤 پروفایل کاربری\n{L2}\n\n"
    t += f"📋 اطلاعات شخصی:\n\n"
    t += f"🔢 شناسه: <code>{uid}</code>\n"
    t += f"🆔 یوزرنیم: {'@'+un if un else 'ثبت نشده'}\n"
    t += f"📛 نام: {esc(user.get('first_name',''))}\n"
    t += f"📅 عضویت: {created}\n"
    t += f"🕐 آخرین فعالیت: {last}\n"
    t += f"\n{L1}\n\n"
    t += f"📊 آمار عملکرد:\n\n"
    t += f"👥 زیرمجموعه: <b>{c}</b> نفر\n"
    t += f"{STAR} موجودی استارز: <b>{stars}</b>\n"
    t += f"{STAR} کل دریافتی: <b>{earned}</b>\n"
    t += f"💫 کل برداشتی: <b>{withdrawn}</b>\n"
    t += f"📋 تعداد سفارشات: <b>{orders}</b>\n"
    t += f"\n{L1}\n\n"
    t += f"📦 اشتراک‌ها:\n\n"
    tabchi = user.get("tabchi_exp", 0) or 0
    if tabchi > now():
        t += f"{ROCKET} تبچی: ✅ فعال ({time_left(tabchi)})\n"
    else:
        t += f"{ROCKET} تبچی: ❌ غیرفعال\n"
    
    await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})

async def wallet_page(cid, uid):
    user = await get_user(uid)
    if not user: return
    stars = user.get("stars", 0)
    c = len(user.get("refs") or [])
    earned = user.get("total_earned", 0)
    withdrawn = user.get("total_withdrawn", 0)
    orders = user.get("orders_count", 0)
    
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"{STAR} کیف پول استارزی\n{L2}\n\n{DIAMOND} موجودی:\n{STAR} <b>{stars}</b> استارز\n\n{L1}\n\n📊 گزارش مالی:\n\n{STAR} کل دریافتی: <b>{earned}</b>\n💫 کل برداشتی: <b>{withdrawn}</b>\n📋 تعداد سفارشات: <b>{orders}</b>\n\n{L1}\n\n📈 منابع درآمد:\n\n👥 از زیرمجموعه ({c} نفر): <b>{(c//NEEDREF)*STARS_PER_REF}</b> {STAR}\n🎯 از ماموریت‌ها: محاسبه شده\n🎁 هدیه مدیریت: محاسبه شده\n\n{L1}\n\n💡 راه‌های افزایش:\n\n1️⃣ دعوت دوستان (هر {NEEDREF} نفر = {STARS_PER_REF} {STAR})\n2️⃣ انجام ماموریت‌ها\n\n{FIRE} برای برداشت به بخش «{STAR} استارز رایگان» بروید.",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [
            [{"text": f"{STAR} استارز رایگان", "callback_data": "MN"}],
            [{"text": "📊 تاریخچه سفارشات", "callback_data": "MY_ORDERS"}],
            [{"text": "🔙 بازگشت", "callback_data": "MN"}]
        ]})
    })

async def shop_page(cid, uid):
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🛒 فروشگاه پنل\n{L2}\n\n⚠️ این بخش موقتاً غیرفعال است\n\n📌 در حال بهبود و توسعه\n\n⏱ به زودی با امکانات جدید و خفن برمی‌گردد!\n\n{SPARKLE} فعلاً از بخش استارز رایگان استفاده کنید!",
        "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
    })

async def mission_page(cid, uid):
    ms = await get_missions()
    if not ms:
        await tg("sendMessage", {
            "chat_id": cid,
            "text": f"🎯 مرکز ماموریت‌ها\n{L2}\n\n❌ در حال حاضر ماموریتی موجود نیست.\n\n{SPARKLE} به زودی ماموریت‌های جدید اضافه می‌شود!",
            "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
        })
        return
    
    btns = []
    for m in ms:
        done = await is_done(uid, m["ch"])
        if done:
            btns.append([{"text": f"✅ {m['ch']} - انجام شده ✓", "callback_data": "MN"}])
        else:
            btns.append([{"text": f"📢 عضویت در {m['ch']}", "url": f"https://t.me/{m['ch'].replace('@','')}"}])
            btns.append([{"text": f"✅ تایید عضویت (+{m['pay']} {STAR})", "callback_data": f"MS:{m['ch']}"}])
    btns.append([{"text": "🔙 بازگشت", "callback_data": "MN"}])
    
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🎯 مرکز ماموریت‌ها\n{L2}\n\n{STAR} پاداش استارز برای عضویت!\n\n📌 مراحل انجام:\n\n1️⃣ روی «📢 عضویت» بزنید\n2️⃣ در کانال عضو شوید\n3️⃣ به ربات برگردید\n4️⃣ «✅ تایید» بزنید\n5️⃣ استارز دریافت کنید ✅\n\n{L1}\n\n💡 هر ماموریت فقط یکبار قابل انجام است.",
        "reply_markup": J({"inline_keyboard": btns})
    })

async def tabchi_page(cid, uid):
    user = await get_user(uid)
    if not user or (user.get("tabchi_exp",0) or 0) < now():
        await tg("sendMessage", {
            "chat_id": cid,
            "text": f"{ROCKET} تبچی هوشمند\n{L2}\n\n🔒 این بخش قفل است\n\n📌 مشخصات:\n💵 قیمت: {F(TABCHI_PRICE)} تومان\n⏰ مدت: {TABCHI_DAYS} روز\n\n⚠️ فعال‌سازی توسط مدیریت\n\n{L1}\n\n🎯 امکانات:\n\n📱 ورود با شماره\n🎯 استفاده از گروه‌ها\n🖼 ارسال بنر\n⏰ زمان‌بندی دلخواه\n🤖 جوین خودکار\n📊 آمار دقیق\n♾ بک‌گراند",
            "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
        })
        return
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"{ROCKET} تبچی فعال!\n⏰ اعتبار: {time_left(user['tabchi_exp'])}",
        "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
    })

async def my_orders_page(cid, uid):
    async with db.acquire() as c:
        rows = await c.fetch("SELECT * FROM star_orders WHERE uid=$1 ORDER BY created_at DESC LIMIT 10", uid)
    if not rows:
        await tg("sendMessage", {"chat_id": cid, "text": f"📋 تاریخچه سفارشات\n{L1}\n\n❌ هنوز سفارشی ثبت نکرده‌اید.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})
        return
    t = f"📋 تاریخچه سفارشات شما\n{L2}\n\n"
    for o in rows:
        o = dict(o)
        st = "✅" if o["status"] == "done" else "🟡"
        t += f"{st} <code>{o['track']}</code>\n{STAR} {o['amount']} | 📅 {fDate(o['created_at'])}\n{L1}\n"
    await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})# ══════════════ WEBHOOK ══════════════
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
    base = str(req.base_url).rstrip("/").replace("http://","https://")
    return await tg("setWebhook", {"url": f"{base}/", "drop_pending_updates": True, "max_connections": 100})

@app.get("/health")
async def health():
    total = await count_users()
    active = await count_active()
    stats = await get_bot_stats()
    return {"status": "healthy", "version": "5.0", "users": total, "active_7d": active, "stats": stats}

# ══════════════ MESSAGE HANDLER ══════════════
async def on_msg(m):
    try:
        cid = m["chat"]["id"]
        uid = m["from"]["id"]
        txt = (m.get("text") or "").strip()
        un = m["from"].get("username", "")
        fn = m["from"].get("first_name", "کاربر")
        
        await reg_user(uid, un, fn)
        
        if txt in ["❌ لغو", "/cancel", "/reset"]:
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ عملیات لغو شد.", "reply_markup": J({"remove_keyboard": True})})
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
                            await tg("sendMessage", {"chat_id": r, "text": f"🎊 زیرمجموعه جدید!\n{L1}\n\n📌 وضعیت: در انتظار تکمیل\n\n⚠️ تا زمانی که کاربر:\n1️⃣ در کانال‌ها عضو نشود\n2️⃣ کپچا حل نکند\n\n{STAR} جایزه واریز نمی‌شود.\n\n💡 هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز"})
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
        
        # کپچا
        if st and st.startswith("CAP:"):
            correct = int(st.split(":")[1])
            try:
                ans = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فقط عدد وارد کنید."})
                return
            if ans == correct:
                await set_verified(uid)
                await clr_st(uid)
                await tg("sendMessage", {"chat_id": cid, "text": f"✅ تایید موفق!\n{L1}\n\n{SPARKLE} خوش آمدید!", "reply_markup": J({"remove_keyboard": True})})
                await process_ref(uid, fn)
                await main_menu(cid, fn, uid)
            else:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ اشتباه!\n🔄 کپچای جدید:"})
                await send_captcha(cid, uid)
            return
        
        # لینک استارز
        if st == "SL":
            if "t.me/" not in txt:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ لینک نامعتبر!\n\nنمونه:\nhttps://t.me/channel/123"})
                return
            await kv_set(f"sl:{uid}", txt)
            await set_st(uid, "SA")
            stars = await get_stars(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ لینک ثبت شد!\n{L1}\n\n{STAR} موجودی: <b>{stars}</b> استارز\n\n📝 تعداد استارز مورد نظر را وارد کنید:\n\n💡 حداقل: 1\n💡 حداکثر: {stars}\n\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        # تعداد استارز
        if st == "SA":
            try:
                amt = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد معتبر وارد کنید!"})
                return
            if amt <= 0:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد مثبت!"})
                return
            stars = await get_stars(uid)
            if amt > stars:
                await tg("sendMessage", {"chat_id": cid, "text": f"❌ موجودی کافی نیست!\n\n{STAR} موجودی: {stars}\n📝 درخواست: {amt}"})
                return
            link = await kv_get(f"sl:{uid}")
            if not link:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ لینک یافت نشد."})
                await clr_st(uid)
                return
            ok = await remove_stars(uid, amt)
            if not ok:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ خطا."})
                await clr_st(uid)
                return
            tc = track_code()
            await create_order(tc, uid, un, fn, link, amt)
            await clr_st(uid)
            
            new_stars = await get_stars(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"{SPARKLE} سفارش شما با موفقیت ثبت شد!\n{L2}\n\n🔢 کد پیگیری: <code>{tc}</code>\n\n📋 جزئیات سفارش:\n🎯 مقصد: {link}\n{STAR} تعداد استارز: {amt}\n{STAR} موجودی باقیمانده: {new_stars}\n\n⏱ زمان پردازش: حداکثر 24 ساعت\n📌 وضعیت: 🟡 در حال بررسی\n\n{L1}\n\n💡 پس از انجام سفارش، اطلاع‌رسانی خواهد شد.\n📌 کد پیگیری را ذخیره کنید.", "parse_mode": "HTML", "reply_markup": J({"remove_keyboard": True})})
            
            await tg("sendMessage", {"chat_id": ADMIN, "text": f"{STAR} سفارش استارز جدید!\n{L2}\n\n🔢 کد پیگیری: <code>{tc}</code>\n\n👤 اطلاعات سفارش‌دهنده:\n🆔 یوزرنیم: {'@'+un if un else 'ندارد'}\n🔢 شماره کاربری: <code>{uid}</code>\n📛 نام: {fn}\n\n🎯 لینک مقصد: {link}\n{STAR} تعداد استارز: {amt}\n\n⏰ زمان ثبت: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n📌 وضعیت: 🟡 در انتظار انجام", "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": J({"inline_keyboard": [[{"text": "✅ سفارش انجام شد", "callback_data": f"STDONE:{tc}"}]]})})
            
            await log_order({"post_link": link, "amount": amt})
            await main_menu(cid, fn, uid)
            return
        
        # broadcast
        if st == "BC" and uid == ADMIN:
            await do_broadcast(cid, m)
            await clr_st(uid)
            return
        
        # افزودن کانال
        if st == "AC" and uid == ADMIN:
            inp = txt.strip()
            save = ""
            if inp.startswith("@"): save = inp
            elif inp.startswith("https://t.me/+") or inp.startswith("https://t.me/joinchat/"): save = inp
            elif inp.startswith("https://t.me/"): save = "@" + inp.replace("https://t.me/","").split("/")[0]
            else:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فرمت نامعتبر!"})
                return
            await add_ch(save)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {save} اضافه شد!", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st == "RC" and uid == ADMIN:
            await rm_ch(txt)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ حذف شد.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st and st.startswith("RP:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            if m.get("text"): await tg("sendMessage", {"chat_id": tid, "text": f"📬 پاسخ مدیریت\n{L1}\n\n{m['text']}"})
            elif m.get("photo"): await tg("sendPhoto", {"chat_id": tid, "photo": m["photo"][-1]["file_id"], "caption": f"📬 پاسخ مدیریت\n{m.get('caption','')}"})
            elif m.get("video"): await tg("sendVideo", {"chat_id": tid, "video": m["video"]["file_id"], "caption": f"📬 پاسخ مدیریت"})
            else: await tg("forwardMessage", {"chat_id": tid, "from_chat_id": cid, "message_id": m["message_id"]})
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ پاسخ به <code>{tid}</code> ارسال شد.", "parse_mode": "HTML", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st == "SU" and uid == ADMIN:
            try: sid = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            user = await get_user(sid)
            if not user:
                await clr_st(uid)
                await tg("sendMessage", {"chat_id": cid, "text": "❌ یافت نشد.", "reply_markup": J({"remove_keyboard": True})})
                await admin_panel(cid)
                return
            refs = len(user.get("refs") or [])
            t = f"👤 پروفایل کاربر\n{L2}\n\n🔢 <code>{user['uid']}</code>\n🆔 {'@'+user['username'] if user['username'] else 'ندارد'}\n📛 {user['first_name']}\n📅 {fDate(user['created_at'])}\n\n📊 آمار:\n👥 زیرمجموعه: {refs}\n{STAR} استارز: {user['stars']}\n{STAR} کل دریافتی: {user.get('total_earned',0)}\n💫 کل برداشتی: {user.get('total_withdrawn',0)}\n📋 سفارشات: {user.get('orders_count',0)}\n\n📦 اشتراک:\n{ROCKET} تبچی: {'✅' if (user.get('tabchi_exp',0) or 0) > now() else '❌'}"
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": cid, "text": "⚙️ عملیات:", "reply_markup": J({"inline_keyboard": [[{"text": f"{STAR} افزودن استارز", "callback_data": f"ADDSTAR:{sid}"}], [{"text": f"{ROCKET} فعال‌سازی تبچی", "callback_data": f"TB{sid}"}], [{"text": "🔙 پنل مدیریت", "callback_data": "AP"}]]})})
            return
        
        if st and st.startswith("ADDSTAR:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try: amt = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            await add_stars(tid, amt)
            nw = await get_stars(tid)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {amt} استارز به {tid} اضافه شد.\n{STAR} موجودی: {nw}", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": f"🎁 هدیه از مدیریت!\n{L1}\n\n{STAR} {amt} استارز اضافه شد!\n{STAR} موجودی: {nw}"})
            await admin_panel(cid)
            return
        
        if st == "MA" and uid == ADMIN:
            p = txt.split(" ")
            if len(p) < 2 or not p[0].startswith("@"):
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فرمت: @channel 2"})
                return
            try: pay = int(p[1])
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            await add_mission(p[0], pay)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ ماموریت ثبت شد.\n📢 {p[0]}\n{STAR} {pay} استارز", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st == "MR" and uid == ADMIN:
            await rm_mission(txt.strip())
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ حذف شد.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st and st.startswith("TB:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try: days = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            exp = now() + (days * 86400000)
            async with db.acquire() as c:
                await c.execute("UPDATE users SET tabchi_exp=$2 WHERE uid=$1", tid, exp)
            await clr_st(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ تبچی فعال!\n👤 {tid}\n📅 {days} روز", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": f"🎊 تبریک!\n{L1}\n\n{ROCKET} تبچی فعال شد!\n📅 {days} روز"})
            await admin_panel(cid)
            return
        
        # منو
        menu = [f"{STAR} استارز رایگان {STAR}", "👥 زیرمجموعه گیری", "👤 حساب کاربری", f"{STAR} کیف پول استارزی", "🎯 انجام ماموریت", "🛒 ساخت پنل", f"{ROCKET} تبچی"]
        if txt in menu:
            nj = await check_join(uid)
            if nj:
                await send_join(cid, nj)
                return
            if not await is_verified(uid):
                await send_captcha(cid, uid)
                return
        
        if txt == f"{STAR} استارز رایگان {STAR}": await stars_page(cid, uid); return
        if txt == "👥 زیرمجموعه گیری": await ref_page(cid, uid); return
        if txt == "👤 حساب کاربری": await acc_page(cid, uid, un); return
        if txt == f"{STAR} کیف پول استارزی": await wallet_page(cid, uid); return
        if txt == "🛒 ساخت پنل": await shop_page(cid, uid); return
        if txt == "🎯 انجام ماموریت": await mission_page(cid, uid); return
        if txt == f"{ROCKET} تبچی": await tabchi_page(cid, uid); return
        if txt == "⚙️ پنل مدیریت" and uid == ADMIN:
            await clr_st(uid)
            await admin_panel(cid)
            return
    
    except Exception as e:
        print(f"msg err: {e}")
        traceback.print_exc()# ══════════════ CALLBACK HANDLER ══════════════
async def on_cb(q):
    try:
        cid = q["message"]["chat"]["id"]
        uid = q["from"]["id"]
        d = q.get("data", "")
        fn = q["from"].get("first_name", "کاربر")
        mid = q["message"]["message_id"]
        un = q["from"].get("username", "")
        
        try:
            await tg("answerCallbackQuery", {"callback_query_id": q["id"]})
        except:
            pass
        
        if d == "CJ":
            nj = await check_join(uid)
            if nj:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "❌ هنوز عضو نشدید!", "show_alert": True})
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
            await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "✅ قبلاً انجام شده"})
            return
        
        # برداشت استارز
        if d == "STARS_WD":
            stars = await get_stars(uid)
            if stars <= 0:
                await tg("sendMessage", {
                    "chat_id": cid,
                    "text": f"❌ برداشت ناموفق!\n{L1}\n\n{STAR} موجودی شما: <b>0</b> استارز\n\n📌 هیچ استارزی برای برداشت ندارید!\n\n{L1}\n\n💡 راه‌های کسب استارز:\n\n1️⃣ دعوت دوستان (هر {NEEDREF} نفر = {STARS_PER_REF} {STAR})\n2️⃣ انجام ماموریت‌ها\n\n{FIRE} از بخش «👥 زیرمجموعه گیری» لینک بگیرید!",
                    "parse_mode": "HTML",
                    "reply_markup": J({"inline_keyboard": [[{"text": "👥 زیرمجموعه گیری", "callback_data": "MN"}], [{"text": "🎯 ماموریت‌ها", "callback_data": "MN"}], [{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
                })
                return
            await set_st(uid, "SL")
            await tg_del(cid, mid)
            await tg("sendMessage", {
                "chat_id": cid,
                "text": f"💫 برداشت استارز رایگان\n{L2}\n\n{STAR} موجودی شما: <b>{stars}</b> استارز\n\n{L1}\n\n📝 لینک پست کانالی که می‌خواهید به آن استارز بدهید را ارسال کنید:\n\n💡 فرمت لینک:\n<code>https://t.me/channel/123</code>\n\n📌 نکات مهم:\n\n✅ پست باید در کانال عمومی باشد\n✅ حداکثر {stars} استارز\n✅ هر لینک فقط یکبار\n\n⚠️ لغو: «❌ لغو»",
                "parse_mode": "HTML",
                "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})
            })
            return
        
        # تاریخچه سفارشات
        if d == "MY_ORDERS":
            await tg_del(cid, mid)
            await my_orders_page(cid, uid)
            return
        
        # سفارش انجام شد
        if d.startswith("STDONE:") and uid == ADMIN:
            try:
                tc = d[7:]
                order = await get_order(tc)
                if not order:
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "❌ سفارش یافت نشد!", "show_alert": True})
                    return
                if order["status"] == "done":
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ قبلاً انجام شده!", "show_alert": True})
                    return
                
                await done_order(tc)
                
                r = await tg("sendMessage", {
                    "chat_id": int(order["uid"]),
                    "text": f"🎊{SPARKLE} تبریک! سفارش شما انجام شد! {SPARKLE}🎊\n{L2}\n\n✅ سفارش استارز رایگان شما با موفقیت پردازش شد!\n\n📋 جزئیات سفارش:\n\n🔢 کد پیگیری: <code>{tc}</code>\n🎯 مقصد: {order['post_link']}\n{STAR} تعداد ارسال شده: {order['amount']} استارز\n\n{L1}\n\n{DIAMOND} با تشکر از اعتماد شما!\n\n💫 برای دریافت استارز بیشتر:\n• دوستان بیشتری دعوت کنید\n• ماموریت‌ها را انجام دهید\n\n{FIRE} استارز رایگان منتظر شماست!",
                    "parse_mode": "HTML"
                })
                
                try:
                    await tg("editMessageReplyMarkup", {"chat_id": cid, "message_id": mid, "reply_markup": J({"inline_keyboard": [[{"text": "✅ انجام شده ✓", "callback_data": "DONE"}]]})})
                except:
                    pass
                
                if r and r.get("ok"):
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "✅ پیام تبریک به کاربر ارسال شد!", "show_alert": True})
                else:
                    await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ سفارش ثبت شد ولی ارسال پیام ناموفق", "show_alert": True})
            except Exception as e:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": f"❌ خطا: {str(e)[:50]}", "show_alert": True})
            return
        
        # لیست سفارشات
        if d == "STLIST" and uid == ADMIN:
            orders = await get_orders(20)
            if not orders:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ سفارشی ثبت نشده.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
                return
            pending = sum(1 for o in orders if o["status"] != "done")
            done_cnt = sum(1 for o in orders if o["status"] == "done")
            t = f"{STAR} لیست سفارشات استارز\n{L2}\n\n📊 آمار: {len(orders)} سفارش\n✅ انجام شده: {done_cnt}\n🟡 در انتظار: {pending}\n\n{L1}\n\n"
            for o in orders[:15]:
                st = "✅" if o["status"] == "done" else "🟡"
                t += f"{st} <code>{o['track']}</code>\n👤 {'@'+o['username'] if o['username'] else 'ID:'+str(o['uid'])}\n{STAR} {o['amount']} | 📅 {fDate(o['created_at'])}\n{L1}\n"
            if len(orders) > 15:
                t += f"\n... و {len(orders)-15} مورد دیگر"
            await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # پیام همگانی
        if d == "AB" and uid == ADMIN:
            await set_st(uid, "BC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"📨 ارسال پیام همگانی\n{L1}\n\n✍️ پیام خود را ارسال کنید:\n\n📌 پشتیبانی از: متن/عکس/ویدیو/فایل\n\n💡 پیام به تمامی کاربران ارسال خواهد شد.\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AA" and uid == ADMIN:
            await set_st(uid, "AC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"➕ افزودن کانال/گروه\n{L1}\n\n📌 فرمت‌های مجاز:\n\n@channel\nhttps://t.me/channel\nhttps://t.me/+abc123\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AR" and uid == ADMIN:
            chs = await get_chs()
            if not chs:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ کانالی نیست."})
                return
            await set_st(uid, "RC")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"➖ حذف کانال\n{L1}\n\n" + "\n".join(f"{i+1}. {c}" for i,c in enumerate(chs)) + "\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AL" and uid == ADMIN:
            chs = await get_chs()
            t = f"📋 لیست کانال‌ها\n{L1}\n\n" + "\n".join(f"{i+1}. {c}" for i,c in enumerate(chs)) + f"\n\n📊 مجموع: {len(chs)}" if chs else "❌ کانالی نیست."
            await tg("sendMessage", {"chat_id": cid, "text": t, "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        if d == "AS" and uid == ADMIN:
            total = await count_users()
            active = await count_active()
            ms = await get_missions()
            chs = await get_chs()
            stats = await get_bot_stats()
            await tg("sendMessage", {
                "chat_id": cid,
                "text": f"📊 آمار پیشرفته ربات\n{L2}\n\n👥 کل کاربران: <b>{total}</b>\n👥 فعال ۷ روز: <b>{active}</b>\n📢 کانال‌ها: <b>{len(chs)}</b>\n🎯 ماموریت‌ها: <b>{len(ms)}</b>\n\n{STAR} کل استارز: <b>{stats.get('total_stars_given',0)}</b>\n📋 کل سفارشات: <b>{stats.get('total_orders',0)}</b>\n✅ انجام شده: <b>{stats.get('total_orders_done',0)}</b>",
                "parse_mode": "HTML",
                "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})
            })
            return
        
        # صفر کردن زیرمجموعه
        if d == "AX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": f"⚠️ هشدار جدی!\n{L1}\n\n❗ تمامی زیرمجموعه‌ها و استارزها صفر می‌شوند!\n\n❌ غیرقابل بازگشت!", "reply_markup": J({"inline_keyboard": [[{"text": "✅ بله، مطمئنم", "callback_data": "DX"}], [{"text": "❌ انصراف", "callback_data": "AP"}]]})})
            return
        
        if d == "DX" and uid == ADMIN:
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"⏳ در حال صفر کردن...\n\n📌 لطفاً صبر کنید..."})
            await reset_refs_all()
            total = await count_users()
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ عملیات کامل شد!\n{L1}\n\n👥 {total} کاربر صفر شدند\n🔄 زیرمجموعه‌ها: صفر ✓\n{STAR} استارز: صفر ✓\n📋 آمار: ریست ✓", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # صفر کردن استارز
        if d == "STX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": f"⚠️ استارز همه صفر بشه؟\n\n❌ غیرقابل بازگشت!", "reply_markup": J({"inline_keyboard": [[{"text": "✅ بله", "callback_data": "DSTX"}], [{"text": "❌ انصراف", "callback_data": "AP"}]]})})
            return
        
        if d == "DSTX" and uid == ADMIN:
            await tg_del(cid, mid)
            await reset_stars_all()
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ استارز همه کاربران صفر شد.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # جستجوی کاربر
        if d == "SU" and uid == ADMIN:
            await set_st(uid, "SU")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🔍 جستجوی کاربر\n{L1}\n\n📝 شماره کاربری عددی را ارسال کنید:\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d.startswith("ADDSTAR:") and uid == ADMIN:
            tid = d[8:]
            await set_st(uid, f"ADDSTAR:{tid}")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"{STAR} افزودن استارز\n{L1}\n\n👤 کاربر: <code>{tid}</code>\n\n📝 تعداد استارز:\n\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d.startswith("TB") and uid == ADMIN and not d.startswith("TB:"):
            tid = d[2:]
            await set_st(uid, f"TB:{tid}")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"{ROCKET} فعال‌سازی تبچی\n{L1}\n\n👤 <code>{tid}</code>\n\n📅 تعداد روز:\n\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "MA" and uid == ADMIN:
            await set_st(uid, "MA")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🎯 افزودن ماموریت\n{L1}\n\n📝 فرمت:\n@channel تعداد_استارز\n\nمثال: @mychannel 2\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "MR" and uid == ADMIN:
            ms = await get_missions()
            if not ms:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ ماموریتی نیست."})
                return
            await set_st(uid, "MR")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🗑 حذف ماموریت\n{L1}\n\n" + "\n".join(f"{m['ch']} - {m['pay']}{STAR}" for m in ms) + "\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "ML" and uid == ADMIN:
            ms = await get_missions()
            t = f"📋 لیست ماموریت‌ها\n{L2}\n\n" + "\n".join(f"{i+1}. 📢 {m['ch']}\n   {STAR} {m['pay']} استارز" for i,m in enumerate(ms)) + f"\n\n📊 مجموع: {len(ms)}" if ms else "❌ ماموریتی نیست."
            await tg("sendMessage", {"chat_id": cid, "text": t, "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # ماموریت
        if d.startswith("MS:"):
            ch = d[3:]
            ms = await get_missions()
            mi = next((m for m in ms if m["ch"] == ch), None)
            if not mi:
                return
            r = await tg("getChatMember", {"chat_id": ch, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member","administrator","creator"]:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "❌ ابتدا عضو شوید!", "show_alert": True})
                return
            if await is_done(uid, ch):
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ قبلاً انجام شده", "show_alert": True})
                return
            await mark_done(uid, ch)
            await add_stars(uid, mi["pay"])
            nw = await get_stars(uid)
            await tg_del(cid, mid)
            await tg("sendMessage", {
                "chat_id": cid,
                "text": f"🎉 ماموریت با موفقیت انجام شد!\n{L1}\n\n📢 کانال: {ch}\n{STAR} پاداش: +{mi['pay']} استارز\n{STAR} موجودی جدید: {nw}\n\n{SPARKLE} عالیه! ادامه بدید!",
                "reply_markup": J({"inline_keyboard": [[{"text": "🎯 سایر ماموریت‌ها", "callback_data": "MN"}], [{"text": "🔙 منو", "callback_data": "MN"}]]})
            })
            return
        
        # پاسخ ادمین
        if d.startswith("RP") and uid == ADMIN:
            tid = d[2:]
            await set_st(uid, f"RP:{tid}")
            await tg_del(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"📩 پاسخ به کاربر\n{L1}\n\n👤 <code>{tid}</code>\n\n📝 پیام:\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
    
    except Exception as e:
        print(f"cb err: {e}")
        traceback.print_exc()

# ══════════════ BROADCAST ══════════════
async def do_broadcast(cid, m):
    try:
        uids = await all_uids()
        if not uids:
            await tg("sendMessage", {"chat_id": cid, "text": "❌ کاربری نیست.", "reply_markup": J({"remove_keyboard": True})})
            return
        
        total = len(uids)
        await tg("sendMessage", {"chat_id": cid, "text": f"📨 شروع ارسال...\n{L1}\n\n👥 تعداد: {total} کاربر\n⏳ لطفاً صبر کنید...", "reply_markup": J({"remove_keyboard": True})})
        
        ok = 0
        fail = 0
        
        async with aiohttp.ClientSession() as session:
            for i in range(0, total, 30):
                batch = uids[i:i+30]
                tasks = []
                for u in batch:
                    try:
                        if m.get("text"):
                            tasks.append(session.post(f"{TAPI}/sendMessage", json={"chat_id": u, "text": m["text"]}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("photo"):
                            tasks.append(session.post(f"{TAPI}/sendPhoto", json={"chat_id": u, "photo": m["photo"][-1]["file_id"], "caption": m.get("caption","")}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("video"):
                            tasks.append(session.post(f"{TAPI}/sendVideo", json={"chat_id": u, "video": m["video"]["file_id"], "caption": m.get("caption","")}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("document"):
                            tasks.append(session.post(f"{TAPI}/sendDocument", json={"chat_id": u, "document": m["document"]["file_id"], "caption": m.get("caption","")}, timeout=aiohttp.ClientTimeout(total=10)))
                        elif m.get("sticker"):
                            tasks.append(session.post(f"{TAPI}/sendSticker", json={"chat_id": u, "sticker": m["sticker"]["file_id"]}, timeout=aiohttp.ClientTimeout(total=10)))
                    except:
                        pass
                
                if tasks:
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, Exception):
                            fail += 1
                        else:
                            try:
                                data = await r.json()
                                if data.get("ok"):
                                    ok += 1
                                else:
                                    fail += 1
                            except:
                                fail += 1
                
                if (i + 30) % 300 == 0 and i > 0:
                    pct = round(((i+30)/total)*100)
                    await tg("sendMessage", {"chat_id": cid, "text": f"📊 پیشرفت: {i+30}/{total} ({pct}%)\n✅ {ok} | ❌ {fail}"})
                
                await asyncio.sleep(1)
        
        pct = round((ok/total)*100) if total > 0 else 0
        await tg("sendMessage", {
            "chat_id": cid,
            "text": f"🎊 ارسال کامل شد!\n{L2}\n\n📊 نتیجه نهایی:\n\n✅ موفق: <b>{ok}</b> کاربر\n❌ ناموفق: <b>{fail}</b> کاربر\n📝 کل: <b>{total}</b> کاربر\n📈 درصد موفقیت: <b>{pct}%</b>",
            "parse_mode": "HTML",
            "reply_markup": J({"inline_keyboard": [[{"text": "🔙 منو", "callback_data": "MN"}]]})
        })
    except Exception as e:
        await tg("sendMessage", {"chat_id": cid, "text": f"❌ خطا: {e}", "reply_markup": J({"remove_keyboard": True})})
