#!/usr/bin/env python3
"""snmptrapd traphandle: turn one trap (on stdin) into one JSON line.

snmptrapd passes: line 1 = hostname, line 2 = transport address, then one "OID value" line per varbind.
Output: /var/log/trapd/traps-YYYY-MM-DD.jsonl (UTC day), read by the Vector shipper.
"""
import datetime
import fcntl
import json
import os
import re
import sys

OUT_DIR = os.environ.get("TRAP_OUT_DIR", "/var/log/trapd")
SYS_UPTIME_OID = ".1.3.6.1.2.1.1.3.0"
SNMP_TRAP_OID = ".1.3.6.1.6.3.1.1.4.1.0"
ADDR_RE = re.compile(r"\[([0-9A-Fa-f:.]+)\]:\d+->")


def main() -> None:
    lines = sys.stdin.read().splitlines()
    now = datetime.datetime.now(datetime.timezone.utc)
    hostname = lines[0].strip() if lines else ""
    transport = lines[1].strip() if len(lines) > 1 else ""
    match = ADDR_RE.search(transport)
    source_ip = match.group(1) if match else hostname

    varbinds = []
    for line in lines[2:]:
        oid, _, value = line.strip().partition(" ")
        if not oid:
            continue
        if not oid.startswith("."):
            oid = "." + oid
        varbinds.append({"oid": oid, "value": value.strip().strip('"')})

    by_oid = {vb["oid"]: vb["value"] for vb in varbinds}
    record = {
        "schema": "monicomm.trap.v1",
        "kind": "trap",
        "received_at": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "source_ip": source_ip,
        "transport": transport,
        "trap_oid": by_oid.get(SNMP_TRAP_OID),
        "device_uptime": by_oid.get(SYS_UPTIME_OID),
        "varbinds": varbinds,
    }

    path = os.path.join(OUT_DIR, f"traps-{now:%Y-%m-%d}.jsonl")
    with open(path, "a", encoding="utf-8") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.write(json.dumps(record, ensure_ascii=False) + "\n")
        fcntl.flock(out, fcntl.LOCK_UN)


if __name__ == "__main__":
    main()
