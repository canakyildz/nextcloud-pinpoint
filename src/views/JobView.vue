<template>
	<div class="job">
		<NcEmptyContent v-if="loadError" :name="t('pinpoint', 'Not found')" :description="loadError">
			<template #icon>
				<NcIconSvgWrapper :path="mdiFileQuestionOutline" />
			</template>
		</NcEmptyContent>

		<template v-else-if="job">
			<header class="head">
				<div class="head__top">
					<div class="head__title">
						<p class="head__crumb pp-mono">
							{{ job.schemaName }} /
						</p>
						<h2>{{ job.fileName }}</h2>
					</div>
					<NcButton :href="fileUrl" target="_blank">
						<template #icon>
							<NcIconSvgWrapper :path="mdiOpenInNew" :size="16" />
						</template>
						{{ t('pinpoint', 'Open in Files') }}
					</NcButton>
					<NcButton variant="tertiary" :aria-label="t('pinpoint', 'Delete this extraction')" @click="remove">
						<template #icon>
							<NcIconSvgWrapper :path="mdiTrashCanOutline" :size="18" />
						</template>
					</NcButton>
				</div>
				<dl class="meta">
					<div>
						<dt>{{ t('pinpoint', 'Status') }}</dt>
						<dd>
							<span class="pp-dot" :class="[`pp-dot--${jobTone(job)}`, { 'pp-dot--pulse': isPending(job) }]" />
							{{ jobLabel(job) }}
						</dd>
					</div>
					<div>
						<dt>{{ t('pinpoint', 'Table') }}</dt>
						<dd>{{ job.schemaName }}</dd>
					</div>
					<div v-if="extraction">
						<dt>{{ t('pinpoint', 'Pages') }}</dt>
						<dd class="pp-mono">
							{{ extraction.pages.length }}<span v-if="ocrPages" class="meta__soft"> · OCR</span>
						</dd>
					</div>
					<div>
						<dt>{{ t('pinpoint', 'Started') }}</dt>
						<dd class="pp-mono">
							{{ startedAt }}
						</dd>
					</div>
					<div v-if="extraction" class="meta__trust">
						<dt>{{ t('pinpoint', 'Fields') }}</dt>
						<dd><TrustBar :summary="extraction.summary" /></dd>
					</div>
				</dl>
			</header>

			<template v-if="isPending(job)">
				<section class="box pending">
					<div class="pending__head">
						<span class="pp-dot pp-dot--amber pp-dot--pulse" />
						<strong>{{ job.status === 'queued' ? t('pinpoint', 'Waiting for its turn') : t('pinpoint', 'Reading the document') }}</strong>
						<span class="pending__time pp-mono">{{ elapsed }}</span>
					</div>
					<p>{{ t('pinpoint', 'Your Nextcloud’s AI provider is reading it, then Pinpoint checks every value against the page. A local model can take a minute or two, and you will get a notification when it is done.') }}</p>
				</section>
				<div class="review review--skeleton" aria-hidden="true">
					<div class="desk">
						<div class="skeleton skeleton--page" />
					</div>
					<div class="list">
						<div v-for="i in 5" :key="i" class="skeleton-row">
							<div class="skeleton skeleton--label" />
							<div class="skeleton skeleton--input" />
						</div>
					</div>
				</div>
			</template>

			<section v-else-if="job.status === 'failed'" class="box failed">
				<div class="pending__head">
					<span class="pp-dot pp-dot--red" />
					<strong>{{ t('pinpoint', 'This document could not be read') }}</strong>
				</div>
				<pre class="log pp-mono">{{ job.error }}</pre>
				<div class="failed__actions">
					<NcButton variant="primary" @click="retry">
						<template #icon>
							<NcIconSvgWrapper :path="mdiRefresh" :size="18" />
						</template>
						{{ t('pinpoint', 'Try again') }}
					</NcButton>
				</div>
			</section>

			<div v-else-if="extraction && schema" class="review">
				<div class="desk">
					<DocumentViewer :job-id="job.id"
						:pages="extraction.pages"
						:fields="extraction.fields"
						:specs="schema.fields"
						:selected-key="selectedKey"
						@select="selectedKey = $event" />
				</div>

				<aside class="panel">
					<div v-if="job.status === 'saved'" class="box saved">
						<NcIconSvgWrapper :path="mdiCheckCircle" :size="20" class="saved__icon" />
						<div class="saved__text">
							<strong>{{ t('pinpoint', 'Saved to {table}', { table: job.schemaName }) }}</strong>
							<p>{{ t('pinpoint', 'The row links back to this document and keeps the evidence for every value.') }}</p>
						</div>
						<NcButton :href="rowUrl" target="_blank">
							{{ t('pinpoint', 'Open in Tables') }}
						</NcButton>
					</div>
					<NcNoteCard v-if="extraction.truncated" type="info">
						{{ t('pinpoint', 'The document is long; only its first pages were read.') }}
					</NcNoteCard>

					<section v-for="group in groups" :key="group.id" class="group">
						<h3 class="group__title">
							{{ group.title }}
							<span class="group__count pp-mono">{{ group.specs.length }}</span>
						</h3>
						<p v-if="group.hint" class="group__hint">
							{{ group.hint }}
						</p>
						<div class="list">
							<FieldCard v-for="spec in group.specs"
								:key="spec.key"
								v-model="values[spec.key]"
								:spec="spec"
								:result="resultFor(spec.key)"
								:original="originals[spec.key]"
								:selected="selectedKey === spec.key"
								:readonly="job.status === 'saved'"
								@select="selectedKey = spec.key" />
						</div>
					</section>

					<section v-if="checks.length" class="group">
						<h3 class="group__title">
							{{ t('pinpoint', 'Cross-checks') }}
						</h3>
						<ul class="list checks">
							<li v-for="check in checks" :key="check.id" :class="check.passed ? 'check--passed' : 'check--failed'">
								<NcIconSvgWrapper :path="check.passed ? mdiCheck : mdiClose" :size="16" class="check__icon" />
								<span>{{ check.label }}<span v-if="check.detail" class="check__detail pp-mono">{{ check.detail }}</span></span>
							</li>
						</ul>
					</section>

					<div v-if="job.status === 'done'" class="box savebar">
						<p class="savebar__text">
							<template v-if="toCheck > 0">
								{{ n('pinpoint', 'Look at the value marked “Check” before saving.', 'Look at the {n} values marked “Check” or “Not found” before saving.', toCheck, { n: toCheck }) }}
							</template>
							<template v-else>
								{{ t('pinpoint', 'Every value was found in the document.') }}
							</template>
						</p>
						<NcButton variant="primary" wide :disabled="saving" @click="save">
							<template #icon>
								<NcLoadingIcon v-if="saving" :size="18" />
								<NcIconSvgWrapper v-else :path="mdiTableArrowRight" :size="18" />
							</template>
							{{ t('pinpoint', 'Approve and save to {table}', { table: job.schemaName }) }}
						</NcButton>
					</div>
				</aside>
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
	mdiCheck,
	mdiCheckCircle,
	mdiClose,
	mdiFileQuestionOutline,
	mdiOpenInNew,
	mdiRefresh,
	mdiTableArrowRight,
	mdiTrashCanOutline,
} from '@mdi/js'
import { showError, showSuccess } from '@nextcloud/dialogs'
import { getCanonicalLocale, n, t } from '@nextcloud/l10n'
import { generateUrl } from '@nextcloud/router'
import NcButton from '@nextcloud/vue/components/NcButton'
import NcEmptyContent from '@nextcloud/vue/components/NcEmptyContent'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage, type FieldSpec, type Job } from '../api.ts'
import DocumentViewer from '../components/DocumentViewer.vue'
import FieldCard, { type FormValue } from '../components/FieldCard.vue'
import TrustBar from '../components/TrustBar.vue'
import { isPending, jobLabel, jobTone } from '../status.ts'
import { refreshJobs, upsertJob } from '../store.ts'

