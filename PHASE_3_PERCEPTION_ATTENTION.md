# Fase 3 - Perception e Attention

## Objetivo

Abrir a próxima responsabilidade estrutural do S.I.M.O.N. depois do fechamento do Executive mínimo: receber sinais do ambiente como observações persistentes e decidir, de forma auditável, se eles merecem tratamento posterior.

O primeiro corte não implementa sensores autônomos nem aplica efeitos no World ou no Executive. Ele define somente a fronteira:

```text
SOURCE / SENSOR
↓
Observation
↓
Attention assessment
↓
IGNORE | RECORD | UPDATE_WORLD | ATTEND | INTERRUPT
```

A decisão de Attention é classificação, não autoridade operacional.

## Passo 73 - Observation -> Attention

### Observation

Uma observação explícita é persistida como Event:

```text
perception.observation.recorded
```

O payload mínimo contém:

- `observer`;
- `signal_kind`;
- `summary`;
- `details`.

O registro preserva:

- `observer` no payload;
- `source=perception` no Event, preservando a fronteira de autoridade;
- `trace_id`;
- `goal_id` opcional;
- `related_entity_ids` opcionais;
- instante de conhecimento pelo S.I.M.O.N.

`record_observation()` não cria Claim, não avança `world_revision`, não cria Goal e não altera foco.

Quando Goal ou Entities são informados explicitamente, eles precisam existir. O primeiro corte não tenta resolver entidades por similaridade nem criar entidades implicitamente.

### AttentionSignals

O primeiro classificador recebe somente sinais booleanos explicitamente conhecidos:

- `urgent`;
- `risk`;
- `goal_relevant`;
- `subscribed`;
- `world_change`;
- `known_noise`.

Não existe score numérico, peso aprendido ou threshold calibrado neste corte.

### Ordem determinística

A decisão usa uma tabela pequena de precedência:

```text
urgent OR risk
→ INTERRUPT

senão goal_relevant OR subscribed
→ ATTEND

senão world_change
→ UPDATE_WORLD

senão known_noise
→ IGNORE

senão
→ RECORD
```

A precedência é deliberada. Um sinal urgente não deixa de ser urgente porque também foi marcado como ruído; relevância foreground vence uma possível atualização de World; uma atualização candidata do World vence descarte por ruído.

### Persistência da avaliação

Cada avaliação é persistida como:

```text
attention.assessed
```

O Event preserva:

- `observation_event_id`;
- `destination`;
- sinais usados;
- razões determinísticas;
- `effect_applied=false`.

O `trace_id`, Goal e Entities da Observation são preservados na avaliação.

### O que os destinos significam neste passo

`IGNORE` significa que nenhuma etapa posterior foi solicitada.

`RECORD` significa que a Observation permanece apenas como conhecimento observado/auditável.

`UPDATE_WORLD` significa que a Observation é candidata a alimentar validação de Claims e materialização do World. Nenhuma Claim é escrita automaticamente.

`ATTEND` significa que a Observation merece entrar em uma futura disputa de atenção. O foco atual não é alterado.

`INTERRUPT` significa que a Observation possui urgência ou risco suficiente para ser candidata a interrupção. Nenhum Goal, Action ou Focus é interrompido automaticamente.

Essa separação evita transformar classificação em autoridade.

## Entrada operacional inicial

A CLI expõe uma borda explícita para teste e integração futura:

```powershell
uv run simon observe --source filesystem --kind file.changed --world-change "target.txt foi alterado"
```

Outro exemplo:

```powershell
uv run simon observe --source process-monitor --kind process.failed --urgent "processo crítico terminou inesperadamente"
```

A CLI registra a Observation, executa a avaliação determinística e mostra o destino. Ela não executa o destino.

## Deliberadamente fora do Passo 73

- watcher de filesystem;
- polling contínuo;
- timers e subscriptions persistentes;
- captura de tela, áudio, câmera ou OCR;
- interpretação cognitiva da Observation;
- validação e aceitação de Proposed Claims no Belief Store;
- escrita automática no World;
- mudança automática de foco;
- pausa ou interrupção de Goal/Action;
- ranking entre múltiplos itens de Attention;
- FocusSession;
- attention inertia;
- scoring probabilístico;
- daemon ou scheduler.

Esses mecanismos só devem nascer quando houver um problema concreto que exija cada um deles.

## Critérios de conclusão do Passo 73

O corte está concluído quando:

