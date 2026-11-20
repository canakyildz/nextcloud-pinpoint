<template>
	<div class="new-extraction">
		<h2>{{ t('pinpoint', 'Extract fields from documents') }}</h2>
		<p class="lead">
			{{ t('pinpoint', 'Pick invoices, receipts or other documents and the table to fill. Every value is shown next to the exact spot in the document it came from, and nothing is saved until you approve it.') }}
		</p>

		<NcNoteCard v-if="store.state && !store.state.textGenerationAvailable" type="error"
			:heading="t('pinpoint', 'No text generation provider')">
			{{ t('pinpoint', 'Pinpoint uses the AI provider configured in Nextcloud. Ask your admin to set one up under Administration → Artificial intelligence, for example the local llm2 app or the OpenAI and LocalAI integration.') }}
		</NcNoteCard>
		<NcNoteCard v-if="store.state?.tablesError" type="error">
			{{ store.state.tablesError }}
		</NcNoteCard>

		<section class="step">
			<h3><span class="step__number">1</span> {{ t('pinpoint', 'Documents') }}</h3>
			<ul v-if="files.length" class="files">
				<li v-for="file in files" :key="file.id">
					<NcIconSvgWrapper :path="file.mime === 'application/pdf' ? mdiFilePdfBox : mdiFileImageOutline" />
					<span class="files__name">{{ file.name }}</span>
					<NcButton variant="tertiary" :aria-label="t('pinpoint', 'Remove {name}', { name: file.name })"
						@click="files = files.filter((f) => f.id !== file.id)">
						<template #icon>
							<NcIconSvgWrapper :path="mdiClose" />
						</template>
					</NcButton>
				</li>
			</ul>
			<NcButton @click="pickFiles">
				<template #icon>
					<NcIconSvgWrapper :path="mdiFolderOpenOutline" />
				</template>
				{{ files.length ? t('pinpoint', 'Add more documents') : t('pinpoint', 'Choose from Files') }}
			</NcButton>
			<p class="hint">
				{{ t('pinpoint', 'PDF files and images (scans, photos). In Files you can also right-click a document and choose “Extract fields”.') }}
			</p>
		</section>

		<section class="step">
			<h3><span class="step__number">2</span> {{ t('pinpoint', 'Table to fill') }}</h3>
			<NcSelect v-model="selectedTable"
				class="table-select"
				:options="tableOptions"
				label="label"
				:input-label="t('pinpoint', 'Table')"
				:placeholder="t('pinpoint', 'Choose a table')"
				:clearable="false" />
			<div class="templates">
				<span class="hint">{{ t('pinpoint', 'Or start a new table:') }}</span>
				<NcButton v-for="template in store.state?.templates ?? []"
					:key="template.id"
					variant="secondary"
					:disabled="creatingTable"
					@click="createTable(template.id, template.name)">
					<template #icon>
						<NcIconSvgWrapper :path="mdiTablePlus" />
					</template>
					{{ template.name === 'Invoice' ? t('pinpoint', 'Invoices') : t('pinpoint', 'Receipts') }}
				</NcButton>
			</div>
			<NcNoteCard v-if="schemaError" type="warning">
				{{ schemaError }}
			</NcNoteCard>
			<div v-else-if="schema" class="schema">
				<p class="hint">
					{{ t('pinpoint', 'Pinpoint will look for one value per column. Column descriptions in Tables tell it what to look for.') }}
				</p>
				<ul class="schema__fields">
					<li v-for="field in schema.fields" :key="field.key" :title="field.description">
						{{ field.label }}
						<span class="schema__type">{{ typeLabel(field.type) }}</span>
					</li>
				</ul>
			</div>
		</section>

		<div class="actions">
			<NcButton variant="primary" :disabled="!canStart" @click="start">
				<template #icon>
					<NcLoadingIcon v-if="starting" :size="20" />
					<NcIconSvgWrapper v-else :path="mdiTextBoxSearchOutline" />
				</template>
				{{ files.length > 1 ? t('pinpoint', 'Extract from {n} documents', { n: files.length }) : t('pinpoint', 'Extract') }}
			</NcButton>
		</div>
	</div>
</template>

<script setup lang="ts">
import {
	mdiClose,
	mdiFileImageOutline,
	mdiFilePdfBox,
	mdiFolderOpenOutline,
	mdiTablePlus,
	mdiTextBoxSearchOutline,
} from '@mdi/js'
import { getFilePickerBuilder, showError, showSuccess } from '@nextcloud/dialogs'
import { t } from '@nextcloud/l10n'
import NcButton from '@nextcloud/vue/components/NcButton'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcLoadingIcon from '@nextcloud/vue/components/NcLoadingIcon'
import NcNoteCard from '@nextcloud/vue/components/NcNoteCard'
import NcSelect from '@nextcloud/vue/components/NcSelect'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage, type FieldType, type FileRef, type Schema } from '../api.ts'
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

function typeLabel(type: FieldType): string {
	return {
		text: t('pinpoint', 'text'),
		number: t('pinpoint', 'number'),
		date: t('pinpoint', 'date'),
		selection: t('pinpoint', 'choice'),
		boolean: t('pinpoint', 'yes/no'),
	}[type]
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
			callback: (nodes) => addFiles(nodes.map((node) => ({ id: node.fileid as number, name: node.basename, mime: node.mime }))),
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
		const title = name === 'Invoice' ? t('pinpoint', 'Invoices') : t('pinpoint', 'Receipts')
		const table = await api.createTable(templateId, title)
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
.new-extraction {
	max-width: 760px;
	margin: 0 auto;
	padding: 24px 24px 64px 56px;
}

h2 {
	margin-top: 8px;
}

.lead {
	color: var(--color-text-maxcontrast);
	margin-bottom: 24px;
}

.step {
	margin-bottom: 28px;
}

.step h3 {
	display: flex;
	align-items: center;
	gap: 8px;
	font-size: 1.1em;
}

.step__number {
	display: inline-flex;
	align-items: center;
	justify-content: center;
	width: 24px;
	height: 24px;
	border-radius: 50%;
	background: var(--color-primary-element);
	color: var(--color-primary-element-text);
	font-size: 0.85em;
	font-weight: bold;
}

.files {
	margin: 8px 0 12px;
}

.files li {
	display: flex;
	align-items: center;
	gap: 8px;
	padding: 2px 0;
}

.files__name {
	flex: 1;
	overflow: hidden;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.hint {
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
	margin-top: 6px;
}

.table-select {
	width: 100%;
	max-width: 420px;
}

.templates {
	display: flex;
	flex-wrap: wrap;
	align-items: center;
	gap: 8px;
	margin: 12px 0;
}

.templates .hint {
	margin: 0 4px 0 0;
}

.schema__fields {
	display: flex;
	flex-wrap: wrap;
	gap: 6px;
	margin-top: 8px;
}

.schema__fields li {
	padding: 4px 10px;
	border-radius: var(--border-radius-pill, 16px);
	background: var(--color-background-dark);
	cursor: default;
}

.schema__type {
	color: var(--color-text-maxcontrast);
	font-size: 0.85em;
	margin-left: 4px;
}

.actions {
	display: flex;
	justify-content: flex-end;
	border-top: 1px solid var(--color-border);
	padding-top: 16px;
}
</style>
