<template>
	<svg class="scan" viewBox="0 0 140 170" aria-hidden="true">
		<defs>
			<linearGradient id="pp-beam" x1="0" y1="0" x2="0" y2="1">
				<stop offset="0" stop-color="#7c6cf2" stop-opacity="0" />
				<stop offset="0.85" stop-color="#7c6cf2" stop-opacity="0.35" />
				<stop offset="1" stop-color="#7c6cf2" stop-opacity="0.9" />
			</linearGradient>
			<clipPath id="pp-page">
				<rect x="16" y="10" width="108" height="150" rx="10" />
			</clipPath>
		</defs>
		<rect x="16" y="10" width="108" height="150" rx="10" class="scan__paper" />
		<g class="scan__ink">
			<rect x="30" y="26" width="52" height="8" rx="4" />
			<rect x="30" y="46" width="80" height="5" rx="2.5" />
			<rect x="30" y="58" width="64" height="5" rx="2.5" />
			<rect x="30" y="80" width="80" height="5" rx="2.5" />
			<rect x="30" y="92" width="56" height="5" rx="2.5" />
			<rect x="30" y="114" width="80" height="5" rx="2.5" />
			<rect x="30" y="136" width="40" height="7" rx="3.5" />
			<rect x="80" y="136" width="30" height="7" rx="3.5" />
		</g>
		<g class="scan__marks">
			<rect x="25" y="41" width="90" height="15" rx="4" class="scan__mark" style="animation-delay: 0.6s" />
			<rect x="25" y="75" width="90" height="15" rx="4" class="scan__mark" style="animation-delay: 1.2s" />
			<rect x="75" y="131" width="40" height="17" rx="4" class="scan__mark" style="animation-delay: 1.9s" />
		</g>
		<g clip-path="url(#pp-page)">
			<rect x="16" y="-40" width="108" height="40" class="scan__beam" fill="url(#pp-beam)" />
		</g>
	</svg>
</template>

<style scoped>
.scan {
	width: 120px;
	height: auto;
}

.scan__paper {
	fill: var(--color-main-background);
	stroke: var(--color-border);
	filter: drop-shadow(0 8px 18px rgba(40, 30, 90, 0.16));
}

.scan__ink rect {
	fill: var(--color-border-dark, #ccc);
}

.scan__mark {
	fill: color-mix(in srgb, var(--color-element-success, #099f05) 12%, transparent);
	stroke: var(--color-element-success, #099f05);
	stroke-width: 2;
	opacity: 0;
	animation: mark-in 2.6s ease-out infinite;
}

.scan__beam {
	animation: sweep 2.6s cubic-bezier(0.45, 0, 0.55, 1) infinite;
}

@keyframes sweep {
	from {
		transform: translateY(0);
	}

	to {
		transform: translateY(200px);
	}
}

@keyframes mark-in {
	0%, 10% {
		opacity: 0;
	}

	30%, 80% {
		opacity: 1;
	}

	100% {
		opacity: 0;
	}
}

@media (prefers-reduced-motion: reduce) {
	.scan__beam {
		animation: none;
		opacity: 0;
	}

	.scan__mark {
		animation: none;
		opacity: 1;
	}
}
</style>
