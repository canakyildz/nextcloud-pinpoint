<template>
	<div class="new">
		<section class="hero">
			<div class="hero__text">
				<span class="hero__eyebrow">
					<NcIconSvgWrapper :path="mdiCrosshairsGps" :size="16" />
					Pinpoint
				</span>
				<h2>{{ t('pinpoint', 'Turn documents into table rows you can trust') }}</h2>
				<p>
					{{ t('pinpoint', 'Every value is shown on the page it came from. Pinpoint only marks a value verified when the document says exactly that, and nothing is saved until you approve it.') }}
				</p>
			</div>
			<HeroIllustration class="hero__art" />
		</section>

		<NcNoteCard v-if="store.state && !store.state.textGenerationAvailable" type="error"
			:heading="t('pinpoint', 'No AI provider yet')">
			{{ t('pinpoint', 'Pinpoint uses the AI provider configured in Nextcloud. Ask your admin to set one up under Administration → Artificial intelligence, for example the local llm2 app or the OpenAI and LocalAI integration.') }}
		</NcNoteCard>
		<NcNoteCard v-if="store.state?.tablesError" type="error">
			{{ store.state.tablesError }}
		</NcNoteCard>

		<div class="steps">
			<section class="card">
				<header class="card__head">
					<span class="card__step">1</span>
					<div>
						<h3>{{ t('pinpoint', 'Documents') }}</h3>
						<p>{{ t('pinpoint', 'PDFs, scans and photos') }}</p>
					</div>
				</header>

				<button type="button" class="dropzone" @click="pickFiles">
					<span class="dropzone__icon">
						<NcIconSvgWrapper :path="mdiFileDocumentMultipleOutline" :size="28" />
					</span>
					<strong>{{ files.length ? t('pinpoint', 'Add more documents') : t('pinpoint', 'Choose from Files') }}</strong>
					<span class="dropzone__hint">{{ t('pinpoint', 'or right-click a document in Files and choose “Extract fields”') }}</span>
				</button>

				<TransitionGroup tag="ul" name="chip" class="files">
					<li v-for="file in files" :key="file.id" class="file">
						<span class="file__icon" :class="file.mime === 'application/pdf' ? 'file__icon--pdf' : 'file__icon--image'">
							<NcIconSvgWrapper :path="file.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileImageOutline" :size="20" />
						</span>
						<span class="file__name">{{ file.name }}</span>
						<span v-if="file.size" class="file__size">{{ formatSize(file.size) }}</span>
						<NcButton variant="tertiary-no-background"
							size="small"
							:aria-label="t('pinpoint', 'Remove {name}', { name: file.name })"
							@click="files = files.filter((f) => f.id !== file.id)">
							<template #icon>
								<NcIconSvgWrapper :path="mdiClose" :size="18" />
							</template>
						</NcButton>
					</li>
				</TransitionGroup>
			</section>

			<section class="card">
				<header class="card__head">
					<span class="card__step">2</span>
					<div>
						<h3>{{ t('pinpoint', 'Table to fill') }}</h3>
						<p>{{ t('pinpoint', 'Its columns are what Pinpoint looks for') }}</p>
					</div>
				</header>

				<NcSelect v-if="tableOptions.length"
					v-model="selectedTable"
					class="table-select"
					:options="tableOptions"
					label="label"
					:input-label="t('pinpoint', 'Table')"
					:placeholder="t('pinpoint', 'Choose a table')"
					:clearable="false" />

				<NcNoteCard v-if="schemaError" type="warning">
					{{ schemaError }}
				</NcNoteCard>
				<ul v-else-if="schema" class="fields">
					<li v-for="field in schema.fields" :key="field.key" :title="field.description">
						<NcIconSvgWrapper :path="typeIcon(field.type)" :size="16" />
						{{ field.label }}
					</li>
				</ul>

				<p class="templates__title">
					{{ tableOptions.length ? t('pinpoint', 'Or start a new table from a template') : t('pinpoint', 'Start with a table made for it') }}
				</p>
				<div class="templates">
					<button v-for="template in store.state?.templates ?? []"
						:key="template.id"
						type="button"
						class="template"
						:disabled="creatingTable"
						@click="createTable(template.id, template.name)">
						<span class="template__icon" :class="`template__icon--${template.id.split(':')[1]}`">
							<NcIconSvgWrapper :path="template.name === 'Invoice' ? mdiFileDocumentOutline : mdiReceiptTextOutline" :size="22" />
						</span>
						<span class="template__text">
							<strong>{{ templateTitle(template.name) }}</strong>
							<span>{{ template.fields.map((f) => f.label).slice(0, 4).join(', ') }}…</span>
						</span>
						<NcIconSvgWrapper :path="mdiTablePlus" :size="20" class="template__add" />
					</button>
				</div>
			</section>
		</div>

		<ol class="how">
			<li>
				<NcIconSvgWrapper :path="mdiTextRecognition" :size="22" />
				<span>{{ t('pinpoint', 'Reads every word and where it is on the page, with OCR for scans') }}</span>
			</li>
			<li>
				<NcIconSvgWrapper :path="mdiCreationOutline" :size="22" />
				<span>{{ t('pinpoint', 'Your Nextcloud’s AI proposes each value, quoting the text it read') }}</span>
			</li>
			<li>
				<NcIconSvgWrapper :path="mdiShieldCheckOutline" :size="22" />
				<span>{{ t('pinpoint', 'Pinpoint checks every value against the page before you see it') }}</span>
			</li>
		</ol>

		<footer class="cta">
			<p class="cta__summary">
				<template v-if="files.length && selectedTable">
					{{ n('pinpoint', '{n} document into {table}', '{n} documents into {table}', files.length, { n: files.length, table: selectedTable.label }) }}
				</template>
				<template v-else>
					{{ t('pinpoint', 'Choose documents and a table to start.') }}
				</template>
			</p>
			<NcButton variant="primary" size="large" :disabled="!canStart" @click="start">
				<template #icon>
					<NcLoadingIcon v-if="starting" :size="20" />
					<NcIconSvgWrapper v-else :path="mdiArrowRight" />
				</template>
				{{ t('pinpoint', 'Extract') }}
			</NcButton>
		</footer>
	</div>
