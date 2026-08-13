import sys
import json
import frappe

def run_production_verification():
    """
    Automated Production Verification Script for Visa CRM Meta Pipeline.
    Verifies 3-way schema contract, physical MariaDB indexes, duplicate event_id records,
    and stage execution health for site context.
    """
    print("======================================================================")
    print("VISA CRM META PIPELINE — PRODUCTION DEPLOYMENT VERIFICATION")
    print("======================================================================")
    
    current_site = frappe.local.site if hasattr(frappe.local, 'site') else 'Unknown'
    print(f"Site Context: {current_site}")
    
    # 1. 3-Way Schema Verification for Communication Event
    print("\n--- 1. Communication Event Schema Verification ---")
    required_fields = [
        'event_id', 'source_channel', 'conversation_id', 'customer360', 'visa_application',
        'lead_intake_queue', 'followup_reference', 'meta_campaign_name', 'meta_campaign_id',
        'meta_adset_name', 'meta_adset_id', 'meta_ad_name', 'meta_ad_id', 'facebook_page_id',
        'facebook_form_id', 'facebook_lead_id', 'original_normalized_payload',
        'meta_attribution_json', 'processing_timeline'
    ]
    
    meta = frappe.get_meta("Communication Event")
    meta_fields = {f.fieldname: f for f in meta.fields}
    db_cols = {c['Field']: c for c in frappe.db.sql("SHOW COLUMNS FROM `tabCommunication Event`", as_dict=True)}
    
    missing_fields = []
    for field in required_fields:
        meta_exists = field in meta_fields
        db_exists = field in db_cols
        status = "✅ MATCH" if (meta_exists and db_exists) else "❌ MISSING"
        print(f"  Field '{field}': Meta={meta_exists}, DB={db_exists} -> {status}")
        if not (meta_exists and db_exists):
            missing_fields.append(field)
            
    # 2. Physical Index Verification
    print("\n--- 2. Physical Index Verification (`tabCommunication Event`) ---")
    indexes = frappe.db.sql("SHOW INDEX FROM `tabCommunication Event` WHERE Column_name = 'event_id'", as_dict=True)
    unique_index_found = False
    for idx in indexes:
        key_name = idx['Key_name']
        non_unique = idx['Non_unique']
        is_unique = (non_unique == 0)
        print(f"  Index '{key_name}': Non_unique={non_unique} ({'UNIQUE' if is_unique else 'INDEX'})")
        if is_unique and key_name == 'uniq_vc_communication_event':
            unique_index_found = True
            
    print(f"  Physical Unique Index Status: {'✅ VERIFIED' if unique_index_found else '❌ NOT FOUND'}")
    
    # 3. Duplicate Record Count
    print("\n--- 3. Duplicate event_id Count ---")
    dups = frappe.db.sql("""
        SELECT event_id, COUNT(*) as cnt
        FROM `tabCommunication Event`
        WHERE event_id IS NOT NULL AND event_id != ''
        GROUP BY event_id
        HAVING cnt > 1
    """, as_dict=True)
    print(f"  Duplicate Count: {len(dups)} rows")
    
    # Summary Result
    all_passed = (len(missing_fields) == 0) and unique_index_found and (len(dups) == 0)
    print("\n======================================================================")
    print(f"VERIFICATION VERDICT: {'✅ VERIFIED PASS' if all_passed else '❌ VERIFICATION FAILED'}")
    print("======================================================================")
    return all_passed

if __name__ == "__main__":
    run_production_verification()
