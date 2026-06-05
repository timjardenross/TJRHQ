import os

from openai import OpenAI


class LLMUnavailableError(RuntimeError):
    pass


def is_llm_configured() -> bool:
    return bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"))


def build_client() -> OpenAI:
    if not is_llm_configured():
        raise LLMUnavailableError("OpenAI credentials are not configured.")

    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_ADMIN_KEY"),
    )


def ask_commander(system_prompt: str, user_prompt: str) -> str:
    client = build_client()
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


def ask_commander_safe(system_prompt: str, user_prompt: str) -> tuple[bool, str]:
    try:
        return True, ask_commander(system_prompt=system_prompt, user_prompt=user_prompt)
    except LLMUnavailableError as error:
        return False, str(error)
    except Exception as error:
        return False, f"{type(error).__name__}"


def ask_commander_with_sources(system_prompt: str, user_prompt: str) -> str:
    return ask_commander(system_prompt=system_prompt, user_prompt=user_prompt)
