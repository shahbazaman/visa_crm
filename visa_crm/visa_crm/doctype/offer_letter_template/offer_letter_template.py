# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document

class OfferLetterTemplate(Document):
    def validate(self):
        if self.is_default:
            # Ensure only one default template exists
            frappe.db.sql(
                "UPDATE `tabOffer Letter Template` SET is_default = 0 WHERE name != %s",
                (self.name,)
            )