1. uma Observation explícita sobrevive a nova conexão com o banco;
2. Observation não altera `world_revision`;
3. Goal e Entities opcionais preservam provenance e não aceitam referências inexistentes;
4. os cinco destinos de Attention são alcançáveis por regras determinísticas;
5. a precedência entre sinais é testada;
6. `attention.assessed` preserva a Observation de origem e os sinais usados;
7. nenhum destino é aplicado ao World ou ao Executive;
8. a entrada `observe` atravessa a CLI sem criar capability implícita;
9. o schema SQLite permanece inalterado.


## Passo 74 - UPDATE_WORLD -> Proposed Claim

O primeiro consumidor de `UPDATE_WORLD` continua sem autoridade para alterar o World. Ele transforma uma avaliação já persistida em um candidato estruturado e auditável:

```text
perception.observation.recorded
↓
attention.assessed(destination=UPDATE_WORLD)
↓
world.claim.proposed
↓
Belief Store inalterado
world_revision inalterada
```

A proposta exige explicitamente:

- `attention_event_id` de um `attention.assessed` cujo destino seja `UPDATE_WORLD`;
- `subject_id` de uma Entity existente e já vinculada à Observation de origem;
- `predicate` não vazio;
- `value` compatível com o mesmo contrato JSON usado por Claims persistidas.

O primeiro corte usa `DIRECT_OBSERVATION` como estado epistemológico fixo. Outros estados pertencem a entradas futuras, como Declaration, derivação ou inferência, e não são inferidos a partir de texto livre neste passo.

A proposta é persistida somente como Event:

```text
world.claim.proposed
```

O payload preserva Observation, Attention assessment, subject, predicate, value, estado epistemológico, evidências e `effect_applied=false`. As evidências iniciais são a Observation e seu assessment de Attention.

A vinculação do subject à Observation é obrigatória. Uma observação relacionada à Entity A não pode ser reutilizada para propor silenciosamente uma Claim sobre a Entity B. Entity Resolution continua sendo responsabilidade anterior à Proposed Claim.

A CLI expõe uma entrada explícita para validar o contrato:

```powershell
uv run simon claim-propose `
    --attention-event-id evt_... `
    --subject-id ent_... `
    --predicate runtime.state `
    --value-json '{"state":"changed"}'
```

O comando não insere linha em `claims`, não substitui Claim ativa, não resolve conflitos e não avança `world_revision`.

### Deliberadamente fora do Passo 74

- aceitação automática da Proposed Claim;
- policy de autoridade por observer/domínio;
- schema validation específica por predicate;
- conflict resolution;
- supersede/retract automático;
- Entity Resolution automática;
- interpretação por LLM da Observation;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 74

1. somente `UPDATE_WORLD` pode alimentar o contrato;
2. a Proposed Claim referencia Observation e Attention assessment como evidência;
3. o subject precisa existir e estar ligado à Observation;
4. valor não serializável no contrato JSON é recusado;
5. `world.claim.proposed` sobrevive a nova conexão;
6. nenhuma linha é criada em `claims`;
7. `world_revision` permanece inalterada;
8. a CLI expõe a proposta sem aplicar o efeito;
9. o schema SQLite permanece na versão 11.

## Passo 75 - Proposed Claim -> validação contra Belief Store

A Proposed Claim continua sem autoridade para alterar o World. Antes de qualquer aceitação futura, ela pode ser comparada deterministicamente com a visão atual do Belief Store:

```text
world.claim.proposed
↓
world.claim.validation.completed
↓
READY | DUPLICATE | CONFLICT
↓
Belief Store inalterado
world_revision inalterada
```

A comparação usa somente Claims `ACTIVE` com o mesmo `subject_id + predicate`. O primeiro contrato não tenta interpretar domínio, confiança ou verdade semântica.

### Outcomes

`READY` significa que não existe Claim ativa naquele eixo. A proposta está livre de concorrência atual, mas ainda não foi aceita nem considerada verdadeira por policy de domínio.

`DUPLICATE` significa que existe ao menos uma Claim ativa com o mesmo `value` e o mesmo `epistemic_status`, sem nenhuma Claim ativa divergente para o eixo. Nenhuma duplicata é criada.

`CONFLICT` significa que existe ao menos uma Claim ativa diferente para o mesmo `subject + predicate`. Se Claims equivalentes e divergentes coexistirem, `CONFLICT` vence, pois ainda existe uma contradição real que precisa ser tratada.

A avaliação é persistida como:

```text
world.claim.validation.completed
```

