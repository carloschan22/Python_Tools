"""ProjectConfig.json 项目配置图形化工具

提供 ProjectConfigDialog 对话框，让用户无需手动编辑 JSON 即可新增 / 编辑项目配置。
Diag.Params.isotp_params 根据 CAN FD 开关自动填充预设模板；
default_client_config 始终使用统一默认值。
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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

        cfg["Diag"] = {
            "SecurityFeedbackBytes": self._spin_security_bytes.value(),
            "DiagPhyAddr": [
                self._spin_diag_req.value(),
                self._spin_diag_resp.value(),
            ],
            "DidConfig": did_config,
            "PeriodicReadDtc": {
                "Interval": self._spin_dtc_interval.value(),
                "SubFunction": self._spin_dtc_subfunc.value(),
                "DtcStatusMask": self._spin_dtc_mask.value(),
                "WhiteList": whitelist,
            },
            "PeriodicDiag": {
                "Interval": self._spin_pdiag_interval.value(),
                "ReDiagInterval": self._spin_pdiag_rediag.value(),
                "Dids": dids,
            },
            "Params": {
                "isotp_params": isotp,
                "default_client_config": copy.deepcopy(DEFAULT_CLIENT_CONFIG),
            },
        }

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
