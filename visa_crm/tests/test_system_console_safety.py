import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils.safe_exec import safe_exec


class TestSystemConsoleSafety(FrappeTestCase):
    def setUp(self):
        frappe.set_user("Administrator")

    def test_system_console_safe_exec_recovery(self):
        """
        Verify that recovery can be triggered inside Frappe Website System Console safe_exec
        using frappe.call without requiring forbidden Python imports or frappe.get_attr.
        """
        code_snippet = """
res = frappe.call("visa_crm.api.recovery.recover_graph_queues_dry_run")
result = res
"""
        exec_locals = {}
        safe_exec(code_snippet, _locals=exec_locals)
        res = exec_locals.get("result")
        self.assertIsNotNone(res)
        self.assertTrue(res.get("dry_run"))
        self.assertIn("would_recover", res)

    def test_system_console_safe_exec_meta_diagnostics(self):
        """
        Verify that meta diagnostics can be triggered inside System Console safe_exec.
        """
        code_snippet = """
res = frappe.call("visa_crm.api.production_diagnostics.meta_diagnostics")
result = res
"""
        exec_locals = {}
        safe_exec(code_snippet, _locals=exec_locals)
        res = exec_locals.get("result")
        self.assertIsNotNone(res)
        self.assertIn("page_access_token_valid", res)

    def test_lead_intake_stage_schema_fields(self):
        """
        Verify that Lead Intake Stage table contains 'attempt_count' and NOT 'attempts'.
        Prevents regression of pymysql.err.OperationalError: Unknown column 'attempts'.
        """
        columns = frappe.db.get_table_columns("Lead Intake Stage")
        self.assertIn("attempt_count", columns)
        self.assertNotIn("attempts", columns)

    def test_graph_download_none_id_protection(self):
        """
        Verify that fetch_lead raises MetaGraphError for invalid IDs like 'None', 'null', '0', ''.
        """
        from visa_crm.api.meta_graph import fetch_lead, MetaGraphError

        for invalid_id in ["None", "null", "0", "", None]:
            with self.assertRaises(MetaGraphError):
                fetch_lead(invalid_id)
