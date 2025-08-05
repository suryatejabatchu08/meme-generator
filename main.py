import os
import httpx
import random
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
import json
import google.generativeai as genai
from dotenv import load_dotenv
import re
from bot_prompt import get_bot_prompt

# Load environment variables from the .env file
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
app = FastAPI()

IMGFLIP_USERNAME = os.getenv("IMGFLIP_USERNAME")
IMGFLIP_PASSWORD = os.getenv("IMGFLIP_PASSWORD")

async def fetch_templates():
    url = "https://api.imgflip.com/get_memes"
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        data = resp.json()
        if data.get("success"):
            return data["data"]["memes"]
        else:
            return []

async def generate_meme_imgflip(top_text: str, bottom_text: str, template_id: str):
    url = "https://api.imgflip.com/caption_image"
    payload = {
        "template_id": template_id,
        "username": IMGFLIP_USERNAME,
        "password": IMGFLIP_PASSWORD,
        "text0": top_text,
        "text1": bottom_text
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, data=payload)
        data = resp.json()
        if data.get("success"):
            return data["data"]["url"]
        else:
            return None
async def call_gemini_api(prompt):
    model = genai.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.7,
            )
        ).text
    return response

async def call_gemma_api(prompt):
    model = genai.GenerativeModel('gemma-3n-e2b-it')
    response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.6,
            )
        ).text
    return response

def extract_json_from_text(text):
    # Try to find a JSON object in the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("No JSON object found in Gemini output")

async def suggest_template(templates, meme_content, previous_conversation):
    """
    Use Gemini to intelligently select the best meme template based on:
    1. The generated meme content (top and bottom text)
    2. The previous conversation context
    """
    template_names = [t['name'] for t in templates]
    
    # Create a more structured prompt with template descriptions
    template_descriptions = []
    for i, template in enumerate(templates):
        template_descriptions.append(f"{i+1}. {template['name']} (ID: {template['id']})")
    
    prompt = (
        f"Given the following context, select the most appropriate meme template:\n\n"
        f"Previous Conversation: {previous_conversation}\n"
        f"Generated Meme Text: {meme_content}\n\n"
        f"Available Templates:\n" + "\n".join(template_descriptions) + "\n\n"
        f"Instructions:\n"
        f"1. Consider the emotional tone, humor style, and context of the conversation\n"
        f"2. Match the template to the meme's sentiment and style\n"
        f"3. Return ONLY the exact template name from the list above\n"
        f"4. Do not add any explanations or additional text\n"
        f"5. Choose a different template than 'Drake Hotline Bling' unless it's the perfect fit"
    )
    
    try:
        print(f"Debug: Sending template selection prompt to Gemini...")
        response = await call_gemini_api(prompt)
        response_clean = response.strip().lower()
        print(f"Debug: Gemini response: '{response}'")
        print(f"Debug: Cleaned response: '{response_clean}'")
        
        # Find the template whose name matches the response
        for template in templates:
            if response_clean == template['name'].lower():
                print(f"AI selected template (exact match): {template['name']}")
                return template
        
        # If no exact match found, try partial matching
        for template in templates:
            if response_clean in template['name'].lower() or template['name'].lower() in response_clean:
                print(f"AI selected template (partial match): {template['name']}")
                return template
        
        # Try to extract template name from response if it contains extra text
        for template in templates:
            if template['name'].lower() in response_clean:
                print(f"AI selected template (extracted): {template['name']}")
                return template
        
        # Fallback to random selection if no match found
        print("No AI match found, using random selection")
        return random.choice(templates)
        
    except Exception as e:
        print(f"Error in AI template selection: {e}")
        return random.choice(templates)

async def improvise_meme_text(previous_conversation, bot_id, templates):
    template_names = [t['name'] for t in templates]
    template_names.reverse()
    # Compose prompt for Gemini
    prompt = (
        "Given the following conversation, generate a meme that represents the bot's response or reaction to the user.\n"
        "The meme should capture the bot's personality, tone, and how they would respond to the situation.\n"
        "The meme should always be short and punchy, and should be a good fit for the bot's personality.\n"
        "But it should not be in the way how bot call the user.\n"
        "Even if the bot prompt contains to use emojis, you should not use them.\n"
        "Return as JSON with 'top_text' and 'bottom_text'.\n"
        f"Bot Personality: {get_bot_prompt(bot_id)}\n"
        f"Conversation: {previous_conversation}\n"
        f"Available Templates: {template_names}\n\n"
        f"Examples:\n"
        f"- If user is sad, bot's meme might be supportive and caring\n"
        f"- If user is frustrated, bot's meme might be understanding and helpful\n"
        f"- If user shares good news, bot's meme might be excited and celebratory\n"
        f"- If user is confused, bot's meme might be reassuring and explanatory"
    )
    # Call Gemma (for quick response)
    response = await call_gemma_api(prompt)

    print("Gemini raw output:", repr(response))
    data = extract_json_from_text(response)
    return data["top_text"], data["bottom_text"]

class MemeRequest(BaseModel):
    previous_conversation: List[str] = []
    bot_id: str = ""

@app.post("/generate-meme")
async def generate_meme_endpoint(request: MemeRequest):
    previous_conversation = request.previous_conversation
    bot_id = request.bot_id

    # 1. Fetch templates
    templates = await fetch_templates()
    if not templates:
        return {"error": "Could not fetch meme templates"}
    
    # 2. Get meme text from Gemma
    top_text, bottom_text = await improvise_meme_text(previous_conversation, bot_id, templates)
    
    # 3. Use AI to intelligently select the best template
    meme_content = f"Top: {top_text} | Bottom: {bottom_text}"
    selected_template = await suggest_template(templates, meme_content, previous_conversation)
    
    # 4. Generate the meme with the selected template
    meme_url = await generate_meme_imgflip(top_text, bottom_text, selected_template['id'])
    
    if meme_url:
        return {
            "meme_url": meme_url, 
            "template_name": selected_template["name"],
            "top_text": top_text,
            "bottom_text": bottom_text
        }
    else:
        return {"error": "Failed to generate meme"}