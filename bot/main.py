import asyncio
import io
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from telegram import Update, InputFile
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from .config import load_config
from . import db as dbm


# -------- Access Control --------
def user_allowed(user_id: Optional[int], allowed: set[int]) -> bool:
    return user_id is not None and user_id in allowed


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    cfg = context.application.bot_data.get("config")
    uid = update.effective_user.id if update.effective_user else None
    return bool(cfg and uid == cfg.admin_id)


async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    cfg = context.application.bot_data.get("config")
    allowed: set[int] = cfg.allowed_user_ids if cfg else set()
    uid = update.effective_user.id if update.effective_user else None
    if not user_allowed(uid, allowed):
        if update.effective_chat:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Access denied.")
        return False
    return True


async def guard_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not is_admin(update, context):
        if update.effective_chat:
            await update.effective_message.reply_text("Admin only.")
        return False
    return True


# -------- Helpers --------
def now_ts() -> int:
    return int(time.time())


def parse_remind_args(args: list[str]) -> tuple[Optional[int], str]:
    # Supported:
    #   in 10m <text>
    #   in 2h <text>
    #   in 3d <text>
    #   at 2025-09-07 10:00 <text> (local time)
    if len(args) >= 2 and args[0].lower() == "in":
        m = re.match(r"^(\d+)([smhd])$", args[1].lower())
        if m:
            n, unit = int(m.group(1)), m.group(2)
            mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
            due = now_ts() + n * mult
            text = " ".join(args[2:]).strip()
            return due, text
        return None, ""
    if len(args) >= 3 and args[0].lower() == "at":
        # at YYYY-MM-DD HH:MM <text>
        dt_str = " ".join(args[1:3])
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
            # assume local time; convert to epoch using local time
            import time as _t
            due = int(_t.mktime(dt.timetuple()))
            text = " ".join(args[3:]).strip()
            return due, text
        except ValueError:
            return None, ""
    return None, ""


def ensure_data_dir(db_path: str) -> None:
    dbm.ensure_dir(db_path)


# -------- Command Handlers --------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = context.application.bot_data["config"]
    if is_admin(update, context):
        msg = (
            "Admin panel ready.\n"
            "- Reply to forwarded messages OR use keyboard: Reply <id>.\n"
            "- Keyboard has Ban/Unban/Who/Stats and Quick Replies.\n"
            "- Commands still available: /ban <id> [reason], /unban <id>, /who <id>, /stats\n"
        )
    else:
        msg = (
            "Welcome.\n\n"
            "Send me any message — it will be delivered to the admin.\n"
            "Your identity is not shared; replies come via this bot.\n"
        )
    await update.effective_message.reply_text(msg)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def note_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    text = " ".join(context.args) or (update.effective_message.reply_to_message.text if update.effective_message.reply_to_message and update.effective_message.reply_to_message.text else "")
    text = text.strip()
    if not text:
        await update.effective_message.reply_text("Usage: /note <text> or reply to a message with /note")
        return
    with dbm.connect(cfg.db_path) as con:
        nid = dbm.insert(con, "INSERT INTO notes(user_id, text) VALUES(?, ?)", (update.effective_user.id, text))
    await update.effective_message.reply_text(f"Saved note #{nid}.")


