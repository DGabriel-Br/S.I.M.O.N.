# S.I.M.O.N.

**Simples Inteligência, Mais Ou Menos Normal**

S.I.M.O.N. é um sistema cognitivo pessoal, local-first e persistente. O projeto começa deliberadamente pequeno: primeiro construímos um núcleo confiável capaz de manter estado fora do contexto do modelo e continuar uma tarefa após reinicialização.

A especificação oficial está em [`SIMON_SPEC.md`](SIMON_SPEC.md).

## Estado atual

Primeiro bootstrap executável do v0.1.

Neste ponto o projeto apenas:

- inicia pelo comando `simon` ou `python -m simon`;
- resolve o diretório local de dados;
- cria e abre um banco SQLite;
- lê a versão atual do schema pelo `PRAGMA user_version`;
- encerra sem manter estado cognitivo em memória do processo.

Ainda não existem World, Goals, Cognition, modelos, Memory ou Lab implementados.

## Preparação

Requer Python 3.14 e `uv`.

```powershell
uv sync --group dev
```

## Executar

```powershell
uv run simon
```

Ou:

```powershell
uv run python -m simon
```

Por padrão, os dados locais ficam em `.simon/` no diretório atual. Outro diretório pode ser usado sem alterar código:

```powershell
uv run simon --data-dir C:\caminho\para\dados
```

## Verificações de desenvolvimento

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
```

## Próximo passo

Implementar a primeira migration do Canonical Data Model mínimo somente quando o primeiro objeto persistente for realmente necessário.
