import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from . import db
from .config import Config
from .embasa import EmbasaClient
from .mailer import send_bill

log = logging.getLogger(__name__)


def process_user(cfg: Config, conn, user, dry_run: bool = False) -> int:
    """Send every not-yet-sent bill of one user. Returns how many were sent."""
    client = EmbasaClient(user["cpf"], user["password"])
    client.login()
    matriculas = client.matriculas()
    log.info("CPF %s: %d matrícula(s): %s", user["cpf"], len(matriculas), ", ".join(matriculas))

    sent = 0
    for matricula in matriculas:
        try:
            bills = client.bills(matricula)
        except Exception:
            log.exception("CPF %s: failed to list bills of matrícula %s", user["cpf"], matricula)
            continue
        for bill in bills:
            if db.is_sent(conn, user["id"], bill.matricula, bill.referencia):
                continue
            label = f"matrícula {bill.matricula} ref {bill.referencia_label}"
            if dry_run:
                log.info("[dry-run] would send %s (venc. %s, %s) to %s",
                         label, bill.due_date, bill.amount, user["email"])
                continue
            try:
                pdf = client.download_bill(bill)
                send_bill(cfg, user["email"], bill, pdf)
            except Exception:
                # Not marked as sent, so it is retried on the next run.
                log.exception("CPF %s: failed to send %s", user["cpf"], label)
                continue
            db.mark_sent(conn, user["id"], bill.matricula, bill.referencia,
                         bill.due_date, bill.amount, user["email"])
            log.info("sent %s to %s", label, user["email"])
            sent += 1
    return sent


def run_once(cfg: Config, dry_run: bool = False, cpf: str = None) -> int:
    conn = db.connect(cfg.db_path)
    try:
        users = db.list_users(conn, only_active=True, cpf=cpf)
        if not users:
            log.warning("no active users configured; add one with the add-user command")
        total = 0
        for user in users:
            try:
                total += process_user(cfg, conn, user, dry_run=dry_run)
            except Exception:
                log.exception("CPF %s: run failed", user["cpf"])
        log.info("run finished: %d bill(s) sent", total)
        return total
    finally:
        conn.close()


def _next_run(cfg: Config, now: datetime) -> datetime:
    hour, minute = (int(part) for part in cfg.run_at.split(":"))
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


def serve(cfg: Config) -> None:
    tz = ZoneInfo(cfg.tz)
    if cfg.run_on_start:
        run_once(cfg)
    while True:
        target = _next_run(cfg, datetime.now(tz))
        log.info("next check at %s", target.isoformat(timespec="minutes"))
        while (remaining := (target - datetime.now(tz)).total_seconds()) > 0:
            time.sleep(min(remaining, 300))
        run_once(cfg)
