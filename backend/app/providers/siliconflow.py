"""Historical SiliconFlow adapter retained for old records only.

Version 2 routes new work through Agnes and no longer has SiliconFlow
configuration fields. Keeping an explicit failing adapter makes accidental
use visible without breaking imports of old tooling.
"""

from ..config import Settings


class ProviderNotConfigured(RuntimeError):
    pass


class SiliconFlowVideoProvider:
    name = "siliconflow"

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or Settings()

    def validate_config(self) -> None:
        raise ProviderNotConfigured("SiliconFlow 已在第二版停用，请使用 Mock 或 Agnes")

    def submit_video_job(self, *args, **kwargs):
        self.validate_config()

    def get_video_job_status(self, *args, **kwargs):
        self.validate_config()

    def download_video(self, *args, **kwargs):
        self.validate_config()

    def cancel_video_job(self, *args, **kwargs):
        self.validate_config()
