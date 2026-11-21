"""인증 사진 저장소.

- S3_BUCKET이 설정돼 있으면 S3에 올리고 https://{bucket}.s3.{region}.amazonaws.com/{key} 로 제공합니다.
  (버킷에 verifications/* 공개 읽기 정책이 있어야 이 URL로 이미지가 보입니다.)
- 비어 있으면 로컬 UPLOAD_DIR에 저장하고 /uploads/{key} 로 제공합니다. (개발용)
"""
import logging
from pathlib import Path
from typing import Protocol

from app.common import BusinessException, ErrorCode
from app.core.config import settings

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
LOCAL_URL_PREFIX = "/uploads"


def detect_image_type(data: bytes) -> tuple[str, str]:
    """파일 앞부분(매직 바이트)으로 실제 형식을 확인합니다. 반환: (확장자, Content-Type)"""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    raise BusinessException(ErrorCode.INVALID_IMAGE)


class ImageStorage(Protocol):
    def save(self, key: str, data: bytes, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...

    def url(self, key: str) -> str: ...


class LocalImageStorage:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self.base_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def delete(self, key: str) -> None:
        (self.base_dir / key).unlink(missing_ok=True)

    def url(self, key: str) -> str:
        return f"{LOCAL_URL_PREFIX}/{key}"


class S3ImageStorage:
    def __init__(self, bucket: str, region: str):
        import boto3

        self.bucket = bucket
        self.region = region
        self.client = boto3.client("s3", region_name=region)

    def save(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        except Exception as exc:
            log.exception("S3 upload failed: %s", key)
            raise BusinessException(ErrorCode.IMAGE_UPLOAD_FAILED) from exc

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception:
            log.exception("S3 delete failed: %s", key)

    def url(self, key: str) -> str:
        return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"


_storage: ImageStorage | None = None


def get_image_storage() -> ImageStorage:
    global _storage
    if _storage is None:
        if settings.s3_bucket:
            _storage = S3ImageStorage(settings.s3_bucket, settings.aws_region)
        else:
            _storage = LocalImageStorage(settings.upload_dir)
    return _storage
