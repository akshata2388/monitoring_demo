"""In-memory SSH stand-ins. Tests that use these never open a socket."""


class Stream:
    def __init__(self, data: bytes, code: int = 0):
        self._data = data
        self._code = code
        self.channel = self

    def settimeout(self, _timeout):
        return None

    def recv_exit_status(self):
        return self._code

    def read(self, _limit):
        data = self._data
        self._data = b""
        return data

    def close(self):
        return None


class ScriptedClient:
    """Return scripted stdout for allow-listed commands and record close()."""

    def __init__(self, outputs: dict[str, list[tuple[int, str]]]):
        self.outputs = {key: list(value) for key, value in outputs.items()}
        self.commands: list[str] = []
        self.closed = False

    def exec_command(self, command, timeout=None):
        self.commands.append(command)
        queue = self.outputs[command]
        code, text = queue.pop(0) if len(queue) > 1 else queue[0]
        raw = text.encode()
        return Stream(b""), Stream(raw, code), Stream(b"")

    def close(self):
        self.closed = True
