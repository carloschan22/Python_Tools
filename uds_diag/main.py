import src.tools as tools


def main():
    # 加载配置文件
    config = tools.load_config()
    print(f"配置内容: {config}")


if __name__ == "__main__":
    main()
