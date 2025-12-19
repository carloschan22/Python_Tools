import can
import src.uds_service as uds_service


def main():

    bus = can.Bus(
        interface=uds_service.diag_config["can_bus"]["interface"],
        channel=uds_service.diag_config["can_bus"]["channel"],
        bitrate=uds_service.diag_config["can_bus"]["bitrate"],
        data_bitrate=uds_service.diag_config["can_bus"]["data_bitrate"],
        fd=uds_service.diag_config["can_bus"]["fd"],
    )

    DS = uds_service.DiagService(
        bus=bus,
    )
    stack = DS.uds_set_stack()
    print("ISOTP栈创建成功")

    client = DS.uds_create_client(stack=stack)
    print("UDS客户端创建成功")

    with client:
        response = client.read_data_by_identifier(0xF197)  # type: ignore[reportArgumentType]
        print(f"读取DID 0xF197 响应: {response.data}")
        response = client.change_session(3)  # type: ignore[reportArgumentType]
        if response.positive:
            print("切换到编程会话成功")
            try:
                response = client.unlock_security_access(1)  # type: ignore[reportArgumentType]
                if response.positive:
                    print("安全访问级别1成功")
                    response = client.read_data_by_identifier(0xF197)  # type: ignore[reportArgumentType]
                    print(f"读取DID 0xF197 响应: {response.data}")
                else:
                    print("安全访问级别1失败")
            except Exception as e:
                print(f"会话切换或安全访问失败: {e}")

    DS.uds_update_stack_address(stack, txid=0x7DF, rxid=0x7E8)
    print("ISOTP地址已更改为 txid=0x7DF, rxid=0x7E8")

    del DS
    bus.shutdown()


if __name__ == "__main__":
    main()
