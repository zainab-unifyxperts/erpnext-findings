"""Rule-based diagnosis from collected evidence. Pure, no frappe imports.

Nothing is guessed: if no rule can confirm a cause, the result is (None, "Unconfirmed")
and the finding cannot be approved.

Evidence shapes (see evidence.py):
  erpnext:  {"sales_order_found": bool, "sales_orders": [{"synced_to_extensiv": 0/1, ...}], ...}
  shopify:  {"collected": bool, "line_items": [{"sku": str}], "fulfilled_at": iso|None, "edited_at": iso|None}
  extensiv: {"collected": bool, "found": bool, "tracking_numbers": [str]}

A source whose "collected" is False is treated as "no information", never as "no problem".
"""


def _collected(ev):
	return bool(ev) and ev.get("collected") is True


def sku_missing(f, erp, shop, ext):
	if f["finding_type"] != "erp_missing" or not _collected(erp) or erp.get("sales_order_found"):
		return False
	return _collected(shop) and any(not (li.get("sku") or "").strip() for li in shop.get("line_items", []))


def no_tracking_on_extensiv(f, erp, shop, ext):
	if f["finding_type"] != "erp_missing":
		return False
	if _collected(shop) and any(not (li.get("sku") or "").strip() for li in shop.get("line_items", [])):
		return False  # the SKU problem explains it first
	return _collected(ext) and ext.get("found") and not ext.get("tracking_numbers")


def edited_after_fulfillment(f, erp, shop, ext):
	if f["finding_type"] != "extensiv_canceled_variant":
		return False
	synced = any(so.get("synced_to_extensiv") for so in erp.get("sales_orders", []))
	edited, fulfilled = shop.get("edited_at"), shop.get("fulfilled_at")
	# ISO-8601 strings in the same format compare correctly as text.
	return synced and _collected(shop) and bool(edited and fulfilled and edited > fulfilled)


RULES = [
	("sku_missing", sku_missing),
	("no_tracking_on_extensiv", no_tracking_on_extensiv),
	("edited_after_fulfillment", edited_after_fulfillment),
]


def diagnose(finding, erp, shop, ext):
	"""Returns (cause_key or None, confidence)."""
	for cause, rule in RULES:
		if rule(finding, erp or {}, shop or {}, ext or {}):
			return cause, "Confirmed"
	return None, "Unconfirmed"