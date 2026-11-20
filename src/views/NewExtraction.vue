<template>
	<div class="new">
		<section class="hero">
			<div class="hero__main">
				<div class="hero__text">
					<span class="hero__eyebrow pp-mono">
						<NcIconSvgWrapper :path="mdiCrosshairsGps" :size="14" />
						Pinpoint
					</span>
					<h2>{{ t('pinpoint', 'Turn documents into table rows you can trust') }}</h2>
					<p>
						{{ t('pinpoint', 'Every value is shown on the page it came from. Pinpoint only marks a value verified when the document says exactly that, and nothing is saved until you approve it.') }}
					</p>
				</div>
				<HeroPreview class="hero__preview" />
			</div>
			<ol class="how">
				<li v-for="(item, i) in how" :key="item.title">
					<span class="how__num pp-mono">{{ String(i + 1).padStart(2, '0') }}</span>
					<strong>{{ item.title }}</strong>
					<span>{{ item.text }}</span>
				</li>
			</ol>
		</section>

		<NcNoteCard v-if="store.state && !store.state.textGenerationAvailable" type="error"
			:heading="t('pinpoint', 'No AI provider yet')">
			{{ t('pinpoint', 'Pinpoint uses the AI provider configured in Nextcloud. Ask your admin to set one up under Administration → Artificial intelligence, for example the local llm2 app or the OpenAI and LocalAI integration.') }}
		</NcNoteCard>
		<NcNoteCard v-if="store.state?.tablesError" type="error">
			{{ store.state.tablesError }}
		</NcNoteCard>

		<ol class="steps">
			<li class="step" :class="{ 'step--done': files.length > 0 }">
				<span class="step__num pp-mono">
					<NcIconSvgWrapper v-if="files.length" :path="mdiCheck" :size="14" />
					<template v-else>1</template>
				</span>
				<div class="step__body">
					<h3>{{ t('pinpoint', 'Documents') }}</h3>
					<p class="step__hint">
						{{ t('pinpoint', 'PDFs, scans and photos') }}
					</p>
					<div class="box">
						<button type="button" class="dropzone" :class="{ 'dropzone--compact': files.length }" @click="pickFiles">
							<span class="dropzone__icon">
								<NcIconSvgWrapper :path="mdiTrayArrowUp" :size="20" />
							</span>
							<strong>{{ files.length ? t('pinpoint', 'Add more documents') : t('pinpoint', 'Choose from Files') }}</strong>
							<span class="dropzone__hint">{{ t('pinpoint', 'or right-click a document in Files and choose “Extract fields”') }}</span>
						</button>
						<TransitionGroup v-if="files.length" tag="ul" name="row" class="files">
							<li v-for="file in files" :key="file.id" class="file">
								<NcIconSvgWrapper :path="file.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileImageOutline" :size="18" class="file__icon" />
								<span class="file__name">{{ file.name }}</span>
								<span v-if="file.size" class="file__size pp-mono">{{ formatSize(file.size) }}</span>
								<NcButton variant="tertiary-no-background"
									size="small"
									:aria-label="t('pinpoint', 'Remove {name}', { name: file.name })"
									@click="files = files.filter((f) => f.id !== file.id)">
									<template #icon>
										<NcIconSvgWrapper :path="mdiClose" :size="16" />
									</template>
								</NcButton>
							</li>
						</TransitionGroup>
					</div>
				</div>
			</li>

			<li class="step" :class="{ 'step--done': schema !== null }">
				<span class="step__num pp-mono">
					<NcIconSvgWrapper v-if="schema" :path="mdiCheck" :size="14" />
					<template v-else>2</template>
				</span>
				<div class="step__body">
					<h3>{{ t('pinpoint', 'Table to fill') }}</h3>
					<p class="step__hint">
						{{ t('pinpoint', 'Its columns are what Pinpoint looks for. Column descriptions are passed to the model.') }}
					</p>
					<div class="box">
						<div class="box__body">
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
									<NcIconSvgWrapper :path="typeIcon(field.type)" :size="14" />
									{{ field.label }}
								</li>
							</ul>
							<p v-if="!tableOptions.length" class="box__empty">
								{{ t('pinpoint', 'You have no tables yet. Start with one made for it:') }}
							</p>
						</div>
						<div class="box__footer">
							<p v-if="tableOptions.length" class="box__footer-title">
								{{ t('pinpoint', 'Or start a new table from a template') }}
							</p>
							<button v-for="template in store.state?.templates ?? []"
								:key="template.id"
								type="button"
								class="template"
								:disabled="creatingTable"
								@click="createTable(template.id, template.name)">
								<span class="template__icon">
									<NcIconSvgWrapper :path="template.name === 'Invoice' ? mdiFileDocumentOutline : mdiReceiptTextOutline" :size="18" />
								</span>
								<span class="template__text">
									<strong>{{ templateTitle(template.name) }}</strong>
									<span>{{ template.fields.map((f) => f.label).slice(0, 5).join(' · ') }}</span>
								</span>
								<span class="template__add">
									{{ t('pinpoint', 'Create') }}
									<NcIconSvgWrapper :path="mdiArrowRight" :size="14" />
								</span>
							</button>
						</div>
					</div>
				</div>
			</li>

			<li class="step step--last">
				<span class="step__num pp-mono">3</span>
				<div class="step__body">
					<div class="box cta">
						<p class="cta__summary">
							<template v-if="files.length && selectedTable">
								{{ n('pinpoint', '{n} document into {table}', '{n} documents into {table}', files.length, { n: files.length, table: selectedTable.label }) }}
							</template>
							<template v-else>
								{{ t('pinpoint', 'Choose documents and a table to start.') }}
							</template>
						</p>
						<NcButton variant="primary" :disabled="!canStart" @click="start">
							<template #icon>
								<NcLoadingIcon v-if="starting" :size="18" />
								<NcIconSvgWrapper v-else :path="mdiArrowRight" :size="18" />
							</template>
							{{ t('pinpoint', 'Extract') }}
						</NcButton>
					</div>
				</div>
			</li>
		</ol>
	</div>