</template>

<script setup lang="ts">
import {
	mdiArrowRight,
	mdiCalendarBlankOutline,
	mdiClose,
	mdiCreationOutline,
	mdiCrosshairsGps,
	mdiFileDocumentMultipleOutline,
	mdiFileDocumentOutline,
	mdiFileImageOutline,
	mdiFilePdfBox,
	mdiFormatListBulleted,
	mdiFormatText,
	mdiPound,
	mdiReceiptTextOutline,
	mdiShieldCheckOutline,
	mdiTablePlus,
	mdiTextRecognition,
	mdiToggleSwitchOutline,
} from '@mdi/js'
import { getFilePickerBuilder, showError, showSuccess } from '@nextcloud/dialogs'
import { n, t } from '@nextcloud/l10n'
import NcButton from '@nextcloud/vue/components/NcButton'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import NcSelect from '@nextcloud/vue/components/NcSelect'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage, type FieldType, type FileRef, type Schema } from '../api.ts'
import HeroIllustration from '../components/HeroIllustration.vue'
import { refreshState, store, upsertJob } from '../store.ts'

const SUPPORTED_MIMES = ['application/pdf', 'image/png', 'image/jpeg', 'image/tiff', 'image/webp']
const LAST_TABLE_KEY = 'pinpoint:lastTable'

interface TableOption { id: number, label: string }

const route = useRoute()
const router = useRouter()

const files = ref<FileRef[]>([])
const selectedTable = ref<TableOption | null>(null)
const schema = ref<Schema | null>(null)
const schemaError = ref('')
const creatingTable = ref(false)
const starting = ref(false)

const tableOptions = computed<TableOption[]>(() => (store.state?.tables ?? []).map((table) => ({
	id: table.id,
	label: `${table.emoji ? table.emoji + ' ' : ''}${table.title}`,
})))

const canStart = computed(() => files.value.length > 0 && schema.value !== null && !starting.value
	&& store.state?.textGenerationAvailable !== false)

function typeIcon(type: FieldType): string {
	return {
		text: mdiFormatText,
		number: mdiPound,
		date: mdiCalendarBlankOutline,
		selection: mdiFormatListBulleted,
		boolean: mdiToggleSwitchOutline,
	}[type]
}

function templateTitle(name: string): string {
	return name === 'Invoice' ? t('pinpoint', 'Invoices') : t('pinpoint', 'Receipts')
}

