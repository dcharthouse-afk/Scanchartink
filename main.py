
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

SCAN_INTERVAL_SECONDS = 60
REPEAT_COOLDOWN_MINS = 15
STATE_FILE = "alert_state.json"

CHARTINK_PAGE_URL = "https://chartink.com/screener/"
CHARTINK_API_URL = "https://chartink.com/screener/process"

IST = timezone(timedelta(hours=5, minutes=30))
# ==================================================


# ================= SCANNER CONDITIONS =============

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
            "✅ *4-Scanner Bot Connected Successfully!*\n"
            f"🕒 *Time:* {get_ist_time()}\n\n"
            f"📋 *Active Scanners ({len(SCANNERS)}):*\n"
            f"{scanner_list_text}"
        ),
        "parse_mode": "Markdown"
    }

    try:
        started = time.monotonic()

        response = requests.post(
            url,
            data=payload,
            timeout=15
        )

        elapsed = time.monotonic() - started
        result = response.json()

        log(
            f"TELEGRAM STARTUP RESPONSE | "
            f"HTTP {response.status_code} | "
            f"Duration: {elapsed:.2f}s"
        )

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

        response = requests.post(
            url,
            data=payload,
            timeout=15
        )

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


# ================= CHARTINK SCANNING ==============

def run_all_scanners():

    cycle_started = time.monotonic()
    cycle_time = get_ist_time()

    log("=" * 55)
    log(f"NEW SCAN CYCLE STARTED | Cycle time: {cycle_time}")
    log("=" * 55)

    state = load_state()
    already_alerted = state["alerted"]

    # Chartink session and CSRF token
    try:

        with requests.Session() as session:

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }

            page_started = time.monotonic()

            log("CHARTINK SESSION | Requesting screener page...")

            page_response = session.get(
                CHARTINK_PAGE_URL,
                headers=headers,
                timeout=15
            )

            page_elapsed = time.monotonic() - page_started

            log(
                f"CHARTINK PAGE RESPONSE | "
                f"HTTP {page_response.status_code} | "
                f"Duration: {page_elapsed:.2f}s"
            )

            page_response.raise_for_status()

            soup = BeautifulSoup(
                page_response.text,
                "html.parser"
            )

            csrf_element = soup.find(
                "meta",
                {"name": "csrf-token"}
            )

            if not csrf_element:
                log("ERROR: Chartink CSRF token not found.")
                return

            csrf_token = csrf_element.get("content")

            if not csrf_token:
                log("ERROR: Chartink CSRF token is empty.")
                return

            headers["x-csrf-token"] = csrf_token
            headers["X-Requested-With"] = "XMLHttpRequest"

            log("CHARTINK SESSION READY | CSRF token received.")

            # Run all four scanners
            for scanner_number, scanner in enumerate(SCANNERS, 1):

                s_name = scanner["name"]
                s_emoji = scanner["emoji"]
                s_clause = scanner["clause"]
                allow_repeat = scanner.get("allow_repeat", False)

                scan_started = time.monotonic()
                scan_start_time = get_ist_time()

                log("-" * 55)
                log(
                    f"SCANNER {scanner_number}/"
                    f"{len(SCANNERS)} STARTED | {s_name}"
                )
                log(f"SCAN REQUEST TIME: {scan_start_time}")

                try:

                    response = session.post(
                        CHARTINK_API_URL,
                        headers=headers,
                        data={"scan_clause": s_clause},
                        timeout=20
                    )

                    response_elapsed = (
                        time.monotonic() - scan_started
                    )

                    response_time = get_ist_time()

                    log(
                        f"CHARTINK RESPONSE RECEIVED | "
                        f"{s_name} | "
                        f"HTTP {response.status_code} | "
                        f"Response time: {response_time} | "
                        f"Duration: {response_elapsed:.2f}s"
                    )

                    if response.status_code != 200:

                        log(
                            f"SCANNER HTTP ERROR | {s_name} | "
                            f"Status: {response.status_code} | "
                            f"Body: {response.text[:300]}"
                        )

                        time.sleep(1)
                        continue

                    try:
                        stocks_data = response.json().get("data", [])

                    except Exception as e:

                        log(
                            f"CHARTINK JSON ERROR | "
                            f"{s_name} | {e}"
                        )

                        traceback.print_exc()
                        time.sleep(1)
                        continue

                    if not isinstance(stocks_data, list):
                        log(
                            f"INVALID DATA FORMAT | {s_name}"
                        )
                        time.sleep(1)
                        continue

                    log(
                        f"CHARTINK MATCH COUNT | "
                        f"{s_name} | "
                        f"Qualified stocks: {len(stocks_data)}"
                    )

                    # Detection timestamp: response receive time
                    detection_ts = get_ist_now().timestamp()
                    detection_time = get_ist_time()

                    new_stocks = []
                    pending_records = []

                    for item in stocks_data:

                        symbol = item.get("nsecode")

                        if not symbol:
                            log(
                                f"WARNING: Stock without NSE code "
                                f"skipped in {s_name}"
                            )
                            continue

                        unique_key = f"{s_name}|{symbol}"

                        prev_record = already_alerted.get(
                            unique_key
                        )

                        if prev_record is None:

                            item["alert_count"] = 1
                            new_stocks.append(item)

                            pending_records.append(
                                (
                                    unique_key,
                                    {
                                        "time": detection_ts,
                                        "count": 1
                                    }
                                )
                            )

                        elif allow_repeat:

                            last_alert_ts = prev_record.get(
                                "time", detection_ts
                            )

                            mins_passed = (
                                detection_ts - last_alert_ts
                            ) / 60.0

                            if mins_passed >= REPEAT_COOLDOWN_MINS:

                                new_count = (
                                    prev_record.get("count", 1) + 1
                                )

                                item["alert_count"] = new_count
                                new_stocks.append(item)

                                pending_records.append(
                                    (
                                        unique_key,
                                        {
                                            "time": detection_ts,
                                            "count": new_count
                                        }
                                    )
                                )

                    log(
                        f"NEW SIGNAL COUNT | {s_name} | "
                        f"New alerts: {len(new_stocks)} | "
                        f"Detection time: {detection_time}"
                    )

                    if new_stocks:

                        symbols = [
                            item["nsecode"]
                            for item in new_stocks
                        ]

                        log(
                            f"NEW SIGNAL SYMBOLS | "
                            f"{s_name} | {', '.join(symbols)}"
                        )

                        log(
                            f"TELEGRAM SEND STARTED | "
                            f"{s_name} | "
                            f"Time: {get_ist_time()}"
                        )

                        telegram_success = send_telegram_alert(
                            s_name,
                            s_emoji,
                            new_stocks
                        )

                        if telegram_success:

                            # Save memory only after successful Telegram send
                            for unique_key, record in pending_records:
                                already_alerted[unique_key] = record

                            state["alerted"] = already_alerted

                            save_state(state)

                            log(
                                f"ALERT COMPLETED | {s_name} | "
                                f"Stocks: {len(new_stocks)} | "
                                f"Detection: {detection_time} | "
                                f"Telegram sent: {get_ist_time()}"
                            )

                        else:

                            log(
                                f"ALERT NOT CONFIRMED | {s_name} | "
                                f"Memory not updated; next scan may retry."
                            )

                    else:

                        log(
                            f"NO NEW STOCK | {s_name} | "
                            f"Qualified by Chartink: "
                            f"{len(stocks_data)}"
                        )

                    scan_total = time.monotonic() - scan_started

                    log(
                        f"SCANNER FINISHED | {s_name} | "
                        f"Total duration: {scan_total:.2f}s"
                    )

                except Exception as e:

                    log(
                        f"SCANNER EXECUTION ERROR | "
                        f"{s_name} | {e}"
                    )

                    traceback.print_exc()

                time.sleep(1)

    except Exception as e:

        log(f"CHARTINK SESSION ERROR: {e}")
        traceback.print_exc()

    cycle_total = time.monotonic() - cycle_started

    log("=" * 55)
    log(
        f"SCAN CYCLE COMPLETED | "
        f"Total duration: {cycle_total:.2f} seconds"
    )
    log("=" * 55)


