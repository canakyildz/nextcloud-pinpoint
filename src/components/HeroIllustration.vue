<template>
	<svg class="hero-art"
		viewBox="0 0 260 180"
		role="img"
		:aria-label="t('pinpoint', 'A document with highlighted values flowing into a table')">
		<defs>
			<linearGradient id="pp-brand" x1="0" y1="0" x2="1" y2="1">
				<stop offset="0" stop-color="#7c6cf2" />
				<stop offset="1" stop-color="#1fb5ac" />
			</linearGradient>
		</defs>
		<circle cx="96" cy="92" r="78" class="hero-art__glow" />

		<!-- the document -->
		<g class="hero-art__doc">
			<rect x="38" y="22" width="112" height="146" rx="10" class="hero-art__paper" />
			<rect x="52" y="38" width="58" height="8" rx="4" class="hero-art__ink hero-art__ink--strong" />
			<rect x="52" y="56" width="84" height="5" rx="2.5" class="hero-art__ink" />
			<rect x="52" y="68" width="70" height="5" rx="2.5" class="hero-art__ink" />
			<rect x="52" y="92" width="84" height="5" rx="2.5" class="hero-art__ink" />
			<rect x="52" y="104" width="60" height="5" rx="2.5" class="hero-art__ink" />
			<rect x="52" y="128" width="46" height="6" rx="3" class="hero-art__ink hero-art__ink--strong" />
			<rect x="104" y="128" width="32" height="6" rx="3" class="hero-art__ink hero-art__ink--strong" />
			<!-- highlights, as Pinpoint draws them -->
			<rect x="47" y="51" width="94" height="15" rx="4" class="hero-art__mark hero-art__mark--ok" />
			<rect x="99" y="122" width="42" height="18" rx="4" class="hero-art__mark hero-art__mark--check" />
			<rect x="47" y="87" width="94" height="15" rx="4" class="hero-art__mark hero-art__mark--ok" />
		</g>

		<!-- the pin -->
		<g transform="translate(128 26)">
			<path d="M14 0C6.3 0 0 6.1 0 13.7 0 24 14 36 14 36s14-12 14-22.3C28 6.1 21.7 0 14 0z" fill="url(#pp-brand)" />
			<circle cx="14" cy="13.5" r="5" fill="#fff" />
		</g>

		<!-- flowing into a table -->
		<path d="M156 98 C172 98 172 98 186 98" class="hero-art__flow" />
		<path d="M182 93 L188 98 L182 103" class="hero-art__flow" />
		<g class="hero-art__table">
			<rect x="192" y="62" width="58" height="74" rx="8" class="hero-art__paper" />
			<rect x="200" y="72" width="42" height="6" rx="3" class="hero-art__ink hero-art__ink--strong" />
			<rect x="200" y="86" width="42" height="5" rx="2.5" class="hero-art__ink" />
			<rect x="196" y="97" width="50" height="12" rx="3" class="hero-art__row" />
			<rect x="200" y="117" width="42" height="5" rx="2.5" class="hero-art__ink" />
		</g>
	</svg>
</template>

<script setup lang="ts">
import { t } from '@nextcloud/l10n'
</script>

<style scoped>
.hero-art {
	width: 100%;
	max-width: 280px;
	height: auto;
	overflow: visible;
}

.hero-art__glow {
	fill: color-mix(in srgb, #7c6cf2 12%, transparent);
}

.hero-art__paper {
	fill: var(--color-main-background);
	stroke: var(--color-border);
	filter: drop-shadow(0 6px 14px rgba(40, 30, 90, 0.14));
}

.hero-art__ink {
	fill: var(--color-border-dark, #ccc);
}

.hero-art__ink--strong {
	fill: var(--color-text-maxcontrast);
	opacity: 0.55;
}

.hero-art__mark {
	fill: none;
	stroke-width: 2;
}

.hero-art__mark--ok {
	stroke: var(--color-element-success, #099f05);
	fill: color-mix(in srgb, var(--color-element-success, #099f05) 10%, transparent);
}

.hero-art__mark--check {
	stroke: var(--color-element-warning, #bf7900);
	fill: color-mix(in srgb, var(--color-element-warning, #bf7900) 12%, transparent);
}

.hero-art__flow {
	fill: none;
	stroke: #7c6cf2;
	stroke-width: 2.5;
	stroke-linecap: round;
	stroke-linejoin: round;
	stroke-dasharray: 4 5;
}

.hero-art__row {
	fill: color-mix(in srgb, var(--color-element-success, #099f05) 22%, transparent);
	stroke: var(--color-element-success, #099f05);
	stroke-width: 1.5;
}
</style>
