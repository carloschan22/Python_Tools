# 组件注入与配方配置指南

目标：通过 `config/ProjectConfig.json` 的 `SupportedComponents` 来组合项目功能；新项目通过“注入”快速扩展能力，而不是改动大量主流程。

## 1. 配置驱动的功能开关

在 `config/ProjectConfig.json` 里为每个项目配置：

- `SupportedComponents`: 该项目启用哪些能力（组件名字符串）

示例：

- `AgingStatus`：启用老化状态解析
- `CustomRxMsg1` / `CustomRxMsg2`：启用自定义接收报文解析
- `CustomTxMsg1` / `CustomTxMsg2`：启用自定义周期发送与在线修改
- `Diagnostic`：启用 UDS/ISO-TP 诊断客户端
- `OTA` / `Updater`：启用 OTA（示例实现）
- `PeriodicTask`：启用后台周期任务线程（可注册任意 job）

## 2. PinControl 风格的调用方式

`CompManager.ComponentsInstantiation` 会根据配置初始化组件，并暴露统一的 `ops` 操作集合。

```python
from CompManager import ComponentsInstantiation

app = ComponentsInstantiation()

# 读取状态（若未启用会返回 None / []）
if "get_status" in app.ops:
    print(app["get_status"]("card_status", 15))

# 修改 Tx1 的周期任务信号（若启用 CustomTxMsg1 + PeriodicTask）
if "tx1_set" in app.ops:
    app["tx1_set"]({"HU_SMIRMColorTest": "Red"})

# 注册后台周期任务（若启用 PeriodicTask）
if "add_job" in app.ops:
    app["add_job"]("heartbeat", 1.0, lambda: print("tick"))

# 退出
app["shutdown"]()
```

## 3. 新项目扩展：通过注入添加新能力

`ComponentsInstantiation` 支持传入 `injectors`：

```python
from CompManager import ComponentsInstantiation

def my_injector(app: ComponentsInstantiation):
    # 1) 注入组件实例
    class Foo:
        def hello(self):
            return "hello"

    app.register_component("Foo", Foo())

    # 2) 注入对外操作（PinControl 风格）
    app.register_op("foo_hello", app.require("Foo").hello)

app = ComponentsInstantiation(injectors=[my_injector])
print(app["foo_hello"]())
```

建议约定：
- 组件名 = 配置 `SupportedComponents` 的字符串
- 操作名 = UI/主程序可直接调用的动作（字符串）

## 4. 周期任务 vs CAN 周期发送

- `python-can` 的 `send_periodic` 是“CAN 周期发送任务”（由库内部驱动）。
- `PeriodicTask`（本项目）是“业务周期任务线程”，用于定期执行任意 Python 回调（例如轮询、策略、心跳、定时切换信号等）。

二者可以叠加使用：
- 先创建 CAN 周期发送任务
- 再通过业务周期线程定期调用 `tx1_set/tx2_set` 修改发送内容
