# Web worklog

Running notes on the web app. Pipeline notes live in `pipeline/WORKLOG.md`.

## Getting started

Loaded the gold tables into Neon with the existing loader and set up the Next.js app in `web/`. The app can now query Neon, with `/api/periods` returning all 24 periods.

Using Neon for both local development and production rather than running Postgres in Docker. S3 is parked for now since only the pipeline needs it.

The loader uses Neon's direct connection string and the app uses the pooled one. All tables sit in the `gold` schema.

## Deployment

The app is deployed on Railway with a generated URL. The Neon connection string is set as an environment variable in Railway.

## Things worth remembering

- Cast dates to text in SQL (`period_end::text`), otherwise they can shift back a day in British Summer Time.
- Source files need to be saved as UTF-8 or Turbopack refuses to build them.
- The Dementia Atlas name was already used by a government tool, so it needs a new public name at some point.
