import time
from datetime import datetime, timedelta, timezone
import requests
from bs4 import BeautifulSoup

# ================= AAPKI DETAILS SET HAIN =================
BOT_TOKEN = "9050887652:AAEBkohIKEkp69jJP9ExRnSCrradzj9iZiM"
CHANNEL_ID = "-1004442551906"
SCAN_INTERVAL_SECONDS = 60  # Har 1 minute me saare scanners check honge
# ==========================================================

SCANNERS = [
    # 1. Morning PDH Heavy Volume Breakout (Buy)
    {
        "name": "🚀 1st 5-Min PDH Heavy Volume Breakout (Buy)",
        "emoji": "🟢",
        "clause": "( {33489} ( [=1] 5 minute close > 1 day ago high and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    # 2. Morning PDL Heavy Volume Breakdown (Sell)
    {
        "name": "🩸 1st 5-Min PDL Heavy Volume Breakdown (Sell)",
        "emoji": "🔴",
        "clause": "( {33489} ( [=1] 5 minute close < 1 day ago low and [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume ) )"
    },

    # 3. PDL Pullback Breakdown (Short Entry)
    {
        "name": "🔻 5-Min PDL Pullback Breakdown (Short Entry)",
        "emoji": "📉",
        "clause": "( {33489} ( [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume and [=1] 5 minute close < 1 day ago low and [-2] 5 minute volume > [-1] 5 minute volume and [0] 5 minute close < [-1] 5 minute low and [0] 5 minute close < [-2] 5 minute low and [-2] 5 minute close < [-2] 5 minute open and [-1] 5 minute close > [-1] 5 minute open and [-2] 5 minute close < 1 day ago low and [-1] 5 minute close < 1 day ago low and [0] 5 minute close < 1 day ago low ) )"
    },

    # 4. PDH Bullish Pullback (Buy Entry) - Naya Scanner
    {
        "name": "📈 5-Min PDH Pullback Breakout (Buy Entry)",
        "emoji": "🟢",
        "clause": "( {33489} ( [=-1] 5 minute sma ( [=1] 5 minute volume * 8 , 21 ) < [=1] 5 minute volume and [=1] 5 minute close > 1 day ago high and [-2] 5 minute volume > [-1] 5 minute volume and [0] 5 minute close > [-1] 5 minute high and [0] 5 minute close > [-2] 5 minute high and [-2] 5 minute close > [-2] 5 minute open and [-1] 5 minute close < [-1] 5 minute open and [-2] 5 minute close > 1 day ago high and [-1] 5 minute close > 1 day ago high and [0] 5 minute close > 1 day ago high ) )"
    }
]

CHARTINK_PAGE_URL = "https://chartink.com/screener/"
CHARTINK_API_URL = "https://chartink.com/screener/process"

IST = timezone(timedelta(hours=5, minutes=30))
already_alerted = set()
last_reset_date = None


def get_ist_time(fmt="%I:%M %p"):
    return datetime.now(IST).strftime(fmt)


def send_startup_test():
    """Script chalu hote hi Telegram channel par charo active scanners ki list bhejta hai"""
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
        return True
    else:
        print("❌ TELEGRAM ERROR:", res.get("description"))
        return False


def run_all_scanners():
    global already_alerted, last_reset_date

    # Roz subah naye din par purane alerts ki memory reset karein
    today_date = datetime.now(IST).date()
    if last_reset_date != today_date:
        already_alerted.clear()
        last_reset_date = today_date

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
                    unique_key = (s_name, symbol)
                    if unique_key not in already_alerted:
                        already_alerted.add(unique_key)
                        new_stocks.append(item)

                if new_stocks:
                    send_telegram_alert(s_name, s_emoji, new_stocks)
                    print(f"[{get_ist_time('%H:%M:%S')}] {s_name} -> Sent {len(new_stocks)} stock(s)!")
                else:
                    print(f"[{get_ist_time('%H:%M:%S')}] {s_name} -> No new stock.")

            time.sleep(1)


def send_telegram_alert(scanner_name, emoji, new_stocks):
    lines = [
        f"🚨 *{scanner_name}*",
        f"🕒 *Time:* {get_ist_time()}\n"
    ]

    for stock in new_stocks:
        symbol = stock["nsecode"]
        ltp = stock["close"]
        per_chg = stock["per_chg"]
        tv_link = f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}"
        lines.append(f"{emoji} *[{symbol}]({tv_link})* — ₹{ltp} ({per_chg}%)")

    payload = {
        "chat_id": CHANNEL_ID,
        "text": "\n".join(lines),
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data=payload, timeout=10)


def main():
    print("🔄 Connecting 4-Scanner Bot to Telegram...")
    if not send_startup_test():
        return

    print(f"🚀 Total {len(SCANNERS)} Scanners Active & Running!")
    while True:
        try:
            run_all_scanners()
        except Exception as e:
            print(f"⚠️ Error: {e}")

        time.sleep(SCAN_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
