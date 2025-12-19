from udsoncan.connections import PythonIsoTpConnection
from udsoncan.client import Client, services
from udsoncan.typing import ClientConfig
from pathlib import Path
from typing import Any, Optional


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

    def encode(self, *did_value: Any) -> bytes:
        return did_value[0]

    def decode(self, did_payload: bytes) -> Any:
        return did_payload

    def __len__(self) -> int:
        return self.string_len


def aes_encrypt_block(block, key):
    """AES-128 block encryption using basic Python operations"""
    # S-box for AES
    s_box = [
        0x63,
        0x7C,
        0x77,
        0x7B,
        0xF2,
        0x6B,
        0x6F,
        0xC5,
        0x30,
        0x01,
        0x67,
        0x2B,
        0xFE,
        0xD7,
        0xAB,
        0x76,
        0xCA,
        0x82,
        0xC9,
        0x7D,
        0xFA,
        0x59,
        0x47,
        0xF0,
        0xAD,
        0xD4,
        0xA2,
        0xAF,
        0x9C,
        0xA4,
        0x72,
        0xC0,
        0xB7,
        0xFD,
        0x93,
        0x26,
        0x36,
        0x3F,
        0xF7,
        0xCC,
        0x34,
        0xA5,
        0xE5,
        0xF1,
        0x71,
        0xD8,
        0x31,
        0x15,
        0x04,
        0xC7,
        0x23,
        0xC3,
        0x18,
        0x96,
        0x05,
        0x9A,
        0x07,
        0x12,
        0x80,
        0xE2,
        0xEB,
        0x27,
        0xB2,
        0x75,
        0x09,
        0x83,
        0x2C,
        0x1A,
        0x1B,
        0x6E,
        0x5A,
        0xA0,
        0x52,
        0x3B,
        0xD6,
        0xB3,
        0x29,
        0xE3,
        0x2F,
        0x84,
        0x53,
        0xD1,
        0x00,
        0xED,
        0x20,
        0xFC,
        0xB1,
        0x5B,
        0x6A,
        0xCB,
        0xBE,
        0x39,
        0x4A,
        0x4C,
        0x58,
        0xCF,
        0xD0,
        0xEF,
        0xAA,
        0xFB,
        0x43,
        0x4D,
        0x33,
        0x85,
        0x45,
        0xF9,
        0x02,
        0x7F,
        0x50,
        0x3C,
        0x9F,
        0xA8,
        0x51,
        0xA3,
        0x40,
        0x8F,
        0x92,
        0x9D,
        0x38,
        0xF5,
        0xBC,
        0xB6,
        0xDA,
        0x21,
        0x10,
        0xFF,
        0xF3,
        0xD2,
        0xCD,
        0x0C,
        0x13,
        0xEC,
        0x5F,
        0x97,
        0x44,
        0x17,
        0xC4,
        0xA7,
        0x7E,
        0x3D,
        0x64,
        0x5D,
        0x19,
        0x73,
        0x60,
        0x81,
        0x4F,
        0xDC,
        0x22,
        0x2A,
        0x90,
        0x88,
        0x46,
        0xEE,
        0xB8,
        0x14,
        0xDE,
        0x5E,
        0x0B,
        0xDB,
        0xE0,
        0x32,
        0x3A,
        0x0A,
        0x49,
        0x06,
        0x24,
        0x5C,
        0xC2,
        0xD3,
        0xAC,
        0x62,
        0x91,
        0x95,
        0xE4,
        0x79,
        0xE7,
        0xC8,
        0x37,
        0x6D,
        0x8D,
        0xD5,
        0x4E,
        0xA9,
        0x6C,
        0x56,
        0xF4,
        0xEA,
        0x65,
        0x7A,
        0xAE,
        0x08,
        0xBA,
        0x78,
        0x25,
        0x2E,
        0x1C,
        0xA6,
        0xB4,
        0xC6,
        0xE8,
        0xDD,
        0x74,
        0x1F,
        0x4B,
        0xBD,
        0x8B,
        0x8A,
        0x70,
        0x3E,
        0xB5,
        0x66,
        0x48,
        0x03,
        0xF6,
        0x0E,
        0x61,
        0x35,
        0x57,
        0xB9,
        0x86,
        0xC1,
        0x1D,
        0x9E,
        0xE1,
        0xF8,
        0x98,
        0x11,
        0x69,
        0xD9,
        0x8E,
        0x94,
        0x9B,
        0x1E,
        0x87,
        0xE9,
        0xCE,
        0x55,
        0x28,
        0xDF,
        0x8C,
        0xA1,
        0x89,
        0x0D,
        0xBF,
        0xE6,
        0x42,
        0x68,
        0x41,
        0x99,
        0x2D,
        0x0F,
        0xB0,
        0x54,
        0xBB,
        0x16,
    ]

    # Rcon values
    rcon = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]

    def sub_bytes(state):
        return [[s_box[state[i][j]] for j in range(4)] for i in range(4)]

    def shift_rows(state):
        return [
            [state[0][0], state[0][1], state[0][2], state[0][3]],
            [state[1][1], state[1][2], state[1][3], state[1][0]],
            [state[2][2], state[2][3], state[2][0], state[2][1]],
            [state[3][3], state[3][0], state[3][1], state[3][2]],
        ]

    def mix_columns(state):
        def gf_multiply(a, b):
            result = 0
            for _ in range(8):
                if b & 1:
                    result ^= a
                a <<= 1
                if a & 0x100:
                    a ^= 0x11B
                b >>= 1
            return result & 0xFF

        new_state = [[0] * 4 for _ in range(4)]
        for c in range(4):
            new_state[0][c] = (
                gf_multiply(2, state[0][c])
                ^ gf_multiply(3, state[1][c])
                ^ state[2][c]
                ^ state[3][c]
            )
            new_state[1][c] = (
                state[0][c]
                ^ gf_multiply(2, state[1][c])
                ^ gf_multiply(3, state[2][c])
                ^ state[3][c]
            )
            new_state[2][c] = (
                state[0][c]
                ^ state[1][c]
                ^ gf_multiply(2, state[2][c])
                ^ gf_multiply(3, state[3][c])
            )
            new_state[3][c] = (
                gf_multiply(3, state[0][c])
                ^ state[1][c]
                ^ state[2][c]
                ^ gf_multiply(2, state[3][c])
            )
        return new_state

    def add_round_key(state, round_key):
        return [[state[i][j] ^ round_key[i][j] for j in range(4)] for i in range(4)]

    def key_expansion(key):
        w = [[0] * 4 for _ in range(44)]
        for i in range(4):
            w[i] = [key[4 * i + j] for j in range(4)]

        for i in range(4, 44):
            temp = w[i - 1][:]
            if i % 4 == 0:
                temp = [s_box[temp[1]], s_box[temp[2]], s_box[temp[3]], s_box[temp[0]]]
                temp[0] ^= rcon[i // 4 - 1]
            w[i] = [w[i - 4][j] ^ temp[j] for j in range(4)]

        round_keys = []
        for r in range(11):
            round_key = [[w[4 * r + c][row] for c in range(4)] for row in range(4)]
            round_keys.append(round_key)
        return round_keys

    # Convert block and key to state matrices
    state = [[block[i + 4 * j] for j in range(4)] for i in range(4)]
    round_keys = key_expansion(list(key))

    # Initial round
    state = add_round_key(state, round_keys[0])

    # 9 main rounds
    for round_num in range(1, 10):
        state = sub_bytes(state)
        state = shift_rows(state)
        state = mix_columns(state)
        state = add_round_key(state, round_keys[round_num])

    # Final round
    state = sub_bytes(state)
    state = shift_rows(state)
    state = add_round_key(state, round_keys[10])

    # Convert state back to bytes
    result = bytearray(16)
    for i in range(4):
        for j in range(4):
            result[i + 4 * j] = state[i][j]

    return bytes(result)


def encrypt_AES_CBC_nopadding(plain_text, key, iv):
    """AES-128-CBC encryption without padding"""
    if len(plain_text) % 16 != 0:
        raise ValueError("Plaintext length must be multiple of 16 bytes")

    encrypted = bytearray()
    previous_block = iv

    for i in range(0, len(plain_text), 16):
        block = plain_text[i : i + 16]
        # XOR with previous ciphertext block (CBC mode)
        xor_block = bytes(a ^ b for a, b in zip(block, previous_block))
        # Encrypt the XORed block
        cipher_block = aes_encrypt_block(xor_block, key)
        encrypted.extend(cipher_block)
        previous_block = cipher_block

    return bytes(encrypted)


def aes_encrypt_block(block, key):
    """AES-128 block encryption using basic Python operations"""
    # S-box for AES
    # fmt: off
    s_box = [
        0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
        0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
        0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
        0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
        0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
        0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
        0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
        0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
        0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
        0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
        0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
        0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
        0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
        0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
        0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
        0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
    ]
    # fmt: on
    # Rcon values
    rcon = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]

    def sub_bytes(state):
        return [[s_box[state[i][j]] for j in range(4)] for i in range(4)]

    def shift_rows(state):
        return [
            [state[0][0], state[0][1], state[0][2], state[0][3]],
            [state[1][1], state[1][2], state[1][3], state[1][0]],
            [state[2][2], state[2][3], state[2][0], state[2][1]],
            [state[3][3], state[3][0], state[3][1], state[3][2]],
        ]

    def mix_columns(state):
        def gf_multiply(a, b):
            result = 0
            for _ in range(8):
                if b & 1:
                    result ^= a
                a <<= 1
                if a & 0x100:
                    a ^= 0x11B
                b >>= 1
            return result & 0xFF

        new_state = [[0] * 4 for _ in range(4)]
        for c in range(4):
            new_state[0][c] = (
                gf_multiply(2, state[0][c])
                ^ gf_multiply(3, state[1][c])
                ^ state[2][c]
                ^ state[3][c]
            )
            new_state[1][c] = (
                state[0][c]
                ^ gf_multiply(2, state[1][c])
                ^ gf_multiply(3, state[2][c])
                ^ state[3][c]
            )
            new_state[2][c] = (
                state[0][c]
                ^ state[1][c]
                ^ gf_multiply(2, state[2][c])
                ^ gf_multiply(3, state[3][c])
            )
            new_state[3][c] = (
                gf_multiply(3, state[0][c])
                ^ state[1][c]
                ^ state[2][c]
                ^ gf_multiply(2, state[3][c])
            )
        return new_state

    def add_round_key(state, round_key):
        return [[state[i][j] ^ round_key[i][j] for j in range(4)] for i in range(4)]

    def key_expansion(key):
        w = [[0] * 4 for _ in range(44)]
        for i in range(4):
            w[i] = [key[4 * i + j] for j in range(4)]

        for i in range(4, 44):
            temp = w[i - 1][:]
            if i % 4 == 0:
                temp = [s_box[temp[1]], s_box[temp[2]], s_box[temp[3]], s_box[temp[0]]]
                temp[0] ^= rcon[i // 4 - 1]
            w[i] = [w[i - 4][j] ^ temp[j] for j in range(4)]

        round_keys = []
        for r in range(11):
            round_key = [[w[4 * r + c][row] for c in range(4)] for row in range(4)]
            round_keys.append(round_key)
        return round_keys

    # Convert block and key to state matrices
    state = [[block[i + 4 * j] for j in range(4)] for i in range(4)]
    round_keys = key_expansion(list(key))

    # Initial round
    state = add_round_key(state, round_keys[0])

    # 9 main rounds
    for round_num in range(1, 10):
        state = sub_bytes(state)
        state = shift_rows(state)
        state = mix_columns(state)
        state = add_round_key(state, round_keys[round_num])

    # Final round
    state = sub_bytes(state)
    state = shift_rows(state)
    state = add_round_key(state, round_keys[10])

    # Convert state back to bytes
    result = bytearray(16)
    for i in range(4):
        for j in range(4):
            result[i + 4 * j] = state[i][j]

    return bytes(result)


def encrypt_AES_CBC_nopadding(plain_text, key, iv):
    """AES-128-CBC encryption without padding"""
    if len(plain_text) % 16 != 0:
        raise ValueError("Plaintext length must be multiple of 16 bytes")

    encrypted = bytearray()
    previous_block = iv

    for i in range(0, len(plain_text), 16):
        block = plain_text[i : i + 16]
        # XOR with previous ciphertext block (CBC mode)
        xor_block = bytes(a ^ b for a, b in zip(block, previous_block))
        # Encrypt the XORed block
        cipher_block = aes_encrypt_block(xor_block, key)
        encrypted.extend(cipher_block)
        previous_block = cipher_block

    return bytes(encrypted)


class Security:

    def security_algo(level, seed):
        dll_file_name = diag_config["security"]["dll_file_name"]
        dll_path = tools._normalize_path("dll", Path(f"dll/{dll_file_name}.dll"))
        dll_func_name = tools.get_dll_func_names(dll_path)[0]

        # 尝试使用 WinDLL 而不是 CDLL (stdcall vs cdecl 调用约定)
        try:
            ZeekrSeedKey = ctypes.WinDLL(str(dll_path))
        except OSError:
            # 如果 WinDLL 失败，回退到 CDLL
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

        result = GenerateKeyEx(
            iSeedArray,
            ctypes.c_ushort(len(seed)),
            iSecurityLevel,
            ctypes.byref(iVariant),
            iKeyArray,
            ctypes.byref(iKeyLen),
        )

        print(f"DLL 返回值: {result}")
        print(f"生成密钥: {[hex(b) for b in iKeyArray]}")
        return bytes(iKeyArray)

    def security_algo(level, seed):
        key_byte = b"\x9b\x3e\x46\xf1\xd2\xc8\x5a\x7b\x1d\xc4\x9e\x78\x04\xa5\xf3\xb6"
        iv_byte = b"\xc4\xa8\xd5\xe3\xb7\xf0\xc1\x9a\x5d\x26\xb0\x3e\x7f\x81\xc4\x9b"

        Security_key = encrypt_AES_CBC_nopadding(seed, key_byte, iv_byte)
        return bytes(Security_key)


def match_data_identifiers(did_config):
    data_identifiers = {
        tools.hex_to_int(did_hex): DefineDidCodec(string_len=info["size"])
        for did_hex, info in did_config.items()
    }
    return data_identifiers


class DiagService:
    def __init__(self, bus: can.BusABC, config: dict):
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
        config=diag_config,
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
