frappe.query_reports["Production Diagnostics"] = {
  filters: [],
  formatter(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);
    if (column.fieldname === "status") {
      const color = data.status === "Healthy" ? "green" : data.status === "Warning" ? "orange" : "red";
      return `<span class="indicator-pill ${color}">${value}</span>`;
    }
    return value;
  }
};
