<template>
	<div class="job">
		<NcEmptyContent v-if="loadError" :name="t('pinpoint', 'Not found')" :description="loadError">
			<template #icon>
				<NcIconSvgWrapper :path="mdiFileQuestionOutline" />
			</template>
		</NcEmptyContent>

		<template v-else-if="job">
			<header class="head">
				<span class="head__icon" :class="job.mime === 'application/pdf' ? 'head__icon--pdf' : 'head__icon--image'">
					<NcIconSvgWrapper :path="job.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileImageOutline" :size="26" />
				</span>
				<div class="head__title">
					<h2>{{ job.fileName }}</h2>
					<p class="head__meta">
						<a :href="fileUrl" target="_blank" rel="noopener">
							{{ t('pinpoint', 'Open in Files') }}
							<NcIconSvgWrapper :path="mdiOpenInNew" :size="14" inline />
						</a>
						<span class="head__table">
							<NcIconSvgWrapper :path="mdiTableLarge" :size="14" inline />
							{{ job.schemaName }}
						</span>
					</p>
				</div>
				<TrustBar v-if="extraction" class="head__trust" :summary="extraction.summary" />
				<NcButton variant="tertiary" :aria-label="t('pinpoint', 'Delete this extraction')" @click="remove">
					<template #icon>
						<NcIconSvgWrapper :path="mdiTrashCanOutline" />
					</template>
				</NcButton>
			</header>

			<section v-if="job.status === 'queued' || job.status === 'running'" class="state">
				<ScanIllustration />
				<h3>{{ job.status === 'queued' ? t('pinpoint', 'Waiting for its turn…') : t('pinpoint', 'Reading the document…') }}</h3>
				<p>{{ t('pinpoint', 'Your Nextcloud’s AI provider is reading it, then Pinpoint checks every value against the page. A local model can take a minute or two, and you will get a notification when it is done.') }}</p>
			</section>

			<section v-else-if="job.status === 'failed'" class="state state--error">
				<span class="state__icon">
					<NcIconSvgWrapper :path="mdiFileAlertOutline" :size="40" />
				</span>
				<h3>{{ t('pinpoint', 'This document could not be read') }}</h3>
				<p>{{ job.error }}</p>
				<NcButton variant="primary" @click="retry">
					<template #icon>
						<NcIconSvgWrapper :path="mdiRefresh" />
					</template>
					{{ t('pinpoint', 'Try again') }}
				</NcButton>
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
					<div v-if="job.status === 'saved'" class="saved">
						<span class="saved__icon">
							<NcIconSvgWrapper :path="mdiCheckDecagramOutline" :size="26" />
						</span>
						<div>
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
						<h3 class="group__title" :class="`group__title--${group.id}`">
							<NcIconSvgWrapper :path="group.icon" :size="18" />
							{{ group.title }}
							<span class="group__count">{{ group.specs.length }}</span>
						</h3>
						<p v-if="group.hint" class="group__hint">
							{{ group.hint }}
						</p>
						<FieldCard v-for="spec in group.specs"
							:key="spec.key"
							v-model="values[spec.key]"
							:spec="spec"
							:result="resultFor(spec.key)"
							:original="originals[spec.key]"
							:selected="selectedKey === spec.key"
							:readonly="job.status === 'saved'"
							@select="selectedKey = spec.key" />
					</section>

					<section v-if="checks.length" class="group">
						<h3 class="group__title">
							<NcIconSvgWrapper :path="mdiScaleBalance" :size="18" />
							{{ t('pinpoint', 'Cross-checks') }}
						</h3>
						<ul class="checks">
							<li v-for="check in checks" :key="check.id" :class="check.passed ? 'check--passed' : 'check--failed'">
								<NcIconSvgWrapper :path="check.passed ? mdiCheckCircle : mdiCloseCircle" :size="18" />
								<span>{{ check.label }}<span v-if="check.detail" class="check__detail">{{ check.detail }}</span></span>
							</li>
						</ul>
					</section>

					<div v-if="job.status === 'done'" class="savebar">
						<p class="savebar__text">
							<template v-if="toCheck > 0">
								{{ n('pinpoint', 'Look at the value marked “Check” before saving.', 'Look at the {n} values marked “Check” or “Not found” before saving.', toCheck, { n: toCheck }) }}
							</template>
							<template v-else>
								{{ t('pinpoint', 'Every value was found in the document.') }}
							</template>
						</p>
						<NcButton variant="primary" size="large" wide :disabled="saving" @click="save">
							<template #icon>
								<NcLoadingIcon v-if="saving" :size="20" />
								<NcIconSvgWrapper v-else :path="mdiTableArrowRight" />
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
	mdiAlertCircleOutline,
	mdiCheckCircle,
	mdiCheckCircleOutline,
	mdiCheckDecagramOutline,
	mdiCloseCircle,
	mdiFileAlertOutline,
	mdiFileImageOutline,
	mdiFilePdfBox,
	mdiFileQuestionOutline,
	mdiMinusCircleOutline,
	mdiOpenInNew,
	mdiRefresh,
	mdiScaleBalance,
	mdiTableArrowRight,
	mdiTableLarge,
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
import { api, errorMessage, type FieldSpec, type Job } from '../api.ts'
import DocumentViewer from '../components/DocumentViewer.vue'
import FieldCard, { type FormValue } from '../components/FieldCard.vue'
import ScanIllustration from '../components/ScanIllustration.vue'
import TrustBar from '../components/TrustBar.vue'
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

