# Databricks notebook source
# MAGIC %md
# MAGIC # Genie LLM Judge

# COMMAND ----------

import requests
import json
import pandas as pd
from datetime import datetime
import time
import os

# COMMAND ----------

# dbutils.widgets.text("genie_space_id","")
# dbutils.widgets.text("schema_name","")

# COMMAND ----------

CATALOG=os.getenv("DATABRICKS_CATALOG")

# COMMAND ----------

# Configuration
SCHEMA = dbutils.widgets.get("schema_name")
TEST_TABLE = f"{CATALOG}.{SCHEMA}.genie_test_results"
CLAUDE_ENDPOINT = "databricks-claude-sonnet-4-5"

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Test Results

# COMMAND ----------

test_df = spark.table(TEST_TABLE).toPandas()
print(f"Loaded {len(test_df)} test results")
display(test_df[['test_number', 'role', 'use_case', 'status', 'row_count']].head())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Evaluation Function

# COMMAND ----------

def evaluate_test(row):
    """Call Claude to evaluate test result against expected output"""
    
    prompt_text = f"""You are evaluating a Genie AI assistant's response quality.

USER QUESTION:
{row['prompt']}

EXPECTED RESULT:
{row['expected_analysis']}

ACTUAL ANALYSIS:
{row['actual_analysis']}

ACTUAL SQL:
```sql
{row['sql_query']}
```

ACTUAL RESULTS:
Rows: {row['row_count']}
Columns: {row['col_count']}

Evaluate on these criteria (score 1-10):
1. Correctness: Does actual match expected?
2. SQL Quality: Is SQL well-written?
3. Completeness: All requirements met?
4. Analysis Quality: Clear explanation?

Provide actionable Genie configuration recommendations:
- TEXT_INSTRUCTION: Natural language guidance
- JOIN_SPEC: Table relationships  
- SQL_EXPRESSION: Reusable metrics
- EXAMPLE_SQL: Sample queries
- DATA_DEFINITION: Column/table comments

Respond ONLY in JSON:
{{
  "correctness_score": <1-10>,
  "sql_quality_score": <1-10>,
  "sql_quality_feedback": "<explanation>",  
  "completeness_score": <1-10>,
  "analysis_quality_score": <1-10>,
  "overall_score": <average>,
  "overall_assessment": "PASS|NEEDS_IMPROVEMENT|FAIL",
  "correctness_gap": "<what's missing or wrong>",
  "key_issues": ["issue1", "issue2"],
  "recommendations": [
    {{
      "type": "TEXT_INSTRUCTION|JOIN_SPEC|SQL_EXPRESSION|EXAMPLE_SQL|DATA_DEFINITION",
      "priority": "HIGH|MEDIUM|LOW",
      "description": "<what to add>",
      "implementation": "<exact text to add>",
      "reason": "<why this helps>"
    }}
  ]
}}"""

    url = f"https://{workspace_url}/serving-endpoints/{CLAUDE_ENDPOINT}/invocations"
    
    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"messages": [{"role": "user", "content": prompt_text}], "max_tokens": 4096, "temperature": 0.2},
            timeout=120
        )
        
        if response.status_code == 200:
            content = response.json()["choices"][0]["message"]["content"]
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            
            return json.loads(content.strip())
        else:
            return {"error": f"API error {response.status_code}"}
    
    except Exception as e:
        return {"error": str(e)}

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Evaluations

# COMMAND ----------

# DBTITLE 1,Cell 11
print("Starting evaluations...\n")

evaluations = []

for idx, row in test_df.iterrows():
    test_num = row['test_number']
    print(f"[{idx+1}/{len(test_df)}] Evaluating test #{test_num}: {row['use_case']}")
    
    eval_result = evaluate_test(row)
    
    if "error" not in eval_result:
        print(f"  Score: {eval_result.get('overall_score', 0):.1f}/10 | {eval_result.get('overall_assessment', 'N/A')}")
        print(f"  Recommendations: {len(eval_result.get('recommendations', []))}")
    else:
        print(f"  ERROR: {eval_result['error']}")
    
    evaluations.append({
        "test_number": test_num,
        "role": row['role'],
        "use_case": row['use_case'],
        "prompt": row['prompt'],
        "correctness_score": eval_result.get("correctness_score", 0.0),
        "sql_quality_score": eval_result.get("sql_quality_score", 0.0),
        "sql_quality_feedback": eval_result.get("sql_quality_feedback", 0),
        "completeness_score": eval_result.get("completeness_score", 0.0),
        "analysis_quality_score": eval_result.get("analysis_quality_score", 0.0),
        "overall_score": eval_result.get("overall_score", 0.0),
        "overall_assessment": eval_result.get("overall_assessment", "ERROR"),
        "correctness_gap": eval_result.get("correctness_gap", ""),
        "key_issues": json.dumps(eval_result.get("key_issues", [])),
        "recommendations": json.dumps(eval_result.get("recommendations", [])),
        "evaluation_timestamp": datetime.now(),
        "error": eval_result.get("error")
    })
    
    time.sleep(2)

print(f"\nCompleted {len(evaluations)} evaluations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Results DataFrame

# COMMAND ----------

# Statistics
print(f"\nAverage Overall Score: {eval_df['overall_score'].mean():.2f}/10")
print(f"Average Correctness: {eval_df['correctness_score'].mean():.2f}/10")
print(f"Average SQL Quality: {eval_df['sql_quality_score'].mean():.2f}/10")
print(f"Average Completeness: {eval_df['completeness_score'].mean():.2f}/10")
print(f"Average Analysis Quality: {eval_df['analysis_quality_score'].mean():.2f}/10")

print(f"\nAssessment Breakdown:")
print(eval_df['overall_assessment'].value_counts())

# COMMAND ----------

eval_df = pd.DataFrame(evaluations)
spark_df = spark.createDataFrame(eval_df)
display(spark_df)

# COMMAND ----------

# Save to Unity Catalog
eval_table = f"{CATALOG}.{SCHEMA}.genie_evaluations"
spark_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(eval_table)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Extract Recommendations

# COMMAND ----------

# Flatten recommendations into separate table
recommendations = []

for idx, row in eval_df.iterrows():
    test_num = row['test_number']
    recs = json.loads(row['recommendations']) if row['recommendations'] else []
    
    for rec in recs:
        recommendations.append({
            "test_number": test_num,
            "role": row['role'],
            "use_case": row['use_case'],
            "type": rec.get("type"),
            "priority": rec.get("priority"),
            "description": rec.get("description"),
            "implementation": rec.get("implementation"),
            "reason": rec.get("reason"),
            "evaluation_timestamp": row['evaluation_timestamp']
        })

if recommendations:
    rec_df = pd.DataFrame(recommendations)
    
    print(f"Total recommendations: {len(rec_df)}")
    print(f"High priority: {len(rec_df[rec_df['priority'] == 'HIGH'])}")
    print(f"Medium priority: {len(rec_df[rec_df['priority'] == 'MEDIUM'])}")
    print(f"Low priority: {len(rec_df[rec_df['priority'] == 'LOW'])}")
    
    # Display recommendations by priority
    print("\nHigh Priority Recommendations:")
    display(rec_df[rec_df['priority'] == 'HIGH'][['test_number', 'type', 'description', 'implementation']])
