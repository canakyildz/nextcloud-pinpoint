<template>
	<div class="field"
		:class="[`field--${statusInfo.tone}`, `field--${spec.type}`, { 'field--selected': selected }]"
		@click="emit('select')"
		@focusin="emit('select')">
		<div class="field__head">
			<span class="field__type" :title="typeLabel">
				<NcIconSvgWrapper :path="typeIcon" :size="14" />
			</span>
			<span class="field__label">
				{{ spec.label }}<span v-if="spec.required" class="field__required" :title="t('pinpoint', 'Required')">*</span>
			</span>
			<span class="pp-badge" :class="`pp-badge--${statusInfo.tone}`" :title="statusInfo.hint">
				<span class="pp-dot" :class="`pp-dot--${statusInfo.tone}`" />
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

		<div v-if="result?.anchor && !edited" class="quote pp-mono">
			<span class="quote__page">{{ t('pinpoint', 'p.{n}', { n: result.anchor.page + 1 }) }}</span>
			<span class="quote__text">“{{ result.anchor.matched_text }}”</span>
		</div>
		<ul v-if="reasons.length" class="reasons">
			<li v-for="reason in reasons" :key="reason">
				{{ reason }}
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import {
	mdiCalendarBlankOutline,
	mdiFormatListBulleted,
	mdiFormatText,
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
const status = computed(() => props.result?.status ?? 'missing')
const statusInfo = computed(() => (edited.value
	? { label: t('pinpoint', 'Edited'), hint: t('pinpoint', 'You changed this value. It will be saved as entered by you.'), tone: 'blue' }
	: FIELD_STATUS[status.value]))
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
	--tone: var(--pp-gray);
	--tone-text: var(--pp-muted);
	position: relative;
	padding: 14px 16px 16px;
	cursor: pointer;
	transition: background 0.15s;
}

.field + .field {
	border-top: 1px solid var(--pp-border);
}

.field:hover {
	background: var(--pp-bg-2);
}

.field--selected {
	background: var(--pp-bg-2);
}

.field--selected::before {
	content: '';
	position: absolute;
	top: -1px;
	bottom: 0;
	left: 0;
	width: 2px;
	background: var(--tone);
}

.field--green { --tone: var(--pp-green); --tone-text: var(--pp-green-text); }
.field--amber { --tone: var(--pp-amber); --tone-text: var(--pp-amber-text); }
.field--red { --tone: var(--pp-red); --tone-text: var(--pp-red-text); }
.field--blue { --tone: var(--pp-blue); --tone-text: var(--pp-blue-text); }

.field__head {
	display: flex;
	align-items: center;
	gap: 8px;
	margin-bottom: 8px;
}

.field__type {
	display: inline-flex;
	color: var(--pp-faint);
}

.field__label {
	flex: 1;
	min-width: 0;
	font-size: 14px;
	font-weight: 500;
}

.field__required {
	margin-left: 2px;
	color: var(--pp-faint);
}

/* Values are data: mono, like the quote they came from. */
.field--text :deep(input),
.field--number :deep(input),
.field--date :deep(input) {
	font-family: var(--pp-mono);
	font-size: 13.5px;
}

.quote {
	display: flex;
	align-items: baseline;
	gap: 8px;
	margin-top: 10px;
	color: var(--pp-muted);
	font-size: 12px;
	line-height: 1.5;
}

.quote__page {
	flex: none;
	padding: 0 5px;
	border: 1px solid var(--pp-border);
	border-radius: 4px;
	background: var(--pp-bg);
	color: var(--pp-faint);
	font-size: 11px;
}

.quote__text {
	min-width: 0;
	overflow-wrap: anywhere;
}

.reasons {
	margin-top: 8px;
	padding-left: 0;
	list-style: none;
}

.reasons li {
	position: relative;
	padding-left: 14px;
	color: var(--tone-text);
	font-size: 13px;
	line-height: 1.45;
}

.reasons li::before {
	content: '';
	position: absolute;
	top: 0.6em;
	left: 2px;
	width: 5px;
	height: 1px;
	background: currentColor;
}

.reasons li + li {
	margin-top: 2px;
}

.field--green .reasons li {
	color: var(--pp-muted);
}
</style>
