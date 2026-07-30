import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import frappe
from visa_crm.overrides.lead_sync_source import VisaCRMLeadSyncSource
from visa_crm.patches import disable_builtin_crm_meta_sync as disable_sync

class MetaSource(dict):
    def __init__(self,name="Meta Ads Facebook",enabled=1,source_type="Facebook"):
        super().__init__(name=name,enabled=enabled,type=source_type)
        self.name=name
        self.enabled=enabled
        self.type=source_type
    def keys(self):
        return super().keys()
    def get(self,key,default=None):
        return getattr(self,key,super().get(key,default))

class TestDisableBuiltinCRMMetaSync(unittest.TestCase):
    def test_meta_source_cannot_be_enabled(self):
        source=MetaSource()
        with patch.object(disable_sync,"_custom_pipeline_active",return_value=True),patch.object(disable_sync.frappe,"logger") as logger:
            disable_sync.prevent_builtin_meta_sync_enable(source)
        self.assertEqual(source.enabled,0)
        logger.assert_called_once()

    def test_non_meta_source_is_untouched(self):
        source=MetaSource(name="Other Provider",source_type="Other")
        with patch.object(disable_sync,"_custom_pipeline_active",return_value=True):
            disable_sync.prevent_builtin_meta_sync_enable(source)
        self.assertEqual(source.enabled,1)

    def test_descriptive_fb_text_does_not_disable_non_meta_provider(self):
        source=MetaSource(name="FB Consulting Referrals",source_type="Other")
        with patch.object(disable_sync,"_custom_pipeline_active",return_value=True):
            disable_sync.prevent_builtin_meta_sync_enable(source)
        self.assertEqual(source.enabled,1)

    def test_all_registered_crm_sync_wrappers_are_stopped(self):
        rows=[SimpleNamespace(name=f"job-{index}",method=method,stopped=0,get=lambda key,default=None:0) for index,method in enumerate(disable_sync.CRM_SYNC_METHODS)]
        meta=SimpleNamespace(has_field=lambda field:field in ("method","stopped"))
        with patch.object(disable_sync.frappe.db,"exists",return_value=True),patch.object(disable_sync.frappe,"get_meta",return_value=meta),patch.object(disable_sync.frappe,"get_all",return_value=rows) as get_all,patch.object(disable_sync.frappe.db,"set_value") as set_value:
            changed=disable_sync._disable_scheduled_job()
        self.assertEqual(len(changed),len(disable_sync.CRM_SYNC_METHODS))
        self.assertEqual(get_all.call_args.kwargs["filters"],{"method":["in",disable_sync.CRM_SYNC_METHODS]})
        self.assertEqual(set_value.call_count,len(disable_sync.CRM_SYNC_METHODS))

    def test_manual_and_queued_meta_sync_are_blocked(self):
        source=frappe.new_doc("Lead Sync Source")
        self.assertIsInstance(source,VisaCRMLeadSyncSource)
        source.name="Meta Ads Facebook"
        source.type="Facebook"
        with patch.object(VisaCRMLeadSyncSource,"_visa_crm_meta_sync_disabled",return_value=True),patch.object(VisaCRMLeadSyncSource,"_log_disabled") as log,patch.object(disable_sync.frappe,"enqueue_doc") as enqueue:
            result=source.sync_leads()
            source._sync_leads()
        self.assertTrue(result["disabled"])
        self.assertEqual(log.call_count,2)
        enqueue.assert_not_called()
