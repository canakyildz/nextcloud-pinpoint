// Builds the frontend as one classic script plus one stylesheet in ex_app/js/.
// AppAPI injects ExApp scripts with Util::addScript under a proxy path, as classic (non-module)
// scripts, so the bundle must be self-contained: an IIFE with no code splitting.
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

export default defineConfig(({ mode }) => ({
	plugins: [vue()],
	define: {
		'process.env.NODE_ENV': JSON.stringify(mode === 'development' ? 'development' : 'production'),
		appName: JSON.stringify('pinpoint'),
		appVersion: JSON.stringify(process.env.npm_package_version ?? '0.0.0'),
	},
	build: {
		outDir: 'ex_app/js',
		emptyOutDir: true,
		cssCodeSplit: false,
		assetsInlineLimit: 1024 * 1024,
		sourcemap: mode === 'development',
		minify: mode !== 'development',
		rollupOptions: {
			input: 'src/main.ts',
			output: {
				format: 'iife',
				inlineDynamicImports: true,
				entryFileNames: 'pinpoint-main.js',
				assetFileNames: 'pinpoint-main.[ext]',
			},
		},
	},
}))
