import { CheckCircle2, LoaderCircle, ShieldAlert, ShieldCheck, Undo2, XCircle } from 'lucide-react';
import { useState } from 'react';
import { Button, StatusPill, Tag } from '../../../components/ui';
import type { Status } from '../../../components/ui';
import { useI18n } from '../../../i18n';
import type { ActionStatus, ProposedAction, Risk } from '../types';
import { CodeBlock } from './CodeBlock';

const RISK_STATUS: Record<Risk, Status> = { low: 'ok', medium: 'warning', high: 'critical' };

const STATUS_PILL: Record<ActionStatus, Status> = {
  pending: 'accent',
  awaiting_second: 'accent',
  applying: 'info',
  verifying: 'info',
  applied: 'ok',
  cancelled: 'neutral',
  failed: 'critical',
  rolled_back: 'neutral',
};

const METHOD_LABEL = { 'snmp-set': 'SNMP SET', netconf: 'NETCONF', cli: 'SSH / CLI' } as const;

/**
 * The approval gate. The AI only ever creates this card in the 'pending' state;
 * the buttons here are the only way a change reaches the configurator.
 */
export function ActionCard({
  action,
  onApprove,
  onCancel,
  onRollback,
}: {
  action: ProposedAction;
  onApprove: () => void;
  onCancel: () => void;
  onRollback: () => void;
}) {
  const { t } = useI18n();
  const [acknowledged, setAcknowledged] = useState(false);
  const { impact } = action;
  const highRisk = impact.risk === 'high';
  const open = action.status === 'pending' || action.status === 'awaiting_second';
  const busy = action.status === 'applying' || action.status === 'verifying';

  return (
    <article className={`action-card action-card--${impact.risk}`} aria-label={action.title}>
      <header className="action-card__header">
        <div className="action-card__eyebrow">
          {highRisk ? <ShieldAlert size={16} aria-hidden="true" /> : <ShieldCheck size={16} aria-hidden="true" />}
          <span>{t('action.header')}</span>
          <Tag>{t('chat.aiTag')}</Tag>
        </div>
        <StatusPill status={STATUS_PILL[action.status]} label={t(`action.status.${action.status}`)} />
      </header>

      <h3 className="action-card__title">{action.title}</h3>

      <dl className="action-card__facts">
        <div>
          <dt>{t('action.device')}</dt>
          <dd className="mono">
            {action.device.name} · {action.device.role}
          </dd>
        </div>
        <div>
          <dt>{t('action.method')}</dt>
          <dd>{METHOD_LABEL[action.method]}</dd>
        </div>
        <div>
          <dt>ID</dt>
          <dd className="mono">{action.id}</dd>
        </div>
      </dl>

      <CodeBlock title={t('action.commands')} language={action.method === 'netconf' ? 'diff' : 'cli'} content={action.commands} />

      <section className="impact" aria-label={t('action.impact')}>
        <div className="impact__head">
          <h4>{t('action.impact')}</h4>
          <StatusPill status={RISK_STATUS[impact.risk]} label={t(`risk.${impact.risk}`)} />
        </div>
        <p className="impact__summary">{impact.summary}</p>
        {impact.affected.length > 0 && (
          <ul className="impact__affected">
            {impact.affected.map((a) => (
              <li key={a.label}>
                <StatusPill status={a.status} label={a.label} />
                <span>{a.detail}</span>
              </li>
            ))}
          </ul>
        )}
        {impact.warnings.length > 0 && (
          <ul className={highRisk ? 'impact__warnings impact__warnings--high' : 'impact__warnings'}>
            {impact.warnings.map((w) => (
              <li key={w}>
                <ShieldAlert size={16} aria-hidden="true" />
                <span>{w}</span>
              </li>
            ))}
          </ul>
        )}
        <p className="impact__safety">
          <strong>{t('action.safetyNet')}:</strong> {impact.safetyNet}
        </p>
        <details className="impact__rollback">
          <summary>{t('action.rollback')}</summary>
          <CodeBlock language="cli" content={action.rollback} />
        </details>
      </section>

      <footer className="action-card__footer">
        <p className="action-card__note">
          {open && (
            <>
              {t('action.aiCannotApply')}
              <br />
              <strong>{t('action.simulation')}</strong>
            </>
          )}
          {action.status === 'applying' && t('action.applyingDetail', { approvalId: action.approvalId ?? '' })}
          {action.status === 'verifying' && t('action.verifyingDetail')}
          {action.status === 'cancelled' && t('action.cancelledDetail')}
          {action.status === 'awaiting_second' && (
            <>
              <br />
              {t('action.secondApprover')}
            </>
          )}
        </p>

        {action.result && action.result.checks.length > 0 && (
          <ul className="action-card__checks">
            {action.result.checks.map((c) => (
              <li key={c.label}>
                {c.ok ? <CheckCircle2 size={14} aria-hidden="true" className="ok" /> : <XCircle size={14} aria-hidden="true" className="bad" />}
                <span>{c.label}</span>
              </li>
            ))}
          </ul>
        )}

        <div className="action-card__row">
          <span className="action-card__approvals num">
            {t('action.approvals', { done: action.approvals.length, required: action.approvalsRequired })}
          </span>

          {action.status === 'pending' && highRisk && (
            <label className="action-card__ack">
              <input type="checkbox" checked={acknowledged} onChange={(e) => setAcknowledged(e.target.checked)} />
              {t('action.acknowledge')}
            </label>
          )}

          <div className="action-card__buttons">
            {action.status === 'pending' && (
              <>
                <Button variant="secondary" onClick={onCancel}>
                  {t('action.cancel')}
                </Button>
                <Button variant={highRisk ? 'danger' : 'primary'} onClick={onApprove} disabled={highRisk && !acknowledged}>
                  {t('action.approve')}
                </Button>
              </>
            )}
            {action.status === 'awaiting_second' && (
              <>
                <Button variant="secondary" onClick={onCancel}>
                  {t('action.cancel')}
                </Button>
                <Button variant="primary" onClick={onApprove}>
                  {t('action.secondApproveDemo')}
                </Button>
              </>
            )}
            {busy && (
              <span className="action-card__busy">
                <LoaderCircle size={16} className="spin" aria-hidden="true" />
                {t(`action.status.${action.status}`)}
              </span>
            )}
            {action.status === 'applied' && (
              <Button variant="secondary" onClick={onRollback}>
                <Undo2 size={16} aria-hidden="true" className="flip-rtl" />
                {t('action.rollbackNow')}
              </Button>
            )}
          </div>
        </div>
      </footer>
    </article>
  );
}
