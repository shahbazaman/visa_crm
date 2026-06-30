frappe.query_reports["Lead Score Trend"] = {
  filters: [
    {
      fieldname: "lead",
      label: __("Lead"),
      fieldtype: "Link",
      options: "Lead",
      reqd: 1,
    },
  ],
};
