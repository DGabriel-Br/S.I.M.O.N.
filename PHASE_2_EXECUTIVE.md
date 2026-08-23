# S.I.M.O.N. Fase 2: Executive mínimo

## Propósito

A v0.1.0 estabilizou o Core persistente. A Fase 2 não substitui esse Core. Ela adiciona uma camada de condução capaz de decidir qual operação já existente deve acontecer a seguir, mantendo intactas as fronteiras de autoridade, provenance e Verification.

O primeiro Executive não é um scheduler geral, um agente autônomo contínuo ou um Attention Manager completo. Seu primeiro trabalho é muito menor:

```text
estado persistido
+ solicitação foreground atual
+ readiness determinístico
=
próxima decisão operacional
```

A pergunta central é:

> Dado o estado que o Core já conhece, qual é a próxima coisa legítima a fazer?

## Princípio central

O Executive pode coordenar autoridade existente. Ele não pode criar autoridade nova.

Isso significa que uma decisão do Executive nunca transforma uma operação que hoje exige `source=user` em uma operação autônoma. O Executive pode preparar a próxima ação, explicar por que ela é necessária e apresentar o gate adequado, mas não pode registrar uma autorização humana que não aconteceu.

Da mesma forma, o Executive não reinterpreta `Verification`, não promove evidência antiga, não reabre Actions anteriores e não contorna blockers de `PlanReadiness`.

## Escopo do primeiro corte

O primeiro corte será foreground e single-focus:

```text
uma solicitação atual
+
zero ou um Goal selecionado
```

Se existir exatamente um Goal aberto, ele pode ser selecionado como foco. Se existirem vários Goals abertos e a solicitação atual não identificar um deles de forma inequívoca, o Executive deve pedir escolha. Não haverá ranking autônomo entre Goals neste corte.

Não haverá ainda:

- Background scheduler;
- FocusSession persistente;
- Attention scoring;
- preempção entre Goals;
- execução paralela;
- criação autônoma de Goals independentes;
- ampliação de escopo ou grants;
- seleção automática de Memory;
- escolha automática de modelo.

## Três classes de autoridade

### 1. Operações autônomas de condução

Podem ser escolhidas pelo Executive porque não fabricam consentimento humano e não criam um novo efeito externo autorizado em nome do usuário.

Exemplos do Core atual:

- reconstruir estado com `resume`;
- avaliar readiness do Plan;
- interpretar uma entrada;
- formular proposta de Goal;
- formular proposta de Plan;
- materializar uma proposta de Plan válida para um Goal já autorizado;
- criar a próxima `user.ask` quando o Plan exige informação;
- executar `process-verify`;
- executar `file-verify`;
- executar assessments semânticos;
- concluir um Plan quando todos os steps atuais continuam `VERIFIED`;
- avaliar semanticamente um Goal concluído por Plan;
- recuperar Memories relevantes para contexto.

Essas operações ainda precisam respeitar todos os contratos existentes do Core. "Autônoma" significa apenas que o Executive pode selecionar a operação, não que pode ignorar seus preconditions.

### 2. Operações vinculadas a um turno real do usuário

Algumas operações podem futuramente ser acionadas pelo Executive somente quando o turno atual do usuário for a própria resposta, seleção ou confirmação que o Core precisa.

Exemplos:

- aceitar uma proposta de Goal;
- responder uma `user.ask`;
- confirmar um assessment semântico;
- confirmar a conclusão de um Goal.

O primeiro Executive não deve inferir silenciosamente essas confirmações. Antes de automatizar esse roteamento, a Fase 2 precisa criar provenance explícita para o turno do usuário, permitindo provar qual texto humano originou o gate.

Até esse contrato existir, o Executive retorna `NEEDS_USER_INPUT` ou `NEEDS_USER_CONFIRMATION`.

### 3. Operações com autorização operacional explícita

Não podem ser deduzidas apenas do fato de o usuário desejar o Goal.

Exemplos atuais:

