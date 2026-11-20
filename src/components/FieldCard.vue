<template>
	<div class="field"
		:class="[`field--${status}`, { 'field--selected': selected }]"
		@click="emit('select')"
		@focusin="emit('select')">
		<div class="field__head">
			<span class="field__type" :title="typeLabel">
				<NcIconSvgWrapper :path="typeIcon" :size="16" />
			</span>
			<span class="field__label">
				{{ spec.label }}<span v-if="spec.required" class="field__required" :title="t('pinpoint', 'Required')">*</span>
			</span>
			<span class="badge" :title="statusInfo.hint">
				<NcIconSvgWrapper :path="statusInfo.icon" :size="15" />
				{{ statusInfo.label }}
			</span>
		</div>

		<NcSelect v-if="spec.type === 'selection'"
			:model-value="stringValue || null"
			:options="spec.options"
			:input-label="spec.label"
			label-outside
			:disabled="readonly"
			@update:model-value="(v: string | null) => emit('update:modelValue', v ?? '')" />
		<NcCheckboxRadioSwitch v-else-if="spec.type === 'boolean'"
			:model-value="modelValue === true || modelValue === 'true'"
			type="switch"
			:disabled="readonly"
			@update:model-value="(v: boolean) => emit('update:modelValue', v)">
			{{ modelValue === true || modelValue === 'true' ? t('pinpoint', 'Yes') : t('pinpoint', 'No') }}
		</NcCheckboxRadioSwitch>
		<NcDateTimePickerNative v-else-if="spec.type === 'date'"
			:id="`field-${spec.key}`"
			:model-value="dateValue"
			type="date"
			:label="spec.label"
			hide-label
			:disabled="readonly"
			@update:model-value="(d: Date | null) => emit('update:modelValue', d ? isoDate(d) : '')" />
		<NcTextField v-else
			:model-value="stringValue"
			:label="spec.label"
			label-outside
			:placeholder="status === 'missing' ? t('pinpoint', 'Not in the document') : ''"
			:inputmode="spec.type === 'number' ? 'decimal' : undefined"
			:disabled="readonly"
			@update:model-value="(v: string | number) => emit('update:modelValue', String(v))" />

		<div v-if="result?.anchor && !edited" class="quote">
			<span class="quote__page">{{ t('pinpoint', 'p. {n}', { n: result.anchor.page + 1 }) }}</span>
			<span class="quote__text">{{ result.anchor.matched_text }}</span>
		</div>
		<ul v-if="reasons.length" class="reasons">
			<li v-for="reason in reasons" :key="reason">
				<svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true"><path :d="mdiInformationOutline" fill="currentColor" /></svg>
				<span>{{ reason }}</span>
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import {
	mdiCalendarBlankOutline,
	mdiFormatListBulleted,
	mdiFormatText,
	mdiInformationOutline,
	mdiPencilOutline,
	mdiPound,
	mdiToggleSwitchOutline,
} from '@mdi/js'
import { t } from '@nextcloud/l10n'
import NcCheckboxRadioSwitch from '@nextcloud/vue/components/NcCheckboxRadioSwitch'
import NcDateTimePickerNative from '@nextcloud/vue/components/NcDateTimePickerNative'
import NcIconSvgWrapper from '@nextcloud/vue/components/NcIconSvgWrapper'
import NcSelect from '@nextcloud/vue/components/NcSelect'
import NcTextField from '@nextcloud/vue/components/NcTextField'
import { computed } from 'vue'
import type { FieldResult, FieldSpec } from '../api.ts'
import { FIELD_STATUS } from '../status.ts'

export type FormValue = string | boolean | null

const props = defineProps<{
	spec: FieldSpec
	result: FieldResult | undefined
	modelValue: FormValue
	original: FormValue
	selected: boolean
	readonly: boolean
}>()

const emit = defineEmits<{ 'update:modelValue': [value: FormValue], select: [] }>()

const TYPES = {
	text: { icon: mdiFormatText, label: t('pinpoint', 'Text') },
	number: { icon: mdiPound, label: t('pinpoint', 'Number') },
	date: { icon: mdiCalendarBlankOutline, label: t('pinpoint', 'Date') },
	selection: { icon: mdiFormatListBulleted, label: t('pinpoint', 'Choice') },
	boolean: { icon: mdiToggleSwitchOutline, label: t('pinpoint', 'Yes or no') },
}

