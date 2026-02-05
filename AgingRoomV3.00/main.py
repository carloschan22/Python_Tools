from __future__ import annotations

import re
import sys
import time
import Tools
import sqlite3
import logging
import csv

from math import ceil
from bisect import bisect_left
from typing import Optional
from PowerSupply import set_powersupply_output
from datetime import datetime, timedelta
from DataBaseWorker import DataBaseWorker
from ui.main_widget_ui import Ui_MainWidget
from CompManager import ComponentsInstantiation
from Tools import COLOR_MAPPING, FUNCTION_CONFIG, PROJECT_CONFIG
from PySide6.QtCore import (
    Qt,
    Signal,
    QThread,
    Slot,
    QTimer,
    QDateTime,
    QMargins,
    QPointF,
    QLineF,
)
from PySide6.QtGui import QColor, QBrush, QPainter, QCursor, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QGridLayout,
    QCheckBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
    QGraphicsView,
    QToolTip,
    QGraphicsLineItem,
    QGraphicsEllipseItem,
    QMenu,
    QFileDialog,
    QHeaderView,
)
from PySide6.QtCharts import (
    QChart,
    QChartView,
    QLineSeries,
    QDateTimeAxis,
    QValueAxis,
    QScatterSeries,
)

_log = logging.getLogger(__name__)


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
                "frozen": False,
            }
            for i in range(1, self._group_count + 1)
        }
        self._slot_status: dict[int, dict[int, int]] = {
            i: {} for i in range(1, self._group_count + 1)
        }
        self._slot_raw_status: dict[int, dict[int, int]] = {
            i: {} for i in range(1, self._group_count + 1)
        }
        self._slot_latched: dict[int, dict[int, int]] = {
            i: {} for i in range(1, self._group_count + 1)
        }
        self._non_recoverable_status = self._load_non_recoverable_status()
        self._db_worker = DataBaseWorker()
        self._db_worker.initialization()
        self._db_worker.start_writing()
        self._group_table: dict[int, str] = {}
        self.ui.setupUi(self)
        self._init_nav()
        self._apply_ui_config()
        self._init_controls()
        self._init_history()
        self._bind_slot_clicks()

        self._runtime_timer = QTimer(self)
        self._runtime_timer.setInterval(1000)
        self._runtime_timer.timeout.connect(self._update_runtime_labels)
        self._runtime_timer.start()
        self._history_export_worker: Optional[_HistoryExportWorker] = None

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

        settings_menu = QMenu("设置", self)
        self.ui.menuBar.addMenu(settings_menu)
        action_alarm = settings_menu.addAction("报警状态配置")
        action_alarm.triggered.connect(self._open_alarm_status_config)

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

    def _init_history(self) -> None:
        self._setup_history_table()
        self._bind_history_controls()
        self._refresh_history_date_options()

    def _setup_history_table(self) -> None:
        table = getattr(self.ui, "historyTable", None)
        if table is None:
            return
        headers = [
            "序号",
            "组别",
            "型号",
            "作业员",
            "设定时长",
            "老化时长",
            "总数量",
            "良品",
            "良率",
        ]
        table.clear()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(0)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)

    def _bind_history_controls(self) -> None:
        btn_refresh = getattr(self.ui, "btn_history_refresh", None)
        if btn_refresh is not None:
            btn_refresh.clicked.connect(self._on_history_refresh)
        btn_query = getattr(self.ui, "btn_history_query", None)
        if btn_query is not None:
            btn_query.clicked.connect(self._on_history_query)
        btn_export = getattr(self.ui, "btn_history_export", None)
        if btn_export is not None:
            btn_export.clicked.connect(self._on_history_export)

        combo_year = getattr(self.ui, "combo_history_year", None)
        combo_month = getattr(self.ui, "combo_history_month", None)
        combo_day = getattr(self.ui, "combo_history_day", None)
        if combo_year is not None:
            combo_year.currentIndexChanged.connect(self._on_history_date_changed)
        if combo_month is not None:
            combo_month.currentIndexChanged.connect(self._on_history_date_changed)
        if combo_day is not None:
            combo_day.currentIndexChanged.connect(self._on_history_date_changed)

    def _refresh_history_date_options(self) -> None:
        prefixes = self._fetch_summary_date_prefixes()
        dates = []
        for prefix in prefixes:
            parts = prefix.split("_")
            if len(parts) >= 3:
                try:
                    dates.append((int(parts[0]), int(parts[1]), int(parts[2])))
                except Exception:
                    continue

        combo_year = getattr(self.ui, "combo_history_year", None)
        combo_month = getattr(self.ui, "combo_history_month", None)
        combo_day = getattr(self.ui, "combo_history_day", None)
        if combo_year is None or combo_month is None or combo_day is None:
            return

        selected_year = self._get_combo_value(combo_year)
        selected_month = self._get_combo_value(combo_month)
        selected_day = self._get_combo_value(combo_day)

        years = sorted({d[0] for d in dates})
        months = sorted(
            {d[1] for d in dates if selected_year is None or d[0] == selected_year}
        )
        days = sorted(
            {
                d[2]
                for d in dates
                if (selected_year is None or d[0] == selected_year)
                and (selected_month is None or d[1] == selected_month)
            }
        )

        self._fill_combo(combo_year, years, selected_year, width=4)
        self._fill_combo(combo_month, months, selected_month, width=2)
        self._fill_combo(combo_day, days, selected_day, width=2)

    @staticmethod
    def _get_combo_value(combo) -> Optional[int]:
        if combo is None:
            return None
        data = combo.currentData()
        if data in (None, ""):
            return None
        try:
            return int(data)
        except Exception:
            return None

    @staticmethod
    def _fill_combo(
        combo, values: list[int], current: Optional[int], width: int = 2
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("全部", None)
        for v in values:
            text = f"{v:0{width}d}"
            combo.addItem(text, v)
        if current in values:
            index = combo.findData(current)
            if index >= 0:
                combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _on_history_refresh(self) -> None:
        self._refresh_history_date_options()
        self._load_history_summary(self._get_history_date_prefix())

    def _on_history_query(self) -> None:
        self._load_history_summary(self._get_history_date_prefix())

    def _on_history_date_changed(self) -> None:
        self._refresh_history_date_options()
        self._load_history_summary(self._get_history_date_prefix())

    def _get_history_date_prefix(self) -> Optional[str]:
        combo_year = getattr(self.ui, "combo_history_year", None)
        combo_month = getattr(self.ui, "combo_history_month", None)
        combo_day = getattr(self.ui, "combo_history_day", None)

        year = self._get_combo_value(combo_year)
        month = self._get_combo_value(combo_month)
        day = self._get_combo_value(combo_day)

        if year is None:
            return None
        if month is None:
            return f"{year:04d}"
        if day is None:
            return f"{year:04d}_{month:02d}"
        return f"{year:04d}_{month:02d}_{day:02d}"

    def _load_history_summary(self, date_prefix: Optional[str]) -> None:
        table = getattr(self.ui, "historyTable", None)
        if table is None:
            return
        table.setRowCount(0)

        db_path = getattr(self._db_worker, "db_path", "./aging_data.db")
        try:
            conn = sqlite3.connect(db_path)
        except Exception:
            return

        try:
            self._ensure_summary_table(conn)
            rows = self._query_summary_rows(conn, date_prefix)
        finally:
            conn.close()

        table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            values = row["values"]
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if c == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["table_name"])
                table.setItem(r, c, item)

    def _fetch_summary_date_prefixes(self) -> list[str]:
        db_path = getattr(self._db_worker, "db_path", "./aging_data.db")
        try:
            conn = sqlite3.connect(db_path)
        except Exception:
            return []
        try:
            self._ensure_summary_table(conn)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT DISTINCT DatePrefix FROM Summary WHERE DatePrefix IS NOT NULL ORDER BY DatePrefix DESC"
            )
            return [row[0] for row in cursor.fetchall() if row and row[0]]
        finally:
            conn.close()

    def _ensure_summary_table(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS Summary (
                TableName TEXT PRIMARY KEY,
                DatePrefix TEXT,
                GroupIndex INTEGER,
                Project TEXT,
                Operator TEXT,
                SetHours REAL,
                StartTime REAL,
                EndTime REAL,
                AgingSeconds REAL,
                Total INTEGER,
                Good INTEGER,
                Bad INTEGER,
                GoodRate REAL
            )
            """
        )
        conn.commit()

    def _query_summary_rows(
        self, conn: sqlite3.Connection, date_prefix: Optional[str]
    ) -> list[dict]:
        cursor = conn.cursor()
        if date_prefix:
            cursor.execute(
                """
                SELECT TableName, GroupIndex, Project, Operator, SetHours, AgingSeconds, Total, Good, GoodRate
                FROM Summary WHERE DatePrefix LIKE ? ORDER BY TableName DESC
                """,
                (f"{date_prefix}%",),
            )
        else:
            cursor.execute(
                """
                SELECT TableName, GroupIndex, Project, Operator, SetHours, AgingSeconds, Total, Good, GoodRate
                FROM Summary ORDER BY TableName DESC
                """
            )
        rows = []
        for idx, row in enumerate(cursor.fetchall(), start=1):
            (
                table_name,
                group_index,
                project,
                operator,
                set_hours,
                aging_seconds,
                total,
                good,
                good_rate,
            ) = row
            set_duration = "--"
            if set_hours is not None:
                try:
                    set_duration = self._format_duration(float(set_hours) * 3600)
                except Exception:
                    set_duration = "--"

            aging_duration = "--"
            if aging_seconds is not None:
                try:
                    aging_duration = self._format_duration(float(aging_seconds))
                except Exception:
                    aging_duration = "--"

            rate_text = f"{float(good_rate):.2f}%" if good_rate is not None else "0.00%"

            rows.append(
                {
                    "table_name": table_name,
                    "values": (
                        idx,
                        int(group_index or 0),
                        project or "--",
                        operator or "--",
                        set_duration,
                        aging_duration,
                        int(total or 0),
                        int(good or 0),
                        rate_text,
                    ),
                }
            )
        return rows

    def _on_history_export(self) -> None:
        table = getattr(self.ui, "historyTable", None)
        if table is None or table.rowCount() == 0:
            return
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出汇总表", "summary.csv", "CSV Files (*.csv)"
        )
        if not file_path:
            return
        selected_rows = (
            table.selectionModel().selectedRows() if table.selectionModel() else []
        )
        table_names = []
        if selected_rows:
            item = table.item(selected_rows[0].row(), 0)
            if item is not None:
                table_name = item.data(Qt.ItemDataRole.UserRole)
                if table_name:
                    table_names = [table_name]
        if not table_names:
            date_prefix = self._get_history_date_prefix()
            db_path = getattr(self._db_worker, "db_path", "./aging_data.db")
            try:
                conn = sqlite3.connect(db_path)
            except Exception:
                return
            try:
                self._ensure_summary_table(conn)
                rows = self._query_summary_rows(conn, date_prefix)
                table_names = [row["table_name"] for row in rows]
            finally:
                conn.close()

        if not table_names:
            return

        if (
            self._history_export_worker is not None
            and self._history_export_worker.isRunning()
        ):
            return
        bad_status = set(FUNCTION_CONFIG.get("UI", {}).get("NonRecoverableStatus", []))
        self._history_export_worker = _HistoryExportWorker(
            getattr(self._db_worker, "db_path", "./aging_data.db"),
            table_names,
            file_path,
            bad_status,
        )
        self._history_export_worker.start()

    def _write_summary_start(
        self,
        table_name: str,
        group_index: int,
        project: str,
        operator: str,
        set_hours: Optional[float],
        start_time: float,
    ) -> None:
        db_path = getattr(self._db_worker, "db_path", "./aging_data.db")
        conn = sqlite3.connect(db_path)
        try:
            self._ensure_summary_table(conn)
            date_prefix = table_name[:10]
            conn.execute(
                """
                INSERT OR REPLACE INTO Summary
                (TableName, DatePrefix, GroupIndex, Project, Operator, SetHours, StartTime,
                 EndTime, AgingSeconds, Total, Good, Bad, GoodRate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    table_name,
                    date_prefix,
                    int(group_index),
                    project or "--",
                    operator or "--",
                    set_hours,
                    float(start_time),
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _write_summary_end(
        self,
        table_name: str,
        end_time: float,
        aging_seconds: Optional[float],
        total: int,
        good: int,
        bad: int,
        good_rate: float,
    ) -> None:
        db_path = getattr(self._db_worker, "db_path", "./aging_data.db")
        conn = sqlite3.connect(db_path)
        try:
            self._ensure_summary_table(conn)
            conn.execute(
                """
                UPDATE Summary
                SET EndTime=?, AgingSeconds=?, Total=?, Good=?, Bad=?, GoodRate=?
                WHERE TableName=?
                """,
                (
                    float(end_time),
                    aging_seconds,
                    int(total),
                    int(good),
                    int(bad),
                    float(good_rate),
                    table_name,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _populate_combo_options(self) -> None:
        projects = list(PROJECT_CONFIG.keys())
        ui_cfg = FUNCTION_CONFIG.get("UI", {})
        operators = list(ui_cfg.get("OperatorList", []))

        for group_index in range(1, self._group_count + 1):
            default_project = Tools.get_default_project(group_index, projects)
            default_operator = Tools.get_default_operator(group_index, operators)
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
        """根据状态变更某个槽位的显示颜色,延时报警功能"""
        state = self._group_state.get(group_index, {})
        if not state.get("running") or state.get("frozen"):
            return
        self._slot_raw_status.setdefault(group_index, {})[slot_no] = status
        if self._is_alarm_delay_active(group_index) and status in (
            -3,
            -2,
            -1,
            1,
            2,
            3,
            4,
        ):  # 设置特定状态延时报警
            display_status = 1
        else:
            display_status = self._apply_latched_status(group_index, slot_no, status)
        self._slot_status.setdefault(group_index, {})[slot_no] = display_status
        self._slot_change_color(group_index, slot_no, display_status)

    def on_group_summary_updated(
        self,
        group_index: int,
        total: int,
        good: int,
        bad: int,
        pass_rate: float,
        fail_rate: float,
        max_temp: Optional[float],
    ) -> None:
        state = self._group_state.get(group_index, {})
        if not state.get("running") or state.get("frozen"):
            return
        total, good, bad, pass_rate, fail_rate = self._calc_group_summary(group_index)

        qty_label = getattr(self.ui, f"edit_qty_{group_index}", None)
        good_label = getattr(self.ui, f"edit_good_{group_index}", None)
        bad_label = getattr(self.ui, f"edit_bad_{group_index}", None)
        pass_label = getattr(self.ui, f"text_pass_rate_{group_index}", None)
        fail_label = getattr(self.ui, f"text_fail_rate_{group_index}", None)
        temp_label = getattr(self.ui, f"text_temp_{group_index}", None)

        if qty_label is not None:
            qty_label.setText(str(total))
        if good_label is not None:
            good_label.setText(str(good))
        if bad_label is not None:
            bad_label.setText(str(bad))
        if pass_label is not None:
            pass_label.setText(f"{pass_rate:.2f}%")
        if fail_label is not None:
            fail_label.setText(f"{fail_rate:.2f}%")
        if temp_label is not None:
            temp_label.setText("--" if max_temp is None else f"{max_temp:.1f}")

    def _calc_group_summary(
        self, group_index: int
    ) -> tuple[int, int, int, float, float]:
        slot_count = int(FUNCTION_CONFIG.get("UI", {}).get("IndexPerGroup", 0))
        status_map = self._slot_status.get(group_index, {})
        total = 0
        good = 0
        bad = 0
        for slot in range(1, slot_count + 1):
            status = int(status_map.get(slot, 0) or 0)
            if status in (0, -4):
                continue
            total += 1
            if status == 1:
                good += 1
            elif status in FUNCTION_CONFIG["UI"]["NonRecoverableStatus"]:
                bad += 1

        pass_rate = (good / total * 100.0) if total > 0 else 0.0
        fail_rate = (bad / total * 100.0) if total > 0 else 0.0
        return total, good, bad, pass_rate, fail_rate

    def _is_alarm_delay_active(self, group_index: int) -> bool:
        delay = FUNCTION_CONFIG.get("UI", {}).get("AlarmDelaySeconds", 0)
        try:
            delay = float(delay)
        except Exception:
            delay = 0.0
        if delay <= 0:
            return False
        state = self._group_state.get(group_index, {})
        start_time = state.get("start_time")
        if not start_time:
            return False
        return (time.time() - float(start_time)) < delay

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

    def _load_non_recoverable_status(self) -> list[int]:
        ui_cfg = FUNCTION_CONFIG.get("UI", {})
        raw_list = ui_cfg.get("NonRecoverableStatus", [])
        result: list[int] = []
        for v in raw_list:
            try:
                result.append(int(v))
            except Exception:
                continue
        return result

    def _apply_latched_status(self, group_index: int, slot_no: int, status: int) -> int:
        latched = self._slot_latched.setdefault(group_index, {})
        if status in self._non_recoverable_status:
            latched[slot_no] = status
            return status
        if status == 1 and slot_no in latched:
            return latched[slot_no]
        return status

    def _open_alarm_status_config(self) -> None:
        dialog = AlarmStatusConfigDialog(self, self._non_recoverable_status)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected = dialog.get_selected_statuses()
        Tools.change_json_value("FuncConfig", "UI.NonRecoverableStatus", selected)
        Tools.refresh_configs()
        self._non_recoverable_status = self._load_non_recoverable_status()
        for group_index in range(1, self._group_count + 1):
            self._reapply_group_status(group_index)

    def _reapply_group_status(self, group_index: int) -> None:
        self._slot_latched[group_index] = {}
        status_map = self._slot_raw_status.get(group_index, {})
        for slot_no, status in status_map.items():
            display_status = self._apply_latched_status(group_index, slot_no, status)
            self._slot_status.setdefault(group_index, {})[slot_no] = display_status
            self._slot_change_color(group_index, slot_no, display_status)

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
            set_powersupply_output(True, project_name=project)
        elif name.startswith("combo_aging_time_"):
            self._group_state[group_index]["aging_hours"] = self._get_group_aging_hours(
                group_index
            )
            self._update_end_time(group_index)

        selected_project = getattr(self.ui, f"combo_product_{group_index}", None)
        selected_duration = getattr(self.ui, f"combo_aging_time_{group_index}", None)
        selected_operator = getattr(self.ui, f"combo_worker_{group_index}", None)
        Tools.refresh_ui_config(
            selected_project.currentText() if selected_project else "",
            selected_duration.currentText() if selected_duration else "",
            selected_operator.currentText() if selected_operator else "",
            group_index=group_index,
        )

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
            if elapsed >= total:
                self._stop_group(group_index)

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

    def _reset_group_summary(self, group_index: int) -> None:
        qty_label = getattr(self.ui, f"edit_qty_{group_index}", None)
        good_label = getattr(self.ui, f"edit_good_{group_index}", None)
        bad_label = getattr(self.ui, f"edit_bad_{group_index}", None)
        pass_label = getattr(self.ui, f"text_pass_rate_{group_index}", None)
        fail_label = getattr(self.ui, f"text_fail_rate_{group_index}", None)
        temp_label = getattr(self.ui, f"text_temp_{group_index}", None)

        if qty_label is not None:
            qty_label.setText("0")
        if good_label is not None:
            good_label.setText("0")
        if bad_label is not None:
            bad_label.setText("0")
        if pass_label is not None:
            pass_label.setText("0.00%")
        if fail_label is not None:
            fail_label.setText("0.00%")
        if temp_label is not None:
            temp_label.setText("--")

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
            group_index=group_index,
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
        worker.summary_updated.connect(self.on_group_summary_updated)
        self._workers[group_index] = worker
        return worker

    def _start_group(self, group_index: int) -> None:
        state = self._group_state[group_index]
        now = time.time()
        app = self._get_group_app(group_index)

        if not state["running"]:
            state["frozen"] = False
            self._slot_latched[group_index] = {}
            self._slot_raw_status[group_index] = {}
            self._slot_status[group_index] = {}
            self._clear_group_color(group_index)
            self._reset_group_labels(group_index)
            self._reset_group_summary(group_index)

        if not state["running"]:
            self._group_table[group_index] = self._db_worker.create_new_table()
            project_name = getattr(self.ui, f"combo_product_{group_index}", None)
            operator_name = getattr(self.ui, f"combo_worker_{group_index}", None)
            project_text = project_name.currentText() if project_name else "--"
            operator_text = operator_name.currentText() if operator_name else "--"
            set_hours = self._get_group_aging_hours(group_index)
            self._write_summary_start(
                self._group_table[group_index],
                group_index,
                project_text,
                operator_text,
                set_hours,
                now,
            )

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
        start_time = state.get("start_time")
        end_time = time.time()
        state["frozen"] = True
        state["running"] = False
        state["paused"] = False
        state["start_time"] = None
        state["paused_at"] = None
        state["paused_duration"] = 0.0
        state["tx_started"] = False
        self._set_group_buttons_running(group_index, running=False, paused=False)
        # 保留最后表名, 以便停止后仍可查看历史曲线

        table_name = self._group_table.get(group_index)
        if table_name:
            total, good, bad, pass_rate, _ = self._calc_group_summary(group_index)
            st = float(start_time) if start_time else None
            aging_seconds = None
            if st is not None:
                aging_seconds = max(0.0, end_time - st)
            self._write_summary_end(
                table_name,
                end_time=end_time,
                aging_seconds=aging_seconds,
                total=total,
                good=good,
                bad=bad,
                good_rate=pass_rate,
            )

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
        combo = getattr(self.ui, f"combo_product_{group_index}", None)
        project_name = (
            combo.currentText()
            if combo is not None
            else Tools.get_default_project(group_index)
        )
        app = self._apps.get(group_index)
        if app is None:
            app = ComponentsInstantiation(
                group_index=group_index,
                project_name=project_name,
                autostart=False,
            )
            self._apps[group_index] = app
        else:
            app.set_project(project_name)
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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._group_index = group_index
        self._slot_no = slot_no
        self._charts: dict[str, dict] = {}
        self._buffers: dict[str, list[tuple[int, float, Optional[int]]]] = {
            "voltage": [],
            "current": [],
            "temperature": [],
        }
        self._max_points = 2000

        charts = QVBoxLayout()
        charts.setSpacing(8)
        chart_cfg = [
            ("voltage", info_mapping[1], "电压(V)"),
            ("current", info_mapping[2], "电流(mA)"),
            ("temperature", info_mapping[3], "温度(°C)"),
        ]
        for key, title, y_label in chart_cfg:
            box = QGroupBox(title)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(6, 6, 6, 6)
            box_layout.setSpacing(4)
            chart, view, series, alert_series, x_axis, y_axis = self._create_chart(
                title, y_label
            )
            box_layout.addWidget(view)
            charts.addWidget(box)
            self._charts[key] = {
                "chart": chart,
                "view": view,
                "series": series,
                "alert_series": alert_series,
                "x_axis": x_axis,
                "y_axis": y_axis,
                "title": title,
                "value_label": y_label,
            }

        layout.addLayout(charts)

        self._data_worker: Optional[_ChartDataWorker] = None
        self._start_data_worker()

    def _create_chart(self, title: str, y_label: str):
        chart = QChart()
        chart.setTitle("")
        chart.legend().hide()
        chart.setBackgroundRoundness(0)
        chart.setMargins(QMargins(6, 4, 6, 6))

        series = QLineSeries()
        series.setName(y_label)
        chart.addSeries(series)

        alert_series = QScatterSeries()
        alert_series.setMarkerShape(QScatterSeries.MarkerShapeCircle)
        alert_series.setMarkerSize(8.0)
        alert_series.setColor(QColor("#ff4d4f"))
        alert_series.setBorderColor(QColor("#ff4d4f"))
        chart.addSeries(alert_series)

        x_axis = QDateTimeAxis()
        x_axis.setFormat("MM-dd HH:mm:ss")
        x_axis.setTitleText("")
        x_axis.setLabelsVisible(False)
        x_axis.setGridLineVisible(False)
        x_axis.setMinorGridLineVisible(False)
        x_axis.setLineVisible(False)
        chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
        series.attachAxis(x_axis)
        alert_series.attachAxis(x_axis)

        y_axis = QValueAxis()
        y_axis.setTitleText("")
        y_axis.setLabelsVisible(False)
        y_axis.setGridLineVisible(False)
        y_axis.setMinorGridLineVisible(False)
        y_axis.setLineVisible(False)
        chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
        series.attachAxis(y_axis)
        alert_series.attachAxis(y_axis)

        view = _ChartView(chart)
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setRenderHint(QPainter.RenderHint.Antialiasing)
        view.setRubberBand(QChartView.RubberBand.NoRubberBand)
        view.setDragMode(QGraphicsView.DragMode.NoDrag)
        view.set_series(series, value_label=y_label)
        return chart, view, series, alert_series, x_axis, y_axis

    def _start_data_worker(self) -> None:
        parent = self.parent()
        db_worker = getattr(parent, "_db_worker", None)
        table_name = getattr(parent, "_group_table", {}).get(self._group_index)
        if db_worker is None or not table_name:
            self._set_no_data("暂无数据")
            return

        db_path = getattr(db_worker, "db_path", "./aging_data.db")
        self._data_worker = _ChartDataWorker(
            db_path=db_path,
            table_name=table_name,
            slot_no=self._slot_no,
            poll_interval=1.0,
            initial_limit=self._max_points,
        )
        self._data_worker.data_ready.connect(self._on_rows_ready)
        self._data_worker.start()

    def _on_rows_ready(self, rows: list[tuple]) -> None:
        if not rows:
            return
        for row in rows:
            ts = row[2]
            if ts is None:
                continue
            x_ms = int(float(ts) * 1000)  # Directly convert timestamp to milliseconds
            status = row[3]
            if row[4] is not None:
                self._append_point("voltage", x_ms, float(row[4]), status)
            if row[5] is not None:
                self._append_point("current", x_ms, float(row[5]), status)
            if row[6] is not None:
                self._append_point("temperature", x_ms, float(row[6]), status)

        self._update_series("voltage", self._buffers["voltage"])
        self._update_series("current", self._buffers["current"])
        self._update_series("temperature", self._buffers["temperature"])

    def _append_point(
        self, key: str, x_ms: int, y: float, status: Optional[int]
    ) -> None:
        buf = self._buffers.get(key)
        if buf is None:
            return
        buf.append((x_ms, y, status))
        overflow = len(buf) - self._max_points
        if overflow > 0:
            del buf[:overflow]

    def _load_and_draw(self) -> None:
        parent = self.parent()
        db_worker = getattr(parent, "_db_worker", None)
        table_name = getattr(parent, "_group_table", {}).get(self._group_index)
        if db_worker is None or not table_name:
            self._set_no_data("暂无数据")
            return

        try:
            rows = db_worker.query_data(
                table_name,
                conditions=f"Slot={int(self._slot_no)} ORDER BY Timestamp ASC",
            )
        except Exception:
            return

        if not rows:
            self._set_no_data("暂无数据")
            return

        voltage_points = []
        current_points = []
        temperature_points = []
        for row in rows:
            ts = row[2]
            if ts is None:
                continue
            x_ms = int(float(ts) * 1000)  # Directly convert timestamp to milliseconds
            status = row[3]
            if row[4] is not None:
                voltage_points.append((x_ms, float(row[4]), status))
            if row[5] is not None:
                current_points.append((x_ms, float(row[5]), status))
            if row[6] is not None:
                temperature_points.append((x_ms, float(row[6]), status))

        self._update_series("voltage", voltage_points)
        self._update_series("current", current_points)
        self._update_series("temperature", temperature_points)

    def closeEvent(self, event) -> None:
        if self._data_worker is not None:
            self._data_worker.stop()
            self._data_worker.wait(2000)
            self._data_worker = None
        super().closeEvent(event)

    def _set_no_data(self, reason: str) -> None:
        for key, cfg in self._charts.items():
            chart = cfg["chart"]
            chart.setTitle(f"{cfg['title']} ({reason})")
            cfg["series"].clear()
            cfg["alert_series"].clear()
            cfg["view"].clear_hover()

    def _update_series(self, key: str, points: list[tuple[int, float, int]]) -> None:
        cfg = self._charts.get(key)
        if not cfg:
            return
        series = cfg["series"]
        alert_series = cfg["alert_series"]
        if not points:
            cfg["chart"].setTitle(f"{cfg['title']} (暂无数据)")
            cfg["view"].clear_hover()
            return

        cfg["chart"].setTitle("")

        clean_points = []
        alert_points = []
        series_points = []
        alert_series_points = []
        for x_ms, y, status in points:
            clean_points.append((x_ms, y))
            series_points.append(QPointF(x_ms, y))
            if status is not None and status not in (1, -4):
                alert_points.append((x_ms, y))
                alert_series_points.append(QPointF(x_ms, y))

        series.replace(series_points)
        alert_series.replace(alert_series_points)

        cfg["view"].set_points(clean_points)

        x_axis = cfg["x_axis"]
        y_axis = cfg["y_axis"]
        min_x = clean_points[0][0]
        max_x = clean_points[-1][0]
        min_y = min(p[1] for p in clean_points)
        max_y = max(p[1] for p in clean_points)
        if min_y == max_y:
            min_y -= 1
            max_y += 1

        if not cfg["view"].is_user_locked():
            x_pad = max(1000, int((max_x - min_x) * 0.03))
            y_pad = (max_y - min_y) * 0.08
            if y_pad == 0:
                y_pad = 1.0
            x_axis.setRange(
                QDateTime.fromMSecsSinceEpoch(min_x - x_pad),
                QDateTime.fromMSecsSinceEpoch(max_x + x_pad),
            )
            y_axis.setRange(min_y - y_pad, max_y + y_pad)


class AlarmStatusConfigDialog(QDialog):
    def __init__(self, parent: QWidget, selected: list[int]):
        super().__init__(parent)
        self.setWindowTitle("报警状态配置")
        self.resize(420, 320)
        self._selected = set(int(v) for v in selected)
        layout = QVBoxLayout(self)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)

        status_items = [
            (-5, "采集卡丢失（电压/电流为0或异常）"),
            (-4, "低于暗电流范围，未接产品"),
            (-3, "超出暗电流范围, 低于工作电压范围, 低于工作电流范围"),
            (-2, "超出暗电流范围, 处于正常工作电流范围, 低于工作电压范围"),
            (-1, "超出暗电流范围, 处于正常工作电压范围, 低于工作电流范围"),
            (1, "正常工作电压/电流"),
            (2, "超出暗电流范围, 处于正常工作电压范围, 超出工作电流范围"),
            (3, "超出暗电流范围, 低于工作电流范围, 高于工作电压范围"),
            (4, "超出暗电流范围, 高于工作电压范围, 超出工作电流范围"),
            (0, "状态初始值"),
        ]

        self._boxes: dict[int, QCheckBox] = {}
        row = 0
        for value, text in status_items:
            cb = QCheckBox(f"{value}: {text}")
            if value in self._selected:
                cb.setChecked(True)
            self._boxes[value] = cb
            grid.addWidget(cb, row, 0, 1, 1)
            row += 1

        layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_ok = QPushButton("保存")
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def get_selected_statuses(self) -> list[int]:
        selected = []
        for value, cb in self._boxes.items():
            if cb.isChecked():
                selected.append(int(value))
        return selected


class _ChartView(QChartView):
    def __init__(self, chart: QChart, parent: Optional[QWidget] = None):
        super().__init__(chart, parent)
        self.setMouseTracking(True)
        self._panning = False
        self._last_pos = None
        self._user_locked = False
        self._points: list[tuple[int, float]] = []
        self._points_x: list[int] = []
        self._series: Optional[QLineSeries] = None
        self._value_label = ""

        self._crosshair_x = QGraphicsLineItem()
        self._crosshair_y = QGraphicsLineItem()
        self._marker = QGraphicsEllipseItem()
        cross_pen = QPen(QColor(180, 180, 180), 1, Qt.PenStyle.DashLine)
        self._crosshair_x.setPen(cross_pen)
        self._crosshair_y.setPen(cross_pen)
        self._marker.setPen(QPen(QColor("#ff7a45"), 1))
        self._marker.setBrush(QColor("#ff7a45"))
        self._crosshair_x.setZValue(10)
        self._crosshair_y.setZValue(10)
        self._marker.setZValue(11)

        scene = self.scene()
        if scene is not None:
            scene.addItem(self._crosshair_x)
            scene.addItem(self._crosshair_y)
            scene.addItem(self._marker)
        self.clear_hover()

    def set_series(self, series: QLineSeries, value_label: str = "") -> None:
        self._series = series
        self._value_label = value_label

    def set_points(self, points: list[tuple[int, float]]) -> None:
        self._points = points or []
        self._points_x = [p[0] for p in self._points]

    def clear_hover(self) -> None:
        self._crosshair_x.hide()
        self._crosshair_y.hide()
        self._marker.hide()
        QToolTip.hideText()

    def is_user_locked(self) -> bool:
        return self._user_locked

    def reset_user_lock(self) -> None:
        self._user_locked = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._last_pos = event.position()
            self._user_locked = True
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._last_pos is not None:
            delta = event.position() - self._last_pos
            self.chart().scroll(-delta.x(), delta.y())
            self._last_pos = event.position()
            event.accept()
            return

        self._update_hover(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._panning:
            self._panning = False
            self._last_pos = None
            self.unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self.clear_hover()
        self.unsetCursor()
        super().leaveEvent(event)

    def _update_hover(self, pos) -> None:
        if not self._points or self._series is None:
            self.clear_hover()
            return

        scene_pos = self.mapToScene(pos.toPoint())
        chart_pos = self.chart().mapFromScene(scene_pos)
        value_pos = self.chart().mapToValue(chart_pos, self._series)
        x_val = value_pos.x()

        idx = bisect_left(self._points_x, x_val)
        candidates = []
        if 0 <= idx < len(self._points):
            candidates.append(self._points[idx])
        if idx - 1 >= 0:
            candidates.append(self._points[idx - 1])
        if not candidates:
            self.clear_hover()
            return

        nearest = min(candidates, key=lambda p: abs(p[0] - x_val))
        nearest_pt = QPointF(nearest[0], nearest[1])
        pos_in_chart = self.chart().mapToPosition(nearest_pt, self._series)
        pos_in_scene = self.chart().mapToScene(pos_in_chart)

        if QLineF(scene_pos, pos_in_scene).length() > 12:
            self.clear_hover()
            return

        plot_area = self.chart().plotArea()
        top_left = self.chart().mapToScene(plot_area.topLeft())
        bottom_right = self.chart().mapToScene(plot_area.bottomRight())

        self._crosshair_x.setLine(
            pos_in_scene.x(), top_left.y(), pos_in_scene.x(), bottom_right.y()
        )
        self._crosshair_y.setLine(
            top_left.x(), pos_in_scene.y(), bottom_right.x(), pos_in_scene.y()
        )

        r = 4.0
        self._marker.setRect(
            pos_in_scene.x() - r,
            pos_in_scene.y() - r,
            2 * r,
            2 * r,
        )

        self._crosshair_x.show()
        self._crosshair_y.show()
        self._marker.show()

        ts = QDateTime.fromMSecsSinceEpoch(int(nearest[0]))
        label = self._value_label or "值"
        text = f"{label}: {nearest[1]:.2f}\n时间: {ts.toString('yyyy-MM-dd HH:mm:ss')}"
        QToolTip.showText(QCursor.pos(), text, self)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)
        factor = 1.2 if delta > 0 else 0.8
        self.chart().zoom(factor)
        self._user_locked = True
        event.accept()


class _ChartDataWorker(QThread):
    data_ready = Signal(list)

    def __init__(
        self,
        db_path: str,
        table_name: str,
        slot_no: int,
        poll_interval: float = 1.0,
        initial_limit: int = 2000,
    ):
        super().__init__()
        self._db_path = db_path
        self._table_name = table_name
        self._slot_no = int(slot_no)
        self._poll_ms = max(200, int(poll_interval * 1000))
        self._initial_limit = max(0, int(initial_limit))
        self._running = True
        self._last_id = 0

    def stop(self) -> None:
        self._running = False

    def run(self):
        try:
            conn = sqlite3.connect(self._db_path)
            cursor = conn.cursor()
            idx_name = f"idx_{self._table_name}_slot_id".replace("-", "_")
            try:
                cursor.execute(
                    f'CREATE INDEX IF NOT EXISTS {idx_name} ON "{self._table_name}" (Slot, Id)'
                )
                conn.commit()
            except Exception:
                pass

            if self._initial_limit > 0:
                cursor.execute(
                    f'SELECT * FROM "{self._table_name}" WHERE Slot=? ORDER BY Id DESC LIMIT ?',
                    (self._slot_no, self._initial_limit),
                )
                rows = cursor.fetchall()[::-1]
                if rows:
                    self._last_id = rows[-1][0]
                    self.data_ready.emit(rows)

            while self._running:
                cursor.execute(
                    f'SELECT * FROM "{self._table_name}" WHERE Slot=? AND Id>? ORDER BY Id ASC',
                    (self._slot_no, self._last_id),
                )
                rows = cursor.fetchall()
                if rows:
                    self._last_id = rows[-1][0]
                    self.data_ready.emit(rows)
                self.msleep(self._poll_ms)
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass


class _HistoryExportWorker(QThread):
    def __init__(
        self,
        db_path: str,
        table_names: list[str],
        file_path: str,
        bad_status: set[int],
    ):
        super().__init__()
        self._db_path = db_path
        self._table_names = table_names
        self._file_path = file_path
        self._bad_status = bad_status

    def run(self):
        try:
            conn = sqlite3.connect(self._db_path)
        except Exception:
            return

        try:
            with open(self._file_path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [
                        "批次表",
                        "穴位",
                        "状态",
                        "电压最小值",
                        "电压最小时间",
                        "电压最大值",
                        "电压最大时间",
                        "电压平均值",
                        "电流最小值",
                        "电流最小时间",
                        "电流最大值",
                        "电流最大时间",
                        "电流平均值",
                        "温度最小值",
                        "温度最小时间",
                        "温度最大值",
                        "温度最大时间",
                        "温度平均值",
                    ]
                )
                for table_name in self._table_names:
                    self._write_table_summary(conn, writer, table_name)
        except Exception:
            return
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _write_table_summary(
        self, conn: sqlite3.Connection, writer: csv.writer, table_name: str
    ) -> None:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f'SELECT DISTINCT Slot FROM "{table_name}" ORDER BY Slot ASC'
            )
        except Exception:
            return

        slots = [row[0] for row in cursor.fetchall()]
        for slot in slots:
            if self._has_ng_status(cursor, table_name, slot):
                status_text = "NG"
            elif self._has_ok_status(cursor, table_name, slot):
                status_text = "OK"
            else:
                status_text = "--"

            v_stats = self._get_stats(cursor, table_name, slot, "Voltage")
            c_stats = self._get_stats(cursor, table_name, slot, "Current")
            t_stats = self._get_stats(cursor, table_name, slot, "Temperature")

            writer.writerow(
                [
                    table_name,
                    slot,
                    status_text,
                    *v_stats,
                    *c_stats,
                    *t_stats,
                ]
            )

    def _has_ng_status(
        self, cursor: sqlite3.Cursor, table_name: str, slot: int
    ) -> bool:
        if not self._bad_status:
            return False
        placeholders = ",".join(["?"] * len(self._bad_status))
        params = [int(slot), *self._bad_status]
        try:
            cursor.execute(
                f'SELECT 1 FROM "{table_name}" WHERE Slot=? AND Status IN ({placeholders}) LIMIT 1',
                params,
            )
            return cursor.fetchone() is not None
        except Exception:
            return False

    def _has_ok_status(
        self, cursor: sqlite3.Cursor, table_name: str, slot: int
    ) -> bool:
        try:
            cursor.execute(
                f'SELECT 1 FROM "{table_name}" WHERE Slot=? AND Status=1 LIMIT 1',
                (int(slot),),
            )
            return cursor.fetchone() is not None
        except Exception:
            return False

    def _get_stats(
        self, cursor: sqlite3.Cursor, table_name: str, slot: int, field: str
    ) -> list[str]:
        try:
            cursor.execute(
                f'SELECT MIN({field}), MAX({field}), AVG({field}) FROM "{table_name}" WHERE Slot=? AND {field} IS NOT NULL',
                (int(slot),),
            )
            row = cursor.fetchone()
        except Exception:
            row = None

        if not row:
            return ["", "", "", "", ""]

        min_val, max_val, avg_val = row
        min_time = self._get_time_for_value(
            cursor, table_name, slot, field, min_val, asc=True
        )
        max_time = self._get_time_for_value(
            cursor, table_name, slot, field, max_val, asc=False
        )

        return [
            self._fmt_float(min_val),
            min_time,
            self._fmt_float(max_val),
            max_time,
            self._fmt_float(avg_val),
        ]

    def _get_time_for_value(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
        slot: int,
        field: str,
        value: Optional[float],
        asc: bool = True,
    ) -> str:
        if value is None:
            return ""
        order = "ASC" if asc else "DESC"
        try:
            cursor.execute(
                f'SELECT Timestamp FROM "{table_name}" WHERE Slot=? AND {field}=? ORDER BY Timestamp {order} LIMIT 1',
                (int(slot), value),
            )
            row = cursor.fetchone()
        except Exception:
            row = None
        if not row or row[0] is None:
            return ""
        try:
            return datetime.fromtimestamp(float(row[0])).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return ""

    @staticmethod
    def _fmt_float(value: Optional[float]) -> str:
        if value is None:
            return ""
        try:
            return f"{float(value):.2f}"
        except Exception:
            return ""


class AgingThread(QThread):
    slot_status_changed = Signal(int, int, int)
    summary_updated = Signal(int, int, int, int, float, float, object)

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

            results = Tools.get_slots_results(self.app, active_slots)  # 状态更新
            if results:
                self.db_worker.enqueue(self.table_name, results)  # 状态写入数据库

            total = 0
            good = 0
            bad = 0

            for slot in range(1, slot_count + 1):
                card_status = status_fn("card_status", slot)
                status = 0
                if isinstance(card_status, dict):
                    status = int(card_status.get("Status", 0))
                    if status not in (0, -4):
                        total += 1
                        if status == 1:
                            good += 1
                        elif status in (-5, -3, -2, -1, 2, 3, 4):
                            bad += 1
                last = self._last_status.get(slot)
                if last != status:
                    self._last_status[slot] = status
                    self.slot_status_changed.emit(self.group_index, slot, status)

            max_temp: Optional[float] = None
            for slot_data in (results or {}).values():
                card_status = slot_data.get("card_status") or {}
                temp = card_status.get("CardTemperature")
                if temp is None:
                    continue
                try:
                    temp_val = float(temp)
                except Exception:
                    continue
                if max_temp is None or temp_val > max_temp:
                    max_temp = temp_val

            pass_rate = (good / total * 100.0) if total > 0 else 0.0
            fail_rate = (bad / total * 100.0) if total > 0 else 0.0
            self.summary_updated.emit(
                self.group_index, total, good, bad, pass_rate, fail_rate, max_temp
            )

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
    _log.info("----应用启动----")
    qt_app = QApplication(sys.argv)
    ui = Ui_MainWidget()
    connector = Connector(ui)
    connector.show()

    set_powersupply_output(True)  # 上电

    def _cleanup():
        _log.info("----应用退出，开始清理----")
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

        set_powersupply_output(False)  # 断电
        _log.info("----清理完成----")

    qt_app.aboutToQuit.connect(_cleanup)
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
