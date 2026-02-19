# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Test Notebook with Performance Metrics

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
# MAGIC ## Helper Functions with Timing

# COMMAND ----------

def start_conversation():
    """Start a new Genie conversation"""
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/start-conversation"
    
    start_time = time.time()
    response = requests.post(url, headers=headers, json={"content": "Starting test"})
    api_latency = time.time() - start_time
    
    data = response.json()
    conversation_id = data.get("conversation_id") or data.get("conversation", {}).get("id")
    
    return conversation_id, api_latency

def send_message(conversation_id, prompt):
    """Send a message to Genie conversation and measure latency"""
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages"
    
    start_time = time.time()
    response = requests.post(url, headers=headers, json={"content": prompt})
    api_latency = time.time() - start_time
    
    data = response.json()
    message_id = data.get("id") or data.get("message", {}).get("id")
    
    return message_id, api_latency

def get_message(conversation_id, message_id, max_wait=300):
    """
    Poll for message completion and track timing metrics
    Returns: (message_data, polling_metrics)
    """
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages/{message_id}"
    
    start_time = time.time()
    poll_count = 0
    poll_latencies = []
    
    while time.time() - start_time < max_wait:
        poll_start = time.time()
        response = requests.get(url, headers=headers)
        poll_latency = time.time() - poll_start
        poll_latencies.append(poll_latency)
        poll_count += 1
        
        data = response.json()
        status = data.get("status")
        
        if status in ["COMPLETED", "FAILED", "CANCELLED"]:
            total_wait_time = time.time() - start_time
            
            metrics = {
                "total_wait_time": total_wait_time,
                "poll_count": poll_count,
                "avg_poll_latency": sum(poll_latencies) / len(poll_latencies) if poll_latencies else 0,
                "min_poll_latency": min(poll_latencies) if poll_latencies else 0,
                "max_poll_latency": max(poll_latencies) if poll_latencies else 0,
                "total_poll_time": sum(poll_latencies)
            }
            
            return data, metrics
        
        time.sleep(5)  # Poll interval
    
    # Timeout case
    timeout_metrics = {
        "total_wait_time": max_wait,
        "poll_count": poll_count,
        "avg_poll_latency": sum(poll_latencies) / len(poll_latencies) if poll_latencies else 0,
        "min_poll_latency": min(poll_latencies) if poll_latencies else 0,
        "max_poll_latency": max(poll_latencies) if poll_latencies else 0,
        "total_poll_time": sum(poll_latencies),
        "timeout": True
    }
    
    return None, timeout_metrics

def get_query_result(conversation_id, message_id, attachment_id):
    """Fetch query results with timing"""
    url = f"https://{workspace_url}/api/2.0/genie/spaces/{SPACE_ID}/conversations/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
    
    start_time = time.time()
    try:
        response = requests.get(url, headers=headers)
        fetch_latency = time.time() - start_time
        
        if response.status_code == 200:
            return response.json(), fetch_latency
        return None, fetch_latency
    except:
        return None, time.time() - start_time

def extract_response(message_data, conversation_id, message_id):
    """Extract response with data size metrics"""
    result = {
        "analysis": None, 
        "sql": None, 
        "results": None, 
        "status": message_data.get("status"),
        "result_fetch_latency": 0,
        "result_bytes": 0
    }
    
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
                qr, fetch_latency = get_query_result(conversation_id, message_id, att_id)
                result["result_fetch_latency"] = fetch_latency
                
                if qr:
                    # Calculate approximate result size
                    result["result_bytes"] = len(json.dumps(qr))
                    
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
# MAGIC ## Run Tests with Performance Tracking

# COMMAND ----------

# Start conversation with timing
conversation_start_time = time.time()
conversation_id, conversation_start_latency = start_conversation()
print(f"Started conversation: {conversation_id}")
print(f"Conversation start latency: {conversation_start_latency:.3f}s\n")

results = []
metrics = []

test_suite_start_time = time.time()

