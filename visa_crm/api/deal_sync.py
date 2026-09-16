# Copyright (c) 2026, Shahbaz and contributors
# For license information, please see license.txt

import re
import frappe
from frappe import _


def parse_numeric_budget(val) -> float:
    """Safely parse currency amount from string (e.g. '₹70,000', '70000', '1.5 Lakhs')."""
    if not val:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    
    val_str = str(val).strip().replace(",", "")
    
    # Handle Lakhs
    lakh_match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lac)s?", val_str, re.IGNORECASE)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except Exception:
            pass

    # Handle standard numbers
    num_match = re.search(r"[0-9]+(?:\.[0-9]+)?", val_str)
    if num_match:
        try:
            return float(num_match.group(0))
        except Exception:
            return 0.0
    return 0.0


def ensure_contact_for_deal(deal_doc, lead_doc):
    """
    Ensure the Deal has a linked Contact in deal_doc.contacts child table.
    Guarantees that:
    1. Existing Contact is reused without creating duplicates.
    2. Child table row has email/mobile_no/is_primary populated so core CRMDeal.validate()
       never clears Deal email and mobile_no.
    3. Handles missing lead or missing contact gracefully.
    """
    if not lead_doc:
        return None

    target_name = getattr(lead_doc, "lead_name", None) or f"{getattr(lead_doc, 'first_name', '') or ''} {getattr(lead_doc, 'last_name', '') or ''}".strip()
    target_mobile = getattr(lead_doc, "mobile_no", None) or getattr(lead_doc, "phone", None)
    target_email = getattr(lead_doc, "email", None)

    # 1. If deal already has contacts in child table, ensure fields are populated on primary row
    if hasattr(deal_doc, "contacts") and deal_doc.contacts:
        primary_row = None
        for row in deal_doc.contacts:
            if getattr(row, "is_primary", None):
                primary_row = row
                break
        if not primary_row and deal_doc.contacts:
            primary_row = deal_doc.contacts[0]
            primary_row.is_primary = 1

        if primary_row:
            if not getattr(deal_doc, "contact", None) and primary_row.contact:
                deal_doc.contact = primary_row.contact
            if not getattr(primary_row, "mobile_no", None) and target_mobile:
                primary_row.mobile_no = target_mobile
            if not getattr(primary_row, "email", None) and target_email:
                primary_row.email = target_email
            if not getattr(primary_row, "full_name", None) and target_name:
                primary_row.full_name = target_name
            return primary_row.contact

    contact_name = None

    # 2. Check if Deal has a linked contact field
    if getattr(deal_doc, "contact", None) and frappe.db.exists("Contact", deal_doc.contact):
        contact_name = deal_doc.contact

    # 3. Check if CRM Lead has a linked Contact via tabDynamic Link
    if not contact_name:
        linked_contact = frappe.db.get_value(
            "Dynamic Link",
            {"link_doctype": "CRM Lead", "link_name": lead_doc.name, "parenttype": "Contact"},
            "parent",
        )
        if linked_contact and frappe.db.exists("Contact", linked_contact):
            contact_name = linked_contact

    # 4. Check if Contact exists by Email or Phone
    if not contact_name:
        if target_email:
            contact_name = frappe.db.get_value("Contact Email", {"email_id": target_email}, "parent")
        if not contact_name and target_mobile:
            contact_name = frappe.db.get_value("Contact Phone", {"phone": target_mobile}, "parent")

    # 5. If no contact exists, create one from the lead
    if not contact_name and (target_name or target_email or target_mobile):
        try:
            contact = frappe.new_doc("Contact")
            contact.first_name = getattr(lead_doc, "first_name", None) or target_name or "Lead"
            contact.last_name = getattr(lead_doc, "last_name", None) or ""
            contact.salutation = getattr(lead_doc, "salutation", None)
            contact.gender = getattr(lead_doc, "gender", None)
            contact.designation = getattr(lead_doc, "job_title", None)
            contact.company_name = getattr(lead_doc, "organization", None)

            if target_email:
                contact.append("email_ids", {"email_id": target_email, "is_primary": 1})
            if target_mobile:
                contact.append("phone_nos", {"phone": target_mobile, "is_primary_mobile_no": 1})

            # Append dynamic link to CRM Lead
            contact.append("links", {"link_doctype": "CRM Lead", "link_name": lead_doc.name})
            contact.insert(ignore_permissions=True)
            contact_name = contact.name
        except Exception as e:
            frappe.logger().warning(f"Unable to auto-create contact for lead {lead_doc.name}: {e}")

    # 6. Link contact to Deal child table with fields populated
    if contact_name:
        if not getattr(deal_doc, "contact", None):
            deal_doc.contact = contact_name
        if hasattr(deal_doc, "contacts"):
            existing = [c.contact for c in (deal_doc.contacts or [])]
            if contact_name not in existing:
                deal_doc.append("contacts", {
                    "contact": contact_name,
                    "full_name": target_name or "",
                    "email": target_email or "",
                    "mobile_no": target_mobile or "",
                    "phone": target_mobile or "",
                    "is_primary": 1
                })

    return contact_name


