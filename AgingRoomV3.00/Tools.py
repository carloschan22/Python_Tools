from __future__ import annotations
import can
import time
import json
import logging
import threading
from pathlib import Path
from Logger import configure_default_logging
from typing import Callable, Iterable, List, Optional, Union

_log = logging.getLogger(__name__)


def load_config(file_name) -> dict:
    """加载配置文件"""
    config_folder = Path(__file__).parent / "config"
    with open(config_folder / file_name, "r", encoding="utf-8") as f:
        return json.load(f)
    raise FileNotFoundError(f"配置文件未找到: {file_name}")


FUNCTION_CONFIG = load_config("FuncConfig.json")
PROJECT_CONFIG = load_config("ProjectConfig.json")
COLOR_MAPPING = FUNCTION_CONFIG.get("UI", {}).get(
    "ColorMapping", FUNCTION_CONFIG.get("ColorMapping", {})
)


def get_ui_version() -> str:
    ui_cfg = FUNCTION_CONFIG.get("UI", {})
    version = ui_cfg.get("Version", "")
    return str(version).strip()


def _normalize_grouped_ui_value(
    value, group_count: int, fallback_value: Optional[str] = None
) -> list:
    """将 UI 配置的按组字段统一归一为长度=group_count 的列表。"""
    group_count = max(1, int(group_count))
    items: list = []

    if isinstance(value, list):
        items = list(value)
    elif isinstance(value, dict):
        items = [None] * group_count
        for i in range(1, group_count + 1):
            items[i - 1] = value.get(str(i), value.get(i))
    else:
        items = [value] * group_count

    # 选择可用的默认填充值
    fallback = None
    for v in items:
        if v not in (None, ""):
            fallback = v
            break
    if fallback is None:
        fallback = fallback_value

    # 补齐长度
    if len(items) < group_count:
        items.extend([fallback] * (group_count - len(items)))

    # 填空
    return [fallback if (v is None or v == "") else v for v in items]


def get_default_project(
    group_index: Optional[int] = None, projects: Optional[list[str]] = None
) -> str:
    ui_cfg = FUNCTION_CONFIG.get("UI", {})
    group_count = int(ui_cfg.get("GroupCount", 1))
    projects = projects or list(PROJECT_CONFIG.keys())
    fallback = projects[0] if projects else ""
    items = _normalize_grouped_ui_value(
        ui_cfg.get("DefaultProject"), group_count, fallback
    )
    index = int(group_index or 1)
    if index < 1:
        index = 1
    if index > len(items):
        return fallback
    value = items[index - 1]
    return value if value in projects else fallback


def get_default_operator(
    group_index: Optional[int] = None, operators: Optional[list[str]] = None
) -> str:
    ui_cfg = FUNCTION_CONFIG.get("UI", {})
    group_count = int(ui_cfg.get("GroupCount", 1))
    operators = operators or list(ui_cfg.get("OperatorList", []))
    fallback = operators[0] if operators else ""
    items = _normalize_grouped_ui_value(
        ui_cfg.get("DefaultOperator"), group_count, fallback
    )
    index = int(group_index or 1)
    if index < 1:
        index = 1
    if index > len(items):
        return fallback
    value = items[index - 1]
    return value if (not operators or value in operators) else fallback


def _update_grouped_ui_value(key: str, group_index: int, value) -> None:
    """更新 UI 下的按组字段，并写回 FuncConfig.json。"""
    config_folder = Path(__file__).parent / "config"
    file_path = config_folder / "FuncConfig.json"
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    ui_cfg = data.setdefault("UI", {})
    group_count = int(ui_cfg.get("GroupCount", 1))
    current = ui_cfg.get(key)
    items = _normalize_grouped_ui_value(current, max(group_count, group_index), value)

    index = int(group_index)
    if index < 1:
        index = 1
    if index > len(items):
        items.extend([items[-1] if items else value] * (index - len(items)))
    items[index - 1] = value

    ui_cfg[key] = items

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


