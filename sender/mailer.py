import smtplib
import ssl
from email.message import EmailMessage

from .config import Config
from .embasa import Bill


def send_bill(cfg: Config, recipients: str, bill: Bill, pdf: bytes) -> None:
    """Send one bill PDF. Raises if the SMTP server does not accept the message."""
    if not cfg.smtp_host or not cfg.smtp_from:
        raise RuntimeError("SMTP is not configured (SMTP_HOST / SMTP_FROM)")

    msg = EmailMessage()
    msg["Subject"] = f"Embasa - 2ª via - matrícula {bill.matricula} - {bill.referencia_label}"
    msg["From"] = cfg.smtp_from
    msg["To"] = ", ".join(a.strip() for a in recipients.split(",") if a.strip())
    msg.set_content(
        "Segue em anexo a 2ª via da conta de água (Embasa).\n\n"
        f"Matrícula: {bill.matricula}\n"
        f"Referência: {bill.referencia_label}\n"
        f"Vencimento: {bill.due_date or '-'}\n"
        f"Valor: {bill.amount or '-'}\n"
    )
    safe_ref = "".join(c if c.isalnum() else "-" for c in bill.referencia_label)
    msg.add_attachment(
        pdf,
        maintype="application",
        subtype="pdf",
        filename=f"embasa-{bill.matricula}-{safe_ref}.pdf",
    )

    context = ssl.create_default_context()
    if cfg.smtp_security == "ssl":
        server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, context=context, timeout=60)
    else:
        server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=60)
    with server:
        if cfg.smtp_security == "starttls":
            server.starttls(context=context)
        if cfg.smtp_user:
            server.login(cfg.smtp_user, cfg.smtp_password)
        server.send_message(msg)
