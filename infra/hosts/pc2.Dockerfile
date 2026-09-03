# PC2 — second host in the virtual LAN.
FROM containernet-host-base:latest

LABEL host.id="pc2" \
      host.name="PC2" \
      host.ip="10.10.0.12"

ENV HOST_ID=pc2 \
    HOST_NAME="PC2" \
    HOST_IP=10.10.0.12

# Run the host agent by default. docker-compose can override if needed.
CMD ["python3", "/app/host-agent/agent.py"]