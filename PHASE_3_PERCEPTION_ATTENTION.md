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
- Proposed Claims;
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
