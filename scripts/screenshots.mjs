// Takes the README and App Store screenshots from the development stack (dev/docker-compose.yml),
// so they can be regenerated whenever the UI changes:
//
//   NC_URL=http://localhost:8080 node scripts/screenshots.mjs
//
// Needs Google Chrome installed (playwright-core drives it; no browser download) and a few extracted
// documents in the dev instance (see docs/DEVELOPMENT.md). Writes screenshots/*.png and review.gif.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { chromium } from 'playwright-core'

const base = process.env.NC_URL ?? 'http://localhost:8080'
const user = process.env.NC_USER ?? 'admin'
const password = process.env.NC_PASSWORD ?? 'admin' // dev stack only
const out = new URL('../screenshots/', import.meta.url).pathname
mkdirSync(out, { recursive: true })

const browser = await chromium.launch({ channel: 'chrome', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: 'light' })
const page = await context.newPage()

async function api(path, init = {}) {
	const response = await page.request.fetch(`${base}/index.php/apps/app_api/proxy/pinpoint/api${path}`, init)
	return response.json()
}

async function settle() {
	await page.waitForLoadState('networkidle')
	await page.waitForTimeout(600)
}

// Log in
await page.goto(`${base}/index.php/login`)
await page.fill('#user', user)
await page.fill('#password', password)
await page.click('button[type=submit]')
await page.waitForURL(/apps\//)

const { jobs } = await api('/jobs')
const byName = (name) => jobs.find((job) => job.fileName === name && (job.status === 'done' || job.status === 'saved'))
const flagged = byName(process.env.REVIEW_FILE ?? 'invoice-07.pdf')
const clean = byName(process.env.SAVE_FILE ?? 'invoice-04.pdf')

// 1. Review screen, with the value the model got wrong selected
if (flagged) {
	await page.goto(`${base}/index.php/apps/app_api/embedded/pinpoint/main/jobs/${flagged.id}`)
	await page.waitForSelector('.review')
	await settle()
	const card = page.locator('.field', { hasText: process.env.REVIEW_FIELD ?? 'Tax amount' })
	await card.click()
	await page.waitForTimeout(900)
	await page.screenshot({ path: join(out, 'review.png') })

	// Animated tour: click through a few fields so the highlight jumps across the page.
	const frames = mkdtempSync(join(tmpdir(), 'pinpoint-gif-'))
	let n = 0
	for (const label of ['Supplier', 'Issue date', 'Net amount', 'Tax amount', 'Total amount']) {
		await page.locator('.field', { hasText: label }).first().click()
		for (let i = 0; i < 6; i++) {
			await page.waitForTimeout(150)
			await page.screenshot({ path: join(frames, `${String(n++).padStart(3, '0')}.png`), scale: 'css' })
		}
	}
	execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', '6', '-i', join(frames, '%03d.png'),
		'-vf', 'scale=960:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse=dither=bayer',
		join(out, 'review.gif')])
	rmSync(frames, { recursive: true })
}

// 2. Starting an extraction, as the Files action opens it
const fileIds = jobs.slice(0, 2).map((job) => job.fileId).join(',')
await page.goto(`${base}/index.php/apps/app_api/embedded/pinpoint/main/new?fileIds=${fileIds}`)
await page.waitForSelector('.schema__fields')
await settle()
await page.screenshot({ path: join(out, 'new.png') })

// 3. The row in Tables, with its Source and Evidence
if (clean) {
	let saved = clean
	if (clean.status !== 'saved') {
		saved = await api(`/jobs/${clean.id}/save`, { method: 'POST', data: { values: {} } })
	}
	// The row's detail view shows every column, including Source and Evidence; a tall window fits them.
	await page.setViewportSize({ width: 1440, height: 1500 })
	await page.goto(`${base}/index.php/apps/tables/#/table/${saved.tableId}/row/${saved.rowId}`)
	await page.waitForSelector('[role="dialog"], .modal-container')
	await settle()
	await page.mouse.move(720, 500)
	await page.mouse.wheel(0, 3000) // scroll the dialog down to Source and Evidence
	await page.waitForTimeout(600)
	await page.waitForTimeout(400)
	await page.screenshot({ path: join(out, 'tables.png') })
}

// 4. The Files action
await page.setViewportSize({ width: 1440, height: 900 })
await page.goto(`${base}/index.php/apps/files/files?dir=/Invoices`)
await page.waitForSelector('[data-cy-files-list-row-name]')
await settle()
const row = page.locator('[data-cy-files-list-row-name="invoice-07.pdf"]')
await row.click({ button: 'right' })
await page.waitForTimeout(800)
await page.screenshot({ path: join(out, 'files-action.png') })

await browser.close()
console.log(`Screenshots written to ${out}`)
