/* =====================================================================
   Live "hide gated stocks" filter for the SA score / count tables.
   Three checkboxes (red / orange / yellow) toggle row visibility instantly
   via CSS classes on the .sa-filtered wrapper -- no Apply button, no
   reload. State lives in the URL (?hide_red=1 / &hide_orange=1 / &hide_yellow=1)
   and is carried forward to menu / date-selector links so it persists across
   algorithm switches (unlike min_score, which is per-algorithm).
   ===================================================================== */
(() => {
    const PARAMS = ['hide_red', 'hide_orange', 'hide_yellow'];
    // Each URL param maps to a wrapper CSS class that hides the matching rows.
    const WRAPPER_CLASS = {
        hide_red:    'hide-gated-red',
        hide_orange: 'hide-gated-orange',
        hide_yellow: 'hide-gated-yellow',
    };

    const wrapper = document.querySelector('.sa-filtered');
    const checkboxes = PARAMS
        .map(name => document.querySelector(`.live-filter input[name="${name}"][type="checkbox"]`))
        .filter(Boolean);

    if (!wrapper || checkboxes.length === 0) return;

    function applyCurrentState() {
        // 1) Toggle wrapper classes so the right rows are hidden via CSS.
        for (const box of checkboxes) {
            wrapper.classList.toggle(WRAPPER_CLASS[box.name], box.checked);
        }
        // 2) Mirror checkbox state into URL bar, menu / date-selector links,
        //    and the filter form's hidden inputs.
        const desired = {};
        for (const box of checkboxes) {
            desired[box.name] = box.checked ? '1' : null;
        }

        // URL bar.
        const url = new URL(window.location.href);
        for (const [name, value] of Object.entries(desired)) {
            if (value === null) url.searchParams.delete(name);
            else url.searchParams.set(name, value);
        }
        history.replaceState(null, '', url.toString());

        // Cross-view nav links.
        document.querySelectorAll('.sa-menu a, .date-selector a').forEach(a => {
            try {
                const linkUrl = new URL(a.href);
                for (const [name, value] of Object.entries(desired)) {
                    if (value === null) linkUrl.searchParams.delete(name);
                    else linkUrl.searchParams.set(name, value);
                }
                a.href = linkUrl.toString();
            } catch (e) { /* skip non-URL hrefs */ }
        });

        // Hidden inputs on the Apply form, so submitting it doesn't drop the flags.
        document.querySelectorAll('form.filter-bar').forEach(form => {
            for (const [name, value] of Object.entries(desired)) {
                let hidden = form.querySelector(`input[type="hidden"][name="${name}"]`);
                if (value !== null) {
                    if (!hidden) {
                        hidden = document.createElement('input');
                        hidden.type = 'hidden';
                        hidden.name = name;
                        form.appendChild(hidden);
                    }
                    hidden.value = value;
                } else if (hidden) {
                    hidden.remove();
                }
            }
        });
    }

    for (const box of checkboxes) {
        box.addEventListener('change', applyCurrentState);
    }
    // No initial applyCurrentState() call: the server-rendered wrapper classes
    // and form hidden inputs already match the URL on first load, so we'd just
    // be re-writing the same state.
})();
