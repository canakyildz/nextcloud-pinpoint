<template>
	<div ref="container" class="viewer">
		<figure v-for="page in pages"
			:key="page.index"
			class="page"
			:style="{ aspectRatio: `${page.width} / ${page.height}` }">
			<img :src="api.pageUrl(jobId, page.index)"
				:alt="t('pinpoint', 'Page {n}', { n: page.index + 1 })"
				loading="lazy">
			<button v-for="mark in marks.filter((m) => m.page === page.index)"
				:key="mark.id"
				type="button"
				class="mark"
				:class="[`mark--${mark.status}`, { 'mark--active': mark.key === selectedKey }]"
				:style="mark.style"
				:data-key="mark.key"
				:aria-label="mark.label"
				:title="mark.label"
				@click="emit('select', mark.key)" />
			<figcaption>
				{{ t('pinpoint', 'Page {n} of {total}', { n: page.index + 1, total: pages.length }) }}
				<span v-if="page.source === 'ocr'"> · {{ t('pinpoint', 'scanned, read with OCR') }}</span>
			</figcaption>
		</figure>
	</div>
</template>

<script setup lang="ts">
import { t } from '@nextcloud/l10n'
import { computed, nextTick, ref, watch } from 'vue'
import { api, type Extraction, type FieldResult, type FieldSpec } from '../api.ts'

const props = defineProps<{
	jobId: string
	pages: Extraction['pages']
	fields: FieldResult[]
	specs: FieldSpec[]
	selectedKey: string | null
}>()

const emit = defineEmits<{ select: [key: string] }>()

const container = ref<HTMLElement | null>(null)

// Highlights come only from the document's own word positions (computed on the server),
// never from the model.
const marks = computed(() => props.fields.flatMap((field) => {
	const label = props.specs.find((s) => s.key === field.key)?.label ?? field.key
	return (field.anchor?.boxes ?? []).map((box, i) => ({
		id: `${field.key}-${i}`,
		key: field.key,
		page: box.page,
		status: field.status,
		label: `${label}: ${field.value ?? ''}`,
		style: {
			left: `${box.x0 * 100}%`,
			top: `${box.y0 * 100}%`,
			width: `${(box.x1 - box.x0) * 100}%`,
			height: `${(box.y1 - box.y0) * 100}%`,
		},
	}))
}))

watch(() => props.selectedKey, async (key) => {
	if (!key) return
	await nextTick()
	const element = container.value?.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)
	element?.scrollIntoView({ block: 'center', behavior: 'smooth' })
})
</script>

<style scoped>
.viewer {
	display: flex;
	flex-direction: column;
	gap: 16px;
}

.page {
	position: relative;
	width: 100%;
	margin: 0;
	background: #fff;
	box-shadow: 0 1px 6px var(--color-box-shadow);
	border-radius: var(--border-radius);
}

.page img {
	position: absolute;
	inset: 0;
	width: 100%;
	height: 100%;
	border-radius: var(--border-radius);
	user-select: none;
}

.page figcaption {
	position: absolute;
	top: 100%;
	left: 0;
	padding-top: 2px;
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
}

.mark {
	position: absolute;
	min-width: 0;
	min-height: 0;
	margin: -2px;
	padding: 2px;
	box-sizing: content-box;
	border: 2px solid var(--mark-color);
	border-radius: 3px;
	background: color-mix(in srgb, var(--mark-color) 14%, transparent);
	cursor: pointer;
	opacity: 0.7;
	transition: opacity 0.15s, box-shadow 0.15s;
}

.mark:hover,
.mark:focus-visible {
	opacity: 1;
}

.mark--active {
	opacity: 1;
	box-shadow: 0 0 0 4px color-mix(in srgb, var(--mark-color) 35%, transparent);
	animation: pulse 1.2s ease-out 1;
}

.mark--verified {
	--mark-color: var(--color-element-success, #099f05);
}

.mark--review {
	--mark-color: var(--color-element-warning, #bf7900);
}

.mark--unverified,
.mark--missing {
	--mark-color: var(--color-element-error, #c90000);
}

@keyframes pulse {
	from {
		box-shadow: 0 0 0 12px color-mix(in srgb, var(--mark-color) 0%, transparent);
	}
}
</style>
