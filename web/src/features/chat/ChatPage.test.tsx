import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { I18nProvider } from '../../i18n';
import { createMockBackend } from './backend';
import { ChatPage } from './ChatPage';

function setup() {
  const backend = createMockBackend(0);
  const applySpy = vi.spyOn(backend, 'applyApproved');
  render(
    <I18nProvider>
      <ChatPage backend={backend} />
    </I18nProvider>,
  );
  return { applySpy, user: userEvent.setup() };
}

async function ask(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText('Message ChatIAF'), `${text}{Enter}`);
  return screen.findByRole('article', {}, { timeout: 3000 });
}

async function reply(user: ReturnType<typeof userEvent.setup>, text: string) {
  const before = document.querySelectorAll('.msg--assistant').length;
  await user.type(screen.getByLabelText('Message ChatIAF'), `${text}{Enter}`);
  await waitFor(() => {
    const all = document.querySelectorAll('.msg--assistant');
    expect(all.length).toBe(before + 1);
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument();
  });
  const all = document.querySelectorAll<HTMLElement>('.msg--assistant');
  return all[all.length - 1];
}

describe('ChatIAF transparency', () => {
  it('shows prototype, mock data, simulated AI and read-only labels, and no "Local model" claim', () => {
    setup();
    const badges = screen.getByRole('list', { name: 'Prototype status' });
    for (const label of ['Prototype mode', 'Mock data', 'Simulated AI', 'Read-only']) {
      expect(within(badges).getByText(label)).toBeInTheDocument();
    }
    expect(screen.queryByText(/Local model/)).not.toBeInTheDocument();
    expect(screen.getByText(/no AI model or real network connected/)).toBeInTheDocument();
  });

  it('says how each answer was made', async () => {
    const { user } = setup();
    const msg = await reply(user, 'What is DNS?');
    expect(within(msg).getByText(/local knowledge base · intent TECHNICAL_KNOWLEDGE/)).toBeInTheDocument();
  });

  it('opened sources show their content, and network sources are marked as mock', async () => {
    const { user } = setup();
    const card = await ask(user, 'Why is Gi1/0/5 on access-sw-12 down?');
    const msg = card.closest('.msg') as HTMLElement;
    await user.click(within(msg).getByText(/^Sources/));
    const sources = msg.querySelector<HTMLElement>('.sources')!;
    expect(sources).toHaveAttribute('open');
    expect(within(sources).getByText(/Mock data: these sources point/)).toBeVisible();
    expect(within(sources).getAllByText('mock').length).toBeGreaterThan(0);
    // The full log line, not a truncated one.
    expect(within(sources).getByText(/BPDU Guard enabled\. Disabling port\./)).toBeVisible();
  });

  it('approved changes are labeled as a simulation', async () => {
    const { user } = setup();
    const card = await ask(user, 'Why is Gi1/0/5 on access-sw-12 down?');
    expect(within(card).getByText(/No real device is contacted/)).toBeInTheDocument();
    await user.click(within(card).getByRole('button', { name: 'Approve and apply' }));
    await waitFor(() => expect(screen.getByText(/Simulated: ACT-\d+ applied/)).toBeInTheDocument(), { timeout: 3000 });
  });
});

describe('ChatIAF conversation context', () => {
  it('follow-ups use the previous topic, and New chat clears it', async () => {
    const { user } = setup();
    await reply(user, 'What is DNS?');
    const more = await reply(user, 'Can you explain it in more detail?');
    expect(within(more).getByText(/intent FOLLOW_UP/)).toBeInTheDocument();
    expect(more).toHaveTextContent(/nslookup/);

    await user.click(screen.getByRole('button', { name: 'New chat' }));
    const fresh = await reply(user, 'Can you explain it in more detail?');
    expect(fresh).toHaveTextContent(/no earlier topic in this chat/);
  });
});

describe('ChatIAF approval flow', () => {
  it('does not apply anything until the technician approves', async () => {
    const { applySpy, user } = setup();
    const card = await ask(user, 'Why is Gi1/0/5 on access-sw-12 down?');

    expect(within(card).getByText('Awaiting approval')).toBeInTheDocument();
    expect(applySpy).not.toHaveBeenCalled();

    await user.click(within(card).getByRole('button', { name: 'Approve and apply' }));
    await waitFor(() => expect(within(card).getByText('Applied')).toBeInTheDocument(), { timeout: 3000 });
    expect(applySpy).toHaveBeenCalledTimes(1);
    expect(applySpy.mock.calls[0][2]).toEqual(['technician']);
  });

  it('cancel sends nothing to the device', async () => {
    const { applySpy, user } = setup();
    const card = await ask(user, 'Why is Gi1/0/5 on access-sw-12 down?');
    await user.click(within(card).getByRole('button', { name: 'Cancel' }));
    expect(within(card).getByText('Cancelled')).toBeInTheDocument();
    expect(applySpy).not.toHaveBeenCalled();
  });

  it('high-risk changes need an explicit acknowledgement', async () => {
    const { user } = setup();
    const card = await ask(user, 'Shut down Gi1/0/48 on access-sw-12');
    const approve = within(card).getByRole('button', { name: 'Approve and apply' });
    expect(approve).toBeDisabled();
    await user.click(within(card).getByLabelText('I understand the impact above'));
    expect(approve).toBeEnabled();
  });

  it('router changes wait for a second approver', async () => {
    const { applySpy, user } = setup();
    const card = await ask(user, 'WAN to Site-North is slow. What can we do?');
    await user.click(within(card).getByRole('button', { name: 'Approve and apply' }));
    expect(within(card).getByText('Awaiting 2nd approval')).toBeInTheDocument();
    expect(applySpy).not.toHaveBeenCalled();

    await user.click(within(card).getByRole('button', { name: 'Approve as second technician (demo)' }));
    await waitFor(() => expect(applySpy).toHaveBeenCalledTimes(1));
    expect(applySpy.mock.calls[0][2]).toEqual(['technician', 'technician-2']);
  });
});
