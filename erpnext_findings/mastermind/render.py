"""Render Jaden's update. Pure functions, no frappe imports."""
from erpnext_findings.mastermind.constants import CAUSES, FINDING_TYPES, ON_BEHALF


def note_for(cause, confidence):
	if not cause or cause not in CAUSES:
		return "Needs investigation - cause not confirmed"
	return CAUSES[cause]["note"] + ("" if confidence == "Confirmed" else " (unconfirmed)")


def finding_block(order_id, finding_type, cause, confidence):
	"""The per-order explanation. Stored in draft_text and editable before approval."""
	t = FINDING_TYPES[finding_type]
	if cause in CAUSES:
		c = CAUSES[cause]
		what, why, fix = c["what"], c["why"], c["fix"]
	else:
		what, why, fix = t["headline"] + ".", "Root cause not confirmed yet.", t["next_step"]
	return "\n".join(
		[
			f"*{order_id}* — {note_for(cause, confidence)}",
			f"   What happened: {what}",
			f"   Why: {why}",
			f"   Fix: {fix}  (Owner: {t['owner']})",
		]
	)


def mention(slack_id, fallback):
	return f"<@{slack_id}>" if slack_id else fallback


def render_update(rows, ian_id="", title="ERP/sync issues - Explanation"):
	"""rows: dicts with order_id, note, draft_text (one per approved finding in one thread)."""
	rows = sorted(rows, key=lambda r: r["order_id"])
	w = max(len(r["order_id"]) for r in rows + [{"order_id": "Order Id"}])
	table = "\n".join(
		[f"{'Order Id':<{w}}  Note"] + [f"{r['order_id']:<{w}}  {r['note']}" for r in rows]
	)
	blocks = "\n\n".join(r["draft_text"] for r in rows)
	return f"```\n{table}\n```\n{mention(ian_id, 'Ian')} {title}\n\n{blocks}\n\n{ON_BEHALF}"
