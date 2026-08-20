"""
T10-MEHEDI - Telegram bot fleet engine.

Built on python-telegram-bot v21+ (async). Each registered bot (token + owner
Telegram user id, added from the admin panel) runs in its own background
thread with its own asyncio event loop, so multiple independent bots can run
concurrently inside a single Flask process.

Features:
- Persistent ReplyKeyboardMarkup main menu (10 buttons, 2 columns x 5 rows).
- Referral system: every successful referral pays the referrer coins; coins
  are spent to create a free hosting panel ("VPS") from inside the chat.
- Owner (the admin id configured for this bot) has unlimited balance and
  unrestricted access to every function.
- Optional "force join channel": if the admin sets a channel for a bot, every
  user must join that channel before they can use any bot feature.
- All bot-facing text is in English.
"""
import os
import shutil
import re
import sqlite3
import threading
import asyncio
import uuid
import hashlib
from html import escape as html_escape
from datetime import datetime, timedelta

from telegram import (
    Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton,
)
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters, ApplicationHandlerStop,
)
from telegram.error import TelegramError

DB_PATH = None
DATA_DIR = None

BOT_INSTANCES = {}   # bot_id -> {"thread": Thread, "stop_flag": Event, "username": str}

REFERRAL_GOAL = 3        # kept for backward compatibility / leaderboard context
REFERRAL_BONUS = 10      # coins earned per successful referral
VPS_COST = 30            # coins required to create a panel via the bot
LIFETIME_EXPIRY = "2300-01-01T00:00:00"

# ── Button layout: 2 columns x 5 rows ────────────────────────────────────────
BTN_CREATE_VPS   = "\U0001F451 Create VPS"
BTN_MY_VPS       = "\U0001F310 My VPS"
BTN_REFER        = "\U0001F517 Refer & Earn"
BTN_PROFILE      = "\U0001F464 My Profile"
BTN_LEADERBOARD  = "\U0001F3C6 Leaderboard"
BTN_SUPPORT      = "\U0001F91D Support"
BTN_STORE        = "\U0001F6D2 Store"
BTN_SYSTEM       = "\U0001F4CA System"
BTN_TRANSFER     = "\U0001F464 Transfer"
BTN_LANGUAGE     = "\U0001F30D Language"

MAIN_MENU_LAYOUT = [
    [BTN_CREATE_VPS, BTN_MY_VPS],
    [BTN_REFER, BTN_PROFILE],
    [BTN_LEADERBOARD, BTN_SUPPORT],
    [BTN_STORE, BTN_SYSTEM],
    [BTN_TRANSFER, BTN_LANGUAGE],
]
ALL_BUTTON_TEXTS = [b for row in MAIN_MENU_LAYOUT for b in row]


def init(db_path, data_dir):
    global DB_PATH, DATA_DIR
    DB_PATH = db_path
    DATA_DIR = data_dir


def _db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()


def _panel_dir(pid):
    d = os.path.join(DATA_DIR, pid)
    os.makedirs(d, exist_ok=True)
    return d


def _main_keyboard():
    return ReplyKeyboardMarkup(MAIN_MENU_LAYOUT, resize_keyboard=True, one_time_keyboard=False)


def _is_owner(user_id, owner_admin_id=None, user_username=None, owner_admin_username=None):
    """Match the configured owner by Telegram ID or username.

    The numeric ID remains supported for existing bots. Usernames are compared
    case-insensitively and work whether the configured value includes "@"
    or not.
    """
    configured_id = str(owner_admin_id or "").strip()
    if configured_id and str(user_id) == configured_id:
        return True
    configured_username = str(owner_admin_username or "").strip().lstrip("@").lower()
    actual_username = str(user_username or "").strip().lstrip("@").lower()
    return bool(configured_username and actual_username and configured_username == actual_username)


