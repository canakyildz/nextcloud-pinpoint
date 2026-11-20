<template>
	<NcContent app-name="pinpoint" class="pp">
		<NcAppNavigation :aria-label="t('pinpoint', 'Extractions')">
			<NcAppNavigationNew :text="t('pinpoint', 'New extraction')" @click="router.push({ name: 'new' })">
				<template #icon>
					<NcIconSvgWrapper :path="mdiPlus" />
				</template>
			</NcAppNavigationNew>
			<template #list>
				<NcAppNavigationCaption :name="t('pinpoint', 'Documents')" />
				<NcAppNavigationItem
					v-for="job in store.jobs"
					:key="job.id"
					class="nav-job"
					:name="job.fileName"
					:title="`${job.fileName} · ${jobLabel(job)}`"
					:to="{ name: 'job', params: { id: job.id } }">
					<template #icon>
						<span class="pp-dot" :class="[`pp-dot--${jobTone(job)}`, { 'pp-dot--pulse': isPending(job) }]" />
					</template>
					<template #counter>
						<span class="nav-job__meta pp-mono" :class="`nav-job__meta--${jobTone(job)}`">{{ jobLabel(job) }}</span>
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
import { mdiPlus } from '@mdi/js'
import { t } from '@nextcloud/l10n'
import NcAppContent from '@nextcloud/vue/components/NcAppContent'
import NcAppNavigation from '@nextcloud/vue/components/NcAppNavigation'
import NcAppNavigationCaption from '@nextcloud/vue/components/NcAppNavigationCaption'
import NcAppNavigationItem from '@nextcloud/vue/components/NcAppNavigationItem'
import NcAppNavigationNew from '@nextcloud/vue/components/NcAppNavigationNew'
import NcContent from '@nextcloud/vue/components/NcContent'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import { onBeforeUnmount, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { errorMessage } from './api.ts'
import { isPending, jobLabel, jobTone } from './status.ts'
import { refreshJobs, refreshState, store } from './store.ts'

const router = useRouter()

// Keep the navigation current while documents are being read.
let poller: ReturnType<typeof setInterval> | undefined

onMounted(async () => {
	try {
		await Promise.all([refreshJobs(), refreshState()])
	} catch (error) {
		store.loadError = t('pinpoint', 'Pinpoint could not load: {error}', { error: errorMessage(error) })
	}
	poller = setInterval(() => {
		if (store.jobs.some(isPending)) {
			refreshJobs().catch(() => undefined)
		}
	}, 4000)
})

onBeforeUnmount(() => clearInterval(poller))
</script>

<style scoped>
.nav-job :deep(.app-navigation-entry-icon) {
	justify-content: center;
}

.nav-job__meta {
	color: var(--pp-faint);
	font-size: 11.5px;
	white-space: nowrap;
}

.nav-job__meta--amber {
	color: var(--pp-amber-text);
}

.nav-job__meta--red {
	color: var(--pp-red-text);
}

.empty-nav {
	padding: 8px 16px;
	color: var(--pp-muted);
	font-size: 13px;
}

.page-note {
	margin: 16px;
}
</style>
