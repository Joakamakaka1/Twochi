#!/bin/sh
# Lambda handler with Lambda Web Adapter: the adapter forwards each invocation to this
# server. Packages are installed at the root of the zip, next to this script.
exec python3 -m uvicorn twochi_api.main:app --host 127.0.0.1 --port "${AWS_LWA_PORT:-8080}" --no-access-log