def _get_or_create_user(bot_id, tg_user, referred_by=None):
    """Returns (user_row_dict, is_new_user, referral_awarded)."""
    uid = str(tg_user.id)
    with _db() as db:
        row = db.execute(
            "SELECT * FROM tg_bot_users WHERE bot_id=? AND tg_user_id=?", (bot_id, uid)
        ).fetchone()
        if row:
            return dict(row), False, False

        rb = referred_by if (referred_by and referred_by != uid) else None
        referral_awarded = False
        if rb:
            exists = db.execute(
                "SELECT 1 FROM tg_bot_users WHERE bot_id=? AND tg_user_id=?", (bot_id, rb)
            ).fetchone()
            if not exists:
                rb = None

        db.execute(
            """INSERT INTO tg_bot_users (bot_id, tg_user_id, tg_username, referred_by,
                ref_count, panels_created, balance, lang, created_at)
               VALUES (?,?,?,?,0,0,0,'en',?)""",
            (bot_id, uid, tg_user.username or "", rb, datetime.now().isoformat()),
        )
        if rb:
            db.execute(
                """UPDATE tg_bot_users SET ref_count = ref_count + 1,
                   balance = balance + ? WHERE bot_id=? AND tg_user_id=?""",
                (REFERRAL_BONUS, bot_id, rb),
            )
            referral_awarded = True
        db.commit()
        row = db.execute(
            "SELECT * FROM tg_bot_users WHERE bot_id=? AND tg_user_id=?", (bot_id, uid)
        ).fetchone()
        return dict(row), True, referral_awarded


def _get_user(bot_id, tg_user_id):
    with _db() as db:
        row = db.execute(
            "SELECT * FROM tg_bot_users WHERE bot_id=? AND tg_user_id=?",
            (bot_id, str(tg_user_id)),
        ).fetchone()
    return dict(row) if row else None


def _channel_join_url(force_channel):
    fc = (force_channel or "").strip()
    if fc.startswith("http"):
        return fc
    if fc.startswith("@"):
        return f"https://t.me/{fc[1:]}"
    return f"https://t.me/{fc}"


async def _is_member(bot, force_channel, user_id):
    try:
        member = await bot.get_chat_member(force_channel, user_id)
        return member.status not in ("left", "kicked")
    except TelegramError:
        return False


def _get_login_url():
    """Build the public login URL from environment variables.
    
    Automatically detects Render's public hostname via RENDER_EXTERNAL_HOSTNAME.
    """
    host = (
        os.environ.get("HOST_URL", "").strip()
        or os.environ.get("PUBLIC_URL", "").strip()
        or os.environ.get("REPLIT_DEV_DOMAIN", "").strip()
        or os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()   # <-- Render auto-detection
    ).rstrip("/")
    if not host:
        return None
    if not host.startswith(("http://", "https://")):
        host = "https://" + host
    bp = os.environ.get("BASE_PATH", "").rstrip("/")
    return f"{host}{bp}/" if host else None


