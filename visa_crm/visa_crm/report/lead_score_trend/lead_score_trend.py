import frappe


def execute(filters=None):
    filters = frappe._dict(filters or {})

    columns = [
        {
            "label": "Date",
            "fieldname": "creation",
            "fieldtype": "Datetime",
            "width": 180,
        },
        {
            "label": "Score",
            "fieldname": "score",
            "fieldtype": "Int",
            "width": 120,
        },
    ]

    if not filters.get("lead"):
        return columns, []

    data = frappe.db.sql(
        """
        SELECT
            creation,
            score
        FROM
            `tabLead Score History`
        WHERE
            lead = %s
        ORDER BY
            creation
        """,
        (filters.lead,),
        as_dict=True,
    )

    return columns, data
