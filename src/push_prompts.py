"""
Script para fazer push de prompts otimizados ao LangSmith Prompt Hub.

Este script:
1. Lê os prompts otimizados de prompts/bug_to_user_story_v2.yml
2. Valida os prompts
3. Faz push PÚBLICO para o LangSmith Hub
4. Adiciona metadados (tags, descrição, técnicas utilizadas)

SIMPLIFICADO: Código mais limpo e direto ao ponto.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from langchain import hub
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.prompts.prompt import PromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from utils import load_yaml, check_env_vars, print_section_header

load_dotenv()

# Constantes
PROMPTS_DIR = Path("prompts")
OPTIMIZED_PROMPT_FILENAME = "bug_to_user_story_v2.yml"
OPTIMIZED_PROMPT_PATH = PROMPTS_DIR / OPTIMIZED_PROMPT_FILENAME


def push_prompt_to_langsmith(prompt_name: str, prompt_data: dict) -> bool:
    """
    Pushes the optimized prompt to the LangSmith Hub (PUBLIC).

    Args:
        prompt_name: Name of the prompt in 'username/prompt_name' format.
        prompt_data: Prompt data loaded from YAML.

    Returns:
        True on success, False otherwise.
    """
    print(f"Pushing prompt '{prompt_name}' to LangSmith Hub...")
    try:
        msg_list = prompt_data["messages"]
        messages = []

        for idx, msg_data in enumerate(msg_list):
            role = msg_data.get("role")
            content = msg_data.get("content")
            is_last = idx == len(msg_list) - 1

            if role == "system":
                messages.append(SystemMessage(content=content))
            elif role == "user" and is_last:
                # Última mensagem user vira template com variável {bug_report}
                if "{bug_report}" not in content:
                    raise ValueError(
                        f"❌ Last user message does not contain '{{bug_report}}' template variable.\n"
                        f"Content: {content[:100]}...\n"
                        f"The template variable must be present for the prompt to work correctly."
                    )
                messages.append(
                    HumanMessagePromptTemplate(
                        prompt=PromptTemplate(
                            template=content,
                            input_variables=["bug_report"]
                        )
                    )
                )
            elif role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))

        prompt_template = ChatPromptTemplate(
            messages=messages,
            input_variables=["bug_report"]
        )

        # Extrai metadados
        tags = prompt_data.get("tags", [])
        description = prompt_data.get("description", "No description provided.")
        techniques = prompt_data.get("metadata", {}).get("techniques", [])

        full_description = f"{description}\n\n**Techniques Used:**\n- " + "\n- ".join(techniques)

        hub.push(
            prompt_name,
            prompt_template,
            new_repo_is_public=True,
            new_repo_description=full_description,
            tags=tags
        )

        hub_url = f"https://smith.langchain.com/hub/{prompt_name}"
        print(f"✅ Prompt publicado com sucesso!")
        print(f"Acesse em: {hub_url}")
        return True

    except ValueError as ve:
        print(f"\n{ve}")
        return False
    except Exception as e:
        print(f"❌ Erro ao fazer push do prompt: {e}")
        print("\nVerifique:")
        print("- Se as credenciais estão corretas no .env (LANGSMITH_API_KEY, USERNAME_LANGSMITH_HUB)")
        print("- Se o arquivo YAML é válido")
        print("- Se tem permissão de escrita no LangSmith")
        return False


def validate_prompt(prompt_data: dict) -> tuple[bool, list]:
    """
    Validates the basic structure of a prompt and required template variables.
    Args:
        prompt_data: Prompt data.
    Returns:
        (is_valid, errors) - Tuple with status and a list of errors.
    """
    errors = []
    if not prompt_data:
        return False, ["YAML file could not be loaded or is empty."]

    if "messages" not in prompt_data or not isinstance(prompt_data["messages"], list) or not prompt_data["messages"]:
        errors.append("The prompt must contain a non-empty list of 'messages'.")

    if "input_variables" not in prompt_data or not isinstance(prompt_data["input_variables"], list):
        errors.append("The prompt must contain the 'input_variables' key.")

    if "description" not in prompt_data or not prompt_data["description"]:
        errors.append("The prompt must contain a non-empty 'description'.")

    if "tags" not in prompt_data or not isinstance(prompt_data["tags"], list) or not prompt_data["tags"]:
        errors.append("The prompt must contain a non-empty list of 'tags'.")

    if "metadata" not in prompt_data or "techniques" not in prompt_data.get("metadata", {}):
        errors.append("The prompt must contain 'metadata.techniques'.")

    # Validar se a variável template {bug_report} existe no conteúdo
    messages = prompt_data.get("messages", [])
    has_template_variable = False

    for msg in messages:
        content = msg.get("content", "")
        if "{bug_report}" in content:
            has_template_variable = True
            break

    if not has_template_variable:
        errors.append(
            "The prompt must contain the template variable '{bug_report}' in at least one message. "
            "This variable is used to inject the bug report into the prompt."
        )

    return len(errors) == 0, errors


def main() -> int:
    """Main function"""
    print_section_header("PUSH PROMPTS TO LANGSMITH HUB")

    required_vars = ["LANGSMITH_API_KEY", "USERNAME_LANGSMITH_HUB"]
    if not check_env_vars(required_vars):
        return 1

    prompt_data = load_yaml(str(OPTIMIZED_PROMPT_PATH))
    is_valid, errors = validate_prompt(prompt_data)
    if not is_valid:
        print("\nThe optimized prompt has validation errors:")
        for error in errors:
            print(f"- {error}")
        return 1

    username = os.getenv("USERNAME_LANGSMITH_HUB")
    prompt_base_name = OPTIMIZED_PROMPT_FILENAME.replace(".yml", "")
    versioned_prompt_name = f"{username}/{prompt_base_name}"

    if not push_prompt_to_langsmith(versioned_prompt_name, prompt_data):
        return 1

    print("\nProcess completed successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
