from Tools import FUNCTION_CONFIG, PROJECT_CONFIG

SETTING_SLAVE_ID = 0
OUTPUT_CTRL_ID_1 = 1
OUTPUT_CTRL_ID_2 = 2
CH1_RX_CONFIG_ID = 3
CH2_RX_CONFIG_ID = 4
CH1_TX_CONFIG_ID = 5
CH2_TX_CONFIG_ID = 6
CH1_TX1_ID = 7
CH1_TX2_ID = 8
CH2_TX1_ID = 9
CH2_TX2_ID = 10


MAGNIFICATION = 10

CH1_INFO_OFFSET = 1
CH2_INFO_OFFSET = 6

STATUS_OFFSET = 0
DIAG_RX_OFFSET = 1
DIAG_TX_OFFSET = 2
APP_RX1_OFFSET = 3
APP_RX2_OFFSET = 4

SLAVE_COUNT = int(FUNCTION_CONFIG["UI"]["IndexPerGroup"] / 2)


_GLOBAL_ID_TO_KEY = {
    SETTING_SLAVE_ID: "SETTING_SLAVE",
    OUTPUT_CTRL_ID_1: "OUTPUT_CTRL_1",
    OUTPUT_CTRL_ID_2: "OUTPUT_CTRL_2",
    CH1_RX_CONFIG_ID: "CH1_RX_CONFIG",
    CH2_RX_CONFIG_ID: "CH2_RX_CONFIG",
    CH1_TX_CONFIG_ID: "CH1_TX_CONFIG",
    CH2_TX_CONFIG_ID: "CH2_TX_CONFIG",
    CH1_TX1_ID: "CH1_TX1",
    CH1_TX2_ID: "CH1_TX2",
    CH2_TX1_ID: "CH2_TX1",
    CH2_TX2_ID: "CH2_TX2",
}


def _is_channel_remap_enabled() -> bool:
    """是否启用通道重映射（CH1/CH2 互换）"""
    ui_cfg = FUNCTION_CONFIG.get("UI", {})
    val = ui_cfg.get("Remap", False)

    # 兼容 bool/int/str 配置
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enable",
            "enabled",
        }
    return bool(val)


def get_slave_id_by_can_id(can_id: int) -> int:
    """根据 CAN ID 获取对应的从机 ID"""
    return can_id // MAGNIFICATION


def get_slot_id_by_can_id(can_id: int) -> int:
    """根据 CAN ID 获取对应的 slot（1..IndexPerGroup）。

    约定（与 UI 展示一致）：
    - “站点编号”使用奇数：1,3,5,...,79（每个站点有 CH1/CH2 两个通道）
    - slot=站点编号表示 CH1；slot=站点编号+1 表示 CH2
    - 若开启 UI.Remap, 则返回“外壳通道视角”的 slot（即 CH1/CH2 互换后）。
    """
    slave_id = get_slave_id_by_can_id(can_id)
    offset = can_id % MAGNIFICATION

    # 基站点编号（奇数）。若出现偶数, 降级到其前一个奇数。
    base_station = slave_id if (slave_id % 2 == 1) else (slave_id - 1)
    if base_station < 1:
        base_station = 1

    # MCU 通道判定：0=CH1, 1=CH2
    mcu_ch_index = 1 if offset >= CH2_INFO_OFFSET else 0

    # 返回时按需做通道重映射（CH1/CH2 互换）, 得到外壳通道
    if _is_channel_remap_enabled():
        shell_ch_index = 1 - mcu_ch_index
    else:
        shell_ch_index = mcu_ch_index

    # slot：CH1=base_station, CH2=base_station+1
    slot_id = base_station + shell_ch_index
    return slot_id


def split_by_can_id(can_id: int) -> str:
    """根据 CAN ID 返回分流键名。

    - 采集卡上报（按 slave 分组）: CH1_STATUS / CH2_APP_RX1 等
    - 本机发送/配置类（可能因 ReceiveOwnMessages 回环进入接收队列）: OUTPUT_CTRL_1 / CH1_TX1 等

    注意：若开启 UI.Remap, 则 CH1/CH2 键名按“外壳通道定义”互换。
    """
    # 先处理“全局/本机发送类”的小 ID, 避免 ReceiveOwnMessages 回环导致解析失败
    if can_id in _GLOBAL_ID_TO_KEY:
        return _GLOBAL_ID_TO_KEY[can_id]

    offset = can_id % MAGNIFICATION

    # 先按 MCU 通道解析（用于 offset 解析与校验）
    if offset >= CH2_INFO_OFFSET:
        mcu_channel = "CH2"
        channel_offset = offset - CH2_INFO_OFFSET
    else:
        mcu_channel = "CH1"
        channel_offset = offset - CH1_INFO_OFFSET

    offset_to_name = {
        STATUS_OFFSET: "STATUS",
        DIAG_RX_OFFSET: "DIAG_RX",
        DIAG_TX_OFFSET: "DIAG_TX",
        APP_RX1_OFFSET: "APP_RX1",
        APP_RX2_OFFSET: "APP_RX2",
    }

    try:
        suffix = offset_to_name[channel_offset]
    except KeyError as exc:
        raise ValueError(
            f"Unknown CAN ID offset: can_id={can_id}, offset={offset}"
        ) from exc

    # 返回时按需做通道重映射（CH1/CH2 互换）
    if _is_channel_remap_enabled():
        out_channel = "CH1" if mcu_channel == "CH2" else "CH2"
    else:
        out_channel = mcu_channel

    return f"{out_channel}_{suffix}"


def get_phy_addr_by_slot(slot_id: int) -> tuple[int, int]:
    """根据采集卡索引获取物理地址。

    注意：
    - slot_id 从 1 开始（外壳/展示通道编号）, 不是从 0 开始。
    - slot_id 的 ch 含义按 UI.Remap 视角（外壳通道定义）。
      若开启 UI.Remap, 则需要在这里把 CH1/CH2 互换回 MCU 通道后, 再计算物理地址。
    """
    max_slots = SLAVE_COUNT * 2
    if slot_id < 1 or slot_id > max_slots:
        raise ValueError(
            f"slot_id must be in [1, {max_slots}] (1-based indexing expected)"
        )

    # 图片中的“站点编号”为奇数：1,3,5,...
    # slot=站点编号 表示 CH1；slot=站点编号+1 表示 CH2
    base_station = slot_id if (slot_id % 2 == 1) else (slot_id - 1)
    shell_ch = 0 if (slot_id % 2 == 1) else 1  # 0=CH1, 1=CH2（外壳/展示通道）

    # 映射回 MCU 通道
    if _is_channel_remap_enabled():
        mcu_ch = 1 - shell_ch
    else:
        mcu_ch = shell_ch
    if mcu_ch == 0:
        phy_addr = base_station * MAGNIFICATION + CH1_INFO_OFFSET
    else:
        phy_addr = base_station * MAGNIFICATION + CH2_INFO_OFFSET
    phy_tx = phy_addr + DIAG_TX_OFFSET
    phy_rx = phy_addr + DIAG_RX_OFFSET
    return phy_tx, phy_rx


if __name__ == "__main__":
    slot_addrs = get_phy_addr_by_slot(7)
    print(slot_addrs)
