# PC3 — third host in the virtual LAN.
FROM containernet-host-base:latest

LABEL host.id="pc3" \
      host.name="PC3" \
      host.ip="10.10.0.13"

ENV HOST_ID=pc3 \
    HOST_NAME="PC3" \
    HOST_IP=10.10.0.13

# Run the host agent by default. docker-compose can override if needed.
CMD ["python3", "/app/host-agent/agent.py"]