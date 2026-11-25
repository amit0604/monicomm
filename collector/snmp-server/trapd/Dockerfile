# snmptrapd for the Monicomm SNMP server: receives v3 informs/traps (and optional v2c),
# writes one JSON line per trap for the Vector shipper.
FROM debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2

# Versions pinned. If the build machine can't find these versions (Debian security update),
# bump them to the current deb13uN and note it in the PR.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      snmptrapd=5.9.4+dfsg-2+deb13u1 \
      snmp=5.9.4+dfsg-2+deb13u1 \
      python3-minimal=3.13.5-1 \
 && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
COPY trap2json.py /usr/local/bin/trap2json
RUN chmod 0755 /usr/local/bin/entrypoint.sh /usr/local/bin/trap2json

# Don't try to load MIBs: traps are written with numeric OIDs, Monicomm translates them.
ENV MIBS=""

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
