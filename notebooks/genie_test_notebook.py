# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Test Notebook

# COMMAND ----------

import requests
import json
import time
import pandas as pd
from datetime import datetime
import os

# COMMAND ----------

# dbutils.widgets.text("genie_space_id","")
# dbutils.widgets.text("schema_name","")

# COMMAND ----------

CATALOG=os.getenv("DATABRICKS_CATALOG")

# COMMAND ----------

# Configuration
SPACE_ID = dbutils.widgets.get("genie_space_id")
SCHEMA_NAME = dbutils.widgets.get("schema_name")

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Expected Results

# COMMAND ----------

try:
    expected_df = pd.read_csv('/dbfs//FileStore/user_prompt_expectations.csv').dropna()
    print(f"Loaded {len(expected_df)} expected test cases")
except:
    print("ERROR: CSV not found at /dbfs//FileStore/user_prompt_expectations.csv")
    print("Please upload the expected_results.csv file")
    expected_df = pd.DataFrame()

display(expected_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helper Functions

# COMMAND ----------

def start_conversation():
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/start-conversation"
    response = requests.post(url, headers=headers, json={"content": "Starting test"})
    data = response.json()
    return data.get("conversation_id") or data.get("conversation", {}).get("id")

def send_message(conversation_id, prompt):
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages"
    response = requests.post(url, headers=headers, json={"content": prompt})
    data = response.json()
    return data.get("id") or data.get("message", {}).get("id")

def get_message(conversation_id, message_id, max_wait=300):
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages/{message_id}"
    start = time.time()
    while time.time() - start < max_wait:
        response = requests.get(url, headers=headers)
        data = response.json()
        if data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
            return data
        time.sleep(5)
    return None

def get_query_result(conversation_id, message_id, attachment_id):
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
    try:
        response = requests.get(url, headers=headers)
        return response.json() if response.status_code == 200 else None
    except:
        return None

def extract_response(message_data, conversation_id, message_id):
    result = {"analysis": None, "sql": None, "results": None, "status": message_data.get("status")}
    
    for att in message_data.get("attachments", []):
        if "text" in att:
            text = att["text"].get("content", "")
            result["analysis"] = (result["analysis"] or "") + "\n" + text
        
        if "query" in att:
            q = att["query"]
            result["sql"] = q.get("query")
            desc = q.get("description", "")
            result["analysis"] = desc + "\n" + (result["analysis"] or "")
            
            att_id = att.get("attachment_id")
            if att_id:
                qr = get_query_result(conversation_id, message_id, att_id)
                if qr:
                    stmt = qr.get("statement_response", {})
                    cols = [c.get("name") for c in stmt.get("manifest", {}).get("schema", {}).get("columns", [])]
                    data = stmt.get("result", {}).get("data_array")
                    
                    if data and cols:
                        result["results"] = pd.DataFrame(data, columns=cols)
                    else:
                        typed = stmt.get("result", {}).get("data_typed_array", [])
                        if typed:
                            rows = []
                            for row in typed:
                                vals = []
                                for v in row.get("values", []):
                                    vals.append(v.get("str") or v.get("int") or v.get("double") or v.get("bool"))
                                rows.append(vals)
                            if rows and cols:
                                result["results"] = pd.DataFrame(rows, columns=cols)
    
    return result

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Tests

# COMMAND ----------

# DBTITLE 1,Cell 11
conversation_id = start_conversation()
print(f"Started conversation: {conversation_id}\n")

results = []

for idx, row in expected_df.iterrows():
    test_num = idx + 1
    role = row['Role']
    use_case = row['Use Case']
    prompt = row['Prompt']
    expected = row['User Expectation ']
    
    print(f"[{test_num}/{len(expected_df)}] {role} - {use_case}")
    
    try:
        msg_id = send_message(conversation_id, prompt)
        msg_data = get_message(conversation_id, msg_id)
        
        if msg_data:
            extracted = extract_response(msg_data, conversation_id, msg_id)
            
            results.append({
                "test_number": test_num,
                "role": role,
                "use_case": use_case,
                "prompt": prompt,
                "expected_analysis": expected,
                "actual_analysis": extracted["analysis"],
                "sql_query": extracted["sql"],
                "results": extracted["results"].to_string(index=False) if extracted["results"] is not None else None,
                "row_count": len(extracted["results"]) if extracted["results"] is not None else 0,
                "col_count": len(extracted["results"].columns) if extracted["results"] is not None else 0,
                "status": extracted["status"],
                "conversation_id": conversation_id,
                "message_id": msg_id,
                "test_timestamp": datetime.now()
            })
            print(f"  Status: {extracted['status']} | Rows: {results[-1]['row_count']}")
        
    except Exception as e:
        print(f"  ERROR: {str(e)}")
        results.append({
            "test_number": test_num,
            "role": role,
            "use_case": use_case,
            "prompt": prompt,
            "expected_analysis": expected,
            "status": "ERROR",
            "error": str(e),
            "test_timestamp": datetime.now()
        })
    
    time.sleep(2)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Save Results

# COMMAND ----------

# Save to Unity Catalog
results_df = spark.createDataFrame(results)
results_df.display()

# COMMAND ----------

table_name = f"{CATALOG}.{SCHEMA_NAME}.genie_test_results"
results_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(table_name)

print(f"Saved {len(results)} results to {table_name}")

# Display summary
display(spark.table(table_name))
