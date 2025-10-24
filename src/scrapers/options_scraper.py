"""
Beursduivel scraper - exact same functionality as your original beursduivel.py
All scraping logic preserved without any changes to behavior.
"""

from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from src.config.settings import settings
from src.utils.data_utils import _parse_eu_number, clean_href


class OptionsDataScraper:
    """
    Professional options data scraper for Beursduivel.be.
    Implements comprehensive options data collection with robust error handling.
    """

    def __init__(self):
        self.base_url = "https://www.beursduivel.be"
        self.ahold_url = f"{self.base_url}/Aandeel-Koers/11755/Ahold-Delhaize-Koninklijke/opties-expiratiedatum.aspx"
        self.headers = {"User-Agent": settings.user_agent}

    def fetch_option_chain(self) -> List[Dict[str, Any]]:
        """
        Fetch option overview - exact same logic as your original fetch_option_chain().
        Returns exact same data structure.
        """
        print(f"Fetching option overview from {self.ahold_url} ...")
        r = requests.get(self.ahold_url, headers=self.headers)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        options = []

        for section in soup.select("section.contentblock"):
            expiry_el = section.find("h3", class_="titlecontent")
            expiry_text = (
                expiry_el.get_text(strip=True) if expiry_el else "Unknown Expiry"
            )

            for row in section.select("tr"):
                strike_cell = row.select_one(".optiontable__focus")
                strike = (
                    strike_cell.get_text(strip=True).split()[0] if strike_cell else None
                )

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

                    bid_el, ask_el = (
                        (bid_call, ask_call)
                        if opt_type == "Call"
                        else (bid_put, ask_put)
                    )
                    bid_val = (
                        _parse_eu_number(bid_el.get_text(strip=True))
                        if bid_el and bid_el.get_text(strip=True)
                        else None
                    )
                    ask_val = (
                        _parse_eu_number(ask_el.get_text(strip=True))
                        if ask_el and ask_el.get_text(strip=True)
                        else None
                    )

                    options.append(
                        {
                            "type": opt_type,
                            "expiry": expiry_text,
                            "strike": strike,
                            "issue_id": issue_id,
                            "url": full_url,
                            "bid": bid_val,
                            "ask": ask_val,
                        }
                    )

        print(f"Found {len(options)} options in total.")
        return options

    def get_live_price(
        self, issue_id: str, detail_url: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get live price for specific option - exact same logic as your original get_live_price().
        Returns exact same data structure.
        """
        r = requests.get(detail_url, headers=self.headers)
        if not r.ok:
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        price_el = soup.find("span", id=f"{issue_id}LastPrice")
        date_el = soup.find("time", id=f"{issue_id}LastDateTime")
        vol_el = soup.find("span", id=f"{issue_id}Volume")

        if not price_el:
            return None

        last_raw = price_el.get_text(strip=True)
        last_val = _parse_eu_number(last_raw)
        date_text = date_el.get_text(strip=True) if date_el else None
        volume_text = (
            vol_el.get_text(strip=True).replace("\xa0", "") if vol_el else None
        )
        volume = int(volume_text) if volume_text and volume_text.isdigit() else None

        return {
            "last_raw": last_raw,
            "last": last_val,
            "date_text": date_text,
            "volume": volume,
        }