def build_application(bot_id, token, owner_admin_id, force_channel=None, owner_admin_username=None):
    application = ApplicationBuilder().token(token).build()
    bot_ctx = {
        "owner_admin_id":       str(owner_admin_id or "").strip(),
        "owner_admin_username": str(owner_admin_username or "").strip().lstrip("@"),
        "force_channel":        force_channel,
        "bot_id":               bot_id,
    }

    # ── Force-join gate (runs before every other handler) ───────────────────
    async def _gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
        fc = bot_ctx["force_channel"]
        user = update.effective_user
        if not fc or not user or _is_owner(
            user.id,
            bot_ctx["owner_admin_id"],
            user.username,
            bot_ctx["owner_admin_username"],
        ):
            return
        if await _is_member(context.bot, fc, user.id):
            return
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("\U0001F4E2 Join Channel", url=_channel_join_url(fc))],
            [InlineKeyboardButton("\u2705 I've Joined", callback_data="check_join")],
        ])
        target = update.effective_message or (update.callback_query.message if update.callback_query else None)
        if target:
            await target.reply_text(
                "\U0001F512 <b>You must join our channel to use this bot.</b>\n\n"
                "Please join the channel below, then tap \u201cI've Joined\u201d.",
                parse_mode="HTML", reply_markup=kb,
            )
        raise ApplicationHandlerStop

    application.add_handler(MessageHandler(filters.ALL, _gate), group=-1)
    application.add_handler(CallbackQueryHandler(_gate, pattern="^(?!check_join$).*"), group=-1)

    # ── /start ────────────────────────────────────────────────────────────
    async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        ref = context.args[0].strip() if context.args else None
        user, is_new, referral_awarded = _get_or_create_user(bot_id, update.effective_user, referred_by=ref)
        if referral_awarded and user.get("referred_by"):
            try:
                await context.bot.send_message(
                    int(user["referred_by"]),
                    f"\U0001F389 Someone joined using your referral link! You earned +{REFERRAL_BONUS} coins.",
                )
            except TelegramError:
                pass
        await update.effective_message.reply_text(
            f"\U0001F44B Welcome, <b>{update.effective_user.first_name}</b>!\n\n"
            f"Use this bot to manage your hosting panel, refer friends, and earn free VPS credits.\n"
            f"Choose an option from the menu below \U0001F447",
            parse_mode="HTML", reply_markup=_main_keyboard(),
        )

    application.add_handler(CommandHandler("start", cmd_start))

    # ── Admin-only commands ───────────────────────────────────────────────
    async def _owner_only(update: Update) -> bool:
        user = update.effective_user
        if not _is_owner(
            user.id,
            bot_ctx["owner_admin_id"],
            user.username,
            bot_ctx["owner_admin_username"],
        ):
            await update.effective_message.reply_text("⛔ This command is for the bot owner only.")
            return False
        return True

    # /setchannel @channel  — set or update force-join channel live
    async def cmd_setchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        args = context.args
        if not args:
            await update.effective_message.reply_text(
                "Usage: /setchannel @yourchannel\n"
                "Example: /setchannel @mychannelname\n\n"
                "Use /removechannel to disable."
            )
            return
        channel = args[0].strip()
        if not channel.startswith("@") and not channel.startswith("http"):
            channel = "@" + channel
        bot_ctx["force_channel"] = channel
        with _db() as db:
            db.execute("UPDATE tg_bots SET force_channel=? WHERE id=?", (channel, bot_ctx["bot_id"]))
            db.commit()
        await update.effective_message.reply_text(
            f"✅ Force-join channel set to <b>{html_escape(channel)}</b>\n\n"
            f"All users must now join that channel to use the bot.",
            parse_mode="HTML"
        )

    # /removechannel — disable force-join
    async def cmd_removechannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        bot_ctx["force_channel"] = None
        with _db() as db:
            db.execute("UPDATE tg_bots SET force_channel=NULL WHERE id=?", (bot_ctx["bot_id"],))
            db.commit()
        await update.effective_message.reply_text("✅ Force-join channel removed. Bot is now open to everyone.")

    # /addbalance <user_id> <amount>  — add coins to a user
    async def cmd_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        if len(context.args) < 2:
            await update.effective_message.reply_text("Usage: /addbalance <user_id> <amount>")
            return
        try:
            target_id = context.args[0].strip()
            amount    = int(context.args[1])
            if amount <= 0: raise ValueError
        except (ValueError, IndexError):
            await update.effective_message.reply_text("❌ Invalid. Example: /addbalance 123456789 50")
            return
        user = _get_user(bot_ctx["bot_id"], target_id)
        if not user:
            await update.effective_message.reply_text("❌ User not found. They must /start the bot first.")
            return
        with _db() as db:
            db.execute(
                "UPDATE tg_bot_users SET balance = balance + ? WHERE bot_id=? AND tg_user_id=?",
                (amount, bot_ctx["bot_id"], target_id)
            )
            db.commit()
        new_bal = (user.get("balance") or 0) + amount
        await update.effective_message.reply_text(
            f"✅ Added <b>{amount} coins</b> to user <code>{target_id}</code>.\n"
            f"New balance: <b>{new_bal} coins</b>",
            parse_mode="HTML"
        )
        try:
            await context.bot.send_message(
                int(target_id),
                f"🎁 <b>You received {amount} coins</b> from the admin!\nNew balance: <b>{new_bal} coins</b>",
                parse_mode="HTML"
            )
        except TelegramError:
            pass

    # /removebalance <user_id> <amount>
    async def cmd_removebalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        if len(context.args) < 2:
            await update.effective_message.reply_text("Usage: /removebalance <user_id> <amount>")
            return
        try:
            target_id = context.args[0].strip()
            amount    = int(context.args[1])
            if amount <= 0: raise ValueError
        except (ValueError, IndexError):
            await update.effective_message.reply_text("❌ Invalid. Example: /removebalance 123456789 20")
            return
        user = _get_user(bot_ctx["bot_id"], target_id)
        if not user:
            await update.effective_message.reply_text("❌ User not found.")
            return
        new_bal = max(0, (user.get("balance") or 0) - amount)
        with _db() as db:
            db.execute(
                "UPDATE tg_bot_users SET balance=? WHERE bot_id=? AND tg_user_id=?",
                (new_bal, bot_ctx["bot_id"], target_id)
            )
            db.commit()
        await update.effective_message.reply_text(
            f"✅ Removed coins. User <code>{target_id}</code> new balance: <b>{new_bal}</b>",
            parse_mode="HTML"
        )

    # /broadcast <message>  — send a message to all users
    async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        if not context.args:
            await update.effective_message.reply_text("Usage: /broadcast Your message here")
            return
        msg = " ".join(context.args)
        with _db() as db:
            rows = db.execute(
                "SELECT tg_user_id FROM tg_bot_users WHERE bot_id=?", (bot_ctx["bot_id"],)
            ).fetchall()
        sent = failed = 0
        for row in rows:
            try:
                await context.bot.send_message(
                    int(row["tg_user_id"]),
                    f"📢 <b>Admin Broadcast</b>\n\n{msg}",
                    parse_mode="HTML"
                )
                sent += 1
            except TelegramError:
                failed += 1
        await update.effective_message.reply_text(
            f"✅ Broadcast done.\n✔ Sent: {sent}  ✖ Failed: {failed}"
        )

    # /users  — list total user count
    async def cmd_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        with _db() as db:
            total = db.execute(
                "SELECT COUNT(*) n FROM tg_bot_users WHERE bot_id=?", (bot_ctx["bot_id"],)
            ).fetchone()["n"]
            latest = db.execute(
                "SELECT tg_user_id, tg_username, balance, ref_count, created_at "
                "FROM tg_bot_users WHERE bot_id=? ORDER BY created_at DESC LIMIT 10",
                (bot_ctx["bot_id"],)
            ).fetchall()
        lines = [f"👥 <b>Total Users: {total}</b>\n\n<b>Last 10 joined:</b>"]
        for r in latest:
            name = f"@{r['tg_username']}" if r["tg_username"] else f"ID {r['tg_user_id']}"
            lines.append(f"• {name} — 💰{r['balance']} coins, {r['ref_count']} refs | {(r['created_at'] or '')[:10]}")
        await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

    # /status  — admin overview
    async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await _owner_only(update): return
        login_url = _get_login_url()
        fc = bot_ctx.get("force_channel") or "None"
        with _db() as db:
            total_users  = db.execute("SELECT COUNT(*) n FROM tg_bot_users WHERE bot_id=?", (bot_ctx["bot_id"],)).fetchone()["n"]
            total_panels = db.execute("SELECT COALESCE(SUM(panels_created),0) n FROM tg_bot_users WHERE bot_id=?", (bot_ctx["bot_id"],)).fetchone()["n"]
        await update.effective_message.reply_text(
            f"📊 <b>Bot Status</b>\n\n"
            f"👥 Users: <b>{total_users}</b>\n"
            f"🖥 VPS Created: <b>{total_panels}</b>\n"
            f"📢 Force Channel: <b>{fc}</b>\n"
            f"🌐 Panel URL: <code>{login_url or 'Not configured'}</code>\n\n"
            f"<b>Commands:</b>\n"
            f"/setchannel @ch — set force-join\n"
            f"/removechannel — remove force-join\n"
            f"/addbalance &lt;id&gt; &lt;amt&gt; — give coins\n"
            f"/removebalance &lt;id&gt; &lt;amt&gt; — remove coins\n"
            f"/broadcast &lt;msg&gt; — message all users\n"
            f"/users — user list",
            parse_mode="HTML"
        )

    application.add_handler(CommandHandler("setchannel",    cmd_setchannel))
    application.add_handler(CommandHandler("removechannel", cmd_removechannel))
    application.add_handler(CommandHandler("addbalance",    cmd_addbalance))
    application.add_handler(CommandHandler("removebalance", cmd_removebalance))
    application.add_handler(CommandHandler("broadcast",     cmd_broadcast))
    application.add_handler(CommandHandler("users",         cmd_users))
    application.add_handler(CommandHandler("status",        cmd_status))

    # ── Check-join callback ──────────────────────────────────────────────
    async def cb_check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        fc = bot_ctx["force_channel"]
        if not fc or await _is_member(context.bot, fc, q.from_user.id):
            await q.answer("\u2705 Verified! You can now use the bot.")
            await q.message.reply_text(
                "\u2705 <b>Thanks for joining!</b> You now have full access.",
                parse_mode="HTML", reply_markup=_main_keyboard(),
            )
        else:
            await q.answer("\u274C You haven't joined the channel yet.", show_alert=True)

    application.add_handler(CallbackQueryHandler(cb_check_join, pattern="^check_join$"))

    # ── Button: My Profile ───────────────────────────────────────────────
    async def btn_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        user = _get_user(bot_id, u.id) or {}
        owner = _is_owner(
            u.id,
            bot_ctx["owner_admin_id"],
            u.username,
            bot_ctx["owner_admin_username"],
        )
        balance = "\u221E Unlimited (Admin)" if owner else f"{user.get('balance', 0)} coins"
        await update.effective_message.reply_text(
            f"\U0001F464 <b>My Profile</b>\n\n"
            f"\U0001F194 Telegram ID: <code>{u.id}</code>\n"
            f"\U0001F4B0 Balance: <b>{balance}</b>\n"
            f"\U0001F465 Total Referrals: <b>{user.get('ref_count', 0)}</b>\n"
            f"\U0001F5A5\uFE0F VPS Created: <b>{user.get('panels_created', 0)}</b>\n"
            f"\U0001F30D Language: <b>{(user.get('lang') or 'en').upper()}</b>",
            parse_mode="HTML",
        )

    # ── Button: Refer & Earn ─────────────────────────────────────────────
    async def btn_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        _get_or_create_user(bot_id, u)
        me = await context.bot.get_me()
        link = f"https://t.me/{me.username}?start={u.id}"
        await update.effective_message.reply_text(
            f"\U0001F517 <b>Refer & Earn</b>\n\n"
            f"Share your link — you earn <b>+{REFERRAL_BONUS} coins</b> for every friend who joins!\n\n"
            f"<code>{link}</code>\n\n"
            f"A free VPS costs <b>{VPS_COST} coins</b>.",
            parse_mode="HTML",
        )

    # ── Button: My VPS ────────────────────────────────────────────────────
    async def btn_my_vps(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        with _db() as db:
            rows = db.execute(
                "SELECT * FROM panels WHERE created_via_bot_id=? AND created_via_tg_id=? ORDER BY created_at DESC",
                (bot_id, str(u.id)),
            ).fetchall() if _has_bot_columns() else []
        if not rows:
            await update.effective_message.reply_text(
                "\U0001F310 <b>My VPS</b>\n\nYou don't have any VPS yet. Tap \u201cCreate VPS\u201d to get one!",
                parse_mode="HTML",
            )
            return
        lines = [f"\U0001F310 <b>My VPS ({len(rows)})</b>\n"]
        login_url = _get_login_url()
        for p in rows:
            panel_url = login_url or "Panel URL unavailable"
            lines.append(
                f"\u2022 <b>{html_escape(p['username'])}</b> | Server: <code>{html_escape(p['server_id'])}</code>\n"
                f"  Status: <b>{html_escape(p['status'])}</b> | Access: <b>24/7</b>\n"
                f"  Panel: <a href=\"{html_escape(panel_url, quote=True)}\">Open panel</a>"
            )
        await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

    # ── Button: Create VPS (starts a text conversation) ─────────────────
    async def btn_create_vps(update: Update, context: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        owner = _is_owner(
            u.id,
            bot_ctx["owner_admin_id"],
            u.username,
            bot_ctx["owner_admin_username"],
        )
        user = _get_user(bot_id, u.id) or {}
        if not owner and (user.get("balance", 0) or 0) < VPS_COST:
            need = VPS_COST - (user.get("balance", 0) or 0)
            await update.effective_message.reply_text(
                f"\U0001F512 <b>Not enough coins</b>\n\n"
                f"Creating a VPS costs <b>{VPS_COST} coins</b>. You need <b>{need}</b> more.\n"
                f"Use \u201cRefer & Earn\u201d to invite friends and earn coins.",
                parse_mode="HTML",
            )
            return
        context.user_data["pending"] = "vps_username"
        await update.effective_message.reply_text(
            "\U0001F6E0\uFE0F <b>Create VPS</b>\n\nSend the username you want for your panel:",
            parse_mode="HTML",
        )

    # ── Button: Transfer (starts a text conversation) ────────────────────
    async def btn_transfer(update: Update, context: ContextTypes.DEFAULT_TYPE):
        context.user_data["pending"] = "transfer_target"
        await update.effective_message.reply_text(
            "\U0001F464 <b>Transfer Coins</b>\n\nSend the Telegram ID of the user you want to send coins to:",
            parse_mode="HTML",
        )

    # ── Button: Leaderboard ───────────────────────────────────────────────
    async def btn_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
        with _db() as db:
            rows = db.execute(
                "SELECT tg_user_id, tg_username, ref_count FROM tg_bot_users "
                "WHERE bot_id=? ORDER BY ref_count DESC LIMIT 10",
                (bot_id,),
            ).fetchall()
        if not rows:
            await update.effective_message.reply_text("\U0001F3C6 <b>Leaderboard</b>\n\nNo data yet.", parse_mode="HTML")
            return
        medals = ["\U0001F947", "\U0001F948", "\U0001F949"]
        lines = ["\U0001F3C6 <b>Top Referrers</b>\n"]
        for i, r in enumerate(rows):
            name = f"@{r['tg_username']}" if r["tg_username"] else f"ID {r['tg_user_id']}"
            prefix = medals[i] if i < 3 else f"{i+1}."
            lines.append(f"{prefix} {name} — <b>{r['ref_count']}</b> referrals")
        await update.effective_message.reply_text("\n".join(lines), parse_mode="HTML")

    # ── Button: Support ───────────────────────────────────────────────────
    async def btn_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.effective_message.reply_text(
            "\U0001F91D <b>Support</b>\n\n"
            "Need help? Contact the bot owner directly or reply here and the admin will assist you.",
            parse_mode="HTML",
        )

    # ── Button: Store ─────────────────────────────────────────────────────
    async def btn_store(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.effective_message.reply_text(
            "\U0001F6D2 <b>Store</b>\n\n"
            f"\u2022 <b>Standard VPS</b> — {VPS_COST} coins (512MB RAM, 1GB Disk, Lifetime / 24-7)\n\n"
            "Earn coins with \u201cRefer & Earn\u201d, then tap \u201cCreate VPS\u201d to redeem.",
            parse_mode="HTML",
        )

    # ── Button: System ────────────────────────────────────────────────────
    async def btn_system(update: Update, context: ContextTypes.DEFAULT_TYPE):
        with _db() as db:
            total_users = db.execute("SELECT COUNT(*) n FROM tg_bot_users WHERE bot_id=?", (bot_id,)).fetchone()["n"]
            total_panels = db.execute("SELECT COALESCE(SUM(panels_created),0) n FROM tg_bot_users WHERE bot_id=?", (bot_id,)).fetchone()["n"]
        await update.effective_message.reply_text(
            f"\U0001F4CA <b>System Status</b>\n\n"
            f"\u2705 Bot: Online\n"
            f"\U0001F465 Total Users: <b>{total_users}</b>\n"
            f"\U0001F5A5\uFE0F Total VPS Created: <b>{total_panels}</b>",
            parse_mode="HTML",
        )

    # ── Button: Language ──────────────────────────────────────────────────
    async def btn_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("English", callback_data="lang_en"),
             InlineKeyboardButton("\u09AC\u09BE\u0982\u09B2\u09BE", callback_data="lang_bn")],
        ])
        await update.effective_message.reply_text(
            "\U0001F30D <b>Select Language</b>", parse_mode="HTML", reply_markup=kb,
        )

    async def cb_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        lang = "bn" if q.data == "lang_bn" else "en"
        with _db() as db:
            db.execute(
                "UPDATE tg_bot_users SET lang=? WHERE bot_id=? AND tg_user_id=?",
                (lang, bot_id, str(q.from_user.id)),
            )
            db.commit()
        await q.answer("Language updated!")
        await q.message.reply_text(f"\u2705 Language set to <b>{lang.upper()}</b>.", parse_mode="HTML")

    application.add_handler(CallbackQueryHandler(cb_language, pattern="^lang_"))

    BUTTON_HANDLERS = {
        BTN_PROFILE: btn_profile,
        BTN_REFER: btn_refer,
        BTN_MY_VPS: btn_my_vps,
        BTN_CREATE_VPS: btn_create_vps,
        BTN_TRANSFER: btn_transfer,
        BTN_LEADERBOARD: btn_leaderboard,
        BTN_SUPPORT: btn_support,
        BTN_STORE: btn_store,
        BTN_SYSTEM: btn_system,
        BTN_LANGUAGE: btn_language,
    }

    for text, handler in BUTTON_HANDLERS.items():
        application.add_handler(MessageHandler(filters.Regex(f"^{re.escape(text)}$"), handler))

    # ── Free-text conversation fallback (VPS creation / transfer flows) ──
    async def text_fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        pending = context.user_data.get("pending")
        text = (update.effective_message.text or "").strip()
        u = update.effective_user

        if pending == "vps_username":
            if not text:
                await update.effective_message.reply_text("\u274C Username can't be empty. Send a username:")
                return
            context.user_data["pending_username"] = text
            context.user_data["pending"] = "vps_password"
            await update.effective_message.reply_text("\U0001F511 Now send a password for this panel:")
            return

        if pending == "vps_password":
            if not text:
                await update.effective_message.reply_text("\u274C Password can't be empty. Send a password:")
                return
            username = context.user_data.pop("pending_username", None)
            context.user_data.pop("pending", None)
            owner = _is_owner(
                u.id,
                bot_ctx["owner_admin_id"],
                u.username,
                bot_ctx["owner_admin_username"],
            )
            user = _get_user(bot_id, u.id) or {}
            if not owner and (user.get("balance", 0) or 0) < VPS_COST:
                await update.effective_message.reply_text("\U0001F512 You no longer have enough coins for this VPS.")
                return
            pid = uuid.uuid4().hex
            sid = uuid.uuid4().hex[:8]
            exp = LIFETIME_EXPIRY
            try:
                os.makedirs(os.path.join(DATA_DIR, pid), exist_ok=False)
                with _db() as db:
                    _insert_panel_via_bot(db, pid, username, text, sid, exp, bot_id, u.id)
                    if not owner:
                        db.execute(
                            "UPDATE tg_bot_users SET balance = balance - ?, panels_created = panels_created + 1 "
                            "WHERE bot_id=? AND tg_user_id=?",
                            (VPS_COST, bot_id, str(u.id)),
                        )
                    else:
                        db.execute(
                            "UPDATE tg_bot_users SET panels_created = panels_created + 1 "
                            "WHERE bot_id=? AND tg_user_id=?",
                            (bot_id, str(u.id)),
                        )
                    db.commit()
                login_url = _get_login_url()
                await update.effective_message.reply_text(
                    f"\u2705 <b>VPS created successfully!</b>\n\n"
                    f"\U0001F310 Panel URL: <a href=\"{html_escape(login_url or '#', quote=True)}\">"
                    f"{html_escape(login_url or 'Unavailable')}</a>\n"
                    f"\U0001F464 Username: <code>{html_escape(username)}</code>\n"
                    f"\U0001F511 Password: <code>{html_escape(text)}</code>\n"
                    f"\U0001F4C5 Duration: <b>Lifetime / 24-7</b>\n\n"
                    f"Use the panel URL and these credentials to upload and run your bot.",
                    parse_mode="HTML",
                )
            except sqlite3.IntegrityError:
                shutil.rmtree(os.path.join(DATA_DIR, pid), ignore_errors=True)
                await update.effective_message.reply_text(
                    "\u274C This username is already taken. Tap \u201cCreate VPS\u201d again with a different username."
                )
            return

        if pending == "transfer_target":
            if not text.isdigit():
                await update.effective_message.reply_text("\u274C Send a valid numeric Telegram ID:")
                return
            target = _get_user(bot_id, text)
            if not target:
                await update.effective_message.reply_text(
                    "\u274C That user hasn't used this bot yet. Ask them to /start it first, then try again."
                )
                context.user_data.pop("pending", None)
                return
            context.user_data["transfer_target"] = text
            context.user_data["pending"] = "transfer_amount"
            await update.effective_message.reply_text("\U0001F4B0 How many coins do you want to send?")
            return

        if pending == "transfer_amount":
            if not text.isdigit() or int(text) <= 0:
                await update.effective_message.reply_text("\u274C Send a valid positive number:")
                return
            amount = int(text)
            target_id = context.user_data.pop("transfer_target", None)
            context.user_data.pop("pending", None)
            owner = _is_owner(
                u.id,
                bot_ctx["owner_admin_id"],
                u.username,
                bot_ctx["owner_admin_username"],
            )
            sender = _get_user(bot_id, u.id) or {}
            if not owner and (sender.get("balance", 0) or 0) < amount:
                await update.effective_message.reply_text("\U0001F512 You don't have enough coins for this transfer.")
                return
            with _db() as db:
                if not owner:
                    db.execute(
                        "UPDATE tg_bot_users SET balance = balance - ? WHERE bot_id=? AND tg_user_id=?",
                        (amount, bot_id, str(u.id)),
                    )
                db.execute(
                    "UPDATE tg_bot_users SET balance = balance + ? WHERE bot_id=? AND tg_user_id=?",
                    (amount, bot_id, target_id),
                )
                db.commit()
            await update.effective_message.reply_text(f"\u2705 Sent {amount} coins to user {target_id}.")
            try:
                await context.bot.send_message(int(target_id), f"\U0001F4B0 You received {amount} coins from a transfer!")
            except TelegramError:
                pass
            return

        # No pending conversation and not a known button -> show menu hint
        await update.effective_message.reply_text(
            "Please use the menu buttons below \U0001F447", reply_markup=_main_keyboard()
        )

    button_pattern = "^(" + "|".join(re.escape(t) for t in ALL_BUTTON_TEXTS) + ")$"
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & ~filters.Regex(button_pattern), text_fallback)
    )

    return application


