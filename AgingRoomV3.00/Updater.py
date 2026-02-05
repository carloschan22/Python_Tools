from Logger import LoggerMixin
from udsoncan.client import Client
from abc import ABC, abstractmethod


class OTA(LoggerMixin, ABC):
    """用于在老化房采集卡上实现OTA的基础类"""

    def __init__(self):
        self.log.info("OTA base class initialized")

    @abstractmethod
    def start_update(self, client: Client, download_cfg: dict):
        """启动一次OTA更新"""
        raise NotImplementedError

    def _parse_intel_hex(self, file_path):
        """解析Intel HEX文件的私有方法"""
        self.log.info(f"Parsing Intel HEX file: {file_path}")

    def _download_file(self, client: Client, download_cfg: dict):
        """下载文件的私有方法"""
        self.log.info(
            f"Downloading file with config: {download_cfg} using client: {client}"
        )

    def _validate_step_result(self, step_name, response):
        """验证步骤结果的私有方法"""
        self.log.info(f"Validating step '{step_name}' with response: {response}")


class OTAType01(OTA):
    """用于实现OTA类型01的类"""

    def __init__(self):
        super().__init__()
        self.log.info("OTA Type 01 initialized")
