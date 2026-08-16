# S.I.M.O.N. - Especificação Conceitual do Sistema

> **S.I.M.O.N.** - *Simples Inteligência, Mais Ou Menos Normal*
>
> Documento vivo de escopo, filosofia, arquitetura conceitual, regras de engenharia e evolução do projeto.

**Status:** especificação teórica consolidada para o v0.1  
**Fase atual:** implementação inicial do SIMON v0.1  
**Princípio central:** **SIMON ≠ modelo. Modelo ⊂ SIMON.**

---

## 1. Visão

S.I.M.O.N. é um sistema cognitivo pessoal, local-first, persistente e evolutivo. Seu objetivo não é ser apenas um LLM com ferramentas nem uma cópia offline de um chatbot, mas um sistema capaz de manter estado, perceber acontecimentos relevantes, formar e perseguir objetivos, planejar, agir por ferramentas controladas, verificar resultados, aprender com experiências e pesquisar melhorias sobre si mesmo em um laboratório isolado.

A identidade, a memória, o estado do mundo, as metas e o histórico do sistema pertencem ao SIMON, não ao modelo carregado em determinado momento. Modelos devem ser substituíveis sem que o sistema deixe de ser o SIMON.

### 1.1. Princípios de alto nível

- Local-first.
- Model-agnostic.
- Memory-before-fine-tuning.
- Measure-before-promote.
- Production lives, Lab evolves.
- O determinístico governa. O probabilístico aconselha.
- O modelo propõe; a infraestrutura decide o que é permitido executar.
- O sistema preserva proveniência e evidência sempre que possível.
- Autonomia é granular por capability e domínio, não um único nível global.
- SIMON pode escolher meios; objetivos importantes permanecem subordinados ao usuário e à Constituição.

---

## 2. Constituição de Engenharia

Estas regras orientam como o projeto deve ser construído.

### 2.1. Arquitetura sob demanda

Não criar arquitetura antes de existir necessidade concreta.

Fluxo preferencial:

```text
problema real
↓
solução simples
↓
limitação ou repetição observada
↓
abstração necessária
```

A arquitetura teórica define responsabilidades conceituais. Ela não obriga que cada conceito exista como módulo, classe, serviço ou processo separado desde o início.

### 2.2. Comentários explicam o porquê

O código deve explicar o que acontece. Comentários devem existir principalmente para registrar por que uma decisão não óbvia foi tomada.

Evitar comentários que apenas traduzem a linha de código imediatamente abaixo.

### 2.3. Erros guiados por evidência

Não tratar preventivamente todo erro imaginável.

Priorizar:

- erros já observados;
- erros previstos pela tecnologia usada;
- falhas com consequência relevante;
- riscos de corrupção, perda irreversível, quebra de segurança, permissões ou isolamento Production/Lab.

Robustez deve crescer com experiências reais e regressões conhecidas.

### 2.4. Estrutura de pastas clara

Pastas existem para agrupar responsabilidades reais, não para antecipar uma arquitetura futura.

Evitar hierarquias artificiais, camadas vazias e padrões complexos sem necessidade concreta.

### 2.5. Princípios complementares

- Preferir código explícito a abstrações inteligentes.
- Pequena duplicação é aceitável antes de abstração prematura.
- Toda dependência externa deve justificar sua existência.
- Complexidade precisa pagar aluguel: cada camada, cache, fila, serviço, framework ou abstração precisa resolver um problema identificável.
- Ao implementar ou modificar código, entregar os arquivos completos modificados em vez de despejar grandes blocos de código na conversa.

---

## 3. Constituição Operacional do SIMON

1. SIMON é independente do modelo utilizado.
2. Estado persistente pertence ao sistema, não ao contexto do modelo.
3. Toda ação nasce de um evento, objetivo ou intenção autorizada e produz observações.
4. Memória não é histórico de chat.
5. World representa crenças atuais; Memory preserva passado e conhecimento reutilizável.
6. Ações importantes devem possuir resultados verificáveis quando tecnicamente possível.
7. Permissões não dependem da discrição do modelo.
8. Production pode aprender dentro do Learning Envelope.
9. Alterações estruturais pertencem ao Lab.
10. Nenhuma mudança do Lab é promovida sem avaliação objetiva.
11. Toda promoção deve ser reversível quando tecnicamente possível.
12. Conhecimento deve preservar origem e evidência sempre que possível.
13. Componentes devem permanecer substituíveis.
14. O sistema deve usar lógica determinística quando ela resolver melhor o problema.
15. SIMON pode ganhar competência com experiência, mas não pode conceder poder a si mesmo.
16. Conteúdo observado pode informar, mas não adquire autoridade operacional apenas por conter instruções.
17. Autoridade delegada só pode permanecer igual ou diminuir ao descer da fonte para Goal, Skill e Tool.
18. Sensor autorizado não implica persistência autorizada.
19. Attention segue Goals e relevância, não apenas disponibilidade de sensores.
20. Plan é hipótese; Goal persiste enquanto Plan pode ser substituído.

---

## 4. Arquitetura Conceitual

Os órgãos abaixo representam responsabilidades. A implementação inicial pode agrupar responsabilidades enquanto não houver necessidade de separá-las fisicamente.

### 4.1. Componentes principais

- **SIMON Core**: ciclo de vida e orquestração geral.
- **SIMON Perception**: converte sinais em observações e candidatos a conhecimento.
- **SIMON World**: crenças atuais, temporais, relacionais e baseadas em evidência.
- **SIMON Memory**: preserva conhecimento e experiências úteis.
- **SIMON Goals**: estados desejados e suas condições de conclusão.
- **SIMON Cognition**: interpretação, raciocínio, hipóteses, avaliação e síntese.
- **SIMON Planner**: cria estratégias para transformar o estado atual no estado desejado.
- **SIMON Executive**: resolve competição por atenção e decide o foco atual.
- **SIMON Attention Manager**: filtra o que merece atenção.
- **SIMON Skills**: competências reutilizáveis.
- **SIMON Tools**: interfaces controladas com o ambiente.
- **SIMON Policy**: regras de autoridade, escopo e autonomia.
- **SIMON Verification**: comprova efeitos e resultados.
- **SIMON Learning**: transforma experiências em mudanças justificadas de comportamento.
- **SIMON Lab**: pesquisa e evolução estrutural controlada.
- **SIMON Observatory**: logs, traces, métricas, artefatos, snapshots e sinais de pesquisa.

### 4.2. Componentes transversais já identificados

- Context Builder
- Model Router
- Capability Registry
- Skill Registry
- Resource Manager
- Agenda
- Working Set
- FocusSession
- CognitiveSession
- Experience Dataset
- Production Archive
- Lab Inbox

Nenhum deles precisa necessariamente nascer como serviço separado.

---

## 5. Life Loop

```text
WORLD
↓
PERCEIVE
↓
ATTEND
↓
THINK
↓
PLAN
↓
ACT
↓
VERIFY
↓
EXPERIENCE
↓
LEARN
↓
BEHAVE BETTER
```

Esse é o ciclo operacional do SIMON em Production.

---

## 6. Evolution Loop

```text
PRODUCTION
↓
OBSERVE PERFORMANCE
↓
PRODUCTION ARCHIVE
↓
LAB INBOX
↓
USER AUTHORIZATION
↓
RESEARCH
↓
EXPERIMENT
↓
VERIFY
↓
COMPARE
↓
PROMOTION GATE
↓
BETTER PRODUCTION
```

Pesquisa e promoção são autorizações separadas.

---

## 7. SIMON World

### 7.1. Definição

> **SIMON World é um modelo temporal, relacional e baseado em evidências que representa as crenças atuais do sistema sobre entidades relevantes, suas propriedades, relações e estados.**

SIMON não assume acesso direto à verdade absoluta. Ele mantém claims justificadas por evidência.

### 7.2. Primitivas conceituais

- Entity
- Property
- Relation
- Claim
- Event

### 7.3. Entidades e identidade

Entidades devem possuir identificadores persistentes e aliases. Entity Resolution associa referências humanas ou técnicas à mesma entidade quando justificável.

### 7.4. Temporalidade

Dois tempos são relevantes:

- **Valid Time**: quando o fato era verdadeiro no mundo.
- **Knowledge Time**: quando SIMON tomou conhecimento do fato.

### 7.5. Três camadas

1. **Event Log**: o que aconteceu.
2. **Belief Store**: o que SIMON acredita com base em evidência.
3. **World State**: melhor visão materializada do estado atual.

### 7.6. Contradições

Contradições são de primeira classe. Não devem ser silenciosamente sobrescritas.

A autoridade depende do domínio. Exemplo: o sistema operacional é fonte mais forte para estado de processo do que uma inferência do LLM.

### 7.7. Estados epistemológicos iniciais

Evitar probabilidades falsas como `0.873` sem calibração real. Preferir classes como:

- DIRECT_OBSERVATION
- AUTHORITATIVE_REPORT
- USER_REPORT
- DERIVED
- INFERRED
- HYPOTHESIS
- UNKNOWN

### 7.8. Frescor

Claims possuem validade/freshness conforme o domínio. Estado de processo pode expirar em segundos; uma decisão arquitetural pode ser persistente.

### 7.9. Active World

Nem tudo do World entra em Cognition.

```text
Observed World
↓
Known World
↓
Active World
```

Active World é o recorte relevante ao Goal e à sessão atual.

### 7.10. Escrita no World

LLMs não escrevem diretamente no World. Produzem Proposed Claims, que passam por evidência, schema, entidade, temporalidade, conflito e policy antes de se tornarem beliefs aceitas.

---

## 8. Perception

### 8.1. Pipeline

```text
REALITY
→ SOURCE / SENSOR
→ RAW EVENT
→ NORMALIZATION
→ ENTITY RESOLUTION
→ INTERPRETATION
→ PROPOSED CLAIMS
→ EVIDENCE BINDING
→ VALIDATION
→ CONFLICT RESOLUTION
→ BELIEF STORE
→ WORLD MATERIALIZATION
```

### 8.2. Tipos de entrada

- Observation
- Declaration
- Deterministic Derivation
- Model Inference
- Prediction

Prediction mantém alvo, tempo esperado e base para avaliação posterior.

### 8.3. Estratégia de observação

Não observar tudo continuamente.

#### Basal Perception

Baixo custo, contínua para:

- saúde do SIMON;
- Goals ativos;
- Jobs e Tools pendentes;
- falhas relevantes;
- recursos críticos;
- timers/subscriptions;
- comunicação direta do usuário.

#### Contextual Perception

Aumenta observação em projetos, arquivos, processos e recursos ligados aos Goals atuais.

#### Deep Perception

Ativada sob demanda para visão, OCR, áudio, câmera, scans extensos e análises pesadas.

### 8.4. Event-driven first

Preferir eventos e deltas a polling repetitivo quando possível.

### 8.5. Observation Subscription

Associa observer, target, eventos/condições, motivo/Goal e expiração.

### 8.6. Privacy

Mic/câmera default off, tela e conteúdo profundo ligados a Goal/escopo, clipboard restrito, e persistência separada de observação.

---

## 9. Attention e Executive

### 9.1. Attention Manager

Pergunta:

> Isto merece atenção?

Destinos possíveis:

- IGNORE
- RECORD
- UPDATE_WORLD
- ATTEND
- INTERRUPT

Sinais considerados:

- relevância ao Goal;
- urgência;
- risco;
- raridade;
- uncertainty;
- impacto;
- custo de observação;
- subscriptions.

### 9.2. SIMON Executive

Pergunta:

> Entre tudo que merece atenção, no que devo trabalhar agora?

### 9.3. Actionability

- READY
- WAITING
- BLOCKED
- RUNNING
- PAUSED
- DEFERRED
- DONE
- FAILED

Importância e actionability são separadas.

### 9.4. Executive Classes

- E0 Critical
- E1 User Foreground
- E2 Committed
- E3 Goal Progress
- E4 Maintenance
- E5 Research

Lab cede recursos à Production e ao usuário.

### 9.5. FocusSession

Pode conter:

- focus goal;
- motivo;
- working set;
- interruptibility;
- resource budget;
- current step;
- checkpoint.

### 9.6. Attention inertia

Pequenas mudanças de prioridade não devem causar thrashing constante.

---

## 10. Goals

### 10.1. Definição

> **Goal é um estado de mundo desejado que SIMON pretende tornar verdadeiro.**

Conceitualmente:

```text
Goal = Desired State - Current State
```

### 10.2. Hierarquia

```text
MISSION
↓
GOAL
↓
SUBGOAL
↓
TASK
↓
ACTION
```

Plan não é nível da hierarquia. É uma estratégia para atingir um Goal.

### 10.3. Propriedades importantes

- origin
- authority
- parent goal
- desired state
- success conditions
- constraints
- anti-goals
- dependencies
- deadline
- resource budget
- escalation policy
- progress evidence
- history

### 10.4. Origem

- USER
- SYSTEM
- DERIVED
- MAINTENANCE
- LAB

