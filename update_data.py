import json
import re
import subprocess
import sys
from datetime import datetime, date

# Install/update NseKit
subprocess.check_call([
    sys.executable, "-m", "pip", "install", "-U", "NseKit"
])

from NseKit import NseKit

print("Starting NSE corporate-action scan...")

# Create NSE client
nse = NseKit.Nse(
    max_rps=1.0,
    retries=3,
    retry_delay=3.0,
    cookie_cache=True
)

# Get upcoming corporate actions.
# NseKit's default corporate-action call is designed
# to return upcoming actions (default: next 90 days).
df = nse.cm_live_hist_corporate_action()

print("Corporate actions received:", len(df))

events = []

# Convert dataframe rows into dictionaries
records = df.to_dict("records")

for row in records:

    # Convert keys to lowercase for easier matching
    data = {
        str(k).lower().replace(" ", "_"): v
        for k, v in row.items()
    }

    # Get purpose/action description
    purpose = str(
        data.get("purpose")
        or data.get("purpose_description")
        or data.get("action")
        or ""
    )

    # We only want dividends
    if "dividend" not in purpose.lower():
        continue

    symbol = (
        data.get("symbol")
        or data.get("security_symbol")
        or data.get("security")
        or ""
    )

    company = (
        data.get("company_name")
        or data.get("companyname")
        or data.get("company")
        or ""
    )

    ex_date = (
        data.get("ex_date")
        or data.get("exdate")
        or data.get("ex-date")
    )

    record_date = (
        data.get("record_date")
        or data.get("recorddate")
        or data.get("record-date")
    )

    # Convert dates to YYYY-MM-DD
    def convert_date(value):
        if value is None:
            return None

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d")

        text = str(value).strip()

        formats = [
            "%d-%b-%Y",
            "%d-%B-%Y",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
            except ValueError:
                pass

        return None

    ex_date = convert_date(ex_date)
    record_date = convert_date(record_date)

    if not symbol or not ex_date:
        continue

    # Extract dividend amount from purpose
    amount = None

    text = purpose.replace(",", "")

    patterns = [
        r"(?:Rs\.?|₹|INR)\s*(\d+(?:\.\d+)?)",
        r"dividend[^\d]*(\d+(?:\.\d+)?)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                amount = float(match.group(1))
                break
            except:
                pass

    if amount is None:
        continue

    events.append({
        "symbol": str(symbol),
        "company": str(company),
        "dividend": amount,
        "exDate": ex_date,
        "recordDate": record_date,
        "purpose": purpose
    })


# Remove duplicate events
unique = {}

for event in events:
    key = (
        event["symbol"],
        event["exDate"]
    )

    unique[key] = event

events = list(unique.values())

events.sort(
    key=lambda x: (
        x["exDate"],
        x["symbol"]
    )
)

print("Dividend events found:", len(events))


# -------------------------------------------------------
# Yahoo Finance price + RSI
# -------------------------------------------------------

import requests
import time

session = requests.Session()

session.headers.update({
    "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/126 Safari/537.36"
})


def calculate_rsi(closes, period=14):

    if len(closes) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(closes)):

        change = closes[i] - closes[i - 1]

        gains.append(max(change, 0))
        losses.append(max(-change, 0))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1))
            + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1))
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return 100 - (100 / (1 + rs))


def yahoo_data(symbol):

    try:

        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            + symbol
            + ".NS?range=6mo&interval=1d"
        )

        response = session.get(
            url,
            timeout=20
        )

        response.raise_for_status()

        result = response.json()["chart"]["result"][0]

        closes = (
            result["indicators"]["quote"][0]["close"]
        )

        closes = [
            x for x in closes
            if x is not None
        ]

        price = result["meta"].get(
            "regularMarketPrice"
        )

        if price is None and closes:
            price = closes[-1]

        rsi = calculate_rsi(closes)

        return price, rsi

    except Exception as error:

        print(
            "Yahoo error:",
            symbol,
            error
        )

        return None, None


# Add price, RSI and dividend percentage
for event in events:

    price, rsi = yahoo_data(
        event["symbol"]
    )

    event["price"] = price
    event["rsi"] = rsi

    if price and price > 0:

        event["dividendYield"] = (
            event["dividend"]
            / price
            * 100
        )

    else:

        event["dividendYield"] = 0

    time.sleep(0.25)


# -------------------------------------------------------
# Save JSON for GitHub Pages
# -------------------------------------------------------

output = {
    "updated":
        datetime.now().strftime(
            "%d %b %Y, %I:%M %p"
        )
        + " IST",

    "events": events
}


with open(
    "data/dividends.json",
    "w",
    encoding="utf-8"
) as file:

    json.dump(
        output,
        file,
        ensure_ascii=False,
        indent=2
    )


print(
    "SUCCESS:",
    len(events),
    "dividend events saved."
)
