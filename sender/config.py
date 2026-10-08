import os
from dataclasses import dataclass


def _bool(value: str) -> bool:
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Config:
    db_path: str
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_security: str
    run_at: str
    tz: str
    run_on_start: bool
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        env = os.environ.get
        smtp_user = env("SMTP_USER", "")
        return cls(
            db_path=env("DB_PATH", "data/embasa.db"),
            smtp_host=env("SMTP_HOST", ""),
            smtp_port=int(env("SMTP_PORT", "587")),
            smtp_user=smtp_user,
            smtp_password=env("SMTP_PASSWORD", ""),
            smtp_from=env("SMTP_FROM", "") or smtp_user,
            smtp_security=env("SMTP_SECURITY", "starttls").lower(),
            run_at=env("RUN_AT", "08:00"),
            tz=env("TZ", "America/Bahia"),
            run_on_start=_bool(env("RUN_ON_START", "true")),
            log_level=env("LOG_LEVEL", "INFO").upper(),
        )
