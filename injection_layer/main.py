from __future__ import annotations
from src.protocol_injector import CommsManager
from src.logger_mixin import LoggerMixin, configure_default_logging
from dataclasses import dataclass
from queue import Queue, Empty
from threading import Thread, Event
from typing import Optional
import logging


@dataclass(frozen=True)
class CANFrame:
    can_id: int
    data: bytes
    is_extended_id: bool = False

    def __str__(self) -> str:
        data_hex = self.data.hex(" ").upper()
        id_fmt = f"0x{self.can_id:X}"
        ext = "EXT" if self.is_extended_id else "STD"
        return f"CANFrame({ext}, id={id_fmt}, data={data_hex})"


class QueuedCANComms(LoggerMixin):
    """
    示例：通过 Queue 传输 CAN 帧的"注入层"通信类。
    CommsManager 会调用 send/receive/parse。
    继承 LoggerMixin 以使用 self.log 记录日志。
    """

    def __init__(self, tx: Queue[CANFrame], rx: Queue[CANFrame]):
        self._tx = tx
        self._rx = rx
        self.log.info("QueuedCANComms 初始化完成")

    def send(self, data) -> None:
        frame = (
            data
            if isinstance(data, CANFrame)
            else CANFrame(can_id=0x123, data=str(data).encode("utf-8"))
        )
        self.log.debug(f"发送 CAN 帧: {frame}")
        self._tx.put(frame)

    def receive(self, timeout: float = 1.0) -> Optional[CANFrame]:
        try:
            frame = self._rx.get(timeout=timeout)
            if frame:
                self.log.debug(f"接收 CAN 帧: {frame}")
            return frame
        except Empty:
            self.log.warning(f"接收超时 ({timeout}s)")
            return None

    def parse(self, data) -> str:
        if data is None:
            return "No CAN data"
        if isinstance(data, CANFrame):
            result = f"Parsed CAN: {data}"
            self.log.info(
                f"解析 CAN 帧: ID=0x{data.can_id:X}, 数据长度={len(data.data)}"
            )
            return result
        return f"Parsed CAN (raw): {data!r}"

    def create_task(self, *args, **kwargs) -> None:
        pass  # No-op for this example

    def cancel_task(self, task: None) -> None:
        pass  # No-op for this example


class CANBusSimulator(LoggerMixin):
    """
    示例：用线程模拟 CAN 总线，把 tx 帧"回环"到 rx。
    实际项目中这里应替换为 python-can 等驱动层。
    继承 LoggerMixin 以记录总线活动。
    """

    def __init__(self, tx: Queue[CANFrame], rx: Queue[CANFrame]):
        self._tx = tx
        self._rx = rx
        self._stop = Event()
        self._t = Thread(target=self._run, daemon=True)
        self.log.info("CANBusSimulator 已创建")

    def start(self) -> None:
        self._t.start()

    def stop(self) -> None:
        self._stop.set()
        self._t.join(timeout=2.0)

    def _run(self) -> None:
        self.log.debug("CAN 总线模拟线程开始运行")
        while not self._stop.is_set():
            try:
                frame = self._tx.get(timeout=0.1)
            except Empty:
                continue

            # 回环 + 轻微变换：把第一个字节加 1，模拟 ECU 响应
            data = frame.data
            if data:
                data = bytes([(data[0] + 1) & 0xFF]) + data[1:]
            response = CANFrame(
                can_id=frame.can_id + 0x8,
                data=data,
                is_extended_id=frame.is_extended_id,
            )
            self.log.debug(f"总线回环: 0x{frame.can_id:X} -> 0x{response.can_id:X}")
            self._rx.put(response)
        self.log.debug("CAN 总线模拟线程结束")


