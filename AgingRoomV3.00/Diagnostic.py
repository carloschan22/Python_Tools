import can
import time
import isotp
import ctypes
import udsoncan

import Tools
from pathlib import Path
from Logger import LoggerMixin
from typing import Any, Optional
from udsoncan.client import Client
from udsoncan.typing import ClientConfig


from Tools import (
    SELECTED_PROJECT,
    PROJECT_CONFIG,
    FUNCTION_CONFIG,
    create_slot_table,
    normalize_slots,
    set_slot_value,
    validate_slot,
    remap_slot,
)


class DefineDidCodec(udsoncan.DidCodec):
    """自定义DID编解码器"""

    def __init__(self, string_len: int):
        self.string_len = string_len

    def encode(self, *did_value: Any) -> bytes:
        return did_value[0]

    def decode(self, did_payload: bytes) -> Any:
        return did_payload

    def __len__(self) -> int:
        return self.string_len


class SecurityAlgorithm(LoggerMixin):
    """安全算法实现"""

    @staticmethod
    def security_algo(level, seed):
        """计算安全密钥"""
        dll_file_name = PROJECT_CONFIG[SELECTED_PROJECT]["DLL路径"]
        dll_func_name = Tools.get_dll_func_names(dll_file_name)[0]
        ZeekrSeedKey = ctypes.CDLL(str(dll_file_name))
        GenerateKeyEx = ZeekrSeedKey.__getattr__(dll_func_name)

        GenerateKeyEx.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ushort,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ushort),
        ]
        GenerateKeyEx.restype = ctypes.c_uint

        iSeedArray = (ctypes.c_ubyte * len(seed))(*seed)
        iSecurityLevel = ctypes.c_uint(level)
        iVariant = ctypes.c_ubyte()
        iKeyArray = (ctypes.c_ubyte * len(seed))()
        iKeyLen = ctypes.c_ushort(
            PROJECT_CONFIG[SELECTED_PROJECT]["Diag"]["SecurityFeedbackBytes"]
        )

        GenerateKeyEx(
            iSeedArray,
            ctypes.c_ushort(len(seed)),
            iSecurityLevel,
            ctypes.byref(iVariant),
            iKeyArray,
            ctypes.byref(iKeyLen),
        )
        return bytes(iKeyArray)


def _extract_rdbi_value(response: Any, did_int: int) -> Any:
    """从 udsoncan 的 read_data_by_identifier 响应中尽可能提取 DID 的值。

    udsoncan 的对象层级在不同版本/调用方式下会有差异：
    - response.service_data.values 通常是 {did_int: value}
    - 有些情况下 service_data 本身不是可下标对象（会触发 'ResponseData' object is not subscriptable）
    """
    try:
        sd = getattr(response, "service_data", None)
        if sd is not None:
            values = getattr(sd, "values", None)
            if isinstance(values, dict):
                return values.get(did_int)
            if isinstance(sd, dict):
                return sd.get(did_int)
    except Exception:
        pass

    # 兜底：有些实现会把原始 payload 挂在 data 上
    if hasattr(response, "data"):
        return getattr(response, "data")
    return response