### 10.5. Estados

- PROPOSED
- ACTIVE
- WAITING
- BLOCKED
- PAUSED
- COMPLETED
- FAILED
- CANCELLED
- SUPERSEDED

### 10.6. Goal Drift

Subgoals derivados devem justificar contribuição real, necessária e proporcional ao parent Goal.

### 10.7. Fim versus meio

SIMON pode criar meios instrumentais para objetivos autorizados, mas não inventar grandes fins próprios.

---

## 11. Planner

### 11.1. Definição

> **Plan é uma hipótese sobre como transformar o World atual no estado desejado.**

### 11.2. Dois tipos de ação

- **Epistemic Actions**: obtêm informação.
- **World Actions**: modificam o mundo.

### 11.3. Plan Graph

Plan pode conter dependências, branches, paralelismo, fallback, unknown nodes e cancelamentos.

### 11.4. Receding Horizon

```text
PLAN
→ EXECUTE
→ OBSERVE
→ UPDATE WORLD
→ REPLAN
```

Detalhar muito apenas o curto prazo; manter horizontes mais distantes abstratos.

### 11.5. Revalidação

Plan registra World version. Antes de ações importantes, preconditions e assumptions são revalidadas.

### 11.6. Assumption Register

Assumptions explícitas permitem invalidar apenas partes dependentes do Plan.

### 11.7. Retry ≠ Replan

Falhas podem ser classificadas como:

- TRANSIENT
- RETRIABLE
- PLAN_INVALID
- WORLD_CHANGED
- RESOURCE_FAILURE
- PERMISSION_FAILURE
- UNKNOWN

Retries possuem budget e backoff.

### 11.8. Reversibilidade

Preferir caminhos reversíveis sob incerteza.

---

## 12. Cognition

### 12.1. Definição

> **Cognition é um serviço do SIMON que usa modelos, regras, memória, contexto e ferramentas para produzir resultados cognitivos estruturados.**

### 12.2. CognitiveJob

Cada invocação relevante possui tarefa explícita, como:

- interpret_event
- generate_hypotheses
- compare_plans
- evaluate_result
- synthesize
- communicate

### 12.3. Deterministic-first

Usar relógio, filesystem, graphs, cálculo, validação e lógica determinística diretamente quando apropriado. Modelos entram para ambiguidade, interpretação, hipóteses e estratégia incerta.

### 12.4. Funções cognitivas

- Interpretation
- Reasoning
- Hypothesis Generation
- Planning
- Evaluation
- Synthesis
- Communication

Communication deve permanecer separada de reasoning interno estruturado.

### 12.5. Context Builder

Monta contexto específico por CognitiveJob usando apenas informações relevantes:

- Identity
- Current Event
- Active Goal
- World slice
- relevant Memories
- Plan
- Open Questions
- constraints
- Skills/Tools relevantes
- Policy summary
- output schema

### 12.6. Model Router

Resolve capability requirements considerando:

- complexidade;
- confiabilidade;
- latência;
- VRAM/RAM;
- especialização;
- histórico de desempenho.

### 12.7. Outputs

Cognition produz propostas, não autoridade:

- Proposed Claim
- Proposed Plan
- Proposed Action
- Proposed Goal
- Hypothesis
- Evaluation
- Interpretation

### 12.8. Unknown é válido

`INSUFFICIENT_INFORMATION` é um resultado válido. O sistema não deve preencher lacunas inventando certeza.

### 12.9. Adaptive deliberation

- C0: sem modelo
- C1: classificação/intepretação rápida
- C2: raciocínio normal
- C3: deliberativo
- C4: research mode

### 12.10. Disagreement

Quando explicações plausíveis competem, buscar evidência discriminante em vez de simples votação entre modelos.

---

## 13. Memory

### 13.1. Princípio

> **SIMON não tenta lembrar tudo. Ele tenta lembrar aquilo cujo esquecimento tornaria seu futuro pior.**

Memória preserva significado útil; Event Log preserva detalhe histórico.

### 13.2. Tipos

- Working Memory
- Episodic Memory
- Semantic Memory
- Procedural Memory
- Prospective Memory
- Meta Memory

### 13.3. Negative Knowledge

Falhas e estratégias rejeitadas também são conhecimento, especialmente quando ligadas às condições em que foram testadas.

### 13.4. Write Path

```text
Experience
↓
Significance Filter
↓
Memory Candidate
↓
Classification
↓
Deduplication
↓
Consistency Check
↓
Consolidation
↓
Memory Store
```

### 13.5. Significance

Possíveis sinais:

- novidade;
- utilidade futura;
- relevância ao Goal;
- importância ao usuário;
- impacto de decisão;
- surpresa;
- valor de falha;
- reutilização;
- frequência;
- custo de redescoberta.

### 13.6. Consolidation

Experiências e memórias repetidas podem gerar conhecimento semanticamente consolidado sem apagar as evidências originais.

### 13.7. Forgetting

Distinguir:

- cognitive forgetting;
- archival;
- expiration;
- retraction;
- deletion.

Esquecer normalmente significa reduzir acessibilidade, não destruir história.

### 13.8. Retrieval

Retrieval não deve ser apenas vector top-k.

Pode combinar:

- semântica;
- entity linkage;
- Goal;
- project;
- recency;
- importance;
- memory type;
- temporal relevance;
- causal relevance;
- historical usefulness.

### 13.9. Hybrid retrieval

Possíveis índices:

- relational/graph;
- temporal;
- full-text;
- embeddings;
- metadata filters.

Embeddings são ferramenta de retrieval, não a memória em si.

### 13.10. Context budget

O Retriever seleciona a melhor combinação de memórias dentro do budget, controlando redundância.

### 13.11. Scope/Namespace

Memórias podem possuir escopos como:

- GLOBAL
- PROJECT
- WORKSPACE
- SESSION
- PRIVATE
- SYSTEM
- LAB

### 13.12. Production versus Lab memory

Conhecimento experimental permanece marcado como LAB/EXPERIMENTAL até promoção.

---

## 14. Experience

### 14.1. Definição

> **Experience é uma unidade temporal de interação em que SIMON parte de um contexto, persegue uma intenção, toma decisões ou executa ações, observa consequências e termina com resultado ou aprendizado potencial.**

Event é um ponto. Experience é uma história causal.

### 14.2. Hierarquia

Experiences podem ser nested, permitindo olhar uma investigação inteira ou um único experimento específico.

### 14.3. Fronteira

Uma Experience nasce quando algo começa a ser perseguido, investigado ou resolvido.

Pode terminar como:

- SUCCESS
- FAILURE
- PARTIAL
- BLOCKED
- ABANDONED
- SUPERSEDED
- INTERRUPTED
- INCONCLUSIVE

### 14.4. Estrutura conceitual

Uma Experience pode referenciar:

- trigger;
- Goal;
- World before;
- relevant context;
- hypothesis;
- prediction;
- decisions;
- actions;
- observations;
- artifacts;
- outcome;
- World after;
- new questions;
- verification.

### 14.5. Deltas

- World Delta
- Knowledge Delta
- Capability Delta

### 14.6. Expectation e Surprise

Registrar expectativa quando possível permite medir diferenças entre previsto e observado.

### 14.7. Information Gain

Uma Experience pode falhar operacionalmente e ainda produzir grande ganho de informação.

### 14.8. Lifecycle

Conceitualmente:

- CREATED
- ACTIVE
- SUSPENDED
- CLOSING
- CLOSED
- EVALUATED
- CONSOLIDATED

---

## 15. Learning

### 15.1. Definição

> **SIMON aprendeu algo quando uma experiência passada modifica de maneira justificável seu comportamento, previsão, interpretação ou escolha futura.**

Memória sem mudança futura é lembrança, não aprendizado operacional.

### 15.2. Behavioral Delta

O aprendizado deve produzir alguma diferença identificável no comportamento futuro sob condições relevantes.

### 15.3. Níveis conceituais

- L0 Observation
- L1 Knowledge
- L2 Adaptation
- L3 Procedure
- L4 Strategy
- L5 Architecture/Parameters

L5 pertence ao Lab.

### 15.4. Learning Envelope

Production pode modificar apenas categorias previamente autorizadas, como:

- memories;
- aliases;
- preference evidence;
- procedure candidates;
- bounded strategy/routing statistics.

Production não modifica:

- Constitution;
- permission system;
- core code;
- benchmark definitions;
- autonomy limits;
- model weights;
- promotion mechanism.

### 15.5. Learning Candidate

Experiências geram candidatos de aprendizagem antes de alterar comportamento.

### 15.6. Escada de generalização

```text
INSTANCE
↓
CONTEXT
↓
TASK CLASS
↓
PROJECT
↓
DOMAIN
↓
GLOBAL
```

Aprendizados nascem no menor escopo justificável e sobem apenas com evidência.

### 15.7. Fast versus Slow Learning

Fast Learning pode ocorrer após correção explícita, alias ou instrução forte.

Slow Learning exige múltiplas experiências para preferências, routing, planner e estratégias.

### 15.8. Concept Drift

Learned Behaviors possuem ambiente e last_validation. Mudanças relevantes podem exigir revalidação.

### 15.9. Exploration versus Exploitation

Production explora pouco e de modo seguro. Lab é o ambiente principal para explorar alternativas.

---

## 16. Skills

### 16.1. Definição

> **Skill é uma capacidade operacional reutilizável, com condições de uso, entradas, efeitos esperados, permissões, verificação e histórico de desempenho conhecidos.**

### 16.2. Tool versus Skill

Tool oferece operação. Skill sabe alcançar um resultado usando uma ou mais capabilities.

### 16.3. Procedure versus Skill

Procedure é conhecimento procedural. Skill é essa competência tornada invocável e operacional.

### 16.4. Skill Contract

Pode declarar:

- Inputs
- Preconditions
- Outputs
- Expected Effects
- Side Effects
- Failure Modes
- Permissions
- Verification
- Resource Requirements

### 16.5. Tipos

- Atomic Skill
- Composite Skill
- Deterministic Skill
- Cognitive Skill
- Hybrid Skill

### 16.6. Capability-first

Planner deve pensar em capabilities. Skill Resolver decide implementação concreta.

### 16.7. Skill Registry

Mantém versions, applicability, dependencies, permissions, resources, health e performance contextual.

### 16.8. Lifecycle

- PROPOSED
- EXPERIMENTAL
- VALIDATED
- ACTIVE
- DEPRECATED
- STALE
- RETIRED
- REJECTED

### 16.9. Skill synthesis

Production pode detectar procedimento/automação potencial. Implementações estruturais novas passam pelo Lab antes de promoção.

### 16.10. Princípio

> Skill é cognição compilada em competência reutilizável quando um padrão se torna confiável, repetível e verificável.

---

## 17. Tools e Tool Gateway

### 17.1. Definição

> **Tool é uma interface controlada que permite observar ou modificar uma parte específica do ambiente externo por operações previamente definidas.**

### 17.2. Mediação obrigatória

Nenhum modelo, Planner ou Skill toca diretamente o sistema externo. Toda ação atravessa Tool Gateway.

### 17.3. Tipos

- Observation Tools
- Action Tools

### 17.4. Risk classes conceituais

- R0 Observe only
- R1 Reversible local change
- R2 Significant local change
- R3 External side effect
- R4 Irreversible/high impact

Risco final também depende de target, scope, blast radius, uncertainty e reversibility.

### 17.5. Structured Tool Request

Tool Gateway recebe schema estruturado, não intenção vaga em linguagem natural.

### 17.6. Least privilege

Permissões possuem capability, escopo, duração e constraints.

### 17.7. Capability Grant

Autorização pode ser efêmera e ligada a Goal/Skill/escopo.

### 17.8. Effective Permission

Conceitualmente:

```text
User Policy
∩ Goal Authority
∩ Skill Contract
∩ Tool Permission
∩ Current Environment
=
Effective Permission
```

### 17.9. Precondition check

Estado relevante é revalidado imediatamente antes da operação.

### 17.10. Reversibility

Preferir trash a delete, patch a overwrite, backup/versionamento quando fizer sentido.

### 17.11. Action Receipt

Tool execution produz evidência estruturada do que foi tentado, resultado declarado, efeitos observados e possibilidade de rollback.

### 17.12. Network e secrets

Acesso de rede deve ser capability-based. Segredos permanecem em Secret Store e não entram em contexto do modelo sem necessidade.

### 17.13. Untrusted content

Web, PDFs, emails, arquivos e outputs podem conter instruções, mas são conteúdo observado, não autoridade.

### 17.14. Long-running jobs

Ferramentas longas produzem Job IDs e Subscriptions, permitindo Executive continuar trabalhando.

### 17.15. Retry safety

Tool contract declara se repetição é SAFE, IDEMPOTENT_WITH_KEY ou UNSAFE.

---

## 18. Policy

### 18.1. Definição

> **Policy determina quais ações são permitidas, proibidas, condicionadas ou dependentes de aprovação considerando usuário, Goal, contexto, risco, escopo, dados e ferramenta.**