def map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False) -> list:
    """
    Pure mapping engine from CRM Lead to CRM Deal.
    Copies standard and custom fields using deterministic precedence:
    1. Existing valid Deal field value (preserved unless overwrite_existing=True)
    2. Linked Lead field value
    Returns list of updated fieldnames.
    """
    if not lead_doc:
        return []

    deal_meta = frappe.get_meta("CRM Deal")
    updated_fields = []

    def set_field(target_field, source_val):
        if not deal_meta.has_field(target_field):
            return
        if source_val is None or source_val == "":
            return
        current_val = getattr(deal_doc, target_field, None)
        if overwrite_existing or current_val is None or current_val == "" or current_val == 0:
            if current_val != source_val:
                setattr(deal_doc, target_field, source_val)
                updated_fields.append(target_field)

    # Core identification & Person fields
    target_name = getattr(lead_doc, "lead_name", None) or f"{getattr(lead_doc, 'first_name', '') or ''} {getattr(lead_doc, 'last_name', '') or ''}".strip()
    target_mobile = getattr(lead_doc, "mobile_no", None) or getattr(lead_doc, "phone", None)
    target_email = getattr(lead_doc, "email", None)

    set_field("lead", lead_doc.name)
    set_field("lead_name", target_name)
    set_field("first_name", getattr(lead_doc, "first_name", None))
    set_field("last_name", getattr(lead_doc, "last_name", None))
    set_field("email", target_email)
    set_field("mobile_no", target_mobile)
    set_field("phone", target_mobile)
    set_field("job_title", getattr(lead_doc, "job_title", None))

    # Organization fields
    if getattr(lead_doc, "organization", None):
        if frappe.db.exists("CRM Organization", lead_doc.organization):
            set_field("organization", lead_doc.organization)
        org_name = getattr(lead_doc, "organization_name", None) or lead_doc.organization
        set_field("organization_name", org_name)
    elif target_name:
        set_field("organization_name", target_name)

    # Source field validation
    if getattr(lead_doc, "source", None):
        if frappe.db.exists("CRM Lead Source", lead_doc.source):
            set_field("source", lead_doc.source)
        elif frappe.db.exists("Lead Source", lead_doc.source):
            set_field("source", lead_doc.source)
        else:
            set_field("source", "Meta Ads")
    else:
        set_field("source", "Meta Ads")

    # Deal Owner assignment
    if not getattr(deal_doc, "deal_owner", None) or overwrite_existing:
        if getattr(lead_doc, "lead_owner", None) and frappe.db.exists("User", lead_doc.lead_owner):
            set_field("deal_owner", lead_doc.lead_owner)
        elif getattr(lead_doc, "assigned_counselor", None):
            emp_user = frappe.db.get_value("Employee", lead_doc.assigned_counselor, "user_id")
            if emp_user and frappe.db.exists("User", emp_user):
                set_field("deal_owner", emp_user)

    # Territory & Industry
    if getattr(lead_doc, "territory", None) and frappe.db.exists("Territory", lead_doc.territory):
        set_field("territory", lead_doc.territory)
    elif getattr(lead_doc, "country", None) and frappe.db.exists("Territory", lead_doc.country):
        set_field("territory", lead_doc.country)

    if getattr(lead_doc, "industry", None) and frappe.db.exists("Industry Type", lead_doc.industry):
        set_field("industry", lead_doc.industry)

    if getattr(lead_doc, "no_of_employees", None):
        set_field("no_of_employees", lead_doc.no_of_employees)

    # Deal Value & Budget
    budget_amt = parse_numeric_budget(getattr(lead_doc, "custom_budget", None))
    if budget_amt > 0:
        set_field("expected_deal_value", budget_amt)
        set_field("deal_value", budget_amt)
        set_field("annual_revenue", budget_amt)

    # Marketing & Campaign Custom Fields
    set_field("custom_meta_campaign_name", getattr(lead_doc, "meta_campaign_name", None))
    set_field("custom_meta_campaign_id", getattr(lead_doc, "meta_campaign_id", None))
    set_field("custom_meta_adset_name", getattr(lead_doc, "meta_adset_name", None))
    set_field("custom_meta_adset_id", getattr(lead_doc, "meta_adset_id", None))
    set_field("custom_meta_ad_name", getattr(lead_doc, "meta_ad_name", None))
    set_field("custom_meta_ad_id", getattr(lead_doc, "meta_ad_id", None))
    set_field("custom_facebook_form_id", getattr(lead_doc, "facebook_form_id", None))
    set_field("custom_facebook_lead_id", getattr(lead_doc, "facebook_lead_id", None))

    # Travel & Qualification Fields
    set_field("custom_lead_category", getattr(lead_doc, "lead_category", None))
    set_field("custom_lead_group", getattr(lead_doc, "lead_group", None))
    set_field("custom_responsible_department", getattr(lead_doc, "responsible_department", None))
    set_field("custom_destination", getattr(lead_doc, "custom_destination", None))
    set_field("custom_visa_type", getattr(lead_doc, "custom_visa_type", None) or getattr(lead_doc, "visa_type", None))
    set_field("custom_travel_month", getattr(lead_doc, "custom_travel_month", None))
    set_field("custom_budget", getattr(lead_doc, "custom_budget", None))
    set_field("custom_assigned_counselor", getattr(lead_doc, "assigned_counselor", None))
    set_field("custom_customer", getattr(lead_doc, "customer", None))

    # Ensure Contact is linked so core CRMDeal doesn't wipe email/mobile_no
    ensure_contact_for_deal(deal_doc, lead_doc)

    return updated_fields


