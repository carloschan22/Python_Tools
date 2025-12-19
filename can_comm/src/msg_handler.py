"""
负责接受和发送CAN消息的处理模块，避免bus.recv()阻塞主线程
"""

import can
import cantools
from multiprocessing import Queue
from multiprocessing.queues import Empty
import sys
from pathlib import Path

current_file = Path(__file__).resolve()
testcase_dir = current_file.parent.parent  # 到达testcase目录
if str(testcase_dir) not in sys.path:
    sys.path.insert(0, str(testcase_dir))

try:
    import tools
except ImportError:
    from src import tools

can_config: dict = tools.load_config()


class MessageHandler:
    def __init__(self, send_queue, recv_queue):
        self.send_queue = send_queue
        self.recv_queue = recv_queue
        self.bus = can.Bus(
            interface=can_config["can_bus"]["interface"],
            channel=can_config["can_bus"]["channel"],
            bitrate=can_config["can_bus"]["bitrate"],
            data_bitrate=can_config["can_bus"]["data_bitrate"],
            fd=can_config["can_bus"]["fd"],
        )
        self.notifier = can.Notifier(self.bus, [self])
        self.dbc_name = f"dbc/{can_config['dbc']['file_name']}.dbc"
        self.dbc_path = tools._normalize_path("dbc", Path(self.dbc_name))
        self.dbc = cantools.db.load_file(
            filename=str(self.dbc_path),
            encoding=can_config["dbc"]["encoding"],
        )
        self.recv_running = True
        self.send_running = True
        self.product_status = {}
        self._stopping = False
        self._recv_thread = None
        self._send_thread = None

    def __call__(self, msg: can.Message):
        """Notifier callback - receives messages from bus"""
        self.recv_queue.put(msg)

    def decode_message_loop(self):
        """Main loop for decoding receive messages"""
        while self.recv_running:
            try:
                msg: can.Message = self.recv_queue.get(timeout=1)
                if msg.arbitration_id not in self.dbc._frame_id_to_message:
                    continue
                decoded_msg = self.dbc.decode_message(msg.arbitration_id, msg.data)
                self.product_status.update(decoded_msg)
                print(f"Message ID: {msg.arbitration_id}, Data: {decoded_msg}")
            except Empty:
                continue
            except Exception as e:
                print(f"Error processing message: {e}")
                continue

    def send_message_loop(self):
        """Main loop for sending messages"""
        while self.send_running:
            try:
                msg: can.Message = self.send_queue.get(timeout=1)
                self.bus.send(msg)
            except Empty:
                continue
            except Exception as e:
                print(f"Error sending message: {e}")
                continue

    def start(self):
        """启动接收和发送线程"""
        import threading

        if self._recv_thread is None or not self._recv_thread.is_alive():
            self._recv_thread = threading.Thread(
                target=self.decode_message_loop, daemon=True, name="CAN-Receiver"
            )
            self._recv_thread.start()

        if self._send_thread is None or not self._send_thread.is_alive():
            self._send_thread = threading.Thread(
                target=self.send_message_loop, daemon=True, name="CAN-Sender"
            )
            self._send_thread.start()

        return self

    def get_status(self):
        """获取最新的product状态"""
        return self.product_status.copy()

    def send_raw_message(self, arbitration_id, data, is_extended_id=False):
        """发送原始CAN消息的便捷方法"""
        msg = can.Message(
            arbitration_id=arbitration_id, data=data, is_extended_id=is_extended_id
        )
        self.send_queue.put(msg)
        return msg

    def send_dbc_message(self, message_or_id, signal_data=None):
        """使用DBC编码并发送消息的便捷方法

        用法:
        1) 只传信号字典: send_dbc_message({"Sig1": 1, "Sig2": 2}) → 根据信号自动匹配唯一DBC消息
        2) 传消息名/帧ID + 信号字典: send_dbc_message("Msg", {...})
        帧ID支持 int 或 0x前缀字符串。缺失信号补0, 多余信号忽略。
        """
        try:
            msg_def, filled_data, _encoded_data, msg = self._build_dbc_message(
                message_or_id, signal_data
            )
            self.send_queue.put(msg)
            print(f"Sending DBC message '{msg_def.name}' with data: {filled_data}")
            return msg
        except Exception as e:
            print(f"发送DBC消息失败: {e!r}")
            return None

    def set_periodic_task(
        self, message_or_id, signal_data=None, interval=0.1, duration=None
    ):
        """使用DBC编码并创建周期报文的便捷方法

        用法:
        1) 只传信号字典: set_periodic_task({"Sig1": 1, "Sig2": 2}, None, interval) → 根据信号自动匹配唯一DBC消息
        2) 传消息名/帧ID + 信号字典: set_periodic_task("Msg", {...}, interval)
        帧ID支持 int 或 0x前缀字符串。缺失信号补0, 多余信号忽略。
        返回值为周期任务句柄(可调用 task.stop() 停止)。
        """
        try:
            msg_def, filled_data, _encoded_data, msg = self._build_dbc_message(
                message_or_id, signal_data
            )
            task = self.bus.send_periodic(msg, interval, duration=duration)
            print(
                f"Started periodic DBC message '{msg_def.name}' every {interval}s with data: {filled_data}"
            )
            return task
        except Exception as e:
            print(f"创建周期DBC消息失败: {e!r}")
            return None

    def _build_dbc_message(self, message_or_id, signal_data):
        """内部工具: 按传参与DBC解析生成 can.Message

        兼容以下两种调用方式:
        - 仅传信号字典: _build_dbc_message({"Sig1":1,...}, None)
        - 传消息名/帧ID + 信号字典: _build_dbc_message("Msg", {...})

        返回 (msg_def, filled_data, encoded_data, can.Message)
        """
        # 兼容只传一个参数就是信号字典的调用方式
        if signal_data is None and isinstance(message_or_id, dict):
            signal_data = message_or_id
            message_or_id = None

        if not isinstance(signal_data, dict):
            raise ValueError("signal_data 必须是字典")

        # 按指定名称/ID解析,否则根据信号自动匹配
        if message_or_id is not None:
            msg_def = self._resolve_message_def(message_or_id)
            if msg_def is None:
                raise ValueError(f"未找到DBC消息: {message_or_id}")
        else:
            msg_def = self._find_message_by_signals(signal_data)

        filled_data = self._complete_dict(msg_def, signal_data)
        encoded_data = self.dbc.encode_message(msg_def.name, filled_data)
        msg = can.Message(arbitration_id=msg_def.frame_id, data=encoded_data)
        return msg_def, filled_data, encoded_data, msg

    def _resolve_message_def(self, message_or_id):
        """根据名称或帧ID解析DBC消息定义"""
        if isinstance(message_or_id, int):
            return next(
                (m for m in self.dbc.messages if m.frame_id == message_or_id), None
            )

        # 尝试把字符串解析为帧ID(支持'0x..'或十进制)
        if isinstance(message_or_id, str):
            try:
                frame_id = int(message_or_id, 0)
                msg_by_id = next(
                    (m for m in self.dbc.messages if m.frame_id == frame_id), None
                )
                if msg_by_id:
                    return msg_by_id
            except ValueError:
                pass
            # 按名称匹配
            try:
                return self.dbc.get_message_by_name(message_or_id)
            except KeyError:
                return None

        return None

    def _find_message_by_signals(self, signal_data):
        """根据提供的信号键集合匹配唯一的DBC消息"""
        provided = set(signal_data.keys())
        candidates = []
        for msg in self.dbc.messages:
            signal_names = {s.name for s in msg.signals}
            if provided.issubset(signal_names):
                candidates.append(msg)

        if not candidates:
            # 提供更详细的错误提示
            all_signals = set()
            for msg in self.dbc.messages:
                all_signals.update(s.name for s in msg.signals)

            missing = provided - all_signals
            if missing:
                hint = f"信号 {missing} 在DBC中不存在。"
            else:
                hint = "可能这些信号分布在多条消息中。"

            raise ValueError(f"未找到包含信号 {provided} 的单条DBC消息。{hint}")

        if len(candidates) > 1:
            names = [m.name for m in candidates]
            raise ValueError(f"匹配到多条DBC消息 {names}, 请指定消息名或帧ID")

        return candidates[0]

    def _complete_dict(self, msg_def, signal_data):
        """填补缺失的信号键,默认值为0,并忽略DBC未定义的多余键"""
        allowed = {s.name for s in msg_def.signals}
        # 仅保留DBC定义的信号
        completed = {k: v for k, v in signal_data.items() if k in allowed}
        # 补齐缺失的信号默认值0
        for signal in allowed:
            completed.setdefault(signal, 0)
        print(f"Completed signal data (filtered): {completed}")
        return completed

    def stop(self):
        """Stop the message handler"""
        if self._stopping:
            return
        self._stopping = True
        self.recv_running = False
        self.send_running = False
        self.notifier.stop()
        self.bus.shutdown()


if __name__ == "__main__":
    import time

    # 创建队列
    send_queue = Queue()
    recv_queue = Queue()

    # 创建并启动消息处理器
    mh = MessageHandler(send_queue, recv_queue).start()

    # 示例: 发送原始CAN消息
    # mh.send_raw_message(0x12, [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])

    # 示例: 发送DBC编码的消息
    # 仅传入信号字典, 将自动根据信号匹配唯一的DBC消息 (需使用DBC中实际的信号名)
    mh.send_dbc_message({"HU_Angle_AdtCmd": 1, "HU_Color_Tem_AdtCmd": 1})

    # 也可显式指定消息名/帧ID (此时只需提供部分信号, 其余自动补0)
    # mh.send_dbc_message("BCU_Input_Detection_0x011", {"BCU_0x11_0_1_Key_ON": 1})
    # mh.send_dbc_message(0x11, {"BCU_0x11_24_16_V_ON": 12500})

    # # 获取最新状态
    for _ in range(5):
        status = mh.get_status()
        print("Latest product Status:", status)
        time.sleep(1)

    # 停止消息处理器
    mh.stop()
