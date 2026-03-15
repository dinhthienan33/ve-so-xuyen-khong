import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from models import CheckRequest, CheckResponse, MatchItem, PrizeTierResult
from settings import LotteryConfig, BASE_DIR

# ============================================================================
# DATABASE HELPER
# ============================================================================
@contextmanager
def get_db():
    """Thread-safe database connection context manager."""
    conn = sqlite3.connect(LotteryConfig.DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


# ============================================================================
# FASTAPI APP
# ============================================================================
app = FastAPI(
    title="Vé Số May Mắn API",
    description="Cỗ Máy Thời Gian - Tra cứu lịch sử xổ số kiến thiết",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "images"), exist_ok=True)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
app.mount("/images", StaticFiles(directory=os.path.join(BASE_DIR, "images")), name="images")


# ============================================================================
# ROUTES
# ============================================================================
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    """Serve the main web interface."""
    html_path = os.path.join(BASE_DIR, "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


def _parse_date(date_str: str) -> Optional[datetime]:
    for fmt in ("%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def _days_ago(date_str: str) -> int:
    dt = _parse_date(date_str)
    return (datetime.now() - dt).days if dt else 0


def _build_result_link(region: str, date_str: str) -> str:
    dt = _parse_date(date_str)
    if not dt:
        return LotteryConfig.BASE_URL
    prefix = LotteryConfig.REGION_URL_PREFIX.get(region, "xsmn")
    return f"{LotteryConfig.BASE_URL}/{prefix}/ngay-{dt.day}-{dt.month}-{dt.year}"


def _row_to_match(row) -> MatchItem:
    return MatchItem(
        draw_date=row["draw_date"],
        region=row["region"],
        region_name=LotteryConfig.REGIONS.get(row["region"], row["region"]),
        province=row["province"],
        prize_name=row["prize_name"],
        prize_tier=row["prize_tier"],
        number=row["number"],
        days_ago=_days_ago(row["draw_date"]),
        link=_build_result_link(row["region"], row["draw_date"]),
    )


@app.post("/api/check", response_model=CheckResponse)
async def check_ticket(req: CheckRequest):

    ticket = req.number.strip()
    regions = req.regions

    region_placeholders = ",".join("?" * len(regions))
    tiers: list[PrizeTierResult] = []
    total_matches = 0
    best_prize_name = None
    best_prize_value = 0

    with get_db() as conn:
        cursor = conn.cursor()

        # STEP 1: Check prize tiers 0 (ĐB) → 8 (G8)
        for prize_tier in range(9):
            prize_name, prize_val, digits_needed = LotteryConfig.PRIZE_STRUCTURE[prize_tier]
            suffix = ticket[-digits_needed:] if len(ticket) >= digits_needed else ticket

            cursor.execute(f"""
                SELECT draw_date, region, province, prize_name, prize_tier, number
                FROM lottery_results
                WHERE prize_tier = ?
                  AND number LIKE ?
                  AND region IN ({region_placeholders})
                ORDER BY draw_date DESC
                LIMIT 50
            """, (prize_tier, f"%{suffix}", *regions))

            rows = cursor.fetchall()
            matches = [_row_to_match(r) for r in rows]
            count = len(matches)
            total_matches += count

            if count > 0 and prize_val > best_prize_value:
                best_prize_value = prize_val
                best_prize_name = prize_name

            tiers.append(PrizeTierResult(
                prize_tier=str(prize_tier),
                prize_name=prize_name,
                prize_value=prize_val,
                digits_matched=digits_needed,
                suffix=suffix,
                match_count=count,
                matches=matches,
            ))

        # STEP 2: Giải Phụ Đặc Biệt
        phu_matches = []
        if len(ticket) == 6:
            ticket_last5 = ticket[-5:]
            ticket_first = ticket[0]

            cursor.execute(f"""
                SELECT draw_date, region, province, prize_name, prize_tier, number
                FROM lottery_results
                WHERE prize_tier = 0
                  AND number LIKE ?
                  AND region IN ({region_placeholders})
                ORDER BY draw_date DESC
                LIMIT 200
            """, (f"%{ticket_last5}", *regions))

            for row in cursor.fetchall():
                db_number = row["number"]
                if (len(db_number) == 6
                        and db_number[-5:] == ticket_last5
                        and db_number[0] != ticket_first):
                    phu_matches.append(_row_to_match(row))

        total_matches += len(phu_matches)
        if phu_matches and LotteryConfig.SPECIAL_PRIZE_PHU_DB > best_prize_value:
            best_prize_value = LotteryConfig.SPECIAL_PRIZE_PHU_DB
            best_prize_name = "Giải Phụ Đặc Biệt"

        tiers.append(PrizeTierResult(
            prize_tier="phu_db",
            prize_name="Giải Phụ Đặc Biệt",
            prize_value=LotteryConfig.SPECIAL_PRIZE_PHU_DB,
            digits_matched=5,
            suffix=ticket[-5:] if len(ticket) >= 5 else ticket,
            match_count=len(phu_matches),
            matches=phu_matches,
        ))

        # STEP 3: Giải Khuyến Khích
        kk_matches = []
        if len(ticket) == 6:
            cursor.execute(f"""
                SELECT draw_date, region, province, prize_name, prize_tier, number
                FROM lottery_results
                WHERE prize_tier = 0
                  AND LENGTH(number) = 6
                  AND region IN ({region_placeholders})
                ORDER BY draw_date DESC
            """, (*regions,))

            phu_set = set((m.draw_date, m.number) for m in phu_matches)

            for row in cursor.fetchall():
                db_number = row["number"]
                diff = sum(1 for a, b in zip(ticket, db_number) if a != b)
                if diff == 1:
                    if (row["draw_date"], db_number) not in phu_set:
                        kk_matches.append(_row_to_match(row))

        total_matches += len(kk_matches)
        if kk_matches and LotteryConfig.SPECIAL_PRIZE_KHUYEN_KHICH > best_prize_value:
            best_prize_value = LotteryConfig.SPECIAL_PRIZE_KHUYEN_KHICH
            best_prize_name = "Giải Khuyến Khích"

        tiers.append(PrizeTierResult(
            prize_tier="khuyen_khich",
            prize_name="Giải Khuyến Khích",
            prize_value=LotteryConfig.SPECIAL_PRIZE_KHUYEN_KHICH,
            digits_matched=6,
            suffix=ticket,
            match_count=len(kk_matches),
            matches=kk_matches,
        ))

    return CheckResponse(
        ticket_number=ticket,
        total_matches=total_matches,
        best_prize_name=best_prize_name,
        best_prize_value=best_prize_value,
        tiers=tiers,
    )


@app.get("/api/stats")
async def get_stats():
    """Returns database statistics."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as cnt FROM lottery_results")
        total = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(DISTINCT draw_date) as cnt FROM lottery_results")
        days = cursor.fetchone()["cnt"]

        cursor.execute("SELECT MIN(draw_date) as d FROM lottery_results")
        earliest = cursor.fetchone()["d"]

        cursor.execute("SELECT MAX(draw_date) as d FROM lottery_results")
        latest = cursor.fetchone()["d"]

        cursor.execute("""
            SELECT region, COUNT(*) as cnt
            FROM lottery_results GROUP BY region
        """)
        by_region = {
            row["region"]: {
                "name": LotteryConfig.REGIONS.get(row["region"], row["region"]),
                "count": row["cnt"],
            }
            for row in cursor.fetchall()
        }

    return {
        "total_records": total,
        "total_days": days,
        "date_range": {"from": earliest, "to": latest},
        "by_region": by_region,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