for idx, row in expected_df.iterrows():
    test_num = idx + 1
    role = row['Role']
    use_case = row['Use Case']
    prompt = row['Prompt']
    expected = row['User Expectation ']
    
    print(f"[{test_num}/{len(expected_df)}] {role} - {use_case}")
    
    # Track end-to-end timing for this test
    test_start_time = time.time()
    
    try:
        # Send message with timing
        msg_id, send_latency = send_message(conversation_id, prompt)
        
        # Get response with polling metrics
        msg_data, poll_metrics = get_message(conversation_id, msg_id)
        
        if msg_data:
            # Extract response with result fetch timing
            extracted = extract_response(msg_data, conversation_id, msg_id)
            
            # Calculate end-to-end latency
            end_to_end_latency = time.time() - test_start_time
            
            # Store results (same as before)
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
            
            # Store detailed performance metrics
            metrics.append({
                "test_number": int(test_num),
                "role": str(role),
                "use_case": str(use_case),
                "prompt": str(prompt),
                "prompt_length_chars": int(len(prompt)),
                "prompt_length_words": int(len(prompt.split())),
                
                # Latency metrics (in seconds) - explicitly cast to float
                "send_message_latency": float(send_latency),
                "total_wait_time": float(poll_metrics["total_wait_time"]),
                "result_fetch_latency": float(extracted["result_fetch_latency"]),
                "end_to_end_latency": float(end_to_end_latency),
                
                # Polling metrics
                "poll_count": int(poll_metrics["poll_count"]),
                "avg_poll_latency": float(poll_metrics["avg_poll_latency"]),
                "min_poll_latency": float(poll_metrics["min_poll_latency"]),
                "max_poll_latency": float(poll_metrics["max_poll_latency"]),
                "total_poll_time": float(poll_metrics["total_poll_time"]),
                
                # Response size metrics
                "result_bytes": int(extracted["result_bytes"]),
                "row_count": int(len(extracted["results"]) if extracted["results"] is not None else 0),
                "col_count": int(len(extracted["results"].columns) if extracted["results"] is not None else 0),
                "analysis_length_chars": int(len(extracted["analysis"]) if extracted["analysis"] else 0),
                "sql_length_chars": int(len(extracted["sql"]) if extracted["sql"] else 0),
                
                # Throughput metrics (calculated) - explicitly cast to float
                "rows_per_second": float((len(extracted["results"]) / end_to_end_latency) if extracted["results"] is not None and end_to_end_latency > 0 else 0.0),
                "bytes_per_second": float((extracted["result_bytes"] / end_to_end_latency) if end_to_end_latency > 0 else 0.0),
                
                # Status and IDs
                "status": str(extracted["status"]),
                "conversation_id": str(conversation_id),
                "message_id": str(msg_id),
                "test_timestamp": datetime.now(),
                "error": None
            })
            
            print(f"  Status: {extracted['status']} | Rows: {results[-1]['row_count']}")
            print(f"  End-to-End Latency: {end_to_end_latency:.2f}s | Wait Time: {poll_metrics['total_wait_time']:.2f}s | Polls: {poll_metrics['poll_count']}")
        
    except Exception as e:
        print(f"  ERROR: {str(e)}")
        
        # Still record what we can measure
        error_latency = time.time() - test_start_time
        
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
        
        metrics.append({
            "test_number": int(test_num),
            "role": str(role),
            "use_case": str(use_case),
            "prompt": str(prompt),
            "prompt_length_chars": int(len(prompt)),
            "prompt_length_words": int(len(prompt.split())),
            "send_message_latency": None,
            "total_wait_time": None,
            "result_fetch_latency": None,
            "end_to_end_latency": float(error_latency),
            "poll_count": None,
            "avg_poll_latency": None,
            "min_poll_latency": None,
            "max_poll_latency": None,
            "total_poll_time": None,
            "result_bytes": None,
            "row_count": None,
            "col_count": None,
            "analysis_length_chars": None,
            "sql_length_chars": None,
            "rows_per_second": None,
            "bytes_per_second": None,
            "status": "ERROR",
            "conversation_id": str(conversation_id),
            "message_id": None,
            "test_timestamp": datetime.now(),
            "error": str(e)
        })
    
    time.sleep(2)  # Brief pause between tests

# Calculate overall test suite metrics
test_suite_duration = time.time() - test_suite_start_time
total_tests = len(expected_df)
successful_tests = len([r for r in results if r.get("status") == "COMPLETED"])

