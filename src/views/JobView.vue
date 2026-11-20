<template>
	<div class="job">
		<NcEmptyContent v-if="loadError" :name="t('pinpoint', 'Not found')" :description="loadError">
			<template #icon>
				<NcIconSvgWrapper :path="mdiFileQuestionOutline" />
			</template>
		</NcEmptyContent>

		<template v-else-if="job">
			<header class="job__header">
				<div class="job__title">
					<h2>{{ job.fileName }}</h2>
					<p class="job__meta">
						<a :href="fileUrl" target="_blank" rel="noopener">{{ t('pinpoint', 'Open in Files') }}</a>
						· {{ t('pinpoint', 'Table: {name}', { name: job.schemaName }) }}
						<template v-if="extraction">
							· {{ summaryText }}
						</template>
					</p>
				</div>
				<NcButton variant="tertiary" :aria-label="t('pinpoint', 'Delete this extraction')" @click="remove">
					<template #icon>
						<NcIconSvgWrapper :path="mdiTrashCanOutline" />
					</template>
				</NcButton>
			</header>

			<NcEmptyContent v-if="job.status === 'queued' || job.status === 'running'"
				:name="job.status === 'queued' ? t('pinpoint', 'Waiting for its turn…') : t('pinpoint', 'Reading the document…')"
				:description="t('pinpoint', 'The language model runs on your Nextcloud’s AI provider. A local model can take a minute or two. You will get a notification when it is done.')">
				<template #icon>
					<NcLoadingIcon :size="64" />
				</template>
			</NcEmptyContent>

			<NcEmptyContent v-else-if="job.status === 'failed'"
				:name="t('pinpoint', 'This document could not be read')"
				:description="job.error ?? ''">
				<template #icon>
					<NcIconSvgWrapper :path="mdiAlertCircleOutline" />
				</template>
				<template #action>
					<NcButton variant="primary" @click="retry">
						{{ t('pinpoint', 'Try again') }}
					</NcButton>
				</template>
			</NcEmptyContent>

			<div v-else-if="extraction && schema" class="review">
				<div class="review__document">
					<DocumentViewer :job-id="job.id"
						:pages="extraction.pages"
						:fields="extraction.fields"
						:specs="schema.fields"
						:selected-key="selectedKey"
						@select="selectedKey = $event" />
				</div>

				<div class="review__fields">
					<NcNoteCard v-if="job.status === 'saved'" type="success">
						{{ t('pinpoint', 'Saved to {table}.', { table: job.schemaName }) }}
						<a :href="rowUrl" target="_blank" rel="noopener">{{ t('pinpoint', 'Open the row in Tables') }}</a>
					</NcNoteCard>
					<NcNoteCard v-else-if="toCheck > 0" type="warning">
						{{ n('pinpoint', 'One value needs your attention before saving.', '{n} values need your attention before saving.', toCheck, { n: toCheck }) }}
					</NcNoteCard>
					<NcNoteCard v-if="extraction.truncated" type="info">
						{{ t('pinpoint', 'The document is long; only its first pages were read.') }}
					</NcNoteCard>

					<FieldCard v-for="spec in schema.fields"
						:key="spec.key"
						v-model="values[spec.key]"
						:spec="spec"
						:result="resultFor(spec.key)"
						:original="originals[spec.key]"
						:selected="selectedKey === spec.key"
						:readonly="job.status === 'saved'"
						@select="selectedKey = spec.key" />

					<section v-if="checks.length" class="checks">
						<h3>{{ t('pinpoint', 'Checks') }}</h3>
						<ul>
							<li v-for="check in checks" :key="check.id" :class="check.passed ? 'check--passed' : 'check--failed'">
								<NcIconSvgWrapper :path="check.passed ? mdiCheck : mdiClose" :size="18" />
								<span>{{ check.label }}<template v-if="check.detail">: {{ check.detail }}</template></span>
							</li>
						</ul>
					</section>

					<div v-if="job.status === 'done'" class="review__actions">
						<NcButton variant="primary" wide :disabled="saving" @click="save">
							<template #icon>
								<NcLoadingIcon v-if="saving" :size="20" />
								<NcIconSvgWrapper v-else :path="mdiTableArrowRight" />
							</template>
							{{ t('pinpoint', 'Approve and save to {table}', { table: job.schemaName }) }}
						</NcButton>
						<p class="hint">
							{{ t('pinpoint', 'The row keeps a link to this document and, for every value, the page and text it came from.') }}
						</p>
					</div>
				</div>
			</div>
		</template>

		<NcEmptyContent v-else :name="t('pinpoint', 'Loading…')">
			<template #icon>
				<NcLoadingIcon :size="64" />
			</template>
		</NcEmptyContent>
	</div>
</template>

<script setup lang="ts">
import {
	mdiAlertCircleOutline,
	mdiCheck,
	mdiClose,
	mdiFileQuestionOutline,
	mdiTableArrowRight,
	mdiTrashCanOutline,
} from '@mdi/js'
import { showError, showSuccess } from '@nextcloud/dialogs'
import { n, t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import NcButton from '@nextcloud/vue/components/NcButton'
import NcEmptyContent from '@nextcloud/vue/components/NcEmptyContent'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage, type Job } from '../api.ts'
import DocumentViewer from '../components/DocumentViewer.vue'
import FieldCard, { type FormValue } from '../components/FieldCard.vue'
import { refreshJobs, upsertJob } from '../store.ts'

