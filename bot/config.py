import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    bot_token: str
    admin_id: int
    db_path: str = "data/bot.db"
    allowed_user_ids: set[int] = None  # default to {admin_id} later


def load_config() -> Config:
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    admin_id_str = os.getenv("ADMIN_ID", "").strip()
    db_path = os.getenv("DB_PATH", "data/bot.db").strip()
    allowed_ids_str = os.getenv("ALLOWED_USER_IDS", "").strip()

    if not token:
        raise RuntimeError("BOT_TOKEN not set. Provide it via .env or environment.")
    if not admin_id_str.isdigit():
        raise RuntimeError("ADMIN_ID must be a numeric Telegram user id.")

    admin_id = int(admin_id_str)
    allowed_ids: set[int] = {admin_id}
    if allowed_ids_str:
        for p in allowed_ids_str.split(","):
            p = p.strip()
            if p.isdigit():
                allowed_ids.add(int(p))

    return Config(bot_token=token, admin_id=admin_id, db_path=db_path, allowed_user_ids=allowed_ids)