O payload preserva `proposed_claim_event_id`, outcome, Claims ativas observadas, Claims equivalentes, Claims conflitantes, razões determinísticas e `effect_applied=false`. O Event reutiliza trace, Goal e Entities da Proposed Claim.

A CLI expõe o contrato explicitamente:

```powershell
uv run simon claim-validate --proposal-event-id evt_...
```

O comando não chama `set_current_claim()`, não cria Claim, não executa supersede/retract e não avança `world_revision`. Uma validação pode ser repetida posteriormente porque o Belief Store pode ter mudado desde a avaliação anterior.

### Deliberadamente fora do Passo 75

- aceitação de uma Proposed Claim `READY`;
- resolução de `CONFLICT`;
- escolha de vencedor por autoridade, recência ou confiança;
- schema validation específica por predicate;
- confidence score;
- alteração automática de Claim `ACTIVE`;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 75

1. Proposed Claim sem concorrente ativo resulta em `READY`;
2. Claim ativa equivalente resulta em `DUPLICATE`;
3. Claim ativa diferente resulta em `CONFLICT`;
4. conflito tem precedência quando equivalência e divergência coexistem;
5. a validação sobrevive a nova conexão com o banco;
6. nenhum outcome altera o Belief Store;
7. nenhum outcome avança `world_revision`;
8. a CLI expõe a validação sem aplicar efeito;
9. o schema SQLite permanece na versão 11.

## Passo 76 - READY -> Claim ACTIVE por confirmação humana

O primeiro caminho autorizado para materializar uma Proposed Claim no Belief Store é deliberadamente estreito:

```text
world.claim.proposed
↓
world.claim.validation.completed(outcome=READY)
↓
confirmação humana explícita
↓
world.claim.accepted
↓
Claim ACTIVE
↓
world_revision + 1
```

A aceitação deste passo só admite Proposed Claims originadas em `perception` com `epistemic_status=DIRECT_OBSERVATION`. `DUPLICATE` e `CONFLICT` não podem atravessar essa fronteira. Outros estados epistemológicos também permanecem fora do contrato até possuírem policy própria.

A autoridade é humana e fica explícita em `world.claim.accepted` com `source=user` e `authority=USER_CONFIRMATION`. Observer, Attention, World, Cognition e ModelProvider não recebem permissão para ativar Claims por conta própria.

A validação `READY` é tratada como snapshot, não como autorização eterna. A aceitação abre `BEGIN IMMEDIATE` e consulta novamente as Claims `ACTIVE` para o mesmo `subject + predicate` dentro da mesma transação que criará a nova Claim. Se qualquer Claim tiver surgido após a validação, a operação falha e exige novo `claim-validate`. Isso evita aceitar uma decisão obsoleta entre validação e escrita.

A aceitação não usa `set_current_claim()`. Portanto, o contrato é incapaz de executar supersede implícito. O eixo precisa continuar vazio no instante da confirmação.

A Claim aceita herda `subject`, `predicate`, `value` e `DIRECT_OBSERVATION` da Proposed Claim. Suas evidências incluem Observation, Attention assessment, validation e o Event de confirmação humana. A operação é atômica: `world.claim.accepted`, a linha em `claims` e o avanço de `world_revision` são persistidos na mesma transação.

A repetição da mesma aceitação é idempotente. A Claim e o Event já existentes são retornados sem nova linha e sem novo incremento de `world_revision`.

A CLI expõe somente essa borda restrita:

```powershell
uv run simon claim-accept-ready --validation-event-id evt_...
```

### Deliberadamente fora do Passo 76

- aceitação de `DUPLICATE`;
- resolução ou supersede de `CONFLICT`;
- autoridade automática por observer, sensor, domínio ou modelo;
- aceitação de `INFERRED`, `HYPOTHESIS`, `USER_REPORT` ou outros estados epistemológicos;
- confidence score;
- schema de domínio por predicate;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 76

1. somente validation `READY` pode ser confirmada;
2. somente Proposed Claim `DIRECT_OBSERVATION` originada em Perception atravessa o contrato;
3. a confirmação registra autoridade humana explícita;
4. o Belief Store é rechecado na mesma transação da escrita;
5. uma mudança ocorrida após `READY` bloqueia a aceitação;
6. nenhuma Claim existente é supersedida;
7. a Claim aceita preserva toda a cadeia de evidência;
8. a repetição é idempotente e não avança novamente `world_revision`;
9. o schema SQLite permanece na versão 11.

## Passo 77 - CONFLICT -> proposta explícita de resolução

