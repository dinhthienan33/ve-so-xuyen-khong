import os
from dataclasses import dataclass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

@dataclass(frozen=True)
class LotteryConfig:
    DB_FILE = os.path.join(BASE_DIR, "lottery_data.db")
    BASE_URL = "https://xskt.com.vn"
    
    REGIONS = {
        "mn": "Miền Nam",
        "mt": "Miền Trung",
        "mb": "Miền Bắc",
    }
    
    REGION_URL_PREFIX = {
        "mn": "xsmn",
        "mt": "xsmt",
        "mb": "xsmb",
    }


    PRIZE_STRUCTURE = {
        0: ("Giải Đặc Biệt", 2_000_000_000, 6),
        1: ("Giải Nhất", 30_000_000, 5),
        2: ("Giải Nhì", 15_000_000, 5),
        3: ("Giải Ba", 10_000_000, 5),
        4: ("Giải Tư", 3_000_000, 5),
        5: ("Giải Năm", 1_000_000, 4),
        6: ("Giải Sáu", 400_000, 4),
        7: ("Giải Bảy", 200_000, 3),
        8: ("Giải Tám", 100_000, 2),
    }

    SPECIAL_PRIZE_PHU_DB = 50_000_000
    SPECIAL_PRIZE_KHUYEN_KHICH = 6_000_000