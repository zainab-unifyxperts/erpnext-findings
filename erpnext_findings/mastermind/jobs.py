"""Scheduled jobs: poll Slack -> parse into Findings -> post approved replies."""
import datetime
import json
import time
from collections import defaultdict

import frappe
from frappe.utils import now_datetime

from erpnext_findings.mastermind import evidence, slack
from erpnext_findings.mastermind.constants import FINDING_TYPES
from erpnext_findings.mastermind.diagnose import diagnose
from erpnext_findings.mastermind.parser import is_master_mind, message_text, parse
from erpnext_findings.mastermind.render import finding_block, note_for, render_update

BACKFILL_SECONDS = 3 * 24 * 3600  # first poll only looks back 3 days


def run_cycle():
	"""Single scheduler entry so the three steps always run in order."""
	for step in (poll_slack, parse_pending, post_approved):
		try:
			step()
		except Exception:
			frappe.log_error(title=f"Mastermind {step.__name__} failed")
			frappe.db.rollback()


# ---------------------------------------------------------------- poll
def poll_slack():
	s = frappe.get_single("Mastermind Settings")
	if not s.enable_slack_polling or not s.slack_channel_id:
		return
	# Slack timestamps have exactly 6 decimals; a longer float makes conversations.history return nothing.
	oldest = "%.6f" % float(s.last_processed_timestamp or (time.time() - BACKFILL_SECONDS))
	try:
		msgs = slack.history(s.slack_channel_id, oldest=oldest)
	except Exception as e:
		frappe.db.set_single_value(
			"Mastermind Settings",
			{"last_poll_at": now_datetime(), "last_poll_status": "Failed", "last_poll_error": str(e)[:500]},
		)
		frappe.db.commit()
		raise

	newest = oldest
	for m in sorted(msgs, key=lambda m: float(m["ts"])):
		newest = m["ts"]
		text = message_text(m)
		if not is_master_mind(text) or frappe.db.exists("Mastermind Slack Message", {"slack_message_ts": m["ts"]}):
			continue
		frappe.get_doc(
			{
				"doctype": "Mastermind Slack Message",
				"slack_message_ts": m["ts"],
				"thread_ts": m.get("thread_ts") or "",
				"channel_id": s.slack_channel_id,
				"message_datetime": frappe.utils.convert_utc_to_system_timezone(
					datetime.datetime.utcfromtimestamp(float(m["ts"]))
				).replace(tzinfo=None),
				"message_text": text,
				"parsing_status": "Pending",
			}
		).insert(ignore_permissions=True)

	# Advance the cursor only after every row above is saved.
	frappe.db.set_single_value(
		"Mastermind Settings",
		{
			"last_processed_timestamp": newest,
			"last_poll_at": now_datetime(),
			"last_poll_status": "Success",
			"last_poll_error": "",
		},
	)
	frappe.db.commit()


# ---------------------------------------------------------------- parse
def parse_pending():
	for name in frappe.get_all("Mastermind Slack Message", filters={"parsing_status": "Pending"}, pluck="name"):
		msg = frappe.get_doc("Mastermind Slack Message", name)
		try:
			found, warnings = parse(msg.message_text, FINDING_TYPES)
			created = sum(1 for f in found if create_finding(msg, f))
			msg.findings_count = created
			msg.parsing_status = "Parsed" if found else "No Findings"
			msg.parser_error = "\n".join(warnings)[:1000]
		except Exception as e:
			frappe.db.rollback()
			frappe.log_error(title=f"Mastermind parse failed: {name}")
			msg.parsing_status = "Failed"
			msg.parser_error = str(e)[:1000]
		msg.save(ignore_permissions=True)
		frappe.db.commit()


def create_finding(msg, f):
	"""Returns True when a new Finding was created (False if it already existed)."""
	from erpnext_findings.mastermind.parser import dedupe_key

	if frappe.db.exists("Mastermind Finding", {"dedupe_key": dedupe_key(f["order_id"], f["finding_type"], f["three_pl"])}):
		return False
	doc = frappe.get_doc(
		{
			"doctype": "Mastermind Finding",
			**f,
			"source_message": msg.name,
			"channel_id": msg.channel_id,
			"parent_ts": msg.slack_message_ts,
			"status": "Draft",
		}
	)
	fill_evidence_and_draft(doc)
	doc.insert(ignore_permissions=True)
	return True


def fill_evidence_and_draft(doc):
	"""Collect evidence, diagnose, render the per-order block. Used on create and on Refresh."""
	erp, shop, ext = evidence.collect_all(doc.order_id)
	cause, confidence = diagnose({"finding_type": doc.finding_type}, erp, shop, ext)
	doc.erpnext_evidence = json.dumps(erp, default=str)
	doc.shopify_evidence = json.dumps(shop, default=str)
	doc.extensiv_evidence = json.dumps(ext, default=str)
	doc.evidence_collected_at = now_datetime()
	doc.cause = cause or ""
	doc.cause_confidence = confidence
	doc.draft_text = finding_block(doc.order_id, doc.finding_type, doc.cause, doc.cause_confidence)


# ---------------------------------------------------------------- post
def post_approved():
	"""Post all Approved findings under the same Master Mind message as ONE thread reply."""
	rows = frappe.get_all(
		"Mastermind Finding",
		filters={"status": "Approved"},
		fields=["name", "order_id", "cause", "cause_confidence", "draft_text", "channel_id", "parent_ts"],
	)
	groups = defaultdict(list)
	for r in rows:
		groups[(r.channel_id, r.parent_ts)].append(r)
	if not groups:
		return
	ian_id = frappe.db.get_single_value("Mastermind Settings", "ian_slack_id") or ""

	for (channel, parent_ts), items in groups.items():
		text = render_update(
			[
				{"order_id": r.order_id, "note": note_for(r.cause, r.cause_confidence), "draft_text": r.draft_text}
				for r in items
			],
			ian_id=ian_id,
		)
		try:
			ts = slack.post_thread_reply(channel, parent_ts, text)
		except Exception as e:
			for r in items:
				frappe.db.set_value(
					"Mastermind Finding", r.name, {"status": "Failed", "post_error": str(e)[:500]}
				)
			frappe.db.commit()
			frappe.log_error(title="Mastermind post failed")
			continue
		for r in items:
			frappe.db.set_value(
				"Mastermind Finding",
				r.name,
				{"status": "Posted", "posted_ts": ts, "posted_at": now_datetime(), "post_error": ""},
			)
		frappe.db.commit()

#Added a comment