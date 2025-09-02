from pydantic import BaseModel, Field
from langchain.llms.base import LLM
import requests
import os

CHATGPT_API_KEY = os.getenv("OPENAI_API_KEY")  # обязательно добавь в .env
class ChatGPTLLM(LLM, BaseModel):
    model: str = "gpt-4o"
    api_key: str = Field(default=CHATGPT_API_KEY, exclude=True)

    def _llm_type(self) -> str:
        return "openai-chat"  # можно назвать как угодно

    def _call(self, prompt: str, history: list = None, stop=None) -> str:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        messages = [{"role": "system", "content": "You are a helpful assistant."}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": prompt})

        response = requests.post(url, headers=headers, json={
            "model": self.model,
            "messages": messages,
            "temperature": 0.7
        })

        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return "Ошибка запроса к ChatGPT."
