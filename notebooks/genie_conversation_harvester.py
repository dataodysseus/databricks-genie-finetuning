# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Space Conversation Harvester (Fixed)
# MAGIC
# MAGIC Collects **all conversations** across **all users** for a given Genie Space.
# MAGIC
# MAGIC **Key insight from API inspection:**
# MAGIC Each message object is a self-contained Q&A pair:
# MAGIC - `content`     → the user's question
# MAGIC - `attachments` → Genie's response: query (SQL + description), text (answer), suggested_questions
# MAGIC - `user_id`     → resolved to name/email via SCIM
# MAGIC - `status`      → COMPLETED / FAILED / etc.
# MAGIC
# MAGIC Feedback (thumbs up/down) is fetched separately per message.

# COMMAND ----------

import requests
import json
import time
import pandas as pd
from datetime import datetime
import os

# COMMAND ----------

dbutils.widgets.text("genie_space_id",        "01f0e0353b4c1353b0f07b21c5422977", "Genie Space ID")
dbutils.widgets.text("schema_name",            "",                                  "Target Schema")
dbutils.widgets.text("max_conversations",      "0",                                 "Max conversations (0 = all)")
dbutils.widgets.text("skip_starter_messages",  "true",                              "Skip opener messages (true/false)")

# COMMAND ----------

SPACE_ID      = dbutils.widgets.get("genie_space_id")
SCHEMA_NAME   = dbutils.widgets.get("schema_name")
MAX_CONV      = int(dbutils.widgets.get("max_conversations") or 0)
SKIP_STARTERS = dbutils.widgets.get("skip_starter_messages").lower() == "true"
CATALOG       = os.getenv("DATABRICKS_CATALOG", "hive_metastore")

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}
BASE = f"https://{workspace_url}/api/2.0"

# Synthetic opener messages injected by automated test notebooks — skip these
STARTER_PHRASES = {"starting test", "starting session", "start", "starting test."}