SELECTED_PROJECT = get_default_project(1)
logging_level = getattr(logging, FUNCTION_CONFIG["Logging"]["LogLevel"], logging.INFO)
logging_file = FUNCTION_CONFIG["Logging"]["LogPath"]
configure_default_logging(level=logging_level, log_file=logging_file)

_THIRD_PARTY_NOISE_LOGGERS = [
    "isotp",
    "can.kvaser",
    "can.zlg",
    "pymodbus",
    "udsoncan",
    "UdsClient",
    "PowerSupply.DCPS1216",
    "Diagnostic.MultiSlotDiagnostic",
    "Connection[NotifierBasedIsoTpConnection]",
]

for _logger_name in _THIRD_PARTY_NOISE_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)

_UNWANTED_LOGGERS = ["UdsClient"]
for _logger_name in _UNWANTED_LOGGERS:
    logging.getLogger(_logger_name).disabled = True


def hex_to_int(value: Union[str, int]) -> int:
    """将 '0xF190' / 'F190' / 0xF190 转成 int。"""
    if isinstance(value, int):
        return value
    if not isinstance(value, str):
        raise TypeError(f"hex_to_int expects str|int, got {type(value)!r}")
    s = value.strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    if not s:
        raise ValueError("empty hex string")
    return int(s, 16)


def _normalize_path(_base_folder: str, rel_path: Path) -> Path:
    """兼容旧项目路径：尽量把相对路径解析到当前工程目录。"""
    # 以当前文件所在目录作为工程根（本项目 Tools.py 位于根目录）
    root = Path(__file__).resolve().parent

    candidates: List[Path] = []
    if rel_path.is_absolute():
        candidates.append(rel_path)
    else:
        candidates.append(root / rel_path)

        # 常见目录映射：历史上可能叫 comm/dll, 现在是 dll/
        parts = list(rel_path.parts)
        if len(parts) >= 2 and parts[0].lower() == "comm" and parts[1].lower() == "dll":
            candidates.append(root / Path("dll") / Path(*parts[2:]))

        # 兜底：直接在 dll/ 下找同名文件
        candidates.append(root / "dll" / rel_path.name)

    for p in candidates:
        if p.exists():
            return p
    # 允许调用方自行处理不存在的情况
    return candidates[0]


