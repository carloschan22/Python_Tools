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
    print(f"{path_type.capitalize()}路径: {path}")
    return path


def load_config(config_file: str = "config/diag_config.json") -> dict:
    config_path = _normalize_path("config", Path(config_file))

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


def get_dll_func_names(dll_name: str) -> list:
    dll_path = _normalize_path("dll", Path(f"dll/{dll_name}.dll"))
    func_names = []

    if not dll_path.exists():
        raise FileNotFoundError(f"DLL文件不存在: {dll_path}")

    pe = pefile.PE(str(dll_path))
    if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
        for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
            name = exp.name.decode() if exp.name else f"Ordinal: {exp.ordinal}"
            func_names.append(name)

    return func_names


if __name__ == "__main__":

    try:
        config = load_config()
        print(f"配置加载成功: {config}")
    except FileNotFoundError as e:
        print(f"配置加载失败: {e}")

    dll_func_names = get_dll_func_names("Q5030_SeedKey_x64")
    print(f"DLL函数列表: {dll_func_names}")
