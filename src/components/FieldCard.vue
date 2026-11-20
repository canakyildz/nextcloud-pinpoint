<template>
	<div class="field"
		:class="[`field--${status}`, { 'field--selected': selected }]"
		@click="emit('select')"
		@focusin="emit('select')">
		<div class="field__head">
			<span class="field__label">
				{{ spec.label }}<span v-if="spec.required" class="field__required" :title="t('pinpoint', 'Required')">*</span>
			</span>
			<span class="badge" :title="statusInfo.hint">
				<NcIconSvgWrapper :path="statusInfo.icon" :size="16" />
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
			:inputmode="spec.type === 'number' ? 'decimal' : undefined"
			:disabled="readonly"
			@update:model-value="(v: string | number) => emit('update:modelValue', String(v))" />

		<p v-if="result?.anchor && !edited" class="field__source">
			<span class="field__page">{{ t('pinpoint', 'Page {n}', { n: result.anchor.page + 1 }) }}</span>
			“{{ result.anchor.matched_text }}”
		</p>
		<ul v-if="reasons.length" class="field__reasons">
			<li v-for="reason in reasons" :key="reason">
				{{ reason }}
			</li>
		</ul>
	</div>
</template>

<script setup lang="ts">
import { mdiPencilOutline } from '@mdi/js'
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
	padding: 10px 12px 12px;
	border: 1px solid var(--color-border);
	border-left: 4px solid var(--status-color);
	border-radius: var(--border-radius-large, 10px);
	background: var(--color-main-background);
	cursor: pointer;
}

.field--selected {
	border-color: var(--status-color);
	box-shadow: 0 0 0 1px var(--status-color);
}

.field--verified {
	--status-color: var(--color-element-success, #099f05);
}

.field--review {
	--status-color: var(--color-element-warning, #bf7900);
}

.field--unverified {
	--status-color: var(--color-element-error, #c90000);
}

.field--edited {
	--status-color: var(--color-primary-element);
}

.field__head {
	display: flex;
	align-items: center;
	justify-content: space-between;
	gap: 8px;
	margin-bottom: 6px;
}

.field__label {
	font-weight: bold;
}

.field__required {
	color: var(--color-text-maxcontrast);
	margin-left: 2px;
}

.badge {
	display: inline-flex;
	align-items: center;
	gap: 4px;
	padding: 1px 8px 1px 6px;
	border-radius: var(--border-radius-pill, 16px);
	color: var(--status-color);
	background: color-mix(in srgb, var(--status-color) 10%, transparent);
	font-size: var(--font-size-small, 13px);
	white-space: nowrap;
}

.field--verified .badge {
	color: var(--color-success-text, var(--status-color));
}

.field--review .badge {
	color: var(--color-warning-text, var(--status-color));
}

.field--unverified .badge {
	color: var(--color-error-text, var(--status-color));
}

.field__source {
	margin-top: 6px;
	color: var(--color-text-maxcontrast);
	font-size: var(--font-size-small, 13px);
	overflow-wrap: anywhere;
}

.field__page {
	font-weight: bold;
	margin-right: 4px;
}

.field__reasons {
	margin-top: 4px;
	font-size: var(--font-size-small, 13px);
}

.field__reasons li::before {
	content: '· ';
}
</style>