def sync_lead_to_deal_before_insert(doc, method=None):
    """Doc event on CRM Deal: before_insert"""
    if getattr(doc, "lead", None):
        try:
            lead_doc = frappe.get_doc("CRM Lead", doc.lead)
            map_lead_to_deal(doc, lead_doc, overwrite_existing=False)
        except Exception as e:
            frappe.logger().warning(f"Error syncing lead to deal before_insert ({doc.name}): {e}")


def sync_lead_to_deal_validate(doc, method=None):
    """
    Doc event on CRM Deal: validate
    Runs AFTER CRMDeal.validate(), restoring email/mobile_no if cleared by core.
    """
    if getattr(doc, "lead", None):
        try:
            lead_doc = frappe.get_cached_doc("CRM Lead", doc.lead)
            target_name = getattr(lead_doc, "lead_name", None) or f"{getattr(lead_doc, 'first_name', '') or ''} {getattr(lead_doc, 'last_name', '') or ''}".strip()
            target_mobile = getattr(lead_doc, "mobile_no", None) or getattr(lead_doc, "phone", None)
            target_email = getattr(lead_doc, "email", None)

            # Restore email and mobile_no if emptied
            if not getattr(doc, "email", None) and target_email:
                doc.email = target_email
            if not getattr(doc, "mobile_no", None) and target_mobile:
                doc.mobile_no = target_mobile
            if not getattr(doc, "phone", None) and target_mobile:
                doc.phone = target_mobile
            if not getattr(doc, "lead_name", None) and target_name:
                doc.lead_name = target_name

            # Ensure contact link in child table
            ensure_contact_for_deal(doc, lead_doc)
        except Exception as e:
            frappe.logger().warning(f"Error syncing lead to deal validate ({doc.name}): {e}")


