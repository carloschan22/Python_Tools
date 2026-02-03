from __future__ import annotations
import can
import time
import json
import logging
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
SELECTED_PROJECT = FUNCTION_CONFIG["UI"]["DefaultProject"]
logging_level = getattr(logging, FUNCTION_CONFIG["Logging"]["LogLevel"], logging.INFO)
logging_file = FUNCTION_CONFIG["Logging"]["LogPath"]
configure_default_logging(level=logging_level, log_file=logging_file)

_THIRD_PARTY_NOISE_LOGGERS = [
    "isotp",
    "can.kvaser",
    "can.zlg",
    "udsoncan",
    "UdsClient",
    "MultiSlotDiagnostic",
    "Diagnostic.MultiSlotDiagnostic",
    "Connection[NotifierBasedIsoTpConnection]",
]

for _logger_name in _THIRD_PARTY_NOISE_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


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


def refresh_ui_config(selected_project, selected_duration, selected_operator):
    """刷新UI相关的全局配置变量"""
    change_json_value("FuncConfig", "UI.DefaultProject", selected_project)
    change_json_value("FuncConfig", "UI.DefaultOperator", selected_operator)
    change_json_value(
        "ProjectConfig", f"{selected_project}.默认老化时长", selected_duration
    )
    refresh_configs()


def refresh_configs():
    """刷新全局配置变量"""
    global FUNCTION_CONFIG, PROJECT_CONFIG, SELECTED_PROJECT, COLOR_MAPPING
    FUNCTION_CONFIG = load_config("FuncConfig.json")
    PROJECT_CONFIG = load_config("ProjectConfig.json")
    SELECTED_PROJECT = FUNCTION_CONFIG["UI"]["DefaultProject"]
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

    card_status = status_fn("card_status", slot) if status_fn else None
    custom_rx1 = status_fn("custom_rx1", slot) if status_fn else None
    custom_rx2 = status_fn("custom_rx2", slot) if status_fn else None

    diag_results = diag_results_fn() if diag_results_fn else []
    diag_result_slot = diag_results[slot] if len(diag_results) > slot else None

    snapshot = diag_snapshot_fn() if diag_snapshot_fn else {}
    data_list = snapshot.get("data", []) if isinstance(snapshot, dict) else []
    diag_periodic_slot = data_list[slot] if len(data_list) > slot else None

    return {
        "card_status": card_status,
        "custom_rx1": custom_rx1,
        "custom_rx2": custom_rx2,
        "diag_results": diag_result_slot,
        "diag_periodic_snapshot": diag_periodic_slot,
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
) -> bool:
    if logger is None:
        logger = _log
    msg_mapping = {True: b"\xff" * 8, False: b"\x00" * 8}
    for id in [1, 2]:
        msg = can.Message(
            arbitration_id=id,
            data=msg_mapping[status],
            is_extended_id=False,
            is_fd=True,
        )
        for _ in range(3):
            result = bus.send(msg)
            if logger:
                logger.info("Set Output:%s", status)
            if not result:
                return False
    return True


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
        if logger:
            logger.info(f"Setting Cards Id, Msg1:{msg_1}\n{' ' * 50}Msg2:{msg_2}")
        for _ in range(3):
            bus.send(msg_1)
            bus.send(msg_2)
            time.sleep(0.1)


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
