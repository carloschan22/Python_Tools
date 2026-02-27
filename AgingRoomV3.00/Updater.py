from __future__ import annotations
import os
import time
import zlib
from pathlib import Path
from abc import ABC, abstractmethod
from typing import Any, Optional
from datetime import datetime


from Logger import LoggerMixin

from udsoncan.client import Client
from udsoncan import MemoryLocation, DataFormatIdentifier


# ────────────────────────────────────────────────────────────────────
#  OTA 基类 — 标准 UDS 协议 OTA 通用逻辑
# ────────────────────────────────────────────────────────────────────


class OTA(LoggerMixin, ABC):
    """UDS 标准 OTA 升级基础类

    封装了通用的刷写辅助能力：
    - Intel HEX 文件解析
    - CRC-32 镜像校验
    - 擦除区域参数自动推算（根据 HEX 地址 / 大小 + 扇区对齐）
    - 编程指纹（DID 0xF15A）自动生成
    - UDS 文件下载流程（RequestDownload → TransferData → TransferExit）
    - 步骤结果校验 & 自动重试
    """

    # ── 子类可覆盖的默认参数 ──
    CHUNK_SIZE: int = 0x400  # TransferData 每包大小 (1024 B)
    FILL_BYTE: int = 0xAA  # 数据 4 字节对齐时的填充值
    ADDRESS_FORMAT: int = 32  # MemoryLocation 地址位宽
    MEMORYSIZE_FORMAT: int = 32  # MemoryLocation 长度位宽
    MAX_RETRIES: int = 3  # 关键步骤最大重试次数
    ERASE_MEMORY_ID: int = 0x44  # RoutineControl 擦除时使用的存储类型标识
    FLASH_SECTOR_SIZE: int = 0x2000  # Flash 扇区大小（8 KB），用于地址 / 大小对齐

    def __init__(self, client: Client = None, ota_cfg: dict = None):
        self.client = client
        self.ota_cfg = ota_cfg or {}
        self.log.info("OTA base class initialized")

    @abstractmethod
    def start_update(self, *args, **kwargs) -> dict:
        """启动一次 OTA 更新，返回结果字典"""
        raise NotImplementedError

    # ──────────────── Intel HEX 解析 ──────────────── #

    @staticmethod
    def _parse_intel_hex(file_path: str) -> list[tuple[int, bytes]]:
        """解析 Intel HEX 文件并合并连续地址段。

        Returns:
            已按地址排序、连续区间已合并的 ``[(start_address, data_bytes)]`` 列表。
        """
        records: list[tuple[int, bytes]] = []
        extended_addr = 0

        with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or not line.startswith(":"):
                    continue
                byte_count = int(line[1:3], 16)
                address = int(line[3:7], 16)
                rec_type = int(line[7:9], 16)
                data = bytes.fromhex(line[9 : 9 + byte_count * 2])

                if rec_type == 0x00:  # Data record
                    records.append((extended_addr + address, data))
                elif rec_type == 0x04 and byte_count == 2:  # Extended Linear Address
                    extended_addr = int.from_bytes(data, "big") << 16
                elif rec_type == 0x02 and byte_count == 2:  # Extended Segment Address
                    extended_addr = int.from_bytes(data, "big") << 4
                elif rec_type == 0x01:  # EOF
                    break

        if not records:
            return []

        records.sort(key=lambda r: r[0])

        # 合并连续段
        segments: list[tuple[int, bytes]] = []
        seg_start, seg_buf = records[0][0], bytearray(records[0][1])
        next_addr = seg_start + len(records[0][1])

        for addr, data in records[1:]:
            if addr == next_addr:
                seg_buf.extend(data)
            else:
                segments.append((seg_start, bytes(seg_buf)))
                seg_start, seg_buf = addr, bytearray(data)
            next_addr = addr + len(data)

        segments.append((seg_start, bytes(seg_buf)))
        return segments

    # ──────────────── CRC-32 校验 ──────────────── #

    @staticmethod
    def _crc32(data: bytes) -> int:
        return zlib.crc32(data) & 0xFFFFFFFF

    @classmethod
    def compute_hex_crc(cls, file_path: str, fill: int = 0xFF) -> str:
        """计算 HEX 文件全镜像 CRC-32。

        Returns:
            空格分隔的 4 字节十六进制字符串，如 ``"ab cd ef 01"``。
        """
        segments = cls._parse_intel_hex(file_path)
        if not segments:
            raise ValueError(f"HEX 文件无有效数据段: {file_path}")

        min_addr = segments[0][0]
        max_addr = max(a + len(d) - 1 for a, d in segments)

        # 用字典快速填充后转连续 bytearray
        image: dict[int, int] = {}
        for addr, data in segments:
            for off, b in enumerate(data):
                image[addr + off] = b

        contiguous = bytearray(
            image.get(a, fill) for a in range(min_addr, max_addr + 1)
        )
        crc = cls._crc32(bytes(contiguous))
        return crc.to_bytes(4, "big").hex(" ")

    # ──────────────── HEX 文件搜索 ──────────────── #

    @staticmethod
    def _find_hex_file(
        name: str,
        search_dirs: Optional[list] = None,
    ) -> str:
        """在指定目录列表（默认 ``ota/`` 和项目根目录）中查找 HEX 文件。

        支持：
        - 精确文件名匹配
        - 自动追加 ``.hex`` 后缀
        - 基于基础名的模糊匹配
        """
        if search_dirs is None:
            project_root = Path(__file__).resolve().parent
            search_dirs = [project_root / "ota", project_root]

        candidates = [name]
        if not name.lower().endswith(".hex"):
            candidates.append(name + ".hex")

        for search_dir in search_dirs:
            search_dir = Path(search_dir)
            if not search_dir.exists():
                continue
            for root, _, files in os.walk(search_dir):
                # 精确匹配
                for c in candidates:
                    if c in files:
                        return os.path.join(root, c)
                # 模糊匹配：文件名含目标基础名
                for f in files:
                    if not f.lower().endswith(".hex"):
                        continue
                    for c in candidates:
                        base = c.replace(".hex", "")
                        if base and base in f:
                            return os.path.join(root, f)

        raise FileNotFoundError(f"未找到 HEX 文件: {name}")

    # ──────────────── 擦除区域自动推算 ──────────────── #

    @classmethod
    def _compute_erase_params(
        cls,
        hex_path: str,
        sector_size: Optional[int] = None,
        memory_id: Optional[int] = None,
    ) -> bytes:
        """根据 HEX 文件数据区间自动推算 RoutineControl(0xFF00) 所需的擦除参数。

        返回 9 字节: ``memory_id(1) + start_address(4, big-endian) + erase_size(4, big-endian)``

        地址和大小均对齐到 Flash 扇区边界（向外扩展）。
        """
        if sector_size is None:
            sector_size = cls.FLASH_SECTOR_SIZE
        if memory_id is None:
            memory_id = cls.ERASE_MEMORY_ID

        segments = cls._parse_intel_hex(hex_path)
        if not segments:
            raise ValueError(f"HEX 文件无有效数据段: {hex_path}")

        min_addr = segments[0][0]
        max_addr = max(a + len(d) for a, d in segments)

        aligned_start = (min_addr // sector_size) * sector_size
        aligned_end = ((max_addr + sector_size - 1) // sector_size) * sector_size
        erase_size = aligned_end - aligned_start

        return (
            bytes([memory_id])
            + aligned_start.to_bytes(4, "big")
            + erase_size.to_bytes(4, "big")
        )

    # ──────────────── 编程指纹自动生成 ──────────────── #

    @staticmethod
    def _build_fingerprint(tester_id: Optional[bytes] = None) -> bytes:
        """自动生成 UDS 编程指纹（DID 0xF15A, 21 字节）。

        结构（与参考实现 ``06 0A 0B 0C 01 02 ... 06`` 兼容）::

            year(1) + tester_serial(9) + 0x00 + tester_serial(9) + year(1)

        - ``year`` = 当前年份后两位（十六进制表示，如 2026 → 0x1A）
        - ``tester_serial`` 默认 ``0A 0B 0C 01 02 03 04 05 06``
        """
        year_byte = datetime.now().year % 100  # 2026 → 26 → 0x1A

        if tester_id is None:
            tester_id = bytes([0x0A, 0x0B, 0x0C, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06])

        # 确保 9 字节
        if len(tester_id) < 9:
            tester_id = tester_id + bytes(9 - len(tester_id))
        else:
            tester_id = tester_id[:9]

        return bytes([year_byte]) + tester_id + b"\x00" + tester_id + bytes([year_byte])

    # ──────────────── UDS 文件下载 ──────────────── #

    def _download_file(self, client: Client, hex_path: str, **kwargs) -> bool:
        """执行 UDS 刷写下载流程。

        对 HEX 文件中每段数据依次执行:
        RequestDownload → TransferData（分包） → RequestTransferExit

        内部对每步均有独立重试机制。
        """
        chunk_size = kwargs.get("chunk_size", self.CHUNK_SIZE)
        fill_byte = kwargs.get("fill_byte", self.FILL_BYTE)
        addr_fmt = kwargs.get("address_format", self.ADDRESS_FORMAT)
        memsize_fmt = kwargs.get("memorysize_format", self.MEMORYSIZE_FORMAT)

        segments = self._parse_intel_hex(hex_path)
        if not segments:
            raise RuntimeError(f"文件 {hex_path} 不包含可用的数据段")

        file_label = Path(hex_path).name
        self.log.info(f"开始下载 {file_label}，共 {len(segments)} 段")

        for seg_idx, (seg_addr, seg_data) in enumerate(segments, 1):
            payload = bytearray(seg_data)
            pad = (-len(payload)) % 4
            if pad:
                payload.extend([fill_byte] * pad)

            mem_loc = MemoryLocation(
                address=seg_addr,
                memorysize=len(payload),
                address_format=addr_fmt,
                memorysize_format=memsize_fmt,
            )
            dfi = DataFormatIdentifier(compression=0x0, encryption=0x0)

            self.log.info(f"段 {seg_idx}: 0x{seg_addr:08X}, {len(payload)} B")

            # ── RequestDownload (retry) ──
            self._retry(
                f"RequestDownload (段{seg_idx})",
                lambda: client.request_download(memory_location=mem_loc, dfi=dfi),
            )

            # ── TransferData (per-chunk retry) ──
            seq_num = 1
            for offset in range(0, len(payload), chunk_size):
                chunk = bytes(payload[offset : offset + chunk_size])
                _seq = seq_num  # 闭包捕获
                self._retry(
                    f"TransferData (段{seg_idx}, seq 0x{_seq:02X})",
                    lambda _c=chunk, _s=_seq: client.transfer_data(_s, _c),
                    delay=0.3,
                )
                seq_num = (seq_num + 1) & 0xFF

            # ── RequestTransferExit (retry) ──
            self._retry(
                f"TransferExit (段{seg_idx})",
                lambda: client.request_transfer_exit(),
            )

        self.log.info(f"{file_label} 下载完成")
        return True

    # ──────────────── 步骤校验 & 重试 ──────────────── #

    def _validate_step_result(self, step_name: str, response: Any) -> Any:
        """验证 UDS 步骤响应；失败则抛出 ``RuntimeError``。"""
        if isinstance(response, bool):
            if not response:
                raise RuntimeError(f"{step_name} 返回 False")
            return response

        if hasattr(response, "positive") and not response.positive:
            code_name = getattr(response, "code_name", None)
            if not code_name:
                sd = getattr(response, "service_data", None)
                code_name = getattr(sd, "code_name", None) if sd else None
            # 通信控制 ConditionsNotCorrect 可以跳过
            if (
                step_name == "禁止收发应用报文和网管报文"
                and code_name == "ConditionsNotCorrect"
            ):
                self.log.info("通信控制返回 ConditionsNotCorrect, 跳过")
                return {"status": "Skipped", "reason": code_name}
            raise RuntimeError(
                f"{step_name} 负响应{f' ({code_name})' if code_name else ''}"
            )
        return response

    def _retry(
        self,
        step_name: str,
        func,
        max_retries: Optional[int] = None,
        delay: float = 0.5,
    ) -> Any:
        """通用重试包装器。"""
        if max_retries is None:
            max_retries = self.MAX_RETRIES
        last_err: Optional[Exception] = None
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self.log.warning(f"{step_name} 重试第 {attempt + 1} 次")
                    time.sleep(delay)
                response = func()
                return self._validate_step_result(step_name, response)
            except Exception as exc:
                last_err = exc
                if attempt < max_retries - 1:
                    self.log.warning(f"{step_name} 异常: {exc}，准备重试")
                    continue
                raise RuntimeError(
                    f"{step_name} 失败 (已重试 {max_retries} 次): {exc}"
                ) from last_err


# ────────────────────────────────────────────────────────────────────
#  OTAType01 — Q5030 系列标准 UDS 刷写实现
# ────────────────────────────────────────────────────────────────────


class OTAType01(OTA):
    """Q5030 系列采集卡标准 UDS OTA 升级实现。

    自动完成以下参数推算，无需在配置文件中手动指定：
    - **擦除区域** — 从 BOOT / APP 的 HEX 文件地址范围自动计算，Flash 扇区对齐
    - **CRC 校验值** — 从 HEX 全镜像 CRC-32 自动计算
    - **编程指纹** — 根据当前日期自动生成 21 字节 DID 0xF15A 数据

    最终配置仅需在 ``ProjectConfig.json`` 中声明::

        "SupportedComponents": ["OTA", ...],
        "Diag": {
            "OTA": {
                "FlashDriver": "Driver.hex",
                "Boot": "Q5030_BOOT_V000F-20251013",
                "APP": "Q5030_APP_V0020-20251013"
            }
        }

    完整刷写序列::

        默认会话 → 扩展会话 → 编程预条件检查
        → 关闭 DTC → 禁止通信 → 编程会话 → 安全访问
        → FlashDriver 下载 & CRC → 写入指纹
        → 擦除 BOOT → BOOT 下载 & CRC → 激活新 BOOT
        → FlashDriver 再下载 & CRC
        → 擦除 APP → APP 下载 & CRC
        → 编程依赖性检查 → ECU 重置 → 版本信息读取
    """

    def __init__(self, client: Client = None, ota_cfg: dict = None):
        super().__init__(client, ota_cfg)
        # 缓存：避免同一文件重复解析 / 计算
        self._path_cache: dict[str, str] = {}
        self._crc_cache: dict[str, str] = {}
        self._erase_cache: dict[str, bytes] = {}
        self.log.info("OTAType01 initialized")

    # ──── 带缓存的参数解析 ──── #

    def _resolve_hex_path(self, name: str) -> str:
        if name not in self._path_cache:
            self._path_cache[name] = self._find_hex_file(name)
            self.log.info(f"解析 HEX 路径: {name} → {self._path_cache[name]}")
        return self._path_cache[name]

    def _get_crc_bytes(self, name: str) -> bytes:
        """返回 4 字节 CRC（bytes），用于 RoutineControl 0xF001。"""
        path = self._resolve_hex_path(name)
        if path not in self._crc_cache:
            self._crc_cache[path] = self.compute_hex_crc(path)
            self.log.info(f"CRC ({Path(path).name}): {self._crc_cache[path]}")
        return bytes.fromhex(self._crc_cache[path])

    def _get_erase_bytes(self, name: str) -> bytes:
        """返回 9 字节擦除参数（bytes），用于 RoutineControl 0xFF00。"""
        path = self._resolve_hex_path(name)
        if path not in self._erase_cache:
            self._erase_cache[path] = self._compute_erase_params(path)
            self.log.info(
                f"擦除参数 ({Path(path).name}): {self._erase_cache[path].hex(' ')}"
            )
        return self._erase_cache[path]

    def clear_cache(self) -> None:
        """清除所有缓存（如需重新计算时调用）。"""
        self._path_cache.clear()
        self._crc_cache.clear()
        self._erase_cache.clear()

    # ──── 核心升级入口 ──── #

    def start_update(
        self,
        client: Client = None,
        ota_cfg: Optional[dict] = None,
    ) -> dict:
        """执行完整 UDS OTA 升级流程。

        Args:
            client:  ``udsoncan.Client`` 实例（已处于打开状态）。
                     若为 ``None`` 则使用构造时传入的实例。
            ota_cfg: OTA 配置字典，至少包含::

                         {"FlashDriver": "xx.hex", "Boot": "xx", "APP": "xx"}

                     若为 ``None`` 则使用构造时传入的配置。

        Returns:
            结果字典，必含 ``"刷写状态"`` 键（``"成功"`` / ``"失败"``）。
        """
        client = client or self.client
        ota_cfg = ota_cfg or self.ota_cfg
        if client is None:
            raise ValueError("未提供 UDS Client 实例")
        if not ota_cfg:
            raise ValueError("未提供 OTA 配置 (FlashDriver / Boot / APP)")

        driver_name = ota_cfg.get("FlashDriver")
        boot_name = ota_cfg.get("Boot")
        app_name = ota_cfg.get("APP")
        if not all([driver_name, boot_name, app_name]):
            raise ValueError(
                f"OTA 配置不完整 (需要 FlashDriver / Boot / APP): {ota_cfg}"
            )

        # ── 预解析所有文件 & 计算参数 ──
        driver_path = self._resolve_hex_path(driver_name)
        boot_path = self._resolve_hex_path(boot_name)
        app_path = self._resolve_hex_path(app_name)

        driver_crc = self._get_crc_bytes(driver_name)
        boot_crc = self._get_crc_bytes(boot_name)
        app_crc = self._get_crc_bytes(app_name)

        erase_boot = self._get_erase_bytes(boot_name)
        erase_app = self._get_erase_bytes(app_name)
        fingerprint = self._build_fingerprint()

        self.log.info(
            f"OTA 参数就绪: Driver={Path(driver_path).name}, "
            f"Boot={Path(boot_path).name}, APP={Path(app_path).name}"
        )
        self.log.info(f"  擦除 BOOT: {erase_boot.hex(' ')}")
        self.log.info(f"  擦除 APP : {erase_app.hex(' ')}")
        self.log.info(f"  指纹     : {fingerprint.hex(' ')}")

        # ── 定义完整 UDS 刷写步骤序列 ──
        diag_steps: dict[str, Any] = {
            "进入默认会话_1": lambda: client.change_session(1),
            "进入扩展会话": lambda: client.change_session(3),
            # "读取当前会话_1": lambda: client.read_data_by_identifier(0xF186),
            "检查编程预条件": lambda: client.routine_control(
                routine_id=0xFF02, control_type=0x01, data=None
            ),
            "关闭DTC": lambda: client.control_dtc_setting(setting_type=0x02),
            "禁止收发应用报文和网管报文": lambda: client.communication_control(
                control_type=0x03, communication_type=0x03
            ),
            "进入编程会话": lambda: client.change_session(2),
            # "读取当前会话_2": lambda: client.read_data_by_identifier(0xF186),
            "安全访问": lambda: client.unlock_security_access(level=9),
            # ── FlashDriver (第一次) ──
            "下载FlashDriver": lambda: self._download_file(client, driver_path),
            "CRC校验FlashDriver": lambda: client.routine_control(
                routine_id=0xF001, control_type=0x01, data=driver_crc
            ),
            # ── BOOT ──
            "写入指纹信息": lambda: client.write_data_by_identifier(
                did=0xF15A, value=fingerprint
            ),
            # "读取当前会话_3": lambda: client.read_data_by_identifier(0xF186),
            "擦除BOOT存储区": lambda: client.routine_control(
                routine_id=0xFF00, control_type=0x01, data=erase_boot
            ),
            "下载BOOT程序": lambda: self._download_file(client, boot_path),
            "CRC校验BOOT": lambda: client.routine_control(
                routine_id=0xF001, control_type=0x01, data=boot_crc
            ),
            "激活新BOOT": lambda: client.routine_control(
                routine_id=0xFF04, control_type=0x01, data=None
            ),
            # ── FlashDriver (第二次 — 新 BOOT 启动后需要重新加载) ──
            "下载FlashDriver_2": lambda: self._download_file(client, driver_path),
            "CRC校验FlashDriver_2": lambda: client.routine_control(
                routine_id=0xF001, control_type=0x01, data=driver_crc
            ),
            # ── APP ──
            "擦除APP存储区": lambda: client.routine_control(
                routine_id=0xFF00, control_type=0x01, data=erase_app
            ),
            "下载APP程序": lambda: self._download_file(client, app_path),
            "CRC校验APP": lambda: client.routine_control(
                routine_id=0xF001, control_type=0x01, data=app_crc
            ),
            # ── 收尾 ──
            "检查编程依赖性": lambda: client.routine_control(
                routine_id=0xFF01, control_type=0x01, data=None
            ),
            "ECU重置": lambda: client.ecu_reset(reset_type=0x01),
            "延时": lambda: time.sleep(1),
            # "读取当前会话_4": lambda: client.read_data_by_identifier(0xF186),
            "进入默认会话_2": lambda: client.change_session(1),
            # "读取当前会话_5": lambda: client.read_data_by_identifier(0xF186),
            "读取ECU硬件版本号": lambda: client.read_data_by_identifier(0xF193),
            "读取ECU软件版本号": lambda: client.read_data_by_identifier(0xFD00),
            "读取车辆识别号": lambda: client.read_data_by_identifier(0xF190),
        }

        # 步骤重试策略分类
        _RETRY_STEPS = {
            "进入默认会话_1",
            "进入扩展会话",
            "检查编程预条件",
            "关闭DTC",
            "禁止收发应用报文和网管报文",
            "进入编程会话",
            "安全访问",
            "CRC校验FlashDriver",
            "写入指纹信息",
            "擦除BOOT存储区",
            "CRC校验BOOT",
            "激活新BOOT",
            "CRC校验FlashDriver_2",
            "擦除APP存储区",
            "CRC校验APP",
            "检查编程依赖性",
            "ECU重置",
            "进入默认会话_2",
        }
        _NO_RETRY_STEPS = {
            "下载FlashDriver",
            "下载FlashDriver_2",
            "下载BOOT程序",
            "下载APP程序",
            "延时",
        }

        result: dict[str, Any] = {}

        for step_name, step_func in diag_steps.items():
            self.log.info(f"▶ 执行: {step_name}")

            # 确定重试次数
            if step_name in _NO_RETRY_STEPS:
                max_retries = 1
            elif step_name in _RETRY_STEPS:
                max_retries = self.MAX_RETRIES
            elif step_name.startswith("读取"):
                max_retries = 2
            else:
                max_retries = 1

            for attempt in range(max_retries):
                try:
                    if attempt > 0:
                        self.log.warning(f"{step_name} 重试第 {attempt + 1} 次")
                        time.sleep(0.5)

                    response = step_func()
                    response = self._validate_step_result(step_name, response)
                    result[step_name] = response

                    # 日志记录响应
                    resp_hex = (
                        response.data.hex()
                        if hasattr(response, "data")
                        else str(response)
                    )
                    self.log.info(f"  ✓ {step_name} → {resp_hex}")

                    # CRC 校验结果判断
                    if isinstance(resp_hex, str) and "01f001" in resp_hex:
                        cleaned = resp_hex.replace(" ", "").lower()
                        if cleaned[-2:] == "00":
                            self.log.info(f"  CRC 校验成功")
                            result[step_name] = "CRC校验成功"
                        else:
                            self.log.warning(f"  CRC 校验失败: {resp_hex}")
                            result[step_name] = "CRC校验失败"
                            if attempt < max_retries - 1:
                                continue
                    break

                except Exception as exc:
                    self.log.error(f"  ✗ {step_name} 异常: {exc}")
                    if attempt < max_retries - 1:
                        continue
                    # 最终失败
                    result["刷写状态"] = "失败"
                    result["失败步骤"] = step_name
                    result["错误信息"] = str(exc)
                    return result

        # ── 汇总 ──
        if "CRC校验失败" in result.values():
            result["刷写状态"] = "失败"
            self.log.error("OTA 升级失败: CRC 校验未通过")
        else:
            result["刷写状态"] = "成功"
            self.log.info("OTA 升级流程全部完成 ✓")

        return result


# ────────────────────────────────────────────────────────────────────
#  示范代码
# ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    """
    本示例展示如何在 AgingRoomV3.00 项目中调用 OTAType01 完成一次 UDS OTA 升级。

    前置条件:
    1. ota/ 目录下已放置:
       - Q5030_Driver.hex    (FlashDriver)
       - Q5030_BOOT_V000F-20251013.hex  (BOOT)
       - Q5030_APP_V0020-20251013.hex   (APP)
    2. config/ProjectConfig.json 中对应项目已配置:
       "SupportedComponents": ["OTA", ...],
       "Diag": {
           "OTA": {
               "FlashDriver": "Q5030_Driver.hex",
               "Boot":        "Q5030_BOOT_V000F-20251013",
               "APP":         "Q5030_APP_V0020-20251013"
           }
       }
    3. 硬件已就绪: 采集卡上电、CAN 总线已连接、ZLG CAN 适配器已插入。
    """

    import json
    import logging
    from Logger import configure_default_logging

    # ── 1. 配置日志 ──
    configure_default_logging(
        level=logging.DEBUG,
        log_file="logs/ota_demo.log",
    )
    logger = logging.getLogger("OTA_Demo")

    # ── 2. 加载项目配置 ──
    config_path = Path(__file__).resolve().parent / "config" / "ProjectConfig.json"
    with open(config_path, "r", encoding="utf-8") as f:
        project_config = json.load(f)

    project_name = "Q5030"
    project_cfg = project_config[project_name]
    ota_cfg = project_cfg["Diag"]["OTA"]

    logger.info(f"项目: {project_name}")
    logger.info(f"OTA 配置: {ota_cfg}")

    # ── 3. 无需真实硬件: 离线验证自动计算的参数 ──
    logger.info("=" * 60)
    logger.info("离线参数验证 (无需 CAN 硬件)")
    logger.info("=" * 60)

    updater = OTAType01()

    # 验证 HEX 文件搜索
    for label, name in ota_cfg.items():
        try:
            hex_path = updater._resolve_hex_path(name)
            logger.info(f"  {label}: {name} → {hex_path}")
        except FileNotFoundError as e:
            logger.warning(f"  {label}: {e}")

    # 验证 CRC 自动计算
    for label in ("FlashDriver", "Boot", "APP"):
        try:
            crc = updater._get_crc_bytes(ota_cfg[label])
            logger.info(f"  {label} CRC: {crc.hex(' ')}")
        except Exception as e:
            logger.warning(f"  {label} CRC 计算失败: {e}")

    # 验证擦除参数自动计算
    for label in ("Boot", "APP"):
        try:
            erase = updater._get_erase_bytes(ota_cfg[label])
            logger.info(f"  擦除{label}: {erase.hex(' ')}")
        except Exception as e:
            logger.warning(f"  擦除{label} 参数计算失败: {e}")

    # 验证指纹自动生成
    fp = updater._build_fingerprint()
    logger.info(f"  编程指纹: {fp.hex(' ')} (共 {len(fp)} 字节)")
    logger.info("=" * 60)

    # ── 4. 真实硬件升级 ──
    # 以下代码展示完整的 CAN 总线初始化 → UDS 客户端创建 → OTA 升级流程。

    import can
    from Diagnostic import UDSClient

    bus = None
    notifier = None
    uds = None
    try:
        # 4a. 初始化 CAN 总线
        bus = can.interface.Bus(
            interface="zlg",
            channel=0,
            device_index=0,
            bitrate=500000,
            data_bitrate=2000000,
            fd=True,
            dev_type=76,
            receive_own_messages=True,
        )
        notifier = can.Notifier(bus, listeners=[], timeout=0.01)

        # 4b. 创建 UDS 客户端 (以 slot 1 为例, 使用 ProjectConfig 中 Diag.DiagPhyAddr)
        diag_cfg = project_cfg["Diag"]
        tx_id, rx_id = diag_cfg["DiagPhyAddr"]
        uds = UDSClient(
            bus,
            notifier,
            physical_tx=tx_id,
            physical_rx=rx_id,
            project_cfg=project_cfg,
        ).initialize()

        # 4c. 执行 OTA 升级
        updater = OTAType01()
        with uds.client as client:
            result = updater.start_update(client=client, ota_cfg=ota_cfg)

        logger.info(f"升级结果: {result}")
        logger.info(f"刷写状态: {result.get('刷写状态', '未知')}")

    except Exception as e:
        logger.error(f"硬件升级异常: {e}")
    finally:
        # 4d. 清理 — 确保资源释放，不影响后续操作
        if uds is not None:
            try:
                uds.shutdown()
            except Exception:
                pass
        if notifier is not None:
            try:
                notifier.stop()
            except Exception:
                pass
        if bus is not None:
            try:
                bus.shutdown()
            except Exception:
                pass

    # ── 5. CompManager 集成方式 (生产环境推荐) ──
    # CompManager 中已内置 OTA 组件的实例化逻辑，使用时取消注释:
    #
    # from CompManager import ComponentsInstantiation
    #
    # comp = ComponentsInstantiation(group_index=0, project_name="Q5030")
    # ota_instance = comp.require("OTA")  # 获取 OTAType01 实例
    #
    # # 使用 Diagnostic 组件获取已初始化的 UDS 客户端
    # diag = comp.require("Diagnostic")
    # uds, client, tx, rx = diag._ensure_client(slot=1)
    #
    # # 从配置中读取 OTA 参数并执行升级
    # ota_cfg = project_cfg["Diag"]["OTA"]
    # result = ota_instance.start_update(client=client, ota_cfg=ota_cfg)
    # print(f"升级结果: {result['刷写状态']}")
