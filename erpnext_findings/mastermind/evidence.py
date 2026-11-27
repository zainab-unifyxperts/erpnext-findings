"""Evidence collectors. Read-only: nothing here writes to ERPNext, Shopify or Extensiv.

ERPNext is implemented against the real Sales Order fields. Shopify and Extensiv are
placeholders until we read the existing client functions (see TODOs); until then they
report collected=False, which the diagnosis rules treat as "no information".
"""
import frappe
from frappe.utils import add_days, nowdate

SO_FIELDS = [
	"name",
	"docstatus",
	"status",
	"delivery_status",
	"marketplace_order_id",
	"custom_shopify_order_id_number",
	"custom_3pl_provider",
	"custom_nearest_warehouse",
	"custom_synced_to_extensiv",
	"custom_ack_failed",
	"modified",
]


def _existing(doctype, fields):
	"""Only the fields this site actually has. Custom fields differ between sites
	(for example a local bench without the Alphard apps)."""
	meta = frappe.get_meta(doctype)
	return [f for f in fields if f in ("name", "docstatus", "modified", "creation") or meta.has_field(f)]


def collect_erpnext(order_id):
	if not frappe.get_meta("Sales Order").has_field("marketplace_order_id"):
		return {
			"collected": False,
			"sales_order_found": False,
			"reason": "Sales Order has no marketplace_order_id field on this site",
			"sales_orders": [],
			"error_logs": [],
		}
	so_fields = _existing("Sales Order", SO_FIELDS)
	sos = frappe.get_all(
		"Sales Order",
		filters={"marketplace_order_id": order_id, "docstatus": ["<", 2]},
		fields=so_fields,
		order_by="creation desc",
	)
	item_fields = _existing(
		"Sales Order Item",
		["item_code", "qty", "warehouse", "custom_shopify_line_item_id", "custom_extensiv_order_item_id"],
	)
	out = {
		"collected": True,
		"sales_order_found": bool(sos),
		"sales_orders": [],
		"missing_fields": sorted(set(SO_FIELDS) - set(so_fields)),
	}
	for so in sos:
		items = frappe.get_all("Sales Order Item", filters={"parent": so.name}, fields=item_fields)
		dns = frappe.get_all(
			"Delivery Note Item",
			filters={"against_sales_order": so.name},
			fields=["parent"],
			distinct=True,
		)
		dn_docs = frappe.get_all(
			"Delivery Note",
			filters={"name": ["in", [d.parent for d in dns] or [""]]},
			fields=["name", "status", "docstatus", "modified"],
		)
		out["sales_orders"].append(
			{
				"name": so.name,
				"status": so.get("status"),
				"delivery_status": so.get("delivery_status"),
				"shopify_order_gid": so.get("custom_shopify_order_id_number"),
				"provider": so.get("custom_3pl_provider"),
				"warehouse": so.get("custom_nearest_warehouse"),
				"synced_to_extensiv": int(so.get("custom_synced_to_extensiv") or 0),
				"ack_failed": int(so.get("custom_ack_failed") or 0),
				"modified": str(so.modified),
				"items": [dict(i) for i in items],
				"delivery_notes": [dict(d, modified=str(d.modified)) for d in dn_docs],
			}
		)
	# Failed syncs leave an Error Log entry that mentions the order id.
	logs = frappe.get_all(
		"Error Log",
		filters={"error": ["like", f"%{order_id}%"], "creation": [">", add_days(nowdate(), -30)]},
		fields=["name", "method", "creation"],
		order_by="creation desc",
		limit=5,
	)
	out["error_logs"] = [{"name": l.name, "method": l.method, "creation": str(l.creation)} for l in logs]
	return out


def collect_shopify(order_id, erp):
	# TODO: needs shopify_selling_utils.get_current_shopify_order_items(shopify_order_id) and the
	# GraphQL call that returns fulfillment / edit times. Waiting to read their code before using them.
	return {"collected": False, "reason": "Shopify client not wired yet"}


def collect_extensiv(order_id, erp):
	# TODO: needs extensiv_setup.shopify_fulfillment_sync.get_all_orders_via_rql / fetch_order_from_extensiv.
	return {"collected": False, "reason": "Extensiv client not wired yet"}


def collect_all(order_id):
	erp = collect_erpnext(order_id)
	return erp, collect_shopify(order_id, erp), collect_extensiv(order_id, erp)