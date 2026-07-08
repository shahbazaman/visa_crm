import frappe
from visa_crm.api.customer import find_customer,find_lead

def auto_link(doc,method=None):

    phone=doc.phone
    email=doc.email

    customer=find_customer(phone,email)

    if customer:
        doc.customer=customer

    lead=find_lead(phone,email)

    if lead:
        doc.lead=lead