- `process.run`;
- `file.patch`;
- `process-retry`;
- `analysis-retry`;
- `file-retry`;
- promoção de Experience para Memory.

O Executive pode preparar os parâmetros e dizer exatamente o que pretende fazer. A execução só acontece depois do gate exigido pelo Core.

Uma solicitação genérica como "corrija meu script" não autoriza por si só qualquer comando arbitrário, workspace arbitrário ou alteração arbitrária de arquivo.

## Contrato de decisão

O primeiro Executive deve produzir uma decisão pequena e auditável. Conceitualmente, cada ciclo responde com um dos seguintes resultados:

```text
PROCEED
NEEDS_USER_INPUT
NEEDS_USER_CONFIRMATION
NEEDS_OPERATION_AUTHORIZATION
NEEDS_GOAL_SELECTION
BLOCKED
DONE
```

Quando o resultado for `PROCEED`, ele também identifica exatamente uma operação do Core a executar em seguida.

Quando o resultado exigir o usuário, deve expor o objeto concreto que aguarda decisão, como Goal proposal, Action, Verification, comando proposto ou Goal candidato.

Quando estiver `BLOCKED`, deve preservar os blockers do Core em vez de convertê-los em texto genérico.

O Executive não decide em loop infinito. Um ciclo executa no máximo uma operação de mudança de estado e reavalia o Core depois dela. Esse limite mantém cada transição observável e torna erros reproduzíveis.

## Ordem de precedência do primeiro corte

Para um Goal foreground já selecionado, a prioridade não nasce de um score probabilístico. Ela deriva do lifecycle persistido:

```text
1. Se existe Action em andamento ou aguardando usuário, lidar com esse estado.
2. Se a Action mais recente precisa de Verification, verificar ou avaliar.
3. Se existe confirmação humana pendente, parar no gate.
4. Se existe retry operacional possível, pedir autorização de retry.
5. Se existe falha epistemológica que exige replan, propor nova estratégia.
6. Se existe step READY, conduzir a capability correspondente.
7. Se todos os steps estão VERIFIED, concluir o Plan.
8. Se o Plan está COMPLETED e o Goal está ACTIVE, avaliar o Goal.
9. Se a conclusão do Goal exige confirmação, parar no gate.
10. Se o Goal está COMPLETED, encerrar o ciclo foreground.
```

Essa ordem não substitui `PlanReadiness`. Ela consome o estado já calculado pelo Core.

## O modelo não escolhe autoridade

O ModelProvider pode participar de:

- interpretação;
- proposta de Goal;
- proposta ou replanejamento de Plan;
- análise cognitiva;
- assessments semânticos.

Ele não decide:

- se uma autorização humana aconteceu;
- se um blocker pode ser ignorado;
- se um workspace pode ser expandido;
- se uma Action antiga volta a ser atual;
- se uma Verification antiga substitui a mais recente;
- se uma operação externa pode ser executada sem gate.

A decisão de próximo estado continua governada por código determinístico.

## Primeiro Golden Scenario da Fase 2

O primeiro cenário não adiciona nenhuma capability nova. Ele prova que o Executive consegue conduzir o Core v0.1.0 já existente.

Pré-condição: existe um Goal persistido com Plan ativo e steps que usam capabilities já implementadas.

O usuário pede em linguagem natural:

> Continue esse Goal.

O Executive deve:

```text
reconstruir estado
→ selecionar o único Goal aberto ou pedir escolha
→ avaliar readiness
→ executar automaticamente somente operações de condução permitidas
→ parar em gates reais
→ depois de cada transição, reconstruir e decidir novamente
→ chegar a DONE quando o Goal estiver concluído
```

Exemplo de comportamento esperado:

```text
process.run READY
→ NEEDS_OPERATION_AUTHORIZATION

usuário autoriza a execução concreta
→ process.run
→ process-verify automaticamente
→ cognition.analyze quando READY
→ analysis-assess automaticamente
→ NEEDS_USER_CONFIRMATION se o assessment for SATISFIED
```

