// Calls to Pinpoint's backend. Every request goes through AppAPI's proxy, which authenticates the
// Nextcloud user and forwards to the ExApp.
import axios from '@nextcloud/axios'
import { generateUrl } from '@nextcloud/router'

export const APP_ID = 'pinpoint'
export const MENU_ENTRY = 'main'

const base = () => generateUrl(`/apps/app_api/proxy/${APP_ID}/api`)

export type FieldStatus = 'verified' | 'review' | 'unverified' | 'missing'
export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'saved'
export type FieldType = 'text' | 'number' | 'date' | 'selection' | 'boolean'

export interface Box { page: number, x0: number, y0: number, x1: number, y1: number }

export interface FieldSpec {
	key: string
	label: string
	type: FieldType
	description: string
	required: boolean
	options: string[]
	column_id: number | null
}

export interface Schema { id: string, name: string, instructions: string, fields: FieldSpec[] }

export interface FieldResult {
	key: string
	value: string | number | boolean | null
	quote: string | null
	status: FieldStatus
	reasons: string[]
	anchor: null | { page: number, boxes: Box[], score: number, method: string, matched_text: string }
}

export interface Check { id: string, label: string, passed: boolean, fields: string[], detail: string }

export interface Extraction {
	fields: FieldResult[]
	checks: Check[]
	pages: { index: number, width: number, height: number, source: 'text-layer' | 'ocr' }[]
	truncated: boolean
	summary: Record<FieldStatus, number>
	timings: Record<string, number>
}

export interface Job {
	id: string
	fileId: number
	fileName: string
	mime: string
	schemaId: string
	schemaName: string
	status: JobStatus
	error: string | null
	tableId: number | null
	rowId: number | null
	createdAt: number
	updatedAt: number
	summary?: Record<FieldStatus, number>
	schema?: Schema
	result?: Extraction | null
	savedValues?: Record<string, unknown> | null
}

export interface Table { id: number, title: string, emoji: string }

export interface State {
	templates: Schema[]
	tables: Table[]
	tablesError: string | null
	textGenerationAvailable: boolean
	ocrAvailable: boolean
}

export interface FileRef { id: number, name: string, mime: string, size?: number }

/** The error message the backend put in the response, or a generic one. */
export function errorMessage(error: unknown): string {
	const data = (error as { response?: { data?: { error?: string, detail?: string } } })?.response?.data
	return data?.error ?? data?.detail ?? (error instanceof Error ? error.message : String(error))
}

export const api = {
	state: async () => (await axios.get<State>(`${base()}/state`)).data,
	files: async (ids: number[]) => (await axios.get<{ files: FileRef[] }>(`${base()}/files`, { params: { ids: ids.join(',') } })).data.files,
	createTable: async (template: string, title: string) => (await axios.post<Table>(`${base()}/tables`, { template, title })).data,
	tableSchema: async (tableId: number) => (await axios.get<Schema>(`${base()}/tables/${tableId}/schema`)).data,
	jobs: async () => (await axios.get<{ jobs: Job[] }>(`${base()}/jobs`)).data.jobs,
	job: async (id: string) => (await axios.get<Job>(`${base()}/jobs/${id}`)).data,
	createJob: async (fileId: number, tableId: number) => (await axios.post<Job>(`${base()}/jobs`, { fileId, tableId })).data,
	retry: async (id: string) => (await axios.post<Job>(`${base()}/jobs/${id}/retry`)).data,
	save: async (id: string, values: Record<string, unknown>) => (await axios.post<Job>(`${base()}/jobs/${id}/save`, { values })).data,
	remove: async (id: string) => { await axios.delete(`${base()}/jobs/${id}`) },
	pageUrl: (id: string, page: number) => `${base()}/jobs/${id}/pages/${page}`,
}