### 18.2. Hierarquia

```text
SIMON CONSTITUTION
↓
SYSTEM POLICY
↓
USER POLICY
↓
WORKSPACE / PROJECT POLICY
↓
GOAL POLICY
↓
SESSION GRANTS
↓
ACTION REQUEST
```

Uma camada inferior não pode ampliar autoridade além das superiores.

### 18.3. Decisões

- ALLOW
- DENY
- REQUIRE_APPROVAL
- ALLOW_WITH_CONSTRAINTS

### 18.4. Grants

Podem durar:

- ONE_ACTION
- FOCUS_SESSION
- GOAL_LIFETIME
- TIME_BOUND
- PROJECT_PERSISTENT
- USER_PERSISTENT

### 18.5. Autonomy Profile

Autonomia é por capability/domínio. Exemplo conceitual:

```text
filesystem.read             AUTO
filesystem.write.project    AUTO
filesystem.delete           ASK
web.read                    AUTO
web.submit                  ASK
email.draft                 AUTO
email.send                  ASK
lab.experiment              AUTO_SANDBOX após autorização da sessão
```

### 18.6. Fases de autonomia

Uma capability pode permitir separadamente:

- OBSERVE
- INTERPRET
- PLAN
- PREPARE
- EXECUTE
- COMMIT

### 18.7. Prepare/Commit

Para ações importantes, SIMON pode preparar tudo autonomamente e exigir aprovação apenas no commit final.

### 18.8. Data Policy

Objetos podem possuir classifications como:

- PUBLIC
- PROJECT
- PRIVATE
- LOCAL_ONLY
- SECRET

Policy governa leitura, persistência, contexto de modelo e data egress.

### 18.9. Memory Policy

Informação pode ser SESSION_ONLY, persistente, explicitamente não memorável ou sujeita a retenção limitada.

### 18.10. Policy learning

Preferência observada não é autorização. SIMON pode sugerir grants, mas não ampliar sozinho a própria autonomia.

---

## 19. Verification

### 19.1. Definição

> **Verification compara efeitos esperados de uma ação, Skill, Plan ou Goal com evidências do estado real do mundo.**

### 19.2. Conceitos

- Claimed Result
- Observed Result
- Verified Result

### 19.3. Verification Plan

Sempre que possível, antes de agir o sistema deve saber:

- o que deve mudar;
- o que deve permanecer verdadeiro;
- o que não pode acontecer;
- como o resultado será verificado.

### 19.4. Proof obligations

Ações importantes geram critérios explícitos de prova.

### 19.5. Tipos

- Structural Verification
- Semantic Verification
- Behavioral Verification
- Integrity Verification
- Constraint Verification
- Regression Verification

### 19.6. Estados

- VERIFIED
- PARTIAL
- FAILED
- INCONCLUSIVE
- ASSESSED
- UNVERIFIED

ASSESSED representa julgamento cognitivo sem prova externa suficiente.

### 19.7. Invariants

Uma ação não é bem-sucedida se atingir o efeito principal violando invariants que deveriam permanecer verdadeiros.

### 19.8. Verification Debt

Quando alguma prova não pode ser feita imediatamente, registrar dívida verificável e, quando relevante, uma Prospective Memory/Subscription.

### 19.9. Learning

Learning distingue verified success, reported success e assessed success para não aprender com falsos positivos.

---

## 20. Observatory

### 20.1. Definição

> **SIMON Observatory torna o funcionamento interno observável, mensurável e reconstruível sem adquirir autoridade sobre os componentes observados.**

### 20.2. Cinco dimensões

- Logs
- Traces
- Metrics
- Artifacts
- Snapshots

### 20.3. Traces

Operações relacionadas carregam identificadores causais e temporais, como:

- trace_id
- parent_id
- goal_id
- experience_id
- session_id

### 20.4. Categorias de métricas

- System
- Models
- Memory
- Planning
- Tools
- Skills
- Goals
- Policy
- Verification
- User interaction signals relevantes

### 20.5. Artifacts

Outputs, diffs, reports, diagnostics e outros resultados grandes permanecem referenciados por hash/localização e relação causal.

### 20.6. System Snapshot

Registra composição relevante do sistema:

- component versions;
- models;
- skills;
- policies;
- config;
- hardware;
- environment.

Experiences importantes apontam para o snapshot que as produziu.

### 20.7. Telemetry levels

- T0 MINIMAL
- T1 NORMAL
- T2 DETAILED
- T3 DIAGNOSTIC
- T4 RESEARCH

A profundidade pode aumentar apenas no escopo investigado.

### 20.8. Production Archive

Observatory alimenta continuamente um arquivo histórico de Production.

### 20.9. Research Signals

Sinais simples podem ser detectados sem iniciar pesquisa, como:

- repeated failures;
- resource inefficiency;
- automation opportunities;
- anomalies;
- capability gaps;
- repeated user corrections.

### 20.10. Structured failures

Falhas devem possuir classificação comum suficiente para correlação e pesquisa.

Categorias iniciais possíveis:

- INPUT_FAILURE
- PRECONDITION_FAILURE
- POLICY_FAILURE
- RESOURCE_FAILURE
- TOOL_FAILURE
- MODEL_FAILURE
- VERIFICATION_FAILURE
- PLAN_FAILURE
- WORLD_CONFLICT
- TIMEOUT
- DEPENDENCY_FAILURE
- UNKNOWN

### 20.11. Incident

Múltiplos failures correlacionados podem formar um Incident e então disputar atenção no Executive.

### 20.12. Observability overhead

Instrumentação tem custo medido e deve permanecer proporcional ao valor operacional/científico.

### 20.13. Context provenance

Observatory registra entradas estruturais, modelos, memórias recuperadas, World slices, Tools/Skills disponíveis e resultados. Não depende de capturar reasoning privado interno do modelo.

---

## 21. SIMON Lab

### 21.1. Definição

> **SIMON Lab é um ambiente científico isolado onde hipóteses sobre o próprio sistema são formuladas, implementadas, testadas e comparadas antes que qualquer mudança possa chegar à Production.**

### 21.2. Princípio

```text
Production lives.
Lab evolves.
```

### 21.3. Lab Intake automático, Lab Research autorizado

Production alimenta continuamente:

```text
Production Archive
↓
Lab Inbox
↓
PENDING AUTHORIZATION
```

O Lab não inicia pesquisa sozinho.

### 21.4. Autorização explícita

Uma sessão de pesquisa só começa após autorização explícita do usuário.

Autorizar pesquisa não autoriza promoção.

### 21.5. Snapshot congelado

Ao autorizar, a entrada é congelada em um snapshot. Novos dados de Production ficam para a próxima Lab Inbox, garantindo reprodutibilidade.

### 21.6. Estados conceituais

- DISABLED
- IDLE
- PENDING_AUTHORIZATION
- AUTHORIZED
- RUNNING
- PAUSED
- COMPLETED

### 21.7. Lab Briefing

Antes de autorização, Production pode apresentar sinais e backlog de modo barato, sem iniciar experimentos.

### 21.8. Research Signal → Research Opportunity

O Lab transforma evidência de Production em problemas mensuráveis, perguntas e hipóteses.

### 21.9. Research Question

Deve ser testável e ligada a baseline, métricas, guardrails e dataset apropriado.

### 21.10. Prediction before experiment

Registrar previsão antes do run para reduzir narrativa pós hoc.

### 21.11. Experiment Spec

Pode conter:

- question;
- hypothesis;
- baseline;
- candidate;
- controlled variables;
- primary metric;
- guardrails;
- resource budget;
- seed policy;
- mutation surface.

### 21.12. Researcher ≠ Evaluator

O componente que cria uma candidata não controla livremente benchmark, expected results, guardrails, hidden cases ou promotion mechanism.

### 21.13. Mutation Surface

Cada experimento define explicitamente o que pode ser modificado e o que permanece protegido.

### 21.14. Evaluation layers

- Unit Bench
- Capability Bench
- System Bench
- Regression Bench
- Production Replay
- Shadow/Canary quando apropriado

### 21.15. Baseline

Toda alegação de melhoria é comparada com uma baseline versionada e reproduzível sob condições equivalentes.

### 21.16. Multi-objective

Pesquisa pode melhorar accuracy, latency, VRAM, RAM, context, robustness, simplicity, energy ou outros objetivos.

Guardrails não são recompensas compensáveis. Violação crítica invalida a candidata.

### 21.17. Research Memory

Armazena perguntas, hipóteses, experimentos, candidatos, resultados positivos/negativos, regressions e promotion history.

Resultados negativos são conhecimento.

### 21.18. Research Budget

Toda sessão e experimento possuem budgets de tempo, compute, GPU, disk e runs.

### 21.19. Production priority

Lab cede recursos quando Production ou usuário precisam deles.

### 21.20. Promotion classes

Conceitualmente:

- P0 low-risk configuration
- P1 operational behavior
- P2 Skill/algorithm
- P3 core architecture
- P4 governance

Governance components não recebem auto-promotion.

### 21.21. Promotion Package

Deve incluir candidata, baseline, diff, metrics, regressions, guardrails, resource delta, limitations e rollback plan.

### 21.22. Candidate integrity

Somente o artefato exato que foi avaliado pode ser promovido. Hash/version mismatch invalida a avaliação.

### 21.23. Rollback

Toda promoção elegível deve preservar previous stable quando tecnicamente possível e possuir monitoramento pós-promoção.

### 21.24. Fine-tuning

Treinamento de pesos é uma opção tardia, avaliada apenas depois de investigar contexto, memória, prompt, routing, deterministic logic e Skills.

---

## 22. Relações Conceituais Principais

```text
User / System Event
        ↓
    Perception
        ↓
       World
        ↓
Attention / Executive
        ↓
       Goal
        ↓
      Planner
        ↓
   Cognitive Jobs
        ↓
Capability / Skill
        ↓
   Tool Gateway
        ↓
      World
        ↓
   Verification
        ↓
    Experience
      ↙     ↘
   Memory   Learning
              ↓
         Future Behavior
```

O Observatory acompanha o fluxo inteiro sem adquirir autoridade operacional.

O Lab recebe dados históricos de Production apenas através do Production Archive/Lab Inbox e só pesquisa após autorização explícita.

---

## 23. Canonical Data Model mínimo do v0.1

### 23.1. Princípio

O modelo de dados inicial não deve materializar toda a arquitetura conceitual como classes ou tabelas. Um objeto persistente só nasce no v0.1 quando possui identidade própria, lifecycle próprio ou precisa ser referenciado por outras partes do sistema.

Conceitos que podem ser derivados, calculados ou mantidos como metadata permanecem assim até existir necessidade concreta de separá-los.

### 23.2. Objetos persistentes mínimos

O v0.1 começa com nove objetos canônicos:

```text
Entity
Event
Claim
Goal
Plan
Action
VerificationResult
Experience
Memory
```

Esses nove objetos são suficientes para sustentar identidade persistente, histórico, World, objetivos, planejamento básico, ação controlada, verificação, experiência, memória e retomada após reinício.

### 23.3. Regras comuns de identidade

Todo objeto canônico possui, no mínimo:

- `id`: identidade persistente e única;
- `created_at`: quando foi criado pelo SIMON;
- referências explícitas aos objetos relacionados quando necessárias.

`trace_id`, `goal_id`, `experience_id` e outros identificadores de correlação são adicionados somente nos objetos em que realmente ajudam a reconstruir causalidade.

Nenhum objeto recebe campos genéricos apenas por uniformidade estética.

### 23.4. Entity

Representa algo que precisa manter identidade estável ao longo do tempo.

Exemplos:

- um projeto;
- um arquivo relevante;
- um problema conhecido;
- o próprio SIMON;
- uma pessoa ou sistema quando isso for necessário ao Goal.

Campos mínimos:

```text
id
kind
name
aliases
created_at
```

`kind` começa simples. Não será criada uma hierarquia extensa de tipos antes de aparecer necessidade real.

Aliases existem porque o mesmo objeto pode ser referido de formas diferentes sem deixar de ser a mesma Entity.

### 23.5. Event

Registro append-only de algo que aconteceu e que merece permanecer reconstruível.

Exemplos:

- mensagem do usuário;
- Tool iniciada ou concluída;
- processo terminou;
- arquivo mudou;
- Goal foi ativado;
- Verification terminou.

Campos mínimos:

```text
id
kind
occurred_at
source
payload
trace_id?
related_entity_ids?
goal_id?
experience_id?
```

O `payload` preserva os dados específicos daquele tipo de evento. Não serão criadas dezenas de subclasses de Event no início.

Event registra ocorrência. Ele não declara sozinho que algo é verdade no World.

### 23.6. Claim

É a unidade persistente mínima do World. Representa algo que o SIMON acredita sobre uma Entity com base em evidência.

Campos mínimos:

```text
id
subject_id
predicate
value
epistemic_status
valid_from?
valid_until?
learned_at
evidence_event_ids
status
```

Exemplo:

```text
subject: project:unlimited_ocr
predicate: current_issue
value: generation_loop
```

O v0.1 não começa com um banco de grafos completo. Relações podem ser expressas naturalmente quando `value` referencia outra Entity.

`World State` não será um objeto persistente separado no v0.1. Ele será uma visão calculada sobre as Claims atualmente válidas.

### 23.7. Goal

Representa um estado desejado que o SIMON está autorizado a perseguir.

Campos mínimos:

```text
id
title
origin
parent_goal_id?
desired_state
success_criteria
status
created_at
updated_at
```

Constraints, budgets, deadlines e escalation entram quando um Goal realmente precisar deles. O modelo permite extensão, mas o v0.1 não exige preencher estruturas vazias.

### 23.8. Plan

Representa a estratégia atual para um Goal.

Campos mínimos:

```text
id
goal_id
revision
steps
status
based_on_world_revision?
created_at
updated_at
```

No v0.1, `steps` pode ser uma estrutura simples e ordenada com dependências opcionais. Não será implementado um Plan Graph sofisticado antes de o comportamento real demonstrar necessidade de branches, paralelismo ou DAGs complexos.

Um novo Plan para o mesmo Goal cria nova revisão em vez de apagar silenciosamente a estratégia anterior.

### 23.9. Action

Representa uma tentativa concreta de fazer algo, normalmente através de uma Tool.

Campos mínimos:

```text
id
goal_id
plan_id?
step_id?
kind
tool
input
expected_effect?
status
started_at?
finished_at?
result?
```

No v0.1, `ToolRequest`, `ToolResult` e `ActionReceipt` permanecem partes estruturadas do mesmo Action enquanto não houver necessidade prática de separá-los em objetos persistentes independentes.

Essa decisão reduz entidades artificiais sem perder auditabilidade.

### 23.10. VerificationResult

Registra a tentativa de demonstrar se uma Action ou Goal realmente atingiu o resultado esperado.

Campos mínimos:

```text
id
subject_type
subject_id
criteria
status
evidence_event_ids
observed
strength
created_at
```

`strength` representa o nível procedural da verificação, não uma probabilidade de confiança. No v0.1 é um nível inteiro de 1 a 5, usado apenas para registrar quão forte foi o processo de verificação empregado.

Os estados distinguem sucesso verificado, falha, inconclusivo e avaliação cognitiva quando não existir prova externa suficiente.

Verification não fica embutida em Action porque possui significado epistemológico próprio e pode ocorrer depois da execução original.

### 23.11. Experience

É a unidade causal que conecta contexto, intenção, ações, observações e resultado.

Campos mínimos:

```text
id
title
goal_id?
parent_experience_id?
started_at
ended_at?
status
start_world_revision?
end_world_revision?
event_ids
action_ids
verification_ids
outcome
summary?
```

O `summary` é uma representação operacional da Experience, nunca substituto dos Events e evidências originais.

No primeiro corte implementável, `start_world_revision` e `end_world_revision` permanecem adiados até o World possuir revisão formal. Criar esses campos antes disso produziria apenas referências vazias sem semântica real.

Experiences podem ser nested desde o modelo inicial porque isso evita transformar um Goal longo em uma única experiência gigantesca.

### 23.12. Memory

Representa significado preservado para uso futuro.

Campos mínimos:

```text
id
kind
content
scope
entity_ids?
source_experience_ids?
source_claim_ids?
status
created_at
last_used_at?
```

Tipos iniciais podem cobrir:

- EPISODIC;
- SEMANTIC;
- PROCEDURAL;
- META.

Working Memory permanece runtime state, não registro permanente próprio.

Prospective Memory permanece inicialmente representada por Goal, Event/subscription ou metadata apropriada. Só vira objeto próprio se seu uso real exigir lifecycle separado.

#### Primeiro corte implementável de Memory

No v0.1, uma Memory persistente nasce apenas por decisão explícita a partir de uma ou mais Experiences já `CLOSED`. Production ainda não executa automaticamente Significance Filter, deduplicação ou consolidação. Esses mecanismos entram quando houver volume real de Experiences que justifique automatizá-los.

O conteúdo persistido começa como texto significativo e mantém referências para Experiences, Claims e Entities de origem. O retrieval inicial é deliberadamente simples: somente Memories `ACTIVE`, filtráveis por texto, `kind`, `scope` e Entity. Busca vetorial, embeddings e índices especializados permanecem adiados até existir evidência de que a busca simples não atende.

`last_used_at` é atualizado quando uma Memory é selecionada pelo retrieval normal, permitindo observar uso real sem criar score de importância ou decay artificial no primeiro corte.

### 23.13. Value objects, não entidades independentes

Algumas estruturas serão utilizadas dentro dos objetos acima sem ganhar tabela ou identidade própria no v0.1:

```text
EvidenceRef
ArtifactRef
PlanStep
ExpectedEffect
SuccessCriterion
ResourceUsage
FailureInfo
```

Elas viram objetos persistentes independentes somente se precisarem ser compartilhadas, versionadas ou possuir lifecycle próprio.

### 23.14. Conceitos que deliberadamente não viram objetos no v0.1

Para evitar arquitetura prematura, estes conceitos continuam como serviços, views, configuração ou metadata:

- WorldState: view calculada de Claims;
- WorkingMemory: estado efêmero do runtime;
- FocusSession: inicialmente runtime state;
- CognitiveJob: trace/event estruturado até surgir necessidade de lifecycle próprio;
- PolicyDecision: Event/metadata enquanto a Policy inicial for simples;
- CapabilityGrant: estrutura efêmera de runtime;
- ToolRequest e ActionReceipt: partes de Action;
- Skill: fora do primeiro corte funcional;
- ResearchSignal: fora do primeiro corte funcional;
- LabSession: só entra quando o Lab executável for implementado;
- SystemSnapshot: inicialmente hash/version metadata em Experience/Event;
- Incident: derivado de Events/Failures enquanto correlação simples for suficiente.

Essa lista não significa que os conceitos foram removidos da arquitetura. Significa apenas que ainda não existe necessidade de transformá-los em entidades persistentes próprias.

### 23.15. Relações mínimas

```text
Entity
  ↑
  └──── Claim
          ↑
          └──── evidence ──── Event

Goal
  │
  ├──── Plan
  │       │
  │       └──── Action
  │               │
  │               └──── VerificationResult
  │
  └──── Experience
           ├──── Events
           ├──── Actions
           └──── Verifications
                    │
                    ▼
                  Memory
```

Memory também pode referenciar Claims e Entities diretamente quando o conhecimento não deriva de uma única Experience.

### 23.16. World revision

O v0.1 precisa de uma revisão monotônica simples do World.

Quando Claims aceitas alterarem a visão atual relevante:

```text
world_revision += 1
```

Plans e Experiences podem registrar a revisão em que foram criados sem exigir snapshots completos do World a cada mudança.

Snapshots mais sofisticados só entram quando reprodução e Lab demonstrarem necessidade real.

### 23.17. Append-only versus mutável

Preferência inicial:

**Append-only ou histórico preservado:**

- Event;
- Action execution history;
- VerificationResult;
- Experience encerrada.

**Mutável com histórico/revisão quando necessário:**

- Claim status;
- Goal status;
- Plan status/revision;
- Memory status e uso.

O sistema não precisa implementar event sourcing completo. Preservar histórico onde ele é realmente necessário é suficiente.

### 23.18. O que esse modelo já permite

Com apenas esses objetos, o primeiro SIMON consegue:

```text
receber um pedido
↓
registrar o Event
↓
identificar/criar Entities
↓
criar um Goal
↓
consultar Claims do World
↓
criar um Plan simples
↓
executar Actions por Tools
↓
registrar observações
↓
verificar resultado
↓
encerrar uma Experience
↓
extrair Memory útil
↓
persistir tudo
↓
reiniciar
↓
reconstruir Goal + World + Experience + Memory
↓
continuar de onde parou
```

Esse é o primeiro teste real da arquitetura.

### 23.19. Critério para adicionar um novo objeto canônico

Um conceito só ganha entidade persistente própria quando pelo menos uma destas condições existir:

1. precisa de identidade independente;
2. precisa de lifecycle independente;
3. é referenciado por múltiplos objetos;
4. precisa ser versionado ou auditado separadamente;
5. tratá-lo apenas como metadata começou a gerar complexidade ou perda de informação real.

A pergunta nunca será "isso poderia ser uma classe?".

A pergunta será:

> **Qual problema concreto é resolvido ao dar identidade própria a isso?**

---

## 24. Component Contracts mínimos do v0.1

Os contratos abaixo definem **fronteiras de responsabilidade**, não obrigam a existência de um serviço, processo, classe ou pacote separado para cada componente.

No v0.1, duas responsabilidades podem viver no mesmo módulo se isso mantiver o código mais simples. Elas só devem ser separadas fisicamente quando acoplamento, testes, substituição ou manutenção demonstrarem necessidade real.

A regra é:

> **Separar conceitos primeiro. Separar código quando houver motivo.**

### 24.1. Forma comum de um contrato

Todo contrato entre responsabilidades do v0.1 deve responder somente a cinco perguntas:

```text
Quem chama?
O que entrega?
O que recebe de volta?
Que efeitos colaterais são permitidos?
O que esse componente não pode decidir sozinho?
```

Não será criado um framework interno de mensagens ou interfaces genéricas apenas para padronizar essas chamadas.

Estruturas compartilhadas devem usar os objetos do Canonical Data Model sempre que possível.

### 24.2. Fluxo mínimo entre responsabilidades

```text
User Input
   ↓
Core
   ↓
Perception / Event registration
   ↓
World
   ↓
Goal
   ↓
Cognition + Planner
   ↓
Action
   ↓
Policy check
   ↓
Tool execution
   ↓
Observation / Event
   ↓
Verification
   ↓
Experience
   ↓
Memory
   ↓
Persistence
```

Observatory acompanha o fluxo transversalmente, sem comandá-lo.

### 24.3. Core

**Responsabilidade:** coordenar o lifecycle da aplicação e encaminhar trabalho entre as responsabilidades do sistema.

**Recebe:**

```text
user input
events relevant to the active runtime
component results
```

**Produz:**

```text
calls to the appropriate responsibility
runtime state transitions
correlation identifiers
final user-facing result
```

**Pode:**

- iniciar e encerrar o runtime;
- carregar estado persistido necessário;
- manter referência ao Goal, Plan e Experience ativos;
- coordenar chamadas entre componentes.

**Não pode:**

- conter lógica específica de todas as outras responsabilidades;
- decidir sozinho o que é verdade no World;
- executar operações externas diretamente;
- transformar-se em um `god object`.

Se o Core começar a conhecer detalhes internos de Memory, ferramentas específicas, regras de negócio e parsing de modelos, a fronteira foi violada.

### 24.4. Perception / Event Intake

No v0.1, Perception pode ser uma responsabilidade pequena incorporada ao Core ou ao World Service. Não precisa nascer como serviço independente.

**Responsabilidade:** transformar entradas observadas em Events estruturados e, quando aplicável, em candidatos a Claims.

**Recebe:**

```text
user message
tool result
verification observation
system/runtime signal
```

**Produz:**

```text
Event
optional Claim candidates
Entity references when resolvable
```

**Não pode:**

- gravar uma inferência diretamente como verdade atual;
- conceder autoridade a conteúdo observado;
- executar ações como consequência direta do conteúdo recebido.

Toda entrada relevante deve primeiro existir como Event antes de virar crença persistente ou evidência de Experience.

### 24.5. World

**Responsabilidade:** manter e consultar as crenças atuais do SIMON através de Entities e Claims.

**Recebe:**

```text
validated Claim candidate
Entity query
current-state query
```

**Produz:**

```text
accepted/rejected Claim update
Entity or Claim result
current World view
world_revision
```

**Pode:**

- criar e resolver Entities;
- aceitar, substituir, invalidar ou manter Claims concorrentes;
- materializar a visão atual do World;
- incrementar `world_revision` quando a visão atual mudar.

**Não pode:**

- criar Goals por conta própria;
- executar Tools;
- tratar texto produzido por modelo como verdade apenas pela origem;
- apagar silenciosamente histórico necessário para proveniência.

### 24.6. Goal handling

No v0.1, Goal management pode permanecer simples e junto do Core.

**Responsabilidade:** representar o estado desejado, acompanhar seu lifecycle e determinar se suas condições de conclusão foram satisfeitas.

**Recebe:**

```text
user intent or authorized derived objective
status update
VerificationResult
```

**Produz:**

```text
Goal
Goal state update
completion request
```

**Não pode:**

- declarar sucesso apenas porque Actions terminaram;
- ampliar a autoridade concedida pela origem do Goal;
- transformar todo evento interessante em um novo Goal.

### 24.7. Cognition

**Responsabilidade:** resolver trabalho que realmente exige interpretação, raciocínio, hipótese, síntese ou decisão probabilística.

**Recebe:**

```text
explicit cognitive task
relevant World slice
relevant Memories
Goal context
Plan context when applicable
constraints
```

