import time
import json
import os
import traceback
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# ================= BOT SETTINGS =================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "-1004442551906"

SCAN_INTERVAL_SECONDS = 15
REPEAT_COOLDOWN_MINS = 15
STATE_FILE = "alert_state.json"

CHARTINK_PAGE_URL = "https://chartink.com/screener/"
CHARTINK_API_URL = "https://chartink.com/screener/process"

IST = timezone(timedelta(hours=5, minutes=30))
# ==================================================


# ================= SCANNER CONDITIONS =============
# Exact clauses as provided by you (No changes made)

SCANNERS = [
    {
        "name": "🚀 Trade terrain intra stocks (Buy)",
        "emoji": "🟢",
        "allow_repeat": False,
        "clause": "( {33489} ( [=1] 5 minute close > 1 day ago high and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    {
        "name": "🩸 Trade Terrain intra stocks (Sell)",
        "emoji": "🔴",
        "allow_repeat": False,
        "clause": "( {33489} ( [=1] 5 minute close < 1 day ago low and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    {
        "name": "🔥 Boss candle",
        "emoji": "⚡",
        "allow_repeat": False,
        "clause": "( {33489} ( [=1] 5 minute volume > [=-1] 25 minute volume * 1.7 and ( {33489} ( [=1] 5 minute close > 1 day ago high or [=1] 5 minute close < 1 day ago low ) ) ) )"
    },
]

# ==================================================


# ================= TIME & LOGGING =================

def get_ist_now():
    return datetime.now(IST)


def get_ist_time(fmt="%I:%M:%S %p"):
    return get_ist_now().strftime(fmt)


def get_today_str():
    return get_ist_now().strftime("%Y-%m-%d")


def log(message):
    """Har log ke saath exact IST timestamp."""
    print(
        f"[{get_ist_time('%Y-%m-%d %H:%M:%S IST')}] {message}",
        flush=True
    )


# ==================================================


# ================= MEMORY FUNCTIONS ===============

def load_state():
    today = get_today_str()

    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)

            if data.get("date") == today:
                log(
                    f"MEMORY LOADED | "
                    f"Previously alerted stocks: "
                    f"{len(data.get('alerted', {}))}"
                )

                return {
                    "date": today,
                    "startup_sent": data.get("startup_sent", False),
                    "alerted": data.get("alerted", {})
                }

        except Exception as e:
            log(f"STATE READ ERROR: {e}")
            traceback.print_exc()

    log("No previous alert memory found for today.")

    return {
        "date": today,
        "startup_sent": False,
        "alerted": {}
    }


def save_state(state):
    try:
        temp_file = STATE_FILE + ".tmp"

        with open(temp_file, "w") as f:
            json.dump(state, f, indent=2)

        os.replace(temp_file, STATE_FILE)

        log(
            f"MEMORY SAVED | "
            f"Total alerted stocks: {len(state['alerted'])}"
        )

        return True

    except Exception as e:
        log(f"STATE SAVE ERROR: {e}")
        traceback.print_exc()
        return False


# ==================================================


# ================= TELEGRAM STARTUP ===============

def send_startup_test(state):

    if state["startup_sent"]:
        log("Startup message already sent today. Skipping.")
        return True

    scanner_list_text = "\n".join(
        [f"{s['emoji']} {s['name']}" for s in SCANNERS]
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHANNEL_ID,
        "text": (
            "✅ *09:20 Candle Scanner Bot Ready!*\n"
            f"🕒 *Ready Time:* {get_ist_time()}\n"
            "⏳ *Scan Window:* 09:20:05 AM – 12:05 PM IST\n\n"
            f"📋 *Active Scanners ({len(SCANNERS)}):*\n"
            f"{scanner_list_text}"
        ),
        "parse_mode": "Markdown"
    }

    try:
        response = requests.post(url, data=payload, timeout=15)
        result = response.json()

        if response.status_code == 200 and result.get("ok"):
            state["startup_sent"] = True
            save_state(state)
            log("STARTUP MESSAGE SENT SUCCESSFULLY.")
            return True

        log(f"TELEGRAM STARTUP ERROR: {result}")
        return False

    except Exception as e:
        log(f"STARTUP MESSAGE FAILED: {e}")
        traceback.print_exc()
        return False


# ==================================================


# ================= TELEGRAM ALERT =================

