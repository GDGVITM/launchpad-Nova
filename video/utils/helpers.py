import json
from groq import Groq
from openai import OpenAI
from google import genai
from google.genai import types
import time
from mistralai import Mistral
import requests
import functools
from django.conf import settings
import re


client = Groq(api_key=settings.GROQ_API_KEY)
google_client = genai.Client(
    api_key=settings.GOOGLE_API_KEY,
)

# https://codestral.mistral.ai/v1/chat/completions
mistral_client = Mistral(api_key=settings.MISTRAL_API_KEY)


def parse_json(raw, r_finder="{", l_finder="}"):
    # get from first { to last }
    # Find the first occurrence of '{' and the last occurrence of '}'
    start_idx = raw.find(r_finder)
    end_idx = raw.rfind(l_finder)

    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        raw = raw[start_idx : end_idx + 1]
    else:
        print(raw, file=open("raw.txt", "w"))
        # Handle case where JSON structure might not be found
        raise ValueError("Could not find valid JSON structure in the response")
    raw = raw.replace("```json", "").replace("```", "")
    try:
        # Try using json package directly with raw string
        return json.loads(raw)
    except json.JSONDecodeError:
        # If standard parsing fails, use json5 which is more lenient
        try:
            import json5

            return json5.loads(raw)
        except Exception as e:
            print(raw, file=open("raw.txt", "w", encoding="utf-8"))
            raise e


def llama_chat_completion(system, user, max_tokens=5000):
    completion = client.chat.completions.create(
        model="meta-llama/llama-4-maverick-17b-128e-instruct",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=1,
        max_completion_tokens=max_tokens,
        top_p=1,
        stop=None,
    )
    return completion.choices[0].message.content


def deepseek_chat_completion(system, user, max_tokens=1024):
    client = OpenAI(
        api_key="sk-fbc06d65ad4e40aa86d31f2b066c5ce3",
        base_url="https://api.deepseek.com",
    )
    completion = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=1,
        max_completion_tokens=max_tokens,
        top_p=1,
        stop=None,
    )
    return completion.choices[0].message.content


def gemini_chat_completion(
    system, user, max_tokens=5000, thinking_budget=0, temperature=1
):
    start = time.time()
    model = "gemini-2.5-flash"
    contents = [
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=user),
            ],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature=temperature,
        response_mime_type="text/plain",
        max_output_tokens=max_tokens,
        system_instruction=[
            types.Part.from_text(text=system),
        ],
        thinking_config=types.ThinkingConfig(
            thinking_budget=thinking_budget,
        ),
    )

    response = google_client.models.generate_content(
        model=model,
        contents=contents,
        config=generate_content_config,
    )
    end = time.time()
    print(f"Time taken for gemini: {end - start} seconds")
    if response.text:
        return response.text
    else:
        return response.candidates[0].content.parts[0].text


def retry_decorator(max_retries=3, delay=1):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retries += 1
                    if retries == max_retries:
                        raise e
                    print(f"Attempt {retries} failed. Retrying in {delay} seconds...")
                    time.sleep(delay)
            return None  # This line should never be reached

        return wrapper

    return decorator


@retry_decorator(max_retries=3, delay=1)
def call_chat_endpoint(data, api_key=settings.MISTRAL_API_KEY):
    url = "https://codestral.mistral.ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    response = requests.post(url, headers=headers, data=json.dumps(data))

    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(response.text)


def mistral_chat_completion(system, user, max_tokens=5000, model="codestral-2501"):
    start = time.time()
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    data = {"model": model, "messages": messages, "max_tokens": max_tokens}

    chat_response = call_chat_endpoint(data, api_key=settings.MISTRAL_API_KEY)

    end = time.time()
    print(f"Time taken for mistral: {end - start} seconds")
    # see if error
    if chat_response["object"] == "error":
        raise Exception(chat_response["message"])
    else:
        return chat_response["choices"][0]["message"]["content"]


def chat_completion(system, user, max_tokens=5000):
    # Use mistral-large-latest model with direct client API
    model = "mistral-large-latest"
    start = time.time()

    chat_response = mistral_client.chat.complete(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
    )

    end = time.time()
    print(f"Time taken for mistral: {end - start} seconds")

    return chat_response.choices[0].message.content


def code_completion(system, user, max_tokens=5000):
    model = "codestral-2501"
    return mistral_chat_completion(system, user, max_tokens, "codestral-latest")
    # return gemini_chat_completion(system, user, max_tokens, thinking_budget=0, temperature=1)

def clean_file_name(file_name):
    # only have letters, numbers, and underscores
    return re.sub(r'[^a-zA-Z0-9_]', '', file_name)