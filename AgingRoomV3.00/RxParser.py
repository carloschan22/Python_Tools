import can
import time

from typing import Any, Optional
from Protocol import split_by_can_id, get_slot_id_by_can_id
from Logger import LoggerMixin
from Tools import (
    FUNCTION_CONFIG,
    PROJECT_CONFIG,
    create_slot_table,
    get_default_project,
)


class CustomRxMsg(LoggerMixin):
    """自定义采集卡报文解析基类"""

    def __init__(self, dbc: Any, project_name: str | None = None):
        self.status = create_slot_table(
            FUNCTION_CONFIG["UI"]["IndexPerGroup"], default_factory=dict
        )
        self.decoder = DbcDecoder(dbc=dbc, data_list=self.status)
        self.project_name = project_name or get_default_project(1)


class DbcDecoder(LoggerMixin):
    """DBC解析器"""

    def __init__(self, dbc: Any, data_list: Optional[list] = None):
        self.dbc = dbc
        self.data_list = data_list

    def on_message_decode(self, msg: can.Message, origin_msg_id: int) -> None:
        if self.dbc is None:
            raise RuntimeError(
                "DbcDecoder.dbc 未初始化, 请从 CanBusManager.get_dbc() 注入"
            )
        index = get_slot_id_by_can_id(msg.arbitration_id)
        try:
            self.data_list[index] = self.dbc.decode_message(origin_msg_id, msg.data)
        except Exception as e:
            self.log.info(
                f"无法使用DBC解码消息: ID={origin_msg_id}, Data={msg.data.hex()}"
            )
            self.log.error(f"处理接收消息时出错: {e}")


class CustomRxMsg1(CustomRxMsg, LoggerMixin):
    """自定义采集卡报文1解析"""

    def __init__(self, dbc: Any, project_name: str | None = None):
        super().__init__(dbc, project_name=project_name)

    def decoding(self, msg: can.Message):
        """启动DBC解码器"""
        rx_cfg = PROJECT_CONFIG.get(self.project_name, {}).get("RX", {})
        origin_id = rx_cfg.get("IdOfRxMsg1")
        if origin_id is None:
            return
        self.decoder.on_message_decode(msg, origin_id)


class CustomRxMsg2(CustomRxMsg, LoggerMixin):
    """自定义采集卡报文2解析"""

    def __init__(self, dbc: Any, project_name: str | None = None):
        super().__init__(dbc, project_name=project_name)

    def decoding(self, msg: can.Message):
        """启动DBC解码器"""
        rx_cfg = PROJECT_CONFIG.get(self.project_name, {}).get("RX", {})
        origin_id = rx_cfg.get("IdOfRxMsg2")
        if origin_id is None:
            return
        self.decoder.on_message_decode(msg, origin_id)


