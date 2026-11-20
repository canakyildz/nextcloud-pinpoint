<template>
	<NcContent app-name="pinpoint">
		<NcAppNavigation :aria-label="t('pinpoint', 'Extractions')">
			<NcAppNavigationNew :text="t('pinpoint', 'New extraction')" @click="router.push({ name: 'new' })">
				<template #icon>
					<NcIconSvgWrapper :path="mdiPlus" />
				</template>
			</NcAppNavigationNew>
			<template #list>
				<NcAppNavigationCaption :name="t('pinpoint', 'Recent documents')" />
				<NcAppNavigationItem
					v-for="job in store.jobs"
					:key="job.id"
					:name="job.fileName"
					:to="{ name: 'job', params: { id: job.id } }">
					<template #icon>
						<NcLoadingIcon v-if="job.status === 'queued' || job.status === 'running'" :size="20" />
						<NcIconSvgWrapper v-else :path="jobIcon(job)" :class="`job-icon job-icon--${job.status}`" />
					</template>
					<template #counter>
						<span class="job-subtitle">{{ jobSubtitle(job) }}</span>
					</template>
				</NcAppNavigationItem>
				<li v-if="store.jobs.length === 0" class="empty-nav">
					{{ t('pinpoint', 'Documents you extract appear here.') }}
				</li>
			</template>
		</NcAppNavigation>
		<NcAppContent>
			<NcNoteCard v-if="store.loadError" type="error" class="page-note">
				{{ store.loadError }}
			</NcNoteCard>
			<RouterView />
		</NcAppContent>
	</NcContent>
</template>

<script setup lang="ts">
import { mdiAlertCircleOutline, mdiCheckAll, mdiFileDocumentCheckOutline, mdiPlus } from '@mdi/js'
import { t } from '@nextcloud/l10n'
import NcAppContent from '@nextcloud/vue/components/NcAppContent'
import NcAppNavigation from '@nextcloud/vue/components/NcAppNavigation'
import NcAppNavigationCaption from '@nextcloud/vue/components/NcAppNavigationCaption'
import NcAppNavigationItem from '@nextcloud/vue/components/NcAppNavigationItem'
import NcAppNavigationNew from '@nextcloud/vue/components/NcAppNavigationNew'
import NcContent from '@nextcloud/vue/components/NcContent'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage, type Job } from './api.ts'
import { JOB_STATUS } from './status.ts'
import { refreshJobs, refreshState, store } from './store.ts'

const router = useRouter()

function jobIcon(job: Job): string {
	if (job.status === 'failed') return mdiAlertCircleOutline
	if (job.status === 'saved') return mdiCheckAll
	return mdiFileDocumentCheckOutline
}

function jobSubtitle(job: Job): string {
	if (job.status === 'done' && job.summary) {
		const toCheck = job.summary.review + job.summary.unverified
		return toCheck ? t('pinpoint', '{n} to check', { n: toCheck }) : t('pinpoint', 'all verified')
	}
	return JOB_STATUS[job.status]
}

// Keep the navigation current while documents are being read.
let poller: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
	try {
		await Promise.all([refreshJobs(), refreshState()])
	} catch (error) {
		store.loadError = t('pinpoint', 'Pinpoint could not load: {error}', { error: errorMessage(error) })
	}
	poller = setInterval(() => {
		if (store.jobs.some((job) => job.status === 'queued' || job.status === 'running')) {
			refreshJobs().catch(() => undefined)
		}
	}, 4000)
})

onBeforeUnmount(() => clearInterval(poller))
</script>

<style scoped>
.job-subtitle {
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
	white-space: nowrap;
}

.job-icon--failed {
	color: var(--color-error-text);
}

.job-icon--saved {
	color: var(--color-success-text);
}

.empty-nav {
	padding: 8px 16px;
	color: var(--color-text-maxcontrast);
}

.page-note {
	margin: 16px;
}
</style>
