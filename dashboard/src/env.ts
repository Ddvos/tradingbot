import { defineEnvVars } from '@sveltejs/kit/env';

// The dashboard's environment variables; SvelteKit only exposes the ones declared here.
export const variables = defineEnvVars({
	/** Where the dashboard reads from. Set it in dashboard/.env; defaults to the local API. */
	PUBLIC_API_URL: {
		public: true,
		static: true,
		schema: (value) => value ?? 'http://localhost:8000'
	}
});
