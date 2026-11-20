<template>
	<div class="trust">
		<div class="trust__bar" role="img" :aria-label="label">
			<span v-for="part in parts"
				:key="part.status"
				class="trust__part"
				:class="`trust__part--${part.status}`"
				:style="{ flexGrow: part.count }" />
		</div>
		<ul class="trust__legend">
			<li v-for="part in parts" :key="part.status" :class="`trust__item--${part.status}`">
				<span class="trust__dot" />
				<strong>{{ part.count }}</strong> {{ part.label }}
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { t } from '@nextcloud/l10n'
import { computed } from 'vue'
import type { FieldStatus } from '../api.ts'

const props = defineProps<{ summary: Record<FieldStatus, number> }>()

const parts = computed(() => [
	{ status: 'verified', count: props.summary.verified, label: t('pinpoint', 'verified') },
	{ status: 'review', count: props.summary.review, label: t('pinpoint', 'to check') },
	{ status: 'unverified', count: props.summary.unverified, label: t('pinpoint', 'not found') },
	{ status: 'missing', count: props.summary.missing, label: t('pinpoint', 'empty') },
].filter((p) => p.count > 0))

const label = computed(() => parts.value.map((p) => `${p.count} ${p.label}`).join(', '))
</script>

<style scoped>
.trust__bar {
	display: flex;
	gap: 3px;
	height: 10px;
	border-radius: 5px;
	overflow: hidden;
}

.trust__part {
	flex-basis: 0;
	min-width: 6px;
	transition: flex-grow 0.4s ease;
}

.trust__part--verified,
.trust__item--verified .trust__dot {
	background: var(--color-element-success, #099f05);
}

.trust__part--review,
.trust__item--review .trust__dot {
	background: var(--color-element-warning, #bf7900);
}

.trust__part--unverified,
.trust__item--unverified .trust__dot {
	background: var(--color-element-error, #c90000);
}

.trust__part--missing,
.trust__item--missing .trust__dot {
	background: var(--color-border-dark, #bbb);
}

.trust__legend {
	display: flex;
	flex-wrap: wrap;
	gap: 4px 16px;
	margin-top: 8px;
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
}

.trust__legend li {
	display: inline-flex;
	align-items: center;
	gap: 6px;
}

.trust__legend strong {
	color: var(--color-main-text);
}

.trust__dot {
	width: 8px;
	height: 8px;
	border-radius: 50%;
}
</style>
