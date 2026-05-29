/* =====================================================================
   Click-to-sort for any <table class="sortable"> on the page.
   Reads cell values from `data-sort` (falls back to text), pre-extracts
   all values to a JS array before sorting, and applies the new row order
   in ONE DocumentFragment append (single reflow).
   Adds .sorted-asc / .sorted-desc classes on the active <th> so style.css
   can show the ▲ / ▼ indicator.

   Sort state lives in the URL: ?sort=<col-index>&dir=asc|desc
   - On page load: applies the URL sort if present.
   - On column click: updates the URL via history.replaceState (no new
     history entries — back button stays clean).
   The menu / date-selector links carry ?sort/&dir forward so the sort
   sticks across algorithm switches and month changes.
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

    function applySort(th, asc) {
        const table = th.closest('table');
        const headerRow = th.parentNode;
        const idx = Array.from(headerRow.children).indexOf(th);

        // Mark the indicator (clears any previously sorted column on this table).
        let state = tableStates.get(table);
        if (state && state.activeTh && state.activeTh !== th) {
            state.activeTh.classList.remove('sorted-asc', 'sorted-desc');
        }
        th.classList.toggle('sorted-asc', asc);
        th.classList.toggle('sorted-desc', !asc);
        tableStates.set(table, { activeTh: th, asc });

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
        const dir = asc ? 1 : -1;
        items.sort((a, b) => numeric
            ? dir * (a.val - b.val)
            : dir * String(a.val).localeCompare(String(b.val)));

        // Reapply order in a single reflow.
        const frag = document.createDocumentFragment();
        for (const item of items) frag.appendChild(item.row);
        tbody.appendChild(frag);
    }

    function syncSortToNavAndForms(sortIdx, dir) {
        // Menu and date-selector links were rendered server-side with whatever sort
        // the request had. Rewrite their hrefs now so clicking them carries the new sort.
        document.querySelectorAll('.sa-menu a, .date-selector a').forEach(a => {
            try {
                const url = new URL(a.href);
                url.searchParams.set('sort', sortIdx);
                url.searchParams.set('dir', dir);
                a.href = url.toString();
            } catch (e) { /* skip non-URL hrefs */ }
        });
        // Filter forms only render hidden sort/dir inputs when the request had them.
        // After a client-side sort we need to insert (or update) them so the next
        // form submit also carries the sort.
        document.querySelectorAll('form.filter-bar').forEach(form => {
            for (const [name, value] of [['sort', sortIdx], ['dir', dir]]) {
                let input = form.querySelector(`input[name="${name}"]`);
                if (!input) {
                    input = document.createElement('input');
                    input.type = 'hidden';
                    input.name = name;
                    form.appendChild(input);
                }
                input.value = value;
            }
        });
    }

    function writeSortToUrl(th, asc) {
        const idx = Array.from(th.parentNode.children).indexOf(th);
        const dir = asc ? 'asc' : 'desc';
        const url = new URL(window.location.href);
        url.searchParams.set('sort', idx);
        url.searchParams.set('dir', dir);
        history.replaceState(null, '', url.toString());
        syncSortToNavAndForms(idx, dir);
    }

    function handleClick(th) {
        const table = th.closest('table');
        const state = tableStates.get(table);
        // Toggle direction if same column; otherwise start ascending on the new one.
        const asc = (state && state.activeTh === th) ? !state.asc : true;
        applySort(th, asc);
        writeSortToUrl(th, asc);
    }

    // Wire up click handlers.
    document.querySelectorAll('table.sortable th').forEach(th => {
        th.addEventListener('click', () => handleClick(th));
    });

    // Apply the URL sort, if any, on initial load.
    const params = new URL(window.location.href).searchParams;
    const initSort = params.get('sort');
    if (initSort !== null) {
        const idx = parseInt(initSort, 10);
        if (!isNaN(idx)) {
            const asc = params.get('dir') !== 'desc';
            document.querySelectorAll('table.sortable').forEach(table => {
                const headerRow = table.querySelector('tr');
                const th = headerRow && headerRow.children[idx];
                if (th) applySort(th, asc);
            });
        }
    }
})();
