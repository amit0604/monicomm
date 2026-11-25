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
