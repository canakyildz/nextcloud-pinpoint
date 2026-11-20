<template>
	<div class="preview" aria-hidden="true">
		<div class="preview__head">
			<span class="preview__file pp-mono">invoice-07.pdf</span>
			<span class="pp-badge pp-badge--amber"><span class="pp-dot pp-dot--amber" />{{ t('pinpoint', '1 to check') }}</span>
		</div>
		<div v-for="row in rows" :key="row.label" class="row">
			<span class="row__label">{{ row.label }}</span>
			<span class="row__value pp-mono" :class="{ 'row__value--flag': row.tone === 'amber' }">{{ row.value }}</span>
			<span class="pp-dot" :class="`pp-dot--${row.tone}`" />
			<span v-if="row.quote" class="row__quote pp-mono">
				<span class="row__page">p.1</span>“{{ row.quote }}”
			</span>
		</div>
	</div>
</template>

<script setup lang="ts">
import { t } from '@nextcloud/l10n'

// A small, static picture of the review screen: the story from the README, where a model read
// "416,10 €" as 4161 and the quote gave it away.
const rows = [
	{ label: t('pinpoint', 'Invoice number'), value: 'RE-2026-0412', tone: 'green', quote: 'Rechnung Nr. RE-2026-0412' },
	{ label: t('pinpoint', 'Net amount'), value: '2,190.00', tone: 'green', quote: '' },
	{ label: t('pinpoint', 'Tax amount'), value: '4161', tone: 'amber', quote: 'MwSt. 19 %: 416,10 €' },
	{ label: t('pinpoint', 'Total'), value: '2,606.10', tone: 'green', quote: '' },
]
</script>

<style scoped>
.preview {
	width: 100%;
	max-width: 340px;
	overflow: hidden;
	border: 1px solid var(--pp-border);
	border-radius: var(--pp-radius-lg);
	background: var(--pp-bg);
	box-shadow: var(--pp-shadow-lg);
	font-size: 12.5px;
}

.preview__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	padding: 10px 14px;
	border-bottom: 1px solid var(--pp-border);
	background: var(--pp-bg-2);
}

.preview__file {
	overflow: hidden;
	font-size: 12px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.row {
	display: grid;
	grid-template-columns: minmax(0, 1fr) auto 8px;
	align-items: center;
	gap: 4px 10px;
	padding: 9px 14px;
}

.row + .row {
	border-top: 1px solid var(--pp-border);
}

.row__label {
	color: var(--pp-muted);
}

.row__value {
	font-weight: 500;
}

.row__value--flag {
	color: var(--pp-amber-text);
}

.row__quote {
	grid-column: 1 / -1;
	overflow: hidden;
	color: var(--pp-muted);
	font-size: 11.5px;
	text-overflow: ellipsis;
	white-space: nowrap;
}

.row__page {
	margin-right: 6px;
	padding: 1px 4px;
	border: 1px solid var(--pp-border);
	border-radius: 4px;
	color: var(--pp-faint);
	font-size: 10.5px;
}
</style>
