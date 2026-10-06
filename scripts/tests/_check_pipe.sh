#!/bin/sh
# Simulate what the CMD does.
echo "STEP1: starting tcpdump for 2s..."
timeout 2 tcpdump -i any -U -l -tttt -nn -vvv -w - 2>/dev/null > /tmp/td.pcap &
TDPID=$!
sleep 1
echo "STEP2: starting another tcpdump just for fun (should see bridge traffic)..."
# Now run a second tcpdump that watches only one interface.
timeout 2 tcpdump -i eth0 -c 5 -nn 2>&1 | head -3
wait $TDPID
echo "STEP3: tcpdump done"
ls -la /tmp/td.pcap
xxd /tmp/td.pcap | head -3
