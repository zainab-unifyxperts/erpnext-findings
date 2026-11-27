"""Parse Master Mind Slack messages. Pure functions, no frappe imports."""
import hashlib
import re

AUTOREPLY_ITEM = re.compile(
	r"\*?(US\d{4,6})\*?\s*—\s*(.+?)\s*\((NEVER|PENDING|NEEDS_REVIEW|SAFE|OK)\s*·\s*(\w+)\)"
)
TRACKING_MSG = re.compile(
	r"Tracking change needs review \(retail\)\s*—\s*(US\d+)\s*Reason:\s*(\S+)\s*"
	r"Customer sees on Shopify:\s*(\S+)\s*3PL latest:\s*(\S+)",
	re.S,
)


def dedupe_key(order_id, finding_type, three_pl):
	"""Same order flagged by two different 3PLs stays two findings."""
	return hashlib.sha1(f"{order_id}:{finding_type}:{three_pl}".encode()).hexdigest()[:10]


def collect_text(node):
	"""Slack keeps some message text only in blocks/attachments; gather every text string."""
	out = []
	if isinstance(node, dict):
		for k, v in node.items():
			if k in ("text", "fallback") and isinstance(v, str):
				out.append(v)
			else:
				out += collect_text(v)
	elif isinstance(node, list):
		for v in node:
			out += collect_text(v)
	return out


def message_text(msg):
	text = msg.get("text") or ""
	if len(text.strip()) < 20:
		text = "\n".join(collect_text([msg.get("blocks", []), msg.get("attachments", [])]))
	return text


def is_master_mind(text):
	return ":rotating_light:" in text or "Tracking change needs review" in text


def parse(text, known_types):
	"""Returns (findings, warnings). Each finding is a plain dict.

	known_types: finding types we can draft; others are reported as warnings, not guessed.
	"""
	findings, warnings = [], []
	for chunk in re.split(r"(?=:rotating_light:)", text):
		items = list(AUTOREPLY_ITEM.finditer(chunk))
		if not items:
			continue
		pl = re.search(r"(\w+) Shipping autoreply", chunk)
		run = re.search(r"Run `?([^\s`]+)`?", chunk)
		three_pl = pl.group(1) if pl else "UNASSIGNED"
		declared = re.search(r"—\s*(\d+) 3PL coordination items", chunk)
		if declared and int(declared.group(1)) != len(items):
			warnings.append(
				f"{three_pl} message says {declared.group(1)} items but only {len(items)} matched"
			)
		for i, m in enumerate(items):
			end = items[i + 1].start() if i + 1 < len(items) else len(chunk)
			age = re.search(r"(\d+)d overdue", chunk[m.end():end])
			order, _headline, tag, ftype = m.groups()
			if ftype not in known_types:
				warnings.append(f"{order}: finding type {ftype!r} is not configured")
				continue
			findings.append(
				{
					"order_id": order,
					"finding_type": ftype,
					"tag": tag,
					"three_pl": three_pl if three_pl in ("PPAK", "PSI") else "UNASSIGNED",
					"days_overdue": int(age.group(1)) if age else None,
					"run_id": run.group(1) if run else "",
				}
			)
	for m in TRACKING_MSG.finditer(text):
		warnings.append(f"{m.group(1)}: tracking_change seen, not drafted (no reply format yet)")
	return findings, warnings