class UDSClient(LoggerMixin):
    """UDS诊断客户端：通过依赖注入使用notifier"""

    def __init__(
        self,
        bus: can.BusABC,
        notifier: can.Notifier,
        physical_tx: Optional[int] = None,
        physical_rx: Optional[int] = None,
    ):
        """
        初始化UDS客户端

        Args:
            bus: CAN总线实例
            notifier: Notifier实例（用于注册isotp stack）
            config: 诊断配置, 如果为None则使用默认配置
        """
        self.bus = bus
        self.notifier = notifier
        self.project_cfg = PROJECT_CONFIG[SELECTED_PROJECT]
        self.diag_cfg = self.project_cfg.get("Diag", self.project_cfg)

        # ISO-TP配置（兼容新旧结构）
        diag_addr = self.diag_cfg.get("DiagPhyAddr") or self.project_cfg.get(
            "DiagPhyAddr"
        )
        if (physical_tx is None) or (physical_rx is None):
            if not diag_addr or len(diag_addr) < 2:
                raise ValueError("Diag.DiagPhyAddr 未配置")
            physical_tx = diag_addr[0]
            physical_rx = diag_addr[1]

        self.physical_tx = int(physical_tx)
        self.physical_rx = int(physical_rx)
        self.isotp_params = self._prepare_isotp_params()

        # ISO-TP栈和UDS客户端
        self.stack: Optional[isotp.NotifierBasedCanStack] = None
        self.client: Optional[Client] = None
        self._initialized = False

    def _prepare_isotp_params(self) -> dict:
        """准备ISO-TP参数"""
        # 新结构: Diag.Params.isotp_params
        params_block = self.diag_cfg.get("Params", {})
        params = params_block.get("isotp_params")

        # 旧结构兼容: isotp_params
        if params is None:
            params = self.project_cfg.get("isotp_params")

        if params is None:
            raise ValueError("Diag.Params.isotp_params 未配置")
        return params.copy()

    def initialize(self) -> "UDSClient":
        """初始化ISO-TP栈和UDS客户端"""
        if self._initialized:
            return self

        # 创建ISO-TP地址
        tp_addr = isotp.Address(
            txid=self.physical_tx,
            rxid=self.physical_rx,
        )

        # 创建NotifierBasedCanStack（使用注入的notifier）
        self.stack = isotp.NotifierBasedCanStack(
            bus=self.bus,
            notifier=self.notifier,
            address=tp_addr,
            params=self.isotp_params,
        )

        # 启动stack（将自己注册到notifier）
        self.stack.start()
        self.stack.set_sleep_timing(0, 0)

        # 创建UDS连接
        conn = _NotifierBasedConnection(self.stack)

        # 创建UDS客户端配置
        client_config = self._create_client_config()

        # 创建UDS客户端
        self.client = Client(conn, config=client_config)

        self._initialized = True
        # self.log.debug(f"初始化UDS客户端, Config:{self.diag_cfg}")
        return self

    def _create_client_config(self) -> ClientConfig:
        """创建UDS客户端配置"""
        # 新结构: Diag.Params.default_client_config
        params_block = self.diag_cfg.get("Params", {})
        cfg = params_block.get("default_client_config")
        if cfg is None:
            cfg = self.project_cfg.get("default_client_config")
        if cfg is None:
            raise ValueError("Diag.Params.default_client_config 未配置")
        config_dict = cfg.copy()

        # 配置DID编解码器
        did_config = self.diag_cfg.get("DidConfig")
        if did_config is None:
            did_config = self.project_cfg.get("did_config")
        did_config = did_config or {}

        config_dict["data_identifiers"] = {
            Tools.hex_to_int(did_hex): DefineDidCodec(string_len=info["size"])
            for did_hex, info in did_config.items()
        }
        # 配置安全算法
        config_dict["security_algo"] = SecurityAlgorithm.security_algo

        return ClientConfig(**config_dict)

    def get_client(self) -> Client:
        """获取UDS客户端实例"""
        if not self._initialized:
            raise RuntimeError("UDSClient未初始化, 请先调用initialize()")
        return self.client

    def update_address(self, txid: int, rxid: int) -> None:
        """
        更新ISO-TP通信地址

        Args:
            txid: 发送ID
            rxid: 接收ID
        """
        if not self._initialized:
            raise RuntimeError("UDSClient未初始化")

        new_address = isotp.Address(txid=txid, rxid=rxid)
        self.stack.set_address(new_address)

    def shutdown(self):
        """关闭UDS客户端"""
        if not self._initialized:
            return

        # 停止stack
        if self.stack:
            try:
                self.stack.stop()
            except Exception:
                pass

        self._initialized = False

    def __enter__(self):
        """支持上下文管理器"""
        return self.initialize()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        self.shutdown()


