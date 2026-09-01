
import boto3

from .config import settings


class PrivateStorage:
    def __init__(self) -> None:
        self.backend = settings.storage_backend
        self._client = None
        if self.backend == "s3":
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
            )

    def ensure_bucket(self) -> None:
        if self.backend == "s3":
            assert self._client is not None
            try:
                self._client.head_bucket(Bucket=settings.s3_bucket)
            except Exception:
                self._client.create_bucket(Bucket=settings.s3_bucket)
        else:
            settings.local_storage_dir.mkdir(parents=True, exist_ok=True)

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self.ensure_bucket()
        if self.backend == "s3":
            assert self._client is not None
            self._client.put_object(
                Bucket=settings.s3_bucket, Key=key, Body=content, ContentType=content_type
            )
        else:
            destination = settings.local_storage_dir / key
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    def get(self, key: str) -> bytes:
        if self.backend == "s3":
            assert self._client is not None
            response = self._client.get_object(Bucket=settings.s3_bucket, Key=key)
            return response["Body"].read()
        path = (settings.local_storage_dir / key).resolve()
        root = settings.local_storage_dir
        if root not in path.parents:
            raise ValueError("无效对象路径")
        return path.read_bytes()


private_storage = PrivateStorage()

