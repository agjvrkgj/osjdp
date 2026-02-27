#!/usr/bin/env python3
"""
PandaLive & SOOP(AfreecaTV) 开播提醒 Telegram Bot
支持多平台监控：
  - panda: PandaLive (包含19禁)
  - soop: SOOP / AfreecaTV

命令：
  /start                - 显示帮助
  /add <平台> <ID> [别名] - 添加主播监控
  /del <平台> <ID>       - 删除主播监控
  /list                 - 查看监控列表
  /status               - 查看服务运行状态
  /check                - 立即检查一次
"""

import json
import threading
import time
import logging
import signal
import requests
from pathlib import Path
from datetime import datetime

# ─── 日志 ───
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("stream-notify")

# ─── 路径 ───
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STREAMERS_PATH = BASE_DIR / "streamers.json"

# ─── 平台配置 ───
PLATFORMS = ["panda", "soop"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}
HEADERS_PANDA = {**HEADERS, "Referer": "https://5721004.xyz/player/"}

# ─── 全局状态 ───
live_status: dict[str, bool] = {}  # "platform:userId" -> bool
running = True
start_time = datetime.now()
check_count = 0


# ═══════════════════════════════════════
#  配置 & 数据
# ═══════════════════════════════════════

def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def load_streamers() -> dict:
    """返回格式: { "platform": { "userId": "alias" } }"""
    if not STREAMERS_PATH.exists():
        d = {"panda": {}, "soop": {}}
        save_streamers(d)
        return d
    with open(STREAMERS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        for p in PLATFORMS:
            if p not in data:
                data[p] = {}
        return data

def save_streamers(streamers: dict):
    with open(STREAMERS_PATH, "w", encoding="utf-8") as f:
        json.dump(streamers, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════
#  API 查询逻辑
# ═══════════════════════════════════════

def check_panda(user_id: str) -> dict:
    url = f"https://5721004.xyz/player/api.php?id={user_id}&t=20240701"
    try:
        resp = requests.get(url, headers=HEADERS_PANDA, timeout=10)
        data = resp.json()
        is_live = (data.get("code") == 200)
        return {
            "is_live": is_live,
            "title": "PandaLive直播中",
            "adult": data.get("status") == "isAdult",
            "room_url": f"https://www.pandalive.co.kr/live/play/{user_id}",
            "m3u8": data.get("url", ""),
            "proxy_url": f"https://5721004.xyz/player/pandalive.html?url={user_id}"
        }
    except Exception as e:
        log.error("Panda %s 查询异常: %s", user_id, e)
        return {"is_live": False}


def check_soop(user_id: str) -> dict:
    url = f"https://chapi.sooplive.co.kr/api/{user_id}/station"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        if data.get("code") == 9000:
            return {"is_live": False, "error": "NOT_FOUND"}
            
        broad = data.get("broad")
        if broad:
            return {
                "is_live": True,
                "title": broad.get("broad_title", "SOOP直播中"),
                "viewers": broad.get("current_sum_viewer", 0),
                "room_url": f"https://play.sooplive.co.kr/{user_id}",
                "adult": bool(broad.get("broad_grade") == 19)
            }
        return {"is_live": False}
    except Exception as e:
        log.error("SOOP %s 查询异常: %s", user_id, e)
        return {"is_live": False}


def check_streamer(platform: str, user_id: str) -> dict:
    if platform == "panda":
        return check_panda(user_id)
    elif platform == "soop":
        return check_soop(user_id)
    return {"is_live": False}


# ═══════════════════════════════════════
#  Telegram Bot API
# ═══════════════════════════════════════

class TelegramBot:
    def __init__(self, token: str, allowed_chat_ids: list[str]):
        self.token = token
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.allowed_chat_ids = set(str(c) for c in allowed_chat_ids)
        self.offset = 0

    def send_message(self, chat_id: str, text: str):
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }
            resp = requests.post(url, json=payload, timeout=15)
            if not resp.json().get("ok"):
                log.error("TG 发送失败: %s", resp.text)
        except Exception as e:
            log.error("TG 请求异常: %s", e)

    def broadcast(self, text: str):
        for cid in self.allowed_chat_ids:
            self.send_message(cid, text)

    def get_updates(self) -> list[dict]:
        try:
            resp = requests.get(
                f"{self.base_url}/getUpdates",
                params={"offset": self.offset, "timeout": 5},
                timeout=10,
            )
            data = resp.json()
            if not data.get("ok"): return []
            results = data.get("result", [])
            if results:
                self.offset = results[-1]["update_id"] + 1
            return results
        except Exception:
            return []

    def is_allowed(self, chat_id) -> bool:
        return str(chat_id) in self.allowed_chat_ids


# ═══════════════════════════════════════
#  命令处理
# ═══════════════════════════════════════

HELP_TEXT = """📺 <b>直播开播提醒 Bot</b>

<b>支持平台：</b>
<code>panda</code> — PandaLive
<code>soop</code> — SOOP (AfreecaTV)

<b>命令：</b>
/add &lt;平台&gt; &lt;ID&gt; [别名] — 添加监控
/del &lt;平台&gt; &lt;ID&gt; — 删除监控
/list — 监控列表
/check — 立即检查
/status — 运行状态

<b>示例：</b>
<code>/add panda siyun12476 诗允</code>
<code>/add soop lshooooo 이상호</code>
<code>/del soop lshooooo</code>"""

def handle_command(bot: TelegramBot, chat_id: str, text: str):
    parts = text.strip().split()
    cmd = parts[0].lower().split("@")[0]

    if cmd in ("/start", "/help"):
        bot.send_message(chat_id, HELP_TEXT)
    elif cmd == "/add":
        cmd_add(bot, chat_id, parts[1:])
    elif cmd == "/del":
        cmd_del(bot, chat_id, parts[1:])
    elif cmd == "/list":
        cmd_list(bot, chat_id)
    elif cmd == "/check":
        cmd_check(bot, chat_id)
    elif cmd == "/status":
        cmd_status(bot, chat_id)
    else:
        bot.send_message(chat_id, "❓ 未知命令，发送 /help")


def cmd_add(bot: TelegramBot, chat_id: str, args: list[str]):
    if len(args) < 2:
        bot.send_message(chat_id, "⚠️ <code>/add 平台 userId [别名]</code>")
        return

    plat = args[0].lower()
    if plat not in PLATFORMS:
        bot.send_message(chat_id, f"❌ 不支持平台 '{plat}'。仅支持: {', '.join(PLATFORMS)}")
        return

    user_id = args[1]
    alias = " ".join(args[2:]) if len(args) > 2 else user_id
    streamers = load_streamers()

    if user_id in streamers[plat]:
        bot.send_message(chat_id, f"⚠️ <b>{user_id}</b> 已在 {plat.upper()} 列表中。")
        return

    # 初始化并保存
    streamers[plat][user_id] = alias
    save_streamers(streamers)

    info = check_streamer(plat, user_id)
    key = f"{plat}:{user_id}"
    live_status[key] = info.get("is_live", False)
    
    state = "🟢 直播中" if live_status[key] else "⚫ 未开播"
    
    bot.send_message(
        chat_id,
        f"✅ 已添加监控 ({plat.upper()})\n\n"
        f"👤 <b>{alias}</b> (<code>{user_id}</code>)\n"
        f"📡 当前状态: {state}"
    )


def cmd_del(bot: TelegramBot, chat_id: str, args: list[str]):
    if len(args) < 2:
        bot.send_message(chat_id, "⚠️ <code>/del 平台 userId</code>")
        return

    plat = args[0].lower()
    user_id = args[1]
    streamers = load_streamers()

    if plat not in streamers or user_id not in streamers[plat]:
        bot.send_message(chat_id, f"⚠️ <b>{user_id}</b> 不在 {plat.upper()} 列表中")
        return

    alias = streamers[plat].pop(user_id)
    save_streamers(streamers)
    live_status.pop(f"{plat}:{user_id}", None)

    bot.send_message(chat_id, f"🗑 已移除 ({plat.upper()}): <b>{alias}</b>")


def cmd_list(bot: TelegramBot, chat_id: str):
    streamers = load_streamers()
    total = sum(len(streamers[p]) for p in PLATFORMS if p in streamers)
    if total == 0:
        bot.send_message(chat_id, "📋 列表为空。发送 /help 查看命令")
        return

    bot.send_message(chat_id, "🔍 正在拉取各主播状态...")
    lines = ["📋 <b>监控列表</b>\n"]
    online_count = 0

    for plat in PLATFORMS:
        if not streamers[plat]: continue
        
        plat_icon = "🐼" if plat == "panda" else "📺"
        lines.append(f"{plat_icon} <b>{plat.upper()}</b>")
        
        for uid, alias in streamers[plat].items():
            info = check_streamer(plat, uid)
            is_live = info.get("is_live", False)
            icon = "🟢" if is_live else "⚫"
            if is_live: online_count += 1
            
            # 只有开播时才显示链接
            link_text = ""
            if is_live:
                if plat == "panda":
                    room_url = f"https://www.pandalive.co.kr/live/play/{uid}"
                    proxy_url = f"https://5721004.xyz/player/pandalive.html?url={uid}"
                    link_text = f" - <a href=\"{room_url}\">官方</a> | <a href=\"{proxy_url}\">免登代理</a>"
                elif plat == "soop":
                    room_url = f"https://play.sooplive.co.kr/{uid}"
                    link_text = f" - <a href=\"{room_url}\">直播间</a>"

            lines.append(f"  {icon} <b>{alias}</b> (<code>{uid}</code>){link_text}")
        lines.append("")

    lines.append(f"共 {total} 个主播，{online_count} 个在线")
    bot.send_message(chat_id, "\n".join(lines))


def cmd_check(bot: TelegramBot, chat_id: str):
    bot.send_message(chat_id, "🔍 正在执行强制检查...")
    notifications = check_streamers_core(bot)
    bot.send_message(chat_id, f"✅ 检查完成。触发通知: {notifications} 条")


def cmd_status(bot: TelegramBot, chat_id: str):
    global check_count
    streamers = load_streamers()
    cfg = load_config()
    uptime = datetime.now() - start_time
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    total = sum(len(streamers[p]) for p in PLATFORMS if p in streamers)

    bot.send_message(
        chat_id,
        f"📊 <b>运行状态</b>\n\n"
        f"⏱ 运行时间: {hours}h {minutes}m {seconds}s\n"
        f"🔄 轮询次数: {check_count} 次\n"
        f"👥 监控数量: {total} 个主播\n"
        f"⏰ 检查间隔: {cfg.get('check_interval_seconds', 60)}s"
    )


# ═══════════════════════════════════════
#  核心检查循环
# ═══════════════════════════════════════

def check_streamers_core(bot: TelegramBot) -> int:
    global check_count
    streamers = load_streamers()
    notifications = 0

    for plat in PLATFORMS:
        for user_id, alias in streamers[plat].items():
            check_count += 1
            key = f"{plat}:{user_id}"
            was_live = live_status.get(key, False)
            
            info = check_streamer(plat, user_id)
            is_live = info.get("is_live", False)

            if is_live and not was_live:
                # 🟢 开播
                plat_emoji = "🐼" if plat=="panda" else "📺"
                adult_txt = " (🔞 19禁)" if info.get("adult") else ""
                
                msg = f"🟢 <b>{alias}</b> 开播了！{adult_txt}\n平台: {plat.upper()} {plat_emoji}\n\n"
                
                if "title" in info:
                    msg += f"📝 {info['title']}\n"
                if info.get("viewers"):
                    msg += f"👥 观众: {info['viewers']}\n"
                msg += f"\n🔗 <a href=\"{info.get('room_url','')}\">进入官方直播间</a>"

                if plat == "panda" and info.get("proxy_url"):
                    msg += f"\n🌐 <a href=\"{info['proxy_url']}\">免登录网页播放</a>"
                if plat == "panda" and info.get("m3u8"):
                    msg += f"\n\n📻 M3U8流: \n<code>{info['m3u8']}</code>"

                bot.broadcast(msg)
                notifications += 1

            elif not is_live and was_live:
                # ⚫ 下播 (静默处理，只更新状态，不发通知)
                # bot.broadcast(f"⚫ <b>{alias}</b> 已下播 ({plat.upper()})")
                pass

            live_status[key] = is_live
            time.sleep(0.5)

    return notifications


def polling_loop(bot: TelegramBot):
    while running:
        try:
            for update in bot.get_updates():
                msg = update.get("message")
                if not msg: continue
                chat_id = str(msg["chat"]["id"])
                text = msg.get("text", "")
                if not text.startswith("/"): continue
                if not bot.is_allowed(chat_id):
                    bot.send_message(chat_id, "⛔ 未授权")
                    continue
                handle_command(bot, chat_id, text)
        except Exception as e:
            log.error("TG 轮询异常: %s", e)
        time.sleep(1)


def checker_loop(bot: TelegramBot, interval: int):
    while running:
        time.sleep(interval)
        if not running: break
        try:
            check_streamers_core(bot)
        except Exception as e:
            log.error("检查异常: %s", e)


def graceful_exit(signum, frame):
    global running
    log.info("停止中...")
    running = False


def main():
    global running
    signal.signal(signal.SIGTERM, graceful_exit)
    signal.signal(signal.SIGINT, graceful_exit)

    cfg = load_config()
    token = cfg["telegram_bot_token"]
    chat_ids = cfg.get("allowed_chat_ids", [cfg["telegram_chat_id"]])
    interval = cfg.get("check_interval_seconds", 60)

    bot = TelegramBot(token, chat_ids)
    streamers = load_streamers()

    # 初始化状态
    total = 0
    for plat in PLATFORMS:
        for uid in streamers[plat]:
            info = check_streamer(plat, uid)
            live_status[f"{plat}:{uid}"] = info.get("is_live", False)
            total += 1
            time.sleep(0.5)

    bot.broadcast(f"✅ 双平台开播提醒启动\n监控: {total} 个主播\n间隔: {interval}s")

    threading.Thread(target=polling_loop, args=(bot,), daemon=True).start()
    threading.Thread(target=checker_loop, args=(bot, interval), daemon=True).start()

    try:
        while running:
            time.sleep(1)
    except KeyboardInterrupt:
        running = False


if __name__ == "__main__":
    main()