const typeIcon = computed(() => TYPES[props.spec.type].icon)
const typeLabel = computed(() => TYPES[props.spec.type].label)
const edited = computed(() => String(props.modelValue ?? '') !== String(props.original ?? ''))
const status = computed(() => (edited.value ? 'edited' : props.result?.status ?? 'missing'))
const statusInfo = computed(() => (edited.value
	? { label: t('pinpoint', 'Edited'), hint: t('pinpoint', 'You changed this value. It will be saved as entered by you.'), icon: mdiPencilOutline }
	: FIELD_STATUS[props.result?.status ?? 'missing']))
const reasons = computed(() => (edited.value || props.result?.status === 'missing' ? [] : props.result?.reasons ?? []))
const stringValue = computed(() => (props.modelValue === null ? '' : String(props.modelValue)))
const dateValue = computed(() => {
	const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(stringValue.value)
	return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : null
})

function isoDate(date: Date): string {
	const pad = (n: number) => String(n).padStart(2, '0')
	return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}
</script>

<style scoped>
.field {
	--status-color: var(--color-text-maxcontrast);
	--status-text: var(--color-text-maxcontrast);
	padding: 12px 14px 14px;
	border: 1px solid var(--color-border);
	border-radius: 14px;
	background: var(--color-main-background);
	box-shadow: 0 1px 2px rgba(0, 0, 0, 0.03);
	cursor: pointer;
	transition: box-shadow 0.15s, border-color 0.15s, transform 0.15s;
}

.field:hover {
	box-shadow: 0 4px 16px rgba(30, 20, 80, 0.07);
}

.field--selected {
	border-color: var(--status-color);
	box-shadow: 0 0 0 3px color-mix(in srgb, var(--status-color) 22%, transparent), 0 6px 20px rgba(30, 20, 80, 0.08);
	transform: translateY(-1px);
}

.field--verified {
	--status-color: var(--color-element-success, #099f05);
	--status-text: var(--color-success-text, #005416);
}

.field--review {
	--status-color: var(--color-element-warning, #bf7900);
	--status-text: var(--color-warning-text, #664700);
}

.field--unverified {
	--status-color: var(--color-element-error, #c90000);
	--status-text: var(--color-error-text, #8a0000);
}

.field--edited {
	--status-color: var(--color-primary-element);
	--status-text: var(--color-primary-element);
}

.field__head {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 8px;
}

.field__type {
	display: inline-flex;
	padding: 4px;
	border-radius: 8px;
	background: var(--color-background-hover);
	color: var(--color-text-maxcontrast);
}

.field__label {
	flex: 1;
	min-width: 0;
	font-weight: 600;
}

.field__required {
	margin-left: 2px;
	color: var(--color-text-maxcontrast);
}

.badge {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	padding: 2px 9px 2px 7px;
	border-radius: 999px;
	color: var(--status-text);
	background: color-mix(in srgb, var(--status-color) 13%, transparent);
	font-size: 12px;
	font-weight: 600;
	white-space: nowrap;
}

.quote {
	display: flex;
	align-items: baseline;
	gap: 8px;
	margin-top: 10px;
	padding: 6px 10px;
	border-left: 3px solid var(--status-color);
	border-radius: 0 8px 8px 0;
	background: color-mix(in srgb, var(--status-color) 6%, var(--color-background-hover));
	font-size: 13px;
}

.quote__page {
	flex: none;
	padding: 0 6px;
	border-radius: 6px;
	background: var(--color-main-background);
	color: var(--color-text-maxcontrast);
	font-size: 11px;
	font-weight: 700;
	text-transform: uppercase;
	letter-spacing: 0.03em;
}

.quote__text {
	overflow-wrap: anywhere;
	font-size: 13px;
}

.quote__text::before {
	content: '“';
	color: var(--color-text-maxcontrast);
}

.quote__text::after {
	content: '”';
	color: var(--color-text-maxcontrast);
}

.reasons {
	margin-top: 8px;
}

.reasons li {
	display: flex;
	align-items: flex-start;
	gap: 6px;
	padding-left: 2px;
	color: var(--status-text);
	font-size: 12.5px;
	line-height: 1.4;
}

.field--verified .reasons li {
	color: var(--color-text-maxcontrast);
}

.reasons svg {
	flex: none;
	margin-top: 2px;
}
</style>
