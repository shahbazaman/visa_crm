# Visa CRM Deployment

## Frappe Cloud Order
1. Push code to GitHub.
2. Deploy latest app code on Frappe Cloud.
3. Run migration.
4. Clear cache.
5. Build assets.
6. Restart workers if available.

## Local Commands
```bash
cd ~/frappe-bench
bench --site local.test migrate
bench --site local.test clear-cache
bench build --app visa_crm
bench restart
```

## Verification
Open `/app/production-health` and run the deployment verification API from `/app/production-tools` if needed.
