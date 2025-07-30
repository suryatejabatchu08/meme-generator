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

async def suggest_template(templates, meme_content):
    template_names = [t['name'] for t in templates]
    temp = ', '.join(template_names)
    print(temp)
    prompt = (
        f"Given the meme caption '{meme_content}', which of the following meme templates is the best fit?\n"
        f"Templates: {', '.join(template_names)}\n"
        "Return the template name only."
    )
    response = await call_gemini_api(prompt)
    # Find the template whose name matches the response
    for template in templates:
        if response.strip().lower() == template['name'].lower():
            print(response)
            return response.strip()
    return random.choice(templates)

async def improvise_meme_text(previous_conversation, bot_id):
    # Compose prompt for Gemini
    prompt = (
        "Given the following conversation, generate a meme caption based on the bot's behaviour.\n"
        "Return as JSON with 'top_text' and 'bottom_text'.\n"
        f"Bot Personality: {get_bot_prompt(bot_id)}\n"
        f"Conversation: {previous_conversation}"
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
    # 1. Get meme text from Gemma
    top_text, bottom_text = await improvise_meme_text(previous_conversation, bot_id)
    # 2. Fetch templates and generate meme as before
    templates = await fetch_templates()
    if not templates:
        return {"error": "Could not fetch meme templates"}
    template = random.choice(templates)
    #print("Templates: ", templates)
    # Use AI-based matching instead of random choice
    #meme_content = f"{top_text} {bottom_text}"
    #template = await suggest_template(templates, meme_content)
    #print("Choosen Template: ", template)
    #for temp in templates:
    #    if template.lower() == temp['name'].lower():
    #        print(template)
    #        print(temp['id'])
    #        template_id = temp['id']
    #        break
    meme_url = await generate_meme_imgflip(top_text, bottom_text, template['id'])
    if meme_url:
        return {"meme_url": meme_url, "template_name": template["name"]}
    else:
        return {"error": "Failed to generate meme"}