async def notes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, text, created_at FROM notes WHERE user_id=? ORDER BY id DESC LIMIT 20", (update.effective_user.id,))
    if not rows:
        await update.effective_message.reply_text("No notes yet.")
        return
    lines = [f"#{r['id']}: {r['text']}" for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def delnote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /delnote <id>")
        return
    nid = int(context.args[0])
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        n = dbm.execute(con, "DELETE FROM notes WHERE id=? AND user_id=?", (nid, update.effective_user.id))
    await update.effective_message.reply_text("Deleted." if n else "Not found or not yours.")


async def task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text("Usage: /task <text>")
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        tid = dbm.insert(con, "INSERT INTO tasks(user_id, text) VALUES(?, ?)", (update.effective_user.id, text))
    await update.effective_message.reply_text(f"Added task #{tid}.")


async def tasks_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, text, done FROM tasks WHERE user_id=? ORDER BY done, id DESC LIMIT 50", (update.effective_user.id,))
    if not rows:
        await update.effective_message.reply_text("No tasks.")
        return
    lines = [f"#{r['id']} [{'x' if r['done'] else ' '}] {r['text']}" for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def done_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /done <id>")
        return
    tid = int(context.args[0])
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        n = dbm.execute(con, "UPDATE tasks SET done=1, done_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?", (tid, update.effective_user.id))
    await update.effective_message.reply_text("Done." if n else "Not found or not yours.")


async def deltask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /deltask <id>")
        return
    tid = int(context.args[0])
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        n = dbm.execute(con, "DELETE FROM tasks WHERE id=? AND user_id=?", (tid, update.effective_user.id))
    await update.effective_message.reply_text("Deleted." if n else "Not found or not yours.")


async def remind_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    due, text = parse_remind_args(context.args)
    if not due or not text:
        await update.effective_message.reply_text(
            "Usage: /remind in 10m <text> | /remind at YYYY-MM-DD HH:MM <text>"
        )
        return
    if due <= now_ts():
        await update.effective_message.reply_text("Time is in the past.")
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rid = dbm.insert(con, "INSERT INTO reminders(user_id, text, due_ts) VALUES(?, ?, ?)", (update.effective_user.id, text, due))

    # schedule
    delay = max(0, due - now_ts())
    context.job_queue.run_once(reminder_fire, when=delay, data={"rid": rid, "uid": update.effective_user.id}, name=f"rem-{rid}", chat_id=update.effective_chat.id)
    dt = datetime.fromtimestamp(due)
    await update.effective_message.reply_text(f"Reminder #{rid} set for {dt:%Y-%m-%d %H:%M}.")


async def reminders_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, text, due_ts, status FROM reminders WHERE user_id=? AND status='active' ORDER BY due_ts ASC", (update.effective_user.id,))
    if not rows:
        await update.effective_message.reply_text("No active reminders.")
        return
    lines = [f"#{r['id']} at {datetime.fromtimestamp(r['due_ts']):%Y-%m-%d %H:%M} — {r['text']}" for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def delrem_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /delrem <id>")
        return
    rid = int(context.args[0])
    cfg = context.application.bot_data["config"]
    # try cancel job
    for job in context.job_queue.get_jobs_by_name(f"rem-{rid}"):
        job.schedule_removal()
    with dbm.connect(cfg.db_path) as con:
        n = dbm.execute(con, "UPDATE reminders SET status='cancelled' WHERE id=? AND user_id=? AND status='active'", (rid, update.effective_user.id))
    await update.effective_message.reply_text("Cancelled." if n else "Not found/active or not yours.")


async def reminder_fire(context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.job.data or {}
    rid = data.get("rid")
    uid = data.get("uid")
    cfg = context.application.bot_data["config"]
    text = None
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT text FROM reminders WHERE id=? AND user_id=? AND status='active'", (rid, uid))
        if rows:
            text = rows[0]["text"]
            dbm.execute(con, "UPDATE reminders SET status='sent' WHERE id=?", (rid,))
    if text and context.job.chat_id:
        await context.bot.send_message(chat_id=context.job.chat_id, text=f"⏰ Reminder #{rid}: {text}")


async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    q = " ".join(context.args).strip()
    if not q:
        await update.effective_message.reply_text("Usage: /search <query>")
        return
    cfg = context.application.bot_data["config"]
    like = f"%{q}%"
    with dbm.connect(cfg.db_path) as con:
        notes = dbm.query(con, "SELECT 'note' AS src, id, text, created_at FROM notes WHERE user_id=? AND text LIKE ? ORDER BY id DESC LIMIT 10", (update.effective_user.id, like))
        tasks = dbm.query(con, "SELECT 'task' AS src, id, text, created_at FROM tasks WHERE user_id=? AND text LIKE ? ORDER BY id DESC LIMIT 10", (update.effective_user.id, like))
        msgs = dbm.query(con, "SELECT 'msg' AS src, id, text, created_at FROM messages WHERE user_id=? AND text LIKE ? ORDER BY id DESC LIMIT 10", (update.effective_user.id, like))
    rows = notes + tasks + msgs
    if not rows:
        await update.effective_message.reply_text("No matches.")
        return
    parts = [f"[{r['src']}] #{r['id']}: {r['text']}" for r in rows]
    await update.effective_message.reply_text("\n".join(parts))


async def export_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or context.args[0] not in {"notes", "tasks"}:
        await update.effective_message.reply_text("Usage: /export notes|tasks")
        return
    what = context.args[0]
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        if what == "notes":
            rows = dbm.query(con, "SELECT id, text, created_at FROM notes WHERE user_id=? ORDER BY id", (update.effective_user.id,))
        else:
            rows = dbm.query(con, "SELECT id, text, done, created_at, done_at FROM tasks WHERE user_id=? ORDER BY id", (update.effective_user.id,))
    payload = [dict(r) for r in rows]
    bio = io.BytesIO(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"))
    bio.name = f"{what}.json"
    await update.effective_message.reply_document(InputFile(bio))


async def files_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, kind, created_at, caption FROM files WHERE user_id=? ORDER BY id DESC LIMIT 20", (update.effective_user.id,))
    if not rows:
        await update.effective_message.reply_text("No files saved.")
        return
    lines = [f"#{r['id']} ({r['kind']}) — {r['caption'] or ''}" for r in rows]
    await update.effective_message.reply_text("\n".join(lines))


async def getfile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /getfile <id>")
        return
    fid = int(context.args[0])
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, file_id, kind, caption FROM files WHERE id=? AND user_id=?", (fid, update.effective_user.id))
    if not rows:
        await update.effective_message.reply_text("Not found or not yours.")
        return
    row = rows[0]
    if row["kind"] == "photo":
        await update.effective_message.reply_photo(row["file_id"], caption=row["caption"] or None)
    elif row["kind"] == "document":
        await update.effective_message.reply_document(row["file_id"], caption=row["caption"] or None)
    elif row["kind"] == "audio":
        await update.effective_message.reply_audio(row["file_id"], caption=row["caption"] or None)
    elif row["kind"] == "video":
        await update.effective_message.reply_video(row["file_id"], caption=row["caption"] or None)
    elif row["kind"] == "voice":
        await update.effective_message.reply_voice(row["file_id"], caption=row["caption"] or None)
    else:
        await update.effective_message.reply_text("Unsupported file type.")


# -------- Message handlers --------
async def text_logger(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Admin-only logger; not used for routing inbound user messages
    if not await guard_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    txt = update.effective_message.text
    if not txt:
        return
    with dbm.connect(cfg.db_path) as con:
        dbm.insert(con, "INSERT INTO messages(user_id, text) VALUES(?, ?)", (update.effective_user.id, txt))


async def file_saver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Admin-only file capture (optional)
    if not await guard_admin(update, context):
        return
    m = update.effective_message
    cfg = context.application.bot_data["config"]
    kind = None
    file_id = None
    unique_id = None
    caption = m.caption if m.caption else None

    if m.document:
        kind = "document"
        file_id = m.document.file_id
        unique_id = m.document.file_unique_id
    elif m.photo:
        kind = "photo"
        ph = m.photo[-1]
        file_id = ph.file_id
        unique_id = ph.file_unique_id
    elif m.audio:
        kind = "audio"
        file_id = m.audio.file_id
        unique_id = m.audio.file_unique_id
    elif m.video:
        kind = "video"
        file_id = m.video.file_id
        unique_id = m.video.file_unique_id
    elif m.voice:
        kind = "voice"
        file_id = m.voice.file_id
        unique_id = m.voice.file_unique_id

    if kind and file_id:
        with dbm.connect(cfg.db_path) as con:
            fid = dbm.insert(
                con,
                "INSERT INTO files(user_id, file_id, unique_id, kind, caption) VALUES(?, ?, ?, ?, ?)",
                (update.effective_user.id, file_id, unique_id, kind, caption),
            )
        await m.reply_text(f"Saved file #{fid} ({kind}). Use /getfile {fid}")


# -------- Messenger routing --------
from telegram import ReplyKeyboardMarkup, KeyboardButton


def upsert_user(con, tg_user) -> None:
    dbm.execute(
        con,
        """
        INSERT INTO users(user_id, first_name, last_name, username, language_code, is_bot, last_seen)
        VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
          first_name=excluded.first_name,
          last_name=excluded.last_name,
          username=excluded.username,
          language_code=excluded.language_code,
          is_bot=excluded.is_bot,
          last_seen=CURRENT_TIMESTAMP
        """,
        (
            tg_user.id,
            tg_user.first_name or "",
            tg_user.last_name or "",
            tg_user.username or "",
            getattr(tg_user, "language_code", None) or "",
            1 if tg_user.is_bot else 0,
        ),
    )


def is_banned(con, user_id: int) -> bool:
    rows = dbm.query(con, "SELECT active FROM bans WHERE user_id=?", (user_id,))
    return bool(rows and rows[0]["active"])  # type: ignore[index]


def admin_reply_keyboard_for(uid: int) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(f"Reply {uid}"), KeyboardButton(f"Who {uid}")],
        [KeyboardButton(f"Ban {uid}"), KeyboardButton(f"Unban {uid}")],
        [KeyboardButton("QR: دریافت شد"), KeyboardButton("QR: به‌زودی پاسخ می‌دم"), KeyboardButton("QR: لطفاً جزئیات بیشتر")],
        [KeyboardButton("Cancel")],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=False)


async def inbound_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Any message from non-admin users → deliver to admin
    if is_admin(update, context):
        return
    # rudimentary rate-limit per user (1 msg per 3s)
    u = update.effective_user
    now = now_ts()
    rl_key = f"rl:{u.id}"
    last = context.application.bot_data.get(rl_key)
    if last and (now - last) < 3:
        return
    context.application.bot_data[rl_key] = now
    cfg = context.application.bot_data["config"]
    m = update.effective_message
    with dbm.connect(cfg.db_path) as con:
        upsert_user(con, u)
        banned = is_banned(con, u.id)
        if banned:
            # silently ignore or inform? We'll ignore to avoid spam
            return
        # Save text part for search
        if m.text:
            dbm.insert(con, "INSERT INTO messages(user_id, text) VALUES(?, ?)", (u.id, m.text))
        # Save incoming file metadata (optional)
        kind = None
        file_id = None
        unique_id = None
        caption = m.caption if m.caption else None
        if m.document:
            kind = "document"; file_id = m.document.file_id; unique_id = m.document.file_unique_id
        elif m.photo:
            ph = m.photo[-1]; kind = "photo"; file_id = ph.file_id; unique_id = ph.file_unique_id
        elif m.audio:
            kind = "audio"; file_id = m.audio.file_id; unique_id = m.audio.file_unique_id
        elif m.video:
            kind = "video"; file_id = m.video.file_id; unique_id = m.video.file_unique_id
        elif m.voice:
            kind = "voice"; file_id = m.voice.file_id; unique_id = m.voice.file_unique_id
        if kind and file_id:
            dbm.insert(con, "INSERT INTO files(user_id, file_id, unique_id, kind, caption) VALUES(?, ?, ?, ?, ?)", (u.id, file_id, unique_id, kind, caption))

    # Build header
    name = (u.first_name or "") + (f" {u.last_name}" if u.last_name else "")
    uname = f"@{u.username}" if u.username else ""
    header = f"From: {name} {uname}\nID: {u.id}"

    # Send to admin
    kb = admin_reply_keyboard_for(u.id)
    sent = None
    if m.text:
        sent = await context.bot.send_message(chat_id=cfg.admin_id, text=f"{header}\n\n{m.text}", reply_markup=kb)
    elif m.photo:
        sent = await context.bot.send_photo(chat_id=cfg.admin_id, photo=m.photo[-1].file_id, caption=f"{header}\n\n{caption or ''}")
    elif m.document:
        sent = await context.bot.send_document(chat_id=cfg.admin_id, document=m.document.file_id, caption=f"{header}\n\n{caption or ''}")
    elif m.audio:
        sent = await context.bot.send_audio(chat_id=cfg.admin_id, audio=m.audio.file_id, caption=f"{header}\n\n{caption or ''}")
    elif m.video:
        sent = await context.bot.send_video(chat_id=cfg.admin_id, video=m.video.file_id, caption=f"{header}\n\n{caption or ''}")
    elif m.voice:
        sent = await context.bot.send_voice(chat_id=cfg.admin_id, voice=m.voice.file_id, caption=f"{header}\n\n{caption or ''}")
    # ensure keyboard is shown/updated for admin chat
    try:
        await context.bot.send_message(chat_id=cfg.admin_id, text="اختیارات: Reply / Ban / Unban / Who / Cancel", reply_markup=kb)
    except Exception:
        pass
    if sent:
        with dbm.connect(cfg.db_path) as con:
            dbm.insert(con, "INSERT INTO relays(user_id, direction, admin_msg_id, peer_msg_id) VALUES(?, 'to_admin', ?, ?)", (u.id, sent.message_id, m.message_id))
        try:
            await m.reply_text("پیام شما برای مدیر ارسال شد ✅")
        except Exception:
            pass


async def admin_text_buttons_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return
    text = (update.effective_message.text or "").strip()
    # Persian/English patterns
    # Reply flow
    m1 = re.match(r"^(reply|پاسخ)\s+(\d+)$", text, flags=re.IGNORECASE)
    if m1:
        uid = int(m1.group(2))
        context.user_data["reply_to_uid"] = uid
        await update.effective_message.reply_text(f"حالت پاسخ فعال شد → {uid}. پیام بعدی شما برای او ارسال می‌شود. برای لغو: Cancel")
        return

    # Ban
    m2 = re.match(r"^(ban|بن)\s+(\d+)(?:\s+(.+))?$", text, flags=re.IGNORECASE)
    if m2:
        uid = int(m2.group(2))
        reason = (m2.group(3) or "").strip()
        with dbm.connect(context.application.bot_data["config"].db_path) as con:
            dbm.execute(con, "INSERT INTO bans(user_id, reason, active, updated_at) VALUES(?, ?, 1, CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason, active=1, updated_at=CURRENT_TIMESTAMP", (uid, reason))
        await update.effective_message.reply_text(f"کاربر {uid} بن شد.")
        return

    # Unban
    m3 = re.match(r"^(unban|رفع\s*بن|آنبن)\s+(\d+)$", text, flags=re.IGNORECASE)
    if m3:
        uid = int(m3.group(2))
        with dbm.connect(context.application.bot_data["config"].db_path) as con:
            dbm.execute(con, "UPDATE bans SET active=0, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (uid,))
        await update.effective_message.reply_text(f"کاربر {uid} آزاد شد.")
        return

    # Who
    m4 = re.match(r"^(who|کی|اطلاعات)\s+(\d+)$", text, flags=re.IGNORECASE)
    if m4:
        uid = int(m4.group(2))
        with dbm.connect(context.application.bot_data["config"].db_path) as con:
            rows = dbm.query(con, "SELECT * FROM users WHERE user_id=?", (uid,))
            banned = is_banned(con, uid)
        if not rows:
            await update.effective_message.reply_text("Unknown user.")
        else:
            r = rows[0]
            info = f"ID: {r['user_id']}\nName: {r['first_name']} {r['last_name']}\nUsername: @{r['username']}\nLang: {r['language_code']}\nBanned: {banned}"
            await update.effective_message.reply_text(info)
        return

    # Stats
    if re.match(r"^(stats|آمار)$", text, flags=re.IGNORECASE):
        await stats_cmd(update, context)
        return

    # Cancel
    if re.match(r"^(cancel|لغو)$", text, flags=re.IGNORECASE):
        context.user_data.pop("reply_to_uid", None)
        await update.effective_message.reply_text("حالت پاسخ غیرفعال شد.")
        return

    # Quick reply buttons
    mqr = re.match(r"^(qr:|پاسخ\s*سریع:)\s*(.+)$", text, flags=re.IGNORECASE)
    if mqr:
        target = context.user_data.get("reply_to_uid")
        if not target:
            await update.effective_message.reply_text("ابتدا با دکمه Reply <id> هدف را انتخاب کنید.")
            return
        payload = mqr.group(2).strip()
        sent = await context.bot.send_message(chat_id=target, text=payload)
        with dbm.connect(context.application.bot_data["config"].db_path) as con:
            dbm.insert(con, "INSERT INTO relays(user_id, direction, admin_msg_id, peer_msg_id) VALUES(?, 'to_user', ?, ?)", (target, update.effective_message.message_id, sent.message_id))
        await update.effective_message.reply_text("ارسال شد ✅")
        return

    # If in reply mode, route this message to target user
    target = context.user_data.get("reply_to_uid")
    if target:
        # send to target
        m = update.effective_message
        sent = await context.bot.send_message(chat_id=target, text=m.text)
        # log relay
        with dbm.connect(context.application.bot_data["config"].db_path) as con:
            dbm.insert(con, "INSERT INTO relays(user_id, direction, admin_msg_id, peer_msg_id) VALUES(?, 'to_user', ?, ?)", (target, m.message_id, sent.message_id))
        await update.effective_message.reply_text("ارسال شد ✅")
        context.user_data.pop("reply_to_uid", None)
        return


async def admin_reply_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Admin replies to a relay → send to that user
    if not is_admin(update, context):
        return
    cfg = context.application.bot_data["config"]
    m = update.effective_message
    if not m.reply_to_message:
        return
    parent_id = m.reply_to_message.message_id
    # lookup mapping
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT user_id FROM relays WHERE direction='to_admin' AND admin_msg_id=? ORDER BY id DESC LIMIT 1", (parent_id,))
    if not rows:
        return
    uid = rows[0]["user_id"]
    sent = None
    if m.text:
        sent = await context.bot.send_message(chat_id=uid, text=m.text)
    elif m.photo:
        sent = await context.bot.send_photo(chat_id=uid, photo=m.photo[-1].file_id, caption=m.caption or None)
    elif m.document:
        sent = await context.bot.send_document(chat_id=uid, document=m.document.file_id, caption=m.caption or None)
    elif m.audio:
        sent = await context.bot.send_audio(chat_id=uid, audio=m.audio.file_id, caption=m.caption or None)
    elif m.video:
        sent = await context.bot.send_video(chat_id=uid, video=m.video.file_id, caption=m.caption or None)
    elif m.voice:
        sent = await context.bot.send_voice(chat_id=uid, voice=m.voice.file_id, caption=m.caption or None)
    if sent:
        with dbm.connect(cfg.db_path) as con:
            dbm.insert(con, "INSERT INTO relays(user_id, direction, admin_msg_id, peer_msg_id) VALUES(?, 'to_user', ?, ?)", (uid, parent_id, sent.message_id))


async def ban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /ban <user_id> [reason]")
        return
    uid = int(context.args[0])
    reason = " ".join(context.args[1:]).strip()
    cfg = context.application.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        dbm.execute(con, "INSERT INTO bans(user_id, reason, active, updated_at) VALUES(?, ?, 1, CURRENT_TIMESTAMP) ON CONFLICT(user_id) DO UPDATE SET reason=excluded.reason, active=1, updated_at=CURRENT_TIMESTAMP", (uid, reason))
    await update.effective_message.reply_text(f"User {uid} banned.")


async def unban_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /unban <user_id>")
        return
    uid = int(context.args[0])
    with dbm.connect(context.application.bot_data["config"].db_path) as con:
        dbm.execute(con, "UPDATE bans SET active=0, updated_at=CURRENT_TIMESTAMP WHERE user_id=?", (uid,))
    await update.effective_message.reply_text(f"User {uid} unbanned.")


async def who_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    if not context.args or not context.args[0].isdigit():
        await update.effective_message.reply_text("Usage: /who <user_id>")
        return
    uid = int(context.args[0])
    with dbm.connect(context.application.bot_data["config"].db_path) as con:
        rows = dbm.query(con, "SELECT * FROM users WHERE user_id=?", (uid,))
        banned = is_banned(con, uid)
    if not rows:
        await update.effective_message.reply_text("Unknown user.")
        return
    r = rows[0]
    info = f"ID: {r['user_id']}\nName: {r['first_name']} {r['last_name']}\nUsername: @{r['username']}\nLang: {r['language_code']}\nBanned: {banned}"
    await update.effective_message.reply_text(info)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await guard_admin(update, context):
        return
    with dbm.connect(context.application.bot_data["config"].db_path) as con:
        users = dbm.query(con, "SELECT COUNT(*) AS c FROM users")[0]["c"]
        banned = dbm.query(con, "SELECT COUNT(*) AS c FROM bans WHERE active=1")[0]["c"]
        msgs = dbm.query(con, "SELECT COUNT(*) AS c FROM messages")[0]["c"]
    await update.effective_message.reply_text(f"Users: {users}\nBanned: {banned}\nMessages: {msgs}")


# -------- App setup --------
async def load_pending_reminders(app):
    cfg = app.bot_data["config"]
    with dbm.connect(cfg.db_path) as con:
        rows = dbm.query(con, "SELECT id, user_id, text, due_ts FROM reminders WHERE status='active' AND due_ts > ?", (now_ts(),))
    for r in rows:
        delay = max(0, r["due_ts"] - now_ts())
        app.job_queue.run_once(reminder_fire, when=delay, data={"rid": r["id"], "uid": r["user_id"]}, name=f"rem-{r['id']}")


def main() -> None:
    cfg = load_config()
    ensure_data_dir(cfg.db_path)
    dbm.init_db(cfg.db_path)

    app = ApplicationBuilder().token(cfg.bot_token).build()
    app.bot_data["config"] = cfg

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("note", note_cmd))
    app.add_handler(CommandHandler("notes", notes_cmd))
    app.add_handler(CommandHandler("delnote", delnote_cmd))
    app.add_handler(CommandHandler("task", task_cmd))
    app.add_handler(CommandHandler("tasks", tasks_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("deltask", deltask_cmd))
    app.add_handler(CommandHandler("remind", remind_cmd))
    app.add_handler(CommandHandler("reminders", reminders_cmd))
    app.add_handler(CommandHandler("delrem", delrem_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("export", export_cmd))
    app.add_handler(CommandHandler("files", files_cmd))
    app.add_handler(CommandHandler("getfile", getfile_cmd))

    # Admin-only capture (optional)
    app.add_handler(MessageHandler((filters.Chat(cfg.admin_id)) & (filters.Document.ALL | filters.PHOTO | filters.AUDIO | filters.VIDEO | filters.VOICE), file_saver))

    # Admin text buttons + reply-mode router
    app.add_handler(MessageHandler((filters.Chat(cfg.admin_id)) & filters.TEXT & (~filters.COMMAND), admin_text_buttons_handler))
    app.add_handler(MessageHandler((filters.Chat(cfg.admin_id)) & (~filters.COMMAND), admin_reply_router))

    # Non-admin inbound routing
    app.add_handler(MessageHandler(~filters.Chat(cfg.admin_id) & (~filters.COMMAND), inbound_user_message))

    # Admin management commands
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("who", who_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))

    # Load pending reminders
    async def _post_startup(_: ApplicationBuilder):
        await load_pending_reminders(app)

    app.post_init = _post_startup  # type: ignore

    print("Bot starting... press Ctrl+C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
