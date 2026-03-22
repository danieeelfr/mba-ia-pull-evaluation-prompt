"""
Script para fazer pull de prompts do LangSmith Prompt Hub.

Este script:
1. Conecta ao LangSmith usando credenciais do .env
2. Faz pull dos prompts do Hub
3. Salva localmente em prompts/bug_to_user_story_v1.yml

SIMPLIFICADO: Usa serialização nativa do LangChain para extrair prompts.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain import hub
from utils import save_yaml, check_env_vars, print_section_header

load_dotenv()

PROMPTS_DIR = Path("prompts")
PROMPT_OWNER = "leonanluppi"
PROMPT_NAME = "bug_to_user_story_v1"
PROMPT_FULL_NAME = f"{PROMPT_OWNER}/{PROMPT_NAME}"
PROMPT_PATH = str(PROMPTS_DIR / f"{PROMPT_NAME}.yml")

def pull_prompt_from_langsmith() -> bool:
 """
 Pulls the specified prompt from the LangSmith Hub and saves it locally.

 Returns:
  True if the operation is successful, False otherwise.
 """
 print(f"Pulling prompt '{PROMPT_FULL_NAME}' from LangSmith Hub...")

 try:
  PROMPTS_DIR.mkdir(exist_ok=True)

  pulled_prompt = hub.pull(PROMPT_FULL_NAME)
  print("Prompt pulled successfully.")

  # Convert to dict for yaml serialization
  prompt_data = pulled_prompt.dict() if hasattr(pulled_prompt, 'dict') else pulled_prompt

  print(f"Saving prompt to '{PROMPT_PATH}'...")
  return save_yaml(prompt_data, PROMPT_PATH)

 except Exception as e:
  print(f"\nAn error occurred while pulling the prompt: {e}")
  print("\nPlease ensure the 'LANGSMITH_API_KEY' environment variable is set correctly.")
  return False


def main() -> int:
 """Main function to execute the script."""
 print_section_header("PULL PROMPTS FROM LANGSMITH HUB")

 if not check_env_vars(["LANGSMITH_API_KEY"]):
  return 1

 if not pull_prompt_from_langsmith():
  return 1

 print("\nProcess completed successfully!")
 return 0


if __name__ == "__main__":
 sys.exit(main())
