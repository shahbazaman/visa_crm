# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document

class EmployeeDocument(Document):
    def validate(self):
        if self.verification_status == "Verified" and not self.verified_by:
            self.verified_by = frappe.session.user
            self.verification_date = frappe.utils.today()
        elif self.verification_status == "Pending":
            self.verified_by = None
            self.verification_date = None