Uma validation `CONFLICT` continua incapaz de alterar o Belief Store. O primeiro contrato de resolução registra somente **qual candidato o usuário escolhe como vencedor**, deixando a aplicação do supersede para uma etapa posterior e separada:

```text
world.claim.validation.completed(outcome=CONFLICT)
↓
USER_DECISION
↓
world.claim.conflict.resolution.proposed
↓
effect_applied=false
Belief Store inalterado
world_revision inalterada
```

O vencedor precisa ser uma referência já presente no conflito validado:

- o próprio Event `world.claim.proposed`, representando intenção de usar o valor da Proposed Claim; ou
- uma Claim `ACTIVE` cujo ID apareça em `active_claim_ids` da validation, representando intenção de mantê-la como vencedora.

Esse desenho também cobre Belief Stores já contraditórios. Se a validation contiver múltiplas Claims `ACTIVE`, o usuário escolhe uma Claim concreta em vez de uma política vaga como “manter as atuais”.

A escolha é persistida como:

```text
world.claim.conflict.resolution.proposed
```

com `source=user`, `authority=USER_DECISION`, `winner_kind`, `winner_id`, snapshot das Claims ativas, Claims equivalentes, Claims conflitantes, `status=PROPOSED` e `effect_applied=false`.

A validation `CONFLICT` é tratada como snapshot. Antes de registrar uma nova proposta de resolução, o sistema abre `BEGIN IMMEDIATE` e compara as Claims atualmente `ACTIVE` para o mesmo `subject + predicate` com `active_claim_ids` da validation. Se o conjunto mudou, a operação é recusada e exige novo `claim-validate`.

Uma validation pode possuir apenas uma escolha de resolução. Repetir a mesma escolha é idempotente. Tentar escolher outro vencedor usando a mesma validation é recusado; para mudar a decisão, é necessário produzir uma nova validation do estado atual.

A CLI expõe somente a proposta, não sua aplicação:

```powershell
uv run simon claim-conflict-propose `
    --validation-event-id evt_... `
    --winner-id evt_...
```

`winner-id` também pode ser o ID de uma Claim `ACTIVE` listada na validation.

### Deliberadamente fora do Passo 77

- executar `SUPERSEDED`;
- criar a Proposed Claim como `ACTIVE`;
- retirar ou expirar Claims perdedoras;
- escolher vencedor automaticamente por recência, observer, confiança ou modelo;
- policy de autoridade por domínio;
- confidence score;
- interpretação de conflito por LLM;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 77

1. somente validation `CONFLICT` alimenta o contrato;
2. o vencedor precisa ser a Proposed Claim ou uma Claim `ACTIVE` do snapshot validado;
3. a escolha é persistida com autoridade humana explícita;
4. o Belief Store é rechecado antes de registrar uma nova decisão;
5. validation obsoleta exige novo `claim-validate`;
6. repetir a mesma escolha é idempotente;
7. uma mesma validation não aceita escolhas concorrentes;
8. nenhuma Claim muda de status e `world_revision` permanece inalterada;
9. o schema SQLite permanece na versão 11.

## Passo 78 - aplicação atômica da resolução de CONFLICT

Uma `world.claim.conflict.resolution.proposed` passa a poder ser aplicada explicitamente depois da escolha humana registrada no Passo 77. A aplicação não escolhe vencedor e não interpreta evidências novamente: ela consome exatamente o `winner_kind` e o `winner_id` já autorizados.

```text
world.claim.validation.completed(outcome=CONFLICT)
↓
world.claim.conflict.resolution.proposed
↓
claim-conflict-apply
↓
world.claim.conflict.resolution.applied
```

A aplicação abre `BEGIN IMMEDIATE` e revalida novamente o snapshot antes de qualquer efeito. O conjunto atual de Claims `ACTIVE` para o mesmo `subject + predicate` precisa continuar exatamente igual a `expected_active_claim_ids` da resolução e ao snapshot da validation. Se o Belief Store mudou, a aplicação é recusada e exige novo `claim-validate` seguido de uma nova decisão humana.

Existem somente dois efeitos possíveis:

- `PROPOSED_CLAIM`: todas as Claims `ACTIVE` do snapshot são marcadas como `SUPERSEDED` e uma nova Claim `ACTIVE` é criada com o valor da Proposed Claim;
- `ACTIVE_CLAIM`: a Claim explicitamente escolhida permanece `ACTIVE` e somente as demais Claims `ACTIVE` do snapshot são marcadas como `SUPERSEDED`.

