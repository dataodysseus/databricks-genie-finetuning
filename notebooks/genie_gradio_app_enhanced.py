# Databricks notebook source
# MAGIC %md
# MAGIC # Enhanced Genie Gradio App
# MAGIC
# MAGIC Full-featured web interface for Databricks Genie workspace

# COMMAND ----------

# MAGIC %pip install gradio==4.44.0
# MAGIC dbutils.library.restartPython()

# COMMAND ----------

import gradio as gr
import requests
import json
import pandas as pd
import time
from datetime import datetime
from io import StringIO

# COMMAND ----------

# Configuration
SPACE_ID = "01f0e0353b4c1353b0f07b21c5422977"
CATALOG = "accenture"
SCHEMA = "sales_analysis"

workspace_url = spark.conf.get("spark.databricks.workspaceUrl")
token = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

print(f"Workspace: {workspace_url}")
print(f"Space ID: {SPACE_ID}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Genie API Class

# COMMAND ----------

class GenieWorkspace:
    def __init__(self, workspace_url, space_id, headers):
        self.workspace_url = workspace_url
        self.space_id = space_id
        self.headers = headers
        self.conversation_id = None
        self.history = []
    
    def start_conversation(self):
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/start-conversation"
        response = requests.post(url, headers=self.headers, json={"content": "Starting"})
        
        if response.status_code == 200:
            data = response.json()
            self.conversation_id = data.get("conversation_id") or data.get("conversation", {}).get("id")
            return True
        return False
    
    def send_message(self, prompt):
        if not self.conversation_id:
            self.start_conversation()
        
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages"
        response = requests.post(url, headers=self.headers, json={"content": prompt})
        
        if response.status_code == 200:
            data = response.json()
            return data.get("id") or data.get("message", {}).get("id")
        return None
    
    def get_message_status(self, message_id, max_wait=300):
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages/{message_id}"
        
        start = time.time()
        while time.time() - start < max_wait:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") in ["COMPLETED", "FAILED", "CANCELLED"]:
                    return data
            time.sleep(3)
        return None
    
    def get_query_result(self, message_id, attachment_id):
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return None
    
    def extract_response(self, message_data, message_id):
        result = {"analysis": "", "sql": None, "results": None, "status": message_data.get("status")}
        
        for att in message_data.get("attachments", []):
            if "text" in att:
                result["analysis"] += "\n" + att["text"].get("content", "")
            
            if "query" in att:
                q = att["query"]
                result["sql"] = q.get("query")
                result["analysis"] = q.get("description", "") + result["analysis"]
                
                att_id = att.get("attachment_id")
                if att_id:
                    qr = self.get_query_result(message_id, att_id)
                    if qr:
                        stmt = qr.get("statement_response", {})
                        cols = [c.get("name") for c in stmt.get("manifest", {}).get("schema", {}).get("columns", [])]
                        data = stmt.get("result", {}).get("data_array")
                        
                        if data and cols:
                            result["results"] = pd.DataFrame(data, columns=cols)
        
        return result
    
    def ask(self, prompt):
        msg_id = self.send_message(prompt)
        if not msg_id:
            return None, None, None, "Error sending message"
        
        msg_data = self.get_message_status(msg_id)
        if not msg_data:
            return None, None, None, "Timeout"
        
        response = self.extract_response(msg_data, msg_id)
        
        # Store in history
        self.history.append({
            "timestamp": datetime.now(),
            "prompt": prompt,
            "analysis": response["analysis"],
            "sql": response["sql"],
            "row_count": len(response["results"]) if response["results"] is not None else 0,
            "status": response["status"]
        })
        
        return response["analysis"], response["sql"], response["results"], response["status"]
    
    def get_history_df(self):
        if not self.history:
            return pd.DataFrame()
        return pd.DataFrame(self.history)
    
    def reset(self):
        self.conversation_id = None
        self.history = []

genie = GenieWorkspace(workspace_url, SPACE_ID, headers)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interface Functions

# COMMAND ----------

def submit_query(prompt, chat_history):
    if not prompt.strip():
        return chat_history, None, None, "Enter a question", None
    
    chat_history.append({"role": "user", "content": prompt})
    
    analysis, sql, results, status = genie.ask(prompt)
    
    if analysis:
        chat_history.append({"role": "assistant", "content": analysis})
        results_display = results.head(100) if results is not None else None
        history_df = genie.get_history_df()
        
        return chat_history, sql, results_display, f"Status: {status} | Rows: {len(results) if results is not None else 0}", history_df
    else:
        chat_history.append({"role": "assistant", "content": f"Error: {status}"})
        return chat_history, None, None, f"Error: {status}", genie.get_history_df()

def reset_all():
    genie.reset()
    return [], None, None, "Reset complete", pd.DataFrame()

def export_results(results_df):
    if results_df is None or len(results_df) == 0:
        return None
    
    csv = results_df.to_csv(index=False)
    return csv

def export_sql(sql_code):
    if not sql_code:
        return None
    return sql_code

def export_history():
    history_df = genie.get_history_df()
    if len(history_df) == 0:
        return None
    return history_df.to_csv(index=False)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build App

# COMMAND ----------

examples = [
    "Show me items with above-average revenue per unit sold",
    "Which customers have made purchases in at least 3 different locations?",
    "What's the average time between purchases for each customer?",
    "Calculate the revenue contribution percentage for each item",
    "Which stores are categorized as 'At Risk' based on their forecast performance?",
    "Show me top 10 items by total revenue",
    "What are the total sales by location?",
    "Show me customer purchase trends over time",
    "Which items have declining sales over the past 3 months?",
    "Show me the correlation between forecast and actual sales"
]

with gr.Blocks(title="Genie Workspace", theme=gr.themes.Soft()) as demo:
    
    # Header
    gr.Markdown("# 🧞 Genie Workspace Explorer")
    gr.Markdown(f"**Space:** {SPACE_ID} | **Schema:** {CATALOG}.{SCHEMA}")
    
    with gr.Tabs():
        
        # Tab 1: Chat Interface
        with gr.Tab("Chat"):
            with gr.Row():
                with gr.Column(scale=3):
                    chatbot = gr.Chatbot(
                        label="Conversation",
                        height=500,
                        type="messages",
                        show_copy_button=True
                    )
                    
                    with gr.Row():
                        prompt = gr.Textbox(
                            label="Ask Genie",
                            placeholder="What would you like to know?",
                            lines=2,
                            scale=4
                        )
                    
                    with gr.Row():
                        submit = gr.Button("Submit", variant="primary", scale=2)
                        reset = gr.Button("Reset", scale=1)
                
                with gr.Column(scale=2):
                    status = gr.Textbox(label="Status", lines=2)
                    
                    sql_display = gr.Code(
                        label="Generated SQL",
                        language="sql",
                        lines=12
                    )
                    
                    with gr.Row():
                        export_sql_btn = gr.DownloadButton("Download SQL")
            
            # Results section
            with gr.Row():
                results = gr.Dataframe(
                    label="Query Results",
                    wrap=True,
                    height=400
                )
            
            with gr.Row():
                export_results_btn = gr.DownloadButton("Download Results CSV")
            
            # Examples
            gr.Markdown("### Example Questions")
            with gr.Row():
                for example in examples[:5]:
                    gr.Button(example, size="sm").click(
                        fn=lambda x: x,
                        inputs=gr.State(example),
                        outputs=prompt
                    )
            
            with gr.Accordion("More Examples", open=False):
                with gr.Row():
                    for example in examples[5:]:
                        gr.Button(example, size="sm").click(
                            fn=lambda x: x,
                            inputs=gr.State(example),
                            outputs=prompt
                        )
        
        # Tab 2: History
        with gr.Tab("History"):
            gr.Markdown("### Conversation History")
            history_table = gr.Dataframe(
                label="All Queries",
                wrap=True,
                height=600
            )
            
            with gr.Row():
                refresh_history = gr.Button("Refresh")
                export_history_btn = gr.DownloadButton("Download History")
            
            refresh_history.click(
                fn=lambda: genie.get_history_df(),
                outputs=history_table
            )
        
        # Tab 3: Analytics
        with gr.Tab("Analytics"):
            gr.Markdown("### Query Analytics")
            
            with gr.Row():
                with gr.Column():
                    total_queries = gr.Number(label="Total Queries", value=0)
                    avg_rows = gr.Number(label="Avg Rows Returned", value=0)
                
                with gr.Column():
                    success_rate = gr.Number(label="Success Rate (%)", value=0)
                    total_rows = gr.Number(label="Total Rows Returned", value=0)
            
            def compute_analytics():
                hist = genie.get_history_df()
                if len(hist) == 0:
                    return 0, 0, 0, 0
                
                total = len(hist)
                success = len(hist[hist['status'] == 'COMPLETED'])
                avg = hist['row_count'].mean()
                total_r = hist['row_count'].sum()
                
                return total, avg, (success/total*100) if total > 0 else 0, total_r
            
            analytics_btn = gr.Button("Compute Analytics")
            analytics_btn.click(
                fn=compute_analytics,
                outputs=[total_queries, avg_rows, success_rate, total_rows]
            )
    
    # Event handlers
    submit.click(
        fn=submit_query,
        inputs=[prompt, chatbot],
        outputs=[chatbot, sql_display, results, status, history_table]
    ).then(
        fn=lambda: "",
        outputs=prompt
    )
    
    prompt.submit(
        fn=submit_query,
        inputs=[prompt, chatbot],
        outputs=[chatbot, sql_display, results, status, history_table]
    ).then(
        fn=lambda: "",
        outputs=prompt
    )
    
    reset.click(
        fn=reset_all,
        outputs=[chatbot, sql_display, results, status, history_table]
    )
    
    export_sql_btn.click(
        fn=export_sql,
        inputs=sql_display,
        outputs=gr.File()
    )
    
    export_results_btn.click(
        fn=export_results,
        inputs=results,
        outputs=gr.File()
    )
    
    export_history_btn.click(
        fn=export_history,
        outputs=gr.File()
    )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Launch

# COMMAND ----------

demo.launch(
    share=True,
    debug=True,
    server_port=8080,
    server_name="0.0.0.0",
    show_error=True
)