_PANEL_BOT_COLS_CHECKED = {"ok": None}


def _has_bot_columns():
    if _PANEL_BOT_COLS_CHECKED["ok"] is None:
        with _db() as db:
            cols = {r["name"] for r in db.execute("PRAGMA table_info(panels)").fetchall()}
        _PANEL_BOT_COLS_CHECKED["ok"] = {"created_via_bot_id", "created_via_tg_id"}.issubset(cols)
    return _PANEL_BOT_COLS_CHECKED["ok"]


def _ensure_panel_bot_columns(db):
    cols = {r["name"] for r in db.execute("PRAGMA table_info(panels)").fetchall()}
    if "created_via_bot_id" not in cols:
        db.execute("ALTER TABLE panels ADD COLUMN created_via_bot_id INTEGER")
    if "created_via_tg_id" not in cols:
        db.execute("ALTER TABLE panels ADD COLUMN created_via_tg_id TEXT")
    _PANEL_BOT_COLS_CHECKED["ok"] = True


def _insert_panel_via_bot(db, pid, username, password, sid, exp, bot_id, tg_user_id):
    _ensure_panel_bot_columns(db)
    db.execute(
        """INSERT INTO panels
            (id,username,password,server_id,type,ram_limit,disk_limit,start_command,status,expires_at,created_at,
             created_via_bot_id,created_via_tg_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (pid, username, _hash_pw(password), sid, "python", 512, 1024,
         "python main.py", "stopped", exp, datetime.now().isoformat(), bot_id, str(tg_user_id)),
    )


def start_bot(bot_id, token, owner_admin_id, force_channel=None, owner_admin_username=None):
    if bot_id in BOT_INSTANCES:
        return True, "Already running"

    stop_flag = threading.Event()
    ready = threading.Event()
    result = {}

    def runner():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        application = None
        try:
            application = build_application(
                bot_id,
                token,
                owner_admin_id,
                force_channel,
                owner_admin_username,
            )
            loop.run_until_complete(application.initialize())
            me = loop.run_until_complete(application.bot.get_me())
            result["username"] = me.username
            loop.run_until_complete(application.start())
            loop.run_until_complete(application.updater.start_polling(drop_pending_updates=True))
            with _db() as db:
                db.execute(
                    "UPDATE tg_bots SET status='running', bot_username=? WHERE id=?",
                    (me.username, bot_id),
                )
                db.commit()
            ready.set()
            while not stop_flag.is_set():
                loop.run_until_complete(asyncio.sleep(1))
        except Exception as e:
            result["error"] = str(e)
            ready.set()
        finally:
            try:
                if application is not None:
                    if application.updater and application.updater.running:
                        loop.run_until_complete(application.updater.stop())
                    if application.running:
                        loop.run_until_complete(application.stop())
                    loop.run_until_complete(application.shutdown())
            except Exception:
                pass
            loop.close()

    t = threading.Thread(target=runner, daemon=True)
    t.start()
    ready.wait(timeout=20)

    if "error" in result:
        return False, result["error"]
    if "username" not in result:
        stop_flag.set()
        return False, "Timed out starting bot (check the token and network)"

    BOT_INSTANCES[bot_id] = {"thread": t, "stop_flag": stop_flag, "username": result["username"]}
    return True, result["username"]


def stop_bot(bot_id):
    inst = BOT_INSTANCES.pop(bot_id, None)
    if inst:
        inst["stop_flag"].set()
        inst["thread"].join(timeout=15)
    with _db() as db:
        db.execute("UPDATE tg_bots SET status='stopped' WHERE id=?", (bot_id,))
        db.commit()


def resume_all():
    try:
        with _db() as db:
            rows = db.execute("SELECT * FROM tg_bots WHERE status='running'").fetchall()
        for row in rows:
            start_bot(
                row["id"],
                row["token"],
                row["owner_admin_id"],
                row["force_channel"],
                owner_admin_username=row["owner_admin_username"],
            )
    except Exception as e:
        print(f"[T10-BOT] resume_all error: {e}", flush=True)