<script module lang="ts">
	/** One cell of a score table; `tone` colours it by the bar it answers. */
	export interface Cell {
		text: string;
		tone?: 'above' | 'below';
	}
	/** One metric of a score: its label, the glossary's definition as a tooltip, one cell per
	 * column, and whether it starts a new group of rows. */
	export interface Row {
		label: string;
		title?: string;
		cells: Cell[];
		group?: boolean;
	}
</script>

<script lang="ts">
	let {
		caption,
		columns,
		rows
	}: {
		caption: string;
		/** The column headings: the eras, then the whole period last. */
		columns: string[];
		rows: Row[];
	} = $props();
</script>

<table>
	<caption>{caption}</caption>
	<thead>
		<tr>
			<th></th>
			{#each columns as column, i (column)}
				<th class:period={i === columns.length - 1}>{column}</th>
			{/each}
		</tr>
	</thead>
	<tbody>
		{#each rows as row (row.label)}
			<tr class:group={row.group}>
				<th title={row.title}>{row.label}</th>
				{#each row.cells as cell, i (i)}
					<td
						class:period={i === row.cells.length - 1}
						class:above={cell.tone === 'above'}
						class:below={cell.tone === 'below'}>{cell.text}</td
					>
				{/each}
			</tr>
		{/each}
	</tbody>
</table>

<style>
	table {
		border-collapse: collapse;
		font-size: 0.85rem;
		font-variant-numeric: tabular-nums;
		color: #333;
	}
	caption {
		text-align: left;
		font-weight: 600;
		color: #222;
		padding: 0 0 4px;
		white-space: nowrap;
	}
	th,
	td {
		padding: 2px 8px;
		text-align: right;
		white-space: nowrap;
	}
	thead th {
		font-weight: 600;
		border-bottom: 1px solid #bbb;
	}
	tbody th {
		text-align: left;
		font-weight: 400;
		color: #555;
		cursor: help;
	}
	tbody th[title=''] {
		cursor: default;
	}
	tr.group > * {
		border-top: 1px solid #e0e0e0;
	}
	.period {
		border-left: 1px solid #bbb;
	}
	.above {
		color: #2e7d32;
	}
	.below {
		color: #c62828;
	}
</style>
