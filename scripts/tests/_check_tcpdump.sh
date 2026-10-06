#!/bin/sh
timeout 1 tcpdump -i any -U -l -tttt -nn -vvv -w - 2>/dev/null > /tmp/raw.pcap
echo "tcpdump exit=$?"
ls -la /tmp/raw.pcap
xxd /tmp/raw.pcap | head -3
