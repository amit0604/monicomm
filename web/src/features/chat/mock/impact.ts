// Mock IMPACT analyzer: predicts what a change will break before anyone approves it.
// Another teammate owns the real one; this keeps the same output shape (types.Impact).
import { approvalsRequiredFor } from '../policy';
import type { Impact, ProposedAction } from '../types';
import { getDevice } from './tools';
import type { Interface } from './network';

export type Operation =
  | { kind: 'shutdown' }
  | { kind: 'bounce' }
  | { kind: 'ospf_cost'; cost: number };

let counter = 0;

export function draftAction(iface: Interface, op: Operation): ProposedAction {
  const device = getDevice(iface.device);
  if (!device) throw new Error(`Unknown device ${iface.device}`);

  const approvalsRequired = approvalsRequiredFor(device.role);
  // Docs §7.1: SNMP SET only for quick Cisco switch-port operations; NETCONF for everything else.
  const isCiscoSwitch = device.vendor === 'Cisco' && device.role.endsWith('switch');
  const method = isCiscoSwitch && op.kind !== 'ospf_cost' ? 'snmp-set' : 'netconf';

  counter += 1;
  return {
    id: `ACT-${String(counter).padStart(4, '0')}`,
    title: titleFor(iface, op),
    device: { name: device.name, role: device.role },
    method,
    commands: commandsFor(iface, op, device.vendor),
    rollback: rollbackFor(iface, op, device.vendor),
    impact: analyzeImpact(iface, op),
    approvalsRequired,
    approvals: [],
    status: 'pending',
  };
}

export function analyzeImpact(iface: Interface, op: Operation): Impact {
  const affected: Impact['affected'] = [];
  const warnings: string[] = [];
  let risk: Impact['risk'];
  let summary: string;

  if (op.kind === 'shutdown') {
    if (iface.activeHosts > 0) {
      affected.push({
        label: `${iface.activeHosts} active host${iface.activeHosts === 1 ? '' : 's'}`,
        detail: `lose connectivity behind ${iface.device} ${iface.name}`,
        status: 'critical',
      });
    }
    if (iface.mode === 'trunk') {
      affected.push({ label: `VLANs ${iface.vlan}`, detail: 'stop forwarding on this trunk', status: 'warning' });
    }
    if (iface.neighbor) {
      affected.push({ label: iface.neighbor, detail: 'neighbor link goes down', status: 'warning' });
    }
    if (iface.carriesMgmt) {
      warnings.push(
        `This link carries the management path to ${iface.device}. After the change the configurator can't reach the device; the confirmed commit rolls it back in 5 minutes unless someone confirms from the console.`,
      );
    }
    if (iface.mode === 'trunk' || iface.activeHosts > 10) {
      warnings.push(`${iface.name} is an uplink, not an edge port. Shutting it isolates the whole switch.`);
      risk = 'high';
    } else {
      risk = iface.activeHosts > 0 ? 'medium' : 'low';
    }
    summary =
      risk === 'high'
        ? `Shutting ${iface.name} cuts ${iface.device} off the network.`
        : `Shutting ${iface.name} affects only this edge port.`;
  } else if (op.kind === 'bounce') {
    affected.push({ label: 'PC-LAB-05 · 10.1.4.22', detail: 'reconnects after ~30 s (STP listening/learning)', status: 'info' });
    warnings.push('If the unmanaged switch is still plugged in, BPDU Guard will err-disable the port again.');
    summary = `Recovers ${iface.name} from err-disabled. Only the one desk port is touched.`;
    risk = 'low';
  } else {
    affected.push({
      label: 'WAN traffic to Site-North',
      detail: `moves from ${iface.name} (92% used, CRC errors) to xe-0/1/1 (8% used)`,
      status: 'info',
    });
    affected.push({ label: 'OSPF adjacency 10.255.0.2', detail: 'stays up; only the path cost changes', status: 'ok' });
    warnings.push('Backup link xe-0/1/1 will carry ~9.2 Gb/s at peak. It is 10G, so headroom is about 8%.');
    warnings.push('Routes reconverge once (~1 s). Long-lived TCP sessions may see a short retransmit burst.');
    summary = `Steers WAN traffic off the failing link until the optic on ${iface.name} is replaced.`;
    risk = 'medium';
  }

  return {
    risk,
    summary,
    affected,
    warnings,
    safetyNet:
      op.kind === 'ospf_cost'
        ? 'NETCONF commit confirmed 5: Junos rolls back by itself unless the configurator confirms after health checks.'
        : 'Previous value is stored; health checks run for 2 minutes after apply, and one click restores it.',
  };
}

function titleFor(iface: Interface, op: Operation): string {
  switch (op.kind) {
    case 'shutdown':
      return `Shut down ${iface.name} on ${iface.device}`;
    case 'bounce':
      return `Recover ${iface.name} on ${iface.device} (shutdown / no shutdown)`;
    case 'ospf_cost':
      return `Raise OSPF cost on ${iface.device} ${iface.name} to ${op.cost}`;
  }
}

function commandsFor(iface: Interface, op: Operation, vendor: string): string {
  if (op.kind === 'ospf_cost') {
    return `[edit protocols ospf area 0.0.0.0]
- interface ${iface.name}.0 { metric 10; }
+ interface ${iface.name}.0 { metric ${op.cost}; }

commit confirmed 5 comment "ChatIAF ${iface.name} cost ${op.cost}"`;
  }
  if (vendor === 'Cisco') {
    // SNMP SET preview shows the exact OIDs and values (docs §7.2), with the CLI meaning beside it.
    const oid = `IF-MIB::ifAdminStatus.${ciscoIfIndex(iface.name)}`;
    const lines = [`SET ${oid} = down(2)    ! interface ${iface.name} / shutdown`];
    if (op.kind === 'bounce') lines.push(`SET ${oid} = up(1)      ! no shutdown`);
    return lines.join('\n');
  }
  return `set interfaces ${iface.name} disable`;
}

/** Catalyst numbers Gi1/0/N as ifIndex 10100+N; good enough for the mock preview. */
function ciscoIfIndex(name: string): number {
  const port = Number(name.split('/').pop());
  return 10100 + (Number.isFinite(port) ? port : 0);
}

function rollbackFor(iface: Interface, op: Operation, vendor: string): string {
  if (op.kind === 'ospf_cost') return 'rollback 1\ncommit';
  const oid = `IF-MIB::ifAdminStatus.${ciscoIfIndex(iface.name)}`;
  if (op.kind === 'bounce') return `SET ${oid} = down(2)    ! back to the stored previous state`;
  return vendor === 'Cisco' ? `SET ${oid} = up(1)      ! stored previous value` : `delete interfaces ${iface.name} disable`;
}