Quando a única Claim `ACTIVE` já é a vencedora, aplicar a resolução não modifica o Belief Store e não avança `world_revision`. O Event de aplicação ainda é persistido para registrar que o conflito foi resolvido sem mudança material do estado atual.

Quando há efeito no Belief Store, todas as mudanças de status, a eventual nova Claim, `world.claim.conflict.resolution.applied` e um único avanço de `world_revision` pertencem à mesma transação. Não há um incremento por Claim supersedida.

Se a Proposed Claim vencer, a nova Claim preserva Observation e Attention da proposta e adiciona validation, resolução humana e Event de aplicação à cadeia de evidências. Se uma Claim já `ACTIVE` vencer, sua evidência não é reescrita; a decisão de resolução permanece auditável pelos Events.

O Event `world.claim.conflict.resolution.applied` usa `source=world`, `authority=USER_DECISION` e `authority_event_id` apontando para a resolução humana. Assim, o subsistema World aplica o efeito, mas a autoridade continua rastreável até a decisão do usuário.

A operação é idempotente por `resolution_event_id`. Repetir a aplicação retorna o mesmo resultado sem novos supersedes, nova Claim ou novo incremento de `world_revision`.

A CLI expõe a borda explicitamente:

```powershell
uv run simon claim-conflict-apply --resolution-event-id evt_...
```

### Deliberadamente fora do Passo 78

- escolha automática do vencedor;
- policy por recência, confidence, observer ou domínio;
- interpretação de conflito por LLM;
- merge de valores concorrentes;
- reescrita de evidências da Claim `ACTIVE` mantida;
- resolução automática de `DUPLICATE`;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 78

1. somente `world.claim.conflict.resolution.proposed` com autoridade humana explícita pode ser aplicada;
2. o snapshot da validation e da resolução é rechecado dentro de `BEGIN IMMEDIATE`;
3. snapshot obsoleto bloqueia qualquer efeito;
4. Proposed Claim vencedora supersede o snapshot anterior e cria uma nova Claim `ACTIVE`;
5. Claim `ACTIVE` vencedora preserva a vencedora e supersede somente concorrentes;
6. manter a única Claim ativa não avança `world_revision`;
7. qualquer mudança material do Belief Store avança `world_revision` exatamente uma vez;
8. a aplicação é idempotente;
9. o schema SQLite permanece na versão 11.

## Passo 79 - DUPLICATE -> evidence binding na Claim existente

Uma validation `DUPLICATE` passa a preservar a nova evidência sem criar uma segunda Claim para o mesmo fato:

```text
world.claim.validation.completed(outcome=DUPLICATE)
↓
claim-bind-duplicate-evidence
↓
world.claim.evidence.bound
↓
Claim ACTIVE existente recebe novas evidence_event_ids
↓
valor/status/claim_id inalterados
world_revision inalterada
```

O contrato inicial continua restrito a Proposed Claims originadas em `perception` com `epistemic_status=DIRECT_OBSERVATION`. A validation precisa conter somente Claims equivalentes: `active_claim_ids` e `matching_claim_ids` devem representar o mesmo snapshot e `conflicting_claim_ids` precisa estar vazio.

Antes do binding, o sistema abre `BEGIN IMMEDIATE` e reconsulta o eixo `subject + predicate`. O conjunto atual de Claims `ACTIVE` precisa continuar exatamente igual ao snapshot validado, e todas precisam continuar equivalentes ao `value + epistemic_status` da Proposed Claim. Qualquer mudança exige novo `claim-validate`.

O Event `world.claim.evidence.bound` usa `source=world`, referencia validation, Proposed Claim e Claims vinculadas, registra `basis=DETERMINISTIC_EQUIVALENCE`, `claim_evidence_updated=true`, `current_world_view_changed=false` e `effect_applied=true`.

Cada Claim equivalente preserva suas evidências anteriores e recebe, sem duplicação, a Observation e o Attention assessment da Proposed Claim, a validation `DUPLICATE` e o próprio Event de binding. Não nasce nova Claim e nenhuma Claim muda de status.

Como `world_revision` representa alterações na visão corrente das Claims e não simples enriquecimento de provenance, o binding não avança a revisão. Isso evita invalidar Plans apenas porque uma crença já corrente recebeu evidência adicional.

A operação é idempotente por `validation_event_id`. Repetir o mesmo comando retorna o binding já persistido e não anexa novamente a mesma cadeia.

A CLI expõe a borda explicitamente:

```powershell
uv run simon claim-bind-duplicate-evidence --validation-event-id evt_...
```

### Deliberadamente fora do Passo 79

