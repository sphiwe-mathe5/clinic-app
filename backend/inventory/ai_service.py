import os
import json
from openai import OpenAI
from inventory.ai_tools import AI_TOOLS_MAP, AI_TOOLS_SCHEMA

SYSTEM_PROMPT = """You are an elite Inventory Analyst AI. 
Your role is to answer questions about inventory health, stock levels, expiring items, and provide recommendations based on the data.
You MUST use the provided tools to fetch real-time data from the database. Do not guess inventory quantities, dates, or product names.
Present your answers in a professional, clean, analytical format. Use bullet points or concise paragraphs. Do not act like a generic chatbot (avoid phrases like 'How can I help you today?'). Provide direct, insightful intelligence.
You are strictly read-only. You cannot modify, delete, or create inventory records.
If you find critical issues (like expired batches or low stock), highlight them and recommend actions.
"""

def get_openai_client():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is not set in environment variables.")
    return OpenAI(api_key=api_key)

def ask_inventory_assistant(user_message: str, chat_history: list = None) -> str:
    try:
        client = get_openai_client()
    except ValueError as e:
        return f"Configuration Error: {str(e)} Please add OPENAI_API_KEY to your .env file."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    if chat_history:
        messages.extend(chat_history)
        
    messages.append({"role": "user", "content": user_message})

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=AI_TOOLS_SCHEMA,
            tool_choice="auto",
        )
        
        response_message = response.choices[0].message
        tool_calls = response_message.tool_calls
        
        if tool_calls:
            # Append the assistant's tool call message
            messages.append(response_message)
            
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                function_to_call = AI_TOOLS_MAP.get(function_name)
                
                if function_to_call:
                    function_args = json.loads(tool_call.function.arguments)
                    function_response = function_to_call(**function_args)
                    
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": function_response,
                    })
                else:
                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": json.dumps({"error": "Function not found"}),
                    })
                    
            # Call OpenAI again with the tool responses
            second_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            return second_response.choices[0].message.content
        else:
            return response_message.content
            
    except Exception as e:
        print(f"OpenAI Error: {e}")
        return f"I encountered an error connecting to the analysis engine: {str(e)}"