O cenário deve atravessar pelo menos um restart para provar que o Executive não depende de memória de processo.

## Por que não começamos com "corrija este script" completo

A v0.1.0 ainda não possui uma capability geral de leitura de arquivos nem um contrato que transforme análise em proposta estruturada de patch. Forçar o Executive a resolver isso agora misturaria duas evoluções diferentes:

```text
orquestração
+
nova percepção/capability de código
```

O primeiro corte prova apenas orquestração. Depois que isso estiver sólido, novas capabilities podem entrar porque um Golden Scenario real demonstrou necessidade.

## Critério de conclusão do Executive mínimo

O primeiro Executive estará pronto quando:

1. conseguir reconstruir o foco depois de restart;
2. nunca selecionar uma operação proibida pelos blockers atuais;
3. nunca fabricar `source=user`;
4. conduzir automaticamente Verification e operações internas seguras;
5. distinguir retry operacional de replanejamento epistemológico;
6. parar com uma razão estruturada quando precisa do usuário;
7. não escolher arbitrariamente entre múltiplos Goals;
8. concluir um Goal já autorizado usando apenas os contratos v0.1.0;
9. possuir um teste integrado que prove o cenário acima.

## Primeiro decisor implementado

A linha `0.2.0.dev0` introduz `ExecutiveDecision` em `simon.executive`. `decide_next()` reconstrói o estado persistido e produz uma decisão read-only. A decisão contém `outcome`, `reason_code`, uma operação quando aplicável, indicação de dependência de modelo e referências concretas para Goal, Plan, step, Action, Verification, capability e blockers.

O decisor já distingue:

- múltiplos Goals abertos, sem seleção arbitrária;
- `user.ask` aguardando resposta real;
- Verification objetiva ou assessment pendente;
- confirmação humana de assessment;
- retry operacional autorizado;
- replanejamento por falha epistemológica;
- steps `READY` seguros ou sujeitos a autorização;
- binding `CHANGE/unknown` elegível para `file.patch`;
- conclusão determinística de Plan;
- assessment e gate de conclusão de Goal;
- Goal já concluído.

`decide_next()` não cria Event, Action ou Verification e não altera lifecycle. O comando `executive-next` apenas torna essa decisão observável na CLI.

## Primeiro runner foreground implementado

`run_executive_once()` consome a decisão atual e aplica a regra:

```text
decidir
→ executar no máximo uma operação PROCEED segura
→ reconstruir estado
→ expor a próxima decisão
→ parar
```

O runner nunca executa decisões `NEEDS_USER_INPUT`, `NEEDS_USER_CONFIRMATION` ou `NEEDS_OPERATION_AUTHORIZATION`. Operações cognitivas exigem um `ModelProvider` e um modelo explícitos; sem isso, o runner retorna `MODEL_REQUIRED` sem alterar o estado. Falha na operação produz `FAILED` e não autoriza automaticamente retry.

As operações `PROCEED` atualmente executáveis pelo runner são proposta e materialização de Plan, `user.ask`, `cognition.analyze`, Verification objetiva de `process.run` e `file.patch`, assessments semânticos, retry local de `user.ask`, conclusão determinística de Plan e assessment de Goal. Efeitos externos e confirmações continuam fora do runner.

Uma proposta de Plan não é materializada na mesma chamada. Depois de `plan.propose`, o decisor reconhece o Event pendente e retorna `plan.materialize` para o ciclo seguinte. Isso evita repetir propostas e preserva a regra de uma transição por ciclo.

A CLI expõe esse comportamento com:

```powershell
uv run simon executive-step [--model MODELO] [goal_id]
```

## Golden Scenario foreground integrado validado

O runner já possui um cenário integrado que percorre um Goal de correção de script em múltiplas chamadas independentes. O teste começa com um Plan persistido de cinco steps (`process.run`, `cognition.analyze`, `CHANGE/unknown`, `process.run`, `cognition.analyze`) e usa o Executive somente para operações `PROCEED` seguras.