def get_dll_func_names(dll_path: Path) -> List[str]:
    """读取 DLL 导出函数名列表（纯 Python 解析 PE 导出表）。

    说明：仅用于获取导出符号名, 避免依赖额外第三方库。
    """
    import struct

    path = Path(dll_path)
    if not path.exists():
        raise FileNotFoundError(str(path))

    data = path.read_bytes()

    def u16(off: int) -> int:
        return struct.unpack_from("<H", data, off)[0]

    def u32(off: int) -> int:
        return struct.unpack_from("<I", data, off)[0]

    def read_cstr(off: int) -> str:
        end = data.find(b"\x00", off)
        if end == -1:
            end = len(data)
        return data[off:end].decode("ascii", errors="ignore")

    # DOS header
    if len(data) < 0x40 or data[0:2] != b"MZ":
        raise ValueError("Not a valid PE file (missing MZ)")
    e_lfanew = u32(0x3C)

    # NT headers
    if data[e_lfanew : e_lfanew + 4] != b"PE\x00\x00":
        raise ValueError("Not a valid PE file (missing PE signature)")
    file_header_off = e_lfanew + 4
    number_of_sections = u16(file_header_off + 2)
    size_of_optional_header = u16(file_header_off + 16)
    optional_header_off = file_header_off + 20
    sections_off = optional_header_off + size_of_optional_header

    magic = u16(optional_header_off)
    if magic == 0x10B:  # PE32
        data_dir_off = optional_header_off + 96
    elif magic == 0x20B:  # PE32+
        data_dir_off = optional_header_off + 112
    else:
        raise ValueError(f"Unknown PE optional header magic: {hex(magic)}")

    export_rva = u32(data_dir_off + 0)
    export_size = u32(data_dir_off + 4)
    if export_rva == 0 or export_size == 0:
        return []

    # Sections: map RVA -> file offset
    sections = []
    for i in range(number_of_sections):
        off = sections_off + i * 40
        virtual_size = u32(off + 8)
        virtual_address = u32(off + 12)
        size_of_raw_data = u32(off + 16)
        pointer_to_raw_data = u32(off + 20)
        sections.append(
            (virtual_address, max(virtual_size, size_of_raw_data), pointer_to_raw_data)
        )

    def rva_to_off(rva: int) -> int:
        for va, vsz, raw in sections:
            if va <= rva < va + vsz:
                return raw + (rva - va)
        raise ValueError(f"RVA {hex(rva)} not in any section")

    exp_off = rva_to_off(export_rva)
    if exp_off + 40 > len(data):
        return []

    # IMAGE_EXPORT_DIRECTORY
    number_of_names = u32(exp_off + 24)
    address_of_names_rva = u32(exp_off + 32)
    if number_of_names == 0 or address_of_names_rva == 0:
        return []

    names_off = rva_to_off(address_of_names_rva)
    names: List[str] = []
    for i in range(number_of_names):
        name_rva = u32(names_off + i * 4)
        try:
            name_off = rva_to_off(name_rva)
            n = read_cstr(name_off)
            if n:
                names.append(n)
        except Exception:
            continue

    return names


def change_json_value(file_name, key, new_value):
    """修改配置文件中的指定键值。支持点分隔的嵌套键"""
    config_folder = Path(__file__).parent / "config"
    file_path = config_folder / f"{file_name}.json"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    keys = key.split(".")
    d = data
    for k in keys[:-1]:
        if k not in d:
            d[k] = {}
        d = d[k]
    d[keys[-1]] = new_value

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def refresh_ui_config(
    selected_project, selected_duration, selected_operator, group_index: int = 1
):
    """刷新UI相关的全局配置变量（按组保存默认值）"""
    _update_grouped_ui_value("DefaultProject", int(group_index), selected_project)
    _update_grouped_ui_value("DefaultOperator", int(group_index), selected_operator)
    change_json_value(
        "ProjectConfig", f"{selected_project}.默认老化时长", selected_duration
    )
    refresh_configs()


def refresh_configs():
    """刷新全局配置变量"""
    global FUNCTION_CONFIG, PROJECT_CONFIG, SELECTED_PROJECT, COLOR_MAPPING
    FUNCTION_CONFIG = load_config("FuncConfig.json")
    PROJECT_CONFIG = load_config("ProjectConfig.json")
    SELECTED_PROJECT = get_default_project(1)
    COLOR_MAPPING = FUNCTION_CONFIG.get("UI", {}).get(
        "ColorMapping", FUNCTION_CONFIG.get("ColorMapping", {})
    )


# -------- Slot helpers (1-based indexing) --------


def validate_slot(slot: int, slot_count: int) -> int:
    """Ensure slot uses physical 1-based index within range."""
    if not isinstance(slot, int):
        raise TypeError("slot must be int")
    if slot < 1 or slot > int(slot_count):
        raise ValueError(f"slot must be in [1, {int(slot_count)}]")
    return slot


def create_slot_table(
    slot_count: int,
    default: Optional[object] = None,
    *,
    default_factory: Optional[Callable[[], object]] = None,
) -> list:
    """Create a 1-based slot table with a sentinel at index 0."""
    count = int(slot_count)
    if count < 1:
        raise ValueError("slot_count must be >=1")
    table = [None] * (count + 1)
    for slot in range(1, count + 1):
        table[slot] = default_factory() if default_factory else default
    return table


