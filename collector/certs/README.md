# certs/

Put this VM's mTLS files here (made by `../pki/make-certs.sh`). Everything except this README is git-ignored.

| VM | Files |
|---|---|
| Syslog server | `ca.crt`, `collector.crt`, `collector.key` from `pki/out/syslog-server/` |
| SNMP server | `ca.crt`, `collector.crt`, `collector.key` from `pki/out/snmp-server/` |
| Monicomm / dev-ingest | `ca.crt`, `ingest.crt`, `ingest.key` from `pki/out/ingest/` |

Permissions: `chmod 600 *.key`.