O fluxo provado é:

```text
Executive para em process.run
→ usuário autoriza plan-run
→ novo processo executa process.verify
→ Executive executa cognition.analyze
→ Executive executa analysis.assess
→ para em NEEDS_USER_CONFIRMATION
→ usuário confirma
→ para em file.patch
→ usuário autoriza plan-patch
→ novo processo executa file.verify
→ para em process.run
→ usuário autoriza nova execução
→ novo processo executa process.verify
→ Executive analisa e avalia a saída final
→ usuário confirma o assessment
→ Executive conclui o Plan
→ Executive avalia o Goal
→ para em confirmação final
→ usuário conclui o Goal
→ novo processo reconstrói DONE
```

Os processos novos recebem apenas o diretório de dados e o `goal_id`; não compartilham objetos Python, provider ou contexto em memória com o processo anterior. Isso prova que a continuidade do Executive deriva do SQLite e dos contratos do Core.

O cenário também prova que `executive-step` não atravessa `NEEDS_OPERATION_AUTHORIZATION` nem `NEEDS_USER_CONFIRMATION`. Efeitos externos e confirmações continuam acontecendo pelos gates explícitos já existentes.

Nenhuma mudança de produção ou migration foi necessária para essa validação. O próximo incremento pode evoluir a ergonomia foreground, mas não precisa criar um loop contínuo para provar continuidade.

## Condutor foreground limitado

`run_executive_until_gate()` reutiliza o runner de uma transição para avançar por uma sequência de decisões `PROCEED` seguras. Depois de cada transição o estado é reconstruído antes de qualquer nova decisão. O condutor para imediatamente quando encontra input humano, confirmação, autorização operacional, falta de modelo, falha, `DONE` ou o limite configurado de transições.

A CLI expõe o fluxo com:

```powershell
uv run simon executive-continue [--model MODELO] [--max-transitions 32] [goal_id]
```

O limite existe mesmo em foreground para que uma inconsistência de readiness não possa produzir um loop sem fronteira. Atingir o limite não autoriza a operação seguinte; a decisão final permanece observável e uma nova chamada pode continuar a partir do SQLite.

O condutor não muda a classificação de autoridade. `process.run`, `file.patch`, retries operacionais, respostas do usuário e confirmações continuam interrompendo o fluxo. O ganho é apenas ergonômico: várias operações internas consecutivas podem ser conduzidas em uma chamada sem esconder os estados intermediários, que continuam persistidos e são registrados no receipt da execução.
## Primeiro gateway de turno humano

A entrada foreground passa a ter provenance explícita com `handle_user_turn()` e o comando `user-turn`. Fora de um gate que já espera contribuição humana, o primeiro intent de controle suportado é deliberadamente estreito: `CONTINUE`. A classificação desse comando é determinística e não usa ModelProvider, porque interpretar linguagem aproximada como grant operacional violaria a fronteira de autoridade desta fase.

O turno literal é persistido antes da condução como:

```text
user.turn.received
source=user
text=<texto literal>
requested_goal_id=<opcional>
```

Quando o intent é reconhecido, o Executive usa `run_executive_until_gate()` sem ganhar permissões adicionais. Um segundo Event de sistema, `executive.user_turn.routed`, referencia o turno pelo `trace_id` e registra `authority_scope=EXECUTIVE_SAFE_CONTINUATION`, status do condutor, transições executadas e decisão final. Isso torna auditável a diferença entre "o usuário pediu para continuar" e "o usuário autorizou um efeito específico".

Exemplos aceitos neste corte incluem `continue`, `continue esse Goal` e variantes explícitas de `continue este objetivo`. Expressões ambíguas como `pode continuar` não são tratadas como `CONTINUE`, e ordens como `execute tudo` são persistidas como `user.turn.unhandled` sem executar qualquer operação.

O comando `CONTINUE` preserva integralmente os gates existentes:

```text
"continue esse Goal"
→ Executive conduz apenas PROCEED seguro
→ process.run READY
→ NEEDS_OPERATION_AUTHORIZATION
→ PARA
```

