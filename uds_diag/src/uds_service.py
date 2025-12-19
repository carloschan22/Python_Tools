from udsoncan.connections import PythonIsoTpConnection
from udsoncan.client import Client, services
from udsoncan.typing import ClientConfig
from pathlib import Path
from typing import Any, Optional


import udsoncan
import ctypes

try:
    import tools
except ImportError:
    from src import tools
import isotp
import can

diag_config: dict = tools.load_config()


class DefineDidCodec(udsoncan.DidCodec):
    string_len: int

    def __init__(self, string_len: int):
        self.string_len = string_len

    def encode(self, *did_value: Any) -> bytes:
        return did_value[0]

    def decode(self, did_payload: bytes) -> Any:
        return did_payload

    def __len__(self) -> int:
        return self.string_len


class Security:

    def security_algo(level, seed):
        dll_file_name = diag_config["security"]["dll_file_name"]
        dll_path = tools._normalize_path("dll", Path(f"dll/{dll_file_name}.dll"))
        dll_func_name = tools.get_dll_func_names(dll_path)[0]

        ZeekrSeedKey = ctypes.CDLL(str(dll_path))

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
        iKeyLen = ctypes.c_ushort(diag_config["security"]["feedback_bytes"])

        GenerateKeyEx(
            iSeedArray,
            ctypes.c_ushort(len(seed)),
            iSecurityLevel,
            ctypes.byref(iVariant),
            iKeyArray,
            ctypes.byref(iKeyLen),
        )
        return bytes(iKeyArray)


def match_data_identifiers(did_config):
    data_identifiers = {
        tools.hex_to_int(did_hex): DefineDidCodec(string_len=info["size"])
        for did_hex, info in did_config.items()
    }
    return data_identifiers


class DiagService:
    def __init__(self, bus: can.BusABC):
        self.bus = bus
        self.config = diag_config
        self.physical_tx = tools.hex_to_int(self.config["address"]["phy_tx"])
        self.physical_rx = tools.hex_to_int(self.config["address"]["phy_rx"])
        self.isotp_params = self.config["isotp_params"]
        self.isotp_params.update(
            {"tx_padding": tools.hex_to_int(self.config["isotp_params"]["tx_padding"])}
        )

    def uds_set_stack(self) -> isotp.CanStack:
        try:
            tp_addr = isotp.Address(
                txid=self.physical_tx,
                rxid=self.physical_rx,
            )
            stack = isotp.CanStack(
                bus=self.bus, address=tp_addr, params=self.isotp_params
            )
            stack.set_sleep_timing(0, 0)
        except Exception as e:
            print(f"创建ISOTP栈失败: {e}")
            raise e
        return stack

    def uds_update_stack_address(
        self, stack: isotp.CanStack, txid: int, rxid: int
    ) -> None:
        try:
            new_address = isotp.Address(txid=txid, rxid=rxid)
            stack.set_address(new_address)
        except Exception as e:
            print(f"更新ISOTP栈地址失败: {e}")
            raise e

    def uds_set_conn(
        self, stack: Optional[isotp.CanStack] = None
    ) -> PythonIsoTpConnection:
        try:
            conn = PythonIsoTpConnection(stack if stack else self.uds_set_stack())
        except Exception as e:
            print(f"创建UDS连接失败: {e}")
            raise e
        return conn

    def uds_set_config(self) -> ClientConfig:
        client_config_dict = self.config["default_client_config"].copy()
        client_config_dict["data_identifiers"] = match_data_identifiers(
            self.config["did_config"]
        )
        client_config_dict["security_algo"] = Security.security_algo
        return ClientConfig(**client_config_dict)

    def uds_create_client(self, stack: Optional[isotp.CanStack] = None) -> Client:
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
    )
    stack = DS.uds_set_stack()
    print("ISOTP栈创建成功")

    client = DS.uds_create_client(stack=stack)
    print("UDS客户端创建成功")

    with client:
        response = client.read_data_by_identifier(0xF197)  # type: ignore[reportArgumentType]
        print(f"读取DID 0xF197 响应: {response.data}")
        response = client.change_session(3)  # type: ignore[reportArgumentType]
        if response.positive:
            print("切换到编程会话成功")
            try:
                response = client.unlock_security_access(1)  # type: ignore[reportArgumentType]
                if response.positive:
                    print("安全访问级别1成功")
                    response = client.read_data_by_identifier(0xF197)  # type: ignore[reportArgumentType]
                    print(f"读取DID 0xF197 响应: {response.data}")
                else:
                    print("安全访问级别1失败")
            except Exception as e:
                print(f"会话切换或安全访问失败: {e}")

    DS.uds_update_stack_address(stack, txid=0x7DF, rxid=0x7E8)
    print("ISOTP地址已更改为 txid=0x7DF, rxid=0x7E8")

    del DS
    bus.shutdown()