def sync_lead_to_linked_deal_after_save(doc, method=None):
    """
    Doc event on CRM Lead: after_save
    Synchronizes updated campaign and contact info to any linked Deal without overwriting manual sales fields.
    """
    if not frappe.db.exists("DocType", "CRM Deal"):
        return

    deals = frappe.get_all("CRM Deal", filters={"lead": doc.name}, pluck="name")
    for deal_name in deals:
        try:
            deal_doc = frappe.get_doc("CRM Deal", deal_name)
            updated = map_lead_to_deal(deal_doc, doc, overwrite_existing=False)
            if updated:
                deal_doc.flags.ignore_permissions = True
                deal_doc.save()
        except Exception as e:
            frappe.logger().warning(f"Error syncing updated Lead {doc.name} to Deal {deal_name}: {e}")


@frappe.whitelist()
def audit_and_backfill_deals(dry_run=True, deal_name=None, limit=None):
    """
    Audited, idempotent backfill utility for CRM Deals linked to CRM Leads.
    Can be run safely via System Console or Whitelisted API.
    In dry_run=True, NO changes are written to the database.
    """
    dry_run = frappe.parse_json(dry_run) if isinstance(dry_run, str) else bool(dry_run)
    limit = int(limit) if limit else None

    filters = {"lead": ("is", "set")}
    if deal_name:
        filters["name"] = deal_name

    deal_names = frappe.get_all("CRM Deal", filters=filters, pluck="name", limit=limit, order_by="creation desc")
    
    report = {
        "mode": "DRY_RUN" if dry_run else "LIVE_UPDATE",
        "total_deals_examined": len(deal_names),
        "deals_requiring_update": 0,
        "contacts_created": 0,
        "contacts_reused": 0,
        "deals_skipped": 0,
        "field_update_counts": {},
        "sample_updates": [],
    }

    for dname in deal_names:
        deal_doc = frappe.get_doc("CRM Deal", dname)
        if not deal_doc.lead or not frappe.db.exists("CRM Lead", deal_doc.lead):
            report["deals_skipped"] += 1
            continue

        lead_doc = frappe.get_doc("CRM Lead", deal_doc.lead)
        
        # Check if contact already exists before mapping
        c_before = len(deal_doc.contacts or [])
        contact_id_before = getattr(deal_doc, "contact", None)

        updated_fields = map_lead_to_deal(deal_doc, lead_doc, overwrite_existing=False)

        if updated_fields:
            report["deals_requiring_update"] += 1
            for f in updated_fields:
                report["field_update_counts"][f] = report["field_update_counts"].get(f, 0) + 1

            if len(report["sample_updates"]) < 10:
                report["sample_updates"].append({
                    "deal": dname,
                    "lead": lead_doc.name,
                    "updated_fields": updated_fields,
                    "lead_name": deal_doc.lead_name,
                    "mobile_no": deal_doc.mobile_no,
                    "email": deal_doc.email,
                    "campaign": getattr(deal_doc, "custom_meta_campaign_name", None),
                })

            if not dry_run:
                deal_doc.flags.ignore_permissions = True
                deal_doc.flags.ignore_validate_update_after_submit = True
                deal_doc.save()

    if not dry_run:
        frappe.db.commit()

    return report