class AgingStatus(LoggerMixin):
    """解析采集卡老化状态"""

    def __init__(self, project_name: str | None = None):
        self.status = create_slot_table(
            FUNCTION_CONFIG["UI"]["IndexPerGroup"],
            default_factory=self._blank_status,
        )
        self._timestamp_offset: Optional[float] = None
        self.project_name = project_name or get_default_project(1)

    def _normalize_timestamp(self, ts: Any) -> Optional[float]:
        try:
            value = float(ts)
        except Exception:
            return None

        if value <= 0:
            return None

        if value < 1_000_000_000:
            if self._timestamp_offset is None:
                self._timestamp_offset = time.time() - value
            return value + self._timestamp_offset

        return value

    @staticmethod
    def _blank_status():
        return {
            "Timestamp": "",
            "Status": 0,
            "Voltage": 0,
            "Current": 0,
            "CardInfo": {},
            "CardTemperature": 20,
            "ResistorInfo": {},
        }

    def decode_status(self, msg: can.Message) -> None:
        """解析采集卡状态"""
        map = {
            "slave_configed": ["configed", "not_configed"],
            "reserve_1": ["default", "default"],
            "output_status": ["open", "close"],
            "current_status": ["normal", "abnormal"],
            "voltage_status": ["normal", "abnormal"],
            "can_status": ["normal", "abnormal"],
            "reserve_2": ["default", "default"],
            "reserve_3": ["default", "default"],
        }

        def byte_to_bit_list(byte_val):
            return [(byte_val >> i) & 1 for i in range(8)]

        status_list = byte_to_bit_list(msg.data[5])

        mapped_status = {}
        for key, value in zip(map.keys(), status_list):
            mapped_status[key] = map[key][value]
        return mapped_status

    def decode_resistor(self, msg: can.Message) -> dict:
        """ "解析采集卡电阻配置报文"""
        resistor_byte = msg.data[6]
        if isinstance(resistor_byte, bytes):
            if len(resistor_byte) != 1:
                raise ValueError("Input bytes must be of length 1.")
            value = resistor_byte[0]
        elif isinstance(resistor_byte, int):
            value = resistor_byte
        else:
            raise ValueError("Input must be a single byte or int.")

        reverse_map = {0: 9999, 1: 120, 2: 240, 3: -1}
        config_keys = ["main_can", "can_1", "can_2"]
        bit_shifts = [4, 2, 0]

        result = {}
        for key, shift in zip(config_keys, bit_shifts):
            code = (value >> shift) & 0x03
            result[key] = reverse_map[code]
        return result

    def decode_voltage(self, msg: can.Message) -> None:
        """解析当前电压报文"""
        return round(msg.data[1] * 0.1, 2)

    def decode_current(self, msg: can.Message) -> None:
        """解析当前老化状态报文"""
        return round(
            int.from_bytes(msg.data[2:5], byteorder="big", signed=False) * 0.001, 2
        )

    def decode_temperature(self, msg: can.Message) -> None:
        """解析当前温度报文"""
        return round(msg.data[7] - 40)

    def mapping_status(self, current, voltage):
        """
        根据电流、电压判断状态码：
        - status = 0: 状态为初始值, UI不更新底色
        - status = -5: 采集卡丢失（电压/电流为0或异常）, UI报警
        - status = -4: 低于暗电流范围, 未接产品, UI不判断
        - status = -3: 超出暗电流范围, 低于工作电压范围, 低于工作电流范围, UI报警
        - status = -2: 超出暗电流范围, 处于正常工作电流范围, 低于工作电压范围, UI报警
        - status = -1: 超出暗电流范围, 处于正常工作电压范围, 低于工作电流范围, UI报警
        - status = 1: 正常工作电压、电流, UI正常
        - status = 2: 超出暗电流范围, 处于正常工作电压范围, 超出工作电流范围, UI报警
        - status = 3: 超出暗电流范围, 低于工作电流范围, 高于工作电压范围, UI报警
        - status = 4: 超出暗电流范围, 高于工作电压范围, 超出工作电流范围, UI报警
        """

        status = 0
        dark_current: float = FUNCTION_CONFIG["PowerSupply"]["DarkCurrent"]
        voltage_range: list[int] = PROJECT_CONFIG[self.project_name]["工作电压范围"]
        current_range: list[int] = PROJECT_CONFIG[self.project_name]["工作电流范围"]
        if voltage <= 0 and current <= 0:
            return -5

        if current <= dark_current:
            return -4

        if voltage_range[0] <= voltage <= voltage_range[1]:
            if current_range[0] <= current <= current_range[1]:
                status = 1
            elif current < current_range[0]:
                status = -1
            else:
                status = 2
        elif voltage < voltage_range[0]:
            if current < current_range[0]:
                status = -3
            else:
                status = -2
        else:
            if current < current_range[0]:
                status = 3
            else:
                status = 4
        return status

    def decoding(self, msg: can.Message):
        """启动DBC解码器"""
        index = get_slot_id_by_can_id(msg.arbitration_id)
        current = self.decode_current(msg)
        voltage = self.decode_voltage(msg)
        status = self.mapping_status(current, voltage)
        normalized_ts = self._normalize_timestamp(msg.timestamp)
        if normalized_ts is None:
            normalized_ts = time.time()

        self.status[index] = {
            "Timestamp": normalized_ts,
            "Status": status,
            "Voltage": voltage,
            "Current": current,
            "CardInfo": self.decode_status(msg),
            "CardTemperature": self.decode_temperature(msg),
            "ResistorInfo": self.decode_resistor(msg),
        }


class RxSplitter(can.Listener, LoggerMixin):
    """来自采集卡Can报文分流器,三个节点报文解析"""

    def __init__(
        self,
        dbc: Any,
        switcher: Optional[list[bool]] = None,
        project_name: str | None = None,
    ):
        if switcher is None:
            switcher = [True, True, True]
        if len(switcher) != 3:
            raise ValueError(
                "switcher 必须为长度=3的列表: [AgingStatus, CustomRxMsg1, CustomRxMsg2]"
            )

        self.rx_msg_managers: list[
            Optional[AgingStatus | CustomRxMsg1 | CustomRxMsg2]
        ] = [
            AgingStatus(project_name=project_name) if switcher[0] else None,
            CustomRxMsg1(dbc, project_name=project_name) if switcher[1] else None,
            CustomRxMsg2(dbc, project_name=project_name) if switcher[2] else None,
        ]

        self._dispatch = {}
        if self.rx_msg_managers[0] is not None:
            self._dispatch["CH1_STATUS"] = self.rx_msg_managers[0].decoding
            self._dispatch["CH2_STATUS"] = self.rx_msg_managers[0].decoding
        if self.rx_msg_managers[1] is not None:
            self._dispatch["CH1_APP_RX1"] = self.rx_msg_managers[1].decoding
            self._dispatch["CH2_APP_RX1"] = self.rx_msg_managers[1].decoding
        if self.rx_msg_managers[2] is not None:
            self._dispatch["CH1_APP_RX2"] = self.rx_msg_managers[2].decoding
            self._dispatch["CH2_APP_RX2"] = self.rx_msg_managers[2].decoding

    def on_message_received(self, msg: can.Message) -> None:
        try:
            key = split_by_can_id(msg.arbitration_id)
        except ValueError:
            # 非协议内可分流的帧（例如回环/噪声/其它模块帧）, 直接忽略
            return

        try:
            handler = self._dispatch.get(key)
            if handler is None:
                # 例如 OUTPUT_CTRL_1 / CH1_TX1 等回环帧, 不参与接收解析
                return
            handler(msg)
        except Exception as e:
            self.log.error(f"处理接收消息时出错: {e}")

    def get_status(self, which: str, slot: int = None):
        mapping = {
            "card_status": 0,
            "custom_rx1": 1,
            "custom_rx2": 2,
        }
        manager = self.rx_msg_managers[mapping[which]]
        if manager is None:
            return None if slot is not None else []
        if slot is None:
            return manager.status
        return manager.status[slot]
