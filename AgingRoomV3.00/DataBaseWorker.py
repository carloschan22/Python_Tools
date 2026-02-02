import os
import sqlite3
import threading
import queue
import json
from datetime import datetime
from typing import List, Tuple, Any, Optional
from Logger import LoggerMixin


class DataBaseWorker(LoggerMixin):
    """用于管理老化数据的数据库工作类"""

    def __init__(self):
        self.db_path = "./aging_data.db"
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.cursor = self.connection.cursor()
        self._queue: "queue.Queue[tuple[str, Tuple[Any, ...]]]" = queue.Queue()
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None

    def check_database_exists(self) -> bool:
        return os.path.isfile(self.db_path)

    def makesure_file_exist(self):
        folder = os.path.dirname(self.db_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        if not os.path.isfile(self.db_path):
            open(self.db_path, "w").close()
        self.log.info("Database file ensured to exist.")

    def initialization(self):
        if not self.check_database_exists():
            self.makesure_file_exist()
        self.log.info("Database initialized.")

    def create_new_table(self):
        """生成以日期和序号命名的新表,表名结构:yyyy_mm_dd_nn
        表数据结构:
        - Id: INTEGER (自增序号)
        - Slot: INTEGER
        - Timestamp: REAL
        - Status: INTEGER
        - Voltage: REAL
        - Current: REAL
        - Temperature: REAL
        - DtcCodes: TEXT
        - AdditionalInfo_1: TEXT
        - AdditionalInfo_2: TEXT
        - DiagResults: TEXT
        """
        today_prefix = datetime.now().strftime("%Y_%m_%d")
        self.cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
            (f"{today_prefix}_%",),
        )
        existing = [row[0] for row in self.cursor.fetchall()]
        indices = []
        for name in existing:
            parts = name.split("_")
            if len(parts) >= 4:
                try:
                    indices.append(int(parts[-1]))
                except Exception:
                    pass
        next_idx = max(indices) + 1 if indices else 1
        table_name = f"{today_prefix}_{next_idx:02d}"

        self.cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{table_name}" (
                Id INTEGER PRIMARY KEY AUTOINCREMENT,
                Slot INTEGER,
                Timestamp REAL,
                Status INTEGER,
                Voltage REAL,
                Current REAL,
                Temperature REAL,
                DtcCodes TEXT,
                AdditionalInfo_1 TEXT,
                AdditionalInfo_2 TEXT,
                DiagResults TEXT
            )
            """
        )
        self.connection.commit()
        self.log.info(f"Created table: {table_name}")
        return table_name

    def query_data(
        self, table_name: str, conditions: str = ""
    ) -> List[Tuple[Any, ...]]:
        if not table_name:
            return []
        sql = f'SELECT * FROM "{table_name}"'
        if conditions:
            sql += f" WHERE {conditions}"
        self.cursor.execute(sql)
        return self.cursor.fetchall()

    def querying_thread(self): ...
    def start_querying(self): ...
    def stop_querying(self): ...

    def insert_data(self, table_name: str, data: Any):
        if not table_name:
            raise ValueError("table_name is required")

        if isinstance(data, dict):
            rows = self.build_rows_from_snapshot(data)
            for row in rows:
                self._insert_row(table_name, row)
            self.connection.commit()
            return

        if not isinstance(data, (tuple, list)) or len(data) != 10:
            raise ValueError("data must be a 10-field tuple or a snapshot dict")
        self._insert_row(table_name, tuple(data))
        self.connection.commit()

    def _insert_row(self, table_name: str, row: Tuple[Any, ...]):
        self.cursor.execute(
            f"""
            INSERT INTO "{table_name}" (
                Slot, Timestamp, Status, Voltage, Current, Temperature,
                DtcCodes, AdditionalInfo_1, AdditionalInfo_2, DiagResults
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            row,
        )

    def writing_thread(self):
        """后台写入线程：从队列取数据并写入数据库。"""
        while not self._stop_event.is_set():
            try:
                table_name, data = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                self.insert_data(table_name, data)
            except Exception as exc:
                self.log.error(f"DB insert failed: {exc}")
            finally:
                self._queue.task_done()

    def start_writing(self):
        if self._worker is not None and self._worker.is_alive():
            return
        self._stop_event.clear()
        self._worker = threading.Thread(target=self.writing_thread, daemon=True)
        self._worker.start()

    def stop_writing(self):
        self._stop_event.set()
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None

    def enqueue(self, table_name: str, data: Any):
        """可选：异步写入队列。"""
        self._queue.put((table_name, data))

    @staticmethod
    def _json_dumps(value: Any) -> str:
        def _default(obj):
            if isinstance(obj, (bytes, bytearray)):
                return obj.hex()
            return str(obj)

        return json.dumps(value, ensure_ascii=False, default=_default)

    def build_row_from_status(self, slot: int, status: dict) -> Tuple[Any, ...]:
        """将单槽位状态转换为数据库行。"""
        card_status = status.get("card_status") or {}
        timestamp = card_status.get("Timestamp")
        st = card_status.get("Status")
        voltage = card_status.get("Voltage")
        current = card_status.get("Current")
        temperature = card_status.get("CardTemperature")

        dtc_codes = status.get("dtc_codes", [])
        if dtc_codes is None:
            dtc_codes = []

        custom_rx1 = status.get("custom_rx1")
        custom_rx2 = status.get("custom_rx2")

        diag_results = status.get("diag_results")
        diag_payload = diag_results

        return (
            int(slot),
            timestamp,
            st,
            voltage,
            current,
            temperature,
            self._json_dumps(dtc_codes),
            self._json_dumps(custom_rx1),
            self._json_dumps(custom_rx2),
            self._json_dumps(diag_payload),
        )

    def build_rows_from_snapshot(self, snapshot: dict) -> List[Tuple[Any, ...]]:
        """将多槽位状态快照转换为多行数据。"""
        rows: List[Tuple[Any, ...]] = []
        for slot, status in (snapshot or {}).items():
            try:
                rows.append(self.build_row_from_status(int(slot), status or {}))
            except Exception as exc:
                self.log.error(f"build_row_from_status failed for slot={slot}: {exc}")
        return rows

    def close(self):
        self.connection.close()


