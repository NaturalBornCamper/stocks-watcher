/* =====================================================================
   Click-to-sort for any <table class="sortable"> on the page.
   Reads cell values from `data-sort` (falls back to text), pre-extracts
   all values to a JS array before sorting, and applies the new row order
   in ONE DocumentFragment append (single reflow).
   Adds .sorted-asc / .sorted-desc classes on the active <th> so style.css
   can show the ▲ / ▼ indicator.
   ===================================================================== */
(() => {
    const tableStates = new WeakMap();  // per-table sort state

    function cellValue(row, idx) {
        const cell = row.children[idx];
        if (!cell) return '';
        return cell.dataset.sort !== undefined
            ? cell.dataset.sort
            : (cell.textContent || '').trim();
    }

    function isColumnNumeric(rows, idx) {
        for (const row of rows) {
            const v = cellValue(row, idx);
            if (v === '') continue;
            if (isNaN(v)) return false;
        }
        return true;
    }

    function sortByColumn(th) {
        const table = th.closest('table');
        const headerRow = th.parentNode;
        const idx = Array.from(headerRow.children).indexOf(th);

        // Per-table toggle state (so each table sorts independently).
        let state = tableStates.get(table);
        if (!state) {
            state = { activeTh: null, asc: true };
            tableStates.set(table, state);
        }
        if (state.activeTh === th) {
            state.asc = !state.asc;
        } else {
            if (state.activeTh) state.activeTh.classList.remove('sorted-asc', 'sorted-desc');
            state.activeTh = th;
            state.asc = true;
        }
        th.classList.toggle('sorted-asc', state.asc);
        th.classList.toggle('sorted-desc', !state.asc);

        // Browsers auto-insert <tbody>; fall back to the table itself if not.
        const tbody = table.tBodies[0] || table;
        const rows = Array.from(tbody.children).filter(r => r !== headerRow);

        // Pre-extract values once (no per-comparison DOM reads).
        const numeric = isColumnNumeric(rows, idx);
        const items = rows.map(r => {
            const v = cellValue(r, idx);
            return { row: r, val: numeric ? parseFloat(v || 0) : v };
        });

        // Sort.
        const dir = state.asc ? 1 : -1;
        items.sort((a, b) => numeric
            ? dir * (a.val - b.val)
            : dir * String(a.val).localeCompare(String(b.val)));

        // Reapply order in a single reflow.
        const frag = document.createDocumentFragment();
        for (const item of items) frag.appendChild(item.row);
        tbody.appendChild(frag);
    }

    document.querySelectorAll('table.sortable th').forEach(th => {
        th.addEventListener('click', () => sortByColumn(th));
    });
})();
