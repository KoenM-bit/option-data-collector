import requests
from bs4 import BeautifulSoup
import datetime as dt

BASE = "https://www.beursduivel.be"
URL = f"{BASE}/Aandeel-Koers/11755/Ahold-Delhaize-Koninklijke/opties-expiratiedatum.aspx"
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ------------------ Helpers ------------------

def clean_href(href: str) -> str:
    """Zet relatieve href om naar absolute URL."""
    href = href.replace("../../../", "/")
    return f"{BASE}{href}"

def _parse_eu_number(s: str) -> float:
    """Parse '1.234,56' -> 1234.56 en '1,900' -> 1.9"""
    s = (s or "").strip().replace("\xa0", "")
    s = s.replace(".", "")  # verwijder duizendtallen
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None

# ------------------ Fetchers ------------------

def fetch_option_chain():
    print(f"Fetching option overview from {URL} ...")
    r = requests.get(URL, headers=HEADERS)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    expiries = set()
    for section in soup.select("section.contentblock"):
        expiry_el = section.find("h3", class_="titlecontent")
        expiry_text = expiry_el.get_text(strip=True) if expiry_el else "Unknown Expiry"
        expiries.add(expiry_text)
    print("Distinct expiries found:", list(expiries))

    options = []
    for section in soup.select("section.contentblock"):
        expiry_el = section.find("h3", class_="titlecontent")
        expiry_text = expiry_el.get_text(strip=True) if expiry_el else "Unknown Expiry"

        for row in section.select("tr"):
            strike_cell = row.select_one(".optiontable__focus")
            strike = strike_cell.get_text(strip=True).split()[0] if strike_cell else None

            bid_call = row.select_one(".optiontable__bidcall")
            ask_call = row.select_one(".optiontable__askcall")
            bid_put = row.select_one(".optiontable__bid")
            ask_put = row.select_one(".optiontable__askput")

            for opt_type in ["Call", "Put"]:
                link = row.select_one(f"a.optionlink.{opt_type}")
                if not link or "href" not in link.attrs:
                    continue

                href = link["href"]
                parts = href.split("/")
                issue_id = next((p for p in parts if p.isdigit()), None)
                if not issue_id:
                    continue

                full_url = clean_href(href)

                # Kies juiste bid/ask afhankelijk van optietype
                if opt_type == "Call":
                    bid_el, ask_el = bid_call, ask_call
                else:
                    bid_el, ask_el = bid_put, ask_put

                bid_val = _parse_eu_number(bid_el.get_text(strip=True)) if bid_el and bid_el.get_text(strip=True) else None
                ask_val = _parse_eu_number(ask_el.get_text(strip=True)) if ask_el and ask_el.get_text(strip=True) else None

                options.append({
                    "type": opt_type,
                    "expiry": expiry_text,
                    "strike": strike,
                    "issue_id": issue_id,
                    "url": full_url,
                    "bid": bid_val,
                    "ask": ask_val
                })

    print(f"Found {len(options)} options in total.")
    return options


def get_live_price(issue_id: str, detail_url: str):
    """Haal actuele prijs, datum en volume van de echte optiepagina (werkt ook met numerieke ID’s)."""
    r = requests.get(detail_url, headers=HEADERS)
    if not r.ok:
        print(f"⚠️ Failed to fetch detail page for {issue_id}")
        return None
    soup = BeautifulSoup(r.text, "html.parser")

    # Gebruik find() ipv select_one() – werkt ook bij numerieke IDs
    price_el = soup.find("span", id=f"{issue_id}LastPrice")
    date_el = soup.find("time", id=f"{issue_id}LastDateTime")
    vol_el = soup.find("span", id=f"{issue_id}Volume")

    if not price_el:
        print(f"⚠️ No price element found for {issue_id}")
        return None

    last_raw = price_el.get_text(strip=True)
    last_val = _parse_eu_number(last_raw)
    date_text = date_el.get_text(strip=True) if date_el else None
    volume_text = vol_el.get_text(strip=True).replace("\xa0", "") if vol_el else None
    volume = int(volume_text) if volume_text and volume_text.isdigit() else None

    return {
        "last_raw": last_raw,
        "last": last_val,
        "date_text": date_text,
        "volume": volume
    }


def get_historical_prices(issue_id):
    """Haal historische (interday) data voor een optie."""
    hist_url = f"{BASE}/issues/interday.ashx?id={issue_id}"
    r = requests.get(hist_url, headers=HEADERS)
    if not r.ok or not r.text.strip():
        print(f"No historical data for {issue_id}")
        return []
    try:
        data = r.json()
    except ValueError:
        print(f"⚠️  Non-JSON response for {issue_id}: {r.text[:80]}")
        return []
    out = []
    for ts, price in data.get("HistoricalData", []):
        date = dt.datetime.utcfromtimestamp(ts / 1000).strftime("%Y-%m-%d")
        out.append({"date": date, "price": price})
    return out

# ------------------ Main logic ------------------

if __name__ == "__main__":
    options = fetch_option_chain()

    # Zoek de gewenste optie
    target = next(
        (o for o in options
         if "November 2025" in o["expiry"]
         and o["type"] == "Call"
         and o["strike"].startswith("38")),
        None
    )

    if not target:
        print("❌ Target option not found.")
        exit()

    print(f"\nSelected: {target}\n")

    # 1️⃣ Eerst: gebruik bid/ask van overzichtspagina
    bid = target.get("bid")
    ask = target.get("ask")
    mid = None
    if bid and ask:
        mid = round((bid + ask) / 2, 3)
        print(f"📈 Using BID/ASK from overview: bid={bid}, ask={ask}, mid={mid}")
    elif bid:
        mid = bid
        print(f"📈 Using BID price only: {bid}")
    elif ask:
        mid = ask
        print(f"📈 Using ASK price only: {ask}")
    else:
        print("ℹ️ No bid/ask on overview, will try live price...")

    # 2️⃣ Dan: detailpagina
    live = get_live_price(target["issue_id"], target["url"])
    print("Live Price:", live)

    # 3️⃣ Historische data
    hist = get_historical_prices(target["issue_id"])
    print(f"\nLast 5 historical prices:")
    for h in hist[-5:]:
        print(f"{h['date']}: {h['price']}")

    # 4️⃣ Beslis welke prijs we gebruiken
    final_price = None
    source = None
    if mid:
        final_price = mid
        source = "BID/ASK"
    elif live and live.get("last") is not None:
        final_price = live["last"]
        source = "LIVE"
    elif hist:
        final_price = hist[-1]["price"]
        source = "HISTORICAL"

    if final_price is not None:
        print(f"\n✅ Using {source} price: {final_price}")
    else:
        print("\n❌ No valid price data found.")

    print(f"\nFinal most recent price: {final_price}")