Com múltiplos Goals abertos e nenhum `--goal-id`, o resultado continua sendo `NEEDS_GOAL_SELECTION`. O gateway não cria ranking de foco. Modelo e `--max-transitions` são apenas repassados ao condutor para as operações já autorizadas pelo contrato do Executive. O SQLite permanece no schema 11.


## Respostas humanas vinculadas ao gate

O gateway passa a interpretar parte do turno pelo estado atual, não apenas pelo texto isolado. A regra é deliberadamente estreita: o significado contextual só existe quando `decide_next()` identifica um gate que já espera aquela categoria de contribuição humana.

Em `NEEDS_USER_INPUT` com operação `action.answer`, qualquer texto não vazio que não seja um comando `CONTINUE` explícito pode ser vinculado à `user.ask` `WAITING` atual. `answer_user_ask()` recebe o `action_id` da própria `ExecutiveDecision` e usa o ID de `user.turn.received` como `trace_id`; assim, a resposta fica causalmente ligada ao turno que a forneceu. Depois da resposta, o condutor retoma apenas operações `PROCEED` seguras.

Em `NEEDS_USER_CONFIRMATION`, o gateway exige uma confirmação afirmativa determinística e curta. `sim`, `confirmo`, `confirmado`, `sim confirmo` e `pode confirmar` são aceitos somente quando a decisão atual aponta `verification.confirm` ou `goal.complete`. O alvo confirmado é sempre o `verification_id` presente na decisão reconstruída. A função de confirmação revalida que o assessment ainda é atual antes de persistir qualquer efeito.

`NEEDS_OPERATION_AUTHORIZATION` só pode aceitar linguagem natural depois que existir uma operação concreta e persistida para aprovar. O primeiro caso implementado é `process.run`. `process-propose` recebe o mesmo `ProcessRunRequest` estruturado da execução e persiste `executive.operation.proposed` com executável, argv, `cwd`, timeout, Goal, Plan, revisão e step. Esse Event usa `source=system`: proposta não é autorização e não cria Action.

Quando o gate atual ainda é o mesmo `plan.run`, somente a proposta `process.run` mais recente daquele Goal é considerada. Um turno afirmativo explícito como `sim`, `autorizo` ou `pode executar` pode então consumir exatamente essa proposta. A execução chama o serviço `execute_next_process_run()` existente com o `trace_id` do `user.turn.received`; portanto o `process.run.authorized` continua sendo o Event autoritativo de `source=user`. A rota registra `authority_scope=CURRENT_OPERATION_PROPOSAL_ONLY` e o `proposal_event_id` consumido.

O mesmo contrato de proposta concreta passa a cobrir `file.patch`. `file-propose` recebe um `FilePatchRequest` com workspace, caminho relativo, trecho esperado e substituição e persiste `executive.operation.proposed` sem ler como autorização e sem modificar o filesystem. A proposta precisa continuar correspondente ao gate `plan.patch/file.patch`, ao mesmo Plan e revisão e ao mesmo step `CHANGE/unknown` antes de ser consumida. Um turno explícito como `sim`, `pode aplicar` ou `pode alterar` chama o executor `execute_next_file_patch()` existente com o `trace_id` do `user.turn.received`; portanto `file.patch.authorized` continua sendo a autoridade real de `source=user`.

Sem proposta concreta, texto afirmativo continua sem efeito. Uma proposta mais nova substitui a anterior para aquele Goal, e propostas que já não correspondem ao Plan/step atuais não podem ser consumidas. Retries só entram no gateway quando possuem uma proposta concreta correspondente ao gate atual.

Turnos contextuais roteados registram `executive.user_turn.routed` com um snapshot do gate consumido, `authority_scope` específico e referência ao efeito persistido. As scopes atuais são `CURRENT_USER_INPUT_GATE_ONLY`, `CURRENT_CONFIRMATION_GATE_ONLY` e `CURRENT_OPERATION_PROPOSAL_ONLY`. Fora desses gates, texto livre continua sem efeito. Nenhuma tabela ou migration nova é necessária.

