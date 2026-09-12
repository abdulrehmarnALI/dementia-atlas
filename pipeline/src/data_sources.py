"""Metadata for extrernal datasets used by the pipeline."""

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
