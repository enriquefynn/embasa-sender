import argparse
import getpass
import logging
import sys

from . import db
from .config import Config
from .embasa import format_cpf
from .service import run_once, serve


def main() -> int:
    parser = argparse.ArgumentParser(prog="sender", description="Email Embasa water bills (2ª via).")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="check every day at RUN_AT (default command)")

    p = sub.add_parser("run-once", help="check now and exit")
    p.add_argument("--dry-run", action="store_true", help="list what would be sent, send nothing")
    p.add_argument("--cpf", help="only this user")

    p = sub.add_parser("add-user", help="add a user, or update password/email of an existing CPF")
    p.add_argument("--cpf", required=True)
    p.add_argument("--email", required=True, help="recipient(s), comma separated")
    p.add_argument("--password", help="portal password (prompted if omitted)")

    for name, text in (("remove-user", "delete a user and its sent history"),
                       ("disable-user", "stop checking a user"),
                       ("enable-user", "resume checking a user")):
        p = sub.add_parser(name, help=text)
        p.add_argument("--cpf", required=True)

    sub.add_parser("list-users", help="list configured users")
    p = sub.add_parser("list-sent", help="list bills already emailed")
    p.add_argument("--limit", type=int, default=50)

    args = parser.parse_args()
    cfg = Config.from_env()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.command == "serve":
        serve(cfg)
        return 0
    if args.command == "run-once":
        run_once(cfg, dry_run=args.dry_run, cpf=format_cpf(args.cpf) if args.cpf else None)
        return 0

    conn = db.connect(cfg.db_path)
    if args.command == "add-user":
        password = args.password or getpass.getpass("Embasa password: ")
        if not password:
            print("password is required", file=sys.stderr)
            return 1
        db.upsert_user(conn, format_cpf(args.cpf), password, args.email)
        print(f"saved user {format_cpf(args.cpf)} -> {args.email}")
    elif args.command in ("remove-user", "disable-user", "enable-user"):
        cpf = format_cpf(args.cpf)
        if args.command == "remove-user":
            found = db.remove_user(conn, cpf)
        else:
            found = db.set_active(conn, cpf, args.command == "enable-user")
        if not found:
            print(f"no user with CPF {cpf}", file=sys.stderr)
            return 1
        print(f"{args.command}: {cpf}")
    elif args.command == "list-users":
        for u in db.list_users(conn):
            print(f"{u['cpf']}  {'active' if u['active'] else 'disabled'}  {u['email']}")
    elif args.command == "list-sent":
        for s in db.list_sent(conn, args.limit):
            print(f"{s['sent_at']}  {s['cpf']}  matrícula {s['matricula']}  ref {s['referencia']}  "
                  f"venc. {s['due_date'] or '-'}  {s['amount'] or '-'}  -> {s['email']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
