# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Harvester - Debug Message Structure
# MAGIC
# MAGIC Run this first to inspect the raw API response and identify
# MAGIC the correct field names for role, content, and feedback.

# COMMAND ----------

import requests
import json
import os

# COMMAND ----------

dbutils.widgets.text("genie_space_id", "01f0e0353b4c1353b0f07b21c5422977", "Genie Space ID")

SPACE_ID = dbutils.widgets.get("genie_space_id")
workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
BASE = f"https://{workspace_url}/api/2.0"

print(f"Space ID: {SPACE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Inspect raw conversation list response

# COMMAND ----------

r = requests.get(
    f"{BASE}/genie/spaces/{SPACE_ID}/conversations",
    headers=headers,
    params={"page_size": 3},
    timeout=30
)
print(f"HTTP {r.status_code}")
print("--- RAW CONVERSATION LIST (first 3) ---")
print(json.dumps(r.json(), indent=2))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Pick the first conversation and inspect its messages

# COMMAND ----------

data = r.json()
# Try common key names for the list
convs = data.get("conversations") or data.get("items") or data.get("results") or []

if not convs:
    print("ERROR: Could not find conversations in response. Keys present:", list(data.keys()))
else:
    first_conv = convs[0]
    conv_id = first_conv.get("id") or first_conv.get("conversation_id")
    print(f"First conversation ID: {conv_id}")
    print("Conversation object keys:", list(first_conv.keys()))

    # Fetch messages for this conversation
    r2 = requests.get(
        f"{BASE}/genie/spaces/{SPACE_ID}/conversations/{conv_id}/messages",
        headers=headers,
        timeout=30
    )
    print(f"\nMessages HTTP {r2.status_code}")
    msg_data = r2.json()
    print("--- RAW MESSAGE LIST RESPONSE KEYS ---")
    print(list(msg_data.keys()))
    
    # Print full response (truncated for readability)
    raw = json.dumps(msg_data, indent=2)
    print(raw[:5000])
    if len(raw) > 5000:
        print(f"\n... (truncated, total {len(raw)} chars)")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Print each message object individually

# COMMAND ----------

msgs = msg_data.get("messages") or msg_data.get("items") or msg_data.get("results") or []
print(f"Total messages found: {len(msgs)}")

for i, msg in enumerate(msgs):
    print(f"\n{'='*60}")
    print(f"Message {i+1} - ALL KEYS: {list(msg.keys())}")
    print(f"  role-related fields:")
    for k in ["role", "author_role", "author", "type", "message_type", "sender"]:
        if k in msg:
            print(f"    {k}: {msg[k]!r}")
    print(f"  content-related fields:")
    for k in ["content", "text", "query", "message"]:
        if k in msg:
            val = str(msg[k])
            print(f"    {k}: {val[:200]!r}")
    print(f"  attachments present: {'attachments' in msg}, count: {len(msg.get('attachments') or [])}")
    if msg.get("attachments"):
        print(f"  attachment[0] keys: {list((msg['attachments'][0] or {}).keys())}")
    print(f"  feedback-related fields:")
    for k in ["feedback", "rating", "comment", "thumbs"]:
        if k in msg:
            print(f"    {k}: {str(msg[k])[:200]!r}")