const props = defineProps<{ id: string }>()
const router = useRouter()

const job = ref<Job | null>(null)
const loadError = ref('')
const values = ref<Record<string, FormValue>>({})
const originals = ref<Record<string, FormValue>>({})
const selectedKey = ref<string | null>(null)
const saving = ref(false)
const now = ref(Date.now())
let timer: ReturnType<typeof setTimeout> | undefined
const clock = setInterval(() => {
	now.value = Date.now()
}, 1000)

const extraction = computed(() => job.value?.result ?? null)
const schema = computed(() => job.value?.schema ?? null)
const checks = computed(() => (extraction.value?.checks ?? []).filter((c) => !c.id.startsWith('required:') || !c.passed))
const toCheck = computed(() => (extraction.value ? extraction.value.summary.review + extraction.value.summary.unverified : 0))
const fileUrl = computed(() => generateUrl(`/f/${job.value?.fileId}`))
const ocrPages = computed(() => extraction.value?.pages.some((p) => p.source === 'ocr') ?? false)
const startedAt = computed(() => (job.value
	? new Date(job.value.createdAt * 1000).toLocaleString(getCanonicalLocale(), { dateStyle: 'medium', timeStyle: 'short' })
	: ''))
const elapsed = computed(() => {
	const seconds = Math.max(0, Math.floor(now.value / 1000 - (job.value?.createdAt ?? now.value / 1000)))
	return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
})
const rowUrl = computed(() => generateUrl(`/apps/tables/#/table/${job.value?.tableId}/row/${job.value?.rowId}`))