if __name__ == "__main__":
    db_worker = DataBaseWorker()
    db_worker.initialization()
    data = {
        8: {
            "card_status": {
                "Timestamp": 1770020616.1704073,
                "Status": -1,
                "Voltage": 11.8,
                "Current": 257.06,
                "CardInfo": {
                    "slave_configed": "configed",
                    "reserve_1": "default",
                    "output_status": "open",
                    "current_status": "normal",
                    "voltage_status": "normal",
                    "can_status": "normal",
                    "reserve_2": "default",
                    "reserve_3": "default",
                },
                "CardTemperature": 40,
                "ResistorInfo": {"main_can": 120, "can_1": 120, "can_2": 9999},
            },
            "custom_rx1": {
                "CMSIVideoAngel": "FOV direction 5",
                "CMSIVideoZoom": "Zoom level 1",
                "CMSIDispMod": "Video mode",
                "CMSIVideoBackLi": "Backlight brightness level 7",
                "CMSII2BusErrSt": "Normal",
                "CMSIPwrErrSt": "Normal",
                "CMSILCDErrSt": "Normal",
                "CMSISnsrErrSt": "Normal",
                "CMSIVideoErrSt": "Fault",
            },
            "custom_rx2": None,
            "diag_results": {"0x8114": None},
            "diag_periodic_snapshot": {"0x8114": bytearray(b"\x81\x14")},
        }
    }
    db_worker.create_new_table()
    rows = db_worker.build_rows_from_snapshot(data)
    for row in rows:
        db_worker.insert_data("2026_02_02_01", row)
    db_worker.close()