- confidence score derivado da quantidade de evidências;
- escolha de melhor observer;
- recência como autoridade;
- merge semântico de valores;
- alteração de `learned_at` da Claim original;
- aplicação de `ATTEND` ou `INTERRUPT`;
- Machine Learning.

### Critérios de conclusão do Passo 79

1. somente validation `DUPLICATE` alimenta o binding;
2. o snapshot é rechecado dentro de `BEGIN IMMEDIATE`;
3. snapshot obsoleto exige nova validation;
4. nenhuma Claim nova é criada;
5. Claims equivalentes preservam evidências anteriores e recebem a nova cadeia;
6. valor, estado epistemológico, status e `claim_id` permanecem inalterados;
7. `world_revision` não avança;
8. repetir o mesmo binding é idempotente;
9. o schema SQLite permanece na versão 11.


## Passo 80 - ATTEND -> item persistente para revisão do Executive

O destino `ATTEND` passa a possuir seu primeiro consumidor sem adquirir semântica de interrupção. Um `attention.assessed` com `destination=ATTEND` pode ser materializado explicitamente como:

```text
attention.item.opened
```

O item preserva o assessment, a Observation, resumo, razões, `trace_id`, Goal e Entities relacionados. O Event usa `source=attention`, `status=PENDING`, `effect_applied=true`, `focus_changed=false` e `goal_created=false`.

A materialização é explícita e separada da classificação:

```powershell
uv run simon attention-open --attention-event-id evt_...
```

`observe` continua somente registrando Observation + assessment. Assim, classificar como `ATTEND` não cria silenciosamente um compromisso executivo.

### Radar do Executive

Itens `PENDING` sobrevivem a restart e podem ser reconstruídos somente pelos Events persistidos. Quando não existe Goal aberto para conduzir, `decide_next()` deixa de responder `DONE/no_open_goal` se houver itens `ATTEND` materializados e retorna:

```text
NEEDS_ATTENTION_REVIEW
```

A decisão carrega `attention_candidates` em ordem de chegada, com item, assessment, Observation, resumo, razões e eventual Goal relacionado. A ordem é somente apresentação estável; não constitui ranking de importância nem escolha autônoma de trabalho.

`ATTEND` não preempta trabalho foreground. Se existir um Goal aberto, a condução normal desse Goal continua tendo precedência e o item permanece pendente. `INTERRUPT` continua sendo uma categoria separada e ainda sem efeito operacional.

### Foreground humano continua superior ao ATTEND ocioso

Quando o Executive está sem Goal e mostra `NEEDS_ATTENTION_REVIEW`, um novo turno humano explícito continua podendo propor um Goal. Da mesma forma, uma proposta conversacional de Goal já pendente continua podendo ser aceita ou rejeitada mesmo enquanto existe item de Attention pendente.

Essa regra não é um score de prioridade. Ela preserva uma fronteira já existente: solicitação e decisão humanas foreground não podem ser bloqueadas por uma pendência passiva de Attention.

### Idempotência e limites

Uma mesma `attention.assessed` pode abrir no máximo um item. Repetir `attention-open` recupera o Event existente. A operação não altera `world_revision`, não cria Claim, não cria Goal, não seleciona foco e não executa capability.

Neste passo ainda não existe operação para concluir, dispensar, adiar ou transformar o item em Goal. Portanto, um item aberto permanece `PENDING` até que o próximo contrato de revisão seja implementado.

### Deliberadamente fora do Passo 80

- revisão conversacional do item;
- `ACKNOWLEDGED`, `DISMISSED`, `DEFERRED` ou outro lifecycle terminal;
- criação automática de Goal a partir de Attention;
- troca automática de foco;
- preempção de Goal;
- aplicação de `INTERRUPT`;
- ranking numérico entre itens;
- FocusSession persistente;
- scheduler/background loop;
- Machine Learning.

### Critérios de conclusão do Passo 80

1. somente assessment `ATTEND` pode ser materializado;
2. o item sobrevive a nova conexão com o banco;
3. repetir a materialização é idempotente;
4. nenhum item altera `world_revision`, Goal ou foco;
5. sem Goal aberto, o Executive expõe `NEEDS_ATTENTION_REVIEW` com os candidatos persistidos;
6. um Goal foreground aberto não é preemptado por `ATTEND`;
7. um turno humano pode iniciar ou responder uma proposta de Goal mesmo com Attention pendente;
8. a CLI expõe `attention-open` sem executar trabalho do item;
9. o schema SQLite permanece na versão 11.
