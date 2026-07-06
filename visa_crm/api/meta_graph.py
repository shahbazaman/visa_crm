import frappe,requests

def get_page_access_token():
    name=frappe.get_all("Meta Settings",pluck="name",limit=1)[0]
    s=frappe.get_doc("Meta Settings",name)
    return s.get_password("access_token")

def fetch_lead(leadgen_id):
    token=get_page_access_token()
    url=f"https://graph.facebook.com/v23.0/{leadgen_id}"
    params={"access_token":token}
    r=requests.get(url,params=params,timeout=30)
    frappe.log_error("META LEAD FETCH",r.text)
    if r.status_code!=200:
        return None
    return r.json()