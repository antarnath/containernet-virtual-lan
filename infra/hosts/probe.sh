#!/bin/sh
ls /sys/class/net/ > /tmp/probe_out.txt 2>&1
ls /sys/class/net/eth1/ > /tmp/probe_out2.txt 2>&1
cat /sys/class/net/eth1/iflink > /tmp/probe_out3.txt 2>&1
