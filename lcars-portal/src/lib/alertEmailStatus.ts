/**
 * Email status for an alert, so the workbench can answer "did anyone get told?"
 *
 * Mirrors intelligence/emergency_alerts.py: an email is sent for Emergency
 * Warnings and for BOM warnings the platform labels "High attention", once per
 * alert (alerts.emergency_email_sent_at). A matching silence skips the send
 * WITHOUT setting that column, so a silenced alert reads "muted", not "sent".
 * Watch and Act and lower tiers are never emailed.
 */

import { bomAttentionLevel } from '@/lib/bomAttention';

export type EmailState = 'sent' | 'muted' | 'pending' | 'not_emailed';

export interface EmailStatus {
  state: EmailState;
  label: string;
  detail: string;
}

interface EmailStatusAlert {
  sourceKey: string;
  severity: string;
  headline: string;
  alertType: string;
  emailSentAt: string | null;
}

export function isEmailEligible(alert: Pick<EmailStatusAlert, 'sourceKey' | 'severity' | 'headline' | 'alertType'>): boolean {
  if (alert.severity === 'emergency_warning') return true;
  return alert.severity === 'unknown' && alert.sourceKey.startsWith('bom_') && bomAttentionLevel(alert.headline, alert.alertType) === 'high';
}

export function alertEmailStatus(alert: EmailStatusAlert, isMuted: boolean, ago: (iso: string) => string): EmailStatus {
  if (alert.emailSentAt) {
    return { state: 'sent', label: `Emailed ${ago(alert.emailSentAt)}`, detail: 'The emergency email for this alert has been sent.' };
  }
  if (!isEmailEligible(alert)) {
    return { state: 'not_emailed', label: 'No email for this level', detail: 'Only Emergency Warnings and high-attention BOM warnings are emailed.' };
  }
  if (isMuted) {
    return { state: 'muted', label: 'Email muted by a silence', detail: 'An active silence is holding the email. It sends if the silence ends while the alert is still active.' };
  }
  return { state: 'pending', label: 'Email not sent yet', detail: 'This alert qualifies for an email and none has gone out. It is picked up on the next 15-minute run; if it stays like this, check the Coverage panel.' };
}