class _NotifierBasedConnection(udsoncan.connections.BaseConnection):
    """为NotifierBasedCanStack定制的UDS连接类"""

    def __init__(self, isotp_stack: isotp.CanStack):
        self.isotp_stack = isotp_stack
        self.opened = False
        super().__init__("NotifierBasedIsoTpConnection")

    def open(self) -> "_NotifierBasedConnection":
        """打开连接"""
        if not self.opened:
            self.opened = True
        return self

    def close(self) -> None:
        """关闭连接"""
        if self.opened:
            self.opened = False

    def specific_send(self, data: bytes) -> None:
        """发送UDS请求"""
        if not self.opened:
            raise RuntimeError("连接未打开")
        self.isotp_stack.send(data)

    def specific_wait_frame(self, timeout: float = 2) -> bytes:
        """等待接收UDS响应"""
        if not self.opened:
            raise RuntimeError("连接未打开")

        import time

        end_time = time.time() + timeout
        while time.time() < end_time:
            if self.isotp_stack.available():
                return self.isotp_stack.recv()
            time.sleep(0.001)

        raise udsoncan.exceptions.TimeoutException(
            f"未在规定时间内收到响应 (timeout={timeout} sec)"
        )

    def empty_rxqueue(self) -> None:
        """清空接收队列"""
        while self.isotp_stack.available():
            self.isotp_stack.recv()

    def is_open(self) -> bool:
        """检查连接是否打开"""
        return self.opened


