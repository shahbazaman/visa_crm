import frappe

def execute():
    """
    Ensure Meta Settings.access_token field length is 1000 and physical MariaDB column is TEXT.
    Fails loudly if database column modification fails.
    Idempotent and safe to run multiple times.
    """
    if frappe.db.exists("DocType", "Meta Settings"):
        # Commit pending transaction before running DDL ALTER TABLE
        frappe.db.commit()
        
        # Modify database column directly
        frappe.db.sql("ALTER TABLE `tabMeta Settings` MODIFY COLUMN `access_token` TEXT")
        
        # Update DocField metadata
        frappe.db.sql("""
            UPDATE `tabDocField`
            SET `length` = 1000
            WHERE `parent` = 'Meta Settings' AND `fieldname` = 'access_token'
        """)
            
        frappe.clear_cache(doctype="Meta Settings")
        frappe.db.commit()
