"""
Script COMPLETO para avaliar prompts otimizados.

Este script:
1. Carrega dataset de avaliação de arquivo .jsonl (datasets/bug_to_user_story.jsonl)
2. Cria/atualiza dataset no LangSmith
3. Puxa prompts otimizados do LangSmith Hub (fonte única de verdade)
4. Executa prompts contra o dataset
5. Calcula 4 métricas específicas (Tone, Acceptance Criteria, User Story Format, Completeness)
6. Publica resultados no dashboard do LangSmith (Experiments)
7. Exibe resumo no terminal

Suporta múltiplos providers de LLM:
- OpenAI (gpt-4o, gpt-4o-mini)
- Google Gemini (gemini-2.0-flash)

Configure o provider no arquivo .env através da variável LLM_PROVIDER.
"""

import os
import sys
import json
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any
from pathlib import Path
from dotenv import load_dotenv  # type: ignore
from langsmith import Client  # type: ignore
from langsmith.schemas import RunTypeEnum  # type: ignore
from langchain import hub  # type: ignore
from langchain_core.prompts import ChatPromptTemplate  # type: ignore
from utils import check_env_vars, format_score, print_section_header, get_llm as get_configured_llm  # type: ignore
from metrics import (  # type: ignore
    evaluate_tone_score,
    evaluate_acceptance_criteria_score,
    evaluate_user_story_format_score,
    evaluate_completeness_score,
    evaluate_metrics_parallel
)

load_dotenv()


def get_llm():
    return get_configured_llm(temperature=0)


def load_dataset_from_jsonl(jsonl_path: str) -> List[Dict[str, Any]]:
    examples = []

    try:
        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    example = json.loads(line)
                    examples.append(example)

        return examples

    except FileNotFoundError:
        print(f"❌ Arquivo não encontrado: {jsonl_path}")
        print("\nCertifique-se de que o arquivo datasets/bug_to_user_story.jsonl existe.")
        return []
    except json.JSONDecodeError as e:
        print(f"❌ Erro ao parsear JSONL: {e}")
        return []
    except Exception as e:
        print(f"❌ Erro ao carregar dataset: {e}")
        return []


def create_evaluation_dataset(client: Client, dataset_name: str, jsonl_path: str) -> str:
    print(f"Criando dataset de avaliação: {dataset_name}...")

    examples = load_dataset_from_jsonl(jsonl_path)

    if not examples:
        print("❌ Nenhum exemplo carregado do arquivo .jsonl")
        return dataset_name

    print(f"   ✓ Carregados {len(examples)} exemplos do arquivo {jsonl_path}")

    try:
        datasets = client.list_datasets(dataset_name=dataset_name)
        existing_dataset = None

        for ds in datasets:
            if ds.name == dataset_name:
                existing_dataset = ds
                break

        if existing_dataset:
            print(f"   ✓ Dataset '{dataset_name}' já existe, usando existente")
            return dataset_name
        else:
            dataset = client.create_dataset(dataset_name=dataset_name)

            for example in examples:
                client.create_example(
                    dataset_id=dataset.id,
                    inputs=example["inputs"],
                    outputs=example["outputs"]
                )

            print(f"   ✓ Dataset criado com {len(examples)} exemplos")
            return dataset_name

    except Exception as e:
        print(f"   ⚠️  Erro ao criar dataset: {e}")
        return dataset_name


def pull_prompt_from_langsmith(prompt_name: str) -> ChatPromptTemplate:
    try:
        print(f"   Puxando prompt do LangSmith Hub: {prompt_name}")
        prompt = hub.pull(prompt_name)
        print(f"   ✓ Prompt carregado com sucesso")
        return prompt

    except Exception as e:
        error_msg = str(e).lower()

        print(f"\n{'=' * 70}")
        print(f"❌ ERRO: Não foi possível carregar o prompt '{prompt_name}'")
        print(f"{'=' * 70}\n")

        if "not found" in error_msg or "404" in error_msg:
            print("⚠️  O prompt não foi encontrado no LangSmith Hub.\n")
            print("AÇÕES NECESSÁRIAS:")
            print("1. Verifique se você já fez push do prompt otimizado:")
            print(f"   python src/push_prompts.py")
            print()
            print("2. Confirme se o prompt foi publicado com sucesso em:")
            print(f"   https://smith.langchain.com/prompts")
            print()
            print(f"3. Certifique-se de que o nome do prompt está correto: '{prompt_name}'")
        else:
            print(f"Erro técnico: {e}\n")
            print("Verifique:")
            print("- LANGSMITH_API_KEY está configurada corretamente no .env")
            print("- Você tem acesso ao workspace do LangSmith")
            print("- Sua conexão com a internet está funcionando")

        print(f"\n{'=' * 70}\n")
        raise


