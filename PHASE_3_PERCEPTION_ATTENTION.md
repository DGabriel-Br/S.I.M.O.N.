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