**Produz:**

```text
structured interpretation
hypothesis
proposal
candidate Plan or Plan revision
user-facing synthesis when requested
```

**Não pode:**

- executar Tools diretamente;
- escrever diretamente no World;
- conceder permissões;
- marcar Goal como concluído sem Verification apropriada;
- usar o modelo para trabalho que lógica determinística simples resolve melhor.

No v0.1, não é necessário persistir `CognitiveJob` como entidade própria. Chamadas cognitivas relevantes entram no trace e em Events estruturados.

### 24.8. Context assembly

Context Builder permanece uma responsabilidade interna de Cognition até existir razão real para extraí-lo.

**Responsabilidade:** montar apenas o contexto necessário para uma chamada cognitiva.

**Recebe:**

```text
cognitive task
Goal
relevant Entity IDs
current Plan
context budget
```

**Consulta:**

```text
World
Memory
```

**Produz:**

```text
bounded cognitive context
references to included Claims and Memories
```

**Não pode:**

- despejar histórico inteiro no modelo por padrão;
- incluir dados proibidos pela Policy;
- transformar resumo em substituto permanente da evidência original.

### 24.9. Planner

No primeiro corte, Planner pode ser uma função de Cognition com validação determinística ao redor. Não precisa nascer como subsistema complexo.

**Responsabilidade:** propor uma sequência executável para transformar o estado atual no estado desejado.

**Recebe:**

```text
Goal
current World view
known constraints
available capabilities
relevant Memories
```

**Produz:**

```text
Plan
Plan revision
or explicit inability to plan
```

**O Plan mínimo deve conter:**

```text
steps
expected effects
known dependencies when necessary
verification intent
```

**Não pode:**

- assumir que o World permanecerá congelado;
- executar seus próprios passos;
- contornar Policy;
- gerar complexidade futura detalhada quando ainda existe alta incerteza.

### 24.10. Policy

A Policy inicial deve ser pequena e determinística. Não será construído um policy framework genérico antes de existir necessidade.

**Responsabilidade:** decidir se uma Action proposta pode ser executada no contexto atual.

**Recebe:**

```text
Action
Goal authority
runtime/user grants
scope
basic risk information
```

**Produz:**

```text
ALLOW
DENY
REQUIRE_APPROVAL
or constraints attached to the Action
```

No v0.1, a decisão pode permanecer registrada como metadata/Event em vez de `PolicyDecision` persistente próprio.

**Não pode:**

- ser modificada pelo modelo durante a decisão;
- conceder nova autoridade porque uma ação parece útil;
- deixar uma autorização específica virar permissão global implicitamente.

### 24.11. Tool execution

Tool Gateway e Executor podem começar como uma única responsabilidade operacional.

**Responsabilidade:** executar a operação concreta representada por uma Action depois da autorização necessária.

**Recebe:**

```text
Action
validated parameters
effective permission
```

**Produz:**

```text
structured execution result
observed raw output
new Events
resource/failure metadata
```

**Pode:**

- chamar providers concretos como filesystem, Python e shell dentro do escopo aprovado;
- aplicar timeout e limites simples;
- registrar stdout, stderr, exit code e alterações relevantes.

**Não pode:**

- interpretar seu próprio resultado como Goal completion;
- expandir o escopo autorizado;
- aceitar uma intenção vaga em linguagem natural quando a operação pode ser estruturada;
- marcar sua própria execução como verdade verificada.

### 24.12. Verification

**Responsabilidade:** comparar efeitos esperados com evidências observadas.

**Recebe:**

```text
Action or Goal subject
expected effects
success criteria
relevant Events / observations
```

**Produz:**

```text
VerificationResult
```

**Não pode:**

- transformar ausência de erro em prova de sucesso;
- declarar certeza quando a evidência é apenas cognitiva;
- confiar exclusivamente no `success` retornado pela mesma operação que está verificando quando houver verificação independente simples disponível.

No primeiro corte, verificadores serão implementados apenas para as operações realmente suportadas.

### 24.13. Experience

Experience handling pode permanecer uma responsabilidade de fechamento de ciclo, sem um `Experience Service` complexo.

**Responsabilidade:** agregar os eventos causalmente relevantes de uma tentativa em uma unidade persistente de experiência.

**Recebe:**

```text
Goal reference
related Events
Actions
VerificationResults
start/end World revisions
```

**Produz:**

```text
Experience
```

**Não pode:**

- duplicar todo dado bruto já preservado em Events e Artifacts;
- inventar causalidade que não possa ser justificada;
- transformar automaticamente toda Experience em Memory.

### 24.14. Memory

**Responsabilidade:** persistir e recuperar significado útil para o futuro.

**Write recebe:**

```text
Experience
Claims
explicit user information eligible for persistence
```

**Write produz:**

```text
Memory or no-memory decision
```

**Read recebe:**

```text
retrieval intent
Goal/project/entity context
context budget
```

**Read produz:**

```text
ranked relevant Memories
with provenance references
```

**Não pode:**

- tratar todo Event como memória;
- retornar histórico inteiro por padrão;
- substituir World para fatos atuais;
- apagar proveniência durante consolidação.

O v0.1 deve começar com retrieval simples. Busca híbrida sofisticada só entra se os dados reais mostrarem necessidade.

### 24.15. Persistence

Persistence é uma responsabilidade técnica necessária desde o primeiro corte, mas não representa um novo órgão cognitivo.

**Responsabilidade:** armazenar e recuperar os nove objetos canônicos e metadados necessários de forma consistente.

**Recebe:**

```text
canonical object writes
queries by ID / relation / basic filters
```

**Produz:**

```text
persisted object
query results
```

**Não pode:**

- decidir significado cognitivo;
- conter regras de Planner, Memory ou World apenas por conveniência;
- expor detalhes do mecanismo de armazenamento para toda a aplicação sem necessidade.

O mecanismo concreto de banco será escolhido depois do escopo do v0.1, não antes.

### 24.16. Observatory

**Responsabilidade:** registrar o funcionamento do sistema de forma suficiente para reconstrução, diagnóstico e futura pesquisa.

**Recebe:**

```text
Events
component timing
resource usage
failure information
correlation IDs
artifact references
```

**Produz:**

```text
structured trace
metrics
Production Archive entries
```

**Não pode:**

- comandar o Executive;
- alterar comportamento operacional por conta própria;
- iniciar o Lab;
- transformar toda telemetria em nova arquitetura preventiva.

No v0.1, Observatory pode reutilizar Event e Experience como sua principal base em vez de introduzir uma stack externa completa de observabilidade.

### 24.17. User interface boundary

A primeira interface pode ser CLI. Interface gráfica, voz e presença contínua não são requisitos para validar a arquitetura inicial.

**Responsabilidade:** receber intenção explícita e apresentar resultados, estados e pedidos de autorização.

**Recebe do usuário:**

```text
message
approval / denial
explicit command
```

**Entrega ao usuário:**

```text
response
relevant status
approval request
verified result when available
```

A UI não contém lógica de World, Planner ou Memory.

### 24.18. Contratos de erro

Não será criada uma taxonomia extensa de exceções antes de observarmos os erros reais.

No boundary entre componentes, o v0.1 precisa distinguir somente o necessário para o fluxo funcionar:

```text
SUCCESS
FAILED
BLOCKED
DENIED
INCONCLUSIVE
```

Um erro concreto deve preservar:

```text
component
operation
human-readable reason
raw technical cause when available
related Goal / Action / Event
```

Novas categorias só entram quando ajudarem algum componente a reagir de maneira diferente.

### 24.19. Regra para comunicação entre componentes

Quando uma responsabilidade chama outra, deve passar **dados do domínio**, não acessar diretamente seu estado interno.

Preferir:

```text
World.get_current_claims(entity_id)
```

em vez de:

```text
planner reaches into world_database.tables...
```

Preferir:

```text
Memory.retrieve(context)
```

em vez de permitir que Cognition conheça o mecanismo de índice.

Isso preserva substituibilidade sem exigir um framework pesado de interfaces desde o início.

### 24.20. Regra de efeitos colaterais

Apenas duas fronteiras possuem efeitos externos deliberados no v0.1:

```text
Persistence
Tool execution
```

Os demais componentes transformam ou avaliam dados e produzem propostas ou estados internos.

Essa regra torna mais fácil testar Cognition, Planner, World, Memory selection e Verification sem modificar o computador real.

### 24.21. Regra de dependência

A dependência conceitual preferida é:

```text
UI
↓
Core
↓
Domain responsibilities
↓
Persistence / Tool boundary
↓
External world
```

O domínio não deve depender de detalhes da UI.

Cognition não deve depender de um modelo específico.

World e Memory não devem depender de uma ferramenta externa específica.

Nenhuma camada adicional será criada apenas para fazer esse desenho parecer arquiteturalmente puro.

### 24.22. Contrato de retomada após reinício

Esse é o principal teste integrado do v0.1.

Após reiniciar o processo, o Core deve conseguir consultar Persistence e reconstruir o suficiente para responder:

```text
qual Goal estava ativo?
qual era o Plan atual?
quais Actions já ocorreram?
qual era a revisão relevante do World?
qual foi a última Experience?
quais Memories são relevantes para continuar?
```

O sistema não precisa restaurar byte a byte o contexto anterior do modelo.

Ele precisa restaurar **estado semântico suficiente para continuar o trabalho**.

### 24.23. O que deliberadamente não existe nesses contratos

O v0.1 não exige contratos próprios para:

```text
Executive avançado
Attention scoring
Resource Manager sofisticado
Skill Runtime
Capability Graph
Model Router multi-modelo
Lab Research Controller
Researcher / Evaluator
Promotion Gate executável
MetaResearch
```

Os conceitos permanecem na especificação global, mas só ganharão contratos de implementação quando entrarem no escopo funcional real.

### 24.24. Critério para criar novo contrato

Uma nova fronteira formal só deve nascer quando pelo menos um problema real aparecer:

1. duas responsabilidades precisam evoluir independentemente;
2. testes estão difíceis porque efeitos e lógica estão misturados;
3. uma implementação precisa ser substituída;
4. o acoplamento começou a causar alterações em cascata;
5. um limite de autoridade, persistência ou efeito colateral precisa ser protegido.

> **Contrato existe para proteger uma fronteira real. Não para antecipar uma arquitetura imaginária.**

---

## 25. State Machines mínimas do v0.1

State existe para representar uma diferença operacional real. Um novo estado só deve ser criado quando ele mudar pelo menos uma destas coisas:

- o que pode acontecer em seguida;
- o que o sistema deve fazer ao retomar após reinício;
- como outro componente deve reagir;
- se o objeto ainda pode ser alterado;
- se o resultado pode ser considerado encerrado.

Não serão criados estados apenas para documentar fases internas que não mudam comportamento.

### 25.1. Regras gerais de lifecycle

1. Transições devem ocorrer por eventos ou operações identificáveis.
2. Uma transição relevante gera Event para manter histórico.
3. Estado terminal não deve ser silenciosamente reaberto. Uma nova tentativa cria nova revisão, Action, Plan ou Experience quando apropriado.
4. Reinício do processo não deve transformar estado semanticamente. O runtime reconstrói o lifecycle persistido.
5. Falha de uma Action não implica falha do Goal.
6. Conclusão de um Plan não implica conclusão do Goal.
7. `COMPLETED` de Goal só pode ocorrer quando seus critérios de sucesso forem satisfeitos de forma compatível com Verification.
8. Não existe transição implícita baseada apenas na opinião do modelo. Cognition pode propor; o domínio aplica a transição válida.

### 25.2. Entity

`Entity` não possui State Machine no v0.1.

Uma Entity representa identidade persistente. Caso no futuro exista necessidade real de arquivamento, merge ou remoção lógica, isso será adicionado com base em casos observados.

### 25.3. Event

`Event` é append-only e imutável depois de persistido.

Não possui `status` operacional.

Se uma interpretação posterior estiver errada, cria-se nova evidência, Claim ou Event corretivo. O evento histórico original não é reescrito para parecer que o passado foi diferente.

### 25.4. Claim

Estados mínimos:

```text
ACTIVE
SUPERSEDED
RETRACTED
EXPIRED
```

Significado:

- `ACTIVE`: faz parte das crenças atualmente válidas do World;
- `SUPERSEDED`: uma Claim posterior substituiu esta como melhor representação do mesmo aspecto do mundo;
- `RETRACTED`: evidência posterior mostrou que a Claim não deve mais ser tratada como válida;
- `EXPIRED`: a informação perdeu validade temporal sem necessariamente ter sido falsa.

Fluxos típicos:

```text
ACTIVE ──► SUPERSEDED
ACTIVE ──► RETRACTED
ACTIVE ──► EXPIRED
```

Uma Claim histórica não volta para `ACTIVE`. Se voltar a ser verdadeira, cria-se uma nova Claim com nova evidência e novo tempo de validade.

### 25.5. Goal

Estados mínimos:

