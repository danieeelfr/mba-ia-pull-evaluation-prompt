"""
Testes automatizados para validação de prompts.

Valida que o prompt otimizado (bug_to_user_story_v2.yml) atende aos requisitos
de prompt engineering: persona, exemplos, formato, técnicas, etc.
"""
import pytest
import yaml
import sys
import re
from pathlib import Path

# Adicionar src ao path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def load_prompts(file_path: str):
    """Carrega prompts do arquivo YAML."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


class TestPrompts:
    """Suite de testes para validar a qualidade do prompt otimizado."""

    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup: carrega o prompt v2 antes de cada teste."""
        prompt_path = Path(__file__).parent.parent / "prompts" / "bug_to_user_story_v2.yml"
        self.prompt_data = load_prompts(str(prompt_path))
        assert self.prompt_data is not None, "Failed to load bug_to_user_story_v2.yml"

    def test_prompt_has_system_prompt(self):
        """
        Verifica se existe uma mensagem com role='system' e se seu content não está vazio.

        Uma mensagem de sistema é essencial para definir persona, contexto e regras.
        """
        messages = self.prompt_data.get("messages", [])
        assert isinstance(messages, list), "messages deve ser uma lista"
        assert len(messages) > 0, "prompt deve conter pelo menos uma mensagem"

        system_messages = [msg for msg in messages if msg.get("role") == "system"]
        assert len(system_messages) > 0, "prompt deve conter uma mensagem com role='system'"

        system_prompt = system_messages[0]
        content = system_prompt.get("content", "").strip()
        assert content, "system prompt não pode estar vazio"
        assert len(content) > 50, "system prompt deve ter conteúdo significativo (> 50 caracteres)"

    def test_prompt_has_role_definition(self):
        """
        Verifica se o prompt define uma persona clara (Role Prompting).

        Procura por indicadores de persona como:
        - "Você é um..."
        - "Você é uma..."
        - "# PERSONA"
        """
        messages = self.prompt_data.get("messages", [])
        full_content = "\n".join([msg.get("content", "") for msg in messages])

        persona_indicators = [
            r"Você é um",
            r"Você é uma",
            r"# PERSONA",
            r"ROLE:",
            r"Role:",
        ]

        found_persona = any(
            re.search(indicator, full_content, re.IGNORECASE)
            for indicator in persona_indicators
        )

        assert found_persona, (
            "prompt deve definir uma persona clara usando Role Prompting "
            "(ex: 'Você é um Product Manager')"
        )

    def test_prompt_mentions_format(self):
        """
        Verifica se o prompt exige um formato de User Story ou estrutura específica.

        Procura por indicadores como:
        - "Como um(a)"
        - "eu quero"
        - "User Story"
        - "formato"
        - "Critérios de Aceitação"
        """
        messages = self.prompt_data.get("messages", [])
        full_content = "\n".join([msg.get("content", "") for msg in messages])

        format_indicators = [
            r"Como um",
            r"eu quero",
            r"para que",
            r"Critérios de Aceitação",
            r"Dado que|When|Então|história de usuário",
            r"User Story",
        ]

        found_format = any(
            re.search(indicator, full_content, re.IGNORECASE)
            for indicator in format_indicators
        )

        assert found_format, (
            "prompt deve exigir um formato claro de User Story "
            "(ex: 'Como um... eu quero... para que...')"
        )

    def test_prompt_has_few_shot_examples(self):
        """
        Verifica se o prompt contém exemplos concretos de entrada/saída (Few-shot Learning).

        Procura por:
        - Mensagens com role='user' (exemplos de entrada)
        - Mensagens com role='assistant' (exemplos de saída)
        - Múltiplos exemplos para cobrir casos diferentes
        """
        messages = self.prompt_data.get("messages", [])

        user_examples = [msg for msg in messages if msg.get("role") == "user"]
        assistant_examples = [msg for msg in messages if msg.get("role") == "assistant"]

        assert len(user_examples) > 0, (
            "prompt deve conter exemplos de entrada (mensagens com role='user')"
        )
        assert len(assistant_examples) > 0, (
            "prompt deve conter exemplos de saída (mensagens com role='assistant')"
        )

        # Verificar que há exemplos com conteúdo significativo
        for example in user_examples + assistant_examples:
            content = example.get("content", "").strip()
            assert content, "exemplos não podem estar vazios"
            assert len(content) > 20, "exemplos devem ter conteúdo significativo"

    def test_prompt_no_todos(self):
        """
        Garante que não há placeholders incompletos ou TODOs no texto do prompt.

        Procura por padrões comuns:
        - [TODO]
        - TODO:
        - FIXME:
        - [PLACEHOLDER]
        - ...incomplete...
        """
        messages = self.prompt_data.get("messages", [])
        full_content = "\n".join([msg.get("content", "") for msg in messages])

        forbidden_patterns = [
            r"\[TODO\]",
            r"TODO:",
            r"FIXME:",
            r"\[PLACEHOLDER\]",
            r"\[INCOMPLETO\]",
            r"\[INCOMPLETE\]",
        ]

        found_issues = [
            pattern for pattern in forbidden_patterns
            if re.search(pattern, full_content, re.IGNORECASE)
        ]

        assert not found_issues, (
            f"prompt contém placeholders ou TODOs incompletos: {found_issues}. "
            "Garanta que o prompt está completo antes de publicar."
        )

    def test_minimum_techniques(self):
        """
        Verifica se pelo menos 2 técnicas de prompt engineering foram aplicadas.

        Valida o campo metadata.techniques do YAML.
        Técnicas esperadas: Role Prompting, Few-shot Learning, Chain of Thought, etc.
        """
        metadata = self.prompt_data.get("metadata", {})
        techniques = metadata.get("techniques", [])

        assert isinstance(techniques, list), "metadata.techniques deve ser uma lista"
        assert len(techniques) >= 2, (
            f"prompt deve usar pelo menos 2 técnicas de prompt engineering. "
            f"Encontradas: {techniques}. "
            f"Exemplos: Role Prompting, Few-shot Learning, Chain of Thought, Tree of Thought"
        )

        # Verificar que cada técnica é uma string não-vazia
        for technique in techniques:
            assert isinstance(technique, str), f"técnica deve ser string, encontrado: {type(technique)}"
            assert technique.strip(), "técnicas não podem estar vazias"

        # Informar quais técnicas foram encontradas
        print(f"\n✓ Técnicas aplicadas: {', '.join(techniques)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
