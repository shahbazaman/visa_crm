import frappe
from crm.lead_syncing.doctype.lead_sync_source.lead_sync_source import LeadSyncSource
from visa_crm.patches.disable_builtin_crm_meta_sync import _custom_pipeline_active, _is_meta_source

class VisaCRMLeadSyncSource(LeadSyncSource):
    @frappe.whitelist()
    def sync_leads(self):
        if self._visa_crm_meta_sync_disabled():
            self._log_disabled("manual_sync_blocked")
            return {"disabled": True, "reason": "Visa CRM custom Meta pipeline is active"}
        return super().sync_leads()

    def _sync_leads(self):
        if self._visa_crm_meta_sync_disabled():
            self._log_disabled("background_sync_blocked")
            return
        return super()._sync_leads()

    def _visa_crm_meta_sync_disabled(self):
        return _custom_pipeline_active() and _is_meta_source(self)

    def _log_disabled(self, event):
        frappe.logger("visa_crm.meta").info({"event": f"crm_builtin_meta_{event}", "source": self.name, "type": self.type})