```text
ACTIVE
WAITING
BLOCKED
PAUSED
COMPLETED
FAILED
CANCELLED
```

Significado:

- `ACTIVE`: SIMON pode trabalhar no Goal agora;
- `WAITING`: existe um evento esperado antes que o trabalho possa continuar;
- `BLOCKED`: existe um obstáculo sem resolução automática disponível naquele momento;
- `PAUSED`: o trabalho foi conscientemente suspenso, mas pode ser retomado;
- `COMPLETED`: os critérios de sucesso foram satisfeitos;
- `FAILED`: o Goal em si foi encerrado porque não pôde ser atingido dentro das condições válidas;
- `CANCELLED`: uma autoridade apropriada decidiu que ele não deve mais ser perseguido.

Fluxo principal:

```text
             ┌────► WAITING ─────┐
             │                   │
ACTIVE ──────┼────► BLOCKED ─────┼────► ACTIVE
             │                   │
             └────► PAUSED ──────┘

ACTIVE ───────────────────────────────► COMPLETED
ACTIVE ───────────────────────────────► FAILED
ACTIVE / WAITING / BLOCKED / PAUSED ─► CANCELLED
```

Regras:

- `WAITING` significa "sei o que estou esperando";
- `BLOCKED` significa "não consigo continuar com o conhecimento, capacidade ou autoridade atual";
- Action ou Plan falhar não muda automaticamente Goal para `FAILED`;
- uma nova estratégia pode devolver um Goal bloqueado para `ACTIVE`;
- um Goal concluído, falho ou cancelado é terminal no v0.1.

`PROPOSED` não será persistido no v0.1. Uma proposta cognitiva ainda não é Goal. O objeto Goal nasce quando a intenção é aceita pelo Core/Policy aplicável.

### 25.6. Plan

Estados mínimos:

```text
ACTIVE
COMPLETED
FAILED
SUPERSEDED
CANCELLED
```

Significado:

- `ACTIVE`: estratégia atualmente utilizável para o Goal;
- `COMPLETED`: todos os passos que pertenciam à estratégia foram resolvidos;
- `FAILED`: a estratégia se mostrou inviável, não o Goal necessariamente;
- `SUPERSEDED`: um novo Plan/revision substituiu esta estratégia;
- `CANCELLED`: o Plan foi encerrado porque deixou de ser necessário.

Fluxos principais:

```text
ACTIVE ─► COMPLETED
ACTIVE ─► FAILED
ACTIVE ─► SUPERSEDED
ACTIVE ─► CANCELLED
```

Uma replanificação cria nova revisão em vez de apagar a anterior.

No v0.1 não haverá estados por step além do mínimo contido na própria estrutura do `steps`. Se steps crescerem a ponto de exigir lifecycle independente, a necessidade será observada antes de criar `PlanStep` como entidade.

### 25.7. Action

Estados mínimos:

```text
PENDING
RUNNING
COMPLETED
FAILED
BLOCKED
DENIED
INTERRUPTED
CANCELLED
```

Significado:

- `PENDING`: Action criada, ainda não iniciada;
- `RUNNING`: execução iniciou;
- `COMPLETED`: o executor terminou a operação e produziu um resultado;
- `FAILED`: execução terminou com falha concreta;
- `BLOCKED`: falta uma precondition, recurso ou condição externa;
- `DENIED`: Policy não autorizou a execução;
- `INTERRUPTED`: execução perdeu continuidade antes de obter resultado terminal confiável;
- `CANCELLED`: foi encerrada antes da execução ou durante uma operação cancelável.

Fluxo principal:

```text
PENDING ─► RUNNING ─► COMPLETED
   │          ├─────► FAILED
   │          ├─────► BLOCKED
   │          ├─────► INTERRUPTED
   │          └─────► CANCELLED
   │
   ├───────────────► BLOCKED
   ├───────────────► DENIED
   └───────────────► CANCELLED
```

`COMPLETED` significa que a operação terminou, não que o efeito desejado foi provado. Essa conclusão pertence ao `VerificationResult`.

Ao reiniciar o SIMON, uma Action persistida como `RUNNING` não deve ser presumida como falha nem sucesso. O Core a trata como execução interrompida e tenta reconciliar o estado real quando isso for necessário.

### 25.8. VerificationResult

`VerificationResult` não possui State Machine mutável no v0.1. Ele nasce como resultado terminal de uma tentativa de verificação.

Classificações mínimas:

```text
VERIFIED
FAILED
INCONCLUSIVE
ASSESSED
```

- `VERIFIED`: evidência satisfaz os critérios exigidos;
- `FAILED`: evidência demonstra que os critérios não foram satisfeitos ou que um invariant foi violado;
- `INCONCLUSIVE`: houve tentativa, mas não existe evidência suficiente para concluir;
- `ASSESSED`: o resultado depende de julgamento cognitivo porque não existe verificação externa adequada.

Se nova evidência surgir depois, cria-se outro `VerificationResult` referenciando o mesmo subject. O histórico anterior permanece intacto.

Isso evita transformar verificação em registro mutável de "verdade atual". O estado epistemológico atual pode ser calculado a partir dos resultados disponíveis.

### 25.9. Experience

A Experience separa lifecycle da sessão e outcome.

Estados mínimos:

```text
ACTIVE
SUSPENDED
CLOSED
```

Fluxo:

```text
ACTIVE ─► SUSPENDED ─► ACTIVE
ACTIVE ──────────────► CLOSED
SUSPENDED ───────────► CLOSED
```

`SUSPENDED` existe porque uma Experience pode atravessar reinícios, espera longa ou mudança de foco sem ter realmente terminado.

Ao fechar, `outcome` registra a conclusão causal sem criar novos estados artificiais. Valores iniciais podem ser:

```text
SUCCESS
FAILURE
PARTIAL
INCONCLUSIVE
INTERRUPTED
```

Exemplo:

```text
status: CLOSED
outcome: FAILURE
```

pode representar uma tentativa de hipótese que falhou, enquanto o Goal pai continua `ACTIVE`.

Uma Experience fechada não é reaberta. Continuação relevante cria nova Experience, podendo referenciar a anterior como parent ou contexto.

### 25.10. Memory

Estados mínimos:

```text
ACTIVE
ARCHIVED
SUPERSEDED
RETRACTED
```

- `ACTIVE`: elegível para retrieval normal;
- `ARCHIVED`: preservada, mas removida do caminho normal de recuperação;
- `SUPERSEDED`: conhecimento mais novo consolidou ou substituiu essa representação;
- `RETRACTED`: não deve ser utilizado como conhecimento válido, embora permaneça no histórico.

Fluxos principais:

```text
ACTIVE ─► ARCHIVED
ACTIVE ─► SUPERSEDED
ACTIVE ─► RETRACTED
```

No v0.1 não haverá decay complexo, confidence score mutável, TTL genérico ou garbage collector sem evidência de necessidade.

### 25.11. Relação entre Action e Verification

É importante que esses dois lifecycles não sejam fundidos.

Exemplo:

```text
Action A17
status: COMPLETED

Verification V9
status: FAILED
```

Significa:

```text
a operação foi executada,
mas o efeito esperado não ocorreu corretamente.
```

Outro caso:

```text
Action A18
status: COMPLETED

Verification V10
status: INCONCLUSIVE
```

O sistema sabe que executou, mas não finge saber se funcionou.

### 25.12. Relação entre Plan e Goal

Também permanecem independentes:

```text
Plan P4
status: FAILED

Goal G2
status: ACTIVE
```

O Planner pode gerar P5.

Somente quando o próprio Goal deixa de ser razoavelmente atingível dentro das condições válidas ele pode terminar como `FAILED`.

### 25.13. Relação entre Experience e Goal

Experience registra uma tentativa causal. Goal registra a intenção persistente.

Portanto:

```text
Experience E14
status: CLOSED
outcome: FAILURE

Goal G2
status: ACTIVE
```

é um estado normal e esperado.

Isso permite ao SIMON aprender com tentativas malsucedidas sem confundir tentativa com objetivo.

### 25.14. Retomada após reinício

Na inicialização, o Core deve procurar no mínimo:

```text
Goals em ACTIVE / WAITING / BLOCKED / PAUSED
Plans ACTIVE associados
Actions PENDING / RUNNING
Experiences ACTIVE / SUSPENDED
```

Regras iniciais:

1. `RUNNING` encontrado após perda do runtime é tratado como execução potencialmente interrompida e precisa ser reconciliado antes de retry.
2. `PENDING` pode ser reavaliado pelo Planner/Policy antes da execução.
3. `ACTIVE Experience` pode ser convertida para `SUSPENDED` durante recovery quando sua continuidade operacional foi perdida.
4. Goal não é cancelado ou falhado apenas porque o processo reiniciou.
5. World e Memory são reconstruídos a partir do estado persistido, não do contexto anterior do modelo.

### 25.15. O que deliberadamente não ganha State Machine agora

Não haverá lifecycle formal independente no v0.1 para:

```text
Entity
Event
WorldState
PlanStep
CognitiveJob
PolicyDecision
ToolRequest
ActionReceipt
FocusSession
ResearchSignal
Skill
LabSession
```

Alguns desses conceitos terão lifecycle em versões futuras, quando se tornarem objetos reais do sistema.

No caso do Lab, o modelo teórico já prevê:

```text
IDLE
PENDING_AUTHORIZATION
AUTHORIZED
RUNNING
PAUSED
COMPLETED
```

mas ele não será implementado como State Machine até o Lab executável entrar no escopo.

### 25.16. Critério para adicionar novo estado

Um novo estado só entra quando existir pelo menos um fluxo real em que dois objetos hoje tratados com o mesmo estado precisem de comportamento diferente.

Exemplo válido:

```text
FAILED
```

e

```text
DENIED
```

são diferentes em Action porque um retry pode depender da causa: falha de execução e falta de autoridade exigem respostas diferentes.

Exemplo inválido sem necessidade concreta:

```text
PREPARING
READY_TO_START
ABOUT_TO_RUN
```

se todos produzem exatamente a mesma decisão seguinte.

> **State existe para mudar comportamento. Se não muda comportamento, é descrição, não estado.**

---

## 26. Próximos passos após o fechamento teórico

A teoria dos órgãos principais, o Canonical Data Model mínimo, os Component Contracts mínimos, as State Machines necessárias e o escopo funcional do v0.1 estão fechados.

A partir daqui, as decisões deixam de ser de arquitetura conceitual e passam a ser de implementação.

A ordem será:

1. **Technology Choices**  
   Escolher tecnologias a partir das necessidades efetivas do v0.1, sem antecipar infraestrutura de versões futuras.

2. **Repository Structure**  
   Criar apenas as pastas necessárias para a implementação escolhida. Nenhuma camada vazia por antecipação.

3. **Bootstrap do projeto**  
   Criar o repositório executável mínimo e iniciar a implementação pelo menor fluxo vertical que atravesse persistência, Goal, Cognition, ação, Verification e Experience.

---

## 27. Critério para começar a implementação

A implementação funcional começa quando os quatro itens de especificação do v0.1 estiverem fechados:

```text
Canonical Data Model mínimo        FECHADO
Component Contracts mínimos        FECHADO
State Machines necessárias         FECHADO
v0.1 Scope                          FECHADO
```

Tecnologia e estrutura do repositório serão decididas imediatamente depois, orientadas pelo escopo fechado e não por preferência arquitetural antecipada.

---

## 28. Resumo filosófico

SIMON não deve tentar ser inteligente em tudo desde o primeiro dia. Deve possuir uma fundação correta para perceber, lembrar, decidir, agir, verificar, aprender e evoluir sem confundir competência com autoridade.

O projeto deve começar simples, observável e persistente. Complexidade entra somente quando experiências reais demonstrarem sua necessidade.

> **Construa para o problema que existe, preserve espaço para evolução e deixe a própria experiência do sistema revelar onde a complexidade realmente precisa nascer.**
---

## 29. SIMON v0.1 Scope

### 29.1. Objetivo do v0.1

O v0.1 não pretende demonstrar toda a visão futura do SIMON.

Seu objetivo é provar o menor ciclo completo que distingue o SIMON de um chatbot com histórico:

```text
compreender contexto persistente
        ↓
manter World e Goals fora do modelo
        ↓
usar Cognição para decidir
        ↓
planejar uma ação local
        ↓
executá-la de forma controlada
        ↓
verificar o resultado
        ↓
registrar a Experience
        ↓
preservar memória útil
        ↓
encerrar o processo
        ↓
reiniciar
        ↓
retomar o trabalho semanticamente
```

A versão é considerada bem-sucedida quando esse ciclo funciona de ponta a ponta de forma simples, observável e recuperável.

> **O v0.1 deve provar persistência cognitiva, não amplitude de funcionalidades.**

### 29.2. Golden Scenario

O cenário de referência será um projeto local de software.

