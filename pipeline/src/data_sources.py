"""Metadata for external datasets held in S3.

NOT part of the silver build. This and ``ingest.py`` are the original S3 download
stubs from before the raw releases were kept locally under ``data/raw/pcdd/``;
nothing in ``src/`` imports them. Kept for when the raw files are fetched from the
bucket rather than copied by hand.
"""

DATA_SOURCES = {
    "nhs_primary_care_dementia": {
        "s3_prefix": "raw/nhs/primary-care-dementia/",
        "releases": [
            "2026-03",
        ],
    },

    "ons_geography": {
        "s3_prefix": "raw/ons/",
        "releases": [],
    },
}
