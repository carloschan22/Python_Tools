from Logger import LoggerMixin
from udsoncan.client import Client
from abc import ABC, abstractmethod


class OTA(LoggerMixin, ABC):
    """用于在老化房采集卡上实现OTA的基础类"""

    def __init__(self, client: Client = None, ota_cfg: dict = None):
        self.client = client
        self.ota_cfg = ota_cfg
        self.log.info("OTA base class initialized")

    @abstractmethod
    def start_update(self):
        """启动一次OTA更新"""
        raise NotImplementedError

    def _parse_intel_hex(self):
        """解析Intel HEX文件的私有方法"""
        self.log.info(f"Parsing Intel HEX file")

    def _download_file(self):
        """下载文件的私有方法"""
        self.log.info(
            f"Downloading file with config: {self.ota_cfg} using client: {self.client}"
        )

    def _validate_step_result(self, step_name, response):
        """验证步骤结果的私有方法"""
        self.log.info(f"Validating step '{step_name}' with response: {response}")


class OTAType01(OTA):
    """用于实现OTA类型01的类"""

    def __init__(self, client: Client = None, ota_cfg: dict = None):
        super().__init__(client, ota_cfg)
        self.log.info("OTA Type 01 initialized")
