import time
import json
import os
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

# ================= AAPKI DETAILS SET HAIN =================
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = "-1004442551906"
SCAN_INTERVAL_SECONDS = 60    # Har 1 minute me saare scanners check honge
REPEAT_COOLDOWN_MINS = 15     # Pullback scanners me same stock kitne minute baad dubara aa sake
STATE_FILE = "alert_state.json"
# ==========================================================

SCANNERS = [
    # 1. Morning PDH Heavy Volume Breakout (Buy) -> Din me 1 baar
    {
        "name": "🚀 1st 5-Min PDH Heavy Volume Breakout (Buy)",
        "emoji": "🟢",
        "allow_repeat": False,  
        "clause": "( {33489} ( [=1] 5 minute close > 1 day ago high and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    # 2. Morning PDL Heavy Volume Breakdown (Sell) -> Din me 1 baar
    {
        "name": "🩸 1st 5-Min PDL Heavy Volume Breakdown (Sell)",
        "emoji": "🔴",
        "allow_repeat": False,  
        "clause": "( {33489} ( [=1] 5 minute close < 1 day ago low and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    # 3. Falcon Long (Buy Entry) -> Naye time par dubara aayega
    {
        "name": "🦅 Falcon Long",
        "emoji": "📈",
        "allow_repeat": True,   
        "clause": "( {33489} (  [=-1] 5 minute sma (  [=1] 5 minute volume *  8 , 21 ) <  [=1] 5 minute volume and  [=1] 5 minute close >  1 day ago high and  [-2] 5 minute volume >  [-1] 5 minute volume and  [0] 5 minute close >  [-1] 5 minute high and  [0] 5 minute close >  [-2] 5 minute high and  [-2] 5 minute close >  [-2] 5 minute open and  [-1] 5 minute close <  [-1] 5 minute open and  [-2] 5 minute close >  1 day ago high and  [-1] 5 minute close >  1 day ago high and  [0] 5 minute close >  1 day ago high and  [-1] 5 minute high <=  [-2] 5 minute high and  [-1] 5 minute low >  [-2] 5 minute low ) )"
    },

    # 4. Falcon Short (Sell Entry) -> Naye time par dubara aayega
    {
        "name": "🦅 Falcon Short",
        "emoji": "📉",
        "allow_repeat": True,   
        "clause": "( {33489} (  [=-1] 5 minute sma (  [=1] 5 minute volume *  8 , 21 ) <  [=1] 5 minute volume and  [=1] 5 minute close <  1 day ago low and  [-2] 5 minute volume >  [-1] 5 minute volume and  [0] 5 minute close <  [-1] 5 minute low and  [0] 5 minute close <  [-2] 5 minute low and  [-2] 5 minute close <  [-2] 5 minute open and  [-1] 5 minute close >  [-1] 5 minute open and  [-2] 5 minute close <  1 day ago low and  [-1] 5 minute close <  1 day ago low and  [0] 5 minute close <  1 day ago low and  [-1] 5 minute low >=  [-2] 5 minute low and  [-1] 5 minute high <  [-2] 5 minute high ) )"
    }
]

CHARTINK_PAGE_URL = "https://chartink.com/screener/"
CHARTINK_API_URL = "https://chartink.com/screener/process"

IST = timezone(timedelta(hours=5, minutes=30))


def get_ist_now():
    return datetime.now(IST)


def get_ist_time(fmt="%I:%M %p"):
    return get_ist_now().strftime(fmt)


def get_today_str():
    return get_ist_now().strftime("%Y-%m-%d")


# ================= MEMORY (STATE) FUNCTIONS =================
def load_state():
    """File se aaj ke alerted stocks aur unka last alert timestamp load karta hai."""
    today = get_today_str()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                data = json.load(f)
                if data.get("date") == today:
                    return {
                        "date": today,
                        "startup_sent": data.get("startup_sent", False),
                        "alerted": data.get("alerted", {})
                    }
        except Exception as e:
            print(f"⚠️ State file read error: {e}")

    return {"date": today, "startup_sent": False, "alerted": {}}


def save_state(state):
    """Alerted stocks aur unke timestamps ko wapas file me save karta hai."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ State file save error: {e}")
# ============================================================


def send_startup_test(state):
    """Din me sirf 1 baar Startup Message bhejega"""
    if state["startup_sent"]:
        print("ℹ️ Startup message aaj pehle hi bheja ja chuka hai. Skipping...")
        return True

    scanner_list_text = "\n".join([f"{s['emoji']} {s['name']}" for s in SCANNERS])
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHANNEL_ID,
        "text": (
            f"✅ *4-Scanner Bot Connected Successfully!*\n"
            f"🕒 *Time:* {get_ist_time()}\n\n"
            f"📋 *Active Scanners ({len(SCANNERS)}):*\n{scanner_list_text}"
        ),
        "parse_mode": "Markdown"
    }
    res = requests.post(url, data=payload, timeout=10).json()
    if res.get("ok"):
        print("✅ SUCCESS: Telegram Channel par 4-Scanner Startup Message chala gaya!")
        state["startup_sent"] = True
        save_state(state)
        return True
    else:
        print("❌ TELEGRAM ERROR:", res.get("description"))
        return False


def run_all_scanners():
    state = load_state()
    already_alerted = state["alerted"]
    state_updated = False
    now_ts = get_ist_now().timestamp()

    with requests.Session() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = session.get(CHARTINK_PAGE_URL, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        csrf_token = soup.find("meta", {"name": "csrf-token"})["content"]

        headers["x-csrf-token"] = csrf_token
        headers["X-Requested-With"] = "XMLHttpRequest"

        for scanner in SCANNERS:
            s_name = scanner["name"]
            s_emoji = scanner["emoji"]
            s_clause = scanner["clause"]
            allow_repeat = scanner.get("allow_repeat", False)

            response = session.post(
                CHARTINK_API_URL,
                headers=headers,
                data={"scan_clause": s_clause},
                timeout=15
            )

            if response.status_code == 200:
                stocks_data = response.json().get("data", [])
                new_stocks = []

                for item in stocks_data:
                    symbol = item["nsecode"]
                    unique_key = f"{s_name}|{symbol}"
                    
                    # Check karein ki pehle alert aaya hai ya nahi
                    prev_record = already_alerted.get(unique_key)

                    if prev_record is None:
                        # Aaj pehli baar aaya hai -> Send Alert!
                        already_alerted[unique_key] = {"time": now_ts, "count": 1}
                        item["alert_count"] = 1
                        new_stocks.append(item)
                        state_updated = True

                    elif allow_repeat:
                        # Agar Falcon scanner hai, to check karein ki Cooldown time (15 min) poora hua ya nahi
                        last_alert_ts = prev_record["time"]
                        mins_passed = (now_ts - last_alert_ts) / 60.0

                        if mins_passed >= REPEAT_COOLDOWN_MINS:
                            new_count = prev_record.get("count", 1) + 1
                            already_alerted[unique_key] = {"time": now_ts, "count": new_count}
                            item["alert_count"] = new_count
                            new_stocks.append(item)
                            state_updated = True

                if new_stocks:
                    send_telegram_alert(s_name, s_emoji, new_stocks)
                    print(f"[{get_ist_time('%H:%M:%S')}] {s_name} -> Sent {len(new_stocks)} stock(s)!")
                else:
                    print(f"[{get_ist_time('%H:%M:%S')}] {s_name} -> No new stock.")

            time.sleep(1)

    if state_updated:
        save_state(state)


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
        tv_link = f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"
        
        # Agar stock dubara naye time par aaya hai, to uske aage (2nd Alert / Re-Entry) likh kar aayega!
        repeat_tag = f" 🔄 *(Alert #{count})*" if count > 1 else ""
        lines.append(f"{emoji} *[{symbol}]({tv_link})* — ₹{ltp} ({per_chg}%){repeat_tag}")

    payload = {
        "chat_id": CHANNEL_ID,
        "text": "\n".join(lines),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload, timeout=10)


def main():
    print("🔄 Connecting 4-Scanner Bot to Telegram...")
    state = load_state()
    if not send_startup_test(state):
        return

    print(f"🚀 Total {len(SCANNERS)} Scanners Active & Running!")
    
    while True:
        now_ist = get_ist_now()
        # Market close hone par (3:35 PM) script band ho jayegi
        if now_ist.hour > 15 or (now_ist.hour == 15 and now_ist.minute >= 35):
            print("🛑 Market Closed (3:35 PM IST). Stopping bot & saving state...")
            break

        try:
            run_all_scanners()
        except Exception as e:
            print(f"⚠️ Error: {e}")

        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