</template>

<script setup lang="ts">
import {
	mdiArrowRight,
	mdiCalendarBlankOutline,
	mdiCheck,
	mdiClose,
	mdiCrosshairsGps,
	mdiFileDocumentOutline,
	mdiFileImageOutline,
	mdiFilePdfBox,
	mdiFormatListBulleted,
	mdiFormatText,
	mdiPound,
	mdiReceiptTextOutline,
	mdiToggleSwitchOutline,
	mdiTrayArrowUp,
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
import HeroPreview from '../components/HeroPreview.vue'
import { refreshState, store, upsertJob } from '../store.ts'

const SUPPORTED_MIMES = ['application/pdf', 'image/png', 'image/jpeg', 'image/tiff', 'image/webp']
const LAST_TABLE_KEY = 'pinpoint:lastTable'

interface TableOption { id: number, label: string }

const how = [
	{ title: t('pinpoint', 'Read'), text: t('pinpoint', 'Every word and where it is on the page. Scans go through OCR.') },
	{ title: t('pinpoint', 'Propose'), text: t('pinpoint', 'Your Nextcloud’s AI suggests each value and quotes the text it read.') },
	{ title: t('pinpoint', 'Verify'), text: t('pinpoint', 'Each value is checked against the page before you see it.') },
]

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
	max-width: 920px;
	margin: 0 auto;
	padding: 24px 32px 48px 56px;
}

/* Hero: a fine grid that fades out, the headline, and a picture of the review screen. */
.hero {
	position: relative;
	overflow: hidden;
	margin-bottom: 40px;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
}

