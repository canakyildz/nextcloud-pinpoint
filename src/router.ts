import { generateUrl } from '@nextcloud/router'
import { createRouter, createWebHistory } from 'vue-router'
import { APP_ID, MENU_ENTRY } from './api.ts'
import JobView from './views/JobView.vue'
import NewExtraction from './views/NewExtraction.vue'

// The page lives at …/apps/app_api/embedded/pinpoint/main/…, with or without /index.php depending on
// the server's URL rewriting. AppAPI serves every sub-path, so deep links such as …/main/jobs/<id>
// (in notifications and in Tables) open directly. The base is read from the address actually in use.
function routerBase(): string {
	const marker = `/apps/app_api/embedded/${APP_ID}/${MENU_ENTRY}`
	const index = window.location.pathname.indexOf(marker)
	return index >= 0 ? window.location.pathname.slice(0, index + marker.length) : generateUrl(marker)
}

export const router = createRouter({
	history: createWebHistory(routerBase()),
	routes: [
		{ path: '/', redirect: '/new' },
		{ path: '/new', name: 'new', component: NewExtraction },
		{ path: '/jobs/:id', name: 'job', component: JobView, props: true },
		{ path: '/:pathMatch(.*)*', redirect: '/new' },
	],
})
