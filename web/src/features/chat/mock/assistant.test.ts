import { describe, expect, it } from 'vitest';
import type { AssistantEvent } from '../types';
import { respond } from './assistant';
import assistantSource from './assistant.ts?raw';

async function collect(question: string) {
  const events: AssistantEvent[] = [];
  for await (const e of respond(question, { pace: 0 })) events.push(e);
  return events;
}

const text = (events: AssistantEvent[]) =>
  events
    .filter((e): e is Extract<AssistantEvent, { type: 'text_delta' }> => e.type === 'text_delta')
    .map((e) => e.text)
    .join('');

describe('mock assistant', () => {
  it('never imports the configurator (AI is read-only)', () => {
    expect(assistantSource).not.toMatch(/from ['"].*configurator['"]/);
  });

  it('explains a down port with tools, sources and a pending proposal', async () => {
    const events = await collect('Why is Gi1/0/5 on access-sw-12 down?');
    const tools = events.filter((e) => e.type === 'tool_start').map((e) => (e as { tool: string }).tool);
    expect(tools).toEqual(['get_interface', 'query_logs']);
    expect(text(events)).toMatch(/BPDU Guard/);

    const proposal = events.find((e) => e.type === 'proposal');
    expect(proposal?.type === 'proposal' && proposal.action.status).toBe('pending');
    expect(proposal?.type === 'proposal' && proposal.action.approvals).toEqual([]);

    const sources = events.find((e) => e.type === 'sources');
    expect(sources?.type === 'sources' && sources.sources.length).toBeGreaterThan(0);
  });

  it('flags shutting an uplink as high risk', async () => {
    const events = await collect('Shut down Gi1/0/48 on access-sw-12');
    const proposal = events.find((e) => e.type === 'proposal');
    if (proposal?.type !== 'proposal') throw new Error('no proposal');
    expect(proposal.action.impact.risk).toBe('high');
    expect(proposal.action.impact.warnings.join(' ')).toMatch(/management path/);
  });

  it('requires two approvers for a router change', async () => {
    const events = await collect('WAN to Site-North is slow. What can we do?');
    const proposal = events.find((e) => e.type === 'proposal');
    if (proposal?.type !== 'proposal') throw new Error('no proposal');
    expect(proposal.action.device.role).toBe('router');
    expect(proposal.action.approvalsRequired).toBe(2);
    expect(proposal.action.method).toBe('netconf');
  });

  it('answers read-only questions without proposing changes', async () => {
    for (const q of ['Show active alerts', 'What changed on core-sw-01 since yesterday?', 'Which switch is host 10.1.4.22 on?']) {
      const events = await collect(q);
      expect(events.some((e) => e.type === 'proposal')).toBe(false);
      expect(events.some((e) => e.type === 'table')).toBe(true);
    }
  });

  it('stops when aborted', async () => {
    const controller = new AbortController();
    controller.abort();
    await expect(async () => {
      for await (const e of respond('Show active alerts', { pace: 0, signal: controller.signal })) void e;
    }).rejects.toThrow(/Aborted/);
  });
});
