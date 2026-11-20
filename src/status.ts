import { mdiAlertCircleOutline, mdiCheckCircleOutline, mdiCloseCircleOutline, mdiMinusCircleOutline } from '@mdi/js'
import { t } from '@nextcloud/l10n'
import type { FieldStatus, Job, JobStatus } from './api.ts'

/** Colour family used for a status dot or badge (see theme.css). */
export type Tone = 'green' | 'amber' | 'red' | 'blue' | 'gray'

export const FIELD_STATUS: Record<FieldStatus, { label: string, hint: string, icon: string, tone: Tone }> = {
	verified: {
		label: t('pinpoint', 'Verified'),
		hint: t('pinpoint', 'The document says exactly this, at the highlighted spot.'),
		icon: mdiCheckCircleOutline,
		tone: 'green',
	},
	review: {
		label: t('pinpoint', 'Check'),
		hint: t('pinpoint', 'Found in the document, but something needs a look.'),
		icon: mdiAlertCircleOutline,
		tone: 'amber',
	},
	unverified: {
		label: t('pinpoint', 'Not found'),
		hint: t('pinpoint', 'The model gave this value, but it could not be found in the document. Treat it as a guess.'),
		icon: mdiCloseCircleOutline,
		tone: 'red',
	},
	missing: {
		label: t('pinpoint', 'Empty'),
		hint: t('pinpoint', 'The model found no value for this field.'),
		icon: mdiMinusCircleOutline,
		tone: 'gray',
	},
}

export const JOB_STATUS: Record<JobStatus, string> = {
	queued: t('pinpoint', 'Waiting'),
	running: t('pinpoint', 'Reading'),
	done: t('pinpoint', 'Ready for review'),
	failed: t('pinpoint', 'Failed'),
	saved: t('pinpoint', 'Saved'),
}

export function isPending(job: Job): boolean {
	return job.status === 'queued' || job.status === 'running'
}

export function toCheckCount(job: Job): number {
	const summary = job.summary ?? job.result?.summary
	return summary ? summary.review + summary.unverified : 0
}

export function jobTone(job: Job): Tone {
	if (job.status === 'failed') return 'red'
	if (isPending(job)) return 'amber'
	if (job.status === 'saved') return 'blue'
	return toCheckCount(job) > 0 ? 'amber' : 'green'
}

/** Short status line for a job: "3 to check", "All verified", "Saved"… */
export function jobLabel(job: Job): string {
	if (job.status === 'done') {
		const n = toCheckCount(job)
		return n ? t('pinpoint', '{n} to check', { n }) : t('pinpoint', 'All verified')
	}
	return JOB_STATUS[job.status]
}

/** "just now", "5m", "3h", "2d": compact relative time for lists. */
export function ago(seconds: number): string {
	const diff = Math.max(0, Date.now() / 1000 - seconds)
	if (diff < 60) return t('pinpoint', 'now')
	if (diff < 3600) return t('pinpoint', '{n}m', { n: Math.floor(diff / 60) })
	if (diff < 86400) return t('pinpoint', '{n}h', { n: Math.floor(diff / 3600) })
	return t('pinpoint', '{n}d', { n: Math.floor(diff / 86400) })
}