def set_slot_value(
    table: list, slot: int, value: object, slot_count: Optional[int] = None
) -> list:
    """Set value by physical slot index (1-based)."""
    count = int(slot_count) if slot_count is not None else len(table) - 1
    slot = validate_slot(int(slot), count)
    if slot >= len(table):
        raise ValueError("slot table is smaller than slot index")
    table[slot] = value
    return table


def get_slot_value(
    table: list, slot: int, slot_count: Optional[int] = None, default: object = None
):
    """Get value by physical slot index (1-based)."""
    count = int(slot_count) if slot_count is not None else len(table) - 1
    slot = validate_slot(int(slot), count)
    if slot >= len(table):
        return default
    return table[slot]


def normalize_slots(slots: Iterable[int], slot_count: int) -> list[int]:
    """Deduplicate + validate slots while keeping order (1-based)."""
    cleaned: list[int] = []
    for s in slots:
        slot = validate_slot(int(s), slot_count)
        if slot not in cleaned:
            cleaned.append(slot)
    return cleaned


def get_slot_results(app, slot):
    """获取指定槽位的card_status\custom_rx1\custom_rx2\diag_results\diag_periodic_snapshot结果的集合"""

    def _get_op(name: str):
        """兼容 ComponentsInstantiation 的 ops 映射或直接属性调用。"""
        if hasattr(app, "ops") and isinstance(getattr(app, "ops"), dict):
            func = getattr(app, "ops").get(name)
            if callable(func):
                return func
        if hasattr(app, name):
            func = getattr(app, name)
            if callable(func):
                return func
        return None

    status_fn = _get_op("get_status")
    diag_results_fn = _get_op("diag_results")
    diag_snapshot_fn = _get_op("diag_periodic_snapshot")
    dtc_snapshot_fn = _get_op("dtc_periodic_snapshot")

    card_status = status_fn("card_status", slot) if status_fn else None
    custom_rx1 = status_fn("custom_rx1", slot) if status_fn else None
    custom_rx2 = status_fn("custom_rx2", slot) if status_fn else None

    diag_results = diag_results_fn() if diag_results_fn else []
    diag_result_slot = diag_results[slot] if len(diag_results) > slot else None

    snapshot = diag_snapshot_fn() if diag_snapshot_fn else {}
    data_list = snapshot.get("data", []) if isinstance(snapshot, dict) else []
    diag_periodic_slot = data_list[slot] if len(data_list) > slot else None

    dtc_snapshot = dtc_snapshot_fn() if dtc_snapshot_fn else {}
    dtc_data_list = (
        dtc_snapshot.get("data", []) if isinstance(dtc_snapshot, dict) else []
    )
    dtc_codes = dtc_data_list[slot] if len(dtc_data_list) > slot else None

    return {
        "card_status": card_status,
        "custom_rx1": custom_rx1,
        "custom_rx2": custom_rx2,
        "diag_results": diag_result_slot,
        "diag_periodic_snapshot": diag_periodic_slot,
        "dtc_codes": dtc_codes,
    }


def get_slots_results(app, slots: int | list[int]) -> dict[int, dict]:
    """获取指定一个或若干个槽位的card_status\custom_rx1\custom_rx2\diag_results\diag_periodic_snapshot结果的集合"""
    slot_count = FUNCTION_CONFIG["UI"]["IndexPerGroup"]
    if isinstance(slots, int):
        slots = [slots]
    slots = normalize_slots(slots, slot_count)
    results = {}
    for slot in slots:
        results[slot] = get_slot_results(app, slot)
    return results


def get_all_slots_results(app):
    """获取所有槽位的card_status\custom_rx1\custom_rx2\diag_results\diag_periodic_snapshot结果的集合"""
    slot_count = FUNCTION_CONFIG["UI"]["IndexPerGroup"]
    results = {}
    for slot in range(1, slot_count + 1):
        results[slot] = get_slot_results(app, slot)
    return results


