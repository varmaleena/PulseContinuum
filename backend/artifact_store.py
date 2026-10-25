"""Private durable artifacts; local files are a cache when hosted on Lambda."""
from pathlib import Path

from aws_client import call, client
from botocore.exceptions import ClientError
from config import settings


def save_artifact(name: str, data: bytes, content_type: str) -> Path:
    path = Path(settings().data_dir) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if settings().serverless:
        call('s3', 'put_object', {'Bucket': settings().assets_bucket, 'Key': f'artifacts/{name}',
            'Body': data, 'ContentType': content_type}, 'S3_ARTIFACT')
    return path


def load_artifact(name: str) -> Path | None:
    path = Path(settings().data_dir) / name
    if settings().serverless:
        # Always refresh: another Lambda environment may have replaced the same episode's audit.
        try:
            response = client('s3').get_object(Bucket=settings().assets_bucket, Key=f'artifacts/{name}')
            data = response['Body'].read(8 * 1024 * 1024 + 1)
            response['Body'].close()
        except ClientError as exc:
            if exc.response['Error']['Code'] in ('NoSuchKey', '404'):
                return None
            raise RuntimeError('Durable artifact retrieval failed') from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return path if path.is_file() else None