class MultiSlotDiagnostic(LoggerMixin):
    """80-slot 诊断管理器。

    - 为每个 slot 维护独立的 UDSClient（独立 stack/connection）
    - 诊断前强制 update_address(tx, rx)（采集卡转发场景的正确用法）
    - Diagnostic：对 pending_slots 执行“成功一次即移除”, 结果写入 results
    - PeriodicDiag：对 periodic_slots 周期诊断；失败按 ReDiagInterval 更快重试
    """

    def __init__(self, bus: can.BusABC, notifier: can.Notifier, slot_count: int = 80):
        from Protocol import get_phy_addr_by_slot

        import threading

        self.bus = bus
        self.notifier = notifier
        self.slot_count = int(slot_count)
        self.project_cfg = PROJECT_CONFIG[SELECTED_PROJECT]
        self.diag_cfg = self.project_cfg.get("Diag", self.project_cfg)
        self.remap = FUNCTION_CONFIG.get("UI", {}).get("Remap", False)
        # 周期线程与外部调用可能并发：这里用一把锁保护状态与 isotp/uds 交互
        self._lock = threading.Lock()

        # slot 索引：外部使用 1..N；内部也用 1..N（index 0 为空）
        self._slot_addrs: list[tuple[int, int] | None] = create_slot_table(
            self.slot_count
        )
        for slot_id in range(1, self.slot_count + 1):
            self._slot_addrs[slot_id] = get_phy_addr_by_slot(slot_id)

        # 80 个独立客户端对象（按 slot 固定初始化地址）
        self.clients: list[UDSClient | None] = create_slot_table(self.slot_count)
        for slot_id in range(1, self.slot_count + 1):
            tx, rx = self._slot_addrs[slot_id]
            self.clients[slot_id] = UDSClient(
                bus, notifier, physical_tx=tx, physical_rx=rx
            )

        # Diagnostic: 待诊断 slot 列表（1-based）
        self.pending_slots: list[int] = []
        # Diagnostic: 成功后结果存放（slot 即物理序号；index 0 为空）
        self.results: list[Optional[dict[str, Any]]] = create_slot_table(
            self.slot_count
        )

        # PeriodicDiag
        self.periodic_slots: list[int] = []
        self.periodic_interval_s: float = 10.0
        self.rediag_interval_s: float = 1.0
        # PeriodicDiag: 读 DIDs 与写入计划（写入时可按值列表轮询）
        self.periodic_dids: list[str] = []
        self.periodic_read_dids: list[str] = []
        self.periodic_write_plan: dict[str, list[Any]] = {}
        self._periodic_write_idx: dict[int, dict[str, int]] = {}
        self._periodic_next_due: dict[int, float] = {}
        self.periodic_last: list[Optional[dict[str, Any]]] = create_slot_table(
            self.slot_count
        )
        self.periodic_last_error: list[Optional[str]] = create_slot_table(
            self.slot_count
        )

    def _validate_slot(self, slot: int) -> int:
        return validate_slot(int(slot), self.slot_count)

    def _ensure_client(self, slot: int) -> tuple[UDSClient, Client, int, int]:
        slot = self._validate_slot(slot)
        uds = self.clients[slot].initialize()
        client = uds.get_client()
        tx, rx = self._slot_addrs[slot]
        return uds, client, tx, rx

    def _get_did_cfg(self) -> dict:
        diag_cfg = self.diag_cfg or {}
        return diag_cfg.get("DidConfig") or self.project_cfg.get("did_config") or {}

    def _get_did_type(self, did_hex: str) -> Optional[str]:
        info = self._get_did_cfg().get(did_hex) or {}
        did_type = info.get("type") or info.get("Type")
        if did_type is None:
            return None
        return str(did_type).strip().lower()

    def _encode_did_value(self, did_hex: str, value: Any) -> Optional[bytes]:
        if value is None:
            return None
        did_type = self._get_did_type(did_hex)
        info = self._get_did_cfg().get(did_hex) or {}
        size = info.get("size") or info.get("Size")
        padding = info.get("Padding") or info.get("padding") or "0x00"

        def _to_padding_byte(pad_val) -> int:
            if isinstance(pad_val, int):
                return pad_val & 0xFF
            s = str(pad_val).strip().lower()
            if s.startswith("0x"):
                s = s[2:]
            return int(s, 16) & 0xFF

        if did_type == "bytes":
            if isinstance(value, (bytes, bytearray)):
                payload = bytes(value)
            elif isinstance(value, str):
                s = value.strip().lower()
                if s.startswith("0x"):
                    s = s[2:]
                s = "".join(s.split())
                payload = bytes.fromhex(s)
            elif isinstance(value, (list, tuple)):
                payload = bytes(int(v) for v in value)
            elif isinstance(value, int):
                length = max(1, (value.bit_length() + 7) // 8)
                payload = value.to_bytes(length, byteorder="big", signed=False)
            else:
                payload = bytes(value)
        elif did_type == "string":
            if isinstance(value, (bytes, bytearray)):
                payload = bytes(value)
            else:
                payload = str(value).encode("utf-8")
        else:
            if isinstance(value, (bytes, bytearray)):
                payload = bytes(value)
            elif isinstance(value, str):
                payload = value.encode("utf-8")
            else:
                payload = str(value).encode("utf-8")

        if size is not None:
            try:
                size = int(size)
            except Exception:
                size = None

        if size is not None:
            if len(payload) < size:
                pad_byte = _to_padding_byte(padding)
                payload = payload + bytes([pad_byte]) * (size - len(payload))
            elif len(payload) > size:
                self.log.warning(
                    f"DID {did_hex} payload too long ({len(payload)}>{size}), truncating"
                )
                payload = payload[:size]

        return payload

    def _decode_did_value(self, did_hex: str, value: Any) -> Any:
        did_type = self._get_did_type(did_hex)
        if did_type == "string":
            if isinstance(value, (bytes, bytearray)):
                result = bytes(value).decode("utf-8", errors="ignore")
                return result.replace(" ", "")
            return str(value)
        if did_type == "bytes":
            if isinstance(value, bytearray):
                value = bytes(value)
            if isinstance(value, (bytes, bytearray)):
                return bytes(value).hex()
            return value
        return value

    def read_dids(self, slot: int, dids: list[str]) -> dict[str, Any]:
        with self._lock:
            uds, client, tx, rx = self._ensure_client(slot)
            # 采集卡转发：每次诊断前必须更新物理地址
            uds.update_address(tx, rx)

            out: dict[str, Any] = {}
            with client:
                for did_hex in dids:
                    did_int = Tools.hex_to_int(did_hex)
                    rsp = client.read_data_by_identifier(did_int)
                    raw = _extract_rdbi_value(rsp, did_int)
                    out[did_hex] = self._decode_did_value(did_hex, raw)
            return out

    def write_dids(
        self, slot: int, dids: list[str], values: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        with self._lock:
            uds, client, tx, rx = self._ensure_client(slot)
            self.log.debug(
                f"Slot {slot} 开始写入 DIDs: {dids}, Values: {values}. with TX {tx}, RX {rx}"
            )
            # 采集卡转发：每次诊断前必须更新物理地址
            uds.update_address(tx, rx)

            did_cfg = self._get_did_cfg()
            values = values or {}

            out: dict[str, Any] = {}
            with client:
                # 先切换会话与安全访问（只做一次）
                try:
                    rsp = client.change_session(3)
                except Exception as exc:
                    self.log.error(f"Slot {slot} 切换会话异常: {exc}")
                    for did_hex in dids:
                        out[did_hex] = None
                    return out

                if rsp.positive:
                    self.log.debug(f"Slot {slot} 切换会话成功, 开始安全访问")
                    try:
                        rsp = client.unlock_security_access(1)
                    except Exception as exc:
                        self.log.error(f"Slot {slot} 安全访问异常: {exc}")
                        for did_hex in dids:
                            out[did_hex] = None
                        return out

                    if not rsp.positive:
                        self.log.warning(
                            f"Slot {slot} 安全访问失败, 响应码: {rsp.code_name}"
                        )
                else:
                    self.log.warning(
                        f"Slot {slot} 切换会话失败, 响应码: {rsp.code_name}"
                    )

                if not rsp.positive:
                    for did_hex in dids:
                        out[did_hex] = None
                    return out

                for did_hex in dids:
                    did_int = Tools.hex_to_int(did_hex)
                    info = did_cfg.get(did_hex) or {}
                    raw_value = values.get(
                        did_hex, info.get("value") or info.get("Value")
                    )
                    payload = self._encode_did_value(did_hex, raw_value)
                    if payload is None:
                        out[did_hex] = None
                        self.log.warning(
                            f"Slot {slot} DID {did_hex} 写入失败, 未配置 value"
                        )
                        continue
                    try:
                        rsp = client.write_data_by_identifier(did_int, payload)
                    except Exception as exc:
                        out[did_hex] = None
                        self.log.error(f"Slot {slot} DID {did_hex} 写入异常: {exc}")
                        continue
                    if rsp.positive:
                        out[did_hex] = _extract_rdbi_value(rsp, did_int)
                    else:
                        out[did_hex] = None
                        self.log.warning(
                            f"Slot {slot} DID {did_hex} 写入失败, 响应码: {rsp.code_name}"
                        )
            return out

    # -------- Diagnostic (one-shot success) --------

    def set_pending_slots(self, slots: list[int]) -> None:
        with self._lock:
            self.pending_slots = normalize_slots(slots, self.slot_count)

    def add_pending_slots(self, slots: list[int]) -> None:
        with self._lock:
            for s in slots:
                s = self._validate_slot(int(s))
                if s not in self.pending_slots:
                    self.pending_slots.append(s)

    def run_pending_once(self, dids: list[str] | dict) -> dict[str, Any]:
        # 支持 PeriodicDiag.Dids 为 dict 时仅取键作为 DID 列表
        if isinstance(dids, dict):
            dids = list(dids.keys())
        ok: list[int] = []
        fail: dict[int, str] = {}

        with self._lock:
            slots = list(self.pending_slots)
        # 根据配置中的 Operation 决定读/写
        did_cfg = self._get_did_cfg()

        def _op_for(did_hex: str) -> str:
            info = did_cfg.get(did_hex) or {}
            op = info.get("Operation") or info.get("operation") or "Read"
            return str(op).strip().lower()

        read_dids: list[str] = []
        write_dids: list[str] = []
        for did in dids:
            op = _op_for(did)
            if op == "write":
                write_dids.append(did)
            else:
                read_dids.append(did)

        for slot in slots:
            try:
                data: dict[str, Any] = {}
                if read_dids:
                    data.update(self.read_dids(slot, read_dids))
                if write_dids:
                    values = {
                        did: (did_cfg.get(did) or {}).get("value")
                        or (did_cfg.get(did) or {}).get("Value")
                        for did in write_dids
                    }
                    data.update(
                        self.write_dids(
                            remap_slot(slot) if self.remap else slot, write_dids, values
                        )
                    )  # 诊断穴位重映射.
                with self._lock:
                    set_slot_value(self.results, slot, data, self.slot_count)
                ok.append(slot)
            except Exception as exc:
                fail[slot] = str(exc)

        # 成功一次后移除
        if ok:
            with self._lock:
                self.pending_slots = [s for s in self.pending_slots if s not in ok]

        with self._lock:
            pending = list(self.pending_slots)

        return {"ok": ok, "fail": fail, "pending": pending}

    # -------- PeriodicDiag --------

    def configure_periodic(
        self, interval_s: float, rediag_interval_s: float, dids: list[str] | dict
    ) -> None:
        def _normalize_value_list(values: Any) -> list[Any]:
            if values is None:
                return []
            if isinstance(values, str):
                return [v.strip() for v in values.split(",") if v.strip()]
            if isinstance(values, (list, tuple)):
                out: list[Any] = []
                for v in values:
                    if isinstance(v, str):
                        parts = [p.strip() for p in v.split(",") if p.strip()]
                        out.extend(parts)
                    else:
                        out.append(v)
                return out
            return [values]

        with self._lock:
            self.periodic_interval_s = float(interval_s)
            self.rediag_interval_s = float(rediag_interval_s)
            self.periodic_read_dids = []
            self.periodic_write_plan = {}
            self._periodic_write_idx = {}

            if isinstance(dids, dict):
                for did_hex, values in dids.items():
                    vlist = _normalize_value_list(values)
                    if vlist:
                        self.periodic_write_plan[str(did_hex)] = vlist
                self.periodic_dids = list(self.periodic_write_plan.keys())
            else:
                self.periodic_read_dids = list(dids or [])
                self.periodic_dids = list(self.periodic_read_dids)

    def set_periodic_slots(self, slots: list[int]) -> None:
        with self._lock:
            self.periodic_slots = normalize_slots(slots, self.slot_count)
            now = time.time()
            # 新设置的 slot 立即触发一次
            for s in self.periodic_slots:
                self._periodic_next_due.setdefault(s, now)
                self._periodic_write_idx.setdefault(s, {})

    def periodic_tick(self) -> dict[str, Any]:
        now = time.time()
        ran: list[int] = []

        with self._lock:
            slots = list(self.periodic_slots)
            read_dids = list(self.periodic_read_dids)
            write_plan = {k: list(v) for k, v in self.periodic_write_plan.items()}
            interval_s = float(self.periodic_interval_s)
            rediag_s = float(self.rediag_interval_s)

        # 根据配置中的 Operation 决定读/写
        did_cfg = self._get_did_cfg()

        def _op_for(did_hex: str) -> str:
            info = did_cfg.get(did_hex) or {}
            op = info.get("Operation") or info.get("operation") or "Read"
            return str(op).strip().lower()

        def _next_write_value(slot: int, did_hex: str, values: list[Any]) -> Any:
            if not values:
                return None
            with self._lock:
                slot_map = self._periodic_write_idx.setdefault(slot, {})
                idx = slot_map.get(did_hex, 0)
                slot_map[did_hex] = idx + 1
            return values[idx % len(values)]

        # 若使用 list 配置, 则按 DID 配置决定读/写
        read_list: list[str] = []
        write_list: list[str] = []
        if read_dids:
            for did in read_dids:
                if _op_for(did) == "write":
                    write_list.append(did)
                else:
                    read_list.append(did)

        for slot in slots:
            with self._lock:
                due = self._periodic_next_due.get(slot, now)
            if now < due:
                continue
            ran.append(slot)
            try:
                data: dict[str, Any] = {}

                if read_list:
                    data.update(self.read_dids(slot, read_list))

                if write_list:
                    values = {
                        did: (did_cfg.get(did) or {}).get("value")
                        or (did_cfg.get(did) or {}).get("Value")
                        for did in write_list
                    }
                    data.update(self.write_dids(slot, write_list, values))

                if write_plan:
                    write_dids = list(write_plan.keys())
                    values = {
                        did: _next_write_value(slot, did, write_plan.get(did, []))
                        for did in write_dids
                    }
                    data.update(self.write_dids(slot, write_dids, values))

                with self._lock:
                    set_slot_value(self.periodic_last, slot, data, self.slot_count)
                    set_slot_value(
                        self.periodic_last_error,
                        slot,
                        None,
                        self.slot_count,
                    )
                    self._periodic_next_due[slot] = now + interval_s
            except Exception as exc:
                with self._lock:
                    set_slot_value(self.periodic_last, slot, None, self.slot_count)
                    set_slot_value(
                        self.periodic_last_error,
                        slot,
                        str(exc),
                        self.slot_count,
                    )
                    self._periodic_next_due[slot] = now + rediag_s

        return {
            "__ts__": now,
            "slots": slots,
            "ran": ran,
        }

    def periodic_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "__ts__": time.time(),
                "slots": list(self.periodic_slots),
                "data": list(self.periodic_last),
                "error": list(self.periodic_last_error),
            }

    def shutdown(self) -> None:
        for uds in self.clients:
            try:
                uds.shutdown()
            except Exception:
                pass
