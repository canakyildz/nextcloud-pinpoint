// A tiny shared store: the job list in the navigation and the state shown on every page.
import { reactive } from 'vue'
import { api, type Job, type State } from './api.ts'

export const store = reactive({
	jobs: [] as Job[],
	state: null as State | null,
	loadError: '' as string,
})

export async function refreshJobs(): Promise<void> {
	store.jobs = await api.jobs()
}

export async function refreshState(): Promise<void> {
	store.state = await api.state()
}

export function upsertJob(job: Job): void {
	const index = store.jobs.findIndex((j) => j.id === job.id)
	if (index === -1) {
		store.jobs.unshift(job)
	} else {
		store.jobs[index] = { ...store.jobs[index], ...job }
	}
}
