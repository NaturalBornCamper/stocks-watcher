/* =====================================================================
   Live text filter for the SA score / count tables.
   A single text field hides any row whose symbol OR company name doesn't
   contain the typed text (case-insensitive). Takes effect on every
   keystroke -- no Apply button, no reload.

   Unlike the gated checkboxes, this filter is NOT carried in the URL:
   it's a quick "find this stock" helper, not a persistent view setting.

   Rows are hidden by adding the .name-filtered-out class (CSS display:none),
   which stacks cleanly with the gated-row hiding (also CSS display:none) --
   a row stays hidden if either filter wants it gone.
   ===================================================================== */
(() => {
    const input = document.querySelector('.name-filter-input');
    const wrapper = document.querySelector('.sa-filtered');
    if (!input || !wrapper) return;

    // All data rows (skip the header row, which has no symbol cell).
    const rows = Array.from(wrapper.querySelectorAll('table.sortable tr'))
        .filter(tr => tr.querySelector('td'));

    // Pre-read each row's searchable text once: symbol (1st cell) + company (3rd cell).
    const rowText = rows.map(tr => {
        const cells = tr.querySelectorAll('td');
        const symbol = cells[0] ? cells[0].textContent : '';
        const company = cells[2] ? cells[2].textContent : '';
        return (symbol + ' ' + company).toLowerCase();
    });

    function applyFilter() {
        const term = input.value.trim().toLowerCase();
        rows.forEach((tr, i) => {
            const hide = term !== '' && !rowText[i].includes(term);
            tr.classList.toggle('name-filtered-out', hide);
        });
    }

    input.addEventListener('input', applyFilter);
})();