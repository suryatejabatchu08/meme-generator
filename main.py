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
def extract_json_from_text(text):
    # Try to find a JSON object in the text
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    else:
        raise ValueError("No JSON object found in Gemini output")

async def improvise_meme_text(previous_conversation):
    # Compose prompt for Gemini
    prompt = (
        "Given the following conversation, generate a funny meme caption. "
        "Return as JSON with 'top_text' and 'bottom_text'.\n"
        f"Conversation: {previous_conversation}"
    )
    # Call Gemini (replace with your actual call)
    response = await call_gemini_api(prompt)

    #print("Gemini raw output:", repr(response))
    data = extract_json_from_text(response)
    return data["top_text"], data["bottom_text"]

class MemeRequest(BaseModel):
    previous_conversation: List[str] = []

@app.post("/generate-meme")
async def generate_meme_endpoint(request: MemeRequest):
    previous_conversation = request.previous_conversation
    # 1. Get meme text from Gemini
    top_text, bottom_text = await improvise_meme_text(previous_conversation)
    # 2. Fetch templates and generate meme as before
    templates = await fetch_templates()
    if not templates:
        return {"error": "Could not fetch meme templates"}
    template = random.choice(templates)
    meme_url = await generate_meme_imgflip(top_text, bottom_text, template["id"])
    if meme_url:
        return {"meme_url": meme_url, "template_name": template["name"]}
    else:
        return {"error": "Failed to generate meme"}