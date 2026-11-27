"""Taxonomy copied from the Master Mind messages and from Jaden's hand-written notes.

Pure data, no frappe imports, so it can be unit-tested anywhere.
"""

TAG_LEGEND = (
	"NEVER=blocked internally · PENDING=normal wait · "
	"NEEDS_REVIEW=conflict, needs a human · SAFE=auto-fixing · OK=no action needed"
)

ON_BEHALF = "_Sent by the pipeline on behalf of Jaden — reply here if anything is wrong._"

# Finding types we draft replies for. tracking_change is parsed but not drafted:
# we do not yet know what Jaden replies to it.
FINDING_TYPES = {
	"erp_missing": {
		"headline": "Stuck before it even reached our order system",
		"owner": "Manan",
		"next_step": "Manan needs to manually create the order record in our system.",
	},
	"extensiv_canceled_variant": {
		"headline": "Warehouse cancelled part of this order without us knowing why",
		"owner": "Manan+Jon",
		"next_step": (
			"Manan and Jon must check the warehouse side and confirm what happened, "
			"then re-route or re-create the order if needed."
		),
	},
}

# Root causes Jaden works out by hand today. Only three are known so far.
CAUSES = {
	"sku_missing": {
		"type": "erp_missing",
		"note": "Shopify Item does not contain SKU",
		"what": "The Shopify order never became an ERPNext Sales Order.",
		"why": (
			"Sales Order creation fails when a Shopify line item has no SKU / item code "
			"(wiki: Order Syncing and Validation, common issues)."
		),
		"fix": (
			"Add the SKU on the Shopify line item; the 10-minute poll then creates the Sales Order, "
			"or create it manually."
		),
	},
	"no_tracking_on_extensiv": {
		"type": "erp_missing",
		"note": "No Tracking number on Extensiv",
		"what": "The order is flagged as missing in ERP and Extensiv has no tracking number for it.",
		"why": (
			"Fulfillment only completes once Extensiv returns tracking (hourly poll), "
			"so nothing moves on the ERP/Shopify side until then."
		),
		"fix": "Ask the 3PL to confirm shipment and add tracking on Extensiv.",
	},
	"edited_after_fulfillment": {
		"type": "extensiv_canceled_variant",
		"note": "Order Edited on Shopify after order fulfillment",
		"what": "Shopify, ERPNext and Extensiv no longer agree on the line items.",
		"why": (
			"The order was edited on Shopify after it was sent to / fulfilled by Extensiv. Per the CS SOP, "
			"once 'Synced to Extensiv' is checked the ERPNext Sales Order must not be changed; "
			"Extensiv has to make the edit."
		),
		"fix": "Confirm with Extensiv which lines were cancelled, then re-route or re-create the order.",
	},
}
