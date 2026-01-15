from Logger import LoggerMixin
import time

from CompManager import ComponentsInstantiation


class Connector(LoggerMixin):
    def __init__(self):
        pass


def main():
    app = ComponentsInstantiation()

    try:
        app["diag_set_periodic_slots"]([8])
        while True:
            op_list = [
                lambda: (print("[MAIN] sleep 3s"), time.sleep(3)),
                lambda: (
                    (
                        app["diag_set_pending_slots"]([8]),
                        print(
                            "[MAIN] diag_results[slot8] =>",
                            (
                                app["diag_results"]()[7]
                                if len(app["diag_results"]()) >= 8
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

            # for op in op_list:
            #     op()
    except KeyboardInterrupt:
        app.shutdown()
        print("程序已终止。")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
