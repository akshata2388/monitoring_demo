"""One SSH private key from the environment, system known_hosts, short timeout.

Unknown hosts are rejected. This module does not add host keys automatically.
Host, user, and port are passed as SSH library arguments, never through a shell.
"""

import logging
import os
import socket
from contextlib import contextmanager

import paramiko

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT = 5.0
SSH_NOT_CONFIGURED = "SSH key is not configured."
SSH_FAILED = "Could not connect."


class SSHConfigError(Exception):
    """SSH_KEY_PATH is missing or is not a file."""


def key_path() -> str | None:
    raw = os.environ.get("SSH_KEY_PATH", "").strip()
    if not raw or not os.path.isfile(raw):
        return None
    return raw


def known_hosts_path() -> str | None:
    raw = os.environ.get("SSH_KNOWN_HOSTS", "").strip()
    return raw or None


def failure_kind(exc: BaseException) -> str:
    """A short category for logs. The exception text is not included."""
    if isinstance(exc, SSHConfigError):
        return "config"
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, paramiko.AuthenticationException):
        return "auth"
    if isinstance(exc, paramiko.BadHostKeyException):
        return "hostkey"
    return exc.__class__.__name__


def connect(
    host: str,
    port: int,
    user: str,
    timeout: float = CONNECT_TIMEOUT,
    client_factory=paramiko.SSHClient,
):
    """Open a client. On failure the client is closed before the error is raised."""
    path = key_path()
    if path is None:
        raise SSHConfigError()
    client = client_factory()
    try:
        hosts_file = known_hosts_path()
        if hosts_file:
            client.load_host_keys(hosts_file)
        else:
            client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            hostname=host,
            port=int(port),
            username=user,
            password=None,
            key_filename=path,
            timeout=timeout,
            auth_timeout=timeout,
            banner_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client
    except Exception:
        client.close()
        raise


@contextmanager
def session(host: str, port: int, user: str, opener=None):
    """Yield an open client and close it in a finally block."""
    client = None
    try:
        if opener is None:
            client = connect(host, port, user)
        else:
            client = opener(host, port, user)
        yield client
    finally:
        if client is not None:
            client.close()
