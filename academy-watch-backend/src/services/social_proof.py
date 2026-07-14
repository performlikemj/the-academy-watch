"""Best-effort verification of one-time codes on public social profiles.

This checker is deliberately advisory: a successful lookup helps an admin
review a claim, but it never approves one. The request path is tightly scoped
to known social hosts and manually controlled redirects to keep user-supplied
URLs away from internal services.
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urljoin, urlparse

import requests
from src.utils.sanitize import is_safe_https_url

ALLOWED_SOCIAL_HOSTS = (
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "youtube.com",
)

_BODY_LIMIT_BYTES = 2 * 1024 * 1024
_MAX_REDIRECTS = 3
_REDIRECT_STATUSES = {301, 302, 303, 307, 308}
_USER_AGENT = "The Academy Watch social-profile verifier/1.0"


def _allowed_hostname(hostname: str) -> bool:
    host = hostname.lower()
    return any(host == allowed or host.endswith(f".{allowed}") for allowed in ALLOWED_SOCIAL_HOSTS)


def validate_proof_url(url: str) -> tuple[bool, str]:
    """Validate a proof URL without performing DNS or network access."""
    if not is_safe_https_url(url):
        return False, "URL must be an absolute HTTPS URL."
    try:
        parsed = urlparse(url.strip())
        hostname = parsed.hostname
        # Accessing parsed.port can itself raise for malformed ports.
        parsed_port = parsed.port
    except (TypeError, ValueError):
        return False, "URL is malformed."

    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return False, "URL must not contain user information."
    if parsed_port is not None or ":" in parsed.netloc:
        return False, "URL must not contain an explicit port."
    if not hostname:
        return False, "URL must include a hostname."

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        return False, "IP-address hosts are not allowed."

    if not _allowed_hostname(hostname):
        return False, "URL hostname is not an allowed social-profile host."
    return True, ""


def _read_capped_body(response) -> bytes:
    """Read at most two decoded-megabytes from a streamed response."""
    body = bytearray()
    for chunk in response.iter_content(chunk_size=64 * 1024, decode_unicode=False):
        if not chunk:
            continue
        remaining = _BODY_LIMIT_BYTES - len(body)
        if remaining <= 0:
            break
        body.extend(chunk[:remaining])
        if len(body) >= _BODY_LIMIT_BYTES:
            break
    return bytes(body)


def _decode_body(body: bytes, encoding: str | None) -> str:
    try:
        return body.decode(encoding or "utf-8", errors="replace")
    except (LookupError, TypeError):
        return body.decode("utf-8", errors="replace")


def _close_quietly(resource) -> None:
    """Close a response/session without letting cleanup violate no-raise."""
    close = getattr(resource, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        pass


def check_proof(url: str, code: str) -> dict:
    """Check whether ``code`` appears in the capped public profile response.

    Every failure is represented as ``found=False``; callers never need to
    handle a networking or parsing exception from this advisory service.
    """
    valid, reason = validate_proof_url(url)
    if not valid:
        return {"found": False, "note": f"Proof URL was refused: {reason}"}
    if not isinstance(code, str) or not code.strip():
        return {"found": False, "note": "The claim has no verification code to check."}

    current_url = url.strip()
    session = None
    try:
        session = requests.Session()
        # Do not consult .netrc/proxy environment state or retain response
        # cookies between manually followed hops.
        session.trust_env = False
        session.auth = None
        session.cookies.clear()

        for redirect_count in range(_MAX_REDIRECTS + 1):
            session.cookies.clear()
            response = session.get(
                current_url,
                headers={"User-Agent": _USER_AGENT},
                timeout=(3.05, 6),
                allow_redirects=False,
                stream=True,
            )
            try:
                if response.status_code in _REDIRECT_STATUSES:
                    if redirect_count >= _MAX_REDIRECTS:
                        return {
                            "found": False,
                            "note": "Profile check stopped after the maximum of 3 redirects.",
                        }
                    location = response.headers.get("Location")
                    if not location:
                        return {
                            "found": False,
                            "note": "Profile check stopped because a redirect had no destination.",
                        }
                    next_url = urljoin(current_url, location)
                    redirect_valid, redirect_reason = validate_proof_url(next_url)
                    if not redirect_valid:
                        return {
                            "found": False,
                            "note": f"Profile redirect was refused: {redirect_reason}",
                        }

                    current_host = (urlparse(current_url).hostname or "").lower()
                    next_host = (urlparse(next_url).hostname or "").lower()
                    if next_host != current_host:
                        return {
                            "found": False,
                            "note": "Profile redirect was refused because it changed hostname.",
                        }
                    current_url = next_url
                    continue

                if not 200 <= response.status_code < 300:
                    return {
                        "found": False,
                        "note": f"Public profile returned HTTP {response.status_code}; no code was confirmed.",
                    }

                body = _read_capped_body(response)
                text = _decode_body(body, getattr(response, "encoding", None))
                found = code.casefold() in text.casefold()
                if found:
                    return {
                        "found": True,
                        "note": "Verification code found on the public profile.",
                    }
                return {
                    "found": False,
                    "note": "Verification code was not found in the first 2 MB of the public profile.",
                }
            finally:
                _close_quietly(response)
        return {"found": False, "note": "Profile check stopped before a response could be checked."}
    except requests.RequestException:
        return {"found": False, "note": "A network error prevented the public profile check."}
    except Exception:
        return {"found": False, "note": "The public profile could not be checked."}
    finally:
        if session is not None:
            _close_quietly(session)


__all__ = ["ALLOWED_SOCIAL_HOSTS", "check_proof", "validate_proof_url"]
