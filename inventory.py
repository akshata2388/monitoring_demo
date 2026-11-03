"""Validate server inventory fields. Values are never passed to a shell."""

import re

ADD_FIELDS = frozenset({"csrf_token", "name", "host", "ssh_port", "ssh_user"})
DELETE_FIELDS = frozenset({"csrf_token"})
HOST_RE = re.compile(r"^[A-Za-z0-9._:\-\[\]]{1,253}$")
USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,31}$")
NAME_MAX = 64


class FormError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def parse_server_form(form, *, require_name: bool) -> dict:
    extra = set(form.keys()) - ADD_FIELDS
    if extra:
        raise FormError("Unexpected fields.")
    name = _text(form, "name")
    host = _text(form, "host")
    user = _text(form, "ssh_user")
    port_text = _text(form, "ssh_port")
    if name is None or host is None or user is None or port_text is None:
        raise FormError("Check the name, host, port, and user.")
    name = name.strip()
    host = host.strip()
    user = user.strip()
    port_text = port_text.strip()
    if require_name and not name:
        raise FormError("Name and host are required.")
    if not host:
        raise FormError("Name and host are required.")
    if name and not _valid_name(name):
        raise FormError("Check the name, host, port, and user.")
    if not HOST_RE.fullmatch(host) or not USER_RE.fullmatch(user):
        raise FormError("Check the name, host, port, and user.")
    port = _port(port_text)
    return {"name": name, "host": host, "ssh_port": port, "ssh_user": user}


def reject_unexpected(form, allowed: frozenset[str]) -> None:
    if set(form.keys()) - allowed:
        raise FormError("Unexpected fields.")


def _text(form, key: str) -> str | None:
    value = form.get(key, "")
    if not isinstance(value, str):
        return None
    return value


def _valid_name(name: str) -> bool:
    if len(name) > NAME_MAX:
        return False
    return all(ord(char) >= 32 for char in name)


def _port(port_text: str) -> int:
    if port_text == "":
        return 22
    if not port_text.isdigit():
        raise FormError("Port must be between 1 and 65535.")
    port = int(port_text)
    if port < 1 or port > 65535:
        raise FormError("Port must be between 1 and 65535.")
    return port