```text
Usuário:
"SIMON, vamos trabalhar neste projeto."

SIMON:
reconhece/cria a Entity do projeto
define o workspace ativo
cria ou recupera o Goal
carrega somente o contexto necessário

Usuário:
"Descubra por que este teste está falhando."

SIMON:
consulta World e Memory
monta um Plan curto
lê os arquivos relevantes
executa o teste
observa a falha
formula ou testa uma hipótese
realiza uma modificação autorizada
executa novamente
verifica o resultado
atualiza o Goal
registra Experience e evidências
consolida memória útil
```

Depois o processo do SIMON é encerrado completamente.

Ao iniciar novamente:

```text
Usuário:
"Continua aquele problema."

SIMON:
resolve qual projeto e Goal estão sendo referidos
recupera World, Goal, estado relevante, Experiences e Memory
identifica o último ponto confiável
valida se o ambiente ainda é compatível
continua sem depender do contexto anterior do modelo
```

Esse é o teste central do v0.1.

### 29.3. Interface mínima

O v0.1 precisa apenas de uma interface textual suficiente para:

```text
enviar solicitações
ver respostas
ver pedidos de autorização
consultar Goals ativos
consultar estado básico
encerrar e reiniciar o runtime
```

Interface gráfica, voz, avatar e experiência visual sofisticada ficam fora do critério de sucesso.

### 29.4. Persistência

Devem sobreviver ao encerramento do runtime:

```text
Entities relevantes
Events
Claims
Goals
Plans necessários à retomada
Actions
Verification Results
Experiences
Memories
referências a Artifacts
configuração persistente necessária
```

O contexto da janela do modelo nunca é fonte oficial de persistência.

### 29.5. World mínimo

O World do v0.1 precisa representar somente o necessário para o cenário inicial:

```text
projetos
arquivos relevantes
Goals
estado de processos iniciados pelo SIMON
propriedades básicas do ambiente
Claims atuais sobre essas entidades
```

Não será criada uma infraestrutura sofisticada de knowledge graph antes de existir necessidade real.

### 29.6. Goals mínimos

O v0.1 deve conseguir:

```text
criar Goal explícito
associar a projeto/contexto
ativar
pausar
bloquear
concluir
falhar somente quando o Goal realmente falhar
retomar após reinício
```

Não haverá criação autônoma de missões independentes de longo prazo.

### 29.7. Cognition mínima

O v0.1 utilizará pelo menos um modelo local como mecanismo cognitivo substituível.

Cognition entra quando houver necessidade real de:

```text
interpretar solicitação
selecionar informação relevante
formular hipótese
propor plano
analisar erro
produzir resposta
```

Não haverá arquitetura multiagente nem obrigação de suportar vários modelos no primeiro corte.

### 29.8. Context mínimo

O modelo não recebe automaticamente todo o histórico. O contexto deve ser montado a partir de:

```text
solicitação atual
Goal ativo
World relevante
memórias relevantes
estado atual do Plan
restrições necessárias
resultados de Tools necessários
```

Reranker, vector database e compressão avançada não são requisitos do v0.1.

### 29.9. Planner mínimo

O Planner precisa produzir apenas planos curtos suficientes para o Golden Scenario, contendo:

```text
intenção de cada passo
ordem ou dependência necessária
precondições relevantes
capability necessária
forma de verificação
```

Plan Graph sofisticado e planejamento de longo horizonte ficam para quando houver necessidade.

### 29.10. Actions mínimas

Actions devem persistir intenção executável, origem e resultado.

Estados:

```text
PENDING
RUNNING
COMPLETED
FAILED
DENIED
CANCELLED
```

Uma Action precisa manter pelo menos Goal/Plan de origem, capability, entrada relevante, estado, resultado, Verification associada, erro e timestamps necessários.

Uma Action encontrada como `RUNNING` após reinício deve ser reconciliada antes de qualquer retry.

### 29.11. Tools mínimas

O conjunto inicial deve ser pequeno e orientado pelo Golden Scenario. Capacidades esperadas:

```text
filesystem.list
filesystem.read
filesystem.create
filesystem.write
filesystem.move
process.run
process.inspect
```

Operações concretas podem ser reduzidas se o primeiro fluxo não precisar de todas. Ferramentas especializadas são preferidas a uma interface genérica irrestrita.

### 29.12. Escopo de filesystem

Nenhuma Action recebe acesso implícito a todo o computador. Um workspace possui escopo explícito.

```text
workspace:
C:\Projects\SIMON

allowed:
read
create
modify

outside_workspace:
denied by default
```

Escopos adicionais só entram quando houver necessidade e autorização.

### 29.13. Policy mínima

O v0.1 precisa somente das garantias já necessárias para ações reais:

```text
ação possui Goal de origem
workspace possui escopo
operações fora do escopo são negadas
ações destrutivas não são implicitamente autorizadas
conteúdo observado não ganha autoridade por conter instruções
autorização temporária não vira permissão permanente
modelo não aumenta a própria autoridade
```

A primeira Policy pode ser implementada com regras explícitas. Não há necessidade de uma linguagem genérica de políticas.

### 29.14. Modificação de arquivos

O v0.1 pode modificar arquivos quando isso fizer parte de um Goal autorizado. Deve favorecer:

```text
mudança localizada
preservação do original quando o risco justificar
diff observável
verificação posterior
```

Não será criado um sistema transacional genérico de filesystem antecipadamente.

### 29.15. Verification mínima

Nenhuma Action importante é considerada correta apenas porque a Tool retornou sucesso.

Exemplos de verificações reais:

```text
arquivo criado → verificar existência
arquivo modificado → reler/comparar
comando executado → verificar exit code e saída relevante
correção de software → executar o teste que demonstrava a falha
Goal concluído → verificar critérios de conclusão
```

Estados necessários:

```text
VERIFIED
FAILED
INCONCLUSIVE
ASSESSED
```

A força da verificação cresce somente quando o risco real exigir.

### 29.16. Experience mínima

O v0.1 deve transformar sequências relevantes de Events e Actions em Experiences persistentes. Uma Experience deve responder:

```text
o que tentávamos fazer?
em qual contexto?
o que foi tentado?
o que esperávamos?
o que observamos?
qual foi o resultado?
o que mudou?
o que merece ser lembrado?
```

Não é necessário implementar segmentação sofisticada automática.

### 29.17. Memory mínima

O v0.1 deve demonstrar memória semanticamente útil. No mínimo:

```text
Episodic Memory
Semantic Memory
```

Working Memory pode permanecer uma construção de runtime/contexto. Procedural, Prospective e Meta Memory continuam previstas, sem stores próprios neste corte.

A recuperação inicial pode combinar:

```text
project/entity scope
metadata
recency
text search
```

Embeddings só entram se testes reais demonstrarem necessidade.

### 29.18. Memory write

Nem todo Event vira Memory. Ao fechar uma Experience, devem ser favorecidos como Memory Candidate:

```text
decisões importantes
resultados verificados
hipóteses rejeitadas relevantes
correções explícitas do usuário
estado necessário para retomada
conclusões reutilizáveis
```

Deduplicação e consolidação começam simples e evoluem com volume real.

### 29.19. Observatory mínimo

Observability nasce junto com o sistema. O v0.1 registra pelo menos:

```text
Events estruturados
trace_id
Goal relacionado
Action relacionada
modelo utilizado
Tool utilizada
latência básica
falhas
Verification Results
Experience de origem
```

Não será criado dashboard antes de existir necessidade.

### 29.20. Production Archive

Toda informação operacional necessária para reconstrução e pesquisa futura deve ser preservada no Production Archive, mantendo relação entre:

```text
Events
Experiences
Goals
Actions
Memories
Verification
Artifacts
```

O objetivo é preservar história operacional e proveniência, não duplicar indiscriminadamente dados.

### 29.21. Lab Intake no v0.1

O SIMON Lab executável não pertence ao v0.1. Entretanto, Production já deve alimentar:

```text
Production
↓
Production Archive
↓
Lab Intake
↓
Lab Inbox
↓
PENDING_AUTHORIZATION
```

Nenhum experimento, mutação, benchmark de autoevolução ou promoção automática será iniciado.

### 29.22. Lab authorization invariant

Desde o v0.1 devem permanecer verdadeiras estas regras:

> **Production pode alimentar continuamente o Lab Intake, mas Lab Research nunca inicia sem autorização explícita do usuário.**

> **Autorizar Lab Research não autoriza Promotion.**

### 29.23. Learning no v0.1

O v0.1 não modifica algoritmos, código, pesos ou arquitetura com base nas Experiences. Learning inicial significa principalmente:

```text
transformar Experience em conhecimento persistente
registrar evidência
permitir que Memory altere decisões futuras
```

Procedure mining, Strategy Learning automatizado, Skill synthesis, fine-tuning e mudanças estruturais ficam fora.

### 29.24. Skills no v0.1

Não é necessário implementar um Skill Registry completo. Se surgir uma sequência operacional estável necessária ao Golden Scenario, ela pode existir como função ou composição explícita.

Skill se torna objeto formal somente quando houver necessidade real de descoberta por capability, versionamento independente, múltiplas implementações, competence tracking ou lifecycle próprio.

### 29.25. Executive e Attention no v0.1

Não haverá scheduler cognitivo sofisticado. No primeiro corte:

```text
solicitação atual
+
Goal foreground
=
foco principal
```

Background jobs necessários podem ser acompanhados de forma simples. Attention Manager e Executive completos entram quando houver competição real entre Goals ou Events.

### 29.26. Autonomia do v0.1

SIMON pode:

```text
interpretar
consultar estado
planejar
ler dentro do workspace
executar ações autorizadas no workspace
executar testes/processos autorizados
verificar
registrar Experience
lembrar
retomar
```

SIMON não pode autonomamente:

```text
expandir os próprios escopos
alterar regras de autoridade
iniciar Lab Research
promover mudanças do Lab
criar missões independentes de longo prazo
acessar sensores pessoais
operar serviços externos sem capability e autorização próprias
```

### 29.27. Fora do v0.1

Não fazem parte do critério de conclusão:

```text
câmera
microfone
screen vision contínua
clipboard monitoring
browser automation
email
calendar
mobile integration
multi-agent architecture
multiple model routing
automatic Skill synthesis
full Capability Registry
advanced Attention Manager
advanced Executive scheduler
vector database obrigatório
knowledge graph database obrigatório
distributed services
containers obrigatórios
microservices
fine-tuning
LoRA
training
autonomous Lab Research
automatic Promotion
graphical dashboard
voice personality
avatar
cloud synchronization
```

Isso não rejeita essas capacidades. Apenas registra que o v0.1 ainda não demonstrou necessidade para elas.

### 29.28. Não objetivos

O v0.1 não precisa parecer humano, resolver qualquer projeto, ser rápido em todos os casos, possuir autonomia contínua, competir com assistentes comerciais ou otimizar a si mesmo.

Ele precisa ser correto em sua fundação.

### 29.29. Definition of Done

O SIMON v0.1 será considerado funcional quando o mesmo sistema conseguir:

1. Iniciar com armazenamento vazio.
2. Registrar um projeto como Entity.
3. Criar um Goal a partir de uma solicitação real.
4. Construir contexto sem depender do histórico bruto integral.
5. Usar um modelo local para uma necessidade cognitiva real.
6. Produzir um Plan simples.
7. Executar pelo menos uma Action real dentro de workspace autorizado.
8. Verificar independentemente o efeito relevante da Action.
9. Atualizar Claims/World com base na evidência.
10. Fechar ou atualizar uma Experience coerente.
11. Persistir memória útil derivada da Experience.
12. Encerrar completamente o processo.
13. Iniciar novamente sem restaurar o contexto do modelo.
14. Resolver projeto e Goal anteriores a partir da persistência.
15. Recuperar memória relevante.
16. Validar que o estado externo necessário continua atual.
17. Continuar no ponto semanticamente correto.
18. Preservar Trace suficiente para reconstruir a relação entre Action, Goal e Experience.
19. Registrar a execução no Production Archive.
20. Tornar o material elegível no Lab Inbox como `PENDING_AUTHORIZATION`, sem iniciar pesquisa.

Se qualquer elemento fundamental depender de informação escondida apenas na janela anterior do modelo, o teste falhou.

### 29.30. Teste de reinício

```text
RUN A

User → Goal → Cognition → Plan → Action
     → Verification → Experience → Memory

PROCESS TERMINATED

────────────────────────────────────

RUN B

No previous model context

Persistence
   ↓
Project / World / Goal / Experience / Memory
   ↓
Context reconstruction
   ↓
State revalidation
   ↓
Continue
```

O segundo runtime não pode depender de replay integral da conversa.

### 29.31. Teste de falsa conclusão

Deve existir um cenário em que:

```text
Action completes
but verification fails
```

Resultado obrigatório:

```text
Action: COMPLETED
Verification: FAILED
Goal: NOT COMPLETED
```

Isso demonstra que SIMON não confunde execução com verdade.

### 29.32. Teste de falha real

Uma Tool ou processo deve falhar deliberadamente em pelo menos um cenário. SIMON deve:

