from __future__ import annotations
from typing import Any, Protocol, runtime_checkable, Optional
import logging


@runtime_checkable
class CommsProtocol(Protocol):
    def send(self, data: Any) -> None: ...
    def receive(self) -> Any: ...
    def parse(self, data: Any) -> Any: ...

    def create_task(self, *args: Any, **kwargs: Any) -> Any: ...
    def cancel_task(self, task: Any) -> None: ...


class CommsManager:
    def __init__(
        self, comms: CommsProtocol, *, logger: Optional[logging.Logger] = None
    ) -> None:
        if not isinstance(comms, CommsProtocol):
            raise TypeError(
                "comms must implement send/receive/parse/create_task/cancel_task methods"
            )

        self._comms = comms
        self._logger = logger or logging.getLogger(__name__)

    def __str__(self) -> str:
        self._logger.debug(f"CommsManager 使用的 comms 类型: {type(self._comms)}")
        return f"CommsManager({self._comms})"

    def send_data(self, data: Any) -> None:
        try:
            self._comms.send(data)
        except Exception:
            self._logger.exception(f"{self._comms} send failed")
            raise

    def receive_data(self) -> Any:
        try:
            return self._comms.receive()
        except Exception:
            self._logger.exception(f"{self._comms} receive failed")
            raise

    def parse_data(self, data: Any) -> Any:
        try:
            return self._comms.parse(data)
        except Exception:
            self._logger.exception(f"{self._comms} parse failed")
            raise

    def create_task(self, *args: Any, **kwargs: Any) -> Any:
        try:
            return self._comms.create_task(*args, **kwargs)
        except Exception:
            self._logger.exception(f"{self._comms} create_task failed")
            raise

    def cancel_task(self, task: Any) -> None:
        try:
            self._comms.cancel_task(task)
        except Exception:
            self._logger.exception(f"{self._comms} cancel_task failed")
            raise