print(f"\n{'='*60}")
print(f"TEST SUITE SUMMARY")
print(f"{'='*60}")
print(f"Total Tests: {total_tests}")
print(f"Successful: {successful_tests}")
print(f"Failed: {total_tests - successful_tests}")
print(f"Total Duration: {test_suite_duration:.2f}s")
print(f"Average Time per Test: {test_suite_duration / total_tests:.2f}s")
print(f"{'='*60}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Display Results

# COMMAND ----------

# Display results (original table)
results_df = spark.createDataFrame(results)
display(results_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Display Performance Metrics

# COMMAND ----------

from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType, 
    DoubleType, TimestampType, LongType
)

# Define explicit schema for metrics to avoid type merge issues
metrics_schema = StructType([
    StructField("test_number", IntegerType(), True),
    StructField("role", StringType(), True),
    StructField("use_case", StringType(), True),
    StructField("prompt", StringType(), True),
    StructField("prompt_length_chars", IntegerType(), True),
    StructField("prompt_length_words", IntegerType(), True),
    
    # All latency metrics as Double to avoid Long/Double merge issues
    StructField("send_message_latency", DoubleType(), True),
    StructField("total_wait_time", DoubleType(), True),
    StructField("result_fetch_latency", DoubleType(), True),
    StructField("end_to_end_latency", DoubleType(), True),
    
    # Polling metrics
    StructField("poll_count", IntegerType(), True),
    StructField("avg_poll_latency", DoubleType(), True),
    StructField("min_poll_latency", DoubleType(), True),
    StructField("max_poll_latency", DoubleType(), True),
    StructField("total_poll_time", DoubleType(), True),
    
    # Size metrics
    StructField("result_bytes", LongType(), True),
    StructField("row_count", IntegerType(), True),
    StructField("col_count", IntegerType(), True),
    StructField("analysis_length_chars", IntegerType(), True),
    StructField("sql_length_chars", IntegerType(), True),
    
    # Throughput metrics - always Double
    StructField("rows_per_second", DoubleType(), True),
    StructField("bytes_per_second", DoubleType(), True),
    
    # Status and IDs
    StructField("status", StringType(), True),
    StructField("conversation_id", StringType(), True),
    StructField("message_id", StringType(), True),
    StructField("test_timestamp", TimestampType(), True),
    
    # Optional error field
    StructField("error", StringType(), True)
])

# Display metrics with explicit schema
metrics_df = spark.createDataFrame(metrics, schema=metrics_schema)
display(metrics_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Performance Summary Statistics

# COMMAND ----------

# Calculate summary statistics
if metrics:
    metrics_pdf = pd.DataFrame(metrics)
    
    # Filter successful tests only
    successful_metrics = metrics_pdf[metrics_pdf['status'] == 'COMPLETED']
    
    if len(successful_metrics) > 0:
        summary_stats = {
            "metric": [
                "End-to-End Latency (avg)",
                "End-to-End Latency (median)",
                "End-to-End Latency (p95)",
                "End-to-End Latency (p99)",
                "Wait Time (avg)",
                "Wait Time (median)",
                "Send Message Latency (avg)",
                "Result Fetch Latency (avg)",
                "Avg Polls per Query",
                "Avg Poll Latency",
                "Rows per Second (avg)",
                "Bytes per Second (avg)",
                "Throughput (queries/min)"
            ],
            "value": [
                f"{successful_metrics['end_to_end_latency'].mean():.3f}s",
                f"{successful_metrics['end_to_end_latency'].median():.3f}s",
                f"{successful_metrics['end_to_end_latency'].quantile(0.95):.3f}s",
                f"{successful_metrics['end_to_end_latency'].quantile(0.99):.3f}s",
                f"{successful_metrics['total_wait_time'].mean():.3f}s",
                f"{successful_metrics['total_wait_time'].median():.3f}s",
                f"{successful_metrics['send_message_latency'].mean():.3f}s",
                f"{successful_metrics['result_fetch_latency'].mean():.3f}s",
                f"{successful_metrics['poll_count'].mean():.1f}",
                f"{successful_metrics['avg_poll_latency'].mean():.3f}s",
                f"{successful_metrics['rows_per_second'].mean():.1f}",
                f"{successful_metrics['bytes_per_second'].mean():.1f}",
                f"{(60 / successful_metrics['end_to_end_latency'].mean()):.2f}"
            ]
        }
        
        summary_df = pd.DataFrame(summary_stats)
        print("\nPERFORMANCE SUMMARY (Successful Tests Only)")
        print("=" * 60)
        display(summary_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Save Results to Tables

# COMMAND ----------

# Save results to Unity Catalog (existing table structure)
results_table = f"{CATALOG}.{SCHEMA_NAME}.genie_test_results"
results_df.write.mode("append").option("mergeSchema", "true").saveAsTable(results_table)
print(f"✅ Saved {len(results)} results to {results_table}")

# Save metrics to Unity Catalog (NEW separate table)
metrics_table = f"{CATALOG}.{SCHEMA_NAME}.genie_performance_metrics"
metrics_df.write.mode("append").option("mergeSchema", "true").saveAsTable(metrics_table)
print(f"✅ Saved {len(metrics)} performance metrics to {metrics_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Query Recent Performance Trends

# COMMAND ----------

# Example: Query to see performance over time
trend_query = f"""
SELECT 
    DATE(test_timestamp) as test_date,
    COUNT(*) as total_tests,
    AVG(end_to_end_latency) as avg_latency,
    PERCENTILE(end_to_end_latency, 0.95) as p95_latency,
    AVG(total_wait_time) as avg_wait_time,
    AVG(poll_count) as avg_polls,
    AVG(row_count) as avg_rows_returned,
    AVG(bytes_per_second) as avg_throughput_bytes_sec
FROM {metrics_table}
WHERE status = 'COMPLETED'
GROUP BY DATE(test_timestamp)
ORDER BY test_date DESC
LIMIT 30
"""

print("Performance Trends (Last 30 Days)")
print("=" * 60)
display(spark.sql(trend_query))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Performance by Use Case

# COMMAND ----------

# Example: Compare performance across different use cases
usecase_query = f"""
SELECT 
    use_case,
    COUNT(*) as test_count,
    AVG(end_to_end_latency) as avg_latency,
    MIN(end_to_end_latency) as min_latency,
    MAX(end_to_end_latency) as max_latency,
    AVG(total_wait_time) as avg_wait_time,
    AVG(poll_count) as avg_polls,
    AVG(row_count) as avg_rows,
    AVG(result_bytes) as avg_result_size_bytes
FROM {metrics_table}
WHERE status = 'COMPLETED'
GROUP BY use_case
ORDER BY avg_latency DESC
"""

print("Performance by Use Case")
print("=" * 60)
display(spark.sql(usecase_query))
