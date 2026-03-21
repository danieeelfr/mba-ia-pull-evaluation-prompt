.PHONY: help install pull push eval test all

help:
	@echo ""
	@echo "Comandos disponíveis:"
	@echo ""
	@echo "  make install   Instala as dependências do projeto"
	@echo "  make pull      Baixa o prompt original do LangSmith Hub"
	@echo "  make push      Publica o prompt otimizado no LangSmith Hub"
	@echo "  make eval      Roda a avaliação automática das métricas"
	@echo "  make test      Roda os testes de validação do prompt"
	@echo "  make all       Roda pull → push → eval → test em sequência"
	@echo ""

install:
	pip install -r requirements.txt

pull:
	python src/pull_prompts.py

push:
	python src/push_prompts.py

eval:
	python src/evaluate.py

test:
	pytest tests/test_prompts.py -v

all: pull push eval test