## Propostas concretas para retries operacionais

O mesmo bridge de autorização concreta passa a cobrir retries de `process.run` e `file.patch`. Uma falha ou interrupção continua produzindo `NEEDS_OPERATION_AUTHORIZATION`; o gateway não transforma esse estado em retry automático e um turno afirmativo isolado continua sem efeito.

`process-retry-propose` recebe o `action_id` FAILED ou INTERRUPTED e um novo `ProcessRunRequest`. A proposta persiste `retry_of_action_id`, `previous_status`, Goal, Plan, revisão, step, critério de Verification, executável, argv, working directory e timeout. Nenhuma nova Action é criada nessa etapa.

`file-retry-propose` faz o equivalente para uma tentativa `file.patch`, congelando a Action anterior e um novo `FilePatchRequest` com workspace, caminho relativo, trecho esperado e substituição. A proposta não altera o filesystem e não antecipa as validações operacionais do executor.

Um turno afirmativo posterior só pode consumir a proposta de retry mais recente que ainda corresponda à `ExecutiveDecision` atual, inclusive ao mesmo `action_id` que o gate `retry_authorization_required` está pedindo para revisar. Se outra tentativa passar a ser a tentativa atual, a proposta antiga deixa de ser elegível.

A execução continua usando `retry_process_run()` ou `retry_file_patch()` com o ID de `user.turn.received` como `trace_id`. Portanto `action.retry.authorized` permanece o único Event autoritativo de `source=user`; `executive.operation.proposed` continua sendo apenas proposta.

`analysis.retry` usa um contrato separado, descrito abaixo, porque além da Action anterior ele precisa congelar modelo e evidência epistemicamente atual.


## Proposta concreta para retry cognitivo

`analysis.retry` continua sendo um gate `NEEDS_OPERATION_AUTHORIZATION`, mas sua proposta precisa conter mais contexto que os retries WORLD. `analysis-retry-propose --model MODELO act_ID` reconstrói a tentativa `cognition.analyze` `FAILED` ou `INTERRUPTED`, valida que ela é a tentativa atual do step e persiste `executive.operation.proposed` com `proposal_type=analysis.retry`.

A proposta congela `retry_of_action_id`, `previous_status`, Goal, Plan, revisão, step, critério de Verification, modelo e a sequência ordenada de `evidence_event_ids` atualmente obtida somente das tentativas anteriores cuja Verification mais recente continua `VERIFIED`. Nenhum provider é chamado, nenhuma nova Action é criada e `action.retry.authorized` ainda não existe nessa etapa.

Um turno afirmativo só pode consumir a proposta mais recente se `decide_next()` continuar pedindo `analysis.retry` para a mesma Action. Antes da execução, o gateway reconstrói novamente o contexto cognitivo e exige a mesma revisão de Plan, o mesmo critério de Verification e exatamente os mesmos IDs de evidência, na mesma ordem. Mudança epistemológica posterior torna a proposta stale.

A aprovação chama `retry_cognition_analysis()` com o modelo congelado na proposta e o `trace_id` de `user.turn.received`. O executor existente permanece responsável por criar `action.retry.authorized` com `source=user`, registrar o modelo e a evidência realmente consumida e criar a nova Action. Para reduzir uma janela entre revalidação e criação da Action, o executor também aceita a revisão e a sequência de evidência esperadas e recusa o retry se elas mudarem durante a autorização.

Na CLI, `user-turn` constrói o provider local mesmo quando o turno não recebe `--model`; isso não chama o modelo por si só. Se o gate consumido for uma proposta `analysis.retry`, o modelo vem obrigatoriamente da proposta. O parâmetro `--model` do turno continua sendo usado apenas pelo condutor para operações cognitivas seguras posteriores. Sem provider na API direta, a proposta não é consumida.

O SQLite permanece no schema 11.