.hero::before {
	content: '';
	position: absolute;
	inset: 0;
	background-image:
		linear-gradient(to right, color-mix(in srgb, var(--pp-fg) 6%, transparent) 1px, transparent 1px),
		linear-gradient(to bottom, color-mix(in srgb, var(--pp-fg) 6%, transparent) 1px, transparent 1px);
	background-size: 28px 28px;
	mask-image: radial-gradient(ellipse 65% 90% at 78% 30%, #000 20%, transparent 75%);
	pointer-events: none;
}

.hero__main {
	position: relative;
	display: grid;
	grid-template-columns: minmax(0, 1.2fr) minmax(240px, 1fr);
	align-items: center;
	gap: 32px;
	padding: 40px 36px 36px 40px;
}

.hero__eyebrow {
	display: inline-flex;
	align-items: center;
	gap: 6px;
	height: 24px;
	padding: 0 10px;
	border: 1px solid var(--pp-border);
	border-radius: 999px;
	background: var(--pp-bg);
	color: var(--pp-muted);
	font-size: 12px;
}

.hero h2 {
	margin: 16px 0 12px;
	font-size: 34px;
	font-weight: 600;
	line-height: 1.1;
	letter-spacing: -0.045em;
}

.hero p {
	max-width: 460px;
	color: var(--pp-muted);
	font-size: 15px;
	line-height: 1.6;
}

.hero__preview {
	justify-self: end;
}

.how {
	position: relative;
	display: grid;
	grid-template-columns: repeat(3, minmax(0, 1fr));
	margin: 0;
	padding: 0;
	border-top: 1px solid var(--pp-border);
	background: var(--pp-bg-2);
	list-style: none;
}

.how li {
	display: flex;
	flex-direction: column;
	gap: 2px;
	padding: 16px 20px 18px;
	font-size: 13px;
	line-height: 1.5;
}

.how li + li {
	border-left: 1px solid var(--pp-border);
}

.how__num {
	margin-bottom: 4px;
	color: var(--pp-faint);
	font-size: 11px;
}

.how strong {
	font-weight: 600;
}

.how li > span:last-child {
	color: var(--pp-muted);
}

/* Steps: numbered circles joined by a line, each with its box. */
.steps {
	margin: 0;
	padding: 0;
	list-style: none;
}

.step {
	position: relative;
	display: flex;
	gap: 20px;
	padding-bottom: 32px;
}

.step:not(.step--last)::before {
	content: '';
	position: absolute;
	top: 32px;
	bottom: 4px;
	left: 13.5px;
	width: 1px;
	background: var(--pp-border);
}

.step__num {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	flex: none;
	width: 28px;
	height: 28px;
	border: 1px solid var(--pp-border-strong);
	border-radius: 50%;
	background: var(--pp-bg);
	color: var(--pp-muted);
	font-size: 13px;
	transition: background 0.2s, color 0.2s, border-color 0.2s;
}

.step--done .step__num {
	border-color: var(--pp-fg);
	background: var(--pp-fg);
	color: var(--pp-bg);
}

.step__body {
	flex: 1;
	min-width: 0;
	padding-top: 3px;
}

.step__body h3 {
	margin: 0;
	font-size: 16px;
	font-weight: 600;
}

.step__hint {
	margin: 2px 0 12px;
	color: var(--pp-muted);
	font-size: 14px;
}

.box {
	overflow: hidden;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
	box-shadow: var(--pp-shadow);
}

.box__body {
	padding: 16px;
}

.box__empty {
	color: var(--pp-muted);
	font-size: 14px;
}

.box__footer {
	padding: 12px 16px 14px;
	border-top: 1px solid var(--pp-border);
	background: var(--pp-bg-2);
}

.box__footer-title {
	margin-bottom: 8px;
	color: var(--pp-muted);
	font-size: 13px;
}

.box .dropzone {
	box-sizing: border-box;
	display: flex;
	flex-direction: column;
	align-items: center;
	gap: 4px;
	width: calc(100% - 24px);
	min-height: 0;
	margin: 12px;
	padding: 24px 16px;
	border: 1px dashed var(--pp-border-strong);
	border-radius: 8px;
	background: var(--pp-bg-2);
	color: var(--pp-fg);
	font-weight: normal;
	cursor: pointer;
	transition: background 0.15s, border-color 0.15s;
}

.dropzone:hover,
.dropzone:focus-visible {
	border-color: var(--pp-fg);
	background: var(--pp-bg-3);
}

.dropzone__icon {
	display: inline-flex;
	margin-bottom: 6px;
	padding: 8px;
	border: 1px solid var(--pp-border);
	border-radius: 50%;
	background: var(--pp-bg);
	color: var(--pp-fg);
}

.dropzone strong {
	font-size: 14px;
	font-weight: 600;
}

.dropzone__hint {
	color: var(--pp-muted);
	font-size: 13px;
	text-align: center;
}

/* Once documents are chosen, the drop zone shrinks to a single line above the list. */
.box .dropzone--compact {
	flex-direction: row;
	gap: 10px;
	padding: 8px 12px;
}

.dropzone--compact .dropzone__icon {
	margin-bottom: 0;
	padding: 5px;
}

.dropzone--compact .dropzone__hint {
	overflow: hidden;
	text-align: start;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.files {
	border-top: 1px solid var(--pp-border);
}

.file {
	display: flex;
	align-items: center;
	gap: 10px;
	padding: 6px 8px 6px 16px;
	font-size: 14px;
}

.file + .file {
	border-top: 1px solid var(--pp-border);
}

.file__icon {
	color: var(--pp-muted);
}

.file__name {
	flex: 1;
	min-width: 0;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.file__size {
	color: var(--pp-faint);
	font-size: 12px;
}

.table-select {
	width: 100%;
}

.fields {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 12px;
}

.fields li {
	display: inline-flex;
	align-items: center;
	gap: 5px;
	height: 24px;
	padding: 0 8px;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius);
	background: var(--pp-bg-2);
	font-size: 12.5px;
	cursor: default;
}

.fields li :deep(svg) {
	color: var(--pp-faint);
}

.box__footer .template {
	box-sizing: border-box;
	display: flex;
	align-items: center;
	gap: 12px;
	width: 100%;
	min-height: 0;
	margin: 0;
	padding: 8px 10px;
	border: 1px solid transparent;
	border-radius: 8px;
	background: transparent;
	color: var(--pp-fg);
	font-weight: normal;
	text-align: start;
	cursor: pointer;
	transition: background 0.15s, border-color 0.15s;
}

.box__footer .template + .template {
	margin-top: 2px;
}

.template:hover,
.template:focus-visible {
	border-color: var(--pp-border);
	background: var(--pp-bg);
}

.template__icon {
	display: inline-flex;
	padding: 6px;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius);
	background: var(--pp-bg);
	color: var(--pp-fg);
}

.template__text {
	display: flex;
	flex: 1;
	flex-direction: column;
	min-width: 0;
	font-size: 14px;
}

.template__text strong {
	font-weight: 500;
}

.template__text span {
	overflow: hidden;
	color: var(--pp-muted);
	font-size: 12.5px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.template__add {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	color: var(--pp-muted);
	font-size: 13px;
}

.template:hover .template__add {
	color: var(--pp-fg);
}

/* The last step stays in view at the bottom while the steps above it scroll. */
.step--last {
	position: sticky;
	bottom: 0;
	z-index: 1;
	padding: 12px 0 16px;
	background: linear-gradient(to bottom, transparent, var(--pp-bg) 14px);
}

.step--last .step__num {
	margin-top: 14px;
}

.cta {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 16px;
	padding: 12px 12px 12px 18px;
	box-shadow: var(--pp-shadow-lg);
}

.cta__summary {
	color: var(--pp-muted);
	font-size: 14px;
}

.row-enter-active,
.row-leave-active {
	transition: opacity 0.2s;
}

.row-enter-from,
.row-leave-to {
	opacity: 0;
}

@media (max-width: 900px) {
	.new {
		padding-left: 48px;
	}

	.hero__main,
	.how {
		grid-template-columns: minmax(0, 1fr);
	}

	.how li + li {
		border-top: 1px solid var(--pp-border);
		border-left: 0;
	}

	.hero__preview {
		display: none;
	}
}
</style>