def get_active_slots(app) -> list[int]:
    """获取当前所有激活槽位列表,基于 card_status 中status状态判断,返回Status非0的槽位列表"""
    slot_count = FUNCTION_CONFIG["UI"]["IndexPerGroup"]
    status_fn = None
    if hasattr(app, "ops") and isinstance(getattr(app, "ops"), dict):
        status_fn = getattr(app, "ops").get("get_status")
    if not status_fn and hasattr(app, "get_status"):
        status_fn = getattr(app, "get_status")
    if not callable(status_fn):
        _log.warning("无法获取 get_status 方法, 无法判断激活槽位")
        return []

    active_slots: list[int] = []
    for slot in range(1, slot_count + 1):
        card_status = status_fn("card_status", slot)
        if isinstance(card_status, dict):
            status = card_status.get("Status", 0)
            if status not in (0, -4, -5):
                active_slots.append(slot)
    return active_slots


def set_card_output(
    bus: can.BusABC, status: bool, logger: Optional[logging.Logger] = None
):
    if logger is None:
        logger = _log
    msg_mapping = {True: b"\xff" * 8, False: b"\x00" * 8}
    ok = True
    for id in [1, 2]:
        msg = can.Message(
            arbitration_id=id,
            data=msg_mapping[status],
            is_extended_id=False,
            is_fd=True,
        )
        for _ in range(3):
            try:
                bus.send(msg)
            except Exception:
                ok = False
                logger.exception("Set Card Output Failed")
            time.sleep(0.06)
    logger.info("Set Card Output:%s", status)
    return ok


