# S.I.M.O.N.

**Simples Inteligência, Mais Ou Menos Normal**

S.I.M.O.N. é um sistema cognitivo pessoal, local-first e persistente. O projeto começa deliberadamente pequeno: primeiro construímos um núcleo confiável capaz de manter estado fora do contexto do modelo e continuar uma tarefa após reinicialização.

A especificação oficial está em [`SIMON_SPEC.md`](SIMON_SPEC.md).

## Estado atual

Fundação persistente inicial do v0.1.

O projeto já consegue:

- iniciar pelo comando `simon` ou `python -m simon`;
- resolver o diretório local de dados;
- criar e migrar um banco SQLite;
- persistir Events imutáveis;
- persistir Entities com identidade estável e aliases;
- manter uma Entity canônica para o próprio SIMON;
- relacionar `system.started` à Entity do SIMON;
- reconstruir Events e Entities em uma nova conexão com o banco.

Ainda não existem Claims, World State, Goals, Cognition, modelos, Memory ou Lab executáveis.

## Preparação

Requer Python 3.14 e `uv`.

```powershell
uv sync
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

Introduzir `Claim`, a primeira representação persistente de algo que o SIMON acredita sobre uma Entity, mantendo evidência e estado epistemológico separados do Event Log.