def evaluate_prompt_on_example(
    prompt_template: ChatPromptTemplate,
    example: Any,
    llm: Any,
    client: Client,
    project_name: str
) -> Dict[str, Any]:
    try:
        inputs = example.inputs if hasattr(example, 'inputs') else {}
        outputs = example.outputs if hasattr(example, 'outputs') else {}

        # Criar run no LangSmith para tracing
        run_id = str(uuid.uuid4())
        try:
            client.create_run(
                id=run_id,
                name="prompt_evaluation",
                run_type=RunTypeEnum.chain,
                inputs=inputs,
                reference_example_id=example.id,
                project_name=project_name,
            )
        except Exception:
            run_id = None

        chain = prompt_template | llm
        response = chain.invoke(inputs)
        answer = response.content

        # Fechar o run com a resposta
        if run_id:
            try:
                client.update_run(
                    run_id=run_id,
                    outputs={"answer": answer},
                    end_time=datetime.now(timezone.utc),
                )
            except Exception:
                pass

        reference = outputs.get("reference", "") if isinstance(outputs, dict) else ""

        if isinstance(inputs, dict):
            question = inputs.get("question", inputs.get("bug_report", inputs.get("pr_title", "N/A")))
        else:
            question = "N/A"

        return {
            "answer": answer,
            "reference": reference,
            "question": question,
            "run_id": run_id
        }

    except Exception as e:
        print(f"      ⚠️  Erro ao avaliar exemplo: {e}")
        import traceback
        print(f"      Traceback: {traceback.format_exc()}")
        return {
            "answer": "",
            "reference": "",
            "question": "",
            "run_id": None
        }


def send_feedback_to_langsmith(
    client: Client,
    run_id: str,
    metrics: Dict[str, float]
) -> None:
    """Envia os scores de cada exemplo para o LangSmith como feedback."""
    if not run_id:
        return
    try:
        for key, score in metrics.items():
            client.create_feedback(
                run_id=run_id,
                key=key,
                score=score,
            )
    except Exception as e:
        print(f"      ⚠️  Erro ao enviar feedback para LangSmith: {e}")


def evaluate_prompt(
    prompt_name: str,
    dataset_name: str,
    client: Client,
    project_name: str
) -> Dict[str, float]:
    print(f"\n🔍 Avaliando: {prompt_name}")

    try:
        prompt_template = pull_prompt_from_langsmith(prompt_name)

        examples = list(client.list_examples(dataset_name=dataset_name))
        print(f"   Dataset: {len(examples)} exemplos")

        llm = get_llm()

        tone_scores = []
        acceptance_scores = []
        format_scores = []
        completeness_scores = []

        print("   Avaliando exemplos...")

        for i, example in enumerate(examples, 1):
            result = evaluate_prompt_on_example(
                prompt_template, example, llm, client, project_name
            )

            if result["answer"]:
                metrics = evaluate_metrics_parallel(
                    result["question"],
                    result["answer"],
                    result["reference"]
                )

                tone_scores.append(metrics["tone"])
                acceptance_scores.append(metrics["acceptance_criteria"])
                format_scores.append(metrics["user_story_format"])
                completeness_scores.append(metrics["completeness"])

                # Enviar scores para o LangSmith
                send_feedback_to_langsmith(client, result["run_id"], metrics)

                print(f"      [{i}/{len(examples)}] Tone:{metrics['tone']:.2f} Acceptance:{metrics['acceptance_criteria']:.2f} Format:{metrics['user_story_format']:.2f} Completeness:{metrics['completeness']:.2f}")

        avg_tone = float(sum(tone_scores) / len(tone_scores) if tone_scores else 0.0)
        avg_acceptance = float(sum(acceptance_scores) / len(acceptance_scores) if acceptance_scores else 0.0)
        avg_format = float(sum(format_scores) / len(format_scores) if format_scores else 0.0)
        avg_completeness = float(sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0)

        return {
            "tone": float(f"{avg_tone:.4f}"),
            "acceptance_criteria": float(f"{avg_acceptance:.4f}"),
            "user_story_format": float(f"{avg_format:.4f}"),
            "completeness": float(f"{avg_completeness:.4f}")
        }

    except Exception as e:
        print(f"   ❌ Erro na avaliação: {e}")
        return {
            "tone": 0.0,
            "acceptance_criteria": 0.0,
            "user_story_format": 0.0,
            "completeness": 0.0
        }


