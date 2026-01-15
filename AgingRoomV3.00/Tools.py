import json
import logging
from pathlib import Path
from Logger import configure_default_logging
from typing import Iterable, List, Union

_log = logging.getLogger(__name__)


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

        # 常见目录映射：历史上可能叫 comm/dll，现在是 dll/
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

    说明：仅用于获取导出符号名，避免依赖额外第三方库。
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


def load_config(file_name) -> dict:
    """加载配置文件"""
    config_folder = Path(__file__).parent / "config"
    with open(config_folder / file_name, "r", encoding="utf-8") as f:
        return json.load(f)
    raise FileNotFoundError(f"配置文件未找到: {file_name}")


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


FUNCTION_CONFIG = load_config("FuncConfig.json")
PROJECT_CONFIG = load_config("ProjectConfig.json")
SELECTED_PROJECT = FUNCTION_CONFIG["UI"]["DefaultProject"]
logging_level = getattr(logging, FUNCTION_CONFIG["Logging"]["LogLevel"], logging.INFO)
logging_file = FUNCTION_CONFIG["Logging"]["LogPath"]
configure_default_logging(level=logging_level, log_file=logging_file)

# 第三方库日志降噪：isotp 在 DEBUG 下会打印大量 Rx/Tx trace
# 不影响业务 logger（你的 self.log.* 仍遵循 FUNCTION_CONFIG["Logging"]["LogLevel"]）

# NOTE:
# - udsoncan 默认使用名为 "UdsClient" 与 "Connection[<name>]" 的 logger
# - isotp/udsoncan 都可能在 DEBUG 下刷屏；降到 WARNING 可以保留异常但不打印调试细节
_THIRD_PARTY_NOISE_LOGGERS = [
    "isotp",
    "can.kvaser",
    "udsoncan",
    "UdsClient",
    "Connection[NotifierBasedIsoTpConnection]",
]

for _logger_name in _THIRD_PARTY_NOISE_LOGGERS:
    logging.getLogger(_logger_name).setLevel(logging.WARNING)


def refresh_configs():
    """刷新全局配置变量"""
    global FUNCTION_CONFIG, PROJECT_CONFIG, SELECTED_PROJECT
    FUNCTION_CONFIG = load_config("FuncConfig.json")
    PROJECT_CONFIG = load_config("ProjectConfig.json")
    SELECTED_PROJECT = FUNCTION_CONFIG["UI"]["DefaultProject"]


if __name__ == "__main__":

    print(PROJECT_CONFIG["Q5030"]["默认老化时长"])
    value = "IdOfTxMsg1"
    change_json_value("ProjectConfig", f"Q5030.{value}", 4)
    refresh_configs()

    print(PROJECT_CONFIG["Q5030"]["默认老化时长"])
