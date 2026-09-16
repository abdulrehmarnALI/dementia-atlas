"""Download raw project data from S3.

NOT part of the silver build - see ``data_sources.py``. The build reads the raw
releases already on disk under ``data/raw/pcdd/``.
"""

import boto3

from .data_sources import DATA_SOURCES

BUCKET_NAME = "aali-dementia-atlas"


def list_release_files(source_name: str, release: str) -> list[str]:
    source = DATA_SOURCES[source_name]
    prefix = f"{source['s3_prefix']}{release}/"

    s3 = boto3.client("s3")

    # ListObjectsV2 is paginated; e.g. Prefix="raw/nhs/primary-care-dementia/2026-03/"
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix)

    files: list[str] = []
    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            if not key.endswith("/"):
                files.append(key)

    return files
