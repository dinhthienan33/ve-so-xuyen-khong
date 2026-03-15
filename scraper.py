import requests
from bs4 import BeautifulSoup
import sqlite3
import time
import random
import re
import argparse
import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Optional


BASE_URL = "https://xskt.com.vn"
DB_FILE = "lottery_data.db"
LOG_FILE = "scraper.log"

MIN_DELAY = 1.0
MAX_DELAY = 2.0

MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
}

# Mapping vung mien
REGIONS = {
    "mn": {"name": "Mien Nam", "url_prefix": "xsmn"},
    "mt": {"name": "Mien Trung", "url_prefix": "xsmt"},
    "mb": {"name": "Mien Bac", "url_prefix": "xsmb"},
}

# Map ten giai thuong
PRIZE_TIER_MAP = {
    "G.8": 8, "G8": 8, "G.7": 7, "G7": 7,
    "G.6": 6, "G6": 6, "G.5": 5, "G5": 5,
    "G.4": 4, "G4": 4, "G.3": 3, "G3": 3,
    "G.2": 2, "G2": 2, "G.1": 1, "G1": 1,
}

PRIZE_NAMES = {
    0: "Giai Dac Biet",
    1: "Giai Nhat",
    2: "Giai Nhi",
    3: "Giai Ba",
    4: "Giai Tu",
    5: "Giai Nam",
    6: "Giai Sau",
    7: "Giai Bay",
    8: "Giai Tam",
}

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ============================================================================
# DATABASE
# ============================================================================
class LotteryDatabase:
    """Quan ly co so du lieu SQLite de luu ket qua xo so."""

    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lottery_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                draw_date TEXT NOT NULL,
                region TEXT NOT NULL,
                province TEXT NOT NULL,
                prize_name TEXT NOT NULL,
                prize_tier INTEGER NOT NULL,
                number TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scrape_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT NOT NULL,
                last_date TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(region)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_number
            ON lottery_results(number)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_draw_date
            ON lottery_results(draw_date)
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_result
            ON lottery_results(draw_date, region, province, prize_tier, number)
        """)
        self.conn.commit()

    def insert_results(self, results: list[dict]) -> int:
        cursor = self.conn.cursor()
        inserted = 0
        for r in results:
            try:
                cursor.execute("""
                    INSERT OR IGNORE INTO lottery_results
                    (draw_date, region, province, prize_name, prize_tier, number)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    r["draw_date"], r["region"], r["province"],
                    r["prize_name"], r["prize_tier"], r["number"],
                ))
                if cursor.rowcount > 0:
                    inserted += 1
            except sqlite3.Error as e:
                logger.error(f"  DB error: {e}")
        self.conn.commit()
        return inserted

    def save_progress(self, region: str, last_date: str):
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO scrape_progress (region, last_date, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(region) DO UPDATE SET
                last_date = excluded.last_date,
                updated_at = CURRENT_TIMESTAMP
        """, (region, last_date))
        self.conn.commit()

    def get_progress(self, region: str) -> Optional[str]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT last_date FROM scrape_progress WHERE region = ?", (region,)
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def has_data_for_date(self, region: str, date_str: str) -> bool:
        """Kiem tra xem ngay nay da co du lieu cua mien nay chua."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT 1 FROM lottery_results 
            WHERE region = ? AND draw_date = ? 
            LIMIT 1
        """, (region, date_str))
        return cursor.fetchone() is not None

    def get_stats(self) -> dict:
        cursor = self.conn.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM lottery_results")
        stats["total_records"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT draw_date) FROM lottery_results")
        stats["total_days"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT MIN(draw_date), MAX(draw_date) FROM lottery_results"
        )
        row = cursor.fetchone()
        stats["date_range"] = {"from": row[0], "to": row[1]}
        cursor.execute("""
            SELECT region, COUNT(*) as cnt
            FROM lottery_results GROUP BY region
        """)
        stats["by_region"] = {row[0]: row[1] for row in cursor.fetchall()}
        return stats

    def close(self):
        self.conn.close()


# ============================================================================
# SCRAPER
# ============================================================================
class LotteryScraper:
    """Cao du lieu xo so tu xskt.com.vn"""

    def __init__(self, db: LotteryDatabase):
        self.db = db
        self.session = requests.Session()
        self.session.headers.update(HEADERS)

    def _build_url(self, region_code: str, date: datetime) -> str:
        """
        URL pattern: https://xskt.com.vn/xsmn/ngay-D-M-YYYY
        Note: xskt.com.vn accepts single-digit day/month (no leading zeros)
        """
        prefix = REGIONS[region_code]["url_prefix"]
        # Use %-d and %-m for no leading zeros (on Windows, use %#d %#m)
        day = date.day
        month = date.month
        year = date.year
        return f"{BASE_URL}/{prefix}/ngay-{day}-{month}-{year}"

    def _fetch_page(self, url: str) -> Optional[str]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 200:
                    return response.text
                elif response.status_code == 404:
                    logger.warning(f"  404 Not found: {url}")
                    return None
                else:
                    logger.warning(
                        f"  HTTP {response.status_code} for {url} "
                        f"(attempt {attempt}/{MAX_RETRIES})"
                    )
            except requests.exceptions.Timeout:
                logger.warning(f"  Timeout: {url} (attempt {attempt}/{MAX_RETRIES})")
            except requests.exceptions.ConnectionError:
                logger.warning(f"  Connection error: {url} (attempt {attempt}/{MAX_RETRIES})")
            except requests.exceptions.RequestException as e:
                logger.error(f"  Request error: {e}")

            if attempt < MAX_RETRIES:
                wait = MIN_DELAY * attempt
                time.sleep(wait)

        logger.error(f"  FAILED after {MAX_RETRIES} attempts: {url}")
        return None

    def _extract_numbers_from_cell(self, cell) -> list[str]:
        """
        Extract all lottery numbers from a table cell.
        Numbers can be:
        - Plain text
        - Inside <b>, <em>, <p>, <span> tags
        - Separated by <br> tags
        """
        numbers = []

        for br in cell.find_all("br"):
            br.replace_with("|BR|")

        text = cell.get_text()
        parts = text.split("|BR|")

        for part in parts:
            part = part.strip()
            if not part:
                continue

            sub_parts = re.split(r"[\s,\-]+", part)
            for sp in sub_parts:
                cleaned = sp.strip()
                # Keep only digit strings of length >= 2
                if cleaned and cleaned.isdigit() and len(cleaned) >= 2:
                    numbers.append(cleaned)

        return numbers

    def _parse_mien_nam_trung(self, html: str, region_code: str, date: datetime) -> list[dict]:
        """
        Parse results for Mien Nam / Mien Trung.
        Table structure (xskt.com.vn):
          <table class="tbl-xsmn colN" id="MN0">  (or tbl-xsmt)
            <tr>
              <th>Thu X<br>DD/MM</th>
              <th><a href="...">Province 1</a></th>
              <th><a href="...">Province 2</a></th>
              ...
            </tr>
            <tr>
              <td>G.8</td>
              <td><b>92</b></td>
              <td><b>78</b></td>
              ...
            </tr>
            <tr>
              <td>G.7</td>
              <td>124</td>
              <td>090</td>
              ...
            </tr>
            ...  (G.6 with numbers separated by <br>)
            <tr>
              <td>DB</td>   (or the cell text may contain "DB" or "ĐB")
              <td><b>123456</b></td>
              ...
            </tr>
          </table>
        """
        soup = BeautifulSoup(html, "lxml")
        results = []
        date_str = date.strftime("%Y-%m-%d")


        table_class_prefix = "tbl-xsmn" if region_code == "mn" else "tbl-xsmt"
        table = soup.find("table", class_=lambda c: c and table_class_prefix in c)

        if not table:
            table_id = "MN0" if region_code == "mn" else "MT0"
            table = soup.find("table", id=table_id)

        if not table:
            table = soup.find("table", class_=lambda c: c and "tbl-xs" in c)

        if not table:
            logger.warning(f"  No result table found for {date_str} ({region_code})")
            return results

        rows = table.find_all("tr")
        if not rows:
            return results

        header_row = rows[0]
        header_cells = header_row.find_all("th")
        provinces = []
        for i, th in enumerate(header_cells):
            if i == 0:
                continue
            a_tag = th.find("a")
            if a_tag:
                provinces.append(a_tag.get_text(strip=True))
            else:
                text = th.get_text(strip=True)
                if text:
                    provinces.append(text)

        if not provinces:
            logger.warning(f"  No provinces found in header for {date_str}")
            return results

        logger.info(f"  Provinces: {', '.join(provinces)}")

        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue

            prize_text = cells[0].get_text(strip=True).upper()

            if prize_text in PRIZE_TIER_MAP:
                prize_tier = PRIZE_TIER_MAP[prize_text]
            elif "DB" in prize_text or "ĐB" in prize_text:
                prize_tier = 0
            else:
                continue

            prize_name = PRIZE_NAMES.get(prize_tier, f"Giai {prize_tier}")

            data_cells = cells[1:]
            for col_idx, cell in enumerate(data_cells):
                if col_idx >= len(provinces):
                    break

                province = provinces[col_idx]
                numbers = self._extract_numbers_from_cell(cell)

                for number in numbers:
                    results.append({
                        "draw_date": date_str,
                        "region": region_code,
                        "province": province,
                        "prize_name": prize_name,
                        "prize_tier": prize_tier,
                        "number": number,
                    })

        return results

    def _parse_mien_bac(self, html: str, date: datetime) -> list[dict]:
        """
        Parse results for Mien Bac.
        Table structure (xskt.com.vn):
          <table class="result" id="MB0">
            <tr>
              <th colspan="2"><b>XSMB > Thu X (Province)</b></th>
              <th>DAU</th>
              <th>DUOI</th>
            </tr>
            <tr>
              <td>DB</td>
              <td><em>97404</em></td>
              <td>...</td>
              <td>...</td>
            </tr>
            <tr>
              <td>G.1</td>
              <td><p>05695</p></td>
              ...
            </tr>
            ...
          </table>

        Mien Bac has only ONE province per day (unlike MN/MT with multiple).
        """
        soup = BeautifulSoup(html, "lxml")
        results = []
        date_str = date.strftime("%Y-%m-%d")

        # Find the result table
        table = soup.find("table", class_="result")
        if not table:
            table = soup.find("table", id="MB0")
        if not table:
            logger.warning(f"  No result table found for {date_str} (mb)")
            return results

        rows = table.find_all("tr")
        if not rows:
            return results

        province = "Mien Bac"
        header_row = rows[0]
        header_th = header_row.find("th")
        if header_th:
            header_text = header_th.get_text(strip=True)
            match = re.search(r"\((.+?)\)", header_text)
            if match:
                province = match.group(1).strip()

        logger.info(f"  Province: {province}")

        current_prize_tier = None
        for row in rows[1:]:
            cells = row.find_all("td")
            if not cells:
                continue

            first_text = cells[0].get_text(strip=True).upper()

            if first_text in PRIZE_TIER_MAP:
                current_prize_tier = PRIZE_TIER_MAP[first_text]
            elif "DB" in first_text or "ĐB" in first_text:
                current_prize_tier = 0
            elif len(cells) == 1:

                pass

            if current_prize_tier is None:
                continue

            prize_name = PRIZE_NAMES.get(current_prize_tier, f"Giai {current_prize_tier}")

            if len(cells) >= 2:
                number_cell = cells[1]
            elif len(cells) == 1 and not first_text.startswith("G") and "DB" not in first_text:
                number_cell = cells[0]
            else:
                continue

            numbers = self._extract_numbers_from_cell(number_cell)
            for number in numbers:
                results.append({
                    "draw_date": date_str,
                    "region": "mb",
                    "province": province,
                    "prize_name": prize_name,
                    "prize_tier": current_prize_tier,
                    "number": number,
                })

        return results

    def scrape_date(self, region_code: str, date: datetime) -> int:
        url = self._build_url(region_code, date)
        date_str = date.strftime("%d-%m-%Y")
        region_name = REGIONS[region_code]["name"]

        logger.info(f"[>] Scraping {region_name} {date_str}...")

        html = self._fetch_page(url)
        if not html:
            return 0

        if region_code in ("mn", "mt"):
            results = self._parse_mien_nam_trung(html, region_code, date)
        else:
            results = self._parse_mien_bac(html, date)

        if not results:
            logger.info(f"  No data for {date_str}")
            return 0

        inserted = self.db.insert_results(results)
        logger.info(
            f"  [OK] Saved {inserted} new records "
            f"({len(results)} total found)"
        )
        return inserted

    def scrape_range(
        self,
        region_code: str,
        start_date: datetime,
        end_date: datetime,
        resume: bool = False,
    ):
        region_name = REGIONS[region_code]["name"]

        if resume:
            last_date_str = self.db.get_progress(region_code)
            if last_date_str:
                resumed_from = datetime.strptime(last_date_str, "%Y-%m-%d")
                start_date = max(start_date, resumed_from + timedelta(days=1))
                logger.info(
                    f"  Resuming {region_name} from "
                    f"{start_date.strftime('%d-%m-%Y')}"
                )

        total_days = (end_date - start_date).days + 1
        if total_days <= 0:
            logger.info(f"  {region_name}: Already up to date.")
            return

        logger.info(
            f"\n{'='*60}\n"
            f"  START: {region_name}\n"
            f"  From:  {start_date.strftime('%d-%m-%Y')}\n"
            f"  To:    {end_date.strftime('%d-%m-%Y')}\n"
            f"  Total: {total_days} days\n"
            f"{'='*60}"
        )

        total_inserted = 0
        errors = 0
        current_date = start_date

        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            display_date = current_date.strftime("%d-%m-%Y")

            try:
                if self.db.has_data_for_date(region_code, date_str):
                    logger.info(f"  [SKIP] {display_date} already in database.")
                else:
                    inserted = self.scrape_date(region_code, current_date)
                    total_inserted += inserted

                    delay = random.uniform(MIN_DELAY, MAX_DELAY)
                    time.sleep(delay)

                self.db.save_progress(region_code, date_str)

                days_done = (current_date - start_date).days + 1
                percent = (days_done / total_days) * 100
                logger.info(
                    f"  Progress: {days_done}/{total_days} "
                    f"({percent:.1f}%) - {total_inserted} records saved"
                )

            except KeyboardInterrupt:
                logger.warning(
                    "\n  User interrupted! Progress saved. Use --resume to continue."
                )
                return
            except Exception as e:
                logger.error(
                    f"  ERROR on {display_date}: {e}"
                )
                errors += 1

            current_date += timedelta(days=1)

        logger.info(
            f"\n{'='*60}\n"
            f"  DONE: {region_name}\n"
            f"  New records: {total_inserted}\n"
            f"  Errors: {errors}\n"
            f"{'='*60}\n"
        )


# ============================================================================
# MAIN
# ============================================================================
def parse_date(date_str: str) -> datetime:
    try:
        return datetime.strptime(date_str, "%d-%m-%Y")
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Invalid date '{date_str}'. Use format dd-mm-yyyy (e.g. 01-01-2020)"
        )


def main():
    parser = argparse.ArgumentParser(
        description="VE SO MAY MAN - Lottery Data Scraper (xskt.com.vn)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--year", type=int,
        help="Number of years to scrape (e.g. 2 means from Jan 1st of last year to today).",
    )
    parser.add_argument(
        "--from", dest="from_date", type=parse_date,
        help="Start date (dd-mm-yyyy). Default: 1 year ago.",
    )
    parser.add_argument(
        "--to", dest="to_date", type=parse_date,
        help="End date (dd-mm-yyyy). Default: today.",
    )
    parser.add_argument(
        "--region", nargs="+", choices=["mn", "mt", "mb"],
        default=["mn", "mt", "mb"],
        help="Regions: mn (South), mt (Central), mb (North). Default: all.",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="Resume from last scrape position.",
    )
    parser.add_argument(
        "--stats", action="store_true",
        help="Show database statistics and exit.",
    )
    parser.add_argument(
        "--db", default=DB_FILE,
        help=f"Database file path. Default: {DB_FILE}",
    )

    args = parser.parse_args()
    db = LotteryDatabase(args.db)

    if args.stats:
        stats = db.get_stats()
        print("\n" + "=" * 60)
        print("  LOTTERY DATABASE STATISTICS")
        print("=" * 60)
        print(f"  Total records:  {stats['total_records']:,}")
        print(f"  Total draw days: {stats['total_days']:,}")
        if stats["date_range"]["from"]:
            print(f"  Earliest date:  {stats['date_range']['from']}")
            print(f"  Latest date:    {stats['date_range']['to']}")
        print("\n  By region:")
        for region, count in stats.get("by_region", {}).items():
            region_name = REGIONS.get(region, {}).get("name", region)
            print(f"    - {region_name}: {count:,} records")
        print("=" * 60 + "\n")
        db.close()
        return

    end_date = args.to_date or datetime.now()
    
    if args.year is not None:
        # e.g. --year 2 in 2026 means from 2025-01-01
        start_year = end_date.year - args.year + 1
        start_date = datetime(start_year, 1, 1)
    else:
        start_date = args.from_date or (end_date - timedelta(days=365))

    print("""
 ====================================================
  VE SO MAY MAN - LOTTERY SCRAPER
  Source: xskt.com.vn
 ====================================================
    """)

    logger.info(
        f"Starting scrape!\n"
        f"  From:    {start_date.strftime('%d-%m-%Y')}\n"
        f"  To:      {end_date.strftime('%d-%m-%Y')}\n"
        f"  Regions: {', '.join(REGIONS[r]['name'] for r in args.region)}\n"
        f"  Resume:  {'Yes' if args.resume else 'No'}\n"
        f"  DB:      {args.db}"
    )

    scraper = LotteryScraper(db)

    try:
        for region in args.region:
            scraper.scrape_range(
                region_code=region,
                start_date=start_date,
                end_date=end_date,
                resume=args.resume,
            )
    except KeyboardInterrupt:
        logger.warning("\n  Stopped by user.")
    finally:
        stats = db.get_stats()
        logger.info(
            f"\n  Summary: {stats['total_records']:,} records "
            f"across {stats['total_days']:,} draw days."
        )
        db.close()
        logger.info("  Database saved and closed.")


if __name__ == "__main__":
    main()
