import can
import time
from typing import Optional
from Logger import LoggerMixin
from CanInitializer import CanBusManager
from Tools import FUNCTION_CONFIG, PROJECT_CONFIG, get_default_project


class OutputCtrl(LoggerMixin):
    """用于控制老化采集卡输出的类"""

    def __init__(self, can_manager: CanBusManager):
        self.bus = can_manager.get_bus()
        self.mode_mapping = {True: [0xFF] * 8, False: [0x00] * 8}

    def setup_card_powermode(self, enable: bool):
        """设置采集卡电源模式"""
        power_mode_msg = [
            can.Message(
                arbitration_id=msg_id,
                data=self.mode_mapping[enable],
                is_extended_id=False,
            )
            for msg_id in [1, 2]
        ]
        for msg in power_mode_msg:
            try:
                for _ in range(FUNCTION_CONFIG["Tx"]["RetransmissionTimes"]):
                    self.bus.send(msg)
                    time.sleep(FUNCTION_CONFIG["Tx"]["RetransmissionInterval"])
            except Exception as e:
                self.log.error(f"Failed to send power mode message: {e}")
        self.log.info(
            f"Setting card power mode to: {'Enabled' if enable else 'Disabled'}"
        )


class CustomTxMsg(LoggerMixin):
    """用于控制自定义发送报文的基类"""

    def __init__(
        self,
        can_manager: CanBusManager,
        which_msg: int,
        project_name: str | None = None,
    ):
        self.can_manager: CanBusManager = can_manager
        self.which_msg = which_msg
        self.bus: can.BusABC = can_manager.get_bus()
        self.project_name = project_name or get_default_project(1)

    def create_periodic_task(self, ch1: bool = True, ch2: bool = True):
        import Protocol

        ch1_msg_id = getattr(Protocol, f"CH1_TX{self.which_msg}_ID")
        ch2_msg_id = getattr(Protocol, f"CH2_TX{self.which_msg}_ID")
        tx_cfg = PROJECT_CONFIG[self.project_name].get("TX", {})
        msg_id = tx_cfg.get(f"IdOfTxMsg{self.which_msg}")
        signal_data = tx_cfg.get(f"DataOfTxMsg{self.which_msg}", {})
        is_fd = tx_cfg.get(f"TypeOfTxMsg{self.which_msg}") == "CANFD"
        period = tx_cfg.get(f"IntervalOfTxMsg{self.which_msg}")

        if msg_id is None:
            raise ValueError(f"TX.IdOfTxMsg{self.which_msg} 未配置")
        if period is None:
            raise ValueError(f"TX.IntervalOfTxMsg{self.which_msg} 未配置")
        if signal_data is None:
            signal_data = {}

        # ProjectConfig 中 DataOfTxMsg* 现在为信号字典, 需要先通过 DBC 编码为 payload
        encoded = self.can_manager.encode_message(msg_id, signal_data)
        payload = encoded.data

        ch1_periodic_task = None
        ch2_periodic_task = None

        if ch1:
            ch1_can_msg = can.Message(
                arbitration_id=ch1_msg_id,
                data=payload,
                is_fd=is_fd,
                is_extended_id=False,
            )
            ch1_periodic_task = self.bus.send_periodic(ch1_can_msg, period)

        if ch2:
            ch2_can_msg = can.Message(
                arbitration_id=ch2_msg_id,
                data=payload,
                is_fd=is_fd,
                is_extended_id=False,
            )
            ch2_periodic_task = self.bus.send_periodic(ch2_can_msg, period)

        # 为了与 modify_periodic_task 的通道约定兼容, 固定返回 [ch1_task, ch2_task]
        return [ch1_periodic_task, ch2_periodic_task]

    def modify_periodic_task(
        self,
        periodic_task: list[can.CyclicSendTaskABC],
        can_msg: Optional[can.Message] = None,
        message_name_or_id=None,
        signal_data: Optional[dict] = None,
    ):
        self.can_manager.modify_periodic_task(
            periodic_task,
            can_msg,
            message_name_or_id,
            signal_data,
        )
        msg_id = message_name_or_id
        if msg_id is None and can_msg is not None:
            msg_id = can_msg.arbitration_id


class CustomTxMsg1(CustomTxMsg):
    """用于控制自定义发送报文1的类"""

    def __init__(self, can_manager: CanBusManager, project_name: str | None = None):
        super().__init__(can_manager, 1, project_name=project_name)


class CustomTxMsg2(CustomTxMsg):
    """用于控制自定义发送报文2的类"""

    def __init__(self, can_manager: CanBusManager, project_name: str | None = None):
        super().__init__(can_manager, 2, project_name=project_name)


if __name__ == "__main__":
    from CanInitializer import CanBusManager

    can_manager = CanBusManager()
    can_manager.initialize(1)
    op = OutputCtrl(can_manager)
    op.setup_card_powermode(True)
    time.sleep(1)
    bus = can_manager.get_bus()
    id3_msg = b"\xff\x07\x9c\x06\x09\x05\xfa\x00"
    id4_msg = b"\xff\x07\x9c\x06\x09\x05\xfa\x00"
    id5_msg = b"\xff\x07\x94\x06\xf6\x05\xae\x00"
    id6_msg = b"\xff\x07\x94\x06\xf6\x05\xae\x00"
    msg_list = [
        can.Message(arbitration_id=3, data=id3_msg, is_extended_id=False),
        can.Message(arbitration_id=4, data=id4_msg, is_extended_id=False),
        can.Message(arbitration_id=5, data=id5_msg, is_extended_id=False),
        can.Message(arbitration_id=6, data=id6_msg, is_extended_id=False),
    ]
    for times in range(3):
        for msg in msg_list:
            bus.send(msg)
            time.sleep(0.1)
            print(f"Sent message ID={msg.arbitration_id}, Data={msg.data.hex()}")

    byte = b"\x16"
    id3_msg = byte + b"\x00\x00\x00\x00\x00\x00\x00"
    id4_msg = byte + b"\x00\x00\x00\x00\x00\x00\x00"
    id5_msg = byte + b"\x00\x00\x00\x00\x00\x00\x00"
    id6_msg = byte + b"\x00\x00\x00\x00\x00\x00\x00"
    msg_list = [
        can.Message(
            arbitration_id=0x7,
            data=id3_msg,
            is_fd=True,
            is_extended_id=False,
            bitrate_switch=True,
        ),
        can.Message(
            arbitration_id=0x9,
            data=id4_msg,
            is_fd=True,
            is_extended_id=False,
            bitrate_switch=True,
        ),
    ]
    for times in range(3):
        for msg in msg_list:
            bus.send(msg)
            time.sleep(0.1)
            print(f"Sent message ID={msg.arbitration_id}, Data={msg.data.hex()}")
