from pathlib import Path
from typing import Optional
import json

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
    """
    加载配置文件

    Args:
        config_file: 配置文件相对路径（默认为 config/diag_config.json）

    Returns:
        加载的配置字典
    """
    config_path = _normalize_path("config", Path(config_file))

    if not config_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    return config


if __name__ == "__main__":

    try:
        config = load_config()
        print(f"配置加载成功: {config}")
    except FileNotFoundError as e:
        print(f"配置加载失败: {e}")
