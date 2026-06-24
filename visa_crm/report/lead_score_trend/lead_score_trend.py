def execute(filters=None):

    columns=[

        {
            "label":"Date",
            "fieldname":"creation",
            "fieldtype":"Datetime"
        },

        {
            "label":"Score",
            "fieldname":"score",
            "fieldtype":"Int"
        }

    ]


    data=frappe.db.sql("""

    select

        creation,

        score


    from

        `tabLead Score History`


    where

        lead=%s


    order by creation


    """,

    filters.lead,

    as_dict=1

    )

    return columns,data