import os
import frappe
from frappe.website.page_renderers.base_renderer import BaseRenderer


class CRMPageRenderer(BaseRenderer):
	"""
	Custom Page Renderer for Frappe CRM (/crm and /crm/*).
	Guarantees that Frappe Cloud serves the enhanced Visa CRM frontend bundle
	(with in-app WhatsApp workspace, 3 view modes, and in-tab navigation)
	regardless of app installation order in MariaDB.
	"""

	def can_render(self) -> bool:
		clean_path = (self.path or "").strip("/")
		return clean_path == "crm" or clean_path.startswith("crm/")

	def render(self):
		from crm.api import check_app_permission

		if not check_app_permission():
			frappe.throw(
				frappe._("You do not have permission to access Frappe CRM"),
				frappe.PermissionError,
			)

		import crm.www.crm

		context = crm.www.crm.get_context()

		if "csrf_token" not in context.boot:
			context.boot["csrf_token"] = frappe.sessions.get_csrf_token()

		template_file = frappe.get_app_path("visa_crm", "www", "crm.html")
		with open(template_file, "r", encoding="utf-8") as f:
			template_source = f.read()

		html = frappe.render_template(template_source, context)
		if frappe.local.session and getattr(frappe.local.session, "data", None):
			csrf_token = frappe.local.session.data.csrf_token
			html = html.replace(
				"<!-- csrf_token -->",
				f'<script>frappe.csrf_token = "{csrf_token}";</script>',
			)

		return self.build_response(html)
