"""Ephemeral scoped Jar matching Helper's BrowserCookie protocol.

Leading-dot domains are domain cookies; other domains are host-only. Equal
paths preserve snapshot/creation order, including replacements.
"""

from __future__ import annotations

import math
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

TOP_SITE = "https://goofish.com"
ALLOWED_HOSTS = frozenset({"h5api.m.goofish.com", "www.goofish.com", "passport.goofish.com", "seller.goofish.com"})
NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")


def allowed_url(url: str) -> bool:
    try:
        u = urlsplit(url)
        return (u.scheme == "https" and u.hostname in ALLOWED_HOSTS
                and u.port in (None, 443) and u.username is None and u.password is None)
    except ValueError:
        return False


def clean_url(url: str) -> str:
    u = urlsplit(url)
    return u._replace(query="", fragment="").geturl()


def identity(c: dict) -> tuple:
    return c["name"], c["domain"].lower(), c["path"], c.get("partitionKey", "")


class CookieJar:
    def __init__(self, snapshot: list[dict]):
        self.cookies: list[dict] = []
        for raw in snapshot:
            if not isinstance(raw, dict) or any(not isinstance(raw.get(k), str) for k in ("name", "value", "domain", "path")):
                raise ValueError("invalid snapshot")
            if (not NAME.fullmatch(raw["name"]) or not raw["domain"] or not raw["path"].startswith("/")
                    or any(ord(ch) < 32 or ord(ch) >= 127 or ch in ';,"\\' for ch in raw["value"])):
                raise ValueError("invalid snapshot")
            if not re.fullmatch(r"\.?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*", raw["domain"]):
                raise ValueError("invalid snapshot domain")
            for key in ("httpOnly", "secure"):
                if key in raw and not isinstance(raw[key], bool):
                    raise ValueError("invalid snapshot flag")
            expiry = raw.get("expires", 0)
            if isinstance(expiry, bool) or not isinstance(expiry, (int, float)) or not math.isfinite(expiry):
                raise ValueError("invalid snapshot expiry")
            if any(not isinstance(raw.get(k, ""), str) for k in ("sameSite", "partitionKey")):
                raise ValueError("invalid snapshot attribute")
            c = dict(raw, domain=raw["domain"].lower())
            old = next((i for i, x in enumerate(self.cookies) if identity(x) == identity(c)), None)
            if old is None:
                self.cookies.append(c)
            else:
                self.cookies[old] = c

    def matching(self, url: str, *, document: bool = False, now: float | None = None) -> list[dict]:
        u = urlsplit(url)
        host, path = u.hostname or "", u.path or "/"
        now = time.time() if now is None else now
        matched = []
        for c in self.cookies:
            domain, cp = c["domain"], c["path"]
            domain_ok = host == domain or (domain.startswith(".") and (host == domain[1:] or host.endswith(domain)))
            path_ok = path == cp or (path.startswith(cp) and (cp.endswith("/") or path[len(cp):].startswith("/")))
            if (not domain_ok or not path_ok or (c.get("expires", 0) > 0 and c["expires"] <= now)
                    or (c.get("secure", False) and u.scheme not in ("https", "wss"))
                    or c.get("partitionKey", "") not in ("", TOP_SITE)
                    or (document and c.get("httpOnly", False))):
                continue
            matched.append(c)
        return sorted(matched, key=lambda c: -len(c["path"]))

    def header(self, url: str) -> str:
        return "; ".join(f"{c['name']}={c['value']}" for c in self.matching(url))

    def token(self, page_url: str) -> str:
        c = next((c for c in self.matching(page_url, document=True) if c["name"] == "_m_h5_tk"), None)
        return c["value"].split("_", 1)[0] if c else ""

    def apply(self, url: str, headers: list[str], received: datetime) -> None:
        u = urlsplit(url)
        host = u.hostname or ""
        for raw in headers:
            parts = raw.split(";")
            name, sep, value = parts[0].strip().partition("=")
            value = value.strip()
            if value.startswith('"') and value.endswith('"') and len(value) >= 2:
                value = value[1:-1]
            if not sep or not NAME.fullmatch(name) or any(ord(ch) < 32 or ord(ch) >= 127 or ch in ';,"\\' for ch in value):
                continue
            attrs = {}
            for part in parts[1:]:
                key, _, val = part.strip().partition("=")
                attrs[key.lower()] = val.strip()
            raw_domain = attrs.get("domain", "").lower()
            base = raw_domain.lstrip(".")
            if raw_domain and (base not in ALLOWED_HOSTS | {"goofish.com", "m.goofish.com"}
                               or not (host == base or host.endswith("." + base))):
                continue
            domain = "." + base if raw_domain else host
            path = attrs.get("path") or (u.path.rsplit("/", 1)[0] or "/")
            if not path.startswith("/"):
                path = "/"
            secure = "secure" in attrs
            same_site = attrs.get("samesite", "").capitalize()
            if same_site not in ("Strict", "Lax", "None"):
                same_site = ""
            if ((same_site == "None" and not secure) or ("partitioned" in attrs and not secure)
                    or (name.startswith("__Secure-") and not secure)
                    or (name.startswith("__Host-") and (not secure or raw_domain or attrs.get("path") != "/"))):
                continue
            expiry = 0
            expiry_present = False
            try:
                expiry = parsedate_to_datetime(attrs["expires"]).timestamp()
                expiry_present = True
            except (KeyError, ValueError, TypeError, OverflowError):
                pass
            deleted = expiry_present and expiry <= received.timestamp()
            if re.fullmatch(r"-?\d+", attrs.get("max-age", "")):
                seconds = int(attrs["max-age"])
                deleted = seconds <= 0
                expiry = int(received.timestamp()) + seconds if seconds > 0 else 0
            c = {"name": name, "value": value, "domain": domain, "path": path,
                 "expires": expiry, "httpOnly": "httponly" in attrs, "secure": secure,
                 "sameSite": same_site, "partitionKey": TOP_SITE if "partitioned" in attrs else ""}
            old = next((i for i, x in enumerate(self.cookies) if identity(x) == identity(c)), None)
            if deleted:
                if old is not None:
                    self.cookies.pop(old)
            elif old is None:
                self.cookies.append(c)
            else:
                self.cookies[old] = c