def send_telegram_alert(scanner_name, emoji, new_stocks):

    lines = [
        f"🚨 *{scanner_name}*",
        f"🕒 *Time:* {get_ist_time()}\n"
    ]

    for stock in new_stocks:

        symbol = stock["nsecode"]
        ltp = stock["close"]
        per_chg = stock["per_chg"]
        count = stock.get("alert_count", 1)

        tv_link = (
            f"https://in.tradingview.com/chart/"
            f"?symbol=NSE:{symbol}"
        )

        repeat_tag = (
            f" 🔄 *(Alert #{count})*"
            if count > 1 else ""
        )

        lines.append(
            f"{emoji} *[{symbol}]({tv_link})* "
            f"— ₹{ltp} ({per_chg}%){repeat_tag}"
        )

    payload = {
        "chat_id": CHANNEL_ID,
        "text": "\n".join(lines),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    try:
        started = time.monotonic()
        response = requests.post(url, data=payload, timeout=15)
        elapsed = time.monotonic() - started

        try:
            result = response.json()
        except ValueError:
            result = {}

        if response.status_code == 200 and result.get("ok"):
            log(
                f"TELEGRAM SUCCESS | {scanner_name} | "
                f"Stocks: {len(new_stocks)} | "
                f"Duration: {elapsed:.2f}s"
            )
            return True

        log(
            f"TELEGRAM FAILED | {scanner_name} | "
            f"HTTP: {response.status_code} | "
            f"Response: {result}"
        )
        return False

    except Exception as e:
        log(f"TELEGRAM EXCEPTION | {scanner_name} | {e}")
        traceback.print_exc()
        return False


# ==================================================


# ================= CHARTINK SESSION ===============

def init_chartink_session():
    """Session aur CSRF token banata hai."""
    session = requests.Session()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    log("CHARTINK SESSION | Requesting new CSRF token...")
    page_response = session.get(CHARTINK_PAGE_URL, headers=headers, timeout=15)
    page_response.raise_for_status()

    soup = BeautifulSoup(page_response.text, "html.parser")
    csrf_element = soup.find("meta", {"name": "csrf-token"})

    if not csrf_element or not csrf_element.get("content"):
        raise RuntimeError("Chartink CSRF token not found.")

    headers["x-csrf-token"] = csrf_element.get("content")
    headers["X-Requested-With"] = "XMLHttpRequest"
    session.headers.update(headers)

    log("CHARTINK SESSION READY | CSRF token configured.")
    return session


# ==================================================


# ================= CHARTINK SCANNING ==============

def run_all_scanners(session, state):

    cycle_started = time.monotonic()
    already_alerted = state["alerted"]

    for scanner_number, scanner in enumerate(SCANNERS, 1):

        s_name = scanner["name"]
        s_emoji = scanner["emoji"]
        s_clause = scanner["clause"]
        allow_repeat = scanner.get("allow_repeat", False)

        scan_started = time.monotonic()

        try:
            response = session.post(
                CHARTINK_API_URL,
                data={"scan_clause": s_clause},
                timeout=15
            )

            response_elapsed = time.monotonic() - scan_started

            if response.status_code in (401, 403, 419):
                log("CSRF Token expired! Refreshing session...")
                return False

            if response.status_code != 200:
                log(f"SCANNER HTTP ERROR | {s_name} | Status: {response.status_code}")
                continue

            stocks_data = response.json().get("data", [])

            if not isinstance(stocks_data, list):
                log(f"INVALID DATA FORMAT | {s_name}")
                continue

            log(
                f"SCAN {scanner_number}/{len(SCANNERS)} | {s_name} | "
                f"Matches: {len(stocks_data)} | {response_elapsed:.2f}s"
            )

            detection_ts = get_ist_now().timestamp()
            detection_time = get_ist_time()

            new_stocks = []
            pending_records = []

            for item in stocks_data:
                symbol = item.get("nsecode")
                if not symbol:
                    continue

                unique_key = f"{s_name}|{symbol}"
                prev_record = already_alerted.get(unique_key)

                if prev_record is None:
                    item["alert_count"] = 1
                    new_stocks.append(item)
                    pending_records.append(
                        (unique_key, {"time": detection_ts, "count": 1})
                    )

                elif allow_repeat:
                    last_alert_ts = prev_record.get("time", detection_ts)
                    mins_passed = (detection_ts - last_alert_ts) / 60.0

                    if mins_passed >= REPEAT_COOLDOWN_MINS:
                        new_count = prev_record.get("count", 1) + 1
                        item["alert_count"] = new_count
                        new_stocks.append(item)
                        pending_records.append(
                            (unique_key, {"time": detection_ts, "count": new_count})
                        )

            if new_stocks:
                symbols = [item["nsecode"] for item in new_stocks]
                log(f"NEW SIGNAL SYMBOLS | {s_name} | {', '.join(symbols)}")

                telegram_success = send_telegram_alert(
                    s_name,
                    s_emoji,
                    new_stocks
                )

                if telegram_success:
                    for unique_key, record in pending_records:
                        already_alerted[unique_key] = record

                    state["alerted"] = already_alerted
                    save_state(state)

                    log(
                        f"ALERT SENT | {s_name} | "
                        f"Stocks: {len(new_stocks)} | "
                        f"Detection: {detection_time}"
                    )

        except Exception as e:
            log(f"SCANNER EXECUTION ERROR | {s_name} | {e}")
            traceback.print_exc()

        time.sleep(0.3)

    cycle_total = time.monotonic() - cycle_started
    log(f"CYCLE DONE IN {cycle_total:.2f}s")
    return True


# ==================================================


# ================= MAIN BOT =======================

def wait_until_session_prep():
    """09:19:30 AM tak wait karega taaki 09:20 candle close hone se 30s pehle session ready ho."""
    while True:
        now_ist = get_ist_now()
        prep_time = now_ist.replace(hour=9, minute=19, second=30, microsecond=0)

        if now_ist >= prep_time:
            break

        wait_seconds = (prep_time - now_ist).total_seconds()
        log(f"WAITING FOR 1ST CANDLE COMPLETION (09:20 AM) | Remaining: {int(wait_seconds)}s")
        time.sleep(min(wait_seconds, 30))


def wait_until_first_candle_close():
    """Exact 09:20:05 AM tak wait karega (jab 09:15-09:20 ki candle complete ho chuki hogi)."""
    while True:
        now_ist = get_ist_now()
        candle_close = now_ist.replace(hour=9, minute=20, second=5, microsecond=0)

        if now_ist >= candle_close:
            break

        wait_seconds = (candle_close - now_ist).total_seconds()
        time.sleep(min(wait_seconds, 0.5))


def main():
    log("=" * 55)
    log("09:15-09:20 CANDLE COMPLETION BOT INITIALIZING")
    log(f"BOT START TIME: {get_ist_time('%Y-%m-%d %H:%M:%S IST')}")
    log(f"TOTAL SCANNERS: {len(SCANNERS)}")
    log("=" * 55)

    if not BOT_TOKEN:
        log("FATAL ERROR: TELEGRAM_BOT_TOKEN secret is missing.")
        return

    now_ist = get_ist_now()
    if now_ist.hour > 12 or (now_ist.hour == 12 and now_ist.minute >= 5):
        log("12:05 PM IST already passed. Exiting.")
        return

    state = load_state()

    if not send_startup_test(state):
        log("FATAL ERROR: Telegram startup test failed. Bot stopping.")
        return

    # Step 1: 09:19:30 AM tak wait karein (Running candle me scan nahi karega)
    wait_until_session_prep()

    # Step 2: 09:19:30 par Chartink session aur CSRF token ready kar lein
    session = None
    try:
        session = init_chartink_session()
    except Exception as e:
        log(f"SESSION PREP ERROR: {e}")

    # Step 3: Exact 09:20:05 AM tak wait karein (Candle complete hone ka time)
    wait_until_first_candle_close()
    log("09:20 AM CANDLE COMPLETED! STARTING SCANS NOW.")

    while True:
        now_ist = get_ist_now()

        # Dopahar 12:05 PM IST par bot band ho jayega
        if now_ist.hour > 12 or (now_ist.hour == 12 and now_ist.minute >= 5):
            log("MORNING SESSION END | 12:05 PM IST reached. Stopping bot.")
            save_state(state)
            break

        loop_started = time.monotonic()

        try:
            if session is None:
                session = init_chartink_session()

            ok = run_all_scanners(session, state)
            if not ok:
                session = None

        except Exception as e:
            log(f"MAIN LOOP ERROR: {e}")
            traceback.print_exc()
            session = None

        loop_elapsed = time.monotonic() - loop_started
        sleep_time = max(1, SCAN_INTERVAL_SECONDS - loop_elapsed)

        time.sleep(sleep_time)

    log("BOT STOPPED SUCCESSFULLY.")


if __name__ == "__main__":
    main()
