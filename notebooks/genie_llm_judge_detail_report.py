# Databricks notebook source
# MAGIC %md
# MAGIC # Actionable LLM Judge
# MAGIC
# MAGIC This notebook evaluates Genie responses and provides actionable recommendations
# MAGIC that map directly to Genie space configuration options.
# MAGIC
# MAGIC **Genie Configuration Options:**
# MAGIC - Text Instructions (natural language guidance)
# MAGIC - Join Specifications (table relationships)
# MAGIC - SQL Expressions (metrics, calculations)
# MAGIC - Example SQL Queries
# MAGIC - Data Definitions (table/column comments in Unity Catalog)

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
SCHEMA_NAME = dbutils.widgets.get("schema_name")
GENIE_TEST_TABLE = f"{CATALOG}.{SCHEMA_NAME}.genie_test_results"
CLAUDE_ENDPOINT = "databricks-claude-sonnet-4-5"

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Load Test Data

# COMMAND ----------

test_results_df = spark.table(GENIE_TEST_TABLE).toPandas()
print(f"Loaded {len(test_results_df)} test results")
display(test_results_df.head(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Actionable Evaluation Function

# COMMAND ----------

def call_claude_actionable_judge(test_data, actual_results=None):
    """
    Call Claude to evaluate and provide Genie-specific actionable recommendations
    """
    
    prompt = test_data.get('prompt', '')
    analysis = test_data.get('actual_analysis', '')
    sql_query = test_data.get('sql_query', '')
    
    # Execute query if not provided
    if actual_results is None and sql_query:
        try:
            result_df = spark.sql(sql_query)
            sample_df = result_df.limit(20).toPandas()
            actual_results = {
                "success": True,
                "row_count": result_df.count(),
                "sample_data": sample_df.to_string(index=False),
                "columns": list(sample_df.columns)
            }
        except Exception as e:
            actual_results = {"success": False, "error": str(e)}
    
    evaluation_prompt = f"""You are an expert Databricks Genie consultant. Evaluate this AI assistant response and provide ACTIONABLE recommendations that map to specific Genie configuration options.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER'S QUESTION:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENIE'S ANALYSIS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{analysis}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENERATED SQL:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```sql
{sql_query}
```

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUERY RESULTS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    
    if actual_results and actual_results.get('success'):
        evaluation_prompt += f"""
Total Rows: {actual_results['row_count']}
Columns: {actual_results['columns']}

Sample Data:
{actual_results['sample_data']}
"""
    else:
        evaluation_prompt += "Query execution failed or not available.\n"
    
    evaluation_prompt += """

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GENIE CONFIGURATION OPTIONS AVAILABLE:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. **Text Instructions**: Natural language guidance for Genie (e.g., "When users ask about 'popular' items, define popular as items in the top 25% by sales volume")

2. **Join Specifications**: Define relationships between tables (e.g., "items_sales.item_id = item_details.item_id")

3. **SQL Expressions**: Create reusable metrics/calculations (e.g., "revenue_per_unit = total_sales_value / units_sold")

4. **Example SQL Queries**: Provide sample queries for similar questions (teach by example)

5. **Data Definitions**: Add comments to tables/columns in Unity Catalog (e.g., COMMENT ON COLUMN is "The unique identifier for each product")

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVALUATION TASK:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Evaluate the response and provide SPECIFIC, ACTIONABLE recommendations using the 5 configuration options above.

For each issue found, specify:
- Which configuration option to use
- Exact text/SQL to add
- Why this will improve results

Respond in JSON format:

{
  "overall_score": <1-10>,
  "overall_assessment": "PASS|NEEDS_IMPROVEMENT|FAIL",
  "correctness_score": <1-10>,
  "correctness_feedback": "<explanation>",
  "sql_quality_score": <1-10>,
  "sql_quality_feedback": "<explanation>",
  "data_validation_score": <1-10>,
  "data_validation_feedback": "<explanation>",
  "analysis_quality_score": <1-10>,
  "analysis_quality_feedback": "<explanation>",
  "completeness_score": <1-10>,
  "completeness_feedback": "<explanation>",
  "key_issues": ["<issue 1>", "<issue 2>"],
  "actionable_recommendations": [
    {
      "priority": "HIGH|MEDIUM|LOW",
      "configuration_type": "TEXT_INSTRUCTION|JOIN_SPEC|SQL_EXPRESSION|EXAMPLE_SQL|DATA_DEFINITION",
      "recommendation": "<specific action to take>",
      "implementation": "<exact text/SQL to add>",
      "expected_improvement": "<how this will improve results>",
      "applies_to_tables": ["<table1>", "<table2>"]
    }
  ],
  "confidence": "HIGH|MEDIUM|LOW"
}

**IMPORTANT**: 
- Be specific in recommendations (don't say "add instructions", say exactly what instruction to add)
- Provide copy-paste ready text/SQL in "implementation"
- Prioritize recommendations (HIGH for critical issues, LOW for nice-to-haves)
- Focus on preventable issues that configuration can fix"""

    # Call Claude
    url = f"https://{workspace_url}/serving-endpoints/{CLAUDE_ENDPOINT}/invocations"
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messages": [{"role": "user", "content": evaluation_prompt}],
        "max_tokens": 8192,
        "temperature": 0.2
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=180)
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            # Clean JSON
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            elif content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
            
            evaluation = json.loads(content)
            evaluation['api_success'] = True
            return evaluation
        else:
            return {
                "api_success": False,
                "error": f"API error: {response.status_code}",
                "details": response.text[:500]
            }
    
    except Exception as e:
        return {
            "api_success": False,
            "error": str(e)
        }

# COMMAND ----------

# MAGIC %md
# MAGIC ## Run Actionable Evaluations

# COMMAND ----------

print("STARTING ACTIONABLE EVALUATION")

evaluations = []

for idx, row in test_results_df.iterrows():
    test_num = row.get('test_number', idx + 1)
    prompt = row.get('prompt', '')
    
    print(f"[{idx+1}/{len(test_results_df)}] TEST #{test_num}")
    print(f"Prompt: {prompt[:80]}...")
    
    # Call Claude judge
    print(f"Evaluating and generating recommendations...")
    evaluation = call_claude_actionable_judge(row.to_dict())
    
    # Add metadata
    evaluation['test_number'] = test_num
    evaluation['prompt'] = prompt
    evaluation['execution_timestamp'] = datetime.now()
    
    if evaluation.get('api_success'):
        score = evaluation.get('overall_score', 0)
        recs = len(evaluation.get('actionable_recommendations', []))
        print(f"Score: {score:.1f}/10")
        print(f"Generated {recs} actionable recommendations")
    else:
        print(f"Error: {evaluation.get('error', 'Unknown')}")
    
    evaluations.append(evaluation)
    time.sleep(2)

print(f"Completed {len(evaluations)} evaluations")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Results with Actionable Recommendations

# COMMAND ----------

# Summary
summary_data = []
for eval_result in evaluations:
    if eval_result.get('api_success'):
        num_recs = len(eval_result.get('actionable_recommendations', []))
        high_priority = sum(1 for r in eval_result.get('actionable_recommendations', []) 
                           if r.get('priority') == 'HIGH')
        
        summary_data.append({
            'Test': eval_result.get('test_number'),
            'Prompt': eval_result.get('prompt', '')[:50] + '...',
            'Score': f"{eval_result.get('overall_score', 0):.1f}",
            'Assessment': eval_result.get('overall_assessment', 'N/A'),
            'Total Recs': num_recs,
            'High Priority': high_priority
        })

summary_df = pd.DataFrame(summary_data)

print("EVALUATION SUMMARY")
print(summary_df.to_string(index=False))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Save Results

# COMMAND ----------

# Flatten recommendations for saving
eval_records = []

for eval_result in evaluations:
    # Base evaluation record
    base_record = {
        'evaluation_timestamp': eval_result.get('execution_timestamp', datetime.now()),
        'test_number': eval_result.get('test_number'),
        'prompt': eval_result.get('prompt'),
        'api_success': eval_result.get('api_success', False),
        'overall_score': float(eval_result.get('overall_score', 0)),
        'overall_assessment': eval_result.get('overall_assessment'),
        'correctness_score': float(eval_result.get('correctness_score', 0)),
        'sql_quality_score': float(eval_result.get('sql_quality_score', 0)),
        'data_validation_score': float(eval_result.get('data_validation_score', 0)),
        'analysis_quality_score': float(eval_result.get('analysis_quality_score', 0)),
        'completeness_score': float(eval_result.get('completeness_score', 0)),
        'total_recommendations': len(eval_result.get('actionable_recommendations', [])),
        'high_priority_count': sum(1 for r in eval_result.get('actionable_recommendations', []) 
                                   if r.get('priority') == 'HIGH'),
        'recommendations_json': json.dumps(eval_result.get('actionable_recommendations', []))
    }
    
    eval_records.append(base_record)

# Save evaluations
eval_df = spark.createDataFrame(eval_records)
eval_table = f"{CATALOG}.{SCHEMA_NAME}.genie_evaluations_actionable"
eval_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(eval_table)

# COMMAND ----------

spark.table(f"{CATALOG}.{SCHEMA_NAME}.genie_evaluations_actionable").display()

# COMMAND ----------

# Save recommendations separately for easier querying
rec_records = []
for eval_result in evaluations:
    test_num = eval_result.get('test_number')
    for rec in eval_result.get('actionable_recommendations', []):
        rec_records.append({
            'evaluation_timestamp': eval_result.get('execution_timestamp', datetime.now()),
            'test_number': test_num,
            'prompt': eval_result.get('prompt'),
            'priority': rec.get('priority'),
            'configuration_type': rec.get('configuration_type'),
            'recommendation': rec.get('recommendation'),
            'implementation': rec.get('implementation'),
            'expected_improvement': rec.get('expected_improvement'),
            'applies_to_tables': json.dumps(rec.get('applies_to_tables', []))
        })

if rec_records:
    rec_df = spark.createDataFrame(rec_records)
    rec_table = f"{CATALOG}.{SCHEMA_NAME}.genie_recommendations"
    rec_df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(rec_table)

# COMMAND ----------

spark.table(f"{CATALOG}.{SCHEMA_NAME}.genie_recommendations").display()
