"""Download raw project data from S3"""

import boto3

from .data_sources import DATA_SOURCES

BUCKET_NAME = "aali-dementia-atlas"


def list_release_files(source_name: str, release: str) -> list[str]:
    source = DATA_SOURCES[source_name]
    prefix = f"{source['s3_prefix']}{release}/"

    # Give a python client for talking to Amazon S3:
    s3 = boto3.client("s3")

    # Call S3's ListObjectsV2 operation and use it via a paginator:
    # i.e. s3.list_objects_v2(Bucket="aali-dementia-atlas", Prefix="raw/nhs/primary-care-dementia/2026-03")
    paginator = s3.get_paginator("list_objects_v2")

    pages = paginator.paginate(
        Bucket=BUCKET_NAME,
        Prefix=prefix,
    )

    files: list[str] = []

    for page in pages:
        for item in page.get("Contents", []):
            key = item["Key"]
            print(item["Key"])

            if not key.endswith("/"):
                files.append(key)

    return files
