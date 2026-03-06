"""ProjectConfig.json / FuncConfig.json 配置图形化工具

提供 ProjectConfigDialog 对话框，让用户无需手动编辑 JSON 即可新增 / 编辑项目配置。
Diag.Params.isotp_params 根据 CAN FD 开关自动填充预设模板；
default_client_config 始终使用统一默认值。

FuncConfigDialog  — FuncConfig.json 图形化编辑。
ManualUpdateDialog — 选择更新压缩包，按文件类型分发到对应目录后自动重启。
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# 预设模板
# ---------------------------------------------------------------------------
ISOTP_CANFD = {
    "stmin": 24,
    "blocksize": 8,
    "wftmax": 0,
    "tx_data_length": 64,
    "tx_data_min_length": 8,
    "can_fd": True,
    "tx_padding": 204,
    "rx_flowcontrol_timeout": 1000,
    "rx_consecutive_frame_timeout": 1000,
    "max_frame_size": 4095,
}

ISOTP_CAN = {
    "stmin": 0,
    "blocksize": 0,
    "wftmax": 0,
    "tx_data_length": 8,
    "tx_data_min_length": 8,
    "can_fd": False,
    "tx_padding": 0,
    "rx_flowcontrol_timeout": 1000,
    "rx_consecutive_frame_timeout": 1000,
    "squash_stmin_requirement": False,
    "max_frame_size": 4095,
}

DEFAULT_CLIENT_CONFIG = {
    "exception_on_negative_response": True,
    "exception_on_invalid_response": True,
    "exception_on_unexpected_response": True,
    "security_algo": None,
    "security_algo_params": None,
    "tolerate_zero_padding": True,
    "ignore_all_zero_dtc": True,
    "dtc_snapshot_did_size": 2,
    "server_address_format": None,
    "server_memorysize_format": None,
    "data_identifiers": {},
    "input_output": {},
    "request_timeout": 5,
    "p2_timeout": 1,
    "p2_star_timeout": 5,
    "standard_version": 2020,
    "use_server_timing": False,
    "extended_data_size": None,
}

ALL_COMPONENTS = [
    "AgingStatus",
    "CustomTxMsg1",
    "CustomTxMsg2",
    "CustomRxMsg1",
    "CustomRxMsg2",
    "Diagnostic",
    "OTA",
    "PowerCycle",
    "PeriodicSwitchMsg1",
    "PeriodicSwitchMsg2",
    "PeriodicDiag",
    "PeriodicReadDtc",
]


# ---------------------------------------------------------------------------
# 对话框
# ---------------------------------------------------------------------------
class ProjectConfigDialog(QDialog):
    """图形化新增 / 编辑 ProjectConfig.json 项目配置"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("新增项目配置")
        self.resize(800, 720)
        self._config_path = Path(__file__).parent / "config" / "ProjectConfig.json"

        main_layout = QVBoxLayout(self)

        # ---- 顶部: 模板选择 ----
        tpl_layout = QHBoxLayout()
        tpl_layout.addWidget(QLabel("从已有项目复制:"))
        self._combo_template = QComboBox()
        self._combo_template.addItem("-- 空白模板 --")
        for name in self._load_existing_projects():
            self._combo_template.addItem(name)
        tpl_layout.addWidget(self._combo_template, 1)
        btn_load = QPushButton("加载模板")
        btn_load.clicked.connect(self._on_load_template)
        tpl_layout.addWidget(btn_load)
        main_layout.addLayout(tpl_layout)

        # ---- 项目名称 ----
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("项目名称:"))
        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("例如: Q5020")
        name_layout.addWidget(self._edit_name, 1)
        main_layout.addLayout(name_layout)

        # ---- Tabs ----
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_basic_tab(), "基本参数")
        self._tabs.addTab(self._build_comm_tab(), "通信配置")
        self._tabs.addTab(self._build_diag_tab(), "诊断配置")
        main_layout.addWidget(self._tabs, 1)

        # ---- 底部按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

    # ================================================================
    # Tab 1 — 基本参数
    # ================================================================
    def _build_basic_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # 老化时长
        self._edit_aging_hours = QLineEdit()
        self._edit_aging_hours.setPlaceholderText("逗号分隔, 如: 2,4,6")
        form.addRow("老化时长选项:", self._edit_aging_hours)

        self._edit_default_aging = QLineEdit()
        self._edit_default_aging.setPlaceholderText("如: 2")
        form.addRow("默认老化时长:", self._edit_default_aging)

        # 电压
        self._spin_default_voltage = QDoubleSpinBox()
        self._spin_default_voltage.setRange(0, 100)
        self._spin_default_voltage.setDecimals(1)
        self._spin_default_voltage.setValue(12)
        form.addRow("默认工作电压 (V):", self._spin_default_voltage)

        h1 = QHBoxLayout()
        self._spin_voltage_min = QDoubleSpinBox()
        self._spin_voltage_min.setRange(0, 100)
        self._spin_voltage_min.setDecimals(1)
        self._spin_voltage_max = QDoubleSpinBox()
        self._spin_voltage_max.setRange(0, 100)
        self._spin_voltage_max.setDecimals(1)
        h1.addWidget(self._spin_voltage_min)
        h1.addWidget(QLabel("~"))
        h1.addWidget(self._spin_voltage_max)
        form.addRow("工作电压范围 (V):", h1)

        # 电流
        h2 = QHBoxLayout()
        self._spin_current_min = QSpinBox()
        self._spin_current_min.setRange(0, 99999)
        self._spin_current_max = QSpinBox()
        self._spin_current_max.setRange(0, 99999)
        h2.addWidget(self._spin_current_min)
        h2.addWidget(QLabel("~"))
        h2.addWidget(self._spin_current_max)
        form.addRow("工作电流范围 (mA):", h2)

        # 温度
        h3 = QHBoxLayout()
        self._spin_temp_min = QSpinBox()
        self._spin_temp_min.setRange(-40, 200)
        self._spin_temp_max = QSpinBox()
        self._spin_temp_max.setRange(-40, 200)
        h3.addWidget(self._spin_temp_min)
        h3.addWidget(QLabel("~"))
        h3.addWidget(self._spin_temp_max)
        form.addRow("老化温度范围 (°C):", h3)

        # 路径
        h_dbc = QHBoxLayout()
        self._edit_dbc = QLineEdit()
        self._edit_dbc.setPlaceholderText("dbc/XXX.dbc")
        btn_dbc = QPushButton("浏览")
        btn_dbc.clicked.connect(
            lambda: self._browse_file(self._edit_dbc, "DBC Files (*.dbc)")
        )
        h_dbc.addWidget(self._edit_dbc, 1)
        h_dbc.addWidget(btn_dbc)
        form.addRow("DBC路径:", h_dbc)

        h_dll = QHBoxLayout()
        self._edit_dll = QLineEdit()
        self._edit_dll.setPlaceholderText("dll/XXX.dll")
        btn_dll = QPushButton("浏览")
        btn_dll.clicked.connect(
            lambda: self._browse_file(self._edit_dll, "DLL Files (*.dll)")
        )
        h_dll.addWidget(self._edit_dll, 1)
        h_dll.addWidget(btn_dll)
        form.addRow("DLL路径:", h_dll)

        # 电压偏移
        self._chk_voltage_offset = QCheckBox("启用")
        form.addRow("是否电压偏移老化:", self._chk_voltage_offset)

        h4 = QHBoxLayout()
        self._spin_offset_min = QDoubleSpinBox()
        self._spin_offset_min.setRange(-10, 10)
        self._spin_offset_min.setDecimals(1)
        self._spin_offset_min.setValue(-2)
        self._spin_offset_max = QDoubleSpinBox()
        self._spin_offset_max.setRange(-10, 10)
        self._spin_offset_max.setDecimals(1)
        self._spin_offset_max.setValue(2)
        h4.addWidget(self._spin_offset_min)
        h4.addWidget(QLabel("~"))
        h4.addWidget(self._spin_offset_max)
        form.addRow("老化电压偏移范围 (V):", h4)

        # 周期上电
        self._chk_power_cycle = QCheckBox("启用")
        form.addRow("是否周期上电老化:", self._chk_power_cycle)

        h5 = QHBoxLayout()
        self._spin_power_on = QSpinBox()
        self._spin_power_on.setRange(0, 9999)
        self._spin_power_on.setSuffix(" min")
        self._spin_power_on.setValue(10)
        self._spin_sleep = QSpinBox()
        self._spin_sleep.setRange(0, 9999)
        self._spin_sleep.setSuffix(" min")
        self._spin_sleep.setValue(1)
        h5.addWidget(QLabel("带电:"))
        h5.addWidget(self._spin_power_on)
        h5.addWidget(QLabel("休眠:"))
        h5.addWidget(self._spin_sleep)
        form.addRow("带电/休眠时长:", h5)

        self._spin_delay_on_judgement = QSpinBox()
        self._spin_delay_on_judgement.setRange(0, 9999)
        self._spin_delay_on_judgement.setSuffix(" s")
        self._spin_delay_on_judgement.setValue(5)
        self._spin_delay_on_judgement.setToolTip(
            "周期上电从断电切换到上电后，延时N秒再恢复状态判定"
        )
        form.addRow("上电判定延时 (DelayOnJudgement):", self._spin_delay_on_judgement)

        scroll.setWidget(container)
        return scroll

    # ================================================================
    # Tab 2 — 通信配置
    # ================================================================
    def _build_comm_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        # ---- SupportedComponents ----
        grp_comp = QGroupBox("支持的功能组件")
        grid = QGridLayout(grp_comp)
        self._comp_checks: dict[str, QCheckBox] = {}
        for i, comp in enumerate(ALL_COMPONENTS):
            cb = QCheckBox(comp)
            self._comp_checks[comp] = cb
            grid.addWidget(cb, i // 3, i % 3)
        layout.addWidget(grp_comp)

        # ---- RX ----
        grp_rx = QGroupBox("接收报文 (RX)")
        rx_form = QFormLayout(grp_rx)

        self._spin_rx1 = self._nullable_spin("RX报文1 ID")
        rx_form.addRow("IdOfRxMsg1:", self._spin_rx1["layout"])

        self._spin_rx2 = self._nullable_spin("RX报文2 ID")
        rx_form.addRow("IdOfRxMsg2:", self._spin_rx2["layout"])

        self._spin_temp_id = self._nullable_spin("温度报文 ID")
        rx_form.addRow("GetTempById:", self._spin_temp_id["layout"])

        self._edit_temp_sig = QLineEdit()
        self._edit_temp_sig.setPlaceholderText("如: SMIRM_NTC_Tem (留空表示不启用)")
        rx_form.addRow("GetTempBySigName:", self._edit_temp_sig)
        layout.addWidget(grp_rx)

        # ---- TX ----
        grp_tx = QGroupBox("发送报文 (TX)")
        tx_form = QFormLayout(grp_tx)

        # TxMsg1
        self._spin_tx1 = self._nullable_spin("TX报文1 ID")
        tx_form.addRow("IdOfTxMsg1:", self._spin_tx1["layout"])

        self._combo_tx1_type = QComboBox()
        self._combo_tx1_type.addItems(["CANFD", "CAN"])
        tx_form.addRow("TypeOfTxMsg1:", self._combo_tx1_type)

        self._spin_tx1_interval = QDoubleSpinBox()
        self._spin_tx1_interval.setRange(0.01, 60)
        self._spin_tx1_interval.setDecimals(2)
        self._spin_tx1_interval.setValue(0.2)
        self._spin_tx1_interval.setSuffix(" s")
        tx_form.addRow("IntervalOfTxMsg1:", self._spin_tx1_interval)

        self._edit_tx1_data = QPlainTextEdit()
        self._edit_tx1_data.setPlaceholderText(
            '信号数据 JSON, 如:\n{"SignalName": "Value"}\n留空表示 {}'
        )
        self._edit_tx1_data.setMaximumHeight(60)
        tx_form.addRow("DataOfTxMsg1:", self._edit_tx1_data)

        # TxMsg2
        self._spin_tx2 = self._nullable_spin("TX报文2 ID")
        tx_form.addRow("IdOfTxMsg2:", self._spin_tx2["layout"])

        self._combo_tx2_type = QComboBox()
        self._combo_tx2_type.addItems(["CANFD", "CAN"])
        tx_form.addRow("TypeOfTxMsg2:", self._combo_tx2_type)

        self._spin_tx2_interval = QDoubleSpinBox()
        self._spin_tx2_interval.setRange(0.01, 60)
        self._spin_tx2_interval.setDecimals(2)
        self._spin_tx2_interval.setValue(0.2)
        self._spin_tx2_interval.setSuffix(" s")
        tx_form.addRow("IntervalOfTxMsg2:", self._spin_tx2_interval)

        self._edit_tx2_data = QPlainTextEdit()
        self._edit_tx2_data.setPlaceholderText(
            '信号数据 JSON, 如:\n{"SignalName": 40}\n留空表示 {}'
        )
        self._edit_tx2_data.setMaximumHeight(60)
        tx_form.addRow("DataOfTxMsg2:", self._edit_tx2_data)
        layout.addWidget(grp_tx)

        # ---- PeriodicSwitching ----
        grp_ps = QGroupBox("周期切换 (PeriodicSwitching)")
        ps_layout = QVBoxLayout(grp_ps)

        ps1_form = QFormLayout()
        self._spin_sw1_interval = self._nullable_spin("切换间隔(s)", max_val=9999)
        ps1_form.addRow("SwitchMsg1 间隔(s):", self._spin_sw1_interval["layout"])
        self._edit_sw1_data = QPlainTextEdit()
        self._edit_sw1_data.setPlaceholderText(
            "切换数据列表 JSON, 如:\n"
            '[{"Signal": "Red"}, {"Signal": "Blue"}]\n'
            "留空表示 []"
        )
        self._edit_sw1_data.setMaximumHeight(80)
        ps1_form.addRow("SwitchMsg1 数据:", self._edit_sw1_data)
        ps_layout.addLayout(ps1_form)

        ps2_form = QFormLayout()
        self._spin_sw2_interval = self._nullable_spin("切换间隔(s)", max_val=9999)
        ps2_form.addRow("SwitchMsg2 间隔(s):", self._spin_sw2_interval["layout"])
        self._edit_sw2_data = QPlainTextEdit()
        self._edit_sw2_data.setPlaceholderText(
            "切换数据列表 JSON, 如:\n"
            '[{"Signal": 40}, {"Signal": 10}]\n'
            "留空表示 []"
        )
        self._edit_sw2_data.setMaximumHeight(80)
        ps2_form.addRow("SwitchMsg2 数据:", self._edit_sw2_data)
        ps_layout.addLayout(ps2_form)

        layout.addWidget(grp_ps)
        layout.addStretch(1)

        scroll.setWidget(container)
        return scroll

    # ================================================================
    # Tab 3 — 诊断配置
    # ================================================================
    def _build_diag_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        layout = QVBoxLayout(container)

        # ---- 基本诊断参数 ----
        grp_basic = QGroupBox("基本参数")
        basic_form = QFormLayout(grp_basic)

        self._spin_security_bytes = QSpinBox()
        self._spin_security_bytes.setRange(1, 64)
        self._spin_security_bytes.setValue(4)
        basic_form.addRow("SecurityFeedbackBytes:", self._spin_security_bytes)

        h_addr = QHBoxLayout()
        self._spin_diag_req = QSpinBox()
        self._spin_diag_req.setRange(0, 65535)
        self._spin_diag_resp = QSpinBox()
        self._spin_diag_resp.setRange(0, 65535)
        h_addr.addWidget(QLabel("请求:"))
        h_addr.addWidget(self._spin_diag_req)
        h_addr.addWidget(QLabel("响应:"))
        h_addr.addWidget(self._spin_diag_resp)
        basic_form.addRow("诊断物理地址:", h_addr)

        self._chk_canfd = QCheckBox("CANFD模式 (取消则为CAN模式)")
        self._chk_canfd.setChecked(True)
        self._chk_canfd.setToolTip(
            "选中 → CANFD isotp_params 模板\n"
            "取消 → CAN isotp_params 模板\n"
            "default_client_config 始终使用默认值"
        )
        basic_form.addRow("通信协议:", self._chk_canfd)

        layout.addWidget(grp_basic)

        # ---- OTA 配置 ----
        grp_ota = QGroupBox("OTA 升级配置")
        ota_form = QFormLayout(grp_ota)

        self._chk_ota_enable = QCheckBox("启用 OTA")
        self._chk_ota_enable.setToolTip(
            "启用后，老化结束将自动对符合条件的穴位执行 OTA 升级"
        )
        ota_form.addRow("OTA:", self._chk_ota_enable)

        self._spin_ota_delay = QSpinBox()
        self._spin_ota_delay.setRange(0, 9999)
        self._spin_ota_delay.setValue(5)
        self._spin_ota_delay.setSuffix(" s")
        ota_form.addRow("老化后延时 (DelayAfterAging):", self._spin_ota_delay)

        self._spin_ota_judge = QSpinBox()
        self._spin_ota_judge.setRange(0, 9999)
        self._spin_ota_judge.setValue(2)
        self._spin_ota_judge.setSuffix(" s")
        ota_form.addRow("判定延时 (DelayJudgement):", self._spin_ota_judge)

        self._combo_ota_type = QComboBox()
        self._combo_ota_type.addItems(["OTAType01"])
        self._combo_ota_type.setEditable(True)
        self._combo_ota_type.setToolTip("OTA 刷写实现类型，如 OTAType01")
        ota_form.addRow("Type:", self._combo_ota_type)

        h_flash = QHBoxLayout()
        self._edit_ota_flash = QLineEdit()
        self._edit_ota_flash.setPlaceholderText("如: Q5030_Driver.hex")
        btn_flash = QPushButton("浏览")
        btn_flash.clicked.connect(
            lambda: self._browse_file(self._edit_ota_flash, "HEX Files (*.hex)")
        )
        h_flash.addWidget(self._edit_ota_flash, 1)
        h_flash.addWidget(btn_flash)
        ota_form.addRow("FlashDriver:", h_flash)

        h_boot = QHBoxLayout()
        self._edit_ota_boot = QLineEdit()
        self._edit_ota_boot.setPlaceholderText("如: Q5030_BOOT_V000F-20251013")
        btn_boot = QPushButton("浏览")
        btn_boot.clicked.connect(
            lambda: self._browse_file(self._edit_ota_boot, "HEX Files (*.hex)")
        )
        h_boot.addWidget(self._edit_ota_boot, 1)
        h_boot.addWidget(btn_boot)
        ota_form.addRow("Boot:", h_boot)

        h_app = QHBoxLayout()
        self._edit_ota_app = QLineEdit()
        self._edit_ota_app.setPlaceholderText("如: Q5030_APP_V0020-20251013")
        btn_app = QPushButton("浏览")
        btn_app.clicked.connect(
            lambda: self._browse_file(self._edit_ota_app, "HEX Files (*.hex)")
        )
        h_app.addWidget(self._edit_ota_app, 1)
        h_app.addWidget(btn_app)
        ota_form.addRow("APP:", h_app)

        self._spin_ota_slot_retry = QSpinBox()
        self._spin_ota_slot_retry.setRange(1, 10)
        self._spin_ota_slot_retry.setValue(1)
        self._spin_ota_slot_retry.setToolTip("单个穴位 OTA 失败后的重试次数")
        ota_form.addRow("穴位重试次数 (SlotRetry):", self._spin_ota_slot_retry)

        self._spin_ota_inter_slot_delay = QDoubleSpinBox()
        self._spin_ota_inter_slot_delay.setRange(0, 60)
        self._spin_ota_inter_slot_delay.setDecimals(1)
        self._spin_ota_inter_slot_delay.setValue(1.0)
        self._spin_ota_inter_slot_delay.setSuffix(" s")
        self._spin_ota_inter_slot_delay.setToolTip(
            "两个穴位 OTA 之间的间隔延时，用于 CAN 总线恢复"
        )
        ota_form.addRow("穴位间延时 (InterSlotDelay):", self._spin_ota_inter_slot_delay)

        # 联动: 未启用时禁用子控件
        ota_children = [
            self._spin_ota_delay,
            self._spin_ota_judge,
            self._combo_ota_type,
            self._edit_ota_flash,
            btn_flash,
            self._edit_ota_boot,
            btn_boot,
            self._edit_ota_app,
            btn_app,
            self._spin_ota_slot_retry,
            self._spin_ota_inter_slot_delay,
        ]
        for w in ota_children:
            w.setEnabled(False)
        self._chk_ota_enable.toggled.connect(
            lambda checked: [w.setEnabled(checked) for w in ota_children]
        )

        layout.addWidget(grp_ota)

        # ---- DID 配置 ----
        grp_did = QGroupBox("DID 配置")
        did_layout = QVBoxLayout(grp_did)

        self._table_did = QTableWidget(0, 7)
        self._table_did.setHorizontalHeaderLabels(
            ["DID", "操作", "名称", "大小", "类型", "值", "Padding"]
        )
        self._table_did.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._table_did.setMinimumHeight(130)
        did_layout.addWidget(self._table_did)

        did_btn = QHBoxLayout()
        btn_add = QPushButton("添加DID")
        btn_add.clicked.connect(self._add_did_row)
        btn_del = QPushButton("删除选中")
        btn_del.clicked.connect(self._del_did_row)
        did_btn.addWidget(btn_add)
        did_btn.addWidget(btn_del)
        did_btn.addStretch(1)
        did_layout.addLayout(did_btn)

        layout.addWidget(grp_did)

        # ---- PeriodicReadDtc ----
        grp_dtc = QGroupBox("周期读DTC (PeriodicReadDtc)")
        dtc_form = QFormLayout(grp_dtc)

        self._spin_dtc_interval = QSpinBox()
        self._spin_dtc_interval.setRange(1, 9999)
        self._spin_dtc_interval.setValue(10)
        self._spin_dtc_interval.setSuffix(" s")
        dtc_form.addRow("读取间隔:", self._spin_dtc_interval)

        self._spin_dtc_subfunc = QSpinBox()
        self._spin_dtc_subfunc.setRange(0, 255)
        self._spin_dtc_subfunc.setValue(2)
        dtc_form.addRow("SubFunction:", self._spin_dtc_subfunc)

        self._spin_dtc_mask = QSpinBox()
        self._spin_dtc_mask.setRange(0, 255)
        self._spin_dtc_mask.setValue(9)
        dtc_form.addRow("DtcStatusMask:", self._spin_dtc_mask)

        self._edit_dtc_whitelist = QLineEdit()
        self._edit_dtc_whitelist.setPlaceholderText(
            "白名单DTC, 逗号分隔, 如: C1408709,C1298709 (留空表示无白名单)"
        )
        dtc_form.addRow("WhiteList:", self._edit_dtc_whitelist)

        layout.addWidget(grp_dtc)

        # ---- PeriodicDiag ----
        grp_pdiag = QGroupBox("周期诊断 (PeriodicDiag)")
        pdiag_form = QFormLayout(grp_pdiag)

        self._spin_pdiag_interval = QSpinBox()
        self._spin_pdiag_interval.setRange(1, 9999)
        self._spin_pdiag_interval.setValue(2)
        self._spin_pdiag_interval.setSuffix(" s")
        pdiag_form.addRow("诊断间隔:", self._spin_pdiag_interval)

        self._spin_pdiag_rediag = QSpinBox()
        self._spin_pdiag_rediag.setRange(1, 9999)
        self._spin_pdiag_rediag.setValue(1)
        self._spin_pdiag_rediag.setSuffix(" s")
        pdiag_form.addRow("重试间隔:", self._spin_pdiag_rediag)

        self._edit_pdiag_dids = QPlainTextEdit()
        self._edit_pdiag_dids.setPlaceholderText(
            "周期诊断DID配置, 支持两种格式:\n"
            '1. Read DID列表: ["0xF193", "0xFD00"]\n'
            '2. Write DID+值: {"0x8114": ["0101,0102,0103"]}'
        )
        self._edit_pdiag_dids.setMaximumHeight(80)
        pdiag_form.addRow("Dids:", self._edit_pdiag_dids)

        layout.addWidget(grp_pdiag)
        layout.addStretch(1)

        scroll.setWidget(container)
        return scroll

    # ================================================================
    # 辅助工具
    # ================================================================
    @staticmethod
    def _nullable_spin(tooltip: str = "", max_val: int = 65535) -> dict:
        """创建一个可置空的 SpinBox（勾选"启用"后才可编辑）。"""
        h = QHBoxLayout()
        chk = QCheckBox("启用")
        spin = QSpinBox()
        spin.setRange(0, max_val)
        spin.setEnabled(False)
        chk.toggled.connect(spin.setEnabled)
        h.addWidget(chk)
        h.addWidget(spin, 1)
        if tooltip:
            spin.setToolTip(tooltip)
        return {"layout": h, "checkbox": chk, "spinbox": spin}

    @staticmethod
    def _set_nullable_spin(ctrl: dict, value) -> None:
        if value is None:
            ctrl["checkbox"].setChecked(False)
            ctrl["spinbox"].setValue(0)
        else:
            ctrl["checkbox"].setChecked(True)
            ctrl["spinbox"].setValue(int(value))

    @staticmethod
    def _get_nullable_spin(ctrl: dict):
        if not ctrl["checkbox"].isChecked():
            return None
        return ctrl["spinbox"].value()

    def _browse_file(self, line_edit: QLineEdit, file_filter: str) -> None:
        base_dir = str(Path(__file__).parent)
        path, _ = QFileDialog.getOpenFileName(self, "选择文件", base_dir, file_filter)
        if path:
            try:
                rel = os.path.relpath(path, base_dir).replace("\\", "/")
            except ValueError:
                rel = path.replace("\\", "/")
            line_edit.setText(rel)

    def _add_did_row(self) -> None:
        row = self._table_did.rowCount()
        self._table_did.insertRow(row)

        op_combo = QComboBox()
        op_combo.addItems(["Read", "Write"])
        self._table_did.setCellWidget(row, 1, op_combo)

        type_combo = QComboBox()
        type_combo.addItems(["bytes", "string"])
        self._table_did.setCellWidget(row, 4, type_combo)

        self._table_did.setItem(row, 0, QTableWidgetItem("0x"))
        self._table_did.setItem(row, 2, QTableWidgetItem(""))
        self._table_did.setItem(row, 3, QTableWidgetItem("2"))
        self._table_did.setItem(row, 5, QTableWidgetItem(""))
        self._table_did.setItem(row, 6, QTableWidgetItem("0x20"))

    def _del_did_row(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table_did.selectedIndexes()}, reverse=True
        )
        for row in rows:
            self._table_did.removeRow(row)

    # ================================================================
    # 模板加载
    # ================================================================
    def _load_existing_projects(self) -> list[str]:
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                return list(json.load(f).keys())
        except Exception:
            return []

    def _on_load_template(self) -> None:
        name = self._combo_template.currentText()
        if name == "-- 空白模板 --":
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if name in data:
                self._fill_from_config(name, data[name])
        except Exception as e:
            QMessageBox.warning(self, "加载失败", str(e))

    def _fill_from_config(self, name: str, cfg: dict) -> None:
        """将已有配置填入所有表单字段。"""
        self._edit_name.setText(name)

        # -- 基本参数 --
        aging = cfg.get("老化时长", [])
        self._edit_aging_hours.setText(",".join(str(x) for x in aging))
        self._edit_default_aging.setText(str(cfg.get("默认老化时长", "")))
        self._spin_default_voltage.setValue(cfg.get("默认工作电压", 12))

        v = cfg.get("工作电压范围", [11, 14])
        self._spin_voltage_min.setValue(v[0] if len(v) > 0 else 11)
        self._spin_voltage_max.setValue(v[1] if len(v) > 1 else 14)

        c = cfg.get("工作电流范围", [400, 1000])
        self._spin_current_min.setValue(c[0] if len(c) > 0 else 400)
        self._spin_current_max.setValue(c[1] if len(c) > 1 else 1000)

        t = cfg.get("老化温度范围", [70, 80])
        self._spin_temp_min.setValue(t[0] if len(t) > 0 else 70)
        self._spin_temp_max.setValue(t[1] if len(t) > 1 else 80)

        self._edit_dbc.setText(cfg.get("DBC路径", ""))
        self._edit_dll.setText(cfg.get("DLL路径", ""))

        self._chk_voltage_offset.setChecked(cfg.get("是否电压偏移老化", False))
        off = cfg.get("老化电压偏移范围", [-2, 2])
        self._spin_offset_min.setValue(off[0] if len(off) > 0 else -2)
        self._spin_offset_max.setValue(off[1] if len(off) > 1 else 2)

        self._chk_power_cycle.setChecked(cfg.get("是否周期上电老化", False))
        ps = cfg.get("带电老化/休眠老化时长", [10, 1])
        self._spin_power_on.setValue(ps[0] if len(ps) > 0 else 10)
        self._spin_sleep.setValue(ps[1] if len(ps) > 1 else 1)
        power_cycle_cfg = cfg.get("PowerCycle", {})
        self._spin_delay_on_judgement.setValue(
            int(power_cycle_cfg.get("DelayOnJudgement", 5) or 0)
        )

        # -- 组件 --
        components = cfg.get("SupportedComponents", [])
        for comp, cb in self._comp_checks.items():
            cb.setChecked(comp in components)

        # -- RX --
        rx = cfg.get("RX", {})
        self._set_nullable_spin(self._spin_rx1, rx.get("IdOfRxMsg1"))
        self._set_nullable_spin(self._spin_rx2, rx.get("IdOfRxMsg2"))
        self._set_nullable_spin(self._spin_temp_id, rx.get("GetTempById"))
        self._edit_temp_sig.setText(rx.get("GetTempBySigName") or "")

        # -- TX --
        tx = cfg.get("TX", {})
        self._set_nullable_spin(self._spin_tx1, tx.get("IdOfTxMsg1"))
        self._combo_tx1_type.setCurrentText(tx.get("TypeOfTxMsg1", "CANFD"))
        self._spin_tx1_interval.setValue(tx.get("IntervalOfTxMsg1", 0.2))
        d1 = tx.get("DataOfTxMsg1", {})
        self._edit_tx1_data.setPlainText(
            json.dumps(d1, ensure_ascii=False) if d1 else ""
        )

        self._set_nullable_spin(self._spin_tx2, tx.get("IdOfTxMsg2"))
        self._combo_tx2_type.setCurrentText(tx.get("TypeOfTxMsg2", "CANFD"))
        self._spin_tx2_interval.setValue(tx.get("IntervalOfTxMsg2", 0.2))
        d2 = tx.get("DataOfTxMsg2", {})
        self._edit_tx2_data.setPlainText(
            json.dumps(d2, ensure_ascii=False) if d2 else ""
        )

        # PeriodicSwitching
        ps_cfg = tx.get("PeriodicSwitching", {})
        sw1 = ps_cfg.get("SwitchMsg1", {})
        self._set_nullable_spin(self._spin_sw1_interval, sw1.get("SwitchInterval"))
        sw1d = sw1.get("Data", [])
        self._edit_sw1_data.setPlainText(
            json.dumps(sw1d, ensure_ascii=False, indent=2) if sw1d else ""
        )
        sw2 = ps_cfg.get("SwitchMsg2", {})
        self._set_nullable_spin(self._spin_sw2_interval, sw2.get("SwitchInterval"))
        sw2d = sw2.get("Data", [])
        self._edit_sw2_data.setPlainText(
            json.dumps(sw2d, ensure_ascii=False, indent=2) if sw2d else ""
        )

        # -- 诊断 --
        diag = cfg.get("Diag", {})
        self._spin_security_bytes.setValue(diag.get("SecurityFeedbackBytes", 4))
        addrs = diag.get("DiagPhyAddr", [0, 0])
        self._spin_diag_req.setValue(addrs[0] if len(addrs) > 0 else 0)
        self._spin_diag_resp.setValue(addrs[1] if len(addrs) > 1 else 0)

        isotp = diag.get("Params", {}).get("isotp_params", {})
        self._chk_canfd.setChecked(isotp.get("can_fd", True))

        # DidConfig
        self._table_did.setRowCount(0)
        for did_id, info in diag.get("DidConfig", {}).items():
            row = self._table_did.rowCount()
            self._table_did.insertRow(row)
            self._table_did.setItem(row, 0, QTableWidgetItem(did_id))

            op_combo = QComboBox()
            op_combo.addItems(["Read", "Write"])
            op_combo.setCurrentText(
                info.get("Operation", info.get("operation", "Read"))
            )
            self._table_did.setCellWidget(row, 1, op_combo)

            self._table_did.setItem(row, 2, QTableWidgetItem(info.get("name", "")))
            self._table_did.setItem(row, 3, QTableWidgetItem(str(info.get("size", 2))))

            type_combo = QComboBox()
            type_combo.addItems(["bytes", "string"])
            type_combo.setCurrentText(info.get("type", "bytes"))
            self._table_did.setCellWidget(row, 4, type_combo)

            self._table_did.setItem(
                row, 5, QTableWidgetItem(str(info.get("value", "")))
            )
            self._table_did.setItem(
                row, 6, QTableWidgetItem(info.get("Padding", "0x20"))
            )

        # OTA
        ota_cfg = diag.get("OTA", {})
        has_ota = bool(ota_cfg)
        self._chk_ota_enable.setChecked(has_ota)
        self._spin_ota_delay.setValue(ota_cfg.get("DelayAfterAging", 5))
        self._spin_ota_judge.setValue(ota_cfg.get("DelayJudgement", 2))
        self._combo_ota_type.setCurrentText(ota_cfg.get("Type", "OTAType01"))
        self._edit_ota_flash.setText(ota_cfg.get("FlashDriver", ""))
        self._edit_ota_boot.setText(ota_cfg.get("Boot", ""))
        self._edit_ota_app.setText(ota_cfg.get("APP", ""))
        self._spin_ota_slot_retry.setValue(ota_cfg.get("SlotRetry", 1))
        self._spin_ota_inter_slot_delay.setValue(ota_cfg.get("InterSlotDelay", 1.0))

        # PeriodicReadDtc
        prdtc = diag.get("PeriodicReadDtc", {})
        self._spin_dtc_interval.setValue(prdtc.get("Interval", 10))
        self._spin_dtc_subfunc.setValue(prdtc.get("SubFunction", 2))
        self._spin_dtc_mask.setValue(prdtc.get("DtcStatusMask", 9))
        self._edit_dtc_whitelist.setText(",".join(prdtc.get("WhiteList", [])))

        # PeriodicDiag
        pdiag = diag.get("PeriodicDiag", {})
        self._spin_pdiag_interval.setValue(pdiag.get("Interval", 2))
        self._spin_pdiag_rediag.setValue(pdiag.get("ReDiagInterval", 1))
        dids_val = pdiag.get("Dids", [])
        self._edit_pdiag_dids.setPlainText(
            json.dumps(dids_val, ensure_ascii=False, indent=2)
        )

    # ================================================================
    # 构建 & 保存
    # ================================================================
    def _build_config(self) -> tuple[str, dict]:
        """从表单收集所有字段，返回 (项目名, 配置字典)。"""
        name = self._edit_name.text().strip()
        if not name:
            raise ValueError("项目名称不能为空")

        # 老化时长
        aging_text = self._edit_aging_hours.text().strip()
        if not aging_text:
            raise ValueError("老化时长选项不能为空")
        try:
            aging_hours = [int(x.strip()) for x in aging_text.split(",") if x.strip()]
        except ValueError:
            raise ValueError("老化时长格式错误，请使用逗号分隔的整数")

        cfg: dict = {}
        cfg["老化时长"] = aging_hours
        cfg["默认老化时长"] = self._edit_default_aging.text().strip()
        cfg["默认工作电压"] = self._spin_default_voltage.value()
        cfg["工作电压范围"] = [
            self._spin_voltage_min.value(),
            self._spin_voltage_max.value(),
        ]
        cfg["工作电流范围"] = [
            self._spin_current_min.value(),
            self._spin_current_max.value(),
        ]
        cfg["老化温度范围"] = [
            self._spin_temp_min.value(),
            self._spin_temp_max.value(),
        ]
        cfg["DBC路径"] = self._edit_dbc.text().strip()
        cfg["DLL路径"] = self._edit_dll.text().strip()
        cfg["是否电压偏移老化"] = self._chk_voltage_offset.isChecked()
        cfg["老化电压偏移范围"] = [
            self._spin_offset_min.value(),
            self._spin_offset_max.value(),
        ]
        cfg["是否周期上电老化"] = self._chk_power_cycle.isChecked()
        cfg["带电老化/休眠老化时长"] = [
            self._spin_power_on.value(),
            self._spin_sleep.value(),
        ]
        cfg["PowerCycle"] = {"DelayOnJudgement": self._spin_delay_on_judgement.value()}

        # SupportedComponents
        cfg["SupportedComponents"] = [
            comp for comp, cb in self._comp_checks.items() if cb.isChecked()
        ]

        # RX
        cfg["RX"] = {
            "IdOfRxMsg1": self._get_nullable_spin(self._spin_rx1),
            "IdOfRxMsg2": self._get_nullable_spin(self._spin_rx2),
            "GetTempById": self._get_nullable_spin(self._spin_temp_id),
            "GetTempBySigName": self._edit_temp_sig.text().strip() or None,
        }

        # TX
        tx1_data = self._parse_json_field(
            self._edit_tx1_data.toPlainText(), "DataOfTxMsg1", {}
        )
        tx2_data = self._parse_json_field(
            self._edit_tx2_data.toPlainText(), "DataOfTxMsg2", {}
        )
        sw1_data = self._parse_json_field(
            self._edit_sw1_data.toPlainText(), "SwitchMsg1 数据", []
        )
        sw2_data = self._parse_json_field(
            self._edit_sw2_data.toPlainText(), "SwitchMsg2 数据", []
        )

        cfg["TX"] = {
            "IdOfTxMsg1": self._get_nullable_spin(self._spin_tx1),
            "TypeOfTxMsg1": self._combo_tx1_type.currentText(),
            "IntervalOfTxMsg1": self._spin_tx1_interval.value(),
            "DataOfTxMsg1": tx1_data,
            "IdOfTxMsg2": self._get_nullable_spin(self._spin_tx2),
            "TypeOfTxMsg2": self._combo_tx2_type.currentText(),
            "IntervalOfTxMsg2": self._spin_tx2_interval.value(),
            "DataOfTxMsg2": tx2_data,
            "PeriodicSwitching": {
                "SwitchMsg1": {
                    "SwitchInterval": self._get_nullable_spin(self._spin_sw1_interval),
                    "Data": sw1_data,
                },
                "SwitchMsg2": {
                    "SwitchInterval": self._get_nullable_spin(self._spin_sw2_interval),
                    "Data": sw2_data,
                },
            },
        }

        # Diag
        is_canfd = self._chk_canfd.isChecked()
        isotp = copy.deepcopy(ISOTP_CANFD if is_canfd else ISOTP_CAN)

        # DidConfig
        did_config: dict = {}
        for row in range(self._table_did.rowCount()):
            did_id = (
                (self._table_did.item(row, 0) or QTableWidgetItem("")).text().strip()
            )
            if not did_id:
                continue
            op_widget = self._table_did.cellWidget(row, 1)
            op = op_widget.currentText() if op_widget else "Read"
            name_val = (
                (self._table_did.item(row, 2) or QTableWidgetItem("")).text().strip()
            )
            size_text = (
                (self._table_did.item(row, 3) or QTableWidgetItem("2")).text().strip()
            )
            type_widget = self._table_did.cellWidget(row, 4)
            type_val = type_widget.currentText() if type_widget else "bytes"
            value_val = (
                (self._table_did.item(row, 5) or QTableWidgetItem("")).text().strip()
            )
            padding_val = (
                (self._table_did.item(row, 6) or QTableWidgetItem("0x20"))
                .text()
                .strip()
            )

            did_config[did_id] = {
                "Operation": op,
                "name": name_val,
                "size": int(size_text) if size_text.isdigit() else 2,
                "type": type_val,
                "value": value_val,
                "Padding": padding_val,
                "offset": None,
            }

        # PeriodicReadDtc
        wl_text = self._edit_dtc_whitelist.text().strip()
        whitelist = (
            [x.strip() for x in wl_text.split(",") if x.strip()] if wl_text else []
        )

        # PeriodicDiag Dids
        dids = self._parse_json_field(
            self._edit_pdiag_dids.toPlainText(), "PeriodicDiag Dids", []
        )

        diag_dict: dict = {
            "SecurityFeedbackBytes": self._spin_security_bytes.value(),
            "DiagPhyAddr": [
                self._spin_diag_req.value(),
                self._spin_diag_resp.value(),
            ],
        }

        # OTA (仅在启用时写入)
        if self._chk_ota_enable.isChecked():
            diag_dict["OTA"] = {
                "DelayAfterAging": self._spin_ota_delay.value(),
                "DelayJudgement": self._spin_ota_judge.value(),
                "Type": self._combo_ota_type.currentText().strip() or "OTAType01",
                "FlashDriver": self._edit_ota_flash.text().strip(),
                "Boot": self._edit_ota_boot.text().strip(),
                "APP": self._edit_ota_app.text().strip(),
                "SlotRetry": self._spin_ota_slot_retry.value(),
                "InterSlotDelay": self._spin_ota_inter_slot_delay.value(),
            }

        diag_dict["DidConfig"] = did_config
        diag_dict["PeriodicReadDtc"] = {
            "Interval": self._spin_dtc_interval.value(),
            "SubFunction": self._spin_dtc_subfunc.value(),
            "DtcStatusMask": self._spin_dtc_mask.value(),
            "WhiteList": whitelist,
        }
        diag_dict["PeriodicDiag"] = {
            "Interval": self._spin_pdiag_interval.value(),
            "ReDiagInterval": self._spin_pdiag_rediag.value(),
            "Dids": dids,
        }
        diag_dict["Params"] = {
            "isotp_params": isotp,
            "default_client_config": copy.deepcopy(DEFAULT_CLIENT_CONFIG),
        }

        cfg["Diag"] = diag_dict

        return name, cfg

    @staticmethod
    def _parse_json_field(text: str, field_name: str, default):
        text = text.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{field_name} JSON格式错误: {e}")

    def _on_save(self) -> None:
        try:
            project_name, config = self._build_config()
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return

        # 读取现有配置
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        if project_name in data:
            ret = QMessageBox.question(
                self,
                "确认覆盖",
                f"项目 '{project_name}' 已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        data[project_name] = config

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        QMessageBox.information(
            self, "保存成功", f"项目 '{project_name}' 已保存到配置文件。"
        )
        self.accept()


# ---------------------------------------------------------------------------
# 管理（编辑 / 删除）已有项目配置
# ---------------------------------------------------------------------------
class ManageProjectConfigDialog(ProjectConfigDialog):
    """图形化管理（更新 / 删除）ProjectConfig.json 中已有项目配置。

    复用 ProjectConfigDialog 的所有 Tab 构建、表单填充及配置构建方法。
    """

    def __init__(self, parent: Optional[QWidget] = None):
        # 跳过 ProjectConfigDialog.__init__，直接调用 QDialog
        QDialog.__init__(self, parent)
        self.setWindowTitle("管理项目配置")
        self.resize(800, 720)
        self._config_path = Path(__file__).parent / "config" / "ProjectConfig.json"
        self._original_name: str = ""  # 记录原始名称，用于检测重命名

        main_layout = QVBoxLayout(self)

        # ---- 顶部: 项目选择 + 删除 ----
        sel_layout = QHBoxLayout()
        sel_layout.addWidget(QLabel("选择项目:"))
        self._combo_project = QComboBox()
        for name in self._load_existing_projects():
            self._combo_project.addItem(name)
        sel_layout.addWidget(self._combo_project, 1)
        btn_delete = QPushButton("删除项目")
        btn_delete.setStyleSheet("color: red;")
        btn_delete.clicked.connect(self._on_delete)
        sel_layout.addWidget(btn_delete)
        main_layout.addLayout(sel_layout)

        # ---- 项目名称（可编辑 → 支持重命名） ----
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("项目名称:"))
        self._edit_name = QLineEdit()
        self._edit_name.setPlaceholderText("项目名称 (修改即重命名)")
        name_layout.addWidget(self._edit_name, 1)
        main_layout.addLayout(name_layout)

        # ---- Tabs（复用父类方法） ----
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_basic_tab(), "基本参数")
        self._tabs.addTab(self._build_comm_tab(), "通信配置")
        self._tabs.addTab(self._build_diag_tab(), "诊断配置")
        main_layout.addWidget(self._tabs, 1)

        # ---- 底部按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存修改")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

        # ---- 选中项目时自动加载 ----
        self._combo_project.currentTextChanged.connect(self._on_project_selected)
        if self._combo_project.count() > 0:
            self._on_project_selected(self._combo_project.currentText())

    # ------------------------------------------------------------------
    # 选择项目 → 自动加载
    # ------------------------------------------------------------------
    def _on_project_selected(self, name: str) -> None:
        if not name:
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if name in data:
                self._fill_from_config(name, data[name])
                self._original_name = name
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 删除项目
    # ------------------------------------------------------------------
    def _on_delete(self) -> None:
        name = self._combo_project.currentText()
        if not name:
            QMessageBox.information(self, "提示", "没有可删除的项目。")
            return

        ret = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除项目 '{name}' 吗？\n此操作不可撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.pop(name, None)
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "删除失败", str(e))
            return

        # 刷新下拉框
        self._combo_project.blockSignals(True)
        self._combo_project.removeItem(self._combo_project.currentIndex())
        self._combo_project.blockSignals(False)

        if self._combo_project.count() > 0:
            self._on_project_selected(self._combo_project.currentText())
        else:
            self._edit_name.clear()
            self._original_name = ""

        QMessageBox.information(self, "删除成功", f"项目 '{name}' 已删除。")

    # ------------------------------------------------------------------
    # 保存（覆盖父类方法，支持重命名）
    # ------------------------------------------------------------------
    def _on_save(self) -> None:  # type: ignore[override]
        try:
            project_name, config = self._build_config()
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

        renamed = self._original_name and self._original_name != project_name

        # 重命名时，若目标名已存在则询问覆盖
        if renamed and project_name in data:
            ret = QMessageBox.question(
                self,
                "确认覆盖",
                f"项目 '{project_name}' 已存在，是否覆盖？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return

        # 重命名：删除旧键
        if renamed:
            data.pop(self._original_name, None)

        data[project_name] = config

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        # 刷新下拉框 & 内部状态
        self._original_name = project_name
        self._combo_project.blockSignals(True)
        self._combo_project.clear()
        for n in self._load_existing_projects():
            self._combo_project.addItem(n)
        self._combo_project.setCurrentText(project_name)
        self._combo_project.blockSignals(False)

        QMessageBox.information(self, "保存成功", f"项目 '{project_name}' 配置已更新。")


# ---------------------------------------------------------------------------
# FuncConfig.json 图形化编辑对话框
# ---------------------------------------------------------------------------
class FuncConfigDialog(QDialog):
    """图形化编辑 FuncConfig.json 所有配置项。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("功能配置 (FuncConfig)")
        self.resize(720, 640)
        self._config_path = Path(__file__).parent / "config" / "FuncConfig.json"

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._data: dict = json.load(f)
        except Exception:
            self._data = {}

        main_layout = QVBoxLayout(self)
        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_ui_tab(), "UI 界面")
        self._tabs.addTab(self._build_logging_tab(), "日志")
        self._tabs.addTab(self._build_canbus_tab(), "CAN总线")
        self._tabs.addTab(self._build_power_tab(), "电源")
        self._tabs.addTab(self._build_txrx_tab(), "收发 / 线程")
        main_layout.addWidget(self._tabs, 1)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存")
        btn_save.clicked.connect(self._on_save)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_save)
        main_layout.addLayout(btn_layout)

    # ================================================================
    # Tab — UI 界面
    # ================================================================
    def _build_ui_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        ui = self._data.get("UI", {})

        self._edit_version = QLineEdit(str(ui.get("Version", "")))
        form.addRow("版本号 (Version):", self._edit_version)

        self._spin_group_count = QSpinBox()
        self._spin_group_count.setRange(1, 10)
        self._spin_group_count.setValue(int(ui.get("GroupCount", 2)))
        form.addRow("分组数量 (GroupCount):", self._spin_group_count)

        self._spin_index_per_group = QSpinBox()
        self._spin_index_per_group.setRange(1, 999)
        self._spin_index_per_group.setValue(int(ui.get("IndexPerGroup", 80)))
        form.addRow("每组穴位数 (IndexPerGroup):", self._spin_index_per_group)

        self._spin_slot_refresh = QDoubleSpinBox()
        self._spin_slot_refresh.setRange(0.1, 60)
        self._spin_slot_refresh.setDecimals(1)
        self._spin_slot_refresh.setSuffix(" s")
        self._spin_slot_refresh.setValue(float(ui.get("SlotRefreshInterval", 0.5)))
        form.addRow("穴位刷新间隔 (SlotRefreshInterval):", self._spin_slot_refresh)

        self._spin_alarm_delay = QSpinBox()
        self._spin_alarm_delay.setRange(0, 9999)
        self._spin_alarm_delay.setSuffix(" s")
        self._spin_alarm_delay.setValue(int(ui.get("AlarmDelaySeconds", 5)))
        form.addRow("报警延迟 (AlarmDelaySeconds):", self._spin_alarm_delay)

        self._edit_operator_list = QLineEdit(",".join(ui.get("OperatorList", [])))
        self._edit_operator_list.setPlaceholderText("逗号分隔, 如: 张三,李四")
        form.addRow("操作员列表 (OperatorList):", self._edit_operator_list)

        self._edit_default_operator = QLineEdit(",".join(ui.get("DefaultOperator", [])))
        self._edit_default_operator.setPlaceholderText("按组逗号分隔, 如: 张三,李四")
        form.addRow("默认操作员 (DefaultOperator):", self._edit_default_operator)

        self._edit_default_project = QLineEdit(",".join(ui.get("DefaultProject", [])))
        self._edit_default_project.setPlaceholderText("按组逗号分隔, 如: Q5012,Q5010A")
        form.addRow("默认项目 (DefaultProject):", self._edit_default_project)

        self._chk_remap = QCheckBox("启用")
        self._chk_remap.setChecked(ui.get("Remap", True))
        form.addRow("穴位重映射 (Remap):", self._chk_remap)

        # ColorMapping
        cm = ui.get("ColorMapping", {})
        grp_color = QGroupBox("颜色映射 (ColorMapping)")
        color_form = QFormLayout(grp_color)
        self._color_edits: dict[str, QLineEdit] = {}
        default_colors = {
            "Idle": "#D3D3D3",
            "good": "#90EE90",
            "Paused": "#FFFF00C5",
            "Warning": "#FF961E",
            "Error": "#FF4500",
        }
        for key, default in default_colors.items():
            edit = QLineEdit(cm.get(key, default))
            edit.setMaximumWidth(150)
            color_form.addRow(f"{key}:", edit)
            self._color_edits[key] = edit
        form.addRow(grp_color)

        # NonRecoverableStatus
        self._edit_non_recoverable = QLineEdit(
            ",".join(str(s) for s in ui.get("NonRecoverableStatus", []))
        )
        self._edit_non_recoverable.setPlaceholderText(
            "逗号分隔整数, 如: -3,-2,-1,2,3,4"
        )
        form.addRow(
            "不可恢复状态码 (NonRecoverableStatus):", self._edit_non_recoverable
        )

        scroll.setWidget(container)
        return scroll

    # ================================================================
    # Tab — 日志
    # ================================================================
    def _build_logging_tab(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        log_cfg = self._data.get("Logging", {})

        self._chk_enable_log = QCheckBox("启用日志")
        self._chk_enable_log.setChecked(log_cfg.get("EnableLogging", True))
        form.addRow("EnableLogging:", self._chk_enable_log)

        self._edit_log_path = QLineEdit(log_cfg.get("LogPath", "logs/app.log"))
        form.addRow("LogPath:", self._edit_log_path)

        self._combo_log_level = QComboBox()
        self._combo_log_level.addItems(
            ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        )
        self._combo_log_level.setCurrentText(log_cfg.get("LogLevel", "DEBUG"))
        form.addRow("LogLevel:", self._combo_log_level)

        self._spin_max_log_size = QSpinBox()
        self._spin_max_log_size.setRange(1, 9999)
        self._spin_max_log_size.setSuffix(" MB")
        self._spin_max_log_size.setValue(int(log_cfg.get("MaxLogFileSizeMB", 100)))
        form.addRow("MaxLogFileSizeMB:", self._spin_max_log_size)

        self._spin_retention = QSpinBox()
        self._spin_retention.setRange(1, 365)
        self._spin_retention.setSuffix(" 天")
        self._spin_retention.setValue(int(log_cfg.get("RetentionPeriod", 3)))
        form.addRow("RetentionPeriod:", self._spin_retention)

        return container

    # ================================================================
    # Tab — CAN总线
    # ================================================================
    def _build_canbus_tab(self) -> QWidget:
        container = QWidget()
        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        can = self._data.get("CanBus", {})

        self._combo_interface = QComboBox()
        self._combo_interface.addItems(["zlg", "pcan", "vector", "socketcan"])
        self._combo_interface.setEditable(True)
        self._combo_interface.setCurrentText(can.get("Interface", "zlg"))
        form.addRow("Interface:", self._combo_interface)

        self._spin_dev_type = QSpinBox()
        self._spin_dev_type.setRange(0, 9999)
        self._spin_dev_type.setValue(int(can.get("DevType", 76)))
        form.addRow("DevType:", self._spin_dev_type)

        self._spin_bitrate = QSpinBox()
        self._spin_bitrate.setRange(1000, 10_000_000)
        self._spin_bitrate.setValue(int(can.get("Bitrate", 500000)))
        self._spin_bitrate.setSuffix(" bps")
        form.addRow("Bitrate:", self._spin_bitrate)

        self._spin_data_bitrate = QSpinBox()
        self._spin_data_bitrate.setRange(1000, 10_000_000)
        self._spin_data_bitrate.setValue(int(can.get("DataBitrate", 2000000)))
        self._spin_data_bitrate.setSuffix(" bps")
        form.addRow("DataBitrate:", self._spin_data_bitrate)

        self._chk_recv_own = QCheckBox("启用")
        self._chk_recv_own.setChecked(can.get("ReceiveOwnMessages", True))
        form.addRow("ReceiveOwnMessages:", self._chk_recv_own)

        self._chk_fd = QCheckBox("CANFD 模式")
        self._chk_fd.setChecked(can.get("FD", True))
        form.addRow("FD:", self._chk_fd)

        return container

    # ================================================================
    # Tab — 电源
    # ================================================================
    def _build_power_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        form = QFormLayout(container)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        ps = self._data.get("PowerSupply", {})

        self._combo_ps_type = QComboBox()
        self._combo_ps_type.addItems(["DCPS1216", "DY4010", ""])
        self._combo_ps_type.setEditable(True)
        self._combo_ps_type.setCurrentText(ps.get("Type", "DCPS1216"))
        form.addRow("Type:", self._combo_ps_type)

        self._edit_com_port = QLineEdit(",".join(ps.get("ComPort", [])))
        self._edit_com_port.setPlaceholderText("逗号分隔, 如: COM3,COM4")
        form.addRow("ComPort:", self._edit_com_port)

        self._edit_output_current_limit = QLineEdit(
            ",".join(str(x) for x in ps.get("OutputCurrentLimit", []))
        )
        self._edit_output_current_limit.setPlaceholderText("逗号分隔, 如: 100,100")
        form.addRow("OutputCurrentLimit:", self._edit_output_current_limit)

        self._edit_voltage_offset = QLineEdit(
            ",".join(str(x) for x in ps.get("VoltageOffset", []))
        )
        self._edit_voltage_offset.setPlaceholderText("逗号分隔, 如: 0.5,0.5")
        form.addRow("VoltageOffset:", self._edit_voltage_offset)

        self._spin_baud_rate = QSpinBox()
        self._spin_baud_rate.setRange(300, 1_000_000)
        self._spin_baud_rate.setValue(int(ps.get("BaudRate", 9600)))
        form.addRow("BaudRate:", self._spin_baud_rate)

        self._spin_group_per_ps = QSpinBox()
        self._spin_group_per_ps.setRange(1, 100)
        self._spin_group_per_ps.setValue(int(ps.get("GroupPerPowerSupply", 1)))
        form.addRow("GroupPerPowerSupply:", self._spin_group_per_ps)

        self._spin_dark_current = QDoubleSpinBox()
        self._spin_dark_current.setRange(0, 99999)
        self._spin_dark_current.setDecimals(1)
        self._spin_dark_current.setSuffix(" mA")
        self._spin_dark_current.setValue(float(ps.get("DarkCurrent", 5.0)))
        form.addRow("DarkCurrent:", self._spin_dark_current)

        scroll.setWidget(container)
        return scroll

    # ================================================================
    # Tab — 收发 / 线程
    # ================================================================
    def _build_txrx_tab(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)

        # ---- Tx ----
        grp_tx = QGroupBox("发送 (Tx)")
        tx_form = QFormLayout(grp_tx)
        tx = self._data.get("Tx", {})

        self._chk_retrans = QCheckBox("启用")
        self._chk_retrans.setChecked(tx.get("RetransmissionMechanism", True))
        tx_form.addRow("RetransmissionMechanism:", self._chk_retrans)

        self._spin_retrans_times = QSpinBox()
        self._spin_retrans_times.setRange(0, 100)
        self._spin_retrans_times.setValue(int(tx.get("RetransmissionTimes", 3)))
        tx_form.addRow("RetransmissionTimes:", self._spin_retrans_times)

        self._spin_retrans_interval = QDoubleSpinBox()
        self._spin_retrans_interval.setRange(0.01, 60)
        self._spin_retrans_interval.setDecimals(2)
        self._spin_retrans_interval.setSuffix(" s")
        self._spin_retrans_interval.setValue(
            float(tx.get("RetransmissionInterval", 0.1))
        )
        tx_form.addRow("RetransmissionInterval:", self._spin_retrans_interval)

        layout.addWidget(grp_tx)

        # ---- Rx ----
        grp_rx = QGroupBox("接收 (Rx)")
        rx_form = QFormLayout(grp_rx)
        rx = self._data.get("Rx", {})

        self._spin_times_change = QSpinBox()
        self._spin_times_change.setRange(1, 100)
        self._spin_times_change.setValue(int(rx.get("TimesToChangeStatus", 3)))
        rx_form.addRow("TimesToChangeStatus:", self._spin_times_change)

        self._chk_status_reset = QCheckBox("启用")
        self._chk_status_reset.setChecked(rx.get("StatusReset", True))
        rx_form.addRow("StatusReset:", self._chk_status_reset)

        self._spin_times_reset = QSpinBox()
        self._spin_times_reset.setRange(1, 100)
        self._spin_times_reset.setValue(int(rx.get("TimesToResetStatus", 5)))
        rx_form.addRow("TimesToResetStatus:", self._spin_times_reset)

        layout.addWidget(grp_rx)

        # ---- Threading ----
        grp_thread = QGroupBox("线程 (Threading)")
        th_form = QFormLayout(grp_thread)
        th = self._data.get("Threading", {})

        self._spin_sched_gran = QDoubleSpinBox()
        self._spin_sched_gran.setRange(0.01, 10)
        self._spin_sched_gran.setDecimals(2)
        self._spin_sched_gran.setSuffix(" s")
        self._spin_sched_gran.setValue(float(th.get("SchedulingGranularity", 0.1)))
        th_form.addRow("SchedulingGranularity:", self._spin_sched_gran)

        layout.addWidget(grp_thread)
        layout.addStretch(1)

        return container

    # ================================================================
    # 构建配置 & 保存
    # ================================================================
    def _build_func_config(self) -> dict:
        """从所有表单字段收集并返回完整的 FuncConfig 字典。"""
        cfg: dict = {}

        # --- UI ---
        operator_list = [
            s.strip() for s in self._edit_operator_list.text().split(",") if s.strip()
        ]
        default_operator = [
            s.strip()
            for s in self._edit_default_operator.text().split(",")
            if s.strip()
        ]
        default_project = [
            s.strip() for s in self._edit_default_project.text().split(",") if s.strip()
        ]
        nrs_text = self._edit_non_recoverable.text().strip()
        non_recoverable = []
        if nrs_text:
            try:
                non_recoverable = [
                    int(x.strip()) for x in nrs_text.split(",") if x.strip()
                ]
            except ValueError:
                raise ValueError("不可恢复状态码格式错误，请使用逗号分隔的整数")

        color_mapping = {
            k: edit.text().strip() for k, edit in self._color_edits.items()
        }

        cfg["UI"] = {
            "Version": self._edit_version.text().strip(),
            "GroupCount": self._spin_group_count.value(),
            "IndexPerGroup": self._spin_index_per_group.value(),
            "SlotRefreshInterval": self._spin_slot_refresh.value(),
            "AlarmDelaySeconds": self._spin_alarm_delay.value(),
            "OperatorList": operator_list,
            "DefaultOperator": default_operator,
            "DefaultProject": default_project,
            "Remap": self._chk_remap.isChecked(),
            "ColorMapping": color_mapping,
            "NonRecoverableStatus": non_recoverable,
        }

        # --- Logging ---
        cfg["Logging"] = {
            "EnableLogging": self._chk_enable_log.isChecked(),
            "LogPath": self._edit_log_path.text().strip(),
            "LogLevel": self._combo_log_level.currentText(),
            "MaxLogFileSizeMB": self._spin_max_log_size.value(),
            "RetentionPeriod": self._spin_retention.value(),
        }

        # --- CanBus ---
        cfg["CanBus"] = {
            "Interface": self._combo_interface.currentText().strip(),
            "DevType": self._spin_dev_type.value(),
            "Bitrate": self._spin_bitrate.value(),
            "DataBitrate": self._spin_data_bitrate.value(),
            "ReceiveOwnMessages": self._chk_recv_own.isChecked(),
            "FD": self._chk_fd.isChecked(),
        }

        # --- PowerSupply ---
        com_ports = [
            s.strip() for s in self._edit_com_port.text().split(",") if s.strip()
        ]
        try:
            ocl = [
                int(x.strip())
                for x in self._edit_output_current_limit.text().split(",")
                if x.strip()
            ]
        except ValueError:
            raise ValueError("OutputCurrentLimit 格式错误，请使用逗号分隔的整数")
        try:
            vo = [
                float(x.strip())
                for x in self._edit_voltage_offset.text().split(",")
                if x.strip()
            ]
        except ValueError:
            raise ValueError("VoltageOffset 格式错误，请使用逗号分隔的数字")

        cfg["PowerSupply"] = {
            "Type": self._combo_ps_type.currentText().strip(),
            "ComPort": com_ports,
            "OutputCurrentLimit": ocl,
            "VoltageOffset": vo,
            "BaudRate": self._spin_baud_rate.value(),
            "GroupPerPowerSupply": self._spin_group_per_ps.value(),
            "DarkCurrent": self._spin_dark_current.value(),
        }

        # --- Tx ---
        cfg["Tx"] = {
            "RetransmissionMechanism": self._chk_retrans.isChecked(),
            "RetransmissionTimes": self._spin_retrans_times.value(),
            "RetransmissionInterval": self._spin_retrans_interval.value(),
        }

        # --- Rx ---
        cfg["Rx"] = {
            "TimesToChangeStatus": self._spin_times_change.value(),
            "StatusReset": self._chk_status_reset.isChecked(),
            "TimesToResetStatus": self._spin_times_reset.value(),
        }

        # --- Threading ---
        cfg["Threading"] = {
            "SchedulingGranularity": self._spin_sched_gran.value(),
        }

        return cfg

    def _on_save(self) -> None:
        try:
            config = self._build_func_config()
        except ValueError as e:
            QMessageBox.warning(self, "输入错误", str(e))
            return

        try:
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))
            return

        QMessageBox.information(self, "保存成功", "功能配置已保存到 FuncConfig.json。")
        self.accept()


# ---------------------------------------------------------------------------
# 手动更新对话框 — 解压更新包并自动重启
# ---------------------------------------------------------------------------

# 特殊文件名 → 目标子目录（优先于扩展名规则）
_SPECIAL_FILE_MAP: dict[str, str] = {
    "main_widget_ui.py": "ui",
    "main_widget.ui": "ui",
}

# 文件扩展名 → 目标子目录（相对于项目根目录）
_EXT_DIR_MAP: dict[str, str] = {
    ".json": "config",
    ".dbc": "dbc",
    ".dll": "dll",
    ".hex": "ota",
    ".ui": "ui",
    ".py": "",  # 根目录
}


class ManualUpdateDialog(QDialog):
    """选择更新压缩包 (.zip)，按文件类型分发到对应目录后自动重启。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("手动更新")
        self.resize(560, 400)
        self._root = Path(__file__).parent

        layout = QVBoxLayout(self)

        # ---- 选择文件 ----
        h_file = QHBoxLayout()
        h_file.addWidget(QLabel("更新包路径:"))
        self._edit_zip = QLineEdit()
        self._edit_zip.setPlaceholderText("选择 .zip 更新包")
        btn_browse = QPushButton("浏览")
        btn_browse.clicked.connect(self._browse_zip)
        h_file.addWidget(self._edit_zip, 1)
        h_file.addWidget(btn_browse)
        layout.addLayout(h_file)

        # ---- 说明 ----
        lbl_info = QLabel(
            "说明:\n"
            "  • .json → config/\n"
            "  • .dbc  → dbc/\n"
            "  • .dll  → dll/\n"
            "  • .hex  → ota/\n"
            "  • .ui   → ui/\n"
            "  • .py   → 根目录\n"
            "  • main_widget_ui.py / main_widget.ui → ui/\n"
            "  • FuncConfig.json 更新时自动保留本地电源配置\n"
            "  • 同名文件将被覆盖，不同名文件则新增\n"
            "  • 更新完成后软件将自动重启"
        )
        lbl_info.setStyleSheet("color: #555; padding: 8px;")
        layout.addWidget(lbl_info)

        # ---- 预览 ----
        self._preview = QPlainTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("选择更新包后将在此预览文件分发计划……")
        layout.addWidget(self._preview, 1)

        # ---- 按钮 ----
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        self._btn_update = QPushButton("执行更新")
        self._btn_update.setEnabled(False)
        self._btn_update.clicked.connect(self._on_update)
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(self._btn_update)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    def _browse_zip(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "选择更新包", "", "ZIP Files (*.zip)"
        )
        if not path:
            return
        self._edit_zip.setText(path)
        self._preview_zip(path)

    def _preview_zip(self, zip_path: str) -> None:
        """预览压缩包内文件及其分发目标。"""
        lines: list[str] = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    fname = Path(info.filename).name
                    # 特殊文件名优先匹配
                    if fname in _SPECIAL_FILE_MAP:
                        target_dir = _SPECIAL_FILE_MAP[fname]
                    else:
                        ext = Path(fname).suffix.lower()
                        target_dir = _EXT_DIR_MAP.get(ext)
                    if target_dir is None:
                        lines.append(f"  [跳过] {fname}  (不支持的类型 {ext})")
                    else:
                        dest = Path(target_dir) / fname if target_dir else Path(fname)
                        target_full = self._root / dest
                        action = "覆盖" if target_full.exists() else "新增"
                        extra = ""
                        if fname == "FuncConfig.json":
                            extra = "  (保留本地 PowerSupply)"
                        lines.append(f"  [{action}] {fname}  → {dest}{extra}")
        except Exception as e:
            lines.append(f"  [错误] 无法读取压缩包: {e}")

        if not lines:
            lines.append("  压缩包为空或不包含支持的文件类型。")

        self._preview.setPlainText("\n".join(lines))
        has_files = any("[跳过]" not in l and "[错误]" not in l for l in lines)
        self._btn_update.setEnabled(has_files)

    # ------------------------------------------------------------------
    def _on_update(self) -> None:
        zip_path = self._edit_zip.text().strip()
        if not zip_path or not Path(zip_path).is_file():
            QMessageBox.warning(self, "错误", "请选择有效的 .zip 更新包。")
            return

        ret = QMessageBox.question(
            self,
            "确认更新",
            "执行更新后软件将自动重启，是否继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        errors: list[str] = []
        deployed: list[str] = []
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    fname = Path(info.filename).name
                    # 特殊文件名优先匹配
                    if fname in _SPECIAL_FILE_MAP:
                        target_dir = _SPECIAL_FILE_MAP[fname]
                    else:
                        ext = Path(fname).suffix.lower()
                        target_dir = _EXT_DIR_MAP.get(ext)
                    if target_dir is None:
                        continue
                    dest_dir = self._root / target_dir if target_dir else self._root
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    dest_file = dest_dir / fname
                    try:
                        data = zf.read(info.filename)
                        # FuncConfig.json 特殊处理: 保留 PowerSupply
                        if fname == "FuncConfig.json":
                            data = self._merge_func_config(data, dest_file)
                        with open(dest_file, "wb") as out:
                            out.write(data)
                        deployed.append(str(dest_file.relative_to(self._root)))
                    except Exception as e:
                        errors.append(f"{fname}: {e}")
        except Exception as e:
            QMessageBox.critical(self, "解压失败", str(e))
            return

        if errors:
            QMessageBox.warning(self, "部分文件部署失败", "\n".join(errors))

        if not deployed:
            QMessageBox.information(self, "提示", "没有文件被部署。")
            return

        # 重启应用
        QMessageBox.information(
            self,
            "更新完成",
            f"已部署 {len(deployed)} 个文件:\n"
            + "\n".join(f"  • {f}" for f in deployed)
            + "\n\n点击确定后将自动重启软件。",
        )
        self._restart_app()

    @staticmethod
    def _merge_func_config(new_data: bytes, dest_file: Path) -> bytes:
        """合并 FuncConfig.json: 用新配置覆盖，但保留本地 PowerSupply 段。"""
        try:
            new_cfg = json.loads(new_data.decode("utf-8"))
        except Exception:
            return new_data  # 解析失败则原样写入
        if not dest_file.exists():
            return new_data  # 本地无旧文件，直接使用新配置
        try:
            with open(dest_file, "r", encoding="utf-8") as f:
                old_cfg = json.load(f)
        except Exception:
            return new_data
        # 用旧的 PowerSupply 覆盖新配置中的 PowerSupply
        if "PowerSupply" in old_cfg:
            new_cfg["PowerSupply"] = old_cfg["PowerSupply"]
        return json.dumps(new_cfg, indent=4, ensure_ascii=False).encode("utf-8")

    @staticmethod
    def _restart_app() -> None:
        """关闭当前进程并重新启动。"""
        python = sys.executable
        script = str(Path(__file__).parent / "main.py")
        subprocess.Popen([python, script], cwd=str(Path(__file__).parent))
        # 退出当前应用
        app = QApplication.instance()
        if app:
            app.quit()
