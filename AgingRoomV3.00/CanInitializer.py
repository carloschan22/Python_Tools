"""
CAN总线管理器 - 统一管理CAN总线和Notifier, 所有监听器通过依赖注入注册
"""

import can
import sys
import Protocol
import cantools
from pathlib import Path
from Logger import LoggerMixin
from typing import List, Optional


from Tools import FUNCTION_CONFIG, PROJECT_CONFIG, get_default_project


class CanBusManager(LoggerMixin):
    """CAN总线管理器：统一管理Bus和Notifier"""

    def __init__(self, business_parser=None, project_name: Optional[str] = None):
        """
        初始化CAN总线管理器

        Args:
            config: CAN总线配置, 如果为None则使用默认配置
            business_parser: BusinessMessageParser实例, 用于DBC编码（可选）
        """
        self.config = FUNCTION_CONFIG["CanBus"]
        self.bus: Optional[can.BusABC] = None
        self.notifier: Optional[can.Notifier] = None
        self._listeners: List[can.Listener] = []
        self._started = False
        self._business_parser = business_parser
        self.project_name = project_name or get_default_project(1)
        self.project_cfg = PROJECT_CONFIG.get(self.project_name, {})
        dbc_path = self.project_cfg.get("DBC路径")
        if not dbc_path:
            raise ValueError(f"DBC路径 未配置: {self.project_name}")
        self.dbc = cantools.db.load_file(dbc_path, encoding="utf-8")
        self.log.info(
            f"CanBusManager initialized with business_parser: {business_parser}"
        )

    def initialize(self, index: int = 1) -> "CanBusManager":
        """初始化CAN总线和Notifier"""

        def get_dev_index_ch(index: int) -> tuple[int, int]:
            dev_type = self.config["DevType"]
            ch_mapping = {41: 2, 76: 4}
            # if index < 1:
            #     raise ValueError("index must be >= 1")
            total_ch = ch_mapping[dev_type]
            dev_index = (index - 1) // total_ch
            ch = (index - 1) % total_ch
            return dev_index, ch

        if self._started:
            return self

        _is_zlg = self.config["Interface"] == "zlg"
        if _is_zlg:
            dev_index, ch = get_dev_index_ch(index)
        # 创建CAN总线
        self.bus = can.Bus(
            device_index=dev_index if _is_zlg else None,
            interface=self.config["Interface"],
            channel=ch if _is_zlg else 0,
            dev_type=(self.config["DevType"] if _is_zlg else None),
            bitrate=self.config["Bitrate"],
            data_bitrate=self.config["DataBitrate"],
            receive_own_messages=self.config["ReceiveOwnMessages"],
            fd=self.config["FD"],
        )

        # 创建Notifier（暂时不添加任何listener）
        self.notifier = can.Notifier(self.bus, [], 0.01)
        self._started = True

        return self

    def register_listener(self, listener: can.Listener) -> "CanBusManager":
        """
        注册监听器到Notifier

        Args:
            listener: 实现了can.Listener接口的监听器
        """
        if not self._started:
            raise RuntimeError("CanBusManager未初始化, 请先调用initialize()")

        if listener not in self._listeners:
            self._listeners.append(listener)
            self.notifier.add_listener(listener)
        self.log.info(f"Registered listener: {listener.__class__.__name__}")
        return self

    def get_bus(self) -> can.BusABC:
        """获取CAN总线实例"""
        if not self._started:
            raise RuntimeError("CanBusManager未初始化")
        return self.bus

    def get_notifier(self) -> can.Notifier:
        """获取Notifier实例"""
        if not self._started:
            raise RuntimeError("CanBusManager未初始化")
        return self.notifier

    def get_dbc(self) -> cantools.db.Database:
        """获取DBC数据库实例"""
        if not self._started:
            raise RuntimeError("CanBusManager未初始化")
        return self.dbc

    def send_periodic(
        self, message: can.Message, period: float, duration: Optional[float] = None
    ):
        """发送周期性消息"""
        if not self._started:
            self.log.warning(RuntimeError("CanBusManager未初始化"))
        return self.bus.send_periodic(message, period, duration)

    def set_business_parser(self, business_parser) -> "CanBusManager":
        """
        设置业务消息解析器（用于DBC编码）

        Args:
            business_parser: BusinessMessageParser实例
        """
        self._business_parser = business_parser
        return self

    def encode_message(self, message_name_or_id, signal_data: dict) -> can.Message:
        """
        使用DBC编码消息

        Args:
            message_name_or_id: 消息名称或帧ID
            signal_data: 信号字典 {信号名: 信号值}

        Returns:
            编码后的CAN消息
        """

        # 查找消息定义
        if isinstance(message_name_or_id, int):
            msg_def = self.dbc.get_message_by_frame_id(message_name_or_id)
        else:
            msg_def = self.dbc.get_message_by_name(message_name_or_id)

        # 补齐缺失的信号（默认值为0）
        complete_data = {}
        for signal in msg_def.signals:
            complete_data[signal.name] = signal_data.get(signal.name, 0)

        # 编码消息
        encoded_data = self.dbc.encode_message(msg_def.name, complete_data)

        return can.Message(
            arbitration_id=msg_def.frame_id,
            data=encoded_data,
            is_extended_id=msg_def.is_extended_frame,
            is_fd=True,  # 根据实际情况调整
        )

    def modify_periodic_task(
        self,
        periodic_task: list[Optional[can.CyclicSendTaskABC]],
        can_msg: Optional[can.Message] = None,
        message_name_or_id=None,
        signal_data: Optional[dict] = None,
    ):
        """修改周期性任务的消息内容。

        约定：periodic_task 传入两个 can.CyclicSendTaskABC 组成的列表。
        - periodic_task[0] 代表 CH1 的周期任务
        - periodic_task[1] 代表 CH2 的周期任务

        remap 的键对应 ProjectConfig 中的 IdOfTxMsg1 / IdOfTxMsg2。
        当输入的 message_name_or_id（或 can_msg.arbitration_id）等于对应配置值时,
        会将消息 ID 重映射为：
        - CH1_TX1_ID = 7
        - CH1_TX2_ID = 8
        - CH2_TX1_ID = 9
        - CH2_TX2_ID = 10
        并按通道分别修改两个周期任务。
        """

        if not self._started:
            self.log.warning(RuntimeError("CanBusManager未初始化"))

        if not isinstance(periodic_task, (list, tuple)) or len(periodic_task) < 2:
            raise ValueError("periodic_task 必须是长度>=2的列表: [ch1_task, ch2_task]")

        tasks = [periodic_task[0], periodic_task[1]]

        remap = {
            "IdOfTxMsg1": [Protocol.CH1_TX1_ID, Protocol.CH2_TX1_ID],
            "IdOfTxMsg2": [Protocol.CH1_TX2_ID, Protocol.CH2_TX2_ID],
        }

        def _find_remap_key(value):
            if isinstance(value, str) and value in remap:
                return value
            for key in ("IdOfTxMsg1", "IdOfTxMsg2"):
                try:
                    tx_cfg = self.project_cfg.get("TX", {})
                    if value == tx_cfg.get(key):
                        return key
                except Exception:
                    continue
            return None

        base_msg: Optional[can.Message] = can_msg
        if (
            base_msg is None
            and message_name_or_id is not None
            and signal_data is not None
        ):
            # self.log.debug(f"Encoding message for modification: {message_name_or_id} with signals {signal_data}")
            base_msg = self.encode_message(message_name_or_id, signal_data)

        if base_msg is None:
            raise ValueError(
                "必须提供 can_msg, 或同时提供 message_name_or_id 与 signal_data"
            )

        remap_key = _find_remap_key(message_name_or_id)
        if remap_key is None:
            remap_key = _find_remap_key(getattr(base_msg, "arbitration_id", None))

        # 未命中 remap：按原 ID 修改两个通道（保持向后兼容）
        if remap_key is None:
            if tasks[0] is not None:
                tasks[0].modify_data(base_msg)
            if tasks[1] is not None:
                tasks[1].modify_data(base_msg)
            return periodic_task

        for ch_index in (0, 1):
            ch_msg_id = remap[remap_key][ch_index]
            ch_msg = can.Message(
                arbitration_id=ch_msg_id,
                data=base_msg.data,
                is_extended_id=getattr(base_msg, "is_extended_id", False),
                is_fd=getattr(base_msg, "is_fd", True),
            )
            if tasks[ch_index] is None:
                continue
            tasks[ch_index].modify_data(ch_msg)
            # self.log.debug(
            #     f"Modified periodic task for channel {ch_index+1} with message ID {ch_msg_id},data: {ch_msg.data.hex()}"
            # )
        return periodic_task

    def stop_all_periodic_tasks(self):
        """停止所有周期性任务"""
        if self.bus:
            self.bus.stop_all_periodic_tasks()

    def shutdown(self):
        """关闭总线管理器"""
        if not self._started:
            return

        # 停止所有周期性任务
        self.stop_all_periodic_tasks()

        # 停止notifier
        if self.notifier:
            try:
                self.notifier.stop()
            except Exception:
                pass

        # 关闭bus
        if self.bus:
            try:
                self.bus.shutdown()
            except Exception:
                pass

        self._started = False
        self._listeners.clear()

    def __enter__(self):
        """支持上下文管理器"""
        return self.initialize()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """支持上下文管理器"""
        self.shutdown()