const props = defineProps<{ id: string }>()
const router = useRouter()

const job = ref<Job | null>(null)
const loadError = ref('')
const values = ref<Record<string, FormValue>>({})
const originals = ref<Record<string, FormValue>>({})
const selectedKey = ref<string | null>(null)
const saving = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

const extraction = computed(() => job.value?.result ?? null)
const schema = computed(() => job.value?.schema ?? null)
const checks = computed(() => (extraction.value?.checks ?? []).filter((c) => !c.id.startsWith('required:') || !c.passed))
const toCheck = computed(() => (extraction.value ? extraction.value.summary.review + extraction.value.summary.unverified : 0))
const fileUrl = computed(() => generateUrl(`/f/${job.value?.fileId}`))
const rowUrl = computed(() => generateUrl(`/apps/tables/#/table/${job.value?.tableId}/row/${job.value?.rowId}`))
const summaryText = computed(() => {
	const s = extraction.value?.summary
	if (!s) return ''
	return t('pinpoint', '{verified} verified, {check} to check, {missing} empty', {
		verified: s.verified, check: s.review + s.unverified, missing: s.missing,
	})
})

function resultFor(key: string) {
	return extraction.value?.fields.find((f) => f.key === key)
}

function toForm(value: unknown): FormValue {
	if (value === null || value === undefined) return null
	if (typeof value === 'boolean') return value
	return String(value)
}

function fillForm(loaded: Job): void {
	const extracted = Object.fromEntries((loaded.result?.fields ?? []).map((f) => [f.key, toForm(f.value)]))
	originals.value = extracted
	values.value = { ...extracted, ...Object.fromEntries(Object.entries(loaded.savedValues ?? {}).map(([k, v]) => [k, toForm(v)])) }
	const firstToCheck = loaded.result?.fields.find((f) => f.status === 'review' || f.status === 'unverified')
	selectedKey.value = firstToCheck?.key ?? loaded.result?.fields[0]?.key ?? null
}

async function load(): Promise<void> {
	clearTimeout(timer)
	try {
		const loaded = await api.job(props.id)
		const wasPending = job.value === null || ['queued', 'running'].includes(job.value.status)
		job.value = loaded
		upsertJob(loaded)
		loadError.value = ''
		if (wasPending && loaded.result) fillForm(loaded)
		if (loaded.status === 'queued' || loaded.status === 'running') {
			timer = setTimeout(load, 2000)
		}
	} catch (error) {
		loadError.value = errorMessage(error)
	}
}

async function save(): Promise<void> {
	if (!job.value) return
	saving.value = true
	try {
		const payload = Object.fromEntries(Object.entries(values.value).map(([k, v]) => [k, v === '' ? null : v]))
		job.value = await api.save(job.value.id, payload)
		upsertJob(job.value)
		showSuccess(t('pinpoint', 'Saved to {table}', { table: job.value.schemaName }))
	} catch (error) {
		showError(errorMessage(error))
	} finally {
		saving.value = false
	}
}

async function retry(): Promise<void> {
	if (!job.value) return
	job.value = await api.retry(job.value.id)
	await load()
}

async function remove(): Promise<void> {
	if (!job.value) return
	try {
		await api.remove(job.value.id)
		await refreshJobs()
		await router.push({ name: 'new' })
	} catch (error) {
		showError(errorMessage(error))
	}
}

watch(() => props.id, () => {
	job.value = null
	values.value = {}
	load()
}, { immediate: true })

onBeforeUnmount(() => clearTimeout(timer))
</script>

<style scoped>
.job {
	padding: 16px 24px 48px 56px;
	height: 100%;
	box-sizing: border-box;
}

.job__header {
	display: flex;
	align-items: flex-start;
	justify-content: space-between;
	gap: 12px;
	margin-bottom: 16px;
}

.job__title h2 {
	margin: 4px 0 0;
	overflow-wrap: anywhere;
}

.job__meta {
	color: var(--color-text-maxcontrast);
}

.job__meta a {
	text-decoration: underline;
}

.review {
	display: grid;
	grid-template-columns: minmax(0, 3fr) minmax(320px, 2fr);
	gap: 24px;
	align-items: start;
}

.review__document {
	position: sticky;
	top: 0;
	max-height: calc(100vh - var(--header-height, 50px) - 32px);
	overflow-y: auto;
	padding: 4px 4px 28px;
}

.review__fields {
	display: flex;
	flex-direction: column;
	gap: 10px;
}

.checks h3 {
	font-size: 1em;
	margin: 8px 0 4px;
}

.checks li {
	display: flex;
	align-items: center;
	gap: 6px;
}

.check--passed {
	color: var(--color-success-text);
}

.check--failed {
	color: var(--color-error-text);
}

.review__actions {
	position: sticky;
	bottom: 0;
	padding: 12px 0;
	background: var(--color-main-background);
	border-top: 1px solid var(--color-border);
}

.hint {
	margin-top: 6px;
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
}

@media (max-width: 1024px) {
	.review {
		grid-template-columns: minmax(0, 1fr);
	}

	.review__document {
		position: static;
		max-height: none;
	}
}
</style>
