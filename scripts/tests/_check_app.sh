#!/bin/sh
ls -la /app/
echo "---"
python3 /app/capture_shim.py < /dev/null
echo "shim stdin-empty exit=$?"
