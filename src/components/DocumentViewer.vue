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
			<figcaption class="pp-mono">
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
	gap: 36px;
}

.page {
	position: relative;
	width: 100%;
	margin: 0;
	border-radius: 4px;
	background: #fff;
	box-shadow: 0 0 0 1px var(--pp-border), 0 8px 24px -6px rgba(0, 0, 0, 0.12);
}

.page img {
	position: absolute;
	inset: 0;
	width: 100%;
	height: 100%;
	border-radius: 4px;
	user-select: none;
}

.page figcaption {
	position: absolute;
	top: 100%;
	left: 0;
	padding-top: 8px;
	color: var(--pp-faint);
	font-size: 11px;
}

.mark {
	position: absolute;
	min-width: 0;
	min-height: 0;
	margin: -3px;
	padding: 2px;
	box-sizing: content-box;
	border: 1.5px solid var(--mark-color);
	border-radius: 4px;
	background: color-mix(in srgb, var(--mark-color) 12%, transparent);
	cursor: pointer;
	opacity: 0.65;
	transition: opacity 0.15s, box-shadow 0.15s;
}

.mark:hover,
.mark:focus-visible {
	opacity: 1;
}

.mark--active {
	opacity: 1;
	border-width: 2px;
	background: color-mix(in srgb, var(--mark-color) 18%, transparent);
	box-shadow: 0 0 0 4px color-mix(in srgb, var(--mark-color) 25%, transparent);
	animation: pulse 1.2s ease-out 1;
}

.mark--verified {
	--mark-color: var(--pp-green);
}

.mark--review {
	--mark-color: var(--pp-amber);
}

.mark--unverified,
.mark--missing {
	--mark-color: var(--pp-red);
}

@keyframes pulse {
	from {
		box-shadow: 0 0 0 14px color-mix(in srgb, var(--mark-color) 0%, transparent);
	}
}

@media (prefers-reduced-motion: reduce) {
	.mark--active {
		animation: none;
	}
}
</style>
