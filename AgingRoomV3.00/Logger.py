import sys
import logging
from pathlib import Path
from datetime import datetime
from typing import ClassVar, Optional, TextIO, TypeVar, overload, cast

"""
- 通过 mixin 提供 `self.log` / `cls.log` 访问统一的 logger
- 默认 logger 名: "{module}.{qualname}"
- 可选快速配置基础 logging（避免重复添加 handler）
"""

T = TypeVar("T", bound="LoggerMixin")


class _LoggerDescriptor:
    """
    同时支持 instance / class 访问的描述符：
        obj.log -> obj.__class__._get_logger()
        Cls.log -> Cls._get_logger()
    """

    @overload
    def __get__(self, obj: None, objtype: type[T]) -> logging.Logger: ...
    @overload
    def __get__(self, obj: T, objtype: type[T] | None = None) -> logging.Logger: ...

    def __get__(
        self,
        obj: T | None,
        objtype: type[T] | None = None,
    ) -> logging.Logger:
        if objtype is None:
            if obj is None:
                # 正常不会发生：类访问时 objtype 会被传入
                raise AttributeError("log must be accessed via instance or class")
            objtype = cast(type[T], type(obj))

        return objtype._get_logger()


class LoggerMixin:
    """Mixin：为实例/类提供统一 logger 入口。"""

    # 同时支持 self.log 与 MyClass.log
    log: ClassVar[logging.Logger] = cast(logging.Logger, _LoggerDescriptor())

    # 可按需覆盖:
    # LOG_NAME: Optional[str] = "my.custom.logger"
    # LOG_LEVEL: Optional[int] = logging.DEBUG
    LOG_NAME: Optional[str] = None
    LOG_LEVEL: Optional[int] = None

    @classmethod
    def _logger_name(cls) -> str:
        return cls.LOG_NAME or f"{cls.__module__}.{cls.__qualname__}"

    @classmethod
    def _get_logger(cls) -> logging.Logger:
        logger = logging.getLogger(cls._logger_name())
        if cls.LOG_LEVEL is not None:
            logger.setLevel(cls.LOG_LEVEL)
        return logger

    @classmethod
    def get_child_logger(cls, suffix: str) -> logging.Logger:
        """获取子 logger："{base}.{suffix}" """
        return cls._get_logger().getChild(suffix)


def configure_default_logging(
    *,
    level: int = logging.INFO,
    fmt: str = "%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    stream: Optional[TextIO] = None,
    # 新增：支持传入 log 保存路径 + 默认保存路径
    log_file: Optional[str] = None,
    default_log_file: Optional[str] = "logs/default_log_name.log",
    file_mode: str = "a",
    encoding: str = "utf-8",
) -> None:
    """
    为根 logger 提供默认 handler（避免重复添加）。

    - 默认添加 StreamHandler（stderr）
    - 若提供 log_file（或 default_log_file 不为 None）, 则额外添加 FileHandler
    """

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    # 1) StreamHandler：若已存在则不重复添加
    has_stream = any(isinstance(h, logging.StreamHandler) for h in root.handlers)
    if not has_stream:
        sh = logging.StreamHandler(stream or sys.stderr)
        sh.setLevel(level)
        sh.setFormatter(formatter)
        root.addHandler(sh)

    # 2) FileHandler：支持传入路径；否则使用默认路径（可关闭：default_log_file=None）
    if log_file:
        now_str = datetime.now().strftime("%Y%m%d")

        if log_file.endswith(".log"):
            log_file = log_file[:-4] + f"_{now_str}.log"
        else:
            log_file = log_file + f"_{now_str}"
    file_path = log_file if log_file is not None else default_log_file
    if file_path:
        p = Path(file_path).expanduser()
        if p.parent:
            p.parent.mkdir(parents=True, exist_ok=True)

        # 避免重复添加同一路径的 FileHandler
        target = str(p.resolve())
        has_file = any(
            isinstance(h, logging.FileHandler)
            and getattr(h, "baseFilename", None) == target
            for h in root.handlers
        )
        if not has_file:
            fh = logging.FileHandler(target, mode=file_mode, encoding=encoding)
            fh.setLevel(level)
            fh.setFormatter(formatter)
            root.addHandler(fh)


if __name__ == "__main__":
    # 测试 LoggerMixin 与默认配置
    from Tools import FUNCTION_CONFIG

    logging_level = getattr(
        logging, FUNCTION_CONFIG["Logging"]["LogLevel"], logging.INFO
    )

    configure_default_logging(
        level=logging_level, log_file=FUNCTION_CONFIG["Logging"]["LogPath"]
    )

    class MyClass(LoggerMixin):
        LOG_LEVEL = logging_level

        def do_something(self):
            self.log.debug("Doing something...")
            MyClass.log.info("Info from class logger.")

    obj = MyClass()
    obj.do_something()
    MyClass.log.warning("This is a class-level warning.")
