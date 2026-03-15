from pydantic import BaseModel, Field
from typing import Optional

class CheckRequest(BaseModel):
    number: str = Field(..., min_length=2, max_length=6, pattern=r"^\d+$")
    regions: list[str] = Field(default=["mn", "mt", "mb"])


class MatchItem(BaseModel):
    draw_date: str
    region: str
    region_name: str
    province: str
    prize_name: str
    prize_tier: int
    number: str
    days_ago: int
    link: str


class PrizeTierResult(BaseModel):
    prize_tier: str          
    prize_name: str
    prize_value: int
    digits_matched: int
    suffix: str            
    match_count: int
    matches: list[MatchItem]


class CheckResponse(BaseModel):
    ticket_number: str
    total_matches: int
    best_prize_name: Optional[str] = None
    best_prize_value: int = 0
    tiers: list[PrizeTierResult]