print(f"Workspace : {workspace_url}")
print(f"Space ID  : {SPACE_ID}")
print(f"Catalog   : {CATALOG}.{SCHEMA_NAME}")
print(f"Max convs : {MAX_CONV if MAX_CONV > 0 else 'all'}")
print(f"Skip openers: {SKIP_STARTERS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper: Resolve user_id to name + email via SCIM API

# COMMAND ----------

_user_cache = {}   # user_id (int/str) → (display_name, email)
 
def _extract_user_fields(d):
    """Pull display name + primary email from a SCIM user object."""
    name  = d.get("displayName") or d.get("userName", "")
    email = next(
        (e["value"] for e in d.get("emails", []) if e.get("primary")),
        None
    ) or d.get("userName", "")
    return name, email
 
def _load_all_users_bulk():
    """
    Strategy 1: GET /api/2.0/preview/scim/v2/Users
    Loads all workspace users in one paginated call and populates _user_cache.
    Works when the token has 'read user' permissions (most non-admin tokens do).
    """
    url    = f"https://{workspace_url}/api/2.0/preview/scim/v2/Users"
    params = {"count": 200, "startIndex": 1}
    loaded = 0
    try:
        while True:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code != 200:
                return False
            data      = r.json()
            resources = data.get("Resources", [])
            for u in resources:
                uid = u.get("id")
                if uid:
                    name, email = _extract_user_fields(u)
                    _user_cache[str(uid)] = (name, email)
                    _user_cache[int(uid) if str(uid).isdigit() else uid] = (name, email)
                    loaded += 1
            total = data.get("totalResults", 0)
            start = data.get("startIndex", 1)
            if start + len(resources) - 1 >= total:
                break
            params["startIndex"] = start + len(resources)
        print(f"  [User lookup] Bulk SCIM loaded {loaded} users ✅")
        return True
    except Exception as e:
        print(f"  [User lookup] Bulk SCIM failed: {e}")
        return False
 
def _lookup_single_user(user_id):
    """
    Strategy 2: GET /api/2.0/preview/scim/v2/Users/{id}
    Individual lookup for a specific user ID.
    """
    try:
        r = requests.get(
            f"https://{workspace_url}/api/2.0/preview/scim/v2/Users/{user_id}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            return _extract_user_fields(r.json())
    except Exception:
        pass
    return None, None
 
def _lookup_via_permissions_api(user_id):
    """
    Strategy 3: GET /api/2.0/preview/permissionassignments/principals/{user_id}
    Returns limited info (principalDisplayName) but works for non-admins.
    """
    try:
        r = requests.get(
            f"https://{workspace_url}/api/2.0/preview/permissionassignments/principals/{user_id}",
            headers=headers, timeout=10
        )
        if r.status_code == 200:
            d    = r.json()
            name = d.get("principalDisplayName") or d.get("displayName") or str(user_id)
            # email not available here, use name as best-effort
            return name, name
    except Exception:
        pass
    return str(user_id), str(user_id)
 
# --- Initialise: attempt bulk load once ---
_bulk_loaded = _load_all_users_bulk()
 
def resolve_user(user_id):
    """Return (display_name, email) for a Databricks user_id."""
    if user_id is None:
        return "unknown", "unknown"
 
    # Check cache first (populated by bulk load or previous lookups)
    for key in (user_id, str(user_id)):
        if key in _user_cache:
            return _user_cache[key]
 
    # Strategy 2: individual SCIM lookup
    name, email = _lookup_single_user(user_id)
    if name:
        _user_cache[user_id] = (name, email)
        _user_cache[str(user_id)] = (name, email)
        return name, email
 
    # Strategy 3: permissions API (display name only)
    name, email = _lookup_via_permissions_api(user_id)
    _user_cache[user_id]       = (name, email)
    _user_cache[str(user_id)]  = (name, email)
    return name, email

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper: List all conversations in the space (paginated)

# COMMAND ----------

def list_all_conversations(space_id, max_results=0):
    url    = f"{BASE}/genie/spaces/{space_id}/conversations"
    params = {"page_size": 100}
    result = []

    while True:
        r = requests.get(url, headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            print(f"  [WARN] HTTP {r.status_code}: {r.text[:300]}")
            break
        data  = r.json()
        batch = data.get("conversations", [])
        result.extend(batch)

        next_token = data.get("next_page_token")
        if not next_token:
            break
        if max_results > 0 and len(result) >= max_results:
            break
        params["page_token"] = next_token

    return result[:max_results] if max_results > 0 else result

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper: Get all messages for one conversation

# COMMAND ----------

def list_messages(space_id, conversation_id):
    url = f"{BASE}/genie/spaces/{space_id}/conversations/{conversation_id}/messages"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json().get("messages", [])
    except Exception as e:
        print(f"  [WARN] messages {conversation_id}: {e}")
    return []

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper: Fetch feedback for a message
# MAGIC
# MAGIC Endpoint: GET .../messages/{message_id}/feedback
# MAGIC Returns rating (POSITIVE/NEGATIVE), comment text, and comment_type.

# COMMAND ----------

def get_message_feedback(space_id, conversation_id, message_id):
    url = f"{BASE}/genie/spaces/{space_id}/conversations/{conversation_id}/messages/{message_id}/feedback"
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data  = r.json()
            items = data if isinstance(data, list) else data.get("feedback", [data])
            for item in items:
                if not item:
                    continue
                rating       = item.get("rating") or item.get("feedback_rating")
                comment      = item.get("comment") or item.get("content") or item.get("text")
                comment_type = item.get("comment_type") or item.get("type")
                if rating or comment:
                    return rating, comment, comment_type
    except Exception:
        pass
    return None, None, None

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper: Parse one message → structured record
# MAGIC
# MAGIC **Confirmed message structure from API debug:**
# MAGIC ```
# MAGIC {
# MAGIC   "content":      "<user question>",   ← THE question
# MAGIC   "user_id":      <int>,               ← who asked it
# MAGIC   "status":       "COMPLETED",
# MAGIC   "message_id":   "...",
# MAGIC   "conversation_id": "...",
# MAGIC   "created_timestamp": <epoch ms>,
# MAGIC   "last_updated_timestamp": <epoch ms>,
# MAGIC   "attachments":  [
# MAGIC     { "query": { "query": "<SQL>", "description": "<Genie reasoning>",
# MAGIC                  "query_result_metadata": { "row_count": N } } },
# MAGIC     { "text":  { "content": "<Genie natural language answer>" } },
# MAGIC     { "suggested_questions": { "questions": [...] } }
# MAGIC   ]
# MAGIC }
# MAGIC ```
# MAGIC There is NO role/author field — every message is a user question + Genie response combined.

# COMMAND ----------

def to_dt(ts):
    try:
        return datetime.utcfromtimestamp(int(ts) / 1000) if ts else None
    except Exception:
        return None

def parse_message(msg, conv_title, conv_id, space_id):
    question   = (msg.get("content") or "").strip()
    user_id    = msg.get("user_id")
    status     = msg.get("status")
    message_id = msg.get("message_id") or msg.get("id")
    created_dt = to_dt(msg.get("created_timestamp"))
    updated_dt = to_dt(msg.get("last_updated_timestamp"))

    sql_query           = None
    genie_description   = None   # Genie's reasoning / description of the SQL
    genie_answer_texts  = []     # Natural language answer paragraphs
    row_count           = None
    suggested_questions = []

    for att in msg.get("attachments") or []:
        if "query" in att:
            q = att["query"]
            sql_query         = q.get("query")
            genie_description = (q.get("description") or "").strip() or None
            meta              = q.get("query_result_metadata") or {}
            row_count         = meta.get("row_count")

        if "text" in att:
            txt = (att["text"].get("content") or "").strip()
            if txt:
                genie_answer_texts.append(txt)

        if "suggested_questions" in att:
            suggested_questions = att["suggested_questions"].get("questions", [])

    # Combine full Genie response: description first, then text answers
    full_answer_parts = []
    if genie_description:
        full_answer_parts.append(genie_description)
    full_answer_parts.extend(genie_answer_texts)
    genie_answer = "\n\n".join(full_answer_parts) or None

    # Fetch feedback
    rating, comment, comment_type = get_message_feedback(space_id, conv_id, message_id)

    return {
        "space_id":               space_id,
        "conversation_id":        conv_id,
        "conversation_title":     conv_title,
        "message_id":             message_id,
        "question_timestamp":     created_dt,
        "last_updated":           updated_dt,
        "user_id":                user_id,
        "user_display_name":      None,     # resolved below
        "user_email":             None,
        "question":               question,
        "genie_description":      genie_description,
        "genie_answer":           genie_answer,
        "sql_query":              sql_query,
        "result_row_count":       row_count,
        "suggested_questions":    ", ".join(suggested_questions) if suggested_questions else None,
        "status":                 status,
        "feedback_rating":        rating,         # POSITIVE / NEGATIVE / None
        "feedback_comment":       comment,
        "feedback_comment_type":  comment_type,  # REQUEST_COMMENT / THUMBS_DOWN_COMMENT / REVIEW_COMMENT
        "auto_regenerate_count":  msg.get("auto_regenerate_count"),
    }

# COMMAND ----------

# MAGIC %md
# MAGIC ## Main: Harvest All Conversations

# COMMAND ----------

print("=" * 70)
print(f"Starting harvest — Space: {SPACE_ID}")
print("=" * 70)

print("\n[1/3] Listing all conversations...")
conversations = list_all_conversations(SPACE_ID, max_results=MAX_CONV)
print(f"  Found {len(conversations)} conversation(s)")

print("\n[2/3] Fetching and parsing messages...")
all_records = []
skipped     = 0

for i, conv in enumerate(conversations, 1):
    conv_id    = conv.get("conversation_id") or conv.get("id")
    conv_title = conv.get("title", "(untitled)")

    if i == 1 or i % 25 == 0:
        print(f"  [{i}/{len(conversations)}] {conv_id}  title={conv_title!r}")

    messages = list_messages(SPACE_ID, conv_id)

    for msg in messages:
        question = (msg.get("content") or "").strip()

        # Skip synthetic opener messages from the test notebook
        if SKIP_STARTERS and question.lower().rstrip(".") in STARTER_PHRASES:
            skipped += 1
            continue

        # Skip empty content
        if not question:
            skipped += 1
            continue

        record = parse_message(msg, conv_title, conv_id, SPACE_ID)

        # Resolve user_id → display name + email (cached)
        name, email = resolve_user(record["user_id"])
        record["user_display_name"] = name
        record["user_email"]        = email

        all_records.append(record)

    time.sleep(0.15)   # gentle rate limiting

print(f"\n  ✅ Records extracted : {len(all_records)}")
print(f"  ⏭  Skipped (openers) : {skipped}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Preview Results

# COMMAND ----------

if all_records:
    result_df = pd.DataFrame(all_records)

    col_order = [
        "question_timestamp", "user_display_name", "user_email",
        "conversation_id", "conversation_title",
        "question", "genie_description", "genie_answer", "sql_query",
        "result_row_count", "status",
        "feedback_rating", "feedback_comment", "feedback_comment_type",
        "suggested_questions", "auto_regenerate_count",
        "message_id", "user_id", "space_id", "last_updated"
    ]
    result_df = result_df[[c for c in col_order if c in result_df.columns]]
    display(result_df)
else:
    print("No records found. Verify SPACE_ID widget and permissions.")

# COMMAND ----------

sdf = spark.createDataFrame(result_df)
sdf.createOrReplaceTempView("messages")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM messages LIMIT 2;

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary Statistics

# COMMAND ----------

if all_records:
    total       = len(all_records)
    uniq_users  = result_df["user_email"].nunique()
    with_sql    = result_df["sql_query"].notna().sum()
    with_fb     = result_df["feedback_rating"].notna().sum()
    thumbs_up   = (result_df["feedback_rating"] == "POSITIVE").sum()
    thumbs_down = (result_df["feedback_rating"] == "NEGATIVE").sum()

    print("=" * 55)
    print(f"  Total Q&A records      : {total}")
    print(f"  Unique users           : {uniq_users}")
    print(f"  Responses with SQL     : {with_sql}  ({100*with_sql//total}%)")
    print(f"  Responses with feedback: {with_fb}")
    print(f"    👍  Positive          : {thumbs_up}")
    print(f"    👎  Negative          : {thumbs_down}")
    print("=" * 55)

    print("\nQuestions per user:")
    display(
        result_df.groupby(["user_display_name", "user_email"])
                 .agg(
                     question_count  = ("question", "count"),
                     with_feedback   = ("feedback_rating", lambda x: x.notna().sum()),
                     thumbs_up       = ("feedback_rating", lambda x: (x == "POSITIVE").sum()),
                     thumbs_down     = ("feedback_rating", lambda x: (x == "NEGATIVE").sum()),
                 )
                 .reset_index()
                 .sort_values("question_count", ascending=False)
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Save to Unity Catalog

# COMMAND ----------

if all_records and SCHEMA_NAME:
    save_df = result_df.copy()
    # Spark needs datetime columns as strings or proper types
    for col in ["question_timestamp", "last_updated"]:
        if col in save_df.columns:
            save_df[col] = save_df[col].astype(str)

    spark_df = spark.createDataFrame(save_df)
    table    = f"{CATALOG}.{SCHEMA_NAME}.genie_space_conversations"

    spark_df.write \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .saveAsTable(table)

    print(f"✅  Saved {len(all_records)} records → {table}")
    display(spark.table(table))

elif not SCHEMA_NAME:
    print("ℹ️  Set the 'schema_name' widget to save results to Unity Catalog.")
else:
    print("Nothing to save.")
