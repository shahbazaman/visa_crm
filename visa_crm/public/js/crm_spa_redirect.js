/**
 * visa_crm/public/js/crm_spa_redirect.js
 *
 * Intercepts Vue Router (Frappe CRM SPA) navigation to the Leads list route
 * and redirects to the custom Lead Management Desk Page.
 *
 * Technique: monkey-patch history.pushState / history.replaceState so we can
 * detect client-side URL changes that never touch the server.
 *
 * Safe guards:
 *   - Only acts when the current origin matches the Frappe site
 *   - Does NOT intercept lead detail URLs (/crm/leads/CRM-LEAD-...)
 *   - Does NOT intercept /crm/contacts, /crm/deals, /crm/dashboard, etc.
 *   - Only redirects list patterns: /crm/leads, /crm/leads/view/*
 *   - Redirect is by window.location.href assignment (hard navigation), which is
 *     what we want: leave the CRM SPA and enter the Frappe Desk Lead Management page.
 */
(function () {
    'use strict';

    var LEAD_MANAGEMENT_URL = '/app/lead-management';

    /**
     * Returns true if the given pathname is a CRM Leads LIST route that should
     * be redirected to Lead Management.
     *
     * Patterns that MATCH (redirect):
     *   /crm/leads
     *   /crm/leads/view/list
     *   /crm/leads/view/kanban
     *   /crm/leads/view/group_by
     *
     * Patterns that DO NOT MATCH (leave alone — individual lead detail):
     *   /crm/leads/CRM-LEAD-2026-00126
     *   /crm/leads/CRM-LEAD-...
     *   /crm/contacts
     *   /crm/deals
     *   /app/*
     */
    function isLeadsListRoute(pathname) {
        // Must be inside /crm/ space
        if (!pathname || pathname.indexOf('/crm') !== 0) return false;

        var crm_relative = pathname.slice(4); // strip leading /crm -> leads/view/list etc
        if (!crm_relative) crm_relative = '/';

        // Strip leading slash for comparison
        var rel = crm_relative.replace(/^\//, '');

        // Match: empty (bare /crm), or starts with "leads" but NOT "leads/<doc-name>"
        // Doc names in Frappe CRM look like: CRM-LEAD-2026-00001 (contains uppercase + digits)
        // View routes look like: leads, leads/view/list, leads/view/kanban

        if (rel === '' || rel === 'leads') return true;

        if (rel.indexOf('leads/') === 0) {
            var afterLeads = rel.slice(6); // strip "leads/"
            // It's a leads sub-path — check if it's a view route or a doc name
            // View routes start with "view/"
            if (afterLeads.indexOf('view/') === 0) return true;
            // Otherwise it's a lead detail doc name — do NOT redirect
            return false;
        }

        return false;
    }

    function redirectIfNeeded(pathname) {
        if (!isLeadsListRoute(pathname)) return;
        if (window.location.href.indexOf(LEAD_MANAGEMENT_URL) !== -1) return;
        window.location.href = LEAD_MANAGEMENT_URL;
    }

    // Check on initial page load
    redirectIfNeeded(window.location.pathname);

    // Monkey-patch history.pushState (Vue Router uses this for SPA navigation)
    var _origPushState = history.pushState.bind(history);
    history.pushState = function (state, title, url) {
        var result = _origPushState(state, title, url);
        try {
            if (url) {
                var parsed;
                try {
                    parsed = new URL(url, window.location.origin);
                } catch (e) {
                    parsed = { pathname: url };
                }
                redirectIfNeeded(parsed.pathname);
            }
        } catch (e) {}
        return result;
    };

    // Monkey-patch history.replaceState (used during initial SPA load)
    var _origReplaceState = history.replaceState.bind(history);
    history.replaceState = function (state, title, url) {
        var result = _origReplaceState(state, title, url);
        try {
            if (url) {
                var parsed;
                try {
                    parsed = new URL(url, window.location.origin);
                } catch (e) {
                    parsed = { pathname: url };
                }
                redirectIfNeeded(parsed.pathname);
            }
        } catch (e) {}
        return result;
    };

    // Also watch popstate (browser back/forward within the SPA)
    window.addEventListener('popstate', function () {
        redirectIfNeeded(window.location.pathname);
    });

})();