# ==================================================


# ================= MAIN BOT =======================

def main():

    log("=" * 55)
    log("4-SCANNER CHARTINK BOT INITIALIZING")
    log(f"BOT START TIME: {get_ist_time('%Y-%m-%d %H:%M:%S IST')}")
    log(f"TOTAL SCANNERS: {len(SCANNERS)}")
    log(f"SCAN INTERVAL: {SCAN_INTERVAL_SECONDS} seconds")
    log(f"FALCON REPEAT COOLDOWN: {REPEAT_COOLDOWN_MINS} minutes")
    log("=" * 55)

    if not BOT_TOKEN:
        log("FATAL ERROR: TELEGRAM_BOT_TOKEN secret is missing.")
        return

    state = load_state()

    if not send_startup_test(state):
        log("FATAL ERROR: Telegram startup test failed. Bot stopping.")
        return

    log("ALL SCANNERS ACTIVE.")

    while True:

        now_ist = get_ist_now()

        if (
            now_ist.hour > 15
            or (
                now_ist.hour == 15
                and now_ist.minute >= 35
            )
        ):

            log(
                "MARKET SESSION END | "
                "03:35 PM IST reached. Stopping bot."
            )

            final_state = load_state()
            save_state(final_state)

            break

        loop_started = time.monotonic()

        log(
            f"NEXT SCAN LOOP | "
            f"Current time: {get_ist_time()}"
        )

        try:
            run_all_scanners()

        except Exception as e:

            log(f"MAIN LOOP ERROR: {e}")
            traceback.print_exc()

        loop_elapsed = time.monotonic() - loop_started

        log(
            f"LOOP PROCESSING TIME: {loop_elapsed:.2f}s"
        )

        sleep_time = max(
            0,
            SCAN_INTERVAL_SECONDS - loop_elapsed
        )

        log(
            f"NEXT CYCLE IN: {sleep_time:.2f} seconds"
        )

        time.sleep(sleep_time)

    log("BOT STOPPED SUCCESSFULLY.")


# ==================================================


if __name__ == "__main__":
    main()
