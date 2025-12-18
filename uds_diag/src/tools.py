from pathlib import Path
from typing import Optional
import json
import pefile

_runtime_root = Path(__file__).resolve().parent.parent


def _normalize_path(path_type: str, path: Optional[Path] = None) -> Path:
    # 布局运行时文件夹结构。
    if path:
        # 如果日志路径是相对路径，则与root连接。
        if not path.is_absolute():
            path = _runtime_root / path
    else:
        path = _runtime_root / path_type
    return path


def load_config(config_file: str = "config/diag_config.json") -> dict:
    config_path = _normalize_path("config", Path(config_file))

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


def get_dll_func_names(dll_path: str) -> list:
    func_names = []

    if not dll_path.exists():
        raise FileNotFoundError(f"DLL文件不存在: {dll_path}")

    pe = pefile.PE(str(dll_path))
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            name = exp.name.decode() if exp.name else f"Ordinal: {exp.ordinal}"
            func_names.append(name)

    return func_names


def hex_to_int(hex_string: str) -> int:
    if not isinstance(hex_string, str):
        raise TypeError("hex_string 必须是字符串")

    s = hex_string.strip().replace("_", "").replace(" ", "")
    if s.lower().startswith("0x"):
        s = s[2:]
    if s == "":
        raise ValueError("空的十六进制字符串")
    return int(s, 16)


if __name__ == "__main__":

    try:
        config = load_config()
        print(f"配置加载成功: {config}")
    except FileNotFoundError as e:
        print(f"配置加载失败: {e}")

    dll_path = _normalize_path("dll", Path(f"dll/Q5030_SeedKey_x64.dll"))
    dll_func_names = get_dll_func_names(dll_path)
    print(f"DLL函数列表: {dll_func_names}")

    hex_string = "0xEE04"
    value = hex_to_int(hex_string)
    print(f"十六进制字符串 '{hex_string}' 转换为整数: {hex(value)} ({value})")
