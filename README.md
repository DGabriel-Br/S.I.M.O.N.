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
- retirar Memories arquivadas, substituídas ou retraídas do retrieval normal;
- interpretar entradas do usuário em um contrato cognitivo estruturado;
- montar contexto cognitivo determinístico com Goals abertos, Entities explicitamente mencionadas, Claims atuais e Memories relacionadas;
- registrar a seleção de contexto como Event sem criar um objeto persistente adicional;
- formular propostas estruturadas de Goal para solicitações (`REQUEST`) sem persistir o Goal automaticamente;
- aceitar explicitamente uma proposta registrada e convertê-la em um Goal `USER` persistente sem nova decisão do modelo;
- formular propostas curtas de Plan para Goals autorizados, com passos epistêmicos ou de mundo, dependências, capabilities abstratas e verificação, sem executar o Plan automaticamente;
- materializar uma proposta validada como revisão persistente de Plan, preservando proveniência e idempotência;
- avaliar deterministicamente a prontidão dos steps de um Plan antes de criar qualquer Action;
- exigir dependências verificadas, preconditions resolvidas e capability disponível antes de considerar um step executável.

O primeiro adapter de modelo local já existe:

- `ModelProvider` define o contrato mínimo usado pelo SIMON;
- `OllamaProvider` implementa o primeiro runtime local sem acoplar o restante do sistema ao Ollama;
- respostas estruturadas usam JSON Schema gerado por Pydantic e são validadas antes de entrar no sistema;
- `model-check` verifica o runtime e lista modelos já instalados;
- `model-test` executa uma chamada estruturada de diagnóstico em um modelo escolhido explicitamente.

Ainda não existe um Cognition Controller, roteamento entre modelos ou escolha automática de modelo. O Context Builder atual é deliberadamente limitado e não usa busca vetorial, resolução fuzzy de entidades ou histórico de chat como estado.

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

## Proposta de Goal

Uma solicitação já classificada como `REQUEST` pode ser transformada em uma proposta explícita de Goal:

```powershell
uv run simon goal-propose --model qwen3.5:4b-q4_K_M "Veja por que esse script está falhando e corrija"
```

A proposta contém título, estado desejado, critérios de sucesso e questões em aberto. Ela é registrada como resultado cognitivo, mas não é inserida na tabela de Goals. O modelo também não cria Plan, não escolhe Tools e não executa ações nessa etapa.

Ao final, o comando imprime o ID imutável do Event que contém a proposta. A persistência do Goal exige um segundo comando explícito:

```powershell
uv run simon goal-accept evt_ID_DA_PROPOSTA
```

`goal-accept` não chama o modelo novamente. Ele aceita exatamente a proposta registrada naquele Event, fixa `origin=USER`, persiste o Goal em estado `ACTIVE` e grava um Event `goal.proposal.accepted` com a proveniência da decisão. Executar a aceitação novamente para a mesma proposta é idempotente e não cria um Goal duplicado.

Questões em aberto continuam preservadas no Event de aceitação para não serem perdidas, mas não são inventadas nem resolvidas pelo gate.

## Proposta de Plan

Um Goal já autorizado pode ser enviado ao primeiro Planner cognitivo:

```powershell
uv run simon plan-propose --model qwen3.5:4b-q4_K_M gol_ID_DO_GOAL
```

O Planner recebe o Goal persistente, as questões em aberto preservadas durante a aceitação e um recorte determinístico do contexto. A saída contém uma estratégia curta com passos `EPISTEMIC` ou `WORLD`, dependências, precondições, capability abstrata e forma de verificação.

Quando falta informação, o Planner deve preferir trabalho epistêmico para obtê-la em vez de inventar arquivos, erros ou caminhos. A proposta é registrada como `cognition.plan_proposal.completed` e não executa nenhuma Action.

Uma proposta validada pode ser materializada sem nova chamada ao modelo:

```powershell
uv run simon plan-materialize evt_ID_DA_PROPOSTA
```

A materialização é idempotente por Event de proposta. Uma nova proposta para o mesmo Goal cria nova revisão e marca o Plan anterior como `SUPERSEDED`.

## Prontidão do próximo step

O SIMON pode avaliar o Plan ativo de um Goal sem criar nem executar uma Action:

```powershell
uv run simon plan-next gol_ID_DO_GOAL
```

A seleção é determinística. Um step somente pode aparecer como `READY` quando o Goal está `ACTIVE`, todas as dependências possuem Action concluída com Verification `VERIFIED`, não existe tentativa em andamento, as preconditions estão resolvidas e a capability requerida está disponível.

No corte atual ainda não existe Capability Registry nem resolvedor de preconditions. Por isso, capabilities não registradas e preconditions textuais são bloqueadores explícitos. Uma Action `COMPLETED` sem Verification também não libera dependências. Tentativas anteriores com falha, bloqueio, negação, interrupção ou cancelamento exigem revisão antes de retry.

A avaliação registra apenas um Event `plan.readiness.evaluated`; ela não cria Action.

## Próximo passo

Introduzir a primeira capability operacional mínima exigida por um Plan real, mantendo Policy e Tool execution fora do caminho até que o step esteja efetivamente pronto.

## Primeira interpretação cognitiva

Com um modelo local já instalado no Ollama, o SIMON pode executar sua primeira função cognitiva estruturada:

```powershell
uv run simon interpret --model qwen3.5:4b-q4_K_M "Veja por que esse script está falhando"
```

A interpretação retorna intenção, objetivo explícito, entidades mencionadas e ambiguidades. Ela não cria Goal nem executa ações automaticamente.

Antes da chamada ao modelo, o Context Builder seleciona de forma determinística um recorte pequeno do estado persistente. Goals abertos entram apenas como resumo; Entities precisam ser mencionadas por nome ou alias conhecido; Claims e Memories são recuperadas somente a partir dessas referências ou de correspondência textual simples. O contexto é apresentado ao modelo como dado, nunca como instrução.

A entrada, a seleção de contexto e o resultado estruturado são preservados como Events com o mesmo `trace_id`, preparando a base de observabilidade sem criar ainda um objeto persistente `CognitiveJob`.

