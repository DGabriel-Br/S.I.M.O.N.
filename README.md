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
- persistir Claims com estado epistemológico e evidência de origem;
- manter Claims contraditórias sem sobrescrevê-las silenciosamente;
- substituir explicitamente Claims de estado atual preservando o histórico;
- materializar o schema atual do próprio SIMON como uma Claim observada;
- persistir Goals com estado desejado e critérios de sucesso explícitos;
- recuperar Goals ainda abertos após uma nova conexão com o banco;
- persistir Plans versionados ligados a Goals;
- substituir um Plan ativo por nova revisão sem apagar o histórico anterior;
- persistir Actions ligadas a Goal, Plan e step;
- reconciliar Actions que perderam continuidade durante reinicialização;
- persistir VerificationResults imutáveis ligados a Actions ou Goals;
- preservar verificações anteriores quando nova evidência surgir;
- manter execução e verificação como fatos separados;
- persistir Experiences como unidades causais ligadas a Goals, Events, Actions e VerificationResults;
- suspender Experiences ativas quando o runtime perde continuidade;
- preservar outcome e resumo sem substituir as evidências originais.

Ainda não existem Memory, Cognition, modelos ou Lab executáveis.

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

Introduzir `Memory`, começando por memória episódica e semântica derivada de Experiences relevantes, sem transformar todo histórico bruto em memória permanente.
