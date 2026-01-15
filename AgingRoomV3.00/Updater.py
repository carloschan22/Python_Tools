from Logger import LoggerMixin


class OTA(LoggerMixin):
    """用于在老化房采集卡上实现OTA的基础类"""

    def __init__(self):
        self.log.info("OTA base class initialized")


class OTAType01(OTA):
    """用于实现OTA类型01的类"""

    def __init__(self):
        super().__init__()
        self.log.info("OTA Type 01 initialized")
