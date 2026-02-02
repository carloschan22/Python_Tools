from __future__ import annotations
import time
import threading
from Logger import LoggerMixin
from RxParser import RxSplitter
from CanInitializer import CanBusManager
from typing import Any, Callable, Optional
from Tools import PROJECT_CONFIG, SELECTED_PROJECT


class _PeriodicWorker(LoggerMixin):
    def __init__(self):
        self._jobs: dict[str, tuple[float, Callable[[], None]]] = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def add_job(self, name: str, interval_s: float, func: Callable[[], None]) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be > 0")
        self._jobs[name] = (float(interval_s), func)

    def remove_job(self, name: str) -> None:
        self._jobs.pop(name, None)

    def has_job(self, name: str) -> bool:
        return name in self._jobs

    def list_jobs(self) -> dict[str, float]:
        """Return current scheduled jobs: {job_name: interval_seconds}."""
        return {name: float(interval_s) for name, (interval_s, _) in self._jobs.items()}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        next_run: dict[str, float] = {name: time.time() for name in self._jobs}
        while not self._stop_event.is_set():
            now = time.time()
            # 避免忙等
            time.sleep(0.01)

            for name, (interval_s, func) in list(self._jobs.items()):
                due = next_run.get(name, now)
                if now < due:
                    continue
                try:
                    func()
                except Exception as exc:
                    self.log.error(f"Periodic job '{name}' failed: {exc}")
                next_run[name] = now + interval_s


