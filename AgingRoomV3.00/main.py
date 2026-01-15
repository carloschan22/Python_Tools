from Logger import LoggerMixin
import time
import Tools
from CompManager import ComponentsInstantiation


class Connector(LoggerMixin):
    def __init__(self):
        pass


def main():
    app = ComponentsInstantiation()

    try:
        # 周期诊断：设置要轮询的物理槽位
        app["diag_set_periodic_slots"]([7])
        # 一次性诊断：先放入 pending，结果写入 diag_results
        app["diag_set_pending_slots"]([7])

        while True:
            op_list = [
                lambda: (print("[MAIN] sleep 3s"), time.sleep(3)),
                lambda: (
                    (
                        app["diag_set_pending_slots"]([8]),
                        print(
                            "[MAIN] diag_results[slot8] =>",
                            (
                                app["diag_results"]()[8]
                                if len(app["diag_results"]()) >= 9
                                else None
                            ),
                        ),
                    )
                ),
                lambda: (
                    print("[MAIN] stop PeriodicDiag"),
                    (app["periodic_disable"]("PeriodicDiag")),
                ),
                lambda: (print("[MAIN] sleep 3s"), time.sleep(3)),
                lambda: (
                    print("[MAIN] stop PeriodicSwitchMsg1/2"),
                    (app["periodic_disable"]("PeriodicSwitchMsg1")),
                    (app["periodic_disable"]("PeriodicSwitchMsg2")),
                ),
                lambda: (
                    # (app["periodic_enable"]("PeriodicDiag")),
                    (app["periodic_enable"]("PeriodicSwitchMsg1")),
                    (app["periodic_enable"]("PeriodicSwitchMsg2")),
                ),
            ]
            time.sleep(2)
            slots = Tools.get_active_slots(app)
            print(f"[MAIN] slot{slots} results =>", slots)
            result = Tools.get_slots_results(app, slots)
            print(f"[MAIN] slot{slots} detailed results =>", result)
            # for op in op_list:
            #     op()
    except KeyboardInterrupt:
        app.shutdown()
        print("程序已终止。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