// Fields that need a person come first; the table's own column order is kept inside each group.
const groups = computed(() => {
	const specs = schema.value?.fields ?? []
	const statusOf = (spec: FieldSpec) => resultFor(spec.key)?.status ?? 'missing'
	return [
		{
			id: 'check',
			title: t('pinpoint', 'Check these'),
			hint: t('pinpoint', 'Click a value to see where it is on the page.'),
				specs: specs.filter((s) => ['review', 'unverified'].includes(statusOf(s))),
		},
		{
			id: 'verified',
			title: t('pinpoint', 'Verified'),
			hint: '',
				specs: specs.filter((s) => statusOf(s) === 'verified'),
		},
		{
			id: 'missing',
			title: t('pinpoint', 'Not in the document'),
			hint: t('pinpoint', 'Fill these in yourself if you know them, or leave them empty.'),
				specs: specs.filter((s) => statusOf(s) === 'missing'),
		},
	].filter((group) => group.specs.length > 0)
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
		if (isPending(loaded)) {
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

onBeforeUnmount(() => {
	clearTimeout(timer)
	clearInterval(clock)
})
</script>

<style scoped>
.job {
	box-sizing: border-box;
	min-height: 100%;
	padding: 20px 28px 40px 56px;
}

.head {
	margin-bottom: 24px;
}

.head__top {
	display: flex;
	align-items: flex-end;
	gap: 8px;
	margin-bottom: 16px;
}

.head__title {
	flex: 1;
	min-width: 0;
}

.head__crumb {
	color: var(--pp-faint);
	font-size: 12px;
}

.head__title h2 {
	margin: 2px 0 0;
	overflow: hidden;
	font-size: 26px;
	font-weight: 600;
	line-height: 1.2;
	letter-spacing: -0.035em;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.meta {
	display: flex;
	flex-wrap: wrap;
	margin: 0;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
	box-shadow: var(--pp-shadow);
}

.meta > div {
	padding: 12px 20px 14px;
	border-right: 1px solid var(--pp-border);
}

.meta dt {
	display: block;
	width: auto;
	margin-bottom: 4px;
	padding: 0;
	text-align: start;
	color: var(--pp-muted);
	font-size: 12.5px;
}

.meta dd {
	display: flex;
	width: auto;
	padding: 0;
	align-items: center;
	gap: 8px;
	margin: 0;
	font-size: 14px;
	font-weight: 500;
	white-space: nowrap;
}

.meta__soft {
	color: var(--pp-faint);
	font-weight: normal;
}

.meta > .meta__trust {
	flex: 1;
	min-width: 240px;
	border-right: 0;
}

.meta__trust dd {
	display: block;
	padding-top: 4px;
	font-weight: normal;
}

.box {
	overflow: hidden;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
	box-shadow: var(--pp-shadow);
}

.pending,
.failed {
	padding: 16px 20px;
	margin-bottom: 20px;
}

.pending__head {
	display: flex;
	align-items: center;
	gap: 10px;
	font-size: 15px;
}

.pending__head strong {
	flex: 1;
	font-weight: 600;
}

.pending__time {
	color: var(--pp-muted);
	font-size: 13px;
}

.pending p {
	max-width: 640px;
	margin-top: 6px;
	color: var(--pp-muted);
	font-size: 14px;
	line-height: 1.55;
}

.log {
	margin: 12px 0;
	padding: 12px 14px;
	border: 1px solid var(--pp-border);
	border-radius: 8px;
	background: var(--pp-bg-2);
	color: var(--pp-red-text);
	font-size: 12.5px;
	line-height: 1.6;
	white-space: pre-wrap;
}

.failed__actions {
	display: flex;
	justify-content: flex-end;
}

.review {
	display: grid;
	grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr);
	gap: 24px;
	align-items: start;
}

.desk {
	position: sticky;
	top: 8px;
	max-height: calc(100vh - var(--header-height, 50px) - 40px);
	overflow-y: auto;
	padding: 24px 24px 44px;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background:
		radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--pp-fg) 13%, transparent) 1px, transparent 0) 0 0 / 16px 16px,
		var(--pp-bg-2);
}

.panel {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.list {
	overflow: hidden;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
	box-shadow: var(--pp-shadow);
}

.group__title {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0 0 8px;
	font-size: 14px;
	font-weight: 600;
	letter-spacing: -0.01em;
}

.group__count {
	display: inline-flex;
	align-items: center;
	height: 20px;
	padding: 0 7px;
	border: 1px solid var(--pp-border);
	border-radius: 999px;
	color: var(--pp-muted);
	font-size: 11.5px;
	font-weight: normal;
}

.group__hint {
	margin: -4px 0 10px;
	color: var(--pp-muted);
	font-size: 13px;
}

.checks li {
	display: flex;
	align-items: flex-start;
	gap: 10px;
	padding: 10px 16px;
	font-size: 13.5px;
}

.checks li + li {
	border-top: 1px solid var(--pp-border);
}

.check__icon {
	flex: none;
	margin-top: 1px;
}

.check--passed .check__icon {
	color: var(--pp-green);
}

.check--failed .check__icon {
	color: var(--pp-red);
}

.check--failed {
	color: var(--pp-red-text);
}

.check__detail {
	display: block;
	margin-top: 2px;
	color: var(--pp-muted);
	font-size: 12px;
}

.saved {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 14px 16px;
}

.saved__icon {
	flex: none;
	color: var(--pp-blue);
}

.saved__text {
	flex: 1;
	min-width: 0;
	font-size: 14px;
}

.saved__text strong {
	font-weight: 600;
}

.saved__text p {
	color: var(--pp-muted);
	font-size: 13px;
}

.savebar {
	position: sticky;
	bottom: 12px;
	display: flex;
	flex-direction: column;
	gap: 10px;
	padding: 12px;
	box-shadow: var(--pp-shadow-lg);
}

.savebar__text {
	color: var(--pp-muted);
	font-size: 13px;
	text-align: center;
}

/* Placeholder layout while the document is read. */
.skeleton {
	border-radius: 6px;
	background: linear-gradient(90deg, var(--pp-bg-3) 0%, var(--pp-bg-2) 50%, var(--pp-bg-3) 100%) 0 0 / 200% 100%;
	animation: shimmer 1.6s linear infinite;
}

.skeleton--page {
	aspect-ratio: 1 / 1.414;
	border-radius: 4px;
}

.skeleton-row {
	padding: 16px;
}

.skeleton-row + .skeleton-row {
	border-top: 1px solid var(--pp-border);
}

.skeleton--label {
	width: 35%;
	height: 12px;
	margin-bottom: 10px;
}

.skeleton--input {
	height: 34px;
}

@keyframes shimmer {
	to {
		background-position: -200% 0;
	}
}

@media (prefers-reduced-motion: reduce) {
	.skeleton {
		animation: none;
	}
}

@media (max-width: 1100px) {
	.meta > .meta__trust {
		flex-basis: 100%;
		border-top: 1px solid var(--pp-border);
	}
}

@media (max-width: 1024px) {
	.review {
		grid-template-columns: minmax(0, 1fr);
	}

	.desk {
		position: static;
		max-height: none;
	}
}
</style>
