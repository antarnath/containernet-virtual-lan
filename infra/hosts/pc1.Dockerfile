# PC1 — first host in the virtual LAN.
# Derives from the shared host base image; sets identity + runs the agent.
FROM containernet-host-base:latest

LABEL host.id="pc1" \
      host.name="PC1" \
      host.ip="10.10.0.11"

ENV HOST_ID=pc1 \
    HOST_NAME="PC1" \
    HOST_IP=10.10.0.11

# Command overridden in docker-compose.yml to run the agent.