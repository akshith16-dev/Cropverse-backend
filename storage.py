"""Storage abstraction: S3/R2 where configured, local files otherwise."""
import asyncio
import logging
from pathlib import Path
from uuid import uuid4
from config import settings

logger = logging.getLogger("cropverse")

class Storage:
    @property
    def using_s3(self) -> bool:
        return bool(settings.S3_BUCKET and settings.S3_ACCESS_KEY and settings.S3_SECRET_KEY)

    async def save(self, content: bytes, filename: str, content_type: str, folder: str) -> str:
        key = f"{folder}/{uuid4().hex}{Path(filename).suffix.lower()}"
        if self.using_s3:
            return await asyncio.to_thread(self._save_s3, content, key, content_type)
        path = Path(__file__).with_name("uploads") / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return f"/uploads/{key}"

    def _save_s3(self, content: bytes, key: str, content_type: str) -> str:
        try:
            import boto3
            client = boto3.client("s3", aws_access_key_id=settings.S3_ACCESS_KEY, aws_secret_access_key=settings.S3_SECRET_KEY, region_name=settings.S3_REGION or None, endpoint_url=settings.S3_ENDPOINT_URL or None)
            client.put_object(Bucket=settings.S3_BUCKET, Key=key, Body=content, ContentType=content_type)
            if settings.S3_PUBLIC_BASE_URL:
                return f"{settings.S3_PUBLIC_BASE_URL.rstrip('/')}/{key}"
            return f"https://{settings.S3_BUCKET}.s3.{settings.S3_REGION}.amazonaws.com/{key}"
        except Exception:
            logger.exception("Object storage upload failed")
            raise

storage = Storage()
