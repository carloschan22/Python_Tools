from struct import pack, unpack
from pymodbus.client import ModbusSerialClient
from Logger import LoggerMixin
from Tools import SELECTED_PROJECT, FUNCTION_CONFIG, PROJECT_CONFIG


def float_to_ieee754_be_words(value: float) -> tuple[int, int]:
    if value is None:
        raise ValueError("value 不能为 None")
    # 处理 NaN/Inf 不做特殊修改, 直接按 IEEE754 打包
    be_bytes = pack(">f", float(value))  # 4 字节
    high_word = (be_bytes[0] << 8) | be_bytes[1]
    low_word = (be_bytes[2] << 8) | be_bytes[3]
    return high_word, low_word


class DY4010(LoggerMixin):
    modbus_ins_counter: int = 0

    def __init__(self, subscript) -> None:
        self.subscript = subscript
        self.comport = FUNCTION_CONFIG["PowerSupply"]["ComPort"][self.subscript]
        self.register_map: dict[str, int] = {
            "Output_Ctrl": 0x0009,
            "Voltage_H": 0x000A,
            "Voltage_L": 0x000B,
            "Current_H": 0x000C,
            "Current_L": 0x000D,
        }
        try:
            self.modbus_client: ModbusSerialClient = ModbusSerialClient(
                port=FUNCTION_CONFIG["PowerSupply"]["ComPort"][self.subscript],
                baudrate=FUNCTION_CONFIG["PowerSupply"]["BaudRate"],
                parity="N",
                stopbits=1,
                bytesize=8,
            )
        except Exception as e:
            print(f"初始化 ModbusSerialClient 时出错: {str(e)}")
        self.modbus_client.connect()
        DY4010.modbus_ins_counter += 1
        self.log.info(f"初始化 Modbus_Pro_power, 端口: {self.comport}, 从站: 1")

    def __del__(self):
        self.modbus_client.close()

    def set_voltage(self, output_voltage: float) -> bool:
        """设置输出电压, 单位 V, 范围 0~30V。

        参数:
          output_voltage: 目标输出电压, 单位 V。

        返回:
          bool: 成功返回 True, 失败返回 False。
        """
        if not (0 <= output_voltage <= 40):
            raise ValueError("output_voltage 必须在 0~40V 范围内")
        high_word, low_word = float_to_ieee754_be_words(output_voltage)
        result_1 = self.modbus_client.write_registers(
            address=self.register_map["Voltage_H"],
            values=[low_word, high_word],
            slave=1,
        )
        return result_1.isError()

    def set_current(self, output_current: float) -> bool:
        """设置输出电流, 单位 A, 范围 0~5A。

        参数:
          output_current: 目标输出电流, 单位 A。

        返回:
          bool: 成功返回 True, 失败返回 False。
        """
        if not (0 <= output_current <= 100):
            raise ValueError("output_current 必须在 0~100A 范围内")
        high_word, low_word = float_to_ieee754_be_words(output_current)
        result_1 = self.modbus_client.write_registers(
            address=self.register_map["Current_H"],
            values=[low_word, high_word],
            slave=1,
        )

        return result_1.isError()

    def start_output(self) -> bool:
        """启动输出。

        返回:
          bool: 成功返回 True, 失败返回 False。
        """
        result = self.modbus_client.write_registers(
            address=self.register_map["Output_Ctrl"], values=[0x0003], slave=1
        )
        return result.isError()

    def stop_output(self) -> bool:
        """停止输出。

        返回:
          bool: 成功返回 True, 失败返回 False。
        """
        result = self.modbus_client.write_registers(
            address=self.register_map["Output_Ctrl"], values=[0x0002], slave=1
        )
        return not result.isError()

    def set_param_and_start_output(self) -> bool:
        return all(
            [
                self.start_output(),
                self.set_voltage(
                    output_voltage=PROJECT_CONFIG[SELECTED_PROJECT]["默认工作电压"]
                    + FUNCTION_CONFIG["PowerSupply"]["VoltageOffset"][self.subscript]
                ),
                self.set_current(
                    output_current=FUNCTION_CONFIG["PowerSupply"]["OutputCurrentLimit"][
                        self.subscript
                    ]
                ),
            ]
        )


class DCPS1216(LoggerMixin):
    """
    一个表示 Modbus 程控电源控制器的类。
    属性
    ----------
    client : ModbusSerialClient
        用于与程控电源通信的 ModbusSerialClient 实例。
    modbus_ins_counter: int
        计数器, 用于跟踪 Modbus_Pro_power 实例的数量。
    方法
    -------
    __init__(port):
        使用指定的串口初始化 Modbus_Pro_power。
    __del__():
        确保在对象销毁时关闭 Modbus 客户端连接。
    close():
        关闭 Modbus 客户端连接。
    """

    modbus_ins_counter: int = 0

    def __init__(self, subscript) -> None:
        self.subscript = subscript
        self.comport = FUNCTION_CONFIG["PowerSupply"]["ComPort"][self.subscript]
        self.cmd_map: dict[str, list] = {
            "set_voltage_valid": [1],
            "set_current_valid": [2],
            "voltage_soft_increace": [3],
            "start_output": [6],
            "stop_output": [7],
        }
        self.register_map: dict[str, int] = {
            "PC": 0x500,
            "ACF": 0x510,
            "OTP": 0x511,
            "OVP": 0x512,
            "OFF": 0x513,
            "CC": 0x514,
            "CMD": 0xA00,
            "VMAX": 0xA01,
            "IMAX": 0xA03,
            "VSET": 0xA05,
            "ISET": 0xA07,
            "TMCVS": 0xA09,
            "BAUDRATE": 0xA1B,
            "VS": 0xB00,
            "IS": 0xB02,
            "MODEL": 0xB04,
            "EDITION": 0xB05,
        }
        try:
            self.modbus_client: ModbusSerialClient = ModbusSerialClient(
                port=self.comport,
                baudrate=FUNCTION_CONFIG["PowerSupply"]["BaudRate"],
                parity="N",
                stopbits=1,
                bytesize=8,
            )
        except Exception as e:
            self.log.error(f"初始化 ModbusSerialClient 时出错: {str(e)}")
            raise
        self.modbus_client.connect()
        DCPS1216.modbus_ins_counter += 1
        self.log.info(f"初始化 Modbus_Pro_power, 端口: {self.comport}, 从站: 1")

    def __del__(self) -> None:
        """
        确保 Modbus 客户端连接被正确关闭。
        """
        try:
            if hasattr(self, "modbus_client") and self.modbus_client is not None:
                if self.modbus_client.is_socket_open():
                    self.modbus_client.close()
                    self.log.info("Modbus 客户端连接已关闭")
        except Exception as e:
            self.log.error(f"关闭 Modbus 客户端时出错: {str(e)}")

    def check_modbus_connection(self):
        """
        检查 Modbus 连接是否正常。
        返回
        -------
        bool
            如果连接正常, 返回 True,否则返回 False。
        """
        try:
            return self.modbus_client.is_socket_open()
        except Exception:
            return False

    def set_output_mode(self, mode: str) -> bool:
        """
        设置远程设备的状态。
        参数
        ----------
        status : str
            远程或本地模式, 'remote' 或 'local'。
        返回
        -------
        bool
            如果设置成功, 返回 True, 否则返回 False。
        """
        status_map: dict[str, bool] = {"remote": True, "local": False}
        if not self.check_modbus_connection():
            return False

        result = self.modbus_client.write_coil(
            address=self.register_map["PC"],
            value=status_map.get(mode),
            slave=1,
        )
        return result.isError() is False

    def get_remote_status(self) -> bool:
        """
        获取远程设备的状态。
        返回
        -------
        bool
            远程模式返回True, 本地模式返回 False。
        """
        if not self.check_modbus_connection():
            return False

        result = self.modbus_client.read_coils(
            address=self.register_map["PC"], count=1, slave=1
        )
        print(result.bits)
        return result.isError() is False and result.bits[0] == 1

    def get_voltage(self) -> int | float:
        """
        获取程控电源的输出电压。
        返回
        -------
        int | float
            程控电源的输出电压值, 如果获取失败, 返回 None。
        """
        if not self.check_modbus_connection():
            return 0  # 返回 0 表示连接失败
        result = self.modbus_client.read_holding_registers(
            self.register_map["VS"], count=2, slave=1
        )
        register_bytes = pack(">HH", *result.registers)
        voltage: float = unpack(">f", register_bytes)[0]
        return voltage if not result.isError() else 0

    def set_voltage(self, output_voltage: int | float) -> bool:
        """
        设置程控电源的输出电压。
        参数
        ----------
        voltage : int | float
            要设置的输出电压值。
        返回
        -------
        bool
            如果设置成功, 返回 True, 否则返回 False。
        """
        if not self.check_modbus_connection():
            return False
        voltage_bytes = pack(">f", output_voltage)
        registers = unpack(">HH", voltage_bytes)
        VSET_result = self.modbus_client.write_registers(
            address=self.register_map["VSET"], values=registers, slave=1
        )
        CMD_result = self.modbus_client.write_registers(
            address=self.register_map["CMD"],
            values=self.cmd_map.get("set_voltage_valid"),
            slave=1,
        )
        return not (VSET_result.isError() or CMD_result.isError())

    def set_current(self, output_current: int | float) -> bool:
        """
        设置程控电源的输出电流。
        参数
        ----------
        current : int | float
            要设置的输出电流值。
        返回
        -------
        bool
            如果设置成功, 返回 True, 否则返回 False。
        """
        if not self.check_modbus_connection():
            return False
        current_bytes = pack(">f", output_current)
        registers = unpack(">HH", current_bytes)
        ISET_result = self.modbus_client.write_registers(
            address=self.register_map["ISET"], values=registers, slave=1
        )
        CMD_result = self.modbus_client.write_registers(
            address=self.register_map["CMD"],
            values=self.cmd_map.get("set_current_valid"),
            slave=1,
        )
        return not (ISET_result.isError() or CMD_result.isError())

    def start_output(self) -> bool:
        """
        启动程控电源的输出。
        返回
        -------
        bool
            如果启动成功, 返回 True, 否则返回 False。
        """
        if not self.check_modbus_connection():
            return False

        result = self.modbus_client.write_registers(
            address=self.register_map["CMD"],
            values=self.cmd_map.get("start_output"),
            slave=1,
        )
        return not result.isError()

    def stop_output(self) -> bool:
        """
        停止程控电源的输出。
        返回
        -------
        bool
            如果停止成功, 返回 True, 否则返回 False。
        """
        if not self.check_modbus_connection():
            return False

        result = self.modbus_client.write_registers(
            address=self.register_map["CMD"],
            values=self.cmd_map.get("stop_output"),
            slave=1,
        )
        return not result.isError()

    def set_param_and_start_output(self) -> bool:
        """
        设置程控电源的输出电压和电流, 并启动输出。
        """

        if not self.set_output_mode(mode="remote"):
            return False
        if not self.set_voltage(
            output_voltage=PROJECT_CONFIG[SELECTED_PROJECT]["默认工作电压"]
            + FUNCTION_CONFIG["PowerSupply"]["VoltageOffset"][self.subscript]
        ):
            return False
        if not self.set_current(
            output_current=FUNCTION_CONFIG["PowerSupply"]["OutputCurrentLimit"][
                self.subscript
            ]
        ):
            return False
        return self.start_output()


def set_powersupply_output(status: bool) -> bool:
    """启动或停止输出, 成功返回 True, 失败返回 False。"""
    ps_type = FUNCTION_CONFIG["PowerSupply"]["Type"]
    counts = len(FUNCTION_CONFIG["PowerSupply"]["ComPort"])

    if ps_type == "DY4010":
        cls = DY4010
    elif ps_type == "DCPS1216":
        cls = DCPS1216
    else:
        print(f"不支持的电源类型: {ps_type}")
        return

    ps_list = [cls(subscript=0)]
    if counts == 2:
        ps_list.append(cls(subscript=1))

    try:
        if status:
            return all(ps.set_param_and_start_output() for ps in ps_list)
        return all(ps.stop_output() for ps in ps_list)
    finally:
        for ps in ps_list:
            del ps


if __name__ == "__main__":
    a = "2026-02-03 13:47:50 INFO Tools: Setting Cards Id, "
    print(len(a))
