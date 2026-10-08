"""HTTP client for Embasa's "Atendimento Virtual" portal (2ª via de conta).

Mirrors the calls made by the portal's own "Segunda Via" wizard:
  login form  -> /o/embasa-cliente-controller/clientes/matriculas
              -> /o/embasa-segunda-via/validacao      (bills of one matrícula)
              -> /o/embasa-conta-controller/gerar-boleto ("BAIXAR 2ª VIA", PDF as base64)
"""
import base64
import html
import logging
import re
from dataclasses import dataclass
from typing import List, Optional

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://atendimentovirtual.embasa.ba.gov.br"
SERVICE_PATH = "/segunda-via"
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
TIMEOUT = 60


class EmbasaError(Exception):
    pass


class LoginError(EmbasaError):
    pass


@dataclass
class Bill:
    matricula: str
    referencia: str
    referencia_label: str
    due_date: Optional[str]
    amount: Optional[str]
    status_code: str


def only_digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def format_cpf(cpf: str) -> str:
    d = only_digits(cpf)
    if len(d) != 11:
        raise ValueError(f"CPF must have 11 digits, got {cpf!r}")
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _js_unescape(value: str) -> str:
    value = re.sub(r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), value)
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), value)


def _theme_display(page: str, getter: str) -> Optional[str]:
    match = re.search(
        getter + r"\s*:\s*function\s*\(\)\s*\{\s*return\s+'?(.*?)'?;\s*\}", page, re.S
    )
    return _js_unescape(match.group(1)) if match else None


def _auth_token(page: str) -> Optional[str]:
    match = re.search(r"Liferay\.authToken\s*=\s*'([^']+)'", page)
    return match.group(1) if match else None


class EmbasaClient:
    def __init__(self, cpf: str, password: str):
        self.cpf = format_cpf(cpf)
        self.password = password
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.auth_token = ""
        self.group_id = ""
        self.user_name = ""
        self.document = self.cpf

    def _get_page(self, path: str, **kwargs) -> str:
        resp = self.session.get(BASE_URL + path, timeout=TIMEOUT, **kwargs)
        resp.raise_for_status()
        return resp.text

    def login(self) -> None:
        page = self._get_page("/login", params={"redirect": SERVICE_PATH})
        form = re.search(r"<form\b[^>]*\bsign-in-form\b[^>]*>.*?</form>", page, re.S)
        if not form:
            raise LoginError("login form not found (portal layout changed?)")
        form_html = form.group(0)
        action = re.search(r'action="([^"]+)"', form_html)
        if not action:
            raise LoginError("login form has no action URL")

        data = {}
        for tag in re.findall(r"<input\b[^>]*>", form_html):
            name = re.search(r'\bname="([^"]+)"', tag)
            if not name:
                continue
            value = re.search(r'\bvalue="([^"]*)"', tag)
            data[name.group(1)] = html.unescape(value.group(1)) if value else ""
        for name in data:
            if name.endswith("_login"):
                data[name] = self.cpf
            elif name.endswith("_password"):
                data[name] = self.password
            elif name.endswith("_redirect"):
                data[name] = SERVICE_PATH
        if not any(n.endswith("_login") for n in data):
            raise LoginError("login form fields not found (portal layout changed?)")

        resp = self.session.post(html.unescape(action.group(1)), data=data, timeout=TIMEOUT)
        resp.raise_for_status()

        page = self._get_page(SERVICE_PATH)
        if _theme_display(page, "isSignedIn") != "true":
            raise LoginError(f"login rejected for CPF {self.cpf} (wrong CPF or password?)")
        self.auth_token = _auth_token(page) or ""
        self.group_id = _theme_display(page, "getScopeGroupId") or ""
        self.user_name = _theme_display(page, "getUserName") or ""
        if not self.auth_token:
            raise LoginError("could not read the portal CSRF token after login")
        self.session.headers["x-csrf-token"] = self.auth_token
        self.document = self._session_value("cnpj") or self._session_value("cpf") or self.cpf
        log.debug("logged in as %r, document %s", self.user_name, self.document)

    def _session_value(self, key: str) -> str:
        """Equivalent of Liferay.Util.Session.get(key) in the portal's JS."""
        try:
            resp = self.session.post(
                BASE_URL + "/c/portal/session_click",
                data={"cmd": "get", "key": key},
                timeout=TIMEOUT,
            )
            value = resp.text.strip() if resp.ok else ""
        except requests.RequestException:
            value = ""
        return value if only_digits(value) and "<" not in value else ""

    def _api(self, path: str, params: dict):
        resp = self.session.get(BASE_URL + path, params=params, timeout=TIMEOUT)
        try:
            payload = resp.json()
        except ValueError:
            payload = None
        if not resp.ok:
            detail = payload.get("descricao") if isinstance(payload, dict) else resp.text[:200]
            raise EmbasaError(f"{path} returned HTTP {resp.status_code}: {detail}")
        return payload

    def matriculas(self) -> List[str]:
        tipo_pessoa = 4 if len(self.document) == 14 else 5
        payload = self._api(
            "/o/embasa-cliente-controller/clientes/matriculas",
            {"cpfcnpj": self.document, "tipoPessoa": tipo_pessoa, "p_auth": self.auth_token},
        )
        log.debug("matriculas payload: %r", payload)
        if isinstance(payload, dict):
            payload = next((v for v in payload.values() if isinstance(v, list)), [])
        result = []
        for item in payload or []:
            if isinstance(item, dict):
                item = next(
                    (v for k, v in item.items() if "matricula" in k.lower() and v), None
                )
            if item is not None and str(item).strip() and str(item).strip() not in result:
                result.append(str(item).strip())
        return result

    def bills(self, matricula: str) -> List[Bill]:
        payload = self._api(
            "/o/embasa-segunda-via/validacao",
            {
                "matricula": matricula,
                "documentoSolicitante": self.document,
                "groupID": self.group_id,
            },
        )
        log.debug("bills payload for %s: %r", matricula, payload)
        if not isinstance(payload, list):
            # The portal answers with {"descricao": "..."} when there is nothing to show.
            detail = payload.get("descricao") if isinstance(payload, dict) else payload
            log.info("matrícula %s: no bills (%s)", matricula, detail)
            return []
        bills = []
        for item in payload:
            if not isinstance(item, dict) or not item.get("referencia"):
                continue
            amount = item.get("valorContaFormatado") or item.get("valorConta")
            bills.append(
                Bill(
                    matricula=matricula,
                    referencia=str(item["referencia"]),
                    referencia_label=str(item.get("referenciaFormatada") or item["referencia"]),
                    due_date=item.get("dataVencimento"),
                    amount=str(amount) if amount is not None else None,
                    status_code=str(item.get("codigoRetencao", "")),
                )
            )
        return bills

    def download_bill(self, bill: Bill) -> bytes:
        payload = self._api(
            "/o/embasa-conta-controller/gerar-boleto",
            {
                "matricula": bill.matricula,
                "referencia": bill.referencia,
                "documentoSolicitante": self.document,
                "nomeSolicitante": self.user_name,
                "p_auth": self.auth_token,
            },
        )
        encoded = payload.get("pdfbase64") if isinstance(payload, dict) else None
        if not encoded:
            raise EmbasaError(f"no PDF returned for {bill.matricula} ref {bill.referencia}")
        pdf = base64.b64decode(encoded)
        if not pdf.startswith(b"%PDF"):
            raise EmbasaError(f"invalid PDF returned for {bill.matricula} ref {bill.referencia}")
        return pdf
