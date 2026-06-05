import os

from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def ask_commander(system_prompt: str, user_prompt: str) -> str:

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.3,
    )

    return response.choices[0].message.content


def ask_commander_with_sources(system_prompt: str, user_prompt: str) -> str:
    return ask_commander(system_prompt=system_prompt, user_prompt=user_prompt)
