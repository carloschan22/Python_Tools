from udsoncan.connections import PythonIsoTpConnection
from udsoncan.client import Client, services
from pathlib import Path
from typing import Any


import udsoncan
import ctypes
import tools
import isotp
import can

diag_config: dict = tools.load_config()


class DefineDidCodec(udsoncan.DidCodec):
    string_len: int

    def __init__(self, string_len: int):
        self.string_len = string_len

    def encode(self, string_bin: Any) -> bytes:
        return string_bin

    def decode(self, string_bin: bytes) -> Any:
        return string_bin

    def __len__(self) -> int:
        return self.string_len


class Security:
    def security_algo(level, seed):
        dll_path = tools._normalize_path(
            "dll", Path(f"dll/{diag_config["security"]["dll_file_name"]}.dll")
        )
        dll_func_name = tools.get_dll_func_names(dll_path)[0]

        ZeekrSeedKey = ctypes.CDLL(dll_path)
        GenerateKeyEx = ZeekrSeedKey.__getattr__(dll_func_name)
        GenerateKeyEx.argtypes = [
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_ushort,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.POINTER(ctypes.c_ushort),
        ]
        GenerateKeyEx.restype = ctypes.c_uint

        iSeedArray = (ctypes.c_ubyte * len(seed))(*seed)
        iSecurityLevel = ctypes.c_uint(level)
        iVariant = (ctypes.c_ubyte)()
        iKeyArray = (ctypes.c_ubyte * len(seed))()

        GenerateKeyEx(
            iSeedArray,
            ctypes.c_ushort(diag_config["security"]["feedback_bytes"]),
            iSecurityLevel,
            iVariant,
            iKeyArray,
            ctypes.c_ushort(diag_config["security"]["feedback_bytes"]),
        )
        return bytes(iKeyArray)


def match_data_identifiers(did_config):
    data_identifiers = {
        tools.hex_to_int(did_hex): DefineDidCodec(string_len=info["size"])
        for did_hex, info in did_config.items()
    }
    return data_identifiers


class DiagService:
    def __init__(self, bus: can.Bus, config: dict):
        self.bus = bus
        self.config = config
        self.physical_tx = tools.hex_to_int(config["address"]["phy_tx"])
        self.physical_rx = tools.hex_to_int(config["address"]["phy_rx"])
        self.isotp_params = config["isotp_params"]
        self.isotp_params.update(
            {"tx_padding": tools.hex_to_int(config["isotp_params"]["tx_padding"])}
        )

    def uds_set_stack(self) -> isotp.CanStack:
        try:
            tp_addr = isotp.Address(
                isotp.AddressingMode.Normal_11bits,
                txid=self.physical_tx,
                rxid=self.physical_rx,
            )
            stack = isotp.CanStack(
                bus=self.bus, address=tp_addr, params=self.isotp_params
            )
        except Exception as e:
            print(f"创建ISOTP栈失败: {e}")
            raise e
        return stack

    def uds_update_stack_address(
        self, stack: isotp.CanStack, txid: int, rxid: int
    ) -> None:
        try:
            new_address = isotp.Address(
                isotp.AddressingMode.Normal_11bits, txid=txid, rxid=rxid
            )
            stack.set_address(new_address)
        except Exception as e:
            print(f"更新ISOTP栈地址失败: {e}")
            raise e

    def uds_set_conn(self, stack: isotp.CanStack) -> PythonIsoTpConnection:
        try:
            conn = PythonIsoTpConnection(stack if stack else self.uds_set_stack())
        except Exception as e:
            print(f"创建UDS连接失败: {e}")
            raise e
        return conn

    def uds_set_config(self) -> dict:
        client_config = self.config["default_client_config"]
        client_config["data_identifiers"] = match_data_identifiers(
            self.config["did_config"]
        )
        client_config["security_algo"] = Security.security_algo
        return client_config

    def uds_create_client(self, stack: isotp.CanStack = None) -> Client:
        try:
            conn = self.uds_set_conn(stack)
            client_config = self.uds_set_config()
            client = Client(conn, config=client_config)
        except Exception as e:
            print(f"创建UDS客户端失败: {e}")
            raise e
        return client


if __name__ == "__main__":
    bus_config = diag_config["can_bus"]

    bus = can.Bus(
        interface=bus_config["interface"],
        channel=bus_config["channel"],
        bitrate=bus_config["bitrate"],
        data_bitrate=bus_config["data_bitrate"],
        fd=bus_config["fd"],
    )

    DS = DiagService(
        bus=bus,
        config=diag_config,
    )
    stack = DS.uds_set_stack()
    print("ISOTP栈创建成功")

    client = DS.uds_create_client(stack=stack)
    print("UDS客户端创建成功")

    with client:
        response = client.read_data_by_identifier(0xF197)
        print(f"读取DID 0xF197 响应: {response.data}")
        response = client.change_session(3)
        if response.positive:
            print("切换到编程会话成功")
            try:
                response = client.unlock_security_access(1)
                if response.positive:
                    print("安全访问级别1成功")
                    response = client.read_data_by_identifier(0xF197)
                    print(f"读取DID 0xF197 响应: {response.data}")
                else:
                    print("安全访问级别1失败")
            except Exception as e:
                print(f"会话切换或安全访问失败: {e}")

    DS.uds_update_stack_address(stack, txid=0x7DF, rxid=0x7E8)
    print("ISOTP地址已更改为 txid=0x7DF, rxid=0x7E8")

    del DS
    bus.shutdown()