class PowerCycleController:
    """根据 ProjectConfig 中的周期上电配置，在后台线程中循环控制采集卡上电/下电。

    配置项:
        是否周期上电老化  (bool)  — 总开关
        带电老化/休眠老化时长 [power_on_min, sleep_min]  — 单位：分钟
    """

    def __init__(
        self,
        bus: can.BusABC,
        config: dict,
        logger: Optional[logging.Logger] = None,
    ):
        self._bus = bus
        self._config = config
        self._log = logger or _log
        self._stop_event = threading.Event()
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._powered_on = True  # 初始状态为已上电

        self.enabled = bool(config.get("是否周期上电老化", False))
        durations = config.get("带电老化/休眠老化时长", [10, 1])
        self.power_on_seconds = float(durations[0]) * 60 if len(durations) > 0 else 600
        self.sleep_seconds = float(durations[1]) * 60 if len(durations) > 1 else 60

    def start(self) -> None:
        """启动周期上电控制线程（仅在配置启用时生效）。"""
        if not self.enabled:
            self._log.info("周期上电老化未启用，跳过")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._paused = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="PowerCycle"
        )
        self._thread.start()
        self._log.info(
            "周期上电控制已启动: 带电%.1f分钟 / 休眠%.1f分钟",
            self.power_on_seconds / 60,
            self.sleep_seconds / 60,
        )

    def stop(self, timeout: float = 5.0) -> None:
        """停止周期上电控制，并确保采集卡回到上电状态。"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout)
        self._thread = None
        # 确保停止后恢复上电
        if not self._powered_on:
            self._power_on()
        self._log.info("周期上电控制已停止")

    def pause(self) -> None:
        """暂停周期控制（保持当前电源状态不变）。"""
        self._paused = True

    def resume(self) -> None:
        """恢复周期控制。"""
        self._paused = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_powered_on(self) -> bool:
        return self._powered_on

    def _power_on(self) -> None:
        """上电：调用 set_cards 同时配置采集卡地址。"""
        try:
            set_cards(self._bus, True, self._config, self._log)
            self._powered_on = True
            self._log.info("周期上电: 采集卡 ON")
        except Exception:
            self._log.exception("周期上电失败")

    def _power_off(self) -> None:
        """下电：仅关闭采集卡输出。"""
        try:
            set_card_output(self._bus, False, self._log)
            self._powered_on = False
            self._log.info("周期上电: 采集卡 OFF")
        except Exception:
            self._log.exception("周期下电失败")

    def _wait(self, seconds: float) -> bool:
        """等待指定秒数，期间可被停止事件打断。返回 True 表示正常结束，False 表示被打断。"""
        return not self._stop_event.wait(timeout=seconds)

    def _run(self) -> None:
        """后台线程主循环：带电 → 休眠 → 带电 → 休眠 ..."""
        while not self._stop_event.is_set():
            if self._paused:
                if not self._wait(0.5):
                    break
                continue

            # ---- 带电阶段 ----
            if not self._powered_on:
                self._power_on()
            if not self._wait(self.power_on_seconds):
                break

            if self._stop_event.is_set():
                break

            # ---- 休眠阶段 ----
            if not self._paused:
                self._power_off()
                if not self._wait(self.sleep_seconds):
                    break


def periodic_power_ctrl(bus: can.BusABC, config: dict) -> PowerCycleController:
    """创建并启动周期上电控制器。"""
    ctrl = PowerCycleController(bus, config)
    ctrl.start()
    return ctrl


def ass_raw_data(config_list: list) -> bytes:
    if not isinstance(config_list, list) or len(config_list) != 3:
        raise ValueError("config_list must be a list of three integers")

    values = []
    for v in config_list:
        if not isinstance(v, int):
            raise TypeError("config_list items must be int")
        if not (0 <= v <= 0xFFFF):
            raise ValueError("config_list items must be in [0, 0xFFFF]")
        values.append(v)

    payload = bytearray()
    payload.append(0xFF)
    for v in values:
        payload += v.to_bytes(2, "big")
    payload.append(0x00)
    return bytes(payload)


def set_card_addr(
    bus: can.BusABC, config: dict, logger: Optional[logging.Logger] = None
) -> bool:
    if logger is None:
        logger = _log
    phy_addrs = config["Diag"].get("DiagPhyAddr", [])
    tx_ids = [config["TX"]["IdOfTxMsg1"], config["TX"]["IdOfTxMsg2"]]
    rx_ids = [config["RX"]["IdOfRxMsg1"], config["RX"]["IdOfRxMsg2"]]
    mapping = {
        (3, 4): [phy_addrs[1] if len(phy_addrs) > 1 else None, rx_ids[0], rx_ids[1]],
        (5, 6): [phy_addrs[0] if len(phy_addrs) > 0 else None, tx_ids[0], tx_ids[1]],
    }
    for ids, addrs in mapping.items():
        addrs = [a if isinstance(a, int) and a is not None else 0x0000 for a in addrs]
        msg_1 = can.Message(
            arbitration_id=ids[0],
            data=ass_raw_data(addrs),
            is_extended_id=False,
            is_fd=True,
        )
        msg_2 = can.Message(
            arbitration_id=ids[1],
            data=ass_raw_data(addrs),
            is_extended_id=False,
            is_fd=True,
        )
        for _ in range(3):
            try:
                bus.send(msg_1)
                bus.send(msg_2)
                time.sleep(0.06)
            except Exception:
                logger.exception("Setting Cards Id Failed")
                return False
        logger.info(f"Setting Cards Id, Msg1:{msg_1}\n{' ' * 50}Msg2:{msg_2}")
    return True


def set_cards(
    bus: can.BusABC, status: bool, config: dict, logger: Optional[logging.Logger] = None
):
    set_card_output(bus, status, logger)
    if status:
        time.sleep(0.1)
        set_card_addr(bus, config, logger)


def remap_slot(slot: int) -> int:
    if not isinstance(slot, int):
        raise TypeError("slot must be int")
    if slot < 1 or slot > 80:
        raise ValueError("slot must be in [1, 80]")
    return slot + 1 if slot % 2 == 1 else slot - 1