def demo_can_with_queue(logger) -> None:
    print("\n" + "=" * 60)
    print("--- CAN demo (Queue injection + LoggerMixin) ---")
    print("=" * 60)
    tx_q: Queue[CANFrame] = Queue()
    rx_q: Queue[CANFrame] = Queue()

    bus = CANBusSimulator(tx_q, rx_q)
    bus.start()

    comms = QueuedCANComms(tx_q, rx_q)
    manager = CommsManager(comms, logger=logger)

    manager.send_data(
        CANFrame(can_id=0x7DF, data=bytes.fromhex("02 01 0C 00 00 00 00 00"))
    )  # 示例：OBD-II PID 0C
    resp = manager.receive_data()
    print(resp)
    print(manager.parse_data(resp))

    bus.stop()


@dataclass(frozen=True)
class UDSRequest:
    service_id: int
    payload: bytes = b""

    def to_bytes(self) -> bytes:
        return bytes([self.service_id]) + self.payload


@dataclass(frozen=True)
class UDSResponse:
    payload: bytes

    def __str__(self) -> str:
        return f"UDSResponse({self.payload.hex(' ').upper()})"


class QueuedUDSComms(LoggerMixin):
    """
    示例：通过 Queue 传输 UDS 请求/响应。
    注意：真实 UDS 通常跑在 ISO-TP/CAN 上；这里用 queue 抽象"传输层"。
    继承 LoggerMixin 以记录 UDS 通信活动。
    """

    def __init__(self, tx: Queue[bytes], rx: Queue[bytes]):
        self._tx = tx
        self._rx = rx
        self.log.info("QueuedUDSComms 初始化完成")

    def send(self, data) -> None:
        if isinstance(data, UDSRequest):
            payload = data.to_bytes()
            self.log.debug(
                f"发送 UDS 请求: SID=0x{data.service_id:02X}, 数据={payload.hex(' ').upper()}"
            )
            self._tx.put(payload)
        elif isinstance(data, (bytes, bytearray)):
            self.log.debug(f"发送原始数据: {bytes(data).hex(' ').upper()}")
            self._tx.put(bytes(data))
        else:
            self.log.debug(f"发送文本数据: {data}")
            self._tx.put(str(data).encode("utf-8"))

    def receive(self, timeout: float = 1.0) -> Optional[UDSResponse]:
        try:
            raw = self._rx.get(timeout=timeout)
            self.log.debug(f"接收 UDS 响应: {raw.hex(' ').upper()}")
            return UDSResponse(payload=raw)
        except Empty:
            self.log.warning(f"UDS 响应接收超时 ({timeout}s)")
            return None

    def parse(self, data) -> str:
        if data is None:
            return "No UDS data"
        if isinstance(data, UDSResponse):
            b = data.payload
        elif isinstance(data, (bytes, bytearray)):
            b = bytes(data)
        else:
            return f"Parsed UDS (raw): {data!r}"

        if not b:
            return "Parsed UDS: <empty>"

        sid = b[0]
        if sid == 0x7F and len(b) >= 3:
            result = (
                f"Parsed UDS: NegativeResponse, reqSID=0x{b[1]:02X}, NRC=0x{b[2]:02X}"
            )
            self.log.warning(f"UDS 否定响应: 请求SID=0x{b[1]:02X}, NRC=0x{b[2]:02X}")
            return result
        if sid >= 0x40:
            result = f"Parsed UDS: PositiveResponse SID=0x{sid:02X}, data={b[1:].hex(' ').upper()}"
            self.log.info(f"UDS 肯定响应: SID=0x{sid:02X}")
            return result
        result = f"Parsed UDS: Request SID=0x{sid:02X}, data={b[1:].hex(' ').upper()}"
        self.log.debug(f"UDS 请求: SID=0x{sid:02X}")
        return result

    def create_task(self, *args, **kwargs) -> None:
        pass  # No-op for this example

    def cancel_task(self, task: None) -> None:
        pass  # No-op for this example