def display_results(prompt_name: str, scores: Dict[str, float]) -> bool:
    print("\n" + "=" * 50)
    print(f"Prompt: {prompt_name}")
    print("=" * 50)

    print("\nMétricas de Avaliação:")
    print(f"  - Tone Score:           {format_score(scores['tone'], threshold=0.9)}")
    print(f"  - Acceptance Criteria:  {format_score(scores['acceptance_criteria'], threshold=0.9)}")
    print(f"  - User Story Format:    {format_score(scores['user_story_format'], threshold=0.9)}")
    print(f"  - Completeness:         {format_score(scores['completeness'], threshold=0.9)}")

    average_score = sum(scores.values()) / len(scores)
    all_above_threshold = all(v >= 0.9 for v in scores.values())

    print("\n" + "-" * 50)
    print(f"📊 MÉDIA GERAL: {average_score:.4f}")
    print("-" * 50)

    passed = average_score >= 0.9 and all_above_threshold

    if passed:
        print(f"\n✅ STATUS: APROVADO - Todas as métricas >= 0.9")
    else:
        print(f"\n❌ STATUS: REPROVADO")
        for k, v in scores.items():
            if v < 0.9:
                print(f"   ⚠️  {k}: {v:.4f} (abaixo de 0.9)")

    return passed


def main():
    print_section_header("AVALIAÇÃO DE PROMPTS OTIMIZADOS")

    provider = os.getenv("LLM_PROVIDER", "openai")
    llm_model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    eval_model = os.getenv("EVAL_MODEL", "gpt-4o")

    print(f"Provider: {provider}")
    print(f"Modelo Principal: {llm_model}")
    print(f"Modelo de Avaliação: {eval_model}\n")

    required_vars = ["LANGSMITH_API_KEY", "LLM_PROVIDER"]
    if provider == "openai":
        required_vars.append("OPENAI_API_KEY")
    elif provider in ["google", "gemini"]:
        required_vars.append("GOOGLE_API_KEY")

    if not check_env_vars(required_vars):
        return 1

    client = Client()
    project_name = os.getenv("LANGSMITH_PROJECT", "prompt-optimization-challenge-resolved")

    jsonl_path = "datasets/bug_to_user_story.jsonl"

    if not Path(jsonl_path).exists():
        print(f"❌ Arquivo de dataset não encontrado: {jsonl_path}")
        print("\nCertifique-se de que o arquivo existe antes de continuar.")
        return 1

    dataset_name = "prompt-optimization-challenge-resolved-eval"
    create_evaluation_dataset(client, dataset_name, jsonl_path)

    username = os.getenv("USERNAME_LANGSMITH_HUB")
    if not username:
        print("❌ Variável USERNAME_LANGSMITH_HUB não configurada no .env")
        return 1

    prompts_to_evaluate = [
        # "leonanluppi/bug_to_user_story_v1",
        f"{username}/bug_to_user_story_v2",
    ]

    print("\n" + "=" * 70)
    print("PROMPTS PARA AVALIAR")
    print("=" * 70)
    print("\nEste script irá puxar prompts do LangSmith Hub.")
    print("Certifique-se de ter feito push dos prompts antes de avaliar:")
    print("  python src/push_prompts.py\n")

    all_passed = True
    evaluated_count = 0
    results_summary = []

    for prompt_name in prompts_to_evaluate:
        evaluated_count += 1

        try:
            scores = evaluate_prompt(prompt_name, dataset_name, client, project_name)
            passed = display_results(prompt_name, scores)
            all_passed = all_passed and passed

            results_summary.append({
                "prompt": prompt_name,
                "scores": scores,
                "passed": passed
            })

        except Exception as e:
            print(f"\n❌ Falha ao avaliar '{prompt_name}': {e}")
            all_passed = False

            results_summary.append({
                "prompt": prompt_name,
                "scores": {
                    "tone": 0.0,
                    "acceptance_criteria": 0.0,
                    "user_story_format": 0.0,
                    "completeness": 0.0
                },
                "passed": False
            })

    print("\n" + "=" * 50)
    print("RESUMO FINAL")
    print("=" * 50 + "\n")

    if evaluated_count == 0:
        print("⚠️  Nenhum prompt foi avaliado")
        return 1

    print(f"Prompts avaliados: {evaluated_count}")
    print(f"Aprovados: {sum(1 for r in results_summary if r['passed'])}")
    print(f"Reprovados: {sum(1 for r in results_summary if not r['passed'])}\n")

    if all_passed:
        print("✅ Todos os prompts atingiram média >= 0.9!")
        print(f"\n✓ Confira os resultados em:")
        print(f"  https://smith.langchain.com/projects/p/{project_name}")
        print("\nPróximos passos:")
        print("1. Documente o processo no README.md")
        print("2. Capture screenshots das avaliações")
        print("3. Faça commit e push para o GitHub")
        return 0
    else:
        print("⚠️  Alguns prompts não atingiram média >= 0.9")
        print("\nPróximos passos:")
        print("1. Refatore os prompts com score baixo")
        print("2. Faça push novamente: python src/push_prompts.py")
        print("3. Execute: python src/evaluate.py novamente")
        return 1


if __name__ == "__main__":
    sys.exit(main())