function formatSize(bytes: number): string {
	if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
	return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function addFiles(added: FileRef[]): void {
	const known = new Set(files.value.map((f) => f.id))
	files.value.push(...added.filter((f) => !known.has(f.id) && SUPPORTED_MIMES.includes(f.mime)))
}

async function pickFiles(): Promise<void> {
	const picker = getFilePickerBuilder(t('pinpoint', 'Choose documents'))
		.setMultiSelect(true)
		.setMimeTypeFilter(SUPPORTED_MIMES)
		.allowDirectories(false)
		.addButton({
			label: t('pinpoint', 'Choose'),
			variant: 'primary',
			callback: (nodes) => addFiles(nodes.map((node) => ({
				id: node.fileid as number, name: node.basename, mime: node.mime, size: node.size,
			}))),
		})
		.build()
	try {
		await picker.pick()
	} catch {
		// closed without choosing
	}
}

async function createTable(templateId: string, name: string): Promise<void> {
	creatingTable.value = true
	try {
		const table = await api.createTable(templateId, templateTitle(name))
		await refreshState()
		selectedTable.value = tableOptions.value.find((o) => o.id === table.id) ?? null
		showSuccess(t('pinpoint', 'Created the table “{title}” in Tables', { title: table.title }))
	} catch (error) {
		showError(errorMessage(error))
	} finally {
		creatingTable.value = false
	}
}

watch(selectedTable, async (option) => {
	schema.value = null
	schemaError.value = ''
	if (!option) return
	try {
		localStorage.setItem(LAST_TABLE_KEY, String(option.id))
	} catch {
		// storage can be unavailable; remembering the table is only a convenience
	}
	try {
		schema.value = await api.tableSchema(option.id)
	} catch (error) {
		schemaError.value = errorMessage(error)
	}
})

watch(tableOptions, (options) => {
	if (selectedTable.value || options.length === 0) return
	let last: string | null = null
	try {
		last = localStorage.getItem(LAST_TABLE_KEY)
	} catch {
		last = null
	}
	selectedTable.value = options.find((o) => String(o.id) === last) ?? (options.length === 1 ? options[0] : null)
}, { immediate: true })

async function start(): Promise<void> {
	if (!selectedTable.value) return
	starting.value = true
	const created = []
	for (const file of files.value) {
		try {
			const job = await api.createJob(file.id, selectedTable.value.id)
			upsertJob(job)
			created.push(job)
		} catch (error) {
			showError(`${file.name}: ${errorMessage(error)}`)
		}
	}
	starting.value = false
	if (created.length) {
		files.value = []
		await router.push({ name: 'job', params: { id: created[0].id } })
	}
}

onMounted(async () => {
	const ids = String(route.query.fileIds ?? '').split(',').map(Number).filter((id) => id > 0)
	if (ids.length) {
		try {
			addFiles(await api.files(ids))
		} catch (error) {
			showError(errorMessage(error))
		}
	}
})
</script>

<style scoped>
.new {
	--pp-brand: #7c6cf2;
	--pp-brand-2: #1fb5ac;
	max-width: 980px;
	margin: 0 auto;
	padding: 20px 28px 40px 56px;
}

.hero {
	display: grid;
	grid-template-columns: minmax(0, 1.4fr) minmax(200px, 1fr);
	align-items: center;
	gap: 24px;
	padding: 28px 32px;
	margin-bottom: 20px;
	border-radius: 20px;
	background:
		radial-gradient(120% 140% at 100% 0%, color-mix(in srgb, var(--pp-brand-2) 18%, transparent), transparent 60%),
		radial-gradient(120% 140% at 0% 100%, color-mix(in srgb, var(--pp-brand) 16%, transparent), transparent 60%),
		var(--color-main-background);
	border: 1px solid color-mix(in srgb, var(--pp-brand) 18%, var(--color-border));
}

.hero__eyebrow {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	padding: 3px 10px;
	border-radius: 999px;
	background: color-mix(in srgb, var(--pp-brand) 14%, transparent);
	color: color-mix(in srgb, var(--pp-brand) 75%, var(--color-main-text));
	font-size: 13px;
	font-weight: 600;
	letter-spacing: 0.02em;
}

.hero h2 {
	margin: 12px 0 8px;
	font-size: 26px;
	line-height: 1.25;
	font-weight: 700;
}

.hero p {
	color: var(--color-text-maxcontrast);
	font-size: 15px;
	line-height: 1.55;
	max-width: 520px;
}

.hero__art {
	justify-self: center;
}

.steps {
	display: grid;
	grid-template-columns: repeat(2, minmax(0, 1fr));
	gap: 16px;
}

.card {
	padding: 20px;
	border-radius: 16px;
	background: var(--color-main-background);
	border: 1px solid var(--color-border);
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04), 0 6px 20px rgba(30, 20, 80, 0.05);
}

.card__head {
	display: flex;
	align-items: center;
	gap: 12px;
	margin-bottom: 16px;
}

.card__head h3 {
	margin: 0;
	font-size: 17px;
}

.card__head p {
	color: var(--color-text-maxcontrast);
	font-size: 13px;
}

.card__step {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	flex: none;
	width: 32px;
	height: 32px;
	border-radius: 10px;
	background: linear-gradient(135deg, var(--pp-brand), var(--pp-brand-2));
	color: #fff;
	font-weight: 700;
}

.dropzone {
	box-sizing: border-box;
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 6px;
	width: 100%;
	margin: 0;
	padding: 22px 16px;
	border: 2px dashed color-mix(in srgb, var(--pp-brand) 35%, var(--color-border));
	border-radius: 14px;
	background: color-mix(in srgb, var(--pp-brand) 4%, transparent);
	color: var(--color-main-text);
	cursor: pointer;
	transition: background 0.15s, border-color 0.15s;
}