```text
registrar o Failure
preservar evidência
não entrar em retry infinito
manter Goal coerente
permitir replanejamento ou bloqueio
```

Não é necessário antecipar todas as falhas possíveis.

### 29.33. Teste de escopo

Uma Action deve tentar ou simular operação fora do workspace autorizado. Resultado obrigatório:

```text
DENIED
```

sem alteração externa.

### 29.34. Teste de memória

Após uma Experience significativa:

```text
Session A:
hipótese X testada e rejeitada
```

Em execução futura e contexto semelhante:

```text
Session B:
Memory retrieval recupera o resultado anterior
```

Cognition não deve repetir X como se nunca tivesse sido testado, salvo se houver nova evidência ou contexto que justifique a repetição.

### 29.35. Teste do Lab Inbox

Após uso em Production:

```text
Production Archive:
contains Experiences and evidence

Lab Inbox:
PENDING_AUTHORIZATION
```

Nenhum processo de pesquisa deve iniciar sozinho.

### 29.36. Critério de simplicidade

Toda abstração nova deve conseguir responder:

```text
Qual problema atual ela resolve?
```

Se a resposta for apenas:

```text
"talvez seja útil depois"
```

ela não entra.

### 29.37. Critério final do v0.1

O marco não será quantidade de código, modelos ou features.

> **SIMON consegue iniciar um trabalho, formar e preservar uma representação própria dele, agir de forma controlada, verificar o que fez, aprender algo útil com a experiência e, após perder completamente o contexto de execução do modelo, voltar e continuar sabendo onde estava.**

Quando isso acontecer, o projeto terá deixado de ser uma arquitetura teórica e terá se tornado o primeiro SIMON real.


---

## 30. Stack tecnológica do SIMON v0.1

Esta seção registra as escolhas tecnológicas iniciais do projeto. A seleção segue a Constituição de Engenharia: poucas dependências, componentes substituíveis e nenhuma infraestrutura adicionada antes de resolver um problema real.

### 30.1. Plataforma alvo

O v0.1 será desenvolvido e executado inicialmente em:

```text
Windows 11 x64
CPython 3.14.x
execução nativa, sem WSL ou container obrigatório
```

A primeira implementação será otimizada para o ambiente real de desenvolvimento, não para portabilidade hipotética. Compatibilidade com Linux poderá ser adicionada quando houver necessidade concreta, evitando dependências desnecessárias de APIs exclusivas do Windows no Core.

### 30.2. Linguagem

**Python 3.14.x** será a linguagem principal.

Motivos:

- combina desenvolvimento rápido com bibliotecas maduras para IA, persistência, testes e integração com o sistema operacional;
- permite manter os componentes do SIMON explícitos e inspecionáveis;
- suporta tipagem gradual sem impor uma arquitetura rígida;
- é adequado para orquestração de modelos e ferramentas locais;
- o runtime de modelo permanecerá fora do processo principal, evitando que o Core dependa diretamente de frameworks específicos de inferência.

A versão de desenvolvimento será fixada pelo projeto e registrada no lockfile. Atualizações de patch podem ocorrer depois de testes.

### 30.3. Gerenciamento do projeto e dependências

**uv** será utilizado para:

```text
instalação/control de Python
ambiente virtual
dependências
pyproject.toml
uv.lock
execução de comandos do projeto
```

Não serão usados simultaneamente Poetry, pip-tools, Conda ou outro gerenciador de ambiente no projeto principal.

Princípio:

> Um projeto deve possuir uma única fonte clara para resolução e lock de dependências.

### 30.4. Modelos de dados e validação

**Pydantic v2** será utilizado nos objetos canônicos e principalmente nas fronteiras que recebem dados não confiáveis ou produzidos por modelos.

Usos iniciais:

```text
Canonical Data Model
structured model outputs
Tool inputs
persisted payload validation
configuration validation quando necessário
```

O objetivo não é transformar toda classe Python em `BaseModel`. Tipos internos triviais podem continuar como tipos normais quando não houver benefício concreto em validação ou serialização.

Pydantic também será usado para produzir JSON Schema quando o runtime cognitivo precisar exigir uma saída estruturada do modelo.

### 30.5. Persistência principal

**SQLite**, através do módulo `sqlite3` da biblioteca padrão do Python, será o banco de dados do v0.1.

Não será utilizado ORM inicialmente.

Motivos:

- SIMON é local-first;
- existe apenas uma instalação pessoal no v0.1;
- o modelo de dados inicial é pequeno;
- SQL explícito mantém comportamento e transações visíveis;
- não existe necessidade demonstrada de PostgreSQL ou outro servidor de banco de dados.

A persistência deve usar transações explícitas e integridade referencial onde aplicável.

### 30.6. Migrações de banco

Não será adicionada uma framework de migrations no v0.1.

Migrações serão SQL versionado e pequeno código próprio para aplicar versões em ordem, utilizando o mecanismo `user_version` do SQLite enquanto ele for suficiente.

Estrutura conceitual:

```text
migrations/
    0001_initial.sql
    0002_....sql
```

Se a evolução de schema demonstrar que esse mecanismo se tornou inadequado, uma ferramenta como Alembic poderá ser avaliada nesse momento.

### 30.7. Journal mode do SQLite

O v0.1 não ativará WAL apenas por antecipação.

O modo padrão será mantido enquanto o SIMON possuir um fluxo simples de acesso ao banco. WAL será avaliado quando houver concorrência real entre leitores e escritores ou quando medições mostrarem benefício.

Isso evita complexidade operacional adicional antes de existir necessidade.

### 30.8. Artefatos e dados grandes

Arquivos grandes não devem ser armazenados como BLOB no banco sem necessidade demonstrada.

O padrão inicial será:

```text
SQLite
→ identidade, relações, estado e metadata

filesystem
→ artifacts, outputs, traces grandes e snapshots físicos quando necessário
```

O banco mantém caminho, hash, tipo e proveniência do Artifact quando ele precisar ser referenciado semanticamente.

### 30.9. Runtime de modelos locais

**Ollama** será o primeiro runtime cognitivo do v0.1.

Ele será executado como processo/serviço separado do SIMON.

Fluxo:

```text
SIMON Core
    ↓
Model Provider Adapter
    ↓ HTTP local
Ollama
    ↓
Local Model
```

O Core nunca dependerá de tipos, objetos ou detalhes internos do Ollama.

O adapter inicial deverá expor apenas as operações que o v0.1 realmente utilizar, principalmente geração estruturada e geração textual quando necessária.

### 30.10. Modelo inicial

Nenhum modelo específico faz parte da arquitetura oficial.

O modelo inicial será escolhido por benchmark no hardware real utilizado pelo SIMON.

A escolha deverá considerar pelo menos:

```text
qualidade em structured output
raciocínio
latência
VRAM
estabilidade
context size necessário
```

Trocar de modelo não pode exigir migração da identidade, World, Goals ou Memory.

### 30.11. Provider substituível

A existência de um boundary de Model Provider é justificada desde o v0.1 porque independência de modelo é uma propriedade fundamental do SIMON.

Contudo, será uma abstração pequena.

Não será criado um sistema genérico para dezenas de providers antes de existir um segundo provider real.

Primeiro:

```text
ModelProvider contract
└── OllamaProvider
```

Quando outro runtime for realmente testado:

```text
ModelProvider contract
├── OllamaProvider
└── SecondProvider
```

**llama.cpp server** é um candidato natural para avaliação futura, especialmente quando houver necessidade de controle mais fino de inferência, recursos ou benchmarking do runtime, mas não será dependência obrigatória do v0.1.

### 30.12. HTTP local

**HTTPX**, em modo síncrono, será usado para comunicação entre o SIMON e o runtime local de modelo.

Motivos:

- API simples;
- timeouts explícitos;
- conexão reutilizável via Client;
- possibilidade de migração para async futuramente sem trocar de biblioteca caso concorrência real apareça.

O v0.1 não será assíncrono apenas porque a biblioteca oferece async.

### 30.13. Modelo de concorrência

O Core do v0.1 será **síncrono por padrão**.

Não serão introduzidos inicialmente:

```text
asyncio como arquitetura geral
filas distribuídas
workers externos
message brokers
```

Processos demorados podem ser tratados por `subprocess` e estados explícitos quando a necessidade surgir.

Concorrência será adicionada a partir de casos reais, principalmente quando Executive, Background Jobs e Lab começarem a exigir paralelismo.

### 30.14. Tools locais

As Tools iniciais utilizarão principalmente a biblioteca padrão:

```text
pathlib
shutil
subprocess
os quando necessário
```

Operações de subprocesso devem preferir argumentos estruturados e `shell=False`.

Shell genérico não será o caminho padrão para operações que possam ser realizadas por uma Tool específica e verificável.

### 30.15. Interface inicial

A interface do v0.1 será uma **CLI/REPL simples**.

Não serão adicionados inicialmente:

```text
FastAPI
Flask
Django
Electron
frontend web
GUI framework
```

A biblioteca padrão é suficiente para a primeira interface. Uma UI mais sofisticada só será escolhida depois que o Life Loop estiver comprovado.

### 30.16. Configuração

A configuração inicial deverá utilizar:

```text
pyproject.toml → configuração do projeto e ferramentas
config TOML → configuração persistente do SIMON quando necessário
environment variables → valores dependentes do ambiente ou sensíveis
```

O parser TOML da biblioteca padrão será preferido enquanto suficiente.

Secrets não devem ser gravados em arquivos versionados.

### 30.17. Logging e Observatory inicial

O v0.1 utilizará **logging da biblioteca padrão** e eventos estruturados próprios.

Não serão introduzidos inicialmente:

```text
OpenTelemetry
Prometheus
Grafana
ELK
serviço externo de observabilidade
```

A primeira necessidade é possuir traces e eventos reconstruíveis localmente, não operar infraestrutura de observabilidade distribuída.

Quando útil, eventos operacionais poderão ser serializados em JSONL além da persistência semântica em SQLite.

### 30.18. Testes

**pytest** será o test runner oficial.

Os primeiros testes deverão privilegiar comportamento e invariantes definidos na Specification, especialmente:

```text
restart test
false-completion test
failure test
scope test
memory test
Lab Inbox test
```

Não buscar cobertura percentual alta como objetivo isolado. Testes existem para defender comportamento real e regressões conhecidas.

### 30.19. Lint e formatação

**Ruff** será utilizado como formatter e linter.

Isso evita a combinação de múltiplas ferramentas diferentes para formatação, ordenação de imports e lint básico.

Configuração inicial deve ser pequena. Regras serão adicionadas quando prevenirem problemas reais ou melhorarem consistentemente a legibilidade.

### 30.20. Tipagem estática

**mypy** será usado de maneira gradual.

No v0.1 ele deve proteger principalmente:

```text
Canonical Data Model
component boundaries
persistence contracts
Tool inputs/results
Model Provider contracts
```

Não será habilitado um conjunto extremo de regras apenas para atingir `strict = true` desde o primeiro commit.

### 30.21. Versionamento

**Git** será obrigatório desde o primeiro commit.

O repositório local é a fonte de versionamento do código. Hospedagem remota não é requisito para o v0.1.

Mudanças estruturais importantes devem permanecer rastreáveis por commit, especialmente antes da existência do Lab.

### 30.22. Tecnologias deliberadamente não escolhidas para o v0.1

Não entram sem nova necessidade demonstrada:

```text
LangChain
LangGraph
AutoGen
CrewAI
PydanticAI como framework de agente
SQLAlchemy ORM
Alembic
PostgreSQL
Redis
Chroma
Qdrant
Milvus
Neo4j
Docker obrigatório
Kubernetes
FastAPI
message broker
microservices
OpenTelemetry
vector database
```

A exclusão não significa que sejam tecnologias inadequadas. Significa apenas que nenhuma delas resolve atualmente um problema que justifique seu custo arquitetural no v0.1.

### 30.23. Stack resumida

```text
OS
└── Windows 11 x64

Runtime
└── CPython 3.14.x

Project management
└── uv + pyproject.toml + uv.lock

Data contracts
└── Pydantic v2

Persistence
└── SQLite / sqlite3 + SQL explícito

Local cognition
└── Ollama
    └── modelo selecionado por benchmark

HTTP adapter
└── HTTPX sync

Local Tools
└── Python standard library

Observability
└── logging + structured events + JSONL quando necessário

Tests
└── pytest

Lint / format
└── Ruff

Static typing
└── mypy gradual

Version control
└── Git
```

### 30.24. Regra de revisão tecnológica

Uma escolha tecnológica pode ser substituída quando existir evidência de que ela limita uma capacidade relevante do SIMON.

O processo será:

```text
limitação observada
↓
medição
↓
alternativas
↓
benchmark/protótipo
↓
decisão
```

Não trocar tecnologia apenas por novidade.

### 30.25. Princípio final da stack

> **A stack do SIMON deve ser pequena o suficiente para ser compreendida por inteiro e sólida o suficiente para que a complexidade futura nasça do próprio sistema, não das ferramentas usadas para construí-lo.**
