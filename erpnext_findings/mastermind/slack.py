"""Minimal Slack Web API client using the bot token stored in Mastermind Settings."""
import frappe
import requests

API = "https://slack.com/api/"


class SlackError(Exception):
	pass


def _call(method, token, http="post", **params):
	fn = requests.post if http == "post" else requests.get
	kw = {"data": params} if http == "post" else {"params": params}
	r = fn(API + method, headers={"Authorization": f"Bearer {token}"}, timeout=30, **kw)
	r.raise_for_status()
	data = r.json()
	if not data.get("ok"):
		raise SlackError(f"{method}: {data.get('error')}")
	return data


def token():
	t = frappe.get_single("Mastermind Settings").get_password("slack_bot_token", raise_exception=False)
	if not t:
		raise SlackError("Slack bot token is not set in Mastermind Settings")
	return t


def history(channel, oldest=None, limit=200):
	params = {"channel": channel, "limit": limit}
	if oldest:
		params["oldest"] = oldest
	return _call("conversations.history", token(), http="get", **params)["messages"]


def post_thread_reply(channel, thread_ts, text):
	return _call("chat.postMessage", token(), channel=channel, thread_ts=thread_ts, text=text)["ts"]
