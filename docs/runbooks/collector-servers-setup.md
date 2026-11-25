# Runbook: set up the syslog server and SNMP server (vSphere, Ubuntu 24.04, air-gapped)

Design and reasons: `docs/plans/syslog-snmp-deployment.md`. This runbook is the hands-on part.
Once the servers run, `talking-to-collectors.md` covers sending to, querying and watching them.

Addresses used below. All three VMs are on one subnet, `192.168.108.0/24`:

| VM | Role | IP |
|---|---|---|
| `moni-app` | Monicomm (or `dev-ingest` until Monicomm exists) | `192.168.108.140` |
| `moni-syslog` | syslog server | `192.168.108.141` |
| `moni-snmp` | SNMP server | `192.168.108.142` |
| NTP | site time source | `<ntp-ip>` (fill in) |

Because `moni-app` shares the subnet with the collectors (and maybe with devices), the separation from the plan
("Monicomm can't talk to devices") is enforced with host firewall rules on `moni-app` (step 5), not with VLANs.

What runs where:

| VM | Containers | Listens | Sends to |
|---|---|---|---|
| `moni-syslog` | `vector` | UDP/TCP 514 from devices | `moni-app:6000` (mTLS) |
| `moni-snmp` | `trapd`, `poller` (Telegraf), `shipper` (Vector) | UDP 162 from devices | devices UDP 161; `moni-app:6000` (mTLS) |
| `moni-app` | `dev-ingest` now, Monicomm `ingest` later | TCP 6000 from the two collectors | |

---

## 1. Build the bundle (connected build machine)

On a Linux machine with Docker and internet access, in a checkout of this repo:

```bash
./deploy/offline/build-collector-bundle.sh
```

Output: `deploy/offline/dist/monicomm-collectors-<date>.tar` and `.tar.sha256`.

## 2. Make the mTLS certificates

On the build machine or an admin machine with `openssl`:

```bash
./collector/pki/make-certs.sh 192.168.108.140 192.168.108.141 192.168.108.142
```

The first argument must be exactly what the collectors use in `MONICOMM_INGEST_ADDRESS` (an IP here).
Output in `collector/pki/out/`: `ingest/`, `syslog-server/`, `snmp-server/`, and `ca/`.
Keep `ca/ca.key` off the VMs (store it on approved media); it is only needed to issue new certs.

Carry the bundle `.tar`, its `.sha256` and the three cert folders into the closed network on approved media.

## 3. Create the VMs in vSphere

Create `moni-syslog` and `moni-snmp` (and `moni-app` if it doesn't exist yet):

| Setting | `moni-syslog` | `moni-snmp` |
|---|---|---|
| Guest OS | Ubuntu Linux (64-bit) | same |
| vCPU / RAM | 4 / 8 GB | 4 / 8 GB |
| Disk 1 (OS) | 40 GB | 40 GB |
| Disk 2 (data, `/srv/monicomm`) | 500 GB (archive grows ~ syslog volume × 365 days, gzip ≈ 10:1) | 100 GB |
| SCSI controller | VMware Paravirtual | same |
| NIC | VMXNET3 on the `192.168.108.0/24` port group | same |

- `moni-app` uses the same port group. If you later move it to its own VLAN, allow only TCP 6000 (and 8443
  for the configurator) between the VLANs, and give `moni-app` no NIC on the device network.
- Turn on vSphere HA for the cluster (restart on host failure). If you later add a second syslog/SNMP VM, add a VM-VM anti-affinity rule.
- Mount the Ubuntu 24.04 Server ISO from a datastore (approved media).

## 4. Install Ubuntu 24.04 Server

- Minimal install, OpenSSH server on, no extra snaps, no network mirror (the installer will warn there is no internet; continue).
- Static IP. Example `/etc/netplan/50-monicomm.yaml` on `moni-syslog`:

```yaml
network:
  version: 2
  ethernets:
    ens192:
      addresses: [192.168.108.141/24]
      routes: [{to: default, via: <gateway-ip>}]
      nameservers: {addresses: [<dns-ip>]}
```

```bash
sudo chmod 600 /etc/netplan/50-monicomm.yaml && sudo netplan apply
sudo hostnamectl set-hostname moni-syslog
```

## 5. Base OS setup (collector VMs; the firewall part also on `moni-app`)

**Data disk** (check the device name with `lsblk` first; usually `/dev/sdb`):

```bash
sudo mkfs.ext4 -L monidata /dev/sdb
sudo mkdir -p /srv/monicomm
echo 'LABEL=monidata /srv/monicomm ext4 defaults,noatime 0 2' | sudo tee -a /etc/fstab
sudo mount -a && df -h /srv/monicomm
```

**Time** (syslog correlation depends on it). Use the site NTP, not VMware Tools:

```bash
sudo vmware-toolbox-cmd timesync disable
sudo sed -i 's/^#\?NTP=.*/NTP=<ntp-ip>/' /etc/systemd/timesyncd.conf
sudo systemctl restart systemd-timesyncd
timedatectl timesync-status      # "Server: <ntp-ip>", small offset
sudo timedatectl set-timezone Asia/Jerusalem
```

**Firewall** (`ufw` works here because the collectors use host networking).
The rules assume devices send from `192.168.108.0/24`. Add the same rule for every other subnet your devices
send from (for example router loopbacks).

On `moni-syslog`:

```bash
sudo ufw default deny incoming
sudo ufw allow from <admin-subnet> to any port 22 proto tcp
sudo ufw allow from 192.168.108.0/24 to any port 514 proto udp
sudo ufw allow from 192.168.108.0/24 to any port 514 proto tcp
sudo ufw enable
```

On `moni-snmp`:

```bash
sudo ufw default deny incoming
sudo ufw allow from <admin-subnet> to any port 22 proto tcp
sudo ufw allow from 192.168.108.0/24 to any port 162 proto udp
sudo ufw enable
```

On `moni-app` (accept collector data only from the two collectors, and block management protocols
toward devices, so Monicomm and the AI can't reach them even on a shared subnet):

```bash
sudo ufw default deny incoming
sudo ufw allow from <admin-subnet> to any port 22 proto tcp
sudo ufw allow from 192.168.108.141 to any port 6000 proto tcp
sudo ufw allow from 192.168.108.142 to any port 6000 proto tcp
sudo ufw allow from 192.168.108.0/24 to any port 443 proto tcp      # web UI for users, once Monicomm exists
sudo ufw deny out to 192.168.108.0/24 port 161 proto udp           # SNMP
sudo ufw deny out to 192.168.108.0/24 port 22 proto tcp            # SSH
sudo ufw deny out to 192.168.108.0/24 port 23 proto tcp            # Telnet
sudo ufw deny out to 192.168.108.0/24 port 830 proto tcp           # NETCONF
sudo ufw enable
```

Repeat the `deny out` lines for every other subnet that has devices. `moni-app` only needs outbound TCP 8443 to
`192.168.108.142` (configurator, phase F).

(When the configurator arrives in phase F, also allow TCP 8443 on `moni-snmp` from `192.168.108.140` only.)

## 6. Install Docker and the collector (offline)

Copy the bundle to the VM (for example with `scp` from an admin machine inside the closed network), then:

```bash
sha256sum -c monicomm-collectors-<date>.tar.sha256
tar -xf monicomm-collectors-<date>.tar
cd monicomm-collectors-<date>
sudo ./install-collector.sh docker
sudo ./install-collector.sh syslog-server     # on moni-syslog
sudo ./install-collector.sh snmp-server       # on moni-snmp
```

Files land in `/opt/monicomm/collector`, data in `/srv/monicomm`. The script also raises UDP buffers
(`/etc/sysctl.d/90-monicomm-collector.conf`) and installs a daily retention job
(`/etc/cron.daily/monicomm-collector-retention`: raw syslog 365 days, trap files 14 days).

**Certificates:** copy the right folder from step 2 into `/opt/monicomm/collector/certs/`:

```bash
sudo cp syslog-server/* /opt/monicomm/collector/certs/     # on moni-syslog (snmp-server/* on moni-snmp)
sudo chmod 600 /opt/monicomm/collector/certs/*.key
```

## 7. Start the receiver on `moni-app` (until Monicomm exists)

```bash
sudo ./install-collector.sh dev-ingest
sudo cp ingest/* /opt/monicomm/collector/certs/ && sudo chmod 600 /opt/monicomm/collector/certs/*.key
cd /opt/monicomm/collector/dev-ingest && sudo docker compose up -d
```

It writes what it receives to `/opt/monicomm/collector/dev-ingest/data/<date>/{syslog,trap,snmp_metric}.jsonl`.
The `moni-app` firewall rules from step 5 already limit TCP 6000 to the two collectors.

## 8. Configure and start the syslog server (`moni-syslog`)

```bash
cd /opt/monicomm/collector/syslog-server
sudo nano .env          # COLLECTOR_ID, MONICOMM_INGEST_ADDRESS=192.168.108.140:6000, buffer size
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs --tail 50
```

Check it locally:

```bash
logger -n 127.0.0.1 -P 514 -d "moni test from $(hostname)"
ls /srv/monicomm/syslog-archive/$(date -u +%F)/          # 127.0.0.1.log.gz appears within ~1 min
```

On `moni-app`: `grep "moni test" /opt/monicomm/collector/dev-ingest/data/$(date -u +%F)/syslog.jsonl`.

## 9. Configure and start the SNMP server (`moni-snmp`)

```bash
cd /opt/monicomm/collector/snmp-server
sudo nano .env                      # COLLECTOR_ID, MONICOMM_INGEST_ADDRESS
sudo nano secrets/snmp_ro.env       # moni-poll user + passwords (must match the devices)
sudo nano secrets/snmp_trap.env     # moni-trap user + passwords + TRAPD_ENGINE_ID
sudo nano inventory/devices.csv     # name,ip,vendor,role for each device
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs poller --tail 30    # "poller: 10-all.conf: N device(s)"
```

**Engine ID:** `TRAPD_ENGINE_ID` in `secrets/snmp_trap.env` is what every device needs in its inform config
(Cisco `snmp-server engineID remote 192.168.108.142 <id without 0x>`, Junos `usm remote-engine <id without 0x>`).
Choose it once. Changing it later breaks informs from every device.

Check polling against one device before onboarding the rest:

```bash
sudo docker compose logs trapd --tail 5      # "trapd: engine ID 0x..., user moni-trap ..., listening on udp/162"
sudo ./snmpq get <device-ip> .1.3.6.1.2.1.1.5.0   # sysName, using the credentials in secrets/ (no passwords typed)
sudo ./snmpq poll-test                            # one run of every Telegraf poll, printed
```

Check the trap path with a test inform from the VM itself:

```bash
sudo ./snmpq test-inform             # "inform acknowledged by trapd"
ls /srv/monicomm/trapd-out/          # traps-<date>.jsonl
```

All the ways to send to, query and watch both servers: `talking-to-collectors.md`.

## 10. Onboard devices

Use the templates in `docs/plans/syslog-snmp-deployment.md` §5 (Cisco IOS/IOS-XE, IOS-XR, Junos) with:
syslog host `192.168.108.141`, SNMP ACL / inform target `192.168.108.142`, the `moni-poll` and `moni-trap`
passwords from step 9, and the engine ID. One device first, then a pilot group, then the rest. Run the
checklist in §5.4 of the plan for each device, then add it to `inventory/devices.csv` and
`sudo docker compose restart poller`.

---

## Day 2

| Task | How |
|---|---|
| Add / remove devices | Edit `inventory/devices.csv`, then `docker compose restart poller` |
| Upgrade | Snapshot the VM in vSphere, unpack the new bundle, re-run `install-collector.sh <role>` (keeps `.env`, secrets, certs, inventory), `docker compose up -d`. Delete the snapshot after a day. |
| Certificates | Valid 825 days. Re-run `make-certs.sh` with the same CA before expiry and replace the files; `docker compose restart`. |
| Disk | `df -h /srv/monicomm`. Grow the data VMDK in vSphere, then `sudo resize2fs /dev/sdb`. |
| Collector health | Each collector sends its own counters (received/sent/dropped events, buffer size) to ingest as `collector_health`. Locally: `docker compose exec vector vector top` (syslog) or `docker compose exec shipper vector top --url http://127.0.0.1:8687/graphql` (SNMP). |

## Troubleshooting

| Symptom | Check |
|---|---|
| No syslog from a device | `sudo tcpdump -ni ens192 udp port 514 and host <device>` on `moni-syslog`. Nothing → device config, ACLs, routing, `ufw status`. Packets but no archive → `docker compose logs vector`. |
| Syslog arrives under the wrong IP | The device sends from another interface: set the source interface (`logging source-interface`, Junos `source-address`). |
| Informs not acknowledged | Engine ID on the device ≠ `TRAPD_ENGINE_ID`, or user/passwords/protocols differ. `docker compose logs trapd` shows auth errors. `tcpdump -ni ens192 udp port 162`. |
| Plain v3 traps dropped (not informs) | Add each device's engine ID to `TRAP_DEVICE_ENGINE_IDS` (`show snmp engineID` / `show snmp v3`), restart trapd. |
| Poller errors "unknown user name" / "wrong digest" | `secrets/snmp_ro.env` doesn't match the device's `moni-poll` user, or the device ACL doesn't allow `192.168.108.142`. |
| Poller errors on one table | That device doesn't support that MIB (normal for some platforms); other tables still work. |
| Nothing reaches `moni-app` | `docker compose logs` shows TLS errors → wrong certs or `MONICOMM_INGEST_ADDRESS` doesn't match the ingest cert's IP. Connection refused → firewall / dev-ingest not running. Data waits in the disk buffer meanwhile. |
| `image ... not found after load` during install | The VM's Docker didn't keep image digests on `docker load`. Use Docker Engine from the bundle (containerd image store), or ask the platform owner. |