class UDSEcuSimulator(LoggerMixin):
    """
    示例：用线程模拟 ECU，对少量 UDS 服务做响应：
    - 0x10 DiagnosticSessionControl -> 0x50
    - 0x22 ReadDataByIdentifier(DID) -> 0x62 + DID + 2 bytes data
    其他 -> 0x7F NRC 0x11 (ServiceNotSupported)
    继承 LoggerMixin 以记录 ECU 模拟行为。
    """

    def __init__(self, tx: Queue[bytes], rx: Queue[bytes]):
        self._tx = tx
        self._rx = rx
        self._stop = Event()
        self._t = Thread(target=self._run, daemon=True)
        self.log.info("UDSEcuSimulator 已创建")

    def start(self) -> None:
        self._t.start()
        self.log.info("UDS ECU 模拟器已启动")

    def stop(self) -> None:
        self.log.info("正在停止 UDS ECU 模拟器...")
        self._stop.set()
        self._t.join(timeout=2.0)
        self.log.info("UDS ECU 模拟器已停止")

    def _run(self) -> None:
        self.log.debug("UDS ECU 模拟线程开始运行")
        while not self._stop.is_set():
            try:
                req = self._tx.get(timeout=0.1)
            except Empty:
                continue

            if not req:
                continue

            sid = req[0]
            self.log.debug(
                f"ECU 收到请求: SID=0x{sid:02X}, 数据={req.hex(' ').upper()}"
            )

            if sid == 0x10 and len(req) >= 2:
                sub = req[1]
                response = bytes([0x50, sub, 0x00, 0x32])  # 示例 P2/P2* 仅占位
                self.log.info(
                    f"ECU 响应 DiagnosticSessionControl: 会话类型=0x{sub:02X}"
                )
                self._rx.put(response)
            elif sid == 0x22 and len(req) >= 3:
                did = req[1:3]
                response = bytes([0x62]) + did + bytes.fromhex("12 34")
                self.log.info(
                    f"ECU 响应 ReadDataByIdentifier: DID=0x{did.hex().upper()}"
                )
                self._rx.put(response)
            else:
                response = bytes([0x7F, sid, 0x11])
                self.log.warning(f"ECU 不支持的服务: SID=0x{sid:02X}, 返回 NRC 0x11")
                self._rx.put(response)
        self.log.debug("UDS ECU 模拟线程结束")


def demo_uds_with_queue(logger) -> None:
    print("\n" + "=" * 60)
    print("--- UDS demo (Queue injection + LoggerMixin) ---")
    print("=" * 60)
    tx_q: Queue[bytes] = Queue()
    rx_q: Queue[bytes] = Queue()

    ecu = UDSEcuSimulator(tx_q, rx_q)
    ecu.start()

    comms = QueuedUDSComms(tx_q, rx_q)
    manager = CommsManager(comms, logger=logger)
    manager.__str__()  # 触发日志输出
    
    manager.send_data(UDSRequest(service_id=0x10, payload=b"\x03"))  # 扩展会话
    resp1 = manager.receive_data()
    print(resp1)
    print(manager.parse_data(resp1))

    manager.send_data(
        UDSRequest(service_id=0x22, payload=bytes.fromhex("F1 90"))
    )  # DID F190
    resp2 = manager.receive_data()
    print(resp2)
    print(manager.parse_data(resp2))

    ecu.stop()


if __name__ == "__main__":
    # 配置日志系统（在应用入口调用一次）
    configure_default_logging(level=logging.DEBUG)
    logger = logging.getLogger("CommsManager")

    print("\n" + "#" * 60)
    print("# LoggerMixin 演示：基于 CAN 和 UDS 通信场景")
    print("#" * 60)
    print("\n所有通信类都继承了 LoggerMixin，通过 self.log 记录操作日志")
    print("观察下方输出，了解 LoggerMixin 在实际通信场景中的使用\n")

    # CAN 和 UDS 演示现在都使用 LoggerMixin
    demo_can_with_queue(logger)
    demo_uds_with_queue(logger)
