# Databricks notebook source
# MAGIC %md
# MAGIC # Genie Workspace Gradio App
# MAGIC
# MAGIC Interactive web interface for Databricks Genie workspace

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
# MAGIC ## Genie API Functions

# COMMAND ----------

class GenieAPI:
    def __init__(self, workspace_url, space_id, headers):
        self.workspace_url = workspace_url
        self.space_id = space_id
        self.headers = headers
        self.conversation_id = None
    
    def start_conversation(self):
        """Start a new Genie conversation"""
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/start-conversation"
        response = requests.post(url, headers=self.headers, json={"content": "Starting conversation"})
        
        if response.status_code == 200:
            data = response.json()
            self.conversation_id = data.get("conversation_id") or data.get("conversation", {}).get("id")
            return True, f"Conversation started: {self.conversation_id}"
        else:
            return False, f"Failed to start conversation: {response.status_code}"
    
    def send_message(self, prompt):
        """Send a message to Genie"""
        if not self.conversation_id:
            success, msg = self.start_conversation()
            if not success:
                return None, msg
        
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages"
        response = requests.post(url, headers=self.headers, json={"content": prompt})
        
        if response.status_code == 200:
            data = response.json()
            message_id = data.get("id") or data.get("message", {}).get("id")
            return message_id, "Message sent"
        else:
            return None, f"Failed to send message: {response.status_code}"
    
    def get_message_status(self, message_id, max_wait=300):
        """Poll for message completion"""
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages/{message_id}"
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            response = requests.get(url, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                
                if status in ["COMPLETED", "FAILED", "CANCELLED"]:
                    return data, status
                
                time.sleep(3)
            else:
                return None, f"ERROR: {response.status_code}"
        
        return None, "TIMEOUT"
    
    def get_query_result(self, message_id, attachment_id):
        """Get query results from attachment"""
        url = f"https://{self.workspace_url}/api/2.0/genie/spaces/{self.space_id}/conversations/{self.conversation_id}/messages/{message_id}/attachments/{attachment_id}/query-result"
        
        try:
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        
        return None
    
    def extract_response(self, message_data, message_id):
        """Extract analysis, SQL, and results from message"""
        result = {
            "analysis": "",
            "sql": None,
            "results": None,
            "status": message_data.get("status")
        }
        
        attachments = message_data.get("attachments", [])
        
        for attachment in attachments:
            # Extract text analysis
            if "text" in attachment:
                text_content = attachment.get("text", {}).get("content", "")
                if text_content:
                    result["analysis"] += "\n\n" + text_content
            
            # Extract SQL and results
            if "query" in attachment:
                query_obj = attachment.get("query", {})
                
                # Get SQL
                result["sql"] = query_obj.get("query")
                
                # Get description
                description = query_obj.get("description", "")
                if description:
                    result["analysis"] = description + result["analysis"]
                
                # Get results
                attachment_id = attachment.get("attachment_id")
                if attachment_id:
                    query_result = self.get_query_result(message_id, attachment_id)
                    
                    if query_result:
                        stmt = query_result.get("statement_response", {})
                        manifest = stmt.get("manifest", {})
                        schema = manifest.get("schema", {})
                        columns = [col.get("name") for col in schema.get("columns", [])]
                        
                        data_array = stmt.get("result", {}).get("data_array")
                        
                        if data_array and columns:
                            result["results"] = pd.DataFrame(data_array, columns=columns)
                        else:
                            # Handle typed array
                            typed_data = stmt.get("result", {}).get("data_typed_array", [])
                            if typed_data:
                                rows = []
                                for row in typed_data:
                                    vals = []
                                    for v in row.get("values", []):
                                        vals.append(
                                            v.get("str") or v.get("int") or 
                                            v.get("double") or v.get("bool")
                                        )
                                    rows.append(vals)
                                
                                if rows and columns:
                                    result["results"] = pd.DataFrame(rows, columns=columns)
        
        return result
    
    def ask_genie(self, prompt):
        """Complete workflow: ask question and get response"""
        # Send message
        message_id, msg = self.send_message(prompt)
        if not message_id:
            return None, None, None, f"Error: {msg}"
        
        # Wait for completion
        message_data, status = self.get_message_status(message_id)
        
        if not message_data:
            return None, None, None, f"Error: {status}"
        
        # Extract response
        response = self.extract_response(message_data, message_id)
        
        return (
            response["analysis"],
            response["sql"],
            response["results"],
            f"Status: {response['status']}"
        )

# Initialize API
genie = GenieAPI(workspace_url, SPACE_ID, headers)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gradio Interface Functions

# COMMAND ----------

def query_genie(prompt, history):
    """Handle Genie query from Gradio"""
    if not prompt.strip():
        return history, None, None, "Please enter a question"
    
    # Add user message to history
    history.append({"role": "user", "content": prompt})
    
    # Query Genie
    analysis, sql, results, status = genie.ask_genie(prompt)
    
    if analysis:
        # Add Genie response to history
        history.append({"role": "assistant", "content": analysis})
        
        # Format results
        results_display = None
        if results is not None:
            results_display = results.head(100)  # Show first 100 rows
        
        return history, sql, results_display, status
    else:
        history.append({"role": "assistant", "content": f"Error: {status}"})
        return history, None, None, status

def reset_conversation():
    """Reset the Genie conversation"""
    global genie
    genie = GenieAPI(workspace_url, SPACE_ID, headers)
    return [], None, None, "Conversation reset"

def load_example(example_prompt):
    """Load an example prompt"""
    return example_prompt

# COMMAND ----------

# MAGIC %md
# MAGIC ## Build Gradio App

# COMMAND ----------

# Example prompts
examples = [
    "Calculate the revenue contribution percentage for each item. Show top 5 items based on their revenue contributions.",
    "Which stores are categorized as 'At Risk' based on their forecast performance in December 2025? ",
    "How does the forecast performance of Austin stores compare over time?",
    "Show the top 10 most popular products in Austin store by revenue.",
    "Who are the most frequent customers at Austin store. List top 10 based on frequency of purchase (not total revenue)"
]

# Build interface
with gr.Blocks(title="Genie Workspace Explorer", theme=gr.themes.Soft()) as app:
    gr.Markdown("# Genie Workspace Explorer")
    gr.Markdown(f"**Space Name:** Retail Sales Analysis | **Schema:** {SCHEMA_NAME}")
    
    with gr.Row():
        with gr.Column(scale=2):
            # Chat interface
            chatbot = gr.Chatbot(
                label="Conversation",
                height=400,
                type="messages"
            )
            
            prompt_input = gr.Textbox(
                label="Ask Genie",
                placeholder="Enter your question...",
                lines=2
            )
            
            with gr.Row():
                submit_btn = gr.Button("Submit", variant="primary")
                reset_btn = gr.Button("Reset Conversation")
            
            # Example prompts
            gr.Markdown("### Example Questions")
            example_buttons = []
            for example in examples[:4]:  # Show first 4
                btn = gr.Button(example, size="sm")
                example_buttons.append(btn)
        
        with gr.Column(scale=1):
            # Status and info
            status_output = gr.Textbox(label="Status", lines=2)
            
            # SQL output
            sql_output = gr.Code(
                label="Generated SQL",
                language="sql",
                lines=10
            )
    
    # Results table (full width)
    with gr.Row():
        results_output = gr.Dataframe(
            label="Query Results",
            wrap=True,
            height=400
        )
    
    # More examples (collapsible)
    with gr.Accordion("More Examples", open=False):
        for example in examples[4:]:
            btn = gr.Button(example, size="sm")
            example_buttons.append(btn)
    
    # Event handlers
    submit_btn.click(
        fn=query_genie,
        inputs=[prompt_input, chatbot],
        outputs=[chatbot, sql_output, results_output, status_output]
    ).then(
        fn=lambda: "",
        outputs=prompt_input
    )
    
    prompt_input.submit(
        fn=query_genie,
        inputs=[prompt_input, chatbot],
        outputs=[chatbot, sql_output, results_output, status_output]
    ).then(
        fn=lambda: "",
        outputs=prompt_input
    )
    
    reset_btn.click(
        fn=reset_conversation,
        outputs=[chatbot, sql_output, results_output, status_output]
    )
    
    # Example button handlers
    for btn in example_buttons:
        btn.click(
            fn=load_example,
            inputs=gr.State(btn.value),
            outputs=prompt_input
        )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Launch App

# COMMAND ----------

# Launch Gradio app
app.launch(
    debug=True,
    server_port=8080,
    server_name="0.0.0.0",
    share=False
)

# Keep the app running
app.block_thread()