.dropzone:hover,
.dropzone:focus-visible {
	border-color: var(--pp-brand);
	background: color-mix(in srgb, var(--pp-brand) 9%, transparent);
}

.dropzone__icon {
	display: inline-flex;
	padding: 10px;
	border-radius: 50%;
	background: var(--color-main-background);
	color: var(--pp-brand);
	box-shadow: 0 4px 12px rgba(30, 20, 80, 0.1);
}

.dropzone strong {
	font-size: 15px;
}

.dropzone__hint {
	color: var(--color-text-maxcontrast);
	font-size: 13px;
	font-weight: normal;
	text-align: center;
}

.files {
	display: flex;
	flex-direction: column;
	gap: 6px;
	margin-top: 12px;
}

.file {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 6px 6px 6px 8px;
	border-radius: 10px;
	background: var(--color-background-hover);
}

.file__icon {
	display: inline-flex;
	padding: 5px;
	border-radius: 8px;
}

.file__icon--pdf {
	color: #d93a3a;
	background: color-mix(in srgb, #d93a3a 12%, transparent);
}

.file__icon--image {
	color: #2f80ed;
	background: color-mix(in srgb, #2f80ed 12%, transparent);
}

.file__name {
	flex: 1;
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
	font-weight: 500;
}

.file__size {
	color: var(--color-text-maxcontrast);
	font-size: 12px;
}

.table-select {
	width: 100%;
}

.fields {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin: 12px 0 4px;
}

.fields li {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	padding: 4px 10px 4px 8px;
	border-radius: 999px;
	background: color-mix(in srgb, var(--pp-brand) 8%, var(--color-background-hover));
	font-size: 13px;
	cursor: default;
}

.fields li :deep(svg) {
	color: color-mix(in srgb, var(--pp-brand) 70%, var(--color-text-maxcontrast));
}

.templates__title {
	margin: 18px 0 8px;
	color: var(--color-text-maxcontrast);
	font-size: 13px;
}

.templates {
	display: grid;
	gap: 8px;
}

.template {
	box-sizing: border-box;
	display: flex;
	align-items: center;
	gap: 12px;
	width: 100%;
	margin: 0;
	padding: 10px 12px;
	border: 1px solid var(--color-border);
	border-radius: 12px;
	background: var(--color-main-background);
	color: var(--color-main-text);
	text-align: start;
	cursor: pointer;
	transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s;
}

.template:hover,
.template:focus-visible {
	border-color: var(--pp-brand);
	box-shadow: 0 4px 14px rgba(30, 20, 80, 0.08);
	transform: translateY(-1px);
}

.template__icon {
	display: inline-flex;
	padding: 8px;
	border-radius: 10px;
}

.template__icon--invoice {
	color: var(--pp-brand);
	background: color-mix(in srgb, var(--pp-brand) 13%, transparent);
}

.template__icon--receipt {
	color: var(--pp-brand-2);
	background: color-mix(in srgb, var(--pp-brand-2) 15%, transparent);
}

.template__text {
	display: flex;
	flex: 1;
	flex-direction: column;
	min-width: 0;
}

.template__text span {
	overflow: hidden;
	font-weight: normal;
	color: var(--color-text-maxcontrast);
	font-size: 12px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.template__add {
	color: var(--color-text-maxcontrast);
}

.how {
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	gap: 12px;
	margin: 20px 0;
	padding: 0;
	list-style: none;
	counter-reset: how;
}

.how li {
	display: flex;
	align-items: flex-start;
	gap: 10px;
	padding: 12px 14px;
	border-radius: 12px;
	background: var(--color-background-hover);
	color: var(--color-text-maxcontrast);
	font-size: 13px;
	line-height: 1.45;
}

.how li :deep(svg) {
	flex: none;
	color: var(--pp-brand);
}

.cta {
	position: sticky;
	bottom: 12px;
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 16px;
	padding: 12px 12px 12px 20px;
	border-radius: 16px;
	background: var(--color-main-background);
	border: 1px solid var(--color-border);
	box-shadow: 0 8px 28px rgba(30, 20, 80, 0.1);
}

.cta__summary {
	color: var(--color-text-maxcontrast);
}

.chip-enter-active,
.chip-leave-active {
	transition: opacity 0.2s, transform 0.2s;
}

.chip-enter-from,
.chip-leave-to {
	opacity: 0;
	transform: translateY(-4px);
}

@media (max-width: 900px) {
	.hero,
	.steps,
	.how {
		grid-template-columns: minmax(0, 1fr);
	}

	.hero__art {
		display: none;
	}
}
</style>
