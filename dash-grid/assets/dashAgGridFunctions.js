// Custom JS used from columnDefs via {"function": "slaFlag(params)"}.
// dash-ag-grid ONLY sees functions attached to window.dashAgGridFunctions.
var dagfuncs = (window.dashAgGridFunctions = window.dashAgGridFunctions || {});

dagfuncs.slaFlag = function (params) {
  if (params.value == null) return "";
  return params.value > params.data.sla_ms ? "BREACH" : "ok";
};
