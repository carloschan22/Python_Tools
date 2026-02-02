from __future__ import annotations

import re
import sys
import time
import Tools
import threading
from math import ceil


from typing import Optional
from datetime import datetime, timedelta
from ui.main_widget_ui import Ui_MainWidget
from CompManager import ComponentsInstantiation
from DataBaseWorker import DataBaseWorker
from Tools import COLOR_MAPPING, FUNCTION_CONFIG, PROJECT_CONFIG
from PySide6.QtCore import Qt, Signal, QThread, Slot, QTimer
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)


class Connector(QWidget):
    def __init__(
        self, ui: Ui_MainWidget, app: Optional[ComponentsInstantiation] = None
    ):
        super().__init__()
        self.ui = ui
        self.app = app
        self._workers: dict[int, AgingThread] = {}
        self._apps: dict[int, ComponentsInstantiation] = {}
        self._group_count = int(FUNCTION_CONFIG.get("UI", {}).get("GroupCount", 1))
        self._group_state: dict[int, dict] = {
            i: {
                "running": False,
                "paused": False,
                "start_time": None,
                "paused_at": None,
                "paused_duration": 0.0,
                "aging_hours": None,
                "tx_started": False,
            }
            for i in range(1, self._group_count + 1)
        }
        self._slot_status: dict[int, dict[int, int]] = {
            i: {} for i in range(1, self._group_count + 1)
        }
        self._db_worker = DataBaseWorker()
        self._db_worker.initialization()
        self._db_worker.start_writing()
        self._group_table: dict[int, str] = {}
        self.ui.setupUi(self)
        self._init_nav()
        self._apply_ui_config()
        self._init_controls()
        self._bind_slot_clicks()

        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(1000)
        self._runtime_timer.timeout.connect(self._update_runtime_labels)
        self._runtime_timer.start()

    def _init_nav(self) -> None:
        self.ui.action_home.triggered.connect(
            lambda: self.ui.stackedPages.setCurrentWidget(self.ui.page_home)
        )
        self.ui.action_history.triggered.connect(
            lambda: self.ui.stackedPages.setCurrentWidget(self.ui.page_history)
        )
        self.ui.action_about.triggered.connect(
            lambda: self.ui.stackedPages.setCurrentWidget(self.ui.page_about)
        )

    def _apply_ui_config(self) -> None:
        ui_cfg = Tools.FUNCTION_CONFIG.get("UI", {})
        group_count = int(ui_cfg.get("GroupCount", 1))
        slots_per_group = int(ui_cfg.get("IndexPerGroup", 80))
        fixed_rows = 5

        groups = []
        for idx in range(1, 4):
            group_box = getattr(self.ui, f"groupBox_{idx}", None)
            table = getattr(self.ui, f"iconTable_{idx}", None)
            icon_frame = getattr(self.ui, f"iconFrame_{idx}", None)
            control_frame = getattr(self.ui, f"controlFrame_{idx}", None)
            control_layout = getattr(self.ui, f"controlLayout_{idx}", None)
            group_layout = getattr(self.ui, f"groupLayout_{idx}", None)
            if group_box is not None and table is not None:
                groups.append(
                    (group_box, table, icon_frame, control_frame, group_layout)
                )

        for i, (group_box, table, icon_frame, control_frame, group_layout) in enumerate(
            groups, start=1
        ):
            visible = i <= group_count
            group_box.setVisible(visible)
            if not visible:
                continue
            group_box.setTitle(f"第{i}组")
            self._render_slots(table, slots_per_group, fixed_rows)

            if icon_frame is not None:
                icon_frame.setSizePolicy(
                    QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
                )
            if control_frame is not None:
                control_frame.setSizePolicy(
                    QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
                )
                control_frame.setStyleSheet(
                    "QLabel{min-height:22px; max-height:22px;}"
                    "QLineEdit{min-height:22px; max-height:22px;}"
                    "QComboBox{min-height:22px; max-height:22px;}"
                    "QPushButton{min-height:24px; max-height:24px;}"
                )
            if control_layout is not None:
                control_layout.setHorizontalSpacing(6)
                control_layout.setVerticalSpacing(6)
                for row in range(7):
                    control_layout.setRowMinimumHeight(row, 24)
                    control_layout.setRowStretch(row, 0)
            if group_layout is not None:
                group_layout.setStretch(0, 1)
                group_layout.setStretch(1, 0)

        # 细化页面边距与间距, 提升布局紧凑度
        self.ui.homeLayout.setContentsMargins(6, 6, 6, 6)
        self.ui.homeLayout.setSpacing(8)

    def _init_controls(self) -> None:
        self._populate_combo_options()
        self._bind_selects()
        self._bind_start_clicks()
        self._bind_pause_clicks()
        self._bind_stop_clicks()

    def _populate_combo_options(self) -> None:
        projects = list(PROJECT_CONFIG.keys())
        ui_cfg = FUNCTION_CONFIG.get("UI", {})
        default_project = ui_cfg.get("DefaultProject", projects[0] if projects else "")
        operators = list(ui_cfg.get("OperatorList", []))
        default_operator = ui_cfg.get(
            "DefaultOperator", operators[0] if operators else ""
        )

        for group_index in range(1, self._group_count + 1):
            combo_product = getattr(self.ui, f"combo_product_{group_index}", None)
            combo_aging_time = getattr(self.ui, f"combo_aging_time_{group_index}", None)
            combo_worker = getattr(self.ui, f"combo_worker_{group_index}", None)

            if combo_product is not None:
                combo_product.blockSignals(True)
                combo_product.clear()
                for p in projects:
                    combo_product.addItem(p)
                if default_project:
                    combo_product.setCurrentText(default_project)
                combo_product.blockSignals(False)

            project = (
                combo_product.currentText()
                if combo_product is not None
                else default_project
            )
            self._refresh_aging_time_combo(group_index, project)

            if combo_worker is not None:
                combo_worker.blockSignals(True)
                combo_worker.clear()
                for name in operators:
                    combo_worker.addItem(name)
                if default_operator:
                    combo_worker.setCurrentText(default_operator)
                combo_worker.blockSignals(False)

    def _refresh_aging_time_combo(self, group_index: int, project: str) -> None:
        combo_aging_time = getattr(self.ui, f"combo_aging_time_{group_index}", None)
        if combo_aging_time is None:
            return
        aging_times = PROJECT_CONFIG.get(project, {}).get("老化时长", [])
        default_aging = PROJECT_CONFIG.get(project, {}).get("默认老化时长")

        combo_aging_time.blockSignals(True)
        combo_aging_time.clear()
        for t in aging_times:
            combo_aging_time.addItem(str(t), t)
        if default_aging is not None:
            combo_aging_time.setCurrentText(str(default_aging))
        combo_aging_time.blockSignals(False)

        if aging_times:
            self._group_state[group_index]["aging_hours"] = float(
                combo_aging_time.currentData() or combo_aging_time.currentText()
            )
        else:
            self._group_state[group_index]["aging_hours"] = None

    def _bind_selects(self) -> None:
        for group_index in range(1, self._group_count + 1):
            combo_product = getattr(self.ui, f"combo_product_{group_index}", None)
            combo_aging_time = getattr(self.ui, f"combo_aging_time_{group_index}", None)
            combo_worker = getattr(self.ui, f"combo_worker_{group_index}", None)
            if combo_product is not None:
                combo_product.currentIndexChanged.connect(self._on_select_changed)
            if combo_aging_time is not None:
                combo_aging_time.currentIndexChanged.connect(self._on_select_changed)
            if combo_worker is not None:
                combo_worker.currentIndexChanged.connect(self._on_select_changed)

    def _render_slots(self, table: QTableWidget, slot_count: int, rows: int) -> None:
        cols = int(ceil(slot_count / rows)) if rows > 0 else slot_count
        rows = max(1, rows)

        table.clear()
        table.setRowCount(rows)
        table.setColumnCount(cols)
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        table.setShowGrid(True)
        table.horizontalHeader().setVisible(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setDefaultSectionSize(28)
        table.verticalHeader().setDefaultSectionSize(28)
        table.horizontalHeader().setSectionResizeMode(
            table.horizontalHeader().ResizeMode.Stretch
        )
        table.verticalHeader().setSectionResizeMode(
            table.verticalHeader().ResizeMode.Stretch
        )

        for slot in range(1, slot_count + 1):
            r = (slot - 1) // cols
            c = (slot - 1) % cols
            item = QTableWidgetItem(str(slot))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(r, c, item)

        # 清空多余单元格
        for r in range(rows):
            for c in range(cols):
                slot = r * cols + c + 1
                if slot > slot_count:
                    table.setItem(r, c, QTableWidgetItem(""))

    def _bind_slot_clicks(self) -> None:
        for idx in range(1, 4):
            table = getattr(self.ui, f"iconTable_{idx}", None)
            if table is None:
                continue
            table.cellClicked.connect(
                lambda row, col, g=idx, t=table: self._on_slot_clicked(g, t, row, col)
            )

    def _on_slot_clicked(
        self, group_index: int, table: QTableWidget, row: int, col: int
    ) -> None:
        item = table.item(row, col)
        if item is None:
            return
        text = item.text().strip()
        if not text:
            return
        try:
            slot_no = int(text)
        except ValueError:
            return
        dialog = SlotDetailDialog(self, group_index, slot_no)
        dialog.exec()

    def on_slot_status_changed(
        self, group_index: int, slot_no: int, status: int
    ) -> None:
        """根据状态变更某个槽位的显示颜色"""
        self._slot_status.setdefault(group_index, {})[slot_no] = status
        self._slot_change_color(group_index, slot_no, status)

    def _slot_change_color(self, group_index: int, slot_no: int, status: int) -> None:
        """变更某个槽位的显示颜色"""
        state = self._group_state.get(group_index, {})
        if state.get("paused"):
            return
        table = getattr(self.ui, f"iconTable_{group_index}", None)
        if table is None:
            return
        cols = table.columnCount()
        rows = table.rowCount()
        if cols <= 0 or rows <= 0:
            return
        r = (slot_no - 1) // cols
        c = (slot_no - 1) % cols
        if r >= rows:
            return
        item = table.item(r, c)
        if item is None:
            item = QTableWidgetItem(str(slot_no))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            table.setItem(r, c, item)

        key = self._map_status_to_color(status)
        if key is None:
            return
        color = COLOR_MAPPING.get(key, "#D3D3D3")
        item.setBackground(QColor(color))

    def _on_select_changed(self, index: int) -> None:
        sender = self.sender()
        if sender is None:
            return
        name = sender.objectName()
        group_index = self._extract_group_index(name)
        if group_index is None:
            return

        if name.startswith("combo_product_"):
            project = sender.currentText()
            self._refresh_aging_time_combo(group_index, project)
            self._update_end_time(group_index)
        elif name.startswith("combo_aging_time_"):
            self._group_state[group_index]["aging_hours"] = self._get_group_aging_hours(
                group_index
            )
            self._update_end_time(group_index)

    def _bind_start_clicks(self) -> None:
        for group_index in range(1, self._group_count + 1):
            btn = getattr(self.ui, f"btn_start_{group_index}", None)
            if btn is not None:
                btn.clicked.connect(self._on_start_clicked)

    def _on_start_clicked(self) -> None:
        group_index = self._extract_group_index_from_sender()
        if group_index is None:
            return
        state = self._group_state[group_index]
        if state["running"]:
            self._stop_group(group_index)
        else:
            self._start_group(group_index)

    def _bind_pause_clicks(self) -> None:
        for group_index in range(1, self._group_count + 1):
            btn = getattr(self.ui, f"btn_pause_{group_index}", None)
            if btn is not None:
                btn.clicked.connect(self._on_pause_clicked)

    def _on_pause_clicked(self) -> None:
        group_index = self._extract_group_index_from_sender()
        if group_index is None:
            return
        state = self._group_state[group_index]
        if not state["running"]:
            return
        if state["paused"]:
            self._resume_group(group_index)
        else:
            self._pause_group(group_index)

    def _bind_stop_clicks(self) -> None:
        btn_stop = getattr(self.ui, "btn_history_force_stop", None)
        if btn_stop is not None:
            btn_stop.clicked.connect(self._on_stop_clicked)

    def _on_stop_clicked(self) -> None:
        for group_index in range(1, self._group_count + 1):
            self._stop_group(group_index)

    def _extract_group_index_from_sender(self) -> Optional[int]:
        sender = self.sender()
        if sender is None:
            return None
        return self._extract_group_index(sender.objectName())

    @staticmethod
    def _extract_group_index(name: str) -> Optional[int]:
        match = re.search(r"_(\d+)$", name or "")
        if not match:
            return None
        return int(match.group(1))

    def _get_group_aging_hours(self, group_index: int) -> Optional[float]:
        combo = getattr(self.ui, f"combo_aging_time_{group_index}", None)
        if combo is None:
            return None
        data = combo.currentData()
        try:
            if data is not None:
                return float(data)
            return float(combo.currentText())
        except Exception:
            return None

    def _update_start_end_time_labels(self, group_index: int) -> None:
        start_label = getattr(self.ui, f"text_start_time_{group_index}", None)
        end_label = getattr(self.ui, f"text_end_time_{group_index}", None)
        state = self._group_state[group_index]
        if start_label is not None and state["start_time"]:
            start_label.setText(
                datetime.fromtimestamp(state["start_time"]).strftime("%Y-%m-%d %H:%M")
            )
        self._update_end_time(group_index)

    def _update_end_time(self, group_index: int) -> None:
        state = self._group_state[group_index]
        end_label = getattr(self.ui, f"text_end_time_{group_index}", None)
        if end_label is None:
            return
        if not state["running"] or not state["start_time"]:
            end_label.setText("--")
            return
        aging_hours = self._get_group_aging_hours(group_index)
        if aging_hours is None:
            end_label.setText("--")
            return
        end_time = datetime.fromtimestamp(state["start_time"]) + timedelta(
            hours=float(aging_hours)
        )
        end_label.setText(end_time.strftime("%Y-%m-%d %H:%M"))

    def _update_runtime_labels(self) -> None:
        now = time.time()
        for group_index in range(1, self._group_count + 1):
            state = self._group_state[group_index]
            if not state["running"] or state["paused"] or not state["start_time"]:
                continue
            elapsed = now - state["start_time"] - state["paused_duration"]
            elapsed = max(0.0, elapsed)
            runtime_text = self._format_duration(elapsed)
            runtime_edit = getattr(self.ui, f"edit_runtime_{group_index}", None)
            if runtime_edit is not None:
                runtime_edit.setText(runtime_text)

            aging_hours = self._get_group_aging_hours(group_index)
            remaining_edit = getattr(self.ui, f"edit_remaining_{group_index}", None)
            if remaining_edit is None:
                continue
            if aging_hours is None:
                remaining_edit.setText("--")
                continue
            total = float(aging_hours) * 3600
            remaining = max(0.0, total - elapsed)
            remaining_edit.setText(self._format_duration(remaining))

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _reset_group_labels(self, group_index: int) -> None:
        runtime_edit = getattr(self.ui, f"edit_runtime_{group_index}", None)
        remaining_edit = getattr(self.ui, f"edit_remaining_{group_index}", None)
        start_label = getattr(self.ui, f"text_start_time_{group_index}", None)
        end_label = getattr(self.ui, f"text_end_time_{group_index}", None)
        if runtime_edit is not None:
            runtime_edit.setText("00:00:00")
        if remaining_edit is not None:
            remaining_edit.setText("00:00:00")
        if start_label is not None:
            start_label.setText("--")
        if end_label is not None:
            end_label.setText("--")

    def _set_group_buttons_running(
        self, group_index: int, running: bool, paused: bool = False
    ) -> None:
        app = self._get_group_app(group_index)
        app_started = getattr(app, "_started", False)
        if running and not app_started:
            app.startup()
        elif not running and app_started:
            app.shutdown()

        selected_project = getattr(self.ui, f"combo_product_{group_index}", None)
        selected_duration = getattr(self.ui, f"combo_aging_time_{group_index}", None)
        selected_operator = getattr(self.ui, f"combo_worker_{group_index}", None)
        Tools.refresh_ui_config(
            selected_project.currentText() if selected_project else "",
            selected_duration.currentText() if selected_duration else "",
            selected_operator.currentText() if selected_operator else "",
        )
        btn_start = getattr(self.ui, f"btn_start_{group_index}", None)
        btn_pause = getattr(self.ui, f"btn_pause_{group_index}", None)
        if btn_start is not None:
            if running:
                btn_start.setEnabled(True)
                btn_start.setText("停止老化")
            else:
                btn_start.setEnabled(True)
                btn_start.setText("启动老化")
        if btn_pause is not None:
            btn_pause.setEnabled(running)
            if paused:
                btn_pause.setText("继续")
            else:
                btn_pause.setText("暂停")

    def _set_group_color(
        self, group_index: int, key: str, only_status_nonzero: bool = False
    ) -> None:
        table = getattr(self.ui, f"iconTable_{group_index}", None)
        if table is None:
            return
        color = COLOR_MAPPING.get(key, "#D3D3D3")
        status_map = self._slot_status.get(group_index, {})
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is None:
                    continue
                text = item.text().strip()
                if not text:
                    continue
                if only_status_nonzero:
                    try:
                        slot_no = int(text)
                    except ValueError:
                        continue
                    if status_map.get(slot_no, 0) == 0:
                        continue
                item.setBackground(QColor(color))

    def _clear_group_color(self, group_index: int) -> None:
        table = getattr(self.ui, f"iconTable_{group_index}", None)
        if table is None:
            return
        clear_brush = QBrush()
        for r in range(table.rowCount()):
            for c in range(table.columnCount()):
                item = table.item(r, c)
                if item is None:
                    continue
                if not item.text().strip():
                    continue
                item.setBackground(clear_brush)

    def _refresh_group_colors(self, group_index: int) -> None:
        status_map = self._slot_status.get(group_index, {})
        for slot_no, status in status_map.items():
            self._slot_change_color(group_index, slot_no, status)

    def _ensure_worker(self, group_index: int) -> AgingThread:
        worker = self._workers.get(group_index)
        if worker is not None and worker.isRunning():
            return worker
        app = self._get_group_app(group_index)
        table_name = self._group_table.get(group_index)
        if table_name is None:
            table_name = self._db_worker.create_new_table()
            self._group_table[group_index] = table_name
        worker = AgingThread(
            app,
            group_index=group_index,
            db_worker=self._db_worker,
            table_name=table_name,
        )
        worker.slot_status_changed.connect(self.on_slot_status_changed)
        self._workers[group_index] = worker
        return worker

    def _start_group(self, group_index: int) -> None:
        state = self._group_state[group_index]
        now = time.time()
        app = self._get_group_app(group_index)

        if group_index not in self._group_table:
            self._group_table[group_index] = self._db_worker.create_new_table()

        if not getattr(app, "_started", False):
            app.startup()

        if state["paused"]:
            paused_at = state.get("paused_at") or now
            state["paused_duration"] += max(0.0, now - paused_at)
            state["paused_at"] = None
        elif not state["running"]:
            state["start_time"] = now
            state["paused_duration"] = 0.0

        state["running"] = True
        state["paused"] = False

        self._update_start_end_time_labels(group_index)
        self._set_group_buttons_running(group_index, running=True, paused=False)

        if "periodic_worker_start" in app.ops:
            app.ops["periodic_worker_start"]()

        worker = self._ensure_worker(group_index)
        if not worker.isRunning():
            worker.start()
        else:
            worker.resume()

        if not state.get("tx_started"):
            if "tx1_start" in app.ops:
                app.ops["tx1_start"](ch1=True, ch2=True)
            if "tx2_start" in app.ops:
                app.ops["tx2_start"](ch1=True, ch2=True)
            state["tx_started"] = True

        self._refresh_group_colors(group_index)

    def _pause_group(self, group_index: int) -> None:
        state = self._group_state[group_index]
        app = self._get_group_app(group_index)
        state["paused"] = True
        state["paused_at"] = time.time()
        self._set_group_buttons_running(group_index, running=True, paused=True)
        self._set_group_color(group_index, "Paused", only_status_nonzero=True)

        worker = self._workers.get(group_index)
        if worker is not None and worker.isRunning():
            worker.pause()

        if "periodic_worker_stop" in app.ops:
            app.ops["periodic_worker_stop"]()
        if hasattr(app, "can_manager") and app.can_manager is not None:
            try:
                app.can_manager.stop_all_periodic_tasks()
            except Exception:
                pass
        state["tx_started"] = False

    def _resume_group(self, group_index: int) -> None:
        state = self._group_state[group_index]
        app = self._get_group_app(group_index)
        now = time.time()
        paused_at = state.get("paused_at") or now
        state["paused_duration"] += max(0.0, now - paused_at)
        state["paused_at"] = None
        state["paused"] = False

        self._set_group_buttons_running(group_index, running=True, paused=False)

        worker = self._ensure_worker(group_index)
        if not worker.isRunning():
            worker.start()
        else:
            worker.resume()

        if "periodic_worker_start" in app.ops:
            app.ops["periodic_worker_start"]()
        if not state.get("tx_started"):
            if "tx1_start" in app.ops:
                app.ops["tx1_start"](ch1=True, ch2=True)
            if "tx2_start" in app.ops:
                app.ops["tx2_start"](ch1=True, ch2=True)
            state["tx_started"] = True

        self._refresh_group_colors(group_index)

    def _stop_group(self, group_index: int) -> None:
        state = self._group_state[group_index]
        app = self._apps.get(group_index)
        state["running"] = False
        state["paused"] = False
        state["start_time"] = None
        state["paused_at"] = None
        state["paused_duration"] = 0.0
        state["tx_started"] = False
        self._reset_group_labels(group_index)
        self._set_group_buttons_running(group_index, running=False, paused=False)
        self._clear_group_color(group_index)
        self._group_table.pop(group_index, None)

        worker = self._workers.pop(group_index, None)
        if worker is not None and worker.isRunning():
            worker.stop()
            worker.wait(2000)

        if app is not None:
            if "periodic_worker_stop" in app.ops:
                app.ops["periodic_worker_stop"]()
            if hasattr(app, "can_manager") and app.can_manager is not None:
                try:
                    app.can_manager.stop_all_periodic_tasks()
                except Exception:
                    pass

    def _get_group_app(self, group_index: int) -> ComponentsInstantiation:
        app = self._apps.get(group_index)
        if app is not None:
            return app
        app = ComponentsInstantiation(group_index=group_index, autostart=False)
        self._apps[group_index] = app
        return app

    @staticmethod
    def _map_status_to_color(status: int) -> Optional[str]:
        if status == 0:
            return None
        if status == 1:
            return "good"
        if status == -4:
            return "Idle"
        if status == -5:
            return "Error"
        if status in (-1, -2, -3, 2, 3, 4):
            return "Warning"
        return "Error"


class SlotDetailDialog(QDialog):
    def __init__(self, parent: QWidget, group_index: int, slot_no: int):
        info_mapping = {
            1: "电压曲线",
            2: "电流曲线",
            3: "温度曲线",
        }
        super().__init__(parent)
        self.setWindowTitle(f"第{group_index}组 - 槽位{slot_no}详情")
        self.resize(900, 600)
        layout = QVBoxLayout(self)

        charts = QVBoxLayout()
        for i in range(1, 4):
            box = QGroupBox(info_mapping[i])
            box_layout = QVBoxLayout(box)
            placeholder = QFrame()
            placeholder.setFrameShape(QFrame.Shape.StyledPanel)
            placeholder.setObjectName(f"chart_placeholder_{i}")
            box_layout.addWidget(placeholder)
            charts.addWidget(box)

        layout.addLayout(charts)


class AgingThread(QThread):
    slot_status_changed = Signal(int, int, int)

    def __init__(
        self,
        app: ComponentsInstantiation,
        group_index: int,
        db_worker: DataBaseWorker,
        table_name: str,
    ):
        super().__init__()
        self.app = app
        self.group_index = group_index
        self.db_worker = db_worker
        self.table_name = table_name
        self.poll_interval = FUNCTION_CONFIG["UI"].get("SlotRefreshInterval", 1)
        self._running = True
        self._paused = False
        self._last_status: dict[int, int] = {}

    def _get_status_func(self):
        if hasattr(self.app, "ops") and isinstance(getattr(self.app, "ops"), dict):
            func = getattr(self.app, "ops").get("get_status")
            if callable(func):
                return func
        if hasattr(self.app, "get_status") and callable(
            getattr(self.app, "get_status")
        ):
            return getattr(self.app, "get_status")
        return None

    def run(self):
        status_fn = self._get_status_func()
        slot_count = int(FUNCTION_CONFIG["UI"].get("IndexPerGroup", 0))
        while self._running:
            if self._paused:
                self.msleep(int(self.poll_interval * 1000))
                continue
            if status_fn is None or slot_count <= 0:
                self.msleep(int(self.poll_interval * 1000))
                status_fn = self._get_status_func()
                slot_count = int(FUNCTION_CONFIG["UI"].get("IndexPerGroup", 0))
                continue

            active_slots = Tools.get_active_slots(self.app)
            diag_set_fn = None
            diag_once_set = None
            if hasattr(self.app, "ops") and isinstance(getattr(self.app, "ops"), dict):
                diag_set_fn = getattr(self.app, "ops").get("diag_set_periodic_slots")
                diag_once_set = getattr(self.app, "ops").get("diag_set_pending_slots")
            if not diag_set_fn and hasattr(self.app, "diag_set_periodic_slots"):
                diag_set_fn = getattr(self.app, "diag_set_periodic_slots")
            if not diag_once_set and hasattr(self.app, "diag_set_pending_slots"):
                diag_once_set = getattr(self.app, "diag_set_pending_slots")
            if callable(diag_set_fn):
                diag_set_fn(active_slots)
            if callable(diag_once_set):
                current_slots = set(active_slots)
                last_slots = getattr(self, "_last_active_slots", set())
                if current_slots != last_slots:
                    diag_once_set(active_slots)
                    self._last_active_slots = current_slots

            results = Tools.get_slots_results(self.app, active_slots)
            if results:
                self.db_worker.enqueue(self.table_name, results)

            for slot in range(1, slot_count + 1):
                card_status = status_fn("card_status", slot)
                status = 0
                if isinstance(card_status, dict):
                    status = int(card_status.get("Status", 0))
                last = self._last_status.get(slot)
                if last != status:
                    self._last_status[slot] = status
                    self.slot_status_changed.emit(self.group_index, slot, status)

            self.msleep(int(self.poll_interval * 1000))

    def stop(self):
        self._running = False

    def pause(self):
        self._paused = True

    def restart(self):
        self._paused = False

    def resume(self):
        self._paused = False

    @property
    def paused(self) -> bool:
        return self._paused


def main():
    qt_app = QApplication(sys.argv)
    ui = Ui_MainWidget()
    connector = Connector(ui)
    connector.show()

    def _cleanup():
        for worker in list(connector._workers.values()):
            if worker.isRunning():
                worker.stop()
                worker.wait(2000)
        if connector._db_worker is not None:
            connector._db_worker.stop_writing()
            connector._db_worker.close()
        for app in list(connector._apps.values()):
            if hasattr(app, "shutdown"):
                app.shutdown()

    qt_app.aboutToQuit.connect(_cleanup)
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
