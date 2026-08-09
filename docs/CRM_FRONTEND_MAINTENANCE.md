# Frappe CRM Frontend Customization Maintenance Guide

This document describes how the customized Frappe CRM frontend is maintained inside `visa_crm` while keeping the official `apps/crm` repository 100% stock and unmodified.

---

## 1. Upstream Pinning Reference

* **Official App**: `apps/crm` (`https://github.com/frappe/crm`)
* **Upstream Version**: `v1.73.0`
* **Upstream Commit Hash**: `3942bf65625f0602e41a15d8657298f83dd80b4b`

---

## 2. Architecture & Design Rationale

Official Frappe CRM (v1.73.0) does not provide a dynamic Vue runtime extension hook for replacing views inside `/crm/leads`. 
To ensure **Frappe Cloud deployment safety** without making uncommitted git modifications to the official `apps/crm` repository:

1. **Source Location**: The customized CRM frontend source code is maintained inside `visa_crm/frontend/crm/`.
2. **Customized Components**:
   - `visa_crm/frontend/crm/src/components/ListViews/LeadsTreeView.vue`: Implements the 3-page query-parameter state machine (`Categories` → `Subcategories` → `Leads`).
   - `visa_crm/frontend/crm/src/pages/Leads.vue`: Renders `LeadsTreeView` when `isTreeView` is active.
3. **Build Artifact Location**: `yarn build` inside `visa_crm/frontend/crm/` compiles the frontend SPA into `visa_crm/public/crm_frontend/`.
4. **Template Precedence**: `visa_crm/www/crm.html` overrides `crm/www/crm.html` via Frappe's `installed_apps` ordering, serving the custom bundle from `/assets/visa_crm/crm_frontend/`.

---

## 3. How to Rebuild the Customized Frontend

If you edit any Vue component inside `visa_crm/frontend/crm/src/`:

```bash
cd /home/shahbaz/frappe-bench/apps/visa_crm/frontend/crm
yarn build
```

The build command automatically:
* Compiles Vite assets into `visa_crm/public/crm_frontend/assets/`.
* Copies the generated `index.html` entry into `visa_crm/www/crm.html`.

---

## 4. How to Upgrade When Frappe Releases a New CRM Version

When a new version of `frappe/crm` (e.g. `v1.74.0`) is released and installed:

1. Sync upstream changes into `visa_crm/frontend/crm/`:
   ```bash
   rsync -av --exclude='node_modules' --exclude='.git' /home/shahbaz/frappe-bench/apps/crm/frontend/ /home/shahbaz/frappe-bench/apps/visa_crm/frontend/crm/
   ```
2. Re-apply the `LeadsTreeView.vue` component and `Leads.vue` tree view integration in `visa_crm/frontend/crm/src/`.
3. Re-run `yarn build` inside `visa_crm/frontend/crm/`.
4. Run `bench --site local.test clear-cache` and run the unit test suite.