// Fields that need a person come first; the table's own column order is kept inside each group.
const groups = computed(() => {
	const specs = schema.value?.fields ?? []
	const statusOf = (spec: FieldSpec) => resultFor(spec.key)?.status ?? 'missing'
	return [
		{
			id: 'check',
			title: t('pinpoint', 'Check these'),
			hint: t('pinpoint', 'Click a value to see where it is on the page.'),
			icon: mdiAlertCircleOutline,
			specs: specs.filter((s) => ['review', 'unverified'].includes(statusOf(s))),
		},
		{
			id: 'verified',
			title: t('pinpoint', 'Verified'),
			hint: '',
			icon: mdiCheckCircleOutline,
			specs: specs.filter((s) => statusOf(s) === 'verified'),
		},
		{
			id: 'missing',
			title: t('pinpoint', 'Not in the document'),
			hint: t('pinpoint', 'Fill these in yourself if you know them, or leave them empty.'),
			icon: mdiMinusCircleOutline,
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
	--pp-brand: #7c6cf2;
	box-sizing: border-box;
	min-height: 100%;
	padding: 16px 24px 32px 56px;
}

.head {
	display: flex;
	align-items: center;
	gap: 14px;
	margin-bottom: 18px;
	padding: 14px 16px;
	border: 1px solid var(--color-border);
	border-radius: 16px;
	background: var(--color-main-background);
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03), 0 6px 20px rgba(30, 20, 80, 0.05);
}

.head__icon {
	display: inline-flex;
	flex: none;
	padding: 9px;
	border-radius: 12px;
}

.head__icon--pdf {
	color: #d93a3a;
	background: color-mix(in srgb, #d93a3a 12%, transparent);
}

.head__icon--image {
	color: #2f80ed;
	background: color-mix(in srgb, #2f80ed 12%, transparent);
}

.head__title {
	flex: 1;
	min-width: 0;
}

.head__title h2 {
	margin: 0;
	overflow: hidden;
	font-size: 19px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.head__meta {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 4px 14px;
	color: var(--color-text-maxcontrast);
	font-size: 13px;
}

.head__meta a,
.head__table {
	display: inline-flex;
	align-items: center;
	gap: 4px;
}

.head__meta a:hover {
	color: var(--color-main-text);
	text-decoration: underline;
}

.head__trust {
	flex: 0 1 380px;
	min-width: 220px;
}

.state {
	display: flex;
	flex-direction: column;
	align-items: center;
	max-width: 520px;
	margin: 48px auto;
	text-align: center;
}

.state h3 {
	margin: 16px 0 6px;
	font-size: 19px;
}

.state p {
	margin-bottom: 18px;
	color: var(--color-text-maxcontrast);
	line-height: 1.5;
}

.state__icon {
	display: inline-flex;
	padding: 18px;
	border-radius: 50%;
	color: var(--color-element-error, #c90000);
	background: color-mix(in srgb, var(--color-element-error, #c90000) 10%, transparent);
}

.review {
	display: grid;
	grid-template-columns: minmax(0, 3fr) minmax(340px, 2fr);
	gap: 20px;
	align-items: start;
}

.desk {
	position: sticky;
	top: 8px;
	max-height: calc(100vh - var(--header-height, 50px) - 40px);
	overflow-y: auto;
	padding: 18px 18px 34px;
	border-radius: 18px;
	background:
		radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--color-main-text) 9%, transparent) 1px, transparent 0) 0 0 / 18px 18px,
		var(--color-background-dark);
}

.panel {
	display: flex;
	flex-direction: column;
	gap: 10px;
}

.group {
	display: flex;
	flex-direction: column;
	gap: 10px;
}

.group + .group {
	margin-top: 10px;
}

.group__title {
	display: flex;
	align-items: center;
	gap: 8px;
	margin: 0;
	font-size: 15px;
}

.group__title--check {
	color: var(--color-warning-text, #664700);
}

.group__title--verified {
	color: var(--color-success-text, #005416);
}

.group__count {
	padding: 0 8px;
	border-radius: 999px;
	background: var(--color-background-dark);
	color: var(--color-text-maxcontrast);
	font-size: 12px;
}

.group__hint {
	margin-top: -4px;
	color: var(--color-text-maxcontrast);
	font-size: 13px;
}

.checks {
	display: flex;
	flex-direction: column;
	gap: 6px;
}

.checks li {
	display: flex;
	align-items: flex-start;
	gap: 8px;
	padding: 8px 12px;
	border-radius: 10px;
	font-size: 13.5px;
}

.check--passed {
	color: var(--color-success-text, #005416);
	background: color-mix(in srgb, var(--color-element-success, #099f05) 9%, transparent);
}

.check--failed {
	color: var(--color-error-text, #8a0000);
	background: color-mix(in srgb, var(--color-element-error, #c90000) 9%, transparent);
}

.check__detail {
	display: block;
	opacity: 0.85;
	font-size: 12.5px;
}

.saved {
	display: flex;
	align-items: center;
	gap: 12px;
	padding: 14px;
	border-radius: 14px;
	background: color-mix(in srgb, var(--color-element-success, #099f05) 10%, var(--color-main-background));
	border: 1px solid color-mix(in srgb, var(--color-element-success, #099f05) 35%, transparent);
}

.saved__icon {
	color: var(--color-element-success, #099f05);
}

.saved div {
	flex: 1;
}

.saved p {
	color: var(--color-text-maxcontrast);
	font-size: 13px;
}

.savebar {
	position: sticky;
	bottom: 12px;
	display: flex;
	flex-direction: column;
	gap: 8px;
	margin-top: 8px;
	padding: 12px;
	border: 1px solid var(--color-border);
	border-radius: 16px;
	background: var(--color-main-background);
	box-shadow: 0 8px 28px rgba(30, 20, 80, 0.12);
}

.savebar__text {
	color: var(--color-text-maxcontrast);
	font-size: 13px;
	text-align: center;
}

@media (max-width: 1100px) {
	.head {
		flex-wrap: wrap;
	}

	.head__trust {
		flex-basis: 100%;
		order: 3;
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