class ComponentsInstantiation(LoggerMixin):
    """统一管理任意项目各个组件的实例化对象,根据Config文件中的SupportedComponents字段进行初始化后在主程序中作用"""

    def __init__(
        self,
        group_index: int = 0,
        injectors: Optional[list[Callable[["ComponentsInstantiation"], None]]] = None,
        autostart: bool = True,
    ):
        self._group_index = group_index
        self._injectors = list(injectors or [])
        self._started = False
        self.can_manager: Optional[CanBusManager] = None

        self.project_cfg = PROJECT_CONFIG.get(SELECTED_PROJECT, {})
        self.supported = set(self.project_cfg.get("SupportedComponents", []))

        if "AgingStatus" not in self.supported:
            # AgingStatus 是基础能力：建议所有项目都显式列出
            self.log.warning(
                "SupportedComponents 未包含 AgingStatus, 已默认启用（建议补充到配置）"
            )

        self._instant_manager: dict[str, Any] = {
            "AgingStatus": None,
            "CustomRxMsg1": None,
            "CustomRxMsg2": None,
            "CustomTxMsg1": None,
            "CustomTxMsg2": None,
            "Diagnostic": None,
            "OTA": None,
            "Updater": None,
            "PowerCycle": None,
            "PeriodicSwitchMsg1": None,
            "PeriodicSwitchMsg2": None,
            "PeriodicDiag": None,
        }

        # PinControl 风格：统一对外暴露操作入口
        self.ops: dict[str, Callable[..., Any]] = {}

        # PeriodicDiag：缓存周期读取的诊断结果（供 UI/上层查询）
        self._periodic_diag_cache: dict[str, Any] = {}

        # 后台周期任务执行器（用于 PeriodicSwitch/PeriodicDiag 这类需要线程的业务）
        self._periodic_worker: Optional[_PeriodicWorker] = None

        # 注册表：保存所有可用周期 job（即使被 remove_job 停用, 也能再 enable）
        self._periodic_job_registry: dict[str, tuple[float, Callable[[], None]]] = {}

        if autostart:
            self.startup()

    def startup(self) -> None:
        if self._started:
            return
        self._started = True

        self.can_manager = CanBusManager().initialize(index=self._group_index)

        rx_cfg = self.project_cfg.get("RX", {})
        rx_id1 = rx_cfg.get("IdOfRxMsg1")
        rx_id2 = rx_cfg.get("IdOfRxMsg2")

        rx_switcher = [
            True,  # AgingStatus 基础能力
            ("CustomRxMsg1" in self.supported) and (rx_id1 is not None),
            ("CustomRxMsg2" in self.supported) and (rx_id2 is not None),
        ]
        rx_splitter = RxSplitter(self.can_manager.get_dbc(), switcher=rx_switcher)
        if any(rx_switcher):
            self.can_manager.register_listener(rx_splitter)

        self._instant_manager["AgingStatus"] = rx_splitter if rx_switcher[0] else None
        self._instant_manager["CustomRxMsg1"] = rx_splitter if rx_switcher[1] else None
        self._instant_manager["CustomRxMsg2"] = rx_splitter if rx_switcher[2] else None

        # Custom TX
        if "CustomTxMsg1" in self.supported:
            try:
                from Sending import CustomTxMsg1

                self._instant_manager["CustomTxMsg1"] = CustomTxMsg1(self.can_manager)
            except Exception as exc:
                self.log.error(f"CustomTxMsg1 实例化失败: {exc}")
        if "CustomTxMsg2" in self.supported:
            try:
                from Sending import CustomTxMsg2

                self._instant_manager["CustomTxMsg2"] = CustomTxMsg2(self.can_manager)
            except Exception as exc:
                self.log.error(f"CustomTxMsg2 实例化失败: {exc}")

        # Diagnostic (UDS)
        if "Diagnostic" in self.supported:
            try:
                from Diagnostic import MultiSlotDiagnostic

                # 40张采集卡 * 2通道 = 80个slot（外部slot序号从1开始）
                self._instant_manager["Diagnostic"] = MultiSlotDiagnostic(
                    self.can_manager.get_bus(),
                    self.can_manager.get_notifier(),
                    slot_count=80,
                )
            except Exception as exc:
                # Diagnostic.py 依赖的 Tools/第三方库可能未就绪, 避免影响其它功能
                self.log.error(f"Diagnostic 实例化失败: {exc}")

        # OTA / Updater
        if "OTA" in self.supported or "Updater" in self.supported:
            try:
                from Updater import OTAType01

                ota = OTAType01()
                if "OTA" in self.supported:
                    self._instant_manager["OTA"] = ota
                if "Updater" in self.supported:
                    self._instant_manager["Updater"] = ota
            except Exception as exc:
                self.log.error(f"OTA/Updater 实例化失败: {exc}")

        # 周期任务线程：只要任一周期类组件启用就启动
        if (
            "PeriodicSwitchMsg1" in self.supported
            or "PeriodicSwitchMsg2" in self.supported
            or "PeriodicDiag" in self.supported
        ):
            self._periodic_worker = _PeriodicWorker()
            self._periodic_worker.start()

        # 注册默认 ops（按已启用组件动态提供）
        self._register_default_ops()

        # 允许外部注入：新项目可通过 injectors 注入新组件/新操作
        if self._injectors:
            for injector in self._injectors:
                try:
                    injector(self)
                except Exception as exc:
                    self.log.error(f"Injector failed: {exc}")

    def get(self, component_name: str, default=None):
        return self._instant_manager.get(component_name, default)

    def require(self, component_name: str):
        comp = self._instant_manager.get(component_name)
        if comp is None:
            raise KeyError(
                f"组件未启用或实例化失败: {component_name}. SupportedComponents={sorted(self.supported)}"
            )
        return comp

    # -------- Injection-friendly APIs --------

    def register_component(self, name: str, instance: Any) -> None:
        self._instant_manager[name] = instance

    def register_op(self, name: str, func: Callable[..., Any]) -> None:
        self.ops[name] = func

    def __getitem__(self, op_name: str) -> Callable[..., Any]:
        return self.ops[op_name]

    def _register_default_ops(self) -> None:
        # Rx status query
        rx = (
            self._instant_manager.get("AgingStatus")
            or self._instant_manager.get("CustomRxMsg1")
            or self._instant_manager.get("CustomRxMsg2")
        )
        if rx is not None:
            self.register_op("get_status", rx.get_status)

        tx_cfg = self.project_cfg.get("TX", {})
        id_tx1 = tx_cfg.get("IdOfTxMsg1")
        id_tx2 = tx_cfg.get("IdOfTxMsg2")

        # 缓存：每个 Msg* 固定存 [ch1_task, ch2_task], 允许某通道为 None
        periodic_tasks: dict[str, Any] = {
            "TxMsg1": None,
            "TxMsg2": None,
        }
        tx1 = self._instant_manager.get("CustomTxMsg1")
        tx2 = self._instant_manager.get("CustomTxMsg2")

        if tx1 is not None:

            def _tx1_set(signal_data: dict, message_name_or_id=None):
                tasks = periodic_tasks.get("TxMsg1")
                if tasks is None:
                    # 默认创建 CH1+CH2 两路周期任务；若只需要单路, 可调用 tx1_start
                    tasks = tx1.create_periodic_task(ch1=True, ch2=True)
                    periodic_tasks["TxMsg1"] = tasks
                if message_name_or_id is None:
                    message_name_or_id = id_tx1
                return tx1.modify_periodic_task(
                    tasks,
                    message_name_or_id=message_name_or_id,
                    signal_data=signal_data,
                )

            self.register_op("tx1_set", _tx1_set)

            def _tx1_start(ch1: bool = True, ch2: bool = True):
                periodic_tasks["TxMsg1"] = tx1.create_periodic_task(ch1=ch1, ch2=ch2)
                return periodic_tasks["TxMsg1"]

            self.register_op("tx1_start", _tx1_start)

        if tx2 is not None:

            def _tx2_set(signal_data: dict, message_name_or_id=None):
                tasks = periodic_tasks.get("TxMsg2")
                if tasks is None:
                    tasks = tx2.create_periodic_task(ch1=True, ch2=True)
                    periodic_tasks["TxMsg2"] = tasks
                if message_name_or_id is None:
                    message_name_or_id = id_tx2
                return tx2.modify_periodic_task(
                    tasks,
                    message_name_or_id=message_name_or_id,
                    signal_data=signal_data,
                )

            self.register_op("tx2_set", _tx2_set)

            def _tx2_start(ch1: bool = True, ch2: bool = True):
                periodic_tasks["TxMsg2"] = tx2.create_periodic_task(ch1=ch1, ch2=ch2)
                return periodic_tasks["TxMsg2"]

            self.register_op("tx2_start", _tx2_start)

        # Diagnostic shortcuts (MultiSlot)
        diag = self._instant_manager.get("Diagnostic")
        if diag is not None:
            # 外部可动态更新待诊断slot列表（序号从1开始）
            self.register_op("diag_set_pending_slots", diag.set_pending_slots)
            self.register_op("diag_add_pending_slots", diag.add_pending_slots)
            self.register_op("diag_get_pending_slots", lambda: list(diag.pending_slots))

            def _diag_run_pending_once(dids: Optional[list[str]] = None):
                diag_cfg = self.project_cfg.get("Diag", {})
                if dids is None:
                    periodic_diag_cfg = diag_cfg.get("PeriodicDiag", {})
                    dids = periodic_diag_cfg.get("Dids")
                    if dids is None:
                        did_cfg = diag_cfg.get("DidConfig") or {}
                        dids = list(did_cfg.keys())
                return diag.run_pending_once(dids or [])

            self.register_op("diag_run_pending_once", _diag_run_pending_once)

            self.register_op("diag_results", lambda: list(diag.results))

            def _diag_read_did(slot: int, did_hex: str):
                return diag.read_dids(int(slot), [did_hex]).get(did_hex)

            self.register_op("diag_read_did", _diag_read_did)

            def _diag_periodic_snapshot():
                return diag.periodic_snapshot()

            self.register_op("diag_periodic_snapshot", _diag_periodic_snapshot)

            # 可选：后台自动诊断（直到成功一次即移除）
            # 运行频率默认用 PeriodicDiag.ReDiagInterval（没配就 1s）
            if self._periodic_worker is not None:
                diag_cfg = self.project_cfg.get("Diag", {})
                periodic_diag_cfg = diag_cfg.get("PeriodicDiag", {})
                diag_tick = periodic_diag_cfg.get("ReDiagInterval", 1)
                try:
                    diag_tick = float(diag_tick)
                except Exception:
                    diag_tick = 1.0
                if diag_tick <= 0:
                    diag_tick = 1.0

                def _job_diagnostic_once(_tick_dids=None):
                    # 没有待诊断slot就不做事
                    if not diag.pending_slots:
                        return
                    dids = _tick_dids
                    if dids is None:
                        pd_cfg = diag_cfg.get("PeriodicDiag", {})
                        dids = pd_cfg.get("Dids")
                        if dids is None:
                            did_cfg = diag_cfg.get("DidConfig") or {}
                            dids = list(did_cfg.keys())
                    diag.run_pending_once(list(dids or []))

                self._periodic_job_registry["Diagnostic"] = (
                    diag_tick,
                    _job_diagnostic_once,
                )
                self._periodic_worker.add_job(
                    "Diagnostic", diag_tick, _job_diagnostic_once
                )

        # Periodic worker management
        if self._periodic_worker is not None:
            self.register_op("add_job", self._periodic_worker.add_job)
            self.register_op("remove_job", self._periodic_worker.remove_job)

            def _periodic_list_jobs():
                return {
                    "running": self._periodic_worker.list_jobs(),
                    "registered": {
                        name: float(interval)
                        for name, (interval, _) in self._periodic_job_registry.items()
                    },
                }

            self.register_op("periodic_list_jobs", _periodic_list_jobs)

            def _periodic_worker_stop(timeout: float = 2.0):
                self._periodic_worker.stop(timeout=timeout)

            self.register_op("periodic_worker_stop", _periodic_worker_stop)

            def _periodic_worker_start():
                self._periodic_worker.start()

            self.register_op("periodic_worker_start", _periodic_worker_start)

            def _periodic_disable(job_name: str):
                self._periodic_worker.remove_job(job_name)

            self.register_op("periodic_disable", _periodic_disable)

            def _periodic_enable(job_name: str):
                if self._periodic_worker.has_job(job_name):
                    return
                cfg = self._periodic_job_registry.get(job_name)
                if cfg is None:
                    raise KeyError(
                        f"Unknown periodic job: {job_name}. Available={sorted(self._periodic_job_registry.keys())}"
                    )
                interval_s, func = cfg
                self._periodic_worker.add_job(job_name, interval_s, func)

            self.register_op("periodic_enable", _periodic_enable)

            def _periodic_restart(job_name: str):
                self._periodic_worker.remove_job(job_name)
                _periodic_enable(job_name)

            self.register_op("periodic_restart", _periodic_restart)

            # PeriodicSwitchMsg1/2：按配置周期切换发送内容
            switching_cfg = tx_cfg.get("PeriodicSwitching", {})

            if "PeriodicSwitchMsg1" in self.supported and tx1 is not None:
                sw = switching_cfg.get("SwitchMsg1", {})
                # Switch 开关已移除：是否启用由 SupportedComponents 决定
                if sw.get("Data"):
                    interval = float(sw.get("SwitchInterval", 5))
                    data_list = list(sw.get("Data") or [])
                    idx = {"i": 0}

                    # 注意：Python 没有 block-scope, 下面的 data_list/idx 会被后续 if 覆盖。
                    # 用默认参数绑定, 确保 SwitchMsg1 永远使用自己的 Data。
                    def _job_msg1(_data_list=data_list, _idx=idx, _msg_id=id_tx1):
                        item = _data_list[_idx["i"] % len(_data_list)]
                        _idx["i"] += 1
                        if "tx1_set" in self.ops:
                            self.ops["tx1_set"](item, message_name_or_id=_msg_id)

                    self._instant_manager["PeriodicSwitchMsg1"] = {
                        "interval": interval,
                        "count": len(data_list),
                    }
                    self._periodic_job_registry["PeriodicSwitchMsg1"] = (
                        interval,
                        _job_msg1,
                    )
                    self._periodic_worker.add_job(
                        "PeriodicSwitchMsg1", interval, _job_msg1
                    )

            if "PeriodicSwitchMsg2" in self.supported and tx2 is not None:
                sw = switching_cfg.get("SwitchMsg2", {})
                # Switch 开关已移除：是否启用由 SupportedComponents 决定
                if sw.get("Data"):
                    interval = float(sw.get("SwitchInterval", 5))
                    data_list = list(sw.get("Data") or [])
                    idx = {"i": 0}

                    # 同上：用默认参数绑定, 避免闭包拿到 SwitchMsg1 的变量或被覆盖。
                    def _job_msg2(_data_list=data_list, _idx=idx, _msg_id=id_tx2):
                        item = _data_list[_idx["i"] % len(_data_list)]
                        _idx["i"] += 1
                        if "tx2_set" in self.ops:
                            self.ops["tx2_set"](item, message_name_or_id=_msg_id)

                    self._instant_manager["PeriodicSwitchMsg2"] = {
                        "interval": interval,
                        "count": len(data_list),
                    }
                    self._periodic_job_registry["PeriodicSwitchMsg2"] = (
                        interval,
                        _job_msg2,
                    )
                    self._periodic_worker.add_job(
                        "PeriodicSwitchMsg2", interval, _job_msg2
                    )

            # PeriodicDiag：按配置轮询 DID 并缓存
            if "PeriodicDiag" in self.supported:
                if diag is None:
                    self.log.warning(
                        "PeriodicDiag 已启用, 但 Diagnostic 未启用/实例化失败；将跳过周期诊断"
                    )
                else:
                    diag_cfg = self.project_cfg.get("Diag", {})
                    # 新结构：Diag.PeriodicDiag 定义轮询间隔与 DID 列表
                    periodic_diag_cfg = diag_cfg.get("PeriodicDiag", {})
                    interval = periodic_diag_cfg.get("Interval", 10)
                    try:
                        interval = float(interval)
                    except Exception:
                        interval = 10.0

                    rediag_interval = periodic_diag_cfg.get("ReDiagInterval", 1)
                    try:
                        rediag_interval = float(rediag_interval)
                    except Exception:
                        rediag_interval = 1.0

                    did_list = periodic_diag_cfg.get("Dids")
                    self.log.debug(f"PeriodicDiag 配置的周期DID列表: {did_list}")
                    if did_list is None:
                        # 兼容旧行为：未配置 Dids 时使用 DidConfig 全量
                        did_cfg = diag_cfg.get("DidConfig") or {}
                        did_list = list(did_cfg.keys())

                    if isinstance(did_list, dict):
                        if not did_list:
                            self.log.warning(
                                "PeriodicDiag 已启用, 但 Diag.PeriodicDiag.Dids 为空；将跳过周期诊断"
                            )
                            did_list = {}
                    elif not isinstance(did_list, list) or not did_list:
                        self.log.warning(
                            "PeriodicDiag 已启用, 但 Diag.PeriodicDiag.Dids 为空；将跳过周期诊断"
                        )
                        did_list = []

                    if did_list:

                        # PeriodicDiag 与 Diagnostic 共用同一个 MultiSlotDiagnostic：
                        # - 周期诊断的 slot 列表由外部设置：diag.set_periodic_slots
                        # - 失败则按 ReDiagInterval 更快重试
                        diag.configure_periodic(
                            interval_s=interval,
                            rediag_interval_s=rediag_interval,
                            dids=did_list,
                        )

                        # 默认：若外部没设置 periodic_slots, 则不自动跑（避免误扫全部80个slot）
                        self.register_op(
                            "diag_set_periodic_slots", diag.set_periodic_slots
                        )
                        self.register_op(
                            "diag_get_periodic_slots", lambda: list(diag.periodic_slots)
                        )

                        # 为了支持 ReDiagInterval, 这个 job 的运行频率取 min(interval, rediag_interval)
                        tick_interval = (
                            min(interval, rediag_interval)
                            if rediag_interval > 0
                            else interval
                        )
                        if tick_interval <= 0:
                            tick_interval = interval if interval > 0 else 1.0

                        def _job_diag():
                            # 执行一次 tick（内部会按每个slot的 next_due 决定是否真的发请求）
                            diag.periodic_tick()
                            self._periodic_diag_cache = diag.periodic_snapshot()

                        self._instant_manager["PeriodicDiag"] = {
                            "interval": interval,
                            "count": len(did_list),
                            "rediag_interval": rediag_interval,
                        }
                        self._periodic_job_registry["PeriodicDiag"] = (
                            tick_interval,
                            _job_diag,
                        )
                        self._periodic_worker.add_job(
                            "PeriodicDiag", tick_interval, _job_diag
                        )

        # Lifecycle
        self.register_op("shutdown", self.shutdown)

    def shutdown(self) -> None:
        # stop periodic worker first
        if self._periodic_worker is not None:
            self._periodic_worker.stop()

        diag = self._instant_manager.get("Diagnostic")
        if diag is not None:
            try:
                if hasattr(diag, "shutdown"):
                    diag.shutdown()
            except Exception:
                pass

        if self.can_manager is not None:
            self.can_manager.shutdown()
