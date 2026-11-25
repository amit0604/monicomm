// Mock of the configurator API on the SNMP server (docs/plans/syslog-snmp-deployment.md §2.3, §7.2).
// Only the approval UI calls this, with a human approval ID. The assistant has no path to it.
import type { ActionResult, ProposedAction } from '../types';

export interface ApplyRequest {
  action: ProposedAction;
  approvalId: string;
  approvers: string[];
}

function wait(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function apply(req: ApplyRequest, pace = 1): Promise<ActionResult> {
  if (!req.approvalId || req.approvers.length < req.action.approvalsRequired) {
    // The real configurator rejects requests without a valid approval (docs §7.3).
    throw new Error('Rejected: missing approval');
  }
  await wait(900 * pace);
  const { action } = req;
  const checks =
    action.impact.risk === 'high'
      ? [
          { label: `${action.device.name} reachable after change`, ok: false },
          { label: 'Auto-rollback triggered by confirmed commit', ok: true },
        ]
      : [
          { label: `${action.device.name} reachable over management`, ok: true },
          { label: 'No new interface errors in 2 min', ok: true },
          { label: 'No new critical syslog in 2 min', ok: true },
        ];
  return {
    checks,
    output: `[SIMULATION] local mock configurator, no device contacted
configurator: ${action.method} apply ${action.id} on ${action.device.name}
approval ${req.approvalId} by ${req.approvers.join(', ')}
${action.commands.split('\n').map((l) => `> ${l}`).join('\n')}
result: ${checks.every((c) => c.ok) ? 'OK, confirmed after health checks' : 'device unreachable, rolled back automatically'}`,
  };
}

export async function rollback(action: ProposedAction, pace = 1): Promise<string> {
  await wait(700 * pace);
  return `[SIMULATION] local mock configurator, no device contacted\nconfigurator: rollback ${action.id} on ${action.device.name}\n${action.rollback.split('\n').map((l) => `> ${l}`).join('\n')}\nresult: OK`;
}
