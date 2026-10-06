#!/bin/sh
timeout 1 tcpdump -i any -U -l -tttt -nn -vvv -w - 2>/dev/null | timeout 1 python3 /app/capture_shim.py > /tmp/out.ndjson 2>&1
echo "exit=$?"
ls -la /tmp/out.ndjson
head -1 /tmp/out.ndjson
