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
- preservar outcome e resumo sem substituir as evidências originais;
- persistir Memories derivadas explicitamente de Experiences fechadas;
- recuperar apenas Memories ativas por texto, tipo, escopo e Entity;
- preservar proveniência de Experiences, Claims e Entities nas Memories;
- retirar Memories arquivadas, substituídas ou retraídas do retrieval normal.

O primeiro adapter de modelo local já existe:

- `ModelProvider` define o contrato mínimo usado pelo SIMON;
- `OllamaProvider` implementa o primeiro runtime local sem acoplar o restante do sistema ao Ollama;
- respostas estruturadas usam JSON Schema gerado por Pydantic e são validadas antes de entrar no sistema;
- `model-check` verifica o runtime e lista modelos já instalados;
- `model-test` executa uma chamada estruturada de diagnóstico em um modelo escolhido explicitamente.

Ainda não existe um Cognition Controller, roteamento entre modelos ou escolha automática de modelo.

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

## Diagnóstico do runtime local

Com o Ollama em execução:

```powershell
uv run simon model-check
```

Para testar structured output com um modelo já instalado:

```powershell
uv run simon model-test --model NOME_DO_MODELO
```

O SIMON não baixa nem escolhe um modelo automaticamente neste estágio.

## Próximo passo

Escolher o primeiro modelo local por medição no hardware real e então introduzir o primeiro `CognitiveJob` que use o `ModelProvider` sem carregar histórico de chat como estado.

## Primeira interpretação cognitiva

Com um modelo local já instalado no Ollama, o SIMON pode executar sua primeira função cognitiva estruturada:

```powershell
uv run simon interpret --model qwen3.5:4b-q4_K_M "Veja por que esse script está falhando"
```

A interpretação retorna intenção, objetivo explícito, entidades mencionadas e ambiguidades. Ela não cria Goal nem executa ações automaticamente.

A entrada e o resultado estruturado são preservados como Events com o mesmo `trace_id`, preparando a base de observabilidade sem criar ainda um objeto persistente `CognitiveJob`.

