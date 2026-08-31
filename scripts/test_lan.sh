#!/usr/bin/env bash
#
# scripts/test_lan.sh
#
# Verifies the ContainerNet virtual LAN works by pinging every host from
# every other host. Exits 0 if all combinations succeed, 1 otherwise.
#
# Usage:
#   chmod +x scripts/test_lan.sh
#   ./scripts/test_lan.sh

set -e

HOSTS=("pc1" "pc2" "pc3")
PASS=0
FAIL=0

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ContainerNet — Virtual LAN Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 1. Confirm all containers are running
echo ""
echo "→ Checking container status..."
for h in "${HOSTS[@]}"; do
  STATUS=$(docker inspect --format='{{.State.Status}}' "$h" 2>/dev/null || echo "missing")
  if [ "$STATUS" = "running" ]; then
    echo "  ✓ $h is running"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $h is NOT running (status: $STATUS)"
    FAIL=$((FAIL + 1))
  fi
done

# 2. Confirm each host has the expected IP
echo ""
echo "→ Checking host IPs..."
declare -A EXPECTED_IP
EXPECTED_IP[pc1]="10.10.0.11"
EXPECTED_IP[pc2]="10.10.0.12"
EXPECTED_IP[pc3]="10.10.0.13"

for h in "${HOSTS[@]}"; do
  ACTUAL_IP=$(docker exec "$h" sh -c "hostname -i 2>/dev/null || ip -4 addr show eth0 | grep inet | awk '{print \$2}' | cut -d/ -f1" 2>/dev/null | tr -d '\r\n ')
  EXPECTED="${EXPECTED_IP[$h]}"
  if [ "$ACTUAL_IP" = "$EXPECTED" ]; then
    echo "  ✓ $h has IP $ACTUAL_IP"
    PASS=$((PASS + 1))
  else
    echo "  ✗ $h has IP '$ACTUAL_IP', expected '$EXPECTED'"
    FAIL=$((FAIL + 1))
  fi
done

# 3. Ping every host from every other host
echo ""
echo "→ Pinging all combinations..."
for src in "${HOSTS[@]}"; do
  for dst in "${HOSTS[@]}"; do
    if [ "$src" != "$dst" ]; then
      # Try by IP first, then by hostname
      DST_IP="${EXPECTED_IP[$dst]}"
      RESULT=$(docker exec "$src" ping -c 1 -W 2 "$DST_IP" 2>&1 | grep -c "1 received" || true)
      if [ "$RESULT" -ge 1 ]; then
        echo "  ✓ $src → $dst ($DST_IP)"
        PASS=$((PASS + 1))
      else
        echo "  ✗ $src → $dst ($DST_IP) FAILED"
        FAIL=$((FAIL + 1))
      fi
    fi
  done
done

# 4. Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results:  $PASS passed,  $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi

echo "✅ Virtual LAN is healthy!"
exit 0