import { mdiAlertCircleOutline, mdiCheckCircleOutline, mdiCloseCircleOutline, mdiMinusCircleOutline } from '@mdi/js'
import { t } from '@nextcloud/l10n'
import type { FieldStatus, JobStatus } from './api.ts'

export const FIELD_STATUS: Record<FieldStatus, { label: string, hint: string, icon: string }> = {
	verified: {
		label: t('pinpoint', 'Verified'),
		hint: t('pinpoint', 'The document says exactly this, at the highlighted spot.'),
		icon: mdiCheckCircleOutline,
	},
	review: {
		label: t('pinpoint', 'Check'),
		hint: t('pinpoint', 'Found in the document, but something needs a look.'),
		icon: mdiAlertCircleOutline,
	},
	unverified: {
		label: t('pinpoint', 'Not found'),
		hint: t('pinpoint', 'The model gave this value, but it could not be found in the document. Treat it as a guess.'),
		icon: mdiCloseCircleOutline,
	},
	missing: {
		label: t('pinpoint', 'Empty'),
		hint: t('pinpoint', 'The model found no value for this field.'),
		icon: mdiMinusCircleOutline,
	},
}

export const JOB_STATUS: Record<JobStatus, string> = {
	queued: t('pinpoint', 'Waiting'),
	running: t('pinpoint', 'Reading'),
	done: t('pinpoint', 'Ready for review'),
	failed: t('pinpoint', 'Failed'),
	saved: t('pinpoint', 'Saved'),
}
