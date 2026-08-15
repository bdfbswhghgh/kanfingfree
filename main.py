import os
import re
import asyncio
import json
import random
import traceback
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
import aiohttp
import asyncpg

# ========== CONFIG ==========
TOKEN = os.getenv("BOT_TOKEN", "8519305274:AAEeacmOTiBCzHpDqr4Bk5D7ZPtlu49rzCY")
ADMIN = int(os.getenv("ADMIN_ID", "8248647747"))
TAPI = f"https://api.telegram.org/bot{TOKEN}"
DATABASE_URL = os.getenv("DATABASE_URL", "")
SECRET_KEY = os.getenv("SECRET_KEY", "MySecret2026BotXYZ")
DEFCH = "@kanfingfree"
FORCED_CH = "@kanfingfree"
LOG_CH = "@starsdarkconfig"
NEEDREF = 3
STARS_PER_REF = 1
TABCHI_PRICE = 150000
TABCHI_DAYS = 30
LINE = "━━━━━━━━━━━━━━━━━━━"
LINE2 = "═══════════════════"

# ========== DATABASE ==========
db_pool = None

async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                uid BIGINT PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                refs BIGINT[] DEFAULT '{}',
                referred_by BIGINT DEFAULT NULL,
                stars INTEGER DEFAULT 0,
                tabchi_exp BIGINT DEFAULT 0,
                verified BOOLEAN DEFAULT FALSE,
                created_at BIGINT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS channels (
                id SERIAL PRIMARY KEY,
                channel TEXT UNIQUE NOT NULL
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS missions (
                id SERIAL PRIMARY KEY,
                channel TEXT UNIQUE NOT NULL,
                reward INTEGER DEFAULT 1
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS mission_done (
                uid BIGINT,
                channel TEXT,
                PRIMARY KEY (uid, channel)
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS star_orders (
                track_code TEXT PRIMARY KEY,
                uid BIGINT,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                post_link TEXT DEFAULT '',
                amount INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending',
                created_at BIGINT DEFAULT 0,
                done_at BIGINT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_refs (
                new_uid BIGINT PRIMARY KEY,
                referrer_uid BIGINT,
                created_at BIGINT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS states (
                uid BIGINT PRIMARY KEY,
                state TEXT DEFAULT '',
                expires_at BIGINT DEFAULT 0
            )
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value TEXT DEFAULT ''
            )
        ''')
        # اضافه کردن کانال پیش‌فرض
        try:
            await conn.execute("INSERT INTO channels (channel) VALUES ($1) ON CONFLICT DO NOTHING", DEFCH)
        except:
            pass
    print("✅ Database initialized")

@asynccontextmanager
async def lifespan(app):
    await init_db()
    yield
    if db_pool:
        await db_pool.close()

app = FastAPI(title="Bot API", version="4.0", lifespan=lifespan)

# ========== TG API ==========
async def tg(method, body):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{TAPI}/{method}", json=body, timeout=aiohttp.ClientTimeout(total=10)) as r:
                return await r.json()
    except:
        return None

async def tg_delete(chat_id, msg_id):
    try:
        await tg("deleteMessage", {"chat_id": chat_id, "message_id": msg_id})
    except:
        pass

_bot_username = None
async def bot_username():
    global _bot_username
    if _bot_username:
        return _bot_username
    r = await tg("getMe", {})
    if r and r.get("ok"):
        _bot_username = r["result"]["username"]
    return _bot_username or "bot"

# ========== HELPERS ==========
def J(o):
    return json.dumps(o)

def F(n):
    return f"{n:,}" if isinstance(n, int) else str(n)

def fD(ts):
    try:
        return datetime.fromtimestamp(ts / 1000).strftime("%Y/%m/%d")
    except:
        return "-"

def esc(s):
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def gen_captcha():
    a = random.randint(1, 9)
    b = random.randint(1, 9)
    if random.random() > 0.5:
        return f"{a} + {b}", a + b
    else:
        big, small = max(a, b), min(a, b)
        return f"{big} - {small}", big - small

def gen_track():
    return "STR-" + "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=6))

def time_left(ts):
    d = ts - int(datetime.now().timestamp() * 1000)
    if d <= 0:
        return "منقضی شده"
    days = d // 86400000
    hrs = (d % 86400000) // 3600000
    return f"{days} روز و {hrs} ساعت"

def now_ms():
    return int(datetime.now().timestamp() * 1000)

# ========== DB HELPERS ==========
async def get_user(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid=$1", uid)
        return dict(row) if row else None

async def reg_user(uid, username="", first_name=""):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT uid FROM users WHERE uid=$1", uid)
        if not existing:
            await conn.execute(
                "INSERT INTO users (uid, username, first_name, refs, stars, created_at) VALUES ($1,$2,$3,'{}',0,$4)",
                uid, username, first_name, now_ms()
            )
        else:
            if username:
                await conn.execute("UPDATE users SET username=$2 WHERE uid=$1", uid, username)
            if first_name:
                await conn.execute("UPDATE users SET first_name=$2 WHERE uid=$1", uid, first_name)

async def get_refs_count(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT refs FROM users WHERE uid=$1", uid)
        if row and row["refs"]:
            return len(row["refs"])
        return 0

async def get_stars(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT stars FROM users WHERE uid=$1", uid)
        return row["stars"] if row else 0

async def add_stars(uid, amount):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET stars = stars + $2 WHERE uid=$1", uid, amount)

async def remove_stars(uid, amount):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT stars FROM users WHERE uid=$1", uid)
        if not row or row["stars"] < amount:
            return False
        await conn.execute("UPDATE users SET stars = stars - $2 WHERE uid=$1", uid, amount)
        return True

async def set_verified(uid):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET verified=TRUE WHERE uid=$1", uid)

async def is_verified(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT verified FROM users WHERE uid=$1", uid)
        return row["verified"] if row else False

async def get_all_uids():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT uid FROM users")
        return [row["uid"] for row in rows]

async def count_users():
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT COUNT(*) as cnt FROM users")
        return row["cnt"]

async def reset_all_refs():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET refs='{}', referred_by=NULL, stars=0")
        await conn.execute("DELETE FROM pending_refs")

async def reset_all_stars():
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE users SET stars=0")

# State
async def get_state(uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT state, expires_at FROM states WHERE uid=$1", uid)
        if row:
            if row["expires_at"] > 0 and row["expires_at"] < now_ms():
                await conn.execute("DELETE FROM states WHERE uid=$1", uid)
                return ""
            return row["state"]
        return ""

async def set_state(uid, state):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO states (uid, state, expires_at) VALUES ($1,$2,$3) ON CONFLICT (uid) DO UPDATE SET state=$2, expires_at=$3",
            uid, state, now_ms() + 3600000
        )

async def clear_state(uid):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM states WHERE uid=$1", uid)

# Channels
async def get_channels():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT channel FROM channels")
        return [row["channel"] for row in rows] if rows else [DEFCH]

async def add_channel(ch):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO channels (channel) VALUES ($1) ON CONFLICT DO NOTHING", ch)

async def remove_channel(ch):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM channels WHERE channel=$1", ch)

# Missions
async def get_missions():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT channel, reward FROM missions")
        return [{"ch": row["channel"], "pay": row["reward"]} for row in rows]

async def add_mission(ch, reward):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO missions (channel, reward) VALUES ($1,$2) ON CONFLICT (channel) DO UPDATE SET reward=$2",
            ch, reward
        )

async def remove_mission(ch):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM missions WHERE channel=$1", ch)

async def is_mission_done(uid, ch):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT 1 FROM mission_done WHERE uid=$1 AND channel=$2", uid, ch)
        return row is not None

async def mark_mission_done(uid, ch):
    async with db_pool.acquire() as conn:
        await conn.execute("INSERT INTO mission_done (uid, channel) VALUES ($1,$2) ON CONFLICT DO NOTHING", uid, ch)

# Pending refs
async def set_pending(new_uid, ref_uid):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO pending_refs (new_uid, referrer_uid, created_at) VALUES ($1,$2,$3) ON CONFLICT (new_uid) DO NOTHING",
            new_uid, ref_uid, now_ms()
        )

async def get_pending(new_uid):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT referrer_uid FROM pending_refs WHERE new_uid=$1", new_uid)
        return row["referrer_uid"] if row else None

async def delete_pending(new_uid):
    async with db_pool.acquire() as conn:
        await conn.execute("DELETE FROM pending_refs WHERE new_uid=$1", new_uid)

# Star orders
async def create_order(track, uid, username, first_name, post_link, amount):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO star_orders (track_code, uid, username, first_name, post_link, amount, status, created_at) VALUES ($1,$2,$3,$4,$5,$6,'pending',$7)",
            track, uid, username, first_name, post_link, amount, now_ms()
        )

async def get_order(track):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM star_orders WHERE track_code=$1", track)
        return dict(row) if row else None

async def complete_order(track):
    async with db_pool.acquire() as conn:
        await conn.execute("UPDATE star_orders SET status='done', done_at=$2 WHERE track_code=$1", track, now_ms())

async def get_all_orders():
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM star_orders ORDER BY created_at DESC LIMIT 20")
        return [dict(row) for row in rows]

# KV store
async def kv_get(key):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT value FROM kv_store WHERE key=$1", key)
        return row["value"] if row else None

async def kv_set(key, value):
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO kv_store (key, value) VALUES ($1,$2) ON CONFLICT (key) DO UPDATE SET value=$2",
            key, value
        )# ========== CHECK JOIN ==========
async def check_join(uid):
    channels = await get_channels()
    not_joined = []
    for ch in channels:
        try:
            check_id = ch
            if ch.startswith("https://t.me/+") or ch.startswith("https://t.me/joinchat/"):
                not_joined.append(ch)
                continue
            if ch.startswith("https://t.me/"):
                check_id = "@" + ch.replace("https://t.me/", "").split("/")[0]
            r = await tg("getChatMember", {"chat_id": check_id, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member", "administrator", "creator"]:
                not_joined.append(ch)
        except:
            not_joined.append(ch)
    return not_joined

async def send_join_msg(cid, nj):
    btns = []
    for ch in nj:
        if ch.startswith("https://"):
            url = ch
            name = ch.replace("https://t.me/", "").replace("+", "")[:20]
        else:
            url = f"https://t.me/{ch.replace('@', '')}"
            name = ch
        btns.append([{"text": f"📢 عضویت در {name}", "url": url}])
    btns.append([{"text": "✅ عضو شدم، تایید کن", "callback_data": "CJ"}])
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"⚠️ عضویت اجباری\n{LINE}\n\n📌 برای استفاده از ربات، ابتدا در کانال‌ها/گروه‌های زیر عضو شوید:\n\n" + "\n".join(nj) + "\n\n✅ سپس دکمه «عضو شدم» را بزنید.",
        "reply_markup": J({"inline_keyboard": btns})
    })

async def send_captcha(cid, uid):
    q, ans = gen_captcha()
    await set_state(uid, f"CAPTCHA:{ans}")
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🔐 تایید امنیتی\n{LINE}\n\n🧮 حاصل عبارت زیر را وارد کنید:\n\n➤ {q} = ?\n\n💡 فقط عدد ارسال کنید.",
        "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})
    })

async def process_pending_ref(uid, fn):
    try:
        rid = await get_pending(uid)
        if not rid:
            return
        await delete_pending(uid)
        
        user = await get_user(uid)
        if user and user["referred_by"]:
            return
        
        async with db_pool.acquire() as conn:
            await conn.execute("UPDATE users SET referred_by=$2 WHERE uid=$1", uid, rid)
            
            ref_user = await get_user(rid)
            if not ref_user:
                return
            
            refs = list(ref_user["refs"] or [])
            if uid in refs:
                return
            refs.append(uid)
            
            old_stars = (len(refs) - 1) // NEEDREF * STARS_PER_REF
            new_stars = len(refs) // NEEDREF * STARS_PER_REF
            gained = new_stars - old_stars
            
            await conn.execute("UPDATE users SET refs=$2 WHERE uid=$1", rid, refs)
            if gained > 0:
                await conn.execute("UPDATE users SET stars = stars + $2 WHERE uid=$1", rid, gained)
            
            cnt = len(refs)
            need_more = NEEDREF - (cnt % NEEDREF)
            
            if gained > 0:
                await tg("sendMessage", {"chat_id": rid, "text": f"🎊 عالی! زیرمجموعه تکمیل شد!\n{LINE}\n\n👤 {fn}\n👥 مجموع: {cnt} نفر\n\n⭐ +{gained} استارز جدید!\n⭐ موجودی: {new_stars}\n\n✅ تمام مراحل انجام شد"})
            else:
                await tg("sendMessage", {"chat_id": rid, "text": f"🎊 زیرمجموعه تکمیل شد!\n{LINE}\n\n👤 {fn}\n👥 مجموع: {cnt}\n📌 با {need_more} زیرمجموعه دیگر یک استارز کسب کنید!"})
    except Exception as e:
        print(f"pending ref error: {e}")

async def log_to_channel(order):
    try:
        link = order.get("post_link", "")
        parts = link.split("/")
        if len(parts) >= 2:
            ch_part = parts[-2] or ""
            if len(ch_part) > 12:
                parts[-2] = "*" * 12 + ch_part[12:]
            else:
                parts[-2] = ch_part[:1] + "*" * 12
            masked = "/".join(parts)
        else:
            masked = link
        bn = await bot_username()
        await tg("sendMessage", {
            "chat_id": LOG_CH,
            "text": f"⭐ سفارش جدید ثبت شد\n{LINE}\n\n📋 نوع سفارش: استارز رایگان\n\n🎯 مقصد سفارش:\n<b>{esc(masked)}</b>\n\n⭐ تعداد: {order['amount']} استارز\n\n{LINE}\n\n🔥 منتظر چی هستی؟\n💫 همین الان استارز رایگانت رو بگیر!",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
            "reply_markup": J({"inline_keyboard": [[{"text": "🤖 ورود به ربات", "url": f"https://t.me/{bn}"}]]})
        })
    except Exception as e:
        print(f"log error: {e}")

# ========== PAGES ==========
async def main_menu(cid, fn, uid):
    kb = [
        [{"text": "⭐ استارز رایگان"}],
        [{"text": "👥 زیرمجموعه گیری"}, {"text": "⭐ کیف استارز"}],
        [{"text": "👤 حساب کاربری"}, {"text": "🎯 انجام ماموریت"}],
        [{"text": "🛒 ساخت پنل"}, {"text": "🚀 تبچی"}]
    ]
    if uid == ADMIN:
        kb.append([{"text": "⚙️ پنل مدیریت"}])
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"👋 سلام {fn} عزیز!\n{LINE2}\n\n🎉 به ربات ما خوش آمدید\n\n🔥 امکانات ویژه:\n\n⭐ استارز رایگان\n👥 سیستم دعوت با پاداش استارز\n⭐ کیف استارز شخصی\n🎯 ماموریت‌های پاداش‌دار\n🚀 تبچی هوشمند\n\n💫 هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز رایگان",
        "reply_markup": J({"keyboard": kb, "resize_keyboard": True})
    })

async def admin_panel(cid):
    total = await count_users()
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"⚙️ پنل مدیریت پیشرفته\n{LINE2}\n\n👑 خوش آمدید، مدیر گرامی!\n\n📊 آمار: {total} کاربر\n\n💡 برای لغو: «❌ لغو»",
        "reply_markup": J({"inline_keyboard": [
            [{"text": "📨 ارسال پیام همگانی", "callback_data": "AB"}],
            [{"text": "🔍 جستجوی کاربر", "callback_data": "SU"}],
            [{"text": "⭐ لیست سفارشات استارز", "callback_data": "STLIST"}],
            [{"text": "🎯 افزودن ماموریت", "callback_data": "MA"}],
            [{"text": "🗑 حذف ماموریت", "callback_data": "MR"}],
            [{"text": "📋 لیست ماموریت‌ها", "callback_data": "ML"}],
            [{"text": "➕ افزودن کانال جوین", "callback_data": "AA"}],
            [{"text": "➖ حذف کانال جوین", "callback_data": "AR"}],
            [{"text": "📋 لیست کانال‌ها", "callback_data": "AL"}],
            [{"text": "📊 آمار کامل", "callback_data": "AS"}],
            [{"text": "🔄 صفر کردن زیرمجموعه‌ها", "callback_data": "AX"}],
            [{"text": "⭐ صفر کردن استارز", "callback_data": "STX"}],
            [{"text": "🔙 بازگشت", "callback_data": "MN"}]
        ]})
    })

async def stars_page(cid, uid):
    stars = await get_stars(uid)
    refs = await get_refs_count(uid)
    bn = await bot_username()
    next_in = NEEDREF - (refs % NEEDREF)
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"⭐ پنل استارز رایگان\n{LINE2}\n\n💫 موجودی: {stars} استارز\n\n📊 وضعیت:\n👥 زیرمجموعه: {refs} نفر\n⭐ استارز کسب شده: {refs // NEEDREF * STARS_PER_REF}\n\n📌 با {next_in} زیرمجموعه دیگر، {STARS_PER_REF} استارز جدید!\n\n🔗 لینک دعوت:\n<code>https://t.me/{bn}?start={uid}</code>",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [
            [{"text": "💫 برداشت استارز", "callback_data": "STARS_WD"}],
            [{"text": "📤 اشتراک لینک", "switch_inline_query": f"https://t.me/{bn}?start={uid}"}],
            [{"text": "🔙 بازگشت", "callback_data": "MN"}]
        ]})
    })

async def ref_page(cid, uid):
    c = await get_refs_count(uid)
    stars = await get_stars(uid)
    bn = await bot_username()
    bar = "█" * min(c % NEEDREF, NEEDREF) + "░" * max(0, NEEDREF - (c % NEEDREF))
    next_in = NEEDREF - (c % NEEDREF)
    pct = round(((c % NEEDREF) / NEEDREF) * 100)
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"👥 پنل زیرمجموعه‌گیری\n{LINE2}\n\n🔗 لینک دعوت:\n<code>https://t.me/{bn}?start={uid}</code>\n\n📊 آمار:\n👥 زیرمجموعه: {c} نفر\n⭐ استارز: {stars}\n\n📈 پیشرفت:\n{bar} {pct}%\n📌 {next_in} زیرمجموعه تا استارز بعدی\n\n💡 هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز",
        "parse_mode": "HTML",
        "reply_markup": J({"inline_keyboard": [[{"text": "📤 اشتراک لینک", "switch_inline_query": f"https://t.me/{bn}?start={uid}"}], [{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
    })

async def acc_page(cid, uid, un):
    c = await get_refs_count(uid)
    stars = await get_stars(uid)
    user = await get_user(uid)
    t = f"👤 پروفایل کاربری\n{LINE2}\n\n🔢 شناسه: <code>{uid}</code>\n"
    t += f"🆔 @{un}\n" if un else "🆔 ثبت نشده\n"
    t += f"📅 عضویت: {fD(user['created_at'] if user else 0)}\n\n📊 وضعیت:\n👥 زیرمجموعه: {c}\n⭐ استارز: {stars}\n"
    if user and user.get("tabchi_exp", 0) > now_ms():
        t += f"\n🚀 تبچی: ✅ فعال"
    else:
        t += f"\n🚀 تبچی: ❌"
    await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})

async def wallet_page(cid, uid):
    stars = await get_stars(uid)
    c = await get_refs_count(uid)
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"⭐ کیف استارز\n{LINE2}\n\n💫 موجودی: {stars} استارز\n\n📊 عملکرد:\n👥 زیرمجموعه: {c}\n⭐ کسب شده: {c // NEEDREF * STARS_PER_REF}\n\n💡 هر {NEEDREF} نفر = {STARS_PER_REF} استارز",
        "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
    })

async def shop_page(cid, uid):
    await tg("sendMessage", {
        "chat_id": cid,
        "text": f"🛒 فروشگاه پنل\n{LINE2}\n\n⚠️ این بخش موقتاً غیرفعال است\n\n⏱ به زودی برمی‌گردد!",
        "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
    })

async def mission_page(cid, uid):
    ms = await get_missions()
    if not ms:
        await tg("sendMessage", {"chat_id": cid, "text": f"🎯 ماموریت\n{LINE2}\n\n❌ ماموریتی موجود نیست.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})
        return
    btns = []
    for m in ms:
        done = await is_mission_done(uid, m["ch"])
        if done:
            btns.append([{"text": f"✅ {m['ch']} ✓", "callback_data": "MN"}])
        else:
            btns.append([{"text": f"📢 عضویت {m['ch']}", "url": f"https://t.me/{m['ch'].replace('@', '')}"}])
            btns.append([{"text": f"✅ تایید (+{m['pay']} ⭐)", "callback_data": f"MS:{m['ch']}"}])
    btns.append([{"text": "🔙 بازگشت", "callback_data": "MN"}])
    await tg("sendMessage", {"chat_id": cid, "text": f"🎯 ماموریت\n{LINE2}\n\n⭐ پاداش استارز برای عضویت!", "reply_markup": J({"inline_keyboard": btns})})

async def tabchi_page(cid, uid):
    user = await get_user(uid)
    if not user or (user.get("tabchi_exp", 0) or 0) < now_ms():
        await tg("sendMessage", {
            "chat_id": cid,
            "text": f"🚀 تبچی هوشمند\n{LINE2}\n\n🔒 این بخش قفل است\n\n💵 قیمت: {F(TABCHI_PRICE)} تومان\n⏰ مدت: {TABCHI_DAYS} روز\n\n⚠️ فعال‌سازی توسط مدیریت",
            "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})
        })
        return
    # تبچی فعال - ادامه بعداً
    await tg("sendMessage", {"chat_id": cid, "text": f"🚀 تبچی فعال!\n⏰ تا: {fD(user['tabchi_exp'])}", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})# ========== WEBHOOK HANDLER ==========
@app.post("/")
async def webhook(request: Request):
    try:
        body = await request.json()
        if "callback_query" in body:
            asyncio.create_task(handle_callback(body["callback_query"]))
        elif "message" in body:
            asyncio.create_task(handle_message(body["message"]))
    except:
        pass
    return {"ok": True}

@app.get("/setup")
async def setup(request: Request):
    base = str(request.base_url).rstrip("/")
    r = await tg("setWebhook", {"url": f"{base}/", "drop_pending_updates": True, "max_connections": 100})
    return r

@app.get("/health")
async def health():
    total = await count_users()
    return {"status": "healthy", "version": "4.0", "users": total, "time": datetime.now().isoformat()}

# ========== MESSAGE HANDLER ==========
async def handle_message(m):
    try:
        cid = m["chat"]["id"]
        uid = m["from"]["id"]
        txt = (m.get("text") or "").strip()
        un = m["from"].get("username", "")
        fn = m["from"].get("first_name", "کاربر")
        
        await reg_user(uid, un, fn)
        
        # لغو
        if txt in ["❌ لغو", "/cancel", "/reset"]:
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ لغو شد.", "reply_markup": J({"remove_keyboard": True})})
            await main_menu(cid, fn, uid)
            return
        
        # /start
        if txt.startswith("/start"):
            await clear_state(uid)
            parts = txt.split(" ")
            if len(parts) > 1:
                try:
                    r = int(parts[1])
                    if r > 0 and r != uid:
                        user = await get_user(uid)
                        if not user or not user.get("referred_by"):
                            await set_pending(uid, r)
                            await tg("sendMessage", {"chat_id": r, "text": f"🎊 زیرمجموعه جدید کسب کردید!\n{LINE}\n\n📌 وضعیت: در انتظار تکمیل\n\n⚠️ برای واریز استارز، کاربر باید:\n\n1️⃣ در تمامی کانال‌ها عضو شود\n2️⃣ کپچا حل کند\n\n⭐ هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز"})
                except:
                    pass
            
            nj = await check_join(uid)
            if nj:
                await send_join_msg(cid, nj)
                return
            
            verified = await is_verified(uid)
            if not verified:
                await send_captcha(cid, uid)
                return
            
            await main_menu(cid, fn, uid)
            return
        
        st = await get_state(uid)
        
        # کپچا
        if st and st.startswith("CAPTCHA:"):
            correct = int(st.split(":")[1])
            try:
                user_ans = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فقط عدد وارد کنید."})
                return
            if user_ans == correct:
                await set_verified(uid)
                await clear_state(uid)
                await tg("sendMessage", {"chat_id": cid, "text": f"✅ کپچا تایید شد!\n{LINE}\n\n🎉 خوش آمدید!", "reply_markup": J({"remove_keyboard": True})})
                await process_pending_ref(uid, fn)
                await main_menu(cid, fn, uid)
            else:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ اشتباه!\n🔄 کپچای جدید:"})
                await send_captcha(cid, uid)
            return
        
        # لینک استارز
        if st == "STARS_LINK":
            if "t.me/" not in txt:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ لینک نامعتبر!\n\nنمونه:\nhttps://t.me/channel/123"})
                return
            await kv_set(f"starslink:{uid}", txt)
            await set_state(uid, "STARS_AMOUNT")
            stars = await get_stars(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ لینک ثبت شد!\n{LINE}\n\n⭐ موجودی: {stars}\n\n📝 تعداد استارز:\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        # تعداد استارز
        if st == "STARS_AMOUNT":
            try:
                amt = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد معتبر!"})
                return
            if amt <= 0:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد مثبت!"})
                return
            stars = await get_stars(uid)
            if amt > stars:
                await tg("sendMessage", {"chat_id": cid, "text": f"❌ موجودی کافی نیست!\n⭐ موجودی: {stars}\n📝 درخواست: {amt}"})
                return
            link = await kv_get(f"starslink:{uid}")
            if not link:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ لینک یافت نشد."})
                await clear_state(uid)
                return
            ok = await remove_stars(uid, amt)
            if not ok:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ خطا."})
                await clear_state(uid)
                return
            track = gen_track()
            await create_order(track, uid, un, fn, link, amt)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ سفارش ثبت شد!\n{LINE2}\n\n🔢 کد پیگیری: <code>{track}</code>\n🎯 مقصد: {link}\n⭐ تعداد: {amt}\n\n⏱ زمان پردازش: حداکثر 24 ساعت\n\n📌 وضعیت: 🟡 در حال بررسی", "parse_mode": "HTML", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": ADMIN, "text": f"⭐ سفارش استارز جدید!\n{LINE2}\n\n🔢 کد: <code>{track}</code>\n\n👤 کاربر:\n🆔 {'@'+un if un else 'ندارد'}\n🔢 شماره: <code>{uid}</code>\n📛 نام: {fn}\n\n🎯 لینک: {link}\n⭐ تعداد: {amt}\n\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M')}", "parse_mode": "HTML", "disable_web_page_preview": True, "reply_markup": J({"inline_keyboard": [[{"text": "✅ سفارش انجام شد", "callback_data": f"STDONE:{track}"}]]})})
            await log_to_channel({"post_link": link, "amount": amt})
            await main_menu(cid, fn, uid)
            return
        
        # broadcast
        if st == "BC" and uid == ADMIN:
            await do_broadcast(cid, m)
            await clear_state(uid)
            return
        
        # افزودن کانال
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
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فرمت نامعتبر!"})
                return
            await add_channel(save)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {save} اضافه شد!", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        # حذف کانال
        if st == "RC" and uid == ADMIN:
            await remove_channel(txt)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ حذف شد.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        # پاسخ ادمین
        if st and st.startswith("RP:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            if m.get("text"):
                await tg("sendMessage", {"chat_id": tid, "text": f"📬 پاسخ مدیریت\n{LINE}\n\n{m['text']}"})
            elif m.get("photo"):
                await tg("sendPhoto", {"chat_id": tid, "photo": m["photo"][-1]["file_id"], "caption": f"📬 پاسخ مدیریت\n{m.get('caption', '')}"})
            else:
                await tg("forwardMessage", {"chat_id": tid, "from_chat_id": cid, "message_id": m["message_id"]})
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ پاسخ به {tid} ارسال شد.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        # جستجوی کاربر
        if st == "SU" and uid == ADMIN:
            try:
                sid = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد وارد کنید."})
                return
            user = await get_user(sid)
            if not user:
                await clear_state(uid)
                await tg("sendMessage", {"chat_id": cid, "text": "❌ یافت نشد.", "reply_markup": J({"remove_keyboard": True})})
                await admin_panel(cid)
                return
            info = f"👤 پروفایل\n{LINE2}\n\n🔢 <code>{user['uid']}</code>\n🆔 {'@'+user['username'] if user['username'] else 'ندارد'}\n📛 {user['first_name']}\n👥 زیرمجموعه: {len(user['refs'] or [])}\n⭐ استارز: {user['stars']}"
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": info, "parse_mode": "HTML", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": cid, "text": "⚙️ عملیات:", "reply_markup": J({"inline_keyboard": [[{"text": "⭐ افزودن استارز", "callback_data": f"ADDSTAR:{sid}"}], [{"text": "🚀 فعال‌سازی تبچی", "callback_data": f"TB{sid}"}], [{"text": "🔙 پنل مدیریت", "callback_data": "AP"}]]})})
            return
        
        # افزودن استارز
        if st and st.startswith("ADDSTAR:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try:
                amt = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            await add_stars(tid, amt)
            nw = await get_stars(tid)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {amt} استارز به {tid} اضافه شد.\n⭐ موجودی: {nw}", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": f"🎁 هدیه!\n{LINE}\n\n⭐ {amt} استارز اضافه شد!\n⭐ موجودی: {nw}"})
            await admin_panel(cid)
            return
        
        # ماموریت
        if st == "MA" and uid == ADMIN:
            p = txt.split(" ")
            if len(p) < 2 or not p[0].startswith("@"):
                await tg("sendMessage", {"chat_id": cid, "text": "❌ فرمت: @channel 2"})
                return
            try:
                pay = int(p[1])
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            await add_mission(p[0], pay)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {p[0]} - {pay} ⭐", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        if st == "MR" and uid == ADMIN:
            await remove_mission(txt.strip())
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": "✅ حذف شد.", "reply_markup": J({"remove_keyboard": True})})
            await admin_panel(cid)
            return
        
        # تبچی
        if st and st.startswith("TB:") and uid == ADMIN:
            tid = int(st.split(":")[1])
            try:
                days = int(txt)
            except:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ عدد."})
                return
            exp = now_ms() + (days * 86400000)
            async with db_pool.acquire() as conn:
                await conn.execute("UPDATE users SET tabchi_exp=$2 WHERE uid=$1", tid, exp)
            await clear_state(uid)
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ تبچی فعال!\n👤 {tid}\n📅 {days} روز", "reply_markup": J({"remove_keyboard": True})})
            await tg("sendMessage", {"chat_id": tid, "text": f"🎊 تبریک!\n{LINE}\n\n🚀 تبچی فعال شد!\n📅 {days} روز"})
            await admin_panel(cid)
            return
        
        # منو
        menu_items = ["⭐ استارز رایگان", "👥 زیرمجموعه گیری", "👤 حساب کاربری", "⭐ کیف استارز", "🛒 ساخت پنل", "🎯 انجام ماموریت", "🚀 تبچی"]
        if txt in menu_items:
            nj = await check_join(uid)
            if nj:
                await send_join_msg(cid, nj)
                return
            verified = await is_verified(uid)
            if not verified:
                await send_captcha(cid, uid)
                return
        
        if txt == "⭐ استارز رایگان": await stars_page(cid, uid); return
        if txt == "👥 زیرمجموعه گیری": await ref_page(cid, uid); return
        if txt == "👤 حساب کاربری": await acc_page(cid, uid, un); return
        if txt == "⭐ کیف استارز": await wallet_page(cid, uid); return
        if txt == "🛒 ساخت پنل": await shop_page(cid, uid); return
        if txt == "🎯 انجام ماموریت": await mission_page(cid, uid); return
        if txt == "🚀 تبچی": await tabchi_page(cid, uid); return
        if txt == "⚙️ پنل مدیریت" and uid == ADMIN:
            await clear_state(uid)
            await admin_panel(cid)
            return
    
    except Exception as e:
        print(f"msg error: {e}")
        traceback.print_exc()

# ========== CALLBACK HANDLER ==========
async def handle_callback(q):
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
            await tg_delete(cid, mid)
            verified = await is_verified(uid)
            if not verified:
                await send_captcha(cid, uid)
                return
            await main_menu(cid, fn, uid)
            return
        
        if d == "MN":
            await clear_state(uid)
            await tg_delete(cid, mid)
            await main_menu(cid, fn, uid)
            return
        
        if d == "AP" and uid == ADMIN:
            await clear_state(uid)
            await tg_delete(cid, mid)
            await admin_panel(cid)
            return
        
        if d == "DONE":
            await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "✅ قبلاً انجام شده"})
            return
        
        # برداشت استارز
        if d == "STARS_WD":
            stars = await get_stars(uid)
            if stars <= 0:
                await tg("sendMessage", {"chat_id": cid, "text": f"❌ هیچ استارزی ندارید!\n\n💡 هر {NEEDREF} زیرمجموعه = {STARS_PER_REF} استارز", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 بازگشت", "callback_data": "MN"}]]})})
                return
            await set_state(uid, "STARS_LINK")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"💫 برداشت استارز\n{LINE2}\n\n⭐ موجودی: {stars}\n\n📝 لینک پست کانال را ارسال کنید:\n\nhttps://t.me/channel/123\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        # سفارش انجام شد
        if d.startswith("STDONE:") and uid == ADMIN:
            track = d[7:]
            order = await get_order(track)
            if not order:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "❌ یافت نشد!", "show_alert": True})
                return
            if order["status"] == "done":
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ قبلاً انجام شده!", "show_alert": True})
                return
            await complete_order(track)
            r = await tg("sendMessage", {"chat_id": int(order["uid"]), "text": f"🎊 تبریک!\n{LINE2}\n\n✅ سفارش استارز شما انجام شد!\n\n🔢 کد: <code>{track}</code>\n🎯 مقصد: {order['post_link']}\n⭐ تعداد: {order['amount']}\n\n💫 برای استارز بیشتر، دوستان بیشتری دعوت کنید!", "parse_mode": "HTML"})
            try:
                await tg("editMessageReplyMarkup", {"chat_id": cid, "message_id": mid, "reply_markup": J({"inline_keyboard": [[{"text": "✅ انجام شده ✓", "callback_data": "DONE"}]]})})
            except:
                pass
            if r and r.get("ok"):
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "✅ پیام ارسال شد!", "show_alert": True})
            else:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ ثبت شد ولی ارسال ناموفق", "show_alert": True})
            return
        
        # لیست سفارشات
        if d == "STLIST" and uid == ADMIN:
            orders = await get_all_orders()
            if not orders:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ سفارشی نیست.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
                return
            t = f"⭐ سفارشات\n{LINE2}\n\n📊 مجموع: {len(orders)}\n\n"
            for o in orders[:15]:
                st = "✅" if o["status"] == "done" else "🟡"
                t += f"{st} <code>{o['track_code']}</code>\n👤 {'@'+o['username'] if o['username'] else o['uid']}\n⭐ {o['amount']} | {fD(o['created_at'])}\n{LINE}\n"
            await tg("sendMessage", {"chat_id": cid, "text": t, "parse_mode": "HTML", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # ادمین callbacks
        if d == "AB" and uid == ADMIN:
            await set_state(uid, "BC")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"📨 پیام همگانی\n{LINE}\n\n✍️ پیام ارسال کنید:\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AA" and uid == ADMIN:
            await set_state(uid, "AC")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"➕ افزودن کانال\n{LINE}\n\n@channel\nhttps://t.me/channel\nhttps://t.me/+abc\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AR" and uid == ADMIN:
            chs = await get_channels()
            if not chs:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ کانالی نیست."})
                return
            await set_state(uid, "RC")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"➖ حذف کانال\n{LINE}\n\n" + "\n".join(f"{i+1}. {c}" for i, c in enumerate(chs)) + "\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "AL" and uid == ADMIN:
            chs = await get_channels()
            await tg("sendMessage", {"chat_id": cid, "text": f"📋 کانال‌ها:\n\n" + "\n".join(chs) if chs else "❌ کانالی نیست.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        if d == "AS" and uid == ADMIN:
            total = await count_users()
            ms = await get_missions()
            chs = await get_channels()
            await tg("sendMessage", {"chat_id": cid, "text": f"📊 آمار\n{LINE2}\n\n👥 کاربران: {total}\n📢 کانال‌ها: {len(chs)}\n🎯 ماموریت‌ها: {len(ms)}", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        if d == "AX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": f"⚠️ زیرمجموعه همه صفر؟\n\n❌ غیرقابل بازگشت!", "reply_markup": J({"inline_keyboard": [[{"text": "✅ بله", "callback_data": "DX"}], [{"text": "❌ انصراف", "callback_data": "AP"}]]})})
            return
        
        if d == "DX" and uid == ADMIN:
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": "⏳ در حال صفر کردن..."})
            await reset_all_refs()
            total = await count_users()
            await tg("sendMessage", {"chat_id": cid, "text": f"✅ {total} کاربر صفر شدند!", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        if d == "STX" and uid == ADMIN:
            await tg("sendMessage", {"chat_id": cid, "text": "⚠️ استارز همه صفر؟", "reply_markup": J({"inline_keyboard": [[{"text": "✅ بله", "callback_data": "DSTX"}], [{"text": "❌ انصراف", "callback_data": "AP"}]]})})
            return
        
        if d == "DSTX" and uid == ADMIN:
            await tg_delete(cid, mid)
            await reset_all_stars()
            await tg("sendMessage", {"chat_id": cid, "text": "✅ استارز همه صفر شد.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        if d == "SU" and uid == ADMIN:
            await set_state(uid, "SU")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🔍 جستجو\n{LINE}\n\nشماره کاربری:\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d.startswith("ADDSTAR:") and uid == ADMIN:
            tid = d[8:]
            await set_state(uid, f"ADDSTAR:{tid}")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"⭐ افزودن استارز\n\n👤 <code>{tid}</code>\n\nتعداد:\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d.startswith("TB") and uid == ADMIN and not d.startswith("TB:"):
            tid = d[2:]
            await set_state(uid, f"TB:{tid}")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🚀 تبچی\n\n👤 <code>{tid}</code>\n\nتعداد روز:\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "MA" and uid == ADMIN:
            await set_state(uid, "MA")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🎯 ماموریت\n{LINE}\n\n@channel 2\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "MR" and uid == ADMIN:
            ms = await get_missions()
            if not ms:
                await tg("sendMessage", {"chat_id": cid, "text": "❌ ماموریتی نیست."})
                return
            await set_state(uid, "MR")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🗑 حذف\n\n" + "\n".join(f"{m['ch']} - {m['pay']}⭐" for m in ms) + "\n\n⚠️ لغو: «❌ لغو»", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
        
        if d == "ML" and uid == ADMIN:
            ms = await get_missions()
            await tg("sendMessage", {"chat_id": cid, "text": f"📋 ماموریت‌ها:\n\n" + "\n".join(f"📢 {m['ch']} - {m['pay']}⭐" for m in ms) if ms else "❌ نیست.", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 ادمین", "callback_data": "AP"}]]})})
            return
        
        # ماموریت
        if d.startswith("MS:"):
            ch = d[3:]
            ms = await get_missions()
            mi = next((m for m in ms if m["ch"] == ch), None)
            if not mi:
                return
            r = await tg("getChatMember", {"chat_id": ch, "user_id": uid})
            if not r or not r.get("ok") or r["result"]["status"] not in ["member", "administrator", "creator"]:
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "❌ عضو شوید!", "show_alert": True})
                return
            if await is_mission_done(uid, ch):
                await tg("answerCallbackQuery", {"callback_query_id": q["id"], "text": "⚠️ قبلاً انجام شده", "show_alert": True})
                return
            await mark_mission_done(uid, ch)
            await add_stars(uid, mi["pay"])
            nw = await get_stars(uid)
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"🎉 ماموریت انجام شد!\n{LINE}\n\n📢 {ch}\n⭐ +{mi['pay']}\n💫 موجودی: {nw}", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 منو", "callback_data": "MN"}]]})})
            return
        
        # پاسخ ادمین
        if d.startswith("RP") and uid == ADMIN:
            tid = d[2:]
            await set_state(uid, f"RP:{tid}")
            await tg_delete(cid, mid)
            await tg("sendMessage", {"chat_id": cid, "text": f"📩 پاسخ به <code>{tid}</code>\n\n⚠️ لغو: «❌ لغو»", "parse_mode": "HTML", "reply_markup": J({"keyboard": [[{"text": "❌ لغو"}]], "resize_keyboard": True})})
            return
    
    except Exception as e:
        print(f"cb error: {e}")
        traceback.print_exc()

# ========== BROADCAST ==========
async def do_broadcast(cid, m):
    try:
        uids = await get_all_uids()
        if not uids:
            await tg("sendMessage", {"chat_id": cid, "text": "❌ کاربری نیست.", "reply_markup": J({"remove_keyboard": True})})
            return
        
        await tg("sendMessage", {"chat_id": cid, "text": f"📨 ارسال به {len(uids)} کاربر...\n⏳ صبر کنید...", "reply_markup": J({"remove_keyboard": True})})
        
        ok = 0
        fail = 0
        
        async with aiohttp.ClientSession() as session:
            for i in range(0, len(uids), 30):
                batch = uids[i:i+30]
                tasks = []
                for u in batch:
                    if m.get("text"):
                        tasks.append(session.post(f"{TAPI}/sendMessage", json={"chat_id": u, "text": m["text"]}, timeout=aiohttp.ClientTimeout(total=10)))
                    elif m.get("photo"):
                        tasks.append(session.post(f"{TAPI}/sendPhoto", json={"chat_id": u, "photo": m["photo"][-1]["file_id"], "caption": m.get("caption", "")}, timeout=aiohttp.ClientTimeout(total=10)))
                    elif m.get("video"):
                        tasks.append(session.post(f"{TAPI}/sendVideo", json={"chat_id": u, "video": m["video"]["file_id"], "caption": m.get("caption", "")}, timeout=aiohttp.ClientTimeout(total=10)))
                
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
                
                await asyncio.sleep(1)
        
        total = len(uids)
        pct = round((ok / total) * 100) if total > 0 else 0
        await tg("sendMessage", {"chat_id": cid, "text": f"🎊 ارسال کامل شد!\n{LINE2}\n\n✅ موفق: {ok}\n❌ ناموفق: {fail}\n📝 کل: {total}\n📈 {pct}%", "reply_markup": J({"inline_keyboard": [[{"text": "🔙 منو", "callback_data": "MN"}]]})})
    
    except Exception as e:
        await tg("sendMessage", {"chat_id": cid, "text": f"❌ خطا: {e}", "reply_markup": J({"remove_keyboard": True})})

# ========== MIGRATE FROM KV ==========
class MigrateReq(BaseModel):
    key: str
    users: list

@app.post("/migrate")
async def migrate(req: MigrateReq):
    check_auth(req.key)
    done = 0
    for u in req.users:
        try:
            await reg_user(u["id"], u.get("un", ""), u.get("fn", ""))
            if u.get("refs"):
                async with db_pool.acquire() as conn:
                    await conn.execute("UPDATE users SET refs=$2 WHERE uid=$1", u["id"], u["refs"])
            if u.get("stars"):
                async with db_pool.acquire() as conn:
                    await conn.execute("UPDATE users SET stars=$2 WHERE uid=$1", u["id"], u["stars"])
            if u.get("rb"):
                async with db_pool.acquire() as conn:
                    await conn.execute("UPDATE users SET referred_by=$2 WHERE uid=$1", u["id"], u["rb"])
            done += 1
        except Exception as e:
            print(f"migrate error {u.get('id')}: {e}")
    return {"ok": True, "done": done, "total": len(req.users)}
