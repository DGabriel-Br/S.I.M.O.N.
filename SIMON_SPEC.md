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

O primeiro write path operacional expõe uma promoção explícita de uma Experience `CLOSED`. O usuário fornece o significado a preservar, `kind` e `scope`; referências opcionais para Claims e Entities permanecem validadas como proveniência. A criação da Memory e o Event que registra a decisão são atômicos. O Event referencia a Experience e a Memory, sem transformar o Event Log em cópia do conteúdo preservado. Outcomes negativos não são descartados automaticamente, pois falhas podem constituir negative knowledge útil.

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

No corte executável de retomada, a revisão passa a existir no schema 11 como um contador persistente único. Ela avança quando uma mudança de Claim altera a visão atual. Uma substituição via `set_current_claim` conta como uma única mudança semântica, ainda que preserve a Claim anterior como `SUPERSEDED` e crie outra `ACTIVE`. Plans novos persistem `based_on_world_revision`. Plans anteriores ao schema 11 recebem como baseline a revisão materializada no upgrade; o sistema não tenta reconstruir retroativamente uma sequência histórica que nunca foi registrada.

A diferença entre a revisão atual e `based_on_world_revision` é inicialmente informativa. Ela não bloqueia automaticamente o Plan inteiro porque ainda não existem assumptions estruturadas suficientes para determinar que toda mudança do World invalida todo step. Revalidação mais seletiva entra quando dependências reais entre Claims e assumptions exigirem isso.

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

No primeiro corte executável, a CLI curta não mantém uma Experience mutável viva entre comandos. Quando um Goal chega a `COMPLETED` por Verification confirmada, o Core materializa uma Experience `CLOSED` que representa o intervalo causal desde a criação do Goal até `goal.completed`. A unidade referencia Actions, VerificationResults e somente os Events necessários para evidência e marcos de lifecycle. Revisions de Plan são preservadas como referências no Event de fechamento, sem duplicar os Plans dentro da Experience.

Esse corte é compatível com retomada porque a causalidade é reconstruída a partir de estado já persistido. Se um runtime futuro mantiver sessões longas reais, Experiences `ACTIVE/SUSPENDED` podem entrar no fluxo quando houver benefício concreto, sem invalidar as Experiences materializadas no fechamento.

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

No primeiro corte executável, `simon resume [goal_id]` reconstrói esse estado diretamente dos nove objetos canônicos e da `world_revision`. O Core recupera Goals abertos sem inventar foco quando houver mais de um, seleciona automaticamente apenas quando existe um único Goal aberto ou quando o usuário fornece o ID, recupera o Plan ativo ou mais recente, Actions de toda a linhagem de revisões com a Verification mais recente, readiness determinístico, última Experience e Memories relevantes por proveniência ou correspondência textual simples.

Actions encontradas como `RUNNING` no startup são reconciliadas antes da reconstrução para `INTERRUPTED`, preservando a regra de que um restart não implica sucesso nem falha do efeito externo. A retomada não recria prompts, hidden state ou histórico de chat do modelo; a continuação precisa ser explicável apenas pelo estado persistido.

O primeiro cenário integrado ponta a ponta validou esse contrato atravessando Goal, Plan, `process.run`, `cognition.analyze`, confirmação epistemológica, restart em um novo processo, `file.patch`, reexecução, conclusão de Plan e Goal, Experience, promoção explícita de Memory e um segundo restart. A fronteira cognitiva usa um `ModelProvider` determinístico no teste para isolar a integração do Core da variabilidade do modelo, enquanto persistência, subprocesso, arquivo e processos de restart são reais.

Esse teste revelou uma lacuna somente na apresentação da retomada: quando o Plan não possuía step `READY`, a CLI escondia o primeiro step ainda pendente embora o readiness já contivesse seus blockers. `resume` passa a expor esse step, sua capability e seus blockers. Isso não muda Planner nem readiness; apenas torna o estado persistido suficiente também para o usuário saber por que a continuação está bloqueada.

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
WAITING
COMPLETED
FAILED
BLOCKED
DENIED
INTERRUPTED
CANCELLED
```

Significado:

- `PENDING`: Action criada, ainda não iniciada;
- `RUNNING`: execução iniciou e depende do runtime local para continuar;
- `WAITING`: a tentativa foi iniciada, mas aguarda uma condição externa explícita, como resposta do usuário;
- `COMPLETED`: o executor terminou a operação e produziu um resultado;
- `FAILED`: execução terminou com falha concreta;
- `BLOCKED`: falta uma precondition, recurso ou condição externa;
- `DENIED`: Policy não autorizou a execução;
- `INTERRUPTED`: execução perdeu continuidade antes de obter resultado terminal confiável;
- `CANCELLED`: foi encerrada antes da execução ou durante uma operação cancelável.

Fluxo principal:

```text
PENDING ─► RUNNING ─► COMPLETED
   │          │
   │          ├─────► WAITING ─► COMPLETED
   │          │          ├─────► BLOCKED
   │          │          └─────► CANCELLED
   │          ├─────► FAILED
   │          ├─────► BLOCKED
   │          ├─────► INTERRUPTED
   │          └─────► CANCELLED
   │
   ├───────────────► WAITING
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
Actions PENDING / RUNNING / WAITING
Experiences ACTIVE / SUSPENDED
```

Regras iniciais:

1. `RUNNING` encontrado após perda do runtime é tratado como execução potencialmente interrompida e precisa ser reconciliado antes de retry.
2. `PENDING` pode ser reavaliado pelo Planner/Policy antes da execução.
3. `WAITING` preserva a dependência externa através do reinício e não é convertido em `INTERRUPTED`.
4. `ACTIVE Experience` pode ser convertida para `SUSPENDED` durante recovery quando sua continuidade operacional foi perdida.
5. Goal não é cancelado ou falhado apenas porque o processo reiniciou.
6. World e Memory são reconstruídos a partir do estado persistido, não do contexto anterior do modelo.

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

## 31. Primeiro Model Provider executável

O primeiro runtime cognitivo conectado ao v0.1 é o Ollama, mas o restante do SIMON não depende de sua API diretamente.

A fronteira mínima é `ModelProvider`:

```text
SIMON / Cognition
      ↓
ModelProvider
      ↓
OllamaProvider
      ↓
Ollama REST API
```

O contrato inicial suporta apenas as necessidades já existentes:

```text
listar modelos disponíveis
gerar uma resposta estruturada por JSON Schema
```

Não entram ainda:

```text
streaming
tool calling pelo modelo
roteamento entre modelos
fallback automático
multi-model ensemble
histórico de chat persistido no provider
```

### 31.1. Structured output

Uma resposta que será consumida pelo sistema deve possuir contrato explícito quando o caso exigir estrutura.

O primeiro adapter utiliza modelos Pydantic para:

```text
gerar JSON Schema
↓
enviar o schema ao runtime
↓
receber JSON textual
↓
validar novamente localmente
↓
aceitar ou rejeitar o resultado
```

O fato de o runtime declarar suporte a structured output não elimina a validação local.

### 31.2. Independência do runtime

Ollama é o primeiro provider, não a identidade cognitiva do SIMON.

Nenhum Goal, Plan, Memory, Experience ou componente persistente deve depender de tipos específicos do Ollama.

Trocar o runtime futuramente deve exigir um novo adapter, não uma reconstrução do Core.

### 31.3. Seleção do primeiro modelo

Nenhum modelo específico é hardcoded nesta etapa.

O usuário escolhe explicitamente o modelo usado no diagnóstico. A seleção automática só será criada depois que houver pelo menos duas alternativas reais ou dados de desempenho suficientes para justificar um Router.

### 31.4. Falhas tratadas no primeiro adapter

O adapter trata apenas falhas concretas desta fronteira:

```text
runtime inacessível
timeout HTTP
erro HTTP retornado pelo runtime
JSON de resposta inválido
resposta incompatível com o schema solicitado
```

Não serão criadas antecipadamente estratégias complexas de retry, fallback ou circuit breaker.

### 31.5. Diagnóstico

O CLI passa a oferecer:

```text
simon model-check
simon model-test --model <modelo_instalado>
```

`model-check` verifica a API local e lista modelos instalados.

`model-test` realiza uma chamada estruturada mínima. Ele existe para provar a integração real antes da construção de Cognition.

## 32. Primeira função cognitiva executável

Com o Model Provider validado contra um modelo local real, o primeiro uso cognitivo do v0.1 é a interpretação estruturada de uma entrada do usuário.

A fronteira permanece pequena:

```text
texto do usuário
      ↓
interpret_user_input
      ↓
ModelProvider
      ↓
UserInputInterpretation
```

### 32.1. Saída mínima

A primeira interpretação contém apenas informações que já possuem uso concreto:

```text
intent
objective
entity_mentions
ambiguities
```

`intent` usa as categorias:

```text
QUESTION
REQUEST
INFORM
CONTINUE
UNKNOWN
```

Uma `entity_mention` ainda não é uma Entity canônica do World. Ela representa apenas um termo explicitamente detectado na mensagem. Entity Resolution será criada quando existir necessidade de transformar essas menções em identidades persistentes.

### 32.2. Limite de autoridade

Interpretar uma mensagem não concede autoridade para agir.

A primeira função cognitiva:

```text
não cria Goal
não cria Plan
não executa Tool
não escreve Claim no World
```

Ela produz uma representação estruturada que outros componentes poderão consumir posteriormente.

### 32.3. Proveniência operacional

Uma execução real de `simon interpret` gera dois Events correlacionados pelo mesmo `trace_id`:

```text
user.input.received
cognition.interpretation.completed
```

Em caso de falha cognitiva:

```text
cognition.interpretation.failed
```

O resultado registra também os metadados de inferência disponibilizados pelo provider, como modelo, tokens e duração quando presentes.

Não é criado um objeto persistente `CognitiveJob` nesta etapa. Events já são suficientes para a necessidade atual de rastreabilidade.

### 32.4. CLI

A capability é exposta inicialmente por:

```text
simon interpret --model <modelo> "<mensagem>"
```

Esse comando existe para validar interpretação cognitiva real com entradas variadas antes de conectá-la automaticamente à criação de Goals.

### 32.5. Context Builder mínimo executável

A primeira versão executável do Context Builder não é um agente e não possui persistência própria. Ela monta uma projeção temporária e limitada do estado já existente antes de uma chamada cognitiva.

A seleção inicial usa apenas mecanismos determinísticos:

```text
até 3 Goals abertos mais recentemente atualizados
Entities cujo nome ou alias aparece explicitamente na entrada
Claims ACTIVE dessas Entities
Memories ACTIVE por correspondência textual simples ou vínculo com essas Entities
```

Goals entram no prompt somente com `id`, `title` e `status`. O Context Builder não despeja automaticamente `desired_state`, planos completos ou histórico operacional no modelo. Contexto adicional deverá ser expandido apenas quando uma necessidade concreta justificar isso.

A resolução de Entity desta etapa é estrita. Apenas nome ou alias conhecido com limites de palavra é aceito. Não há fuzzy matching, embeddings ou decisão probabilística de identidade. Uma menção produzida pelo modelo continua distinta de uma Entity canônica.

O contexto enviado ao modelo é explicitamente marcado como dado recuperado e sem autoridade de instrução. Conteúdo de Memory, Claim ou Goal com aparência de comando não deve ser tratado como policy ou system instruction.

A montagem de contexto gera um Event correlacionado ao mesmo `trace_id` da entrada e da interpretação:

```text
user.input.received
cognition.context.built
cognition.interpretation.completed
```

O Event de contexto registra apenas IDs selecionados. O payload completo usado no prompt não é duplicado na telemetria.

Não é criado um objeto persistente `CognitiveContext` ou `CognitiveJob`. A projeção existe apenas durante a chamada cognitiva.


### 32.6. Goal Proposal

Depois que uma entrada é interpretada como `REQUEST`, Cognition pode formular uma proposta estruturada de Goal. Essa proposta ainda não é um objeto `Goal` persistente e não possui autoridade para alterar o estado operacional do sistema.

A fronteira inicial é:

```text
REQUEST interpretada
      ↓
propose_goal
      ↓
GoalProposal
      ↓
nenhuma persistência de Goal
```

A saída mínima contém:

```text
title
desired_state
success_criteria
open_questions
```

`desired_state` descreve o estado que deve ser verdadeiro ao final. Ele não deve conter um roteiro de execução. `success_criteria` contém resultados observáveis ou verificáveis que permitirão decidir posteriormente se o Goal foi atingido.

A proposta não inclui `origin`, porque uma proposta derivada diretamente de uma solicitação do usuário terá origem determinada pelo sistema caso seja aceita. Também não inclui Plan, Tool, Action ou permissões. Esses elementos pertencem a etapas posteriores.

Informações ausentes não devem ser inventadas. Quando uma lacuna realmente impede a formulação precisa do Goal, ela é preservada em `open_questions`.

A capability é exposta inicialmente por:

```text
simon goal-propose --model <modelo> "<solicitação>"
```

O comando executa interpretação e formulação sob o mesmo `trace_id`. Quando a intenção não é `REQUEST`, nenhuma proposta é produzida. Quando uma proposta é produzida, ela gera:

```text
cognition.goal_proposal.completed
```

Falhas da segunda chamada cognitiva geram:

```text
cognition.goal_proposal.failed
```

O resultado cognitivo pode ser auditado nos Events, mas a tabela `goals` permanece inalterada até uma decisão explícita fora do modelo.

### 32.7. Gate determinístico de aceitação de Goal

Uma proposta cognitiva somente se torna um Goal operacional quando o usuário aceita explicitamente o Event imutável que contém aquela proposta. O modelo não participa da decisão de aceitação e não é chamado novamente durante a persistência.

A fronteira executável é:

```text
cognition.goal_proposal.completed
        ↓
ID imutável do Event
        ↓
decisão explícita do usuário
        ↓
simon goal-accept <proposal_event_id>
        ↓
Goal(origin=USER, status=ACTIVE)
```

O gate lê exatamente `title`, `desired_state` e `success_criteria` armazenados no Event de proposta. Para encaixar o contrato textual cognitivo no modelo persistente do v0.1, a representação inicial é: 

```text
desired_state = {description: <texto proposto>}
success_criteria = ({description: <critério 1>}, ...)
```

`origin` não é herdado do modelo. Para uma proposta derivada diretamente de uma solicitação do usuário, o Core determina `origin=USER`. O Goal nasce `ACTIVE` pelo lifecycle já existente.

A aceitação produz um Event separado:

```text
goal.proposal.accepted
```

Esse Event referencia `goal_id`, `proposal_event_id`, o `trace_id` original da proposta quando disponível, o modelo que produziu a proposta e as `open_questions` ainda não resolvidas. A aceitação possui seu próprio `trace_id`, porque ocorre em uma nova decisão operacional, enquanto a proveniência aponta de volta para o trace cognitivo original.

As `open_questions` não impedem automaticamente a criação do Goal. Elas representam desconhecidos que poderão exigir investigação ou ações epistêmicas durante planejamento. O gate preserva essas questões, mas não as responde.

Aceitar o mesmo `proposal_event_id` mais de uma vez é idempotente. O sistema retorna o Goal já criado e não duplica nem o Goal nem o Event de aceitação. A escrita do Goal e do Event de proveniência acontece na mesma transação SQLite para evitar um Goal autorizado sem rastro de aceitação.

O comando rejeita Events inexistentes, Events de outro tipo e propostas que não respeitem o contrato `GoalProposal`. Nenhum novo objeto persistente ou migration é criado nesta etapa; o SQLite permanece no schema 9.

### 32.8. Primeira proposta cognitiva de Plan

Depois que um Goal já possui autoridade operacional, o Planner pode produzir uma estratégia estruturada sem executar ações e sem persistir automaticamente um `Plan`. Neste primeiro corte, o Planner continua sendo uma função cognitiva com validação determinística ao redor, conforme o escopo v0.1.

A fronteira executável é:

```text
Goal autorizado
      ↓
contexto determinístico + questões em aberto
      ↓
propose_plan
      ↓
PlanProposal
      ↓
nenhuma Action e nenhuma persistência de Plan
```

A saída temporária contém:

```text
summary
steps[]:
  id
  description
  kind = EPISTEMIC | WORLD
  depends_on[]
  preconditions[]
  capability
  verification
open_questions[]
```

`EPISTEMIC` representa passos cujo efeito principal é obter informação. `WORLD` representa passos que pretendem modificar o estado externo. A distinção não concede autoridade de execução; ela apenas torna explícita a natureza da estratégia proposta.

`capability` é abstrata. O Planner descreve o que precisa ser capaz de fazer, mas não escolhe Tool concreta, comando de shell ou implementação. Skill Resolver e Tool Gateway permanecem fora desta etapa.

Questões preservadas em `goal.proposal.accepted` são recuperadas como entrada do planejamento. Quando uma lacuna puder ser resolvida operacionalmente, o Planner deve produzir um passo `EPISTEMIC` em vez de inventar a resposta. Questões ainda não resolvidas permanecem em `open_questions`.

A proposta possui no máximo seis passos. IDs precisam ser únicos e dependências só podem apontar para passos anteriores. Cada passo declara precondições relevantes e uma forma observável de verificação. Essas invariantes são validadas pelo contrato estruturado, não apenas pelo prompt.

O comando inicial é:

```text
simon plan-propose --model <modelo> <goal_id>
```

A seleção de contexto produz `cognition.context.built` com `purpose=plan` e `goal_id`. Uma proposta válida produz:

```text
cognition.plan_proposal.completed
```

Falhas produzem:

```text
cognition.plan_proposal.failed
```

Todos os Events da chamada compartilham o mesmo `trace_id` e referenciam o Goal planejado. O Event de proposta preserva o modelo, o objeto estruturado, métricas de inferência e as questões em aberto recebidas da proveniência do Goal.

Nenhum novo objeto persistente ou migration é criado nesta etapa. A tabela `plans` permanece inalterada até a futura materialização determinística da proposta e o SQLite permanece no schema 9.

### 32.9. Materialização determinística de PlanProposal

Uma `PlanProposal` validada pode ser transformada no objeto persistente `Plan` sem uma nova decisão do modelo e sem introduzir um segundo gate de autoridade sobre os meios instrumentais de um Goal já autorizado.

A materialização usa exatamente o Event `cognition.plan_proposal.completed` selecionado como fonte. Os passos estruturados da proposta são preservados no `steps` do Plan, incluindo `kind`, `depends_on`, `preconditions`, `capability` e `verification`. O resumo e as questões ainda abertas permanecem na proveniência do Event de materialização, em vez de criar novos campos persistentes antes de existir necessidade real.

A operação deve ser idempotente por `proposal_event_id`: repetir a materialização da mesma proposta retorna o mesmo Plan. Uma proposta diferente para o mesmo Goal cria uma nova revisão e marca o Plan ativo anterior como `SUPERSEDED`, preservando o histórico de estratégias.

A criação da revisão e o Event `plan.proposal.materialized` pertencem à mesma transação SQLite. Nenhuma Action é criada nesta etapa. Preconditions continuam sendo requisitos a verificar antes da execução, não fatos presumidos como verdadeiros.

### 32.10. Avaliação determinística de prontidão de steps

Antes de transformar um step persistido em `Action`, o Core precisa demonstrar que o step está operacionalmente elegível. Essa decisão não pertence ao modelo e não exige novo objeto persistente.

A primeira fronteira executável é:

```text
Goal ACTIVE
   ↓
Plan ACTIVE
   ↓
steps persistidos
   ↓
evaluate_active_plan
   ↓
READY | BLOCKED | IN_PROGRESS | VERIFIED
   ↓
nenhuma Action criada
```

A avaliação considera apenas fatos que o sistema consegue demonstrar. Dependências entre steps só são satisfeitas quando existe uma `Action` `COMPLETED` para o step dependência e ao menos um `VerificationResult` `VERIFIED` associado àquela Action. `COMPLETED` sem Verification não é suficiente para liberar o próximo step.

Um step com `Action` `PENDING`, `RUNNING` ou `WAITING` é `IN_PROGRESS` e não recebe uma tentativa concorrente. Um step já demonstrado por Action verificada é `VERIFIED` e deixa de competir como próximo trabalho.

Falhas anteriores não geram retry silencioso. `FAILED`, `BLOCKED`, `DENIED`, `INTERRUPTED` e `CANCELLED` produzem um bloqueador `PREVIOUS_ATTEMPT_REQUIRES_REVIEW` até que uma política de retry ou replanning seja implementada.

Preconditions continuam sendo requisitos, não fatos. Enquanto o v0.1 não possuir um resolvedor que as conecte ao World ou a evidência observável, cada precondition textual permanece `PRECONDITION_UNRESOLVED`. O sistema não assume que uma frase declarada pelo Planner é verdadeira.

Da mesma forma, `capability` continua sendo um requisito abstrato. O avaliador recebe um conjunto explícito de capabilities realmente disponíveis. Se a capability do step não estiver nesse conjunto, o step recebe `CAPABILITY_UNAVAILABLE`. O runtime inicial fornece conjunto vazio porque nenhuma capability de Tool execution foi registrada ainda.

A ordem do Plan só desempata steps que já estão `READY`; um step bloqueado não impede que outro step independente e comprovadamente pronto seja selecionado. O primeiro `READY` na ordem persistida é retornado como `next_step`.

O comando diagnóstico inicial é:

```text
simon plan-next <goal_id>
```

Ele resolve o Plan `ACTIVE`, avalia todos os steps, mostra bloqueadores e registra `plan.readiness.evaluated` com IDs, estados e categorias de bloqueio. O Event não duplica o conteúdo completo do Plan e nenhuma `Action` é criada.

Nenhuma migration é necessária. O SQLite permanece no schema 9. Essa etapa torna observável a fronteira entre planejamento e ação e impede que JSON estruturalmente válido seja confundido com trabalho executável.



### 32.11. Catálogo mínimo de capabilities e primeira capability disponível

O primeiro teste real de `plan-next` demonstrou que capability em linguagem natural não é uma interface estável entre Planner e runtime. Descrições como `Consultar logs ou solicitar ao usuário...` não podem ser comparadas deterministicamente com capacidades executáveis sem introduzir fuzzy matching ou interpretação adicional.

O v0.1 passa a usar um catálogo pequeno de IDs estáveis na saída do Planner:

```text
user.ask
file.read
process.run
logs.read
cognition.analyze
unknown
```

`unknown` existe para representar uma necessidade ainda não coberta pelo catálogo sem inventar uma Tool. Quando usado, `capability_detail` deve explicar a necessidade. O catálogo é enviado ao Planner como dado estruturado, incluindo quais capabilities estão disponíveis naquele runtime.

Neste estágio somente `user.ask` é considerada disponível. Ela significa solicitar ao usuário informação, confirmação ou contexto ausente e aguardar uma resposta. A existência dessa capability não concede acesso a arquivos, logs, processos ou outras fontes.

Para `user.ask`, preconditions textuais como `o usuário possui a informação` não bloqueiam readiness. A pergunta é justamente o mecanismo seguro para descobrir se o usuário consegue fornecer o dado. Preconditions de todas as demais capabilities continuam não resolvidas até que exista um mecanismo baseado em World, Claims ou Verification para demonstrá-las.

Plans persistidos antes do catálogo continuam válidos historicamente. Capabilities antigas em texto livre não são convertidas por similaridade e permanecem `CAPABILITY_UNAVAILABLE`. A correção ocorre através de uma nova `PlanProposal` e nova revisão de Plan, preservando a estratégia anterior como histórico.

`plan.readiness.evaluated` passa a registrar também `available_capabilities`, tornando reproduzível por que um step foi considerado pronto ou bloqueado naquele momento. Nenhuma Action é criada nesta etapa e o SQLite permanece no schema 9.


### 32.12. Primeira Action de interação humana: `user.ask`

O primeiro step realmente executável do v0.1 é uma interação com o usuário. A capability `user.ask` não acessa filesystem, shell, rede ou logs; ela apenas materializa uma solicitação já presente em um Plan autorizado e aguarda uma resposta humana.

A fronteira operacional inicial é:

```text
Plan ACTIVE
   ↓
step user.ask READY
   ↓
plan-ask
   ↓
Action(kind=user.ask, status=WAITING)
   ↓
user.question.asked
   ↓
resposta humana
   ↓
action-answer
   ↓
user.response.received
   ↓
Action COMPLETED
   ↓
Verification ainda pendente
```

`WAITING` passa a fazer parte do lifecycle persistente de `Action`. Esse estado representa uma tentativa que já foi iniciada, mas cuja continuidade depende de uma resposta externa. Ele não é terminal e não representa CPU, Tool ou processo local atualmente em execução.

Por isso, o recovery de startup continua convertendo somente Actions `RUNNING` para `INTERRUPTED`. Uma Action `WAITING` sobrevive ao encerramento e reinício do SIMON sem mudança de estado. O avaliador de readiness a considera `IN_PROGRESS`, impedindo que o mesmo step seja iniciado novamente.

A transição inicial suportada é `PENDING → WAITING`; `started_at` é preenchido quando a pergunta é emitida. Uma resposta válida permite `WAITING → COMPLETED`. O resultado reportado da Action referencia o Event que preserva a resposta, em vez de duplicar o texto bruto em múltiplos objetos.

O comando inicial é:

```text
simon plan-ask <goal_id>
```

Ele avalia o Plan ativo, exige que o próximo step `READY` utilize exatamente `user.ask`, cria a Action, registra `user.question.asked` e a coloca em `WAITING`. Se o mesmo Plan já possui uma `user.ask` em espera, o comando é idempotente operacionalmente e devolve a Action existente em vez de abrir outra pergunta concorrente.

A resposta é registrada por:

```text
simon action-answer <action_id> <resposta>
```

A operação exige Action `user.ask` em `WAITING`, grava `user.response.received` com `source=user` e conclui a Action na mesma transação. A Action preserva apenas `response_event_id` em `reported_result`.

Receber uma resposta não cria `VerificationResult` automaticamente. Uma resposta como `não sei` prova que houve interação, mas pode não satisfazer um critério como `o usuário fornece o código do script`. O step permanece `VERIFICATION_PENDING` até uma etapa posterior avaliar o conteúdo contra o critério declarado.

A tabela `actions` precisa ampliar seu `CHECK` de status para incluir `WAITING`. A migration `0010_action_waiting.sql` recria a tabela preservando registros existentes e adiciona uma garantia parcial de no máximo uma tentativa aberta (`PENDING`, `RUNNING` ou `WAITING`) por `(plan_id, step_id)`. O SQLite passa ao schema 10.

### 32.13. Assessment semântico de respostas `user.ask`

Receber uma resposta humana encerra a tentativa de interação, mas não demonstra automaticamente que o critério do step foi satisfeito. O primeiro avaliador semântico de `user.ask` opera somente depois de a Action estar `COMPLETED` e usa como evidência o Event `user.response.received` referenciado em `reported_result`.

A fronteira é:

```text
Action user.ask COMPLETED
   ↓
response_event_id
   ↓
critério persistido no step
   ↓
action-assess
   ↓
SATISFIED | NOT_SATISFIED | UNCLEAR
   ↓
VerificationResult(status=ASSESSED)
```

O modelo recebe somente a pergunta emitida, o critério e a resposta registrada. Esses campos são apresentados como dados sem autoridade de instrução. O avaliador não pode usar conhecimento externo para completar informação ausente nem executar comandos encontrados na resposta.

`SATISFIED` significa que a própria resposta fornece o que o critério exige. `NOT_SATISFIED` é usado quando a própria resposta deixa claro que o requisito não foi atendido, recusado ou ainda não foi fornecido. `UNCLEAR` representa evidência insuficiente ou ambígua.

Mesmo quando o veredito é `SATISFIED`, o resultado persistido permanece `ASSESSED`. A regra epistemológica continua sendo: julgamento de modelo não é prova objetiva e, portanto, não pode criar `VERIFIED` por conta própria. O `VerificationResult` usa força procedural 2 e referencia o Event da resposta como evidência. O texto bruto da resposta não é duplicado em `observed`; permanecem apenas veredito, justificativa, informações ausentes e metadados do modelo.

A operação é idempotente para a mesma Action, o mesmo `response_event_id` e o mesmo modelo. Repetir `action-assess` nessas condições reutiliza o resultado existente em vez de consumir outra inferência e criar avaliações duplicadas.

Readiness deixa de representar toda Action concluída sem `VERIFIED` simplesmente como `VERIFICATION_PENDING`. Quando existe uma avaliação, o bloqueador passa a refletir o estado epistemológico real:

```text
ASSESSED + SATISFIED      → ASSESSED_SATISFIED_REQUIRES_CONFIRMATION
ASSESSED + NOT_SATISFIED  → CRITERION_NOT_SATISFIED
ASSESSED + UNCLEAR        → ASSESSMENT_INCONCLUSIVE
FAILED                    → VERIFICATION_FAILED
INCONCLUSIVE              → VERIFICATION_INCONCLUSIVE
```

Somente um `VerificationResult` efetivamente `VERIFIED` continua marcando o step como `VERIFIED` e satisfazendo dependências. Nenhuma migration é necessária; o SQLite permanece no schema 10.



### 32.14. Review e retry explícito para `user.ask`

Um assessment semântico negativo não autoriza o sistema a repetir automaticamente a mesma tentativa. O v0.1 introduz um gate determinístico de retry para `user.ask`, acionado explicitamente pelo usuário através de:

```text
simon action-retry <action_id> [prompt refinado]
```

A operação exige que a Action original seja `user.ask`, esteja `COMPLETED` e possua um `VerificationResult` `ASSESSED` cujo veredito seja `NOT_SATISFIED` ou `UNCLEAR`. `SATISFIED` pertence ao fluxo separado de confirmação e não pode ser convertido em retry por conveniência.

Retry não altera a Action anterior. Uma nova Action é criada para o mesmo `(goal_id, plan_id, step_id)` e entra em `WAITING`, preservando a tentativa anterior como histórico. A nova Action registra em `input_data`:

```text
retry_of_action_id
review_verification_id
retry_authorization_event_id
```

A decisão explícita produz `action.retry.authorized` com `source=user`. A emissão da nova pergunta produz outro `user.question.asked` no mesmo trace operacional. A criação da Action, a transição para `WAITING` e os dois Events pertencem à mesma transação SQLite.

Por padrão o prompt anterior é reutilizado. Um texto refinado pode ser fornecido explicitamente no comando, permitindo corrigir uma pergunta ruim sem alterar retroativamente o Plan nem a tentativa anterior. O critério de Verification do step é preservado.

A operação é idempotente enquanto o retry correspondente ainda está `WAITING`: repetir a autorização para a mesma Action anterior devolve a tentativa já aberta. Se uma tentativa posterior já foi concluída, a Action antiga não pode ser usada novamente como origem de retry; somente a tentativa mais recente daquele step pode ser revisada. Isso evita bifurcações silenciosas na linhagem causal.

O sistema continua permitindo apenas uma `user.ask` em `WAITING` por Plan neste corte, evitando perguntas concorrentes ao usuário. Nenhuma inferência é necessária para autorizar o retry, nenhum `VerificationResult` novo é criado nessa operação e nenhuma migration adicional é necessária. O SQLite permanece no schema 10.

### 32.15. Confirmação explícita de assessment positivo

Um `VerificationResult(status=ASSESSED)` com veredito `SATISFIED` continua sendo apenas julgamento cognitivo. O modelo não pode promover sua própria avaliação para `VERIFIED`. O v0.1 introduz um gate explícito acionado por:

```text
simon verification-confirm <assessment_verification_id>
```

A operação aceita somente assessments de `ACTION` produzidos pelo fluxo `user.ask.semantic` e cujo veredito persistido seja exatamente `SATISFIED`. `NOT_SATISFIED` e `UNCLEAR` permanecem nos fluxos de review e retry. Assessments de outro tipo, VerificationResults que não estejam em `ASSESSED` e Actions que não sejam `user.ask COMPLETED` são rejeitados.

A confirmação não modifica o assessment original. Ela registra um Event imutável:

```text
verification.assessment.confirmed
source = user
```

e cria um novo `VerificationResult` para a mesma Action com:

```text
status = VERIFIED
strength = 3
verification_type = user.ask.assessment_confirmation
confirmed_assessment_id = <assessment selecionado>
confirmed_by = user
```

Os critérios são copiados exatamente do assessment confirmado. A evidência da nova Verification preserva os Events já usados pelo assessment, incluindo `user.response.received`, e acrescenta o Event de confirmação explícita. Dessa forma, a promoção mantém a linhagem entre evidência original, julgamento cognitivo e decisão de autoridade.

A criação do Event de confirmação e do `VerificationResult` `VERIFIED` ocorre na mesma transação SQLite. A operação é idempotente por `assessment_verification_id`: repetir a confirmação recupera a mesma Verification sem criar Events ou provas duplicadas.

Para evitar promover evidência obsoleta após uma nova tentativa, somente a tentativa mais recente do `(plan_id, step_id)` pode ser confirmada. O gate não chama o modelo e não altera Goal, Plan ou Action.

Depois de existir uma Verification `VERIFIED`, o avaliador de readiness considera aquela Action suficiente para marcar o step como `VERIFIED`. A partir desse ponto, dependências que apontem para o step podem ser liberadas. Nenhuma migration adicional é necessária; o SQLite permanece no schema 10.



### 32.16. Conclusão determinística de Plan

Um Plan não é considerado concluído apenas porque não existe outro step `READY`. Ausência de próximo passo pode significar bloqueio, espera, capability indisponível ou verificação pendente. A conclusão do Plan exige uma condição positiva e verificável: todos os steps persistidos precisam estar em estado operacional `VERIFIED`.

No v0.1, todos os steps presentes em `Plan.steps` são obrigatórios. Não existe ainda semântica de step opcional, branch condicional ou quorum parcial. A operação explícita é:

```text
simon plan-complete <goal_id>
```

A fronteira é:

```text
Plan ACTIVE
   ↓
todos os steps VERIFIED
   ↓
revalidação transacional das Actions e VerificationResults
   ↓
Plan COMPLETED
   ↓
plan.completed
   ↓
Goal continua ACTIVE
```

A avaliação preliminar reutiliza a mesma semântica de readiness. Para cada step deve existir uma Action `COMPLETED` sustentada por ao menos um `VerificationResult(status=VERIFIED)`. `ASSESSED`, `INCONCLUSIVE`, `FAILED`, Action concluída sem Verification e tentativa em andamento não satisfazem o gate.

Antes da transição, a condição é revalidada dentro de uma transação `BEGIN IMMEDIATE`. O Plan ativo precisa continuar sendo a mesma revisão observada, o Goal precisa continuar `ACTIVE` e cada step precisa continuar possuindo evidência `VERIFIED`. Somente então o Plan transita de `ACTIVE` para `COMPLETED`.

Na mesma transação é registrado o Event imutável:

```text
plan.completed
source = system
```

O payload preserva `plan_id`, revisão, `verified_step_ids`, `verified_action_ids` e o fato de que o Goal permaneceu `ACTIVE`. Se o Event não puder ser persistido, a transição do Plan é revertida.

A operação é idempotente. Se o Goal não possui mais Plan `ACTIVE`, mas existe um `plan.completed` válido associado ao Plan já `COMPLETED`, repetir o comando recupera o mesmo receipt sem criar novo Event nem alterar timestamps.

Plan completion permanece estritamente separado de Goal completion. Executar e verificar todos os passos prova que a estratégia registrada terminou conforme seus critérios locais. Isso não prova, por si só, que o `desired_state` do Goal se tornou verdadeiro. A futura conclusão de Goal precisa de Verification no nível `GOAL`, com seus próprios critérios e evidências. Nenhuma migration adicional é necessária; o SQLite permanece no schema 10.

### 32.17. Assessment semântico no nível de Goal

Plan `COMPLETED` não promove Goal automaticamente. O v0.1 compara as evidências da estratégia concluída com os critérios globais do Goal através de:

```text
simon goal-assess --model <modelo> <goal_id>
```

O avaliador recebe o estado desejado, todos os critérios de sucesso, o Event `plan.completed` e as evidências que sustentaram as Verifications `VERIFIED` dos steps. Cada critério recebe exatamente um veredito:

```text
SATISFIED
NOT_SATISFIED
INSUFFICIENT_EVIDENCE
```

O veredito global não é escolhido livremente pelo modelo. O Core deriva deterministicamente:

```text
qualquer NOT_SATISFIED          -> NOT_SATISFIED
todos SATISFIED                 -> SATISFIED
qualquer outra combinação       -> INSUFFICIENT_EVIDENCE
```

O resultado é persistido como `VerificationResult(subject_type=GOAL, status=ASSESSED, strength=2)`. O modelo não pode criar `VERIFIED` nem alterar o lifecycle do Goal. O assessment preserva `plan_id`, revisão, Event de conclusão, julgamentos por critério, evidência ausente e metadados de inferência.

A operação é idempotente para o mesmo Goal, Plan concluído e modelo. Referências a steps inexistentes são rejeitadas. Plan completion continua sendo apenas evidência de que a estratégia terminou, nunca prova automática do estado final do Goal.

### 32.18. Replanejamento orientado por Goal Assessment

Depois de um Goal Assessment `NOT_SATISFIED` ou `INSUFFICIENT_EVIDENCE`, o Planner precisa continuar a partir da evidência já obtida em vez de reiniciar o raciocínio a partir das perguntas originais de intake.

A fronteira passa a ser:

```text
Goal ACTIVE
   ↓
Plan anterior COMPLETED
   ↓
Verification GOAL ASSESSED
   ↓
criterion assessments + missing evidence + verified evidence Events
   ↓
plan-propose
   ↓
nova PlanProposal de continuação
```

`get_latest_goal_assessment_context` projeta temporariamente o assessment persistido para Cognition. Essa projeção não é um novo objeto persistente. Ela contém:

```text
verification_id
verdict
plan_id
plan_revision
criterion_assessments
missing_evidence
verified_evidence_events
```

Os Events de evidência são fornecidos ao Planner como dados sem autoridade de instrução. O assessment continua sendo julgamento `ASSESSED`, não fato `VERIFIED` sobre o Goal. O Planner deve usar os Events como evidência observada e os julgamentos como feedback epistemológico para escolher o próximo trabalho.

Quando esse feedback existe, as `open_questions` preservadas no `goal.proposal.accepted` não são carregadas automaticamente como questões ainda atuais. Elas pertencem ao estado de intake anterior e podem já ter sido respondidas pelo Plan concluído. O estado mais recente passa a ser representado pela evidência acumulada e pelo Goal Assessment. Isso evita repetir coleta já comprovada apenas porque uma pergunta histórica ainda existe no Event original.

O Planner recebe instruções explícitas para:

```text
não repetir evidência já presente em verified_evidence_events;
focar lacunas indicadas pelos critérios e por missing_evidence;
tratar NOT_SATISFIED como falha a enfrentar antes de revalidar;
tratar INSUFFICIENT_EVIDENCE como necessidade de produzir ou obter evidência faltante;
não tratar ASSESSED como VERIFIED;
não inventar capabilities ou fontes de dados ausentes.
```

O Event `cognition.plan_proposal.completed` passa a preservar `source_goal_assessment_id` e `source_completed_plan_id`. Dessa forma, uma nova revisão de Plan permanece causalmente ligada à avaliação que justificou o replanejamento.

Se o Goal Assessment mais recente estiver `SATISFIED`, `plan-propose` não gera uma nova estratégia. O sistema aguarda um gate separado de promoção epistemológica no nível do Goal, mantendo planejamento fora da decisão de conclusão do objetivo.

Nenhuma migration é necessária. O SQLite permanece no schema 10.

### 32.19. Guarda causal contra mudanças de estado pressupostas

> Nota histórica: esta guarda textual foi supersedida para novas propostas geradas pelo Planner pela fronteira tipada descrita em 32.20 e 32.21. Ela permanece documentada porque explica os experimentos que levaram ao compilador determinístico, mas não governa o caminho atual de geração.

Structured output válido não basta para uma `PlanProposal`. O Planner também precisa respeitar causalidade mínima entre passos. Quando um passo descreve uma ação que pressupõe uma mudança anterior, como `reexecutar com as correções aplicadas`, essa mudança precisa ter sido produzida por um passo `WORLD` anterior e aparecer explicitamente em `depends_on`.

O Core aplica uma validação determinística para padrões observados de pressuposição de correções, alterações, modificações ou fixes já aplicados. Se nenhuma dependência `WORLD` anterior sustentar essa condição, a proposta é rejeitada antes de qualquer materialização.

Se a mudança ainda precisa acontecer e não existe capability adequada no catálogo, a representação correta é um passo `WORLD` com `capability=unknown` e `capability_detail`. A ausência de capability deve permanecer visível em vez de ser escondida dentro da linguagem da descrição.

Essa regra não cria um novo objeto persistente, não altera o schema e mantém o SQLite no schema 10.


### 32.20. Planner de intenção + compilador determinístico

Os testes reais de replanejamento mostraram que descrições em linguagem natural estavam acumulando responsabilidade operacional demais. O modelo escolhia ao mesmo tempo `kind`, `capability`, `depends_on`, `preconditions` e a própria estratégia; em seguida o Core tentava recuperar causalidade por padrões textuais como `script corrigido`, `correções aplicadas` ou referências indiretas a passos anteriores. Isso criou um ciclo de guards e reparos dependentes da redação do modelo.

A fronteira v0.1 é substituída por duas etapas:

```text
Goal + contexto + evidência
          ↓
        modelo
          ↓
   PlanIntentDraft
          ↓
 compilador determinístico
          ↓
     PlanProposal
          ↓
 readiness / materialização
```

`PlanIntentDraft` é transitório e contém somente estratégia cognitiva:

```text
summary
steps[]:
  subject
  role = COLLECT | ANALYZE | CHANGE | EXECUTE
  source = USER | SIMON   # somente quando role=COLLECT
  verification
open_questions[]
```

O modelo não escolhe `kind`, `capability`, `depends_on`, `preconditions`, Tool ou comando. Também não recebe o catálogo de capabilities para tentar adaptar a estratégia ao que o runtime consegue executar. Trabalho necessário deve continuar aparecendo mesmo quando a capability correspondente ainda estiver indisponível.

O Core compila deterministicamente a intenção tipada:

```text
COLLECT + source USER  -> actor USER  -> EPISTEMIC + user.ask
COLLECT + source SIMON -> actor SIMON -> EPISTEMIC + unknown
ANALYZE                 -> actor SIMON -> EPISTEMIC + cognition.analyze
EXECUTE                 -> actor SIMON -> WORLD     + process.run
CHANGE                  -> actor SIMON -> WORLD     + unknown
```

No Planner v0.1, `USER` não é um executor genérico de trabalho substantivo. O usuário participa de novas PlanProposals somente como fonte de informação ou evidência já existente através de `COLLECT`. `ANALYZE`, `CHANGE` e `EXECUTE` permanecem responsabilidade do SIMON mesmo quando a capability correspondente ainda está indisponível. `user.perform` continua existindo no catálogo e em Plans históricos, mas não é emitido pelo compilador de novas intenções nesta fase.

Quando a compilação produz `unknown`, `capability_detail` é derivada do próprio `subject`. A ausência operacional fica explícita e será tratada pelo readiness como `CAPABILITY_UNAVAILABLE`; ela não torna o Plan semanticamente inválido.

IDs são produzidos pelo Core como `step_01`, `step_02`, ... e a política serial do v0.1 também é aplicada por construção: todo passo após o primeiro depende do passo imediatamente anterior. Novas propostas compiladas recebem `preconditions=[]`. Preconditions livres deixam de fazer parte da saída cognitiva até existir uma necessidade real e um mecanismo verificável para resolvê-las.

Cada passo compilado preserva `intent_role` e `intent_actor` como proveniência tipada. `PlanProposal` continua validando invariantes de campos, grafo, cadeia serial, compatibilidade de capability/kind e proveniência compilada, mas sua `description` deixa de ser tratada como protocolo. O Core não interpreta mais expressões como `script corrigido` por regex para decidir validade operacional.

As guards textuais introduzidas durante os experimentos anteriores permanecem apenas como histórico de desenvolvimento e deixam de participar do caminho de geração de novas PlanProposals. O reparo semântico específico do Planner também deixa de ser necessário nessa fronteira: structured output pode continuar usando o reparo genérico do ModelProvider para JSON ou contrato inválido, mas a estratégia válida é compilada uma única vez pelo Core.

Essa separação estabelece duas responsabilidades:

```text
modelo -> decide o que precisa acontecer e, em COLLECT, de onde vem a evidência
Core   -> atribui a responsabilidade operacional e compila a intenção no v0.1
```

Plan válido não significa Plan executável. Um Plan pode conter `cognition.analyze`, `process.run` ou `unknown` indisponíveis e ainda ser uma representação correta da estratégia. O bloqueio operacional pertence a `plan-next`, não ao Planner. Nenhuma migration é necessária; o SQLite permanece no schema 10.


### 32.21. Texto humano não escolhe a operação

O primeiro teste real do Planner de intenção mostrou uma ambiguidade residual: o modelo marcou um passo como `COLLECT/USER`, mas escreveu no texto algo equivalente a “solicitar ao usuário que execute o script”. O compilador tipado classificou corretamente `COLLECT/USER` como `user.ask`, porém a `description` ainda reutilizava literalmente o texto produzido pelo modelo. Isso permitia que linguagem humana e campos operacionais se contradissessem.

A fronteira é refinada sem reintroduzir regex ou guards semânticas. `PlanIntentStep` passa a usar `subject` como objeto neutro da intenção, e não `purpose` como instrução executável. O modelo informa:

```text
subject
role
source   # somente para COLLECT
verification
```

O `subject` nomeia a informação, material, mudança ou execução em questão. A `description` operacional é gerada deterministicamente pelo Core a partir de `role + source + subject`, com actor efetivo definido pelo compilador. Exemplos:

```text
COLLECT + source USER
subject = logs da última execução já realizada
-> actor efetivo USER
-> Obter do usuário informação ou evidência já existente sobre: logs da última execução já realizada
-> user.ask

EXECUTE
subject = o script para produzir uma nova saída observável
-> actor efetivo SIMON
-> Executar: o script para produzir uma nova saída observável
-> process.run

ANALYZE
subject = código atual e erro observado
-> actor efetivo SIMON
-> Analisar: código atual e erro observado
-> cognition.analyze
```

Assim, linguagem livre deixa de poder alterar silenciosamente a natureza operacional do passo. Se o modelo classificar incorretamente uma necessidade de nova execução como `COLLECT`, o sistema continuará tratando aquele passo apenas como coleta de evidência já existente; ele não converterá a frase em execução. Para `ANALYZE`, `CHANGE` e `EXECUTE`, o modelo também não escolhe mais um executor humano: o Core atribui esses trabalhos ao SIMON. A eventual ausência dessa evidência será tratada pelo ciclo normal de Action, Verification e replanejamento.

O contexto de continuidade também passa a expor uma projeção determinística `verified_user_responses`, extraída somente de Events `user.response.received` que já sustentam o Goal Assessment. Essa projeção não resume nem interpreta as respostas: apenas torna visíveis `event_id`, `step_id` e `response` para reduzir repetição de coleta já concluída. O Planner é instruído a não criar `COLLECT/USER` para dados já presentes nessa projeção.

Nenhum novo objeto persistente é criado e nenhuma migration é necessária. SQLite permanece no schema 10.


### 32.22. Responsabilidade substantiva permanece com o SIMON

O primeiro Plan estável produzido após a introdução de `subject` revelou uma última ambiguidade do campo `actor`: o modelo planejou análise e execução pelo SIMON, mas atribuiu a correção do código ao usuário. A estratégia era tipada e causalmente coerente, porém terceirizava ao usuário justamente o trabalho substantivo delegado ao sistema.

No v0.1, essa decisão deixa de pertencer ao modelo. `PlanIntentStep` passa a usar `source` somente em passos `COLLECT`. A source informa de onde uma evidência já existente deve ser obtida. Os demais roles possuem responsabilidade fixa:

```text
ANALYZE -> SIMON
CHANGE  -> SIMON
EXECUTE -> SIMON
```

Isso não significa que o SIMON já consiga executar essas operações. Quando a capability estiver ausente, o Plan continua válido e o readiness deve expor `CAPABILITY_UNAVAILABLE`. Em particular, `CHANGE` compila para `unknown` até existir uma capability concreta de modificação. A ausência deixa de ser escondida através de `user.perform`.

`user.perform` não é removido do catálogo, pois Plans históricos e uma futura necessidade real de ação humana ainda podem justificá-lo. Ele apenas deixa de ser produzido automaticamente pelo Planner v0.1. Essa restrição pode ser revisada quando aparecer um caso concreto em que uma ação humana externa seja parte essencial do Goal e não simples terceirização de trabalho que pertence ao SIMON.

### 32.23. Primeira modificação operacional: `file.patch`

O Plan real da revisão 3 expôs um step `CHANGE/SIMON` com `capability=unknown` e critério explícito de que o arquivo do script deve ser modificado e salvo. Esse caso concreto justifica a primeira capability de mudança no filesystem.

`CHANGE` continua compilando para `unknown`. Nem toda mudança futura é uma alteração de arquivo, portanto o Core não converte `CHANGE` em `file.patch` por padrão e não interpreta `capability_detail` ou `description` por regex. A resolução ocorre apenas quando o usuário invoca explicitamente a operação `plan-patch`.

O binding v0.1 aceita somente um step persistido que satisfaça simultaneamente:

```text
kind = WORLD
intent_role = CHANGE
intent_actor = SIMON
capability = unknown
```

Além disso, `CAPABILITY_UNAVAILABLE: unknown` precisa ser o único blocker restante do step. Assim, a resolução concreta da capability não contorna dependências, preconditions, tentativas anteriores ou Verification pendente. O Plan não é reescrito e a proveniência original permanece intacta; a Action registra `kind=file.patch` e `bound_from_capability=unknown`.

A requisição concreta possui somente:

```text
workspace
relative_path
expected_text
replacement_text
```

O workspace é autorizado explicitamente pela fronteira CLI. O target precisa permanecer dentro dele após resolução canônica. Caminhos absolutos, segmentos `..`, links simbólicos e targets fora do workspace são recusados.

O v0.1 não oferece overwrite genérico. `expected_text` precisa existir exatamente uma vez no arquivo UTF-8 e é substituído por `replacement_text`. Zero ou múltiplas ocorrências encerram a Action como `FAILED` sem modificar o arquivo. O restante do conteúdo permanece byte a byte igual, inclusive line endings não tocados pela substituição.

A escrita usa arquivo temporário no mesmo diretório e `os.replace` para reduzir risco de escrita parcial. O Event `file.patch.completed` registra:

```text
target_path
relative_path
before_sha256
after_sha256
expected_text_sha256
replacement_text_sha256
```

O conteúdo do patch permanece no `input_data` da Action e não precisa ser duplicado no Event. A Action `COMPLETED` significa apenas que a alteração localizada foi aplicada. Nenhum `VerificationResult` é criado automaticamente; a próxima etapa deve reler o arquivo e verificar a evidência estrutural separadamente.

Nenhuma migration é necessária e o SQLite permanece no schema 10.


### 32.24. Verification objetiva do estado produzido por `file.patch`

Uma Action `file.patch` `COMPLETED` prova que uma substituição localizada foi aplicada naquele momento, mas o arquivo pode ser alterado novamente por outro processo antes que o Plan avance. Por isso, o estado atual do target precisa ser observado separadamente.

A operação `file-verify` aceita somente a tentativa mais recente do step e revalida a linhagem persistida da Action: request original, Event `file.patch.authorized`, Event `file.patch.completed`, Goal, Plan, step, caminho relativo e hashes registrados. O workspace canônico usado na verificação vem do Event de autorização, evitando que um workspace relativo dependa do diretório corrente de uma execução posterior.

A verificação relê o arquivo somente quando ele ainda resolve de forma segura dentro do workspace autorizado, sem atravessar links simbólicos. O resultado objetivo possui três estados observados:

```text
MATCHED
HASH_MISMATCH
TARGET_UNAVAILABLE
```

`MATCHED` significa que o SHA-256 atual é exatamente igual ao `after_sha256` produzido pela Action e gera `VerificationResult(status=VERIFIED, strength=4)`. `HASH_MISMATCH` e `TARGET_UNAVAILABLE` geram `FAILED`. Esses resultados comprovam apenas o estado estrutural do arquivo; `semantic_effect_assessed=false` permanece explícito porque igualdade de bytes não prova que a correção de software está conceitualmente certa.

Como o filesystem pode mudar depois de uma observação, verificações repetidas são idempotentes somente quando o estado mais recente observado continua igual. Se o arquivo mudar, uma nova Verification imutável é criada. Se depois ele voltar ao hash esperado, outra Verification `VERIFIED` pode ser criada. Consequentemente, o readiness passa a considerar o `VerificationResult` mais recente de uma Action, e não qualquer `VERIFIED` histórico, ao decidir se um step continua verificado.

Nenhuma migration é necessária e o SQLite permanece no schema 10.

### 32.25. Promoção epistemológica e conclusão de Goal

Um `Goal Assessment` `SATISFIED` continua sendo apenas julgamento cognitivo `ASSESSED`. O modelo não ganha autoridade para transformar seu próprio veredito em verdade operacional nem para encerrar o lifecycle do Goal. O bloqueio observado depois de `goal-assess` justifica um gate explícito:

```text
simon goal-complete <assessment_verification_id>
```

A operação aceita somente `VerificationResult` com:

```text
subject_type = GOAL
status = ASSESSED
assessment_type = goal.semantic
verdict = SATISFIED
```

Todos os `criterion_assessments` precisam permanecer `SATISFIED` e `missing_evidence` precisa estar vazio. O assessment também precisa continuar sendo o `goal.semantic` mais recente do Goal e apontar para o Plan `COMPLETED` mais recente, com revisão e Event `plan.completed` íntegros. Isso impede que uma avaliação antiga encerre o Goal depois que evidência epistemológica posterior mudou a conclusão.

A confirmação explícita do usuário produz, na mesma transação:

```text
verification.goal_assessment.confirmed
        ↓
VerificationResult(subject_type=GOAL, status=VERIFIED, strength=3)
        ↓
Goal ACTIVE -> COMPLETED
        ↓
goal.completed
```

A Verification final preserva o assessment confirmado, Plan, revisão, Event de conclusão do Plan, toda a linhagem de evidências do assessment e o Event de confirmação. O Event `goal.completed` referencia a Verification que autorizou a transição.

A transação é atômica: falha ao criar a Verification, alterar o Goal ou persistir os Events reverte a operação inteira. A conclusão é idempotente para o mesmo assessment; uma repetição recupera a conclusão já persistida sem criar novos registros ou atualizar timestamps.

`Plan COMPLETED`, `Goal ASSESSED` e `Goal COMPLETED` permanecem três fatos distintos. A estratégia ter terminado não prova o objetivo; o modelo considerar o objetivo satisfeito também não prova sozinho o objetivo; somente o gate confirmado promove a evidência para `VERIFIED` e encerra o Goal.

Nenhuma migration é necessária e o SQLite permanece no schema 10.

### 32.26. Retry operacional explícito de `process.run`

Os primeiros cenários de falha integrados confirmam o comportamento conservador do readiness: uma Action `process.run` `FAILED` ou `INTERRUPTED` produz `PREVIOUS_ATTEMPT_REQUIRES_REVIEW` e nunca é repetida automaticamente. O teste também expôs a primeira lacuna de recuperação: não existia uma operação capaz de autorizar uma nova tentativa depois desse review.

O v0.1 introduz:

```text
simon process-retry <action_id> --cwd <diretório> <executável> [argumentos...]
```

A operação exige simultaneamente:

```text
Action.kind = process.run
Action.status = FAILED | INTERRUPTED
Action = tentativa mais recente do step
Plan da Action = Plan ACTIVE atual
blockers do step = somente PREVIOUS_ATTEMPT_REQUIRES_REVIEW daquela Action
```

Isso impede que retry seja usado para contornar dependências não verificadas, preconditions, capability indisponível ou outra mudança no estado operacional do Plan. Se qualquer blocker adicional existir, a tentativa permanece bloqueada até que sua causa seja tratada.

O retry recebe um novo `ProcessRunRequest` estruturado e explicitamente autorizado. Executável, argumentos, working directory e timeout podem ser corrigidos sem modificar a Action anterior. A decisão produz `action.retry.authorized` com `source=user`; a nova Action registra `retry_of_action_id` e segue o mesmo lifecycle normal de `process.run`.

Uma Action anterior nunca é reaberta. Cada tentativa permanece imutável e a causalidade forma uma cadeia de novas Actions. Se um retry falhar novamente, somente a tentativa mais recente pode originar outra autorização. Uma tentativa concluída não pode ser convertida em retry operacional; seu resultado pertence ao fluxo de Verification.

Falha ao iniciar e timeout continuam produzindo `FAILED`. Uma execução que efetivamente inicia e termina continua produzindo `COMPLETED`, independentemente do exit code, e precisa passar por `process-verify` antes de satisfazer o step.

Esse corte não introduz retry automático, backoff, circuit breaker, limite global de tentativas, nova tabela ou migration. O SQLite permanece no schema 11. A próxima distinção a endurecer é entre falha que admite nova tentativa e evidência negativa que exige revisão da estratégia do Plan.

### 32.27. Replanejamento explícito motivado por falha epistemológica

O hardening posterior ao retry de `process.run` expôs a distinção complementar: uma tentativa operacional pode precisar ser repetida, mas uma conclusão epistemológica negativa pode demonstrar que o Plan atual não deve continuar pela mesma estratégia. O v0.1 não transforma qualquer blocker em replanejamento automático.

`plan-propose` passa a atuar também como gate explícito de revisão quando já existe um Plan `ACTIVE`. Se o Plan ainda possui step `READY`, Action em andamento, Verification pendente, assessment positivo aguardando confirmação ou blocker com recovery local conhecido, a chamada não substitui a estratégia atual. Em particular:

```text
user.ask + NOT_SATISFIED/UNCLEAR -> action-retry
process.run + FAILED/INTERRUPTED -> process-retry
cognition.analyze + FAILED/INTERRUPTED -> analysis-retry
```

Esses caminhos continuam locais porque a evidência disponível ainda não demonstra que a estratégia global precisa mudar.

O primeiro `PlanFailureContext` nasce somente de blockers epistemológicos persistidos:

```text
VERIFICATION_FAILED
VERIFICATION_INCONCLUSIVE
CRITERION_NOT_SATISFIED
ASSESSMENT_INCONCLUSIVE
```

A origem precisa ser uma Action `COMPLETED` do Plan `ACTIVE` e do step bloqueado. O contexto preserva Plan e revisão, step, capability, Action, Verification, `observed` e os Events de evidência da conclusão. `user.ask` permanece excluído desse corte porque já possui review/retry local explícito.

Quando esse contexto existe, o Planner recebe `prior_plan_failure` como dado sem autoridade de instrução. A orientação cognitiva é produzir a menor continuação capaz de enfrentar a falha observada, não repetir cegamente a mesma estratégia nem declarar a falha resolvida sem nova evidência. `NOT_SATISFIED` exige estratégia diferente ou evidência discriminante; `INCONCLUSIVE/UNCLEAR` exige produzir a evidência ausente; `FAILED` exige restaurar ou substituir o estado ou estratégia cuja Verification falhou.

O Event `cognition.plan_proposal.completed` preserva a causalidade da revisão através de:

```text
source_active_plan_id
source_active_plan_revision
source_failure_step_id
source_failure_action_id
source_failure_verification_id
source_failure_blocker_kind
```

Essa proveniência não é apenas documental. `plan-materialize` revalida o estado antes de criar a nova revisão. O Plan fonte precisa continuar `ACTIVE`; a Action precisa continuar `COMPLETED` e ser a tentativa mais recente do step; a Verification precisa continuar sendo a conclusão mais recente daquela Action; e status/veredito precisam continuar correspondendo ao blocker registrado. Se uma nova tentativa, Verification ou revisão surgir depois da proposta, a materialização é recusada como obsoleta em vez de sobrescrever o estado novo.

A criação da nova revisão continua usando o mecanismo existente de Plans: somente depois da revalidação o Plan anterior passa a `SUPERSEDED` e a revisão seguinte nasce `ACTIVE`. Nenhuma nova tabela, estado de Plan ou migration é necessária; o SQLite permanece no schema 11.

### 32.28. Retry operacional explícito de `cognition.analyze`

O hardening do ciclo separa falha da tentativa cognitiva de falha epistemológica da estratégia. Uma Action `cognition.analyze` pode terminar `FAILED` porque o ModelProvider ficou indisponível, porque a saída produzida não permaneceu grounded nos Events fornecidos ou porque a execução foi interrompida por restart. Nenhum desses fatos, isoladamente, demonstra que o Plan precisa ser substituído.

O v0.1 introduz:

```text
simon analysis-retry --model <modelo> <action_id>
```

A operação exige simultaneamente:

```text
Action.kind = cognition.analyze
Action.status = FAILED | INTERRUPTED
Action = tentativa mais recente do step
Plan da Action = Plan ACTIVE atual
blockers do step = somente PREVIOUS_ATTEMPT_REQUIRES_REVIEW daquela Action
```

O retry não reabre nem modifica a Action anterior. Uma nova Action é criada no mesmo `(goal_id, plan_id, step_id)`, preservando `retry_of_action_id`. A decisão explícita produz `action.retry.authorized` com `source=user`; a nova Action também registra `retry_authorization_event_id`. Se outra tentativa já sucedeu a Action indicada, a autorização é recusada.

Antes da chamada ao modelo, as evidências são reconstruídas a partir do estado epistemológico atual do Plan. Somente Events sustentados por Verifications `VERIFIED` de steps anteriores são novamente fornecidos à capability. Se uma dependência deixou de estar verificada ou surgiu qualquer blocker adicional, o retry é recusado em vez de consumir evidência antiga.

O resultado da nova tentativa segue exatamente o lifecycle existente. `ModelProviderError` e análise sem grounding produzem uma nova Action `FAILED`; sucesso produz `COMPLETED` e `cognition.analysis.completed`, ainda sem Verification automática. Uma tentativa `COMPLETED` precisa seguir por `analysis-assess` e eventual `verification-confirm`.

Esse retry não se aplica a uma análise executada com sucesso cuja conclusão epistemológica posterior seja negativa ou inconclusiva. `CRITERION_NOT_SATISFIED`, `ASSESSMENT_INCONCLUSIVE`, `VERIFICATION_FAILED` e `VERIFICATION_INCONCLUSIVE` continuam pertencendo ao fluxo explícito de replanejamento. Assim, falha operacional da cognição e falha da estratégia permanecem fatos distintos.

Nenhuma nova tabela, capability ou migration é necessária; o SQLite permanece no schema 11.

### 32.29. Retry operacional explícito de `file.patch`

O hardening de `file.patch` expõe uma particularidade que não existe em `process.run` e `cognition.analyze`: o Plan continua declarando o step de mudança como `capability=unknown`, e `file.patch` é um binding operacional especializado. Depois de uma tentativa `FAILED` ou `INTERRUPTED`, o readiness preserva simultaneamente a necessidade de review da tentativa e a indisponibilidade da capability persistida.

O v0.1 introduz:

```text
simon file-retry <action_id> --workspace <raiz> --file <relativo> --old <trecho> --new <trecho>
```

A operação exige simultaneamente:

```text
Action.kind = file.patch
Action.status = FAILED | INTERRUPTED
Action = tentativa mais recente do step
Plan da Action = Plan ACTIVE atual
step persistido = WORLD / CHANGE / SIMON / unknown
blockers do step =
  PREVIOUS_ATTEMPT_REQUIRES_REVIEW daquela Action
  + CAPABILITY_UNAVAILABLE: unknown
```

A presença de `DEPENDENCY_NOT_VERIFIED`, `PRECONDITION_UNRESOLVED` ou qualquer outro blocker impede o retry. Assim, a operação reautoriza somente o binding `CHANGE/unknown -> file.patch`; ela não transforma `file.patch` em capability genérica do Planner e não contorna condições causais do Plan.

A nova tentativa recebe um novo `FilePatchRequest`. Workspace, caminho relativo, trecho esperado e substituição podem ser corrigidos explicitamente sem modificar a Action anterior. A autorização gera `action.retry.authorized` com `source=user`, `capability=file.patch`, `retry_of_action_id`, `previous_status`, workspace e caminho relativo. O conteúdo integral de `expected_text` e `replacement_text` continua pertencendo à Action, evitando duplicação desnecessária no Event Log.

A Action de retry preserva `retry_of_action_id` e `retry_authorization_event_id`. `file.patch.started`, `file.patch.completed` e `file.patch.failed` carregam a referência causal para a tentativa anterior quando aplicável. Somente a tentativa mais recente pode originar outro retry, permitindo cadeias explícitas sem reabrir ou reescrever Actions antigas.

`file-verify` passa a reconhecer tanto a autorização inicial `file.patch.authorized` quanto `action.retry.authorized`. No caso de retry, a Verification revalida capability, Action anterior, Goal, Plan, step, status anterior, workspace, arquivo e a mesma linhagem declarada pelo Event `file.patch.completed`. Uma autorização de retry adulterada ou pertencente a outra tentativa é rejeitada antes da criação de nova Verification.

O retry se aplica apenas a falha operacional da tentativa. Uma Action `file.patch` `COMPLETED` não pode ser submetida a `file-retry`, mesmo se uma Verification posterior resultar `FAILED`; nesse caso existe evidência de que uma mudança ocorreu mas o estado verificado não atende mais ao esperado, portanto o recovery continua no fluxo explícito de replanejamento.

Nenhuma nova tabela, capability ou migration é necessária; o SQLite permanece no schema 11.



### 32.30. Recovery integrado com falhas e reinicialização

Os retries locais de `process.run`, `cognition.analyze` e `file.patch` passam a ser validados em conjunto por um cenário integrado, não apenas por testes isolados de cada capability. O objetivo é provar que persistência, readiness, provenance e Verification continuam coerentes quando várias falhas operacionais acontecem dentro do mesmo Plan e o runtime é reiniciado entre elas.

O cenário usa um Plan serial com três steps:

```text
step_01: process.run
step_02: cognition.analyze, depende de step_01
step_03: CHANGE / SIMON / unknown, depende de step_02 e é ligado operacionalmente a file.patch
```

Cada step falha uma vez por uma causa operacional controlada. Depois da falha, um novo processo executa `resume` antes do retry. A retomada precisa reconstruir a Action `FAILED` como tentativa mais recente e manter o blocker `PREVIOUS_ATTEMPT_REQUIRES_REVIEW`. Para `file.patch`, o blocker `CAPABILITY_UNAVAILABLE: unknown` também precisa permanecer presente porque o binding especializado não altera a capability persistida do Plan.

A recuperação segue exclusivamente os comandos locais já existentes:

```text
process.run FAILED
  -> process-retry
  -> process-verify

cognition.analyze FAILED
  -> analysis-retry
  -> analysis-assess
  -> verification-confirm

file.patch FAILED
  -> file-retry
  -> file-verify
```

Ao final do cenário, o Plan só pode ser concluído se as três tentativas novas forem a tentativa mais recente de seus steps e estiverem `VERIFIED`. As três Actions originais permanecem `FAILED` e imutáveis. As Actions recuperadas precisam preservar `retry_of_action_id`, e cada decisão de retry precisa possuir um Event `action.retry.authorized` com `source=user` e a capability correspondente.

A reinicialização final precisa reconstruir as seis Actions e o Plan `COMPLETED` diretamente do SQLite. Nenhum estado interno do `ModelProvider` anterior participa dessa reconstrução. O teste não encontrou nova lacuna de produção: os contratos de retry, retomada e Verification já implementados permaneceram consistentes quando combinados.

Esse corte adiciona somente cobertura integrada e documentação. Nenhuma tabela, capability, estado de lifecycle ou migration nova é necessária; o SQLite permanece no schema 11.

### 32.31. Auditoria de estabilização e invariantes de runtime

A estabilização do v0.1 passa a tratar exclusão mútua do runtime e freshness epistemológica como invariantes do Core, e não como convenções da CLI.

Cada diretório de dados admite uma única instância de CLI ativa. O processo adquire um lock exclusivo do sistema operacional em `.runtime.lock` antes de inicializar o banco, suspender Experiences ou reconciliar Actions. Se o lock já estiver ocupado, a nova instância termina sem alterar estado persistido. A reconciliação `RUNNING -> INTERRUPTED` só é válida depois da aquisição desse lock, porque sua premissa é que não existe outro runtime vivo responsável pela Action. O arquivo pode permanecer no filesystem após o encerramento; a autoridade é o lock mantido pelo kernel, não a existência do arquivo. Nenhuma tabela de heartbeat, PID lease ou daemon é introduzida.

O estado de um step passa a obedecer a uma regra única:

```text
tentativa atual = Action mais recente do step
conclusão epistemológica atual = VerificationResult mais recente dessa Action
```

Uma Action mais antiga `VERIFIED` nunca torna o step atual `VERIFIED` se existe tentativa posterior. Do mesmo modo, um `VERIFIED` antigo da mesma Action não permanece autoritativo quando existe Verification posterior `FAILED`, `INCONCLUSIVE` ou `ASSESSED`. Histórico continua imutável e consultável, mas não substitui a conclusão atual.

`plan-complete` revalida esse contrato dentro da mesma transação que muda o Plan para `COMPLETED`. O Event `plan.completed` registra `verified_step_ids` e `verified_action_ids` na ordem dos steps do Plan. Depois do fechamento, `goal-assess` exige que as Actions registradas nesse Event ainda correspondam à tentativa atual de cada step e que a Verification mais recente de cada uma continue `VERIFIED`.

`goal-complete` repete essa validação depois do assessment semântico e antes da promoção do Goal para `VERIFIED/COMPLETED`. Assim, uma mudança observada entre `goal-assess` e `goal-complete` invalida o gate de conclusão em vez de permitir que o Goal seja fechado com evidência stale.

A mesma regra é aplicada ao contexto de `cognition.analyze`: somente a tentativa mais recente de cada step anterior pode fornecer evidência, e apenas quando sua Verification mais recente continua `VERIFIED`. Tentativas históricas permanecem disponíveis para auditoria, Experience e diagnóstico, mas não são usadas como substitutas silenciosas de uma tentativa atual que falhou.

A auditoria considera deliberadamente fora do escopo bloqueador do v0.1: múltiplos runtimes concorrentes no mesmo banco, recuperação automática de efeitos externos incertos, invalidação automática de Plans baseada apenas em `world_revision` e promoção automática de Experience para Memory. Esses itens exigem mecanismos ou semântica adicionais e não são necessários para preservar os invariantes atuais do Core.

Nenhuma migration é necessária; o SQLite permanece no schema 11.

### 32.32. Release candidate instalável do v0.1

Após a auditoria de estabilização, o núcleo entra em release candidate `0.1.0rc1`. Este corte não adiciona capability, lifecycle, tabela ou decisão cognitiva nova. O objetivo é provar que a distribuição instalada preserva os contratos que já foram validados no checkout de desenvolvimento.

O projeto passa a manter `scripts/rc_smoke.py` como verificação reproduzível de release. O script constrói os dois artefatos padrão do projeto:

```text
wheel
sdist
```

e inspeciona o wheel antes da instalação. O artefato precisa conter as migrations `0001` até `0011`, metadata compatível com a versão e com Python 3.14, além do entry point:

```text
simon = simon.cli:main
```

Em seguida, o wheel é instalado em um virtualenv temporário criado com o mesmo interpretador que executa o smoke. A validação não usa o checkout como import path. O ambiente instalado precisa responder corretamente por `simon --version`, `simon --help` e `python -m simon --version`.

O smoke também valida persistência em duas trajetórias. Em banco vazio, o startup precisa criar `simon.db`, materializar as tabelas esperadas e terminar diretamente no schema 11. Em um segundo banco, as migrations extraídas do próprio wheel criam deliberadamente um schema 7 com um Event sentinela; a instalação do RC precisa migrá-lo até 11 preservando esse registro e materializando `world_state`.

A suíte normal continua responsável por invariantes de domínio e comportamento. O smoke de RC é deliberadamente menor e testa a fronteira de distribuição, evitando que um pacote aparentemente válido seja promovido sem migrations, entry point ou capacidade de upgrade. Ollama e chamadas de modelo ficam fora desse teste porque não são requisitos para provar a integridade do artefato local.

O SQLite permanece no schema 11. A promoção de `0.1.0rc1` para `0.1.0` só deve ocorrer depois que testes, lint, tipagem e smoke do artefato instalado estiverem verdes no runtime oficial Python 3.14.7.

### 32.33. Release final do núcleo v0.1

Depois da aprovação do release candidate `0.1.0rc1` em Python 3.14.7, o núcleo é promovido para `0.1.0`. A promoção não adiciona capability, lifecycle, tabela, migration ou decisão cognitiva nova. Ela congela como contrato estável o comportamento já validado no RC.

A versão final preserva o SQLite no schema 11 e mantém como invariantes do núcleo: persistência de Goal/Plan/Action/Event/Verification/Experience/Memory; separação entre execução e conclusão epistemológica; autoridade exclusiva da tentativa mais recente de cada step e da Verification mais recente dessa tentativa; retry explícito para falha operacional; replanejamento explícito para falha epistemológica; restart e `resume` sem dependência de contexto anterior do modelo; exclusão mútua por diretório de dados; e revalidação da evidência antes de concluir Plan ou Goal.

A distribuição final continua sendo validada pelo smoke reproduzível em `scripts/rc_smoke.py`. O nome do arquivo é preservado por compatibilidade com o gate já aprovado no release candidate, mas o script passa a representar o smoke da distribuição v0.1. Ele precisa construir wheel e sdist, inspecionar migrations e metadata, instalar o wheel fora do checkout, validar `simon` e `python -m simon`, criar um banco limpo no schema 11 e executar upgrade 7 -> 11 preservando um Event sentinela. O sucesso é reportado como `Release smoke: OK`.

`CHANGELOG.md` passa a ser a fotografia histórica do release, enquanto `RELEASE_NOTES_0.1.0.md` apresenta a primeira versão como marco público. Esses arquivos registram as garantias do núcleo, a qualidade validada antes da promoção, compatibilidade e os limites deliberadamente deixados para fases posteriores. Esses limites não devem ser resolvidos dentro do `0.1.x` apenas por conveniência arquitetural; mudanças que alterem os contratos centrais do Core exigem uma decisão de versão compatível com o impacto.

O v0.1 permanece deliberadamente sem Executive/Attention persistente, seleção automática de Memory, invalidação automática de Plan por assumptions, roteamento entre modelos, busca vetorial, visão, voz ou interface gráfica. Essas capacidades pertencem à fase seguinte e devem consumir os contratos estabilizados em vez de substituí-los.

A versão final do pacote é `simon-local==0.1.0`, com Python `>=3.14,<3.15` e SQLite schema 11.

## 33. Fase 2: Executive sobre o Core v0.1.0

### 33.1. Regra de evolução

A Fase 2 consome os contratos estabilizados em `0.1.0`. Executive, interação natural e capabilities futuras não podem reabrir invariantes do Core por conveniência. Em particular, continuam autoritativas a tentativa mais recente de cada step, a Verification mais recente dessa tentativa, os blockers de `PlanReadiness`, provenance imutável, gates humanos explícitos e exclusão mútua por diretório de dados.

O Executive coordena autoridade existente; ele não cria autoridade nova.

### 33.2. Executive mínimo foreground

O primeiro corte é deliberadamente single-focus e não persistente. A solicitação foreground atual e zero ou um Goal selecionado formam o foco. Exatamente um Goal aberto pode ser selecionado automaticamente; múltiplos Goals permanecem ambíguos até escolha explícita ou identificação inequívoca pelo usuário.

Não entram neste corte Background scheduler, FocusSession persistente, Attention scoring, preempção, paralelismo ou priorização probabilística entre Goals.

### 33.3. Classes de autoridade

As operações se dividem em três classes.

`EXECUTIVE_AUTONOMOUS` contém condução sem novo consentimento humano, como reconstrução de estado, readiness, interpretação, propostas cognitivas, materialização de Plan já autorizado, Verification objetiva, assessments semânticos, conclusão determinística de Plan e avaliação de Goal.

`USER_TURN_BOUND` contém operações cujo efeito representa uma escolha ou confirmação humana, como aceitar Goal, responder `user.ask` e confirmar assessment. Elas só poderão ser roteadas automaticamente quando existir provenance explícita que vincule o turno real do usuário ao gate. Até lá, o Executive deve parar e pedir a decisão.

`EXPLICIT_OPERATION_GATE` contém efeitos externos e decisões deliberadamente autorizadas no v0.1, incluindo `process.run`, `file.patch`, retries operacionais e promoção de Experience para Memory. Um Goal desejado não concede implicitamente esses grants.

### 33.4. Resultado de decisão

Cada ciclo do Executive produz exatamente uma decisão observável:

```text
PROCEED
NEEDS_USER_INPUT
NEEDS_USER_CONFIRMATION
NEEDS_OPERATION_AUTHORIZATION
NEEDS_GOAL_SELECTION
BLOCKED
DONE
```

`PROCEED` aponta para uma única operação do Core. Os demais resultados preservam o objeto ou blocker concreto que impede continuidade. O Executive não transforma blocker em autorização e não executa mais de uma mudança de estado sem reavaliar o Core.

### 33.5. Precedência determinística

No primeiro corte, prioridade é lifecycle, não score. O Executive trata primeiro Actions em andamento ou aguardando usuário; depois Verification pendente; gates de confirmação; recoveries operacionais; falhas epistemológicas que exigem replan; step READY; conclusão do Plan; avaliação do Goal; gate de conclusão do Goal; e por fim `DONE`.

Essa precedência consome `PlanReadiness` e os objetos persistidos. Ela não replica nem substitui a lógica de readiness.

### 33.6. Fronteira do modelo

ModelProvider pode interpretar, propor Goals/Plans, analisar e avaliar semanticamente. Ele não decide se autorização humana aconteceu, se blocker pode ser ignorado, se escopo pode ser expandido, se Action histórica volta a ser atual ou se Verification histórica substitui evidência mais recente.

### 33.7. Golden Scenario inicial

O primeiro cenário da Fase 2 começa com Goal e Plan já persistidos e usa somente capabilities existentes. O usuário pede em linguagem natural para continuar o Goal. O Executive reconstrói estado, seleciona o foco quando não há ambiguidade, conduz automaticamente operações epistemicamente seguras e para nos gates reais de autorização ou confirmação. O cenário precisa atravessar restart e terminar em `DONE` sem depender de memória do processo anterior.

O corte não promete ainda resolver "corrija este script" do zero. A v0.1 não possui leitura geral de arquivos nem proposta estruturada de patch suficiente para esse caso sem adicionar novas capabilities. Essas capabilities só devem nascer depois que a orquestração foreground estiver provada.

### 33.8. Primeiro incremento de código

A linha de desenvolvimento pós-v0.1 passa a ser `0.2.0.dev0`. O primeiro código do Executive é `ExecutiveDecision`, produzido por `decide_next()` sobre `reconstruct_resume_state()` e `PlanReadiness`. A decisão é read-only e contém um `outcome`, razão estável, uma única operação quando aplicável, indicação de necessidade de modelo e referências para Goal, Plan, step, Action, Verification, capability e blockers.

`PROCEED` só existe quando há exatamente uma próxima operação interna legítima. `NEEDS_USER_INPUT`, `NEEDS_USER_CONFIRMATION` e `NEEDS_OPERATION_AUTHORIZATION` podem apontar a operação que está atrás do gate sem executá-la. `NEEDS_GOAL_SELECTION`, `BLOCKED` e `DONE` nunca carregam operação executável.

A precedência implementada cobre Action em andamento, `user.ask` em espera, Verification pendente, confirmação de assessment, retry local, falha epistemológica que exige replan, step `READY`, binding especializado de `CHANGE/unknown` para `file.patch`, conclusão de Plan, assessment de Goal e gate de conclusão do Goal. O decisor não escolhe modelo e apenas marca `requires_model` quando a operação futura depender de um `ModelProvider`.

O comando `executive-next [goal_id]` expõe essa decisão na CLI sem persistir Action, Event ou Verification. Múltiplos Goals abertos produzem `NEEDS_GOAL_SELECTION`. O runner descrito na seção seguinte consome apenas decisões `PROCEED` e preserva a regra de uma única transição antes de reconstruir o estado.


### 33.9. Runner foreground de uma transição

O Executive ganha `run_executive_once()`, responsável por consumir a decisão atual e executar no máximo uma operação `PROCEED` segura. A chamada nunca percorre um loop interno. Depois da transição, o estado é reconstruído e uma nova `ExecutiveDecision` é retornada apenas como observação do próximo ciclo.

O resultado do runner distingue `EXECUTED`, `STOPPED`, `MODEL_REQUIRED` e `FAILED`. `STOPPED` preserva gates de usuário, confirmação e autorização operacional sem criar efeitos. `MODEL_REQUIRED` ocorre quando a decisão é legítima, mas depende de cognição e nenhum provider/model foi fornecido. `FAILED` registra a falha da chamada sem convertê-la em autorização de retry.

O runner pode conduzir somente operações internas já autorizadas pelo contrato: proposta e materialização de Plan, `user.ask`, `cognition.analyze`, Verification objetiva, assessments, retry local de `user.ask`, conclusão de Plan e assessment de Goal. `process.run`, `file.patch`, retries operacionais, confirmações de assessment, conclusão confirmada de Goal e promoção de Memory permanecem fora do executor automático.

`ExecutiveDecision` passa a reconhecer proposta de Plan concluída e não materializada. Nessa condição, a próxima operação é `plan.materialize` com referência explícita ao Event de proposta. Proposta e materialização nunca acontecem no mesmo ciclo. Para replanejamento, a proposta pendente só é aceita quando sua provenance ainda corresponde ao Plan, revisão e Verification de falha atuais; para continuação após assessment de Goal, precisa corresponder ao Plan concluído e ao assessment atual.

O comando `executive-step [--model MODELO] [goal_id]` expõe o runner. Uma chamada que executa algo imprime a decisão consumida, a referência do resultado e a próxima decisão não executada. O SQLite permanece no schema 11.

### 33.10. Golden Scenario foreground com restart

A primeira prova integrada do Executive usa um Goal e um Plan persistidos com `process.run`, `cognition.analyze`, `CHANGE/unknown -> file.patch`, nova execução e análise final. Cada invocação de `executive-step` continua limitada a uma transição `PROCEED`; efeitos externos e confirmações permanecem gates explícitos fora do runner.

O cenário deve demonstrar, em uma única história causal:

- `NEEDS_OPERATION_AUTHORIZATION` antes de cada `process.run` e `file.patch`;
- Verification objetiva conduzida pelo Executive depois da autorização e execução externas;
- `cognition.analyze` e assessments executados apenas com `ModelProvider` e modelo explícitos;
- `NEEDS_USER_CONFIRMATION` antes de promover assessments SATISFIED;
- conclusão de Plan e assessment de Goal em ciclos separados;
- confirmação final do Goal fora do runner;
- pelo menos três reinícios reais de processo durante o mesmo Goal;
- reconstrução final `DONE` em um processo que não compartilha memória com as invocações anteriores.

A continuidade deve depender exclusivamente dos objetos persistidos e de `reconstruct_resume_state()`. O teste não pode usar um loop monolítico, não pode fabricar provenance `source=user` e não pode autorizar efeitos externos em nome do usuário.

A validação deste cenário não introduz nova capability, tabela ou migration; o SQLite permanece no schema 11.

### 33.11. Condutor foreground limitado

A ergonomia foreground evolui com `run_executive_until_gate()`. O condutor não introduz um novo scheduler e não altera `ExecutiveDecision`; ele apenas chama o runner seguro repetidamente enquanto a decisão reconstruída continuar `PROCEED`. Cada transição continua isolada por uma nova leitura do estado persistido.

A execução termina em um destes estados: `STOPPED`, `DONE`, `MODEL_REQUIRED`, `FAILED` ou `LIMIT_REACHED`. `STOPPED` preserva qualquer gate externo já definido; `MODEL_REQUIRED` não escolhe um modelo; `FAILED` não autoriza retry; `DONE` representa lifecycle concluído; `LIMIT_REACHED` interrompe uma sequência ainda `PROCEED` sem consumir a operação seguinte.

O comando `executive-continue [--model MODELO] [--max-transitions N] [goal_id]` expõe esse comportamento. O padrão é 32 transições por chamada e valores menores que 1 são inválidos. O limite é uma proteção foreground contra ciclos acidentais de decisão, não um orçamento persistente nem uma política de Attention.

Efeitos externos e escolhas humanas continuam fora do condutor. Em particular, `process.run`, `file.patch`, retries operacionais, `action.answer`, `verification.confirm`, `goal.complete` e promoção de Memory permanecem gates explícitos. O SQLite continua no schema 11.


### 33.12. Gateway foreground de turno humano

A primeira borda de interação natural é `handle_user_turn()` e o comando `user-turn`. Todo texto recebido é persistido como Event `user.turn.received` com `source=user` antes de qualquer condução. Esse Event prova que o usuário produziu o turno, mas não constitui autorização operacional genérica.

O único intent de controle livre neste corte é `CONTINUE`, reconhecido por um conjunto pequeno e determinístico de formulações equivalentes. O ModelProvider não participa dessa classificação. Fora dos gates contextuais descritos na seção 33.13, texto não reconhecido produz `user.turn.unhandled` e nenhuma operação do Executive é executada. Isso impede que similaridade linguística ou inferência probabilística amplie grants.

Um turno `CONTINUE` reconhecido chama o condutor foreground com exatamente a autoridade que ele já possuía. O Event `executive.user_turn.routed`, com `source=system`, referencia o `user.turn.received` por `trace_id` e declara `authority_scope=EXECUTIVE_SAFE_CONTINUATION`. O payload registra status, quantidade de transições, decisão final e referências dos resultados produzidos pelo condutor.

`CONTINUE` não satisfaz `NEEDS_OPERATION_AUTHORIZATION`, `NEEDS_USER_CONFIRMATION` ou `NEEDS_USER_INPUT`. Em particular, ele não autoriza `process.run`, `file.patch`, retries operacionais, `verification.confirm`, `goal.complete` nem promoção de Memory. Se houver múltiplos Goals abertos e nenhum Goal explícito no turno, `NEEDS_GOAL_SELECTION` continua autoritativo.

A CLI usa `--goal-id` somente para indicar foco explícito e aceita `--model` e `--max-transitions` como parâmetros do condutor. Nenhuma tabela ou migration nova é necessária; os Events existentes são suficientes para a provenance deste primeiro gateway.


### 33.13. Resposta humana contextual ao gate aberto

`user-turn` passa a consultar `ExecutiveDecision` para distinguir um texto humano genérico de uma resposta válida ao gate atual. Essa interpretação contextual não amplia grants: ela só pode satisfazer um gate que o Core já declarou explicitamente.

Quando a decisão é `NEEDS_USER_INPUT` com `action.answer`, o turno não vazio é aplicado somente à `user.ask` `WAITING` referenciada por `action_id`. O Event `user.response.received` usa o `user.turn.received` como `trace_id`, preservando a causalidade entre fala humana e resposta persistida. Depois disso, o condutor pode avançar pelas operações `PROCEED` seguras até o próximo gate.

Quando a decisão é `NEEDS_USER_CONFIRMATION`, somente uma confirmação afirmativa pertencente ao conjunto determinístico suportado pode ser aplicada. `verification.confirm` usa exatamente o `verification_id` do assessment atual; `goal.complete` usa exatamente o assessment `goal.semantic` atual. Ambos os serviços existentes revalidam freshness e provenance antes de promover o estado.

`NEEDS_OPERATION_AUTHORIZATION` só entra na linguagem natural quando existe uma proposta operacional concreta que corresponda ao gate atual. `process.run` é detalhado na seção 33.14 e `file.patch` na seção 33.15. Sem proposta correspondente, uma resposta afirmativa não cria Action. Retries operacionais continuam exigindo as fronteiras explícitas anteriores.

O Event de roteamento contextual inclui o snapshot do gate consumido, `effect_type`, `effect_id` e uma `authority_scope` limitada ao gate atual. O ModelProvider não classifica confirmações, não escolhe o alvo e não cria autorização. O SQLite permanece no schema 11.


### 33.14. Proposta concreta de autorização para process.run

O primeiro bridge entre uma autorização conversacional e um efeito externo é deliberadamente específico para `process.run`. A proposta não executa nada e não representa consentimento. Ela apenas congela os parâmetros exatos que serão apresentados ao usuário antes do gate.

`propose_process_run()` exige que `decide_next()` esteja em `NEEDS_OPERATION_AUTHORIZATION`, com operação `plan.run` e capability `process.run`. O request é ligado ao Plan ACTIVE por `bind_process_run_step()` e então persistido como Event `executive.operation.proposed`, com `source=system`. O payload registra Goal, Plan, revisão, step, critério de Verification, executável, argv, working directory e timeout. Nenhuma Action ou Verification é criada.

A CLI expõe essa materialização com:

```powershell
uv run simon process-propose gol_ID --cwd C:\projeto python -m pytest
```

Somente a proposta mais recente de `process.run` para o Goal pode ser considerada. Para permanecer válida, ela precisa continuar correspondendo ao mesmo Goal, Plan e step que a `ExecutiveDecision` atual está pedindo para autorizar. Criar uma proposta nova registra qual proposta anterior ela substitui; uma proposta pertencente a um gate antigo não é reaproveitada.

Se o usuário responder afirmativamente enquanto essa proposta continua atual, `user-turn` usa exatamente o `ProcessRunRequest` persistido e chama `execute_next_process_run()` com o ID de `user.turn.received` como `trace_id`. O executor mantém seu contrato antigo: cria `process.run.authorized` com `source=user`, cria a Action e executa sem shell implícito. O gateway não fabrica um segundo grant; ele apenas vincula a fala humana ao grant que o Core já sabe registrar.

O Event `executive.user_turn.routed` registra `authority_scope=CURRENT_OPERATION_PROPOSAL_ONLY`, o `proposal_event_id` consumido e a Action resultante. Sem proposta, com texto não afirmativo, com proposta stale ou diante de outro tipo de autorização operacional, nenhuma Action externa é criada. O SQLite permanece no schema 11.


### 33.15. Proposta concreta de autorização para file.patch

O segundo efeito externo coberto pela autorização conversacional concreta é `file.patch`. A proposta continua não sendo consentimento e não modifica arquivo; ela apenas materializa o `FilePatchRequest` exato que o usuário poderá aprovar depois.

`propose_file_patch()` exige uma `ExecutiveDecision` atual em `NEEDS_OPERATION_AUTHORIZATION`, operação `plan.patch` e capability `file.patch`. O request é validado por `FilePatchRequest` e ligado ao Plan ACTIVE por `bind_file_patch_step()`. O Event `executive.operation.proposed`, com `source=system`, registra Goal, Plan, revisão, step, `capability_detail`, critério de Verification, workspace, caminho relativo, trecho esperado e substituição proposta. Nenhuma Action, autorização ou escrita no filesystem acontece nessa etapa.

A CLI expõe a proposta com:

```powershell
uv run simon file-propose gol_ID --workspace C:\projeto --file script.py --old "valor = 1" --new "valor = 2"
```

Somente a proposta operacional mais recente do Goal pode ser consumida. Para continuar válida, ela precisa corresponder ao mesmo gate `plan.patch/file.patch`, Goal, Plan, revisão e step atuais, e o request precisa continuar ligável ao `CHANGE/unknown` persistido. Uma proposta nova registra `supersedes_proposal_event_id`, tornando a anterior inelegível para autorização natural.

Um turno afirmativo explícito como `sim`, `pode aplicar`, `pode alterar` ou `pode modificar` pode consumir a proposta atual. O gateway chama `execute_next_file_patch()` com o ID de `user.turn.received` como `trace_id`; o executor existente cria `file.patch.authorized` com `source=user`, aplica a substituição localizada e registra hashes e resultado como antes. A proposta não antecipa a validação do conteúdo real do arquivo: ausência, ambiguidade do trecho, path inválido em runtime ou outro erro operacional continuam sendo responsabilidade do executor e podem produzir uma Action `FAILED`.

O Event `executive.user_turn.routed` usa `authority_scope=CURRENT_OPERATION_PROPOSAL_ONLY`, registra o `proposal_event_id` consumido e a Action `file.patch` resultante. Sem proposta, com texto não afirmativo ou com proposta stale, nenhuma alteração é realizada. Retries de `file.patch` continuam fora deste bridge natural. O SQLite permanece no schema 11.

### 33.16. Propostas concretas para retries de process.run e file.patch

Retries operacionais continuam sendo decisões `NEEDS_OPERATION_AUTHORIZATION`, nunca operações `PROCEED`. Para permitir aprovação conversacional sem transformar um "sim" em permissão aberta, o Executive passa a materializar uma nova tentativa concreta antes do consentimento.

`propose_process_retry()` exige uma Action `process.run` `FAILED` ou `INTERRUPTED` que seja exatamente o `action_id` exposto pela decisão atual `process.retry`. O novo `ProcessRunRequest` é ligado ao mesmo step do Plan ACTIVE e persistido como `executive.operation.proposed`, com `proposal_type=process.retry`, `retry_of_action_id`, `previous_status`, revisão do Plan, critério de Verification e argv completo. A CLI correspondente é `process-retry-propose`.

`propose_file_patch_retry()` aplica a mesma regra a `file.retry`. A Action anterior precisa ser `file.patch` `FAILED` ou `INTERRUPTED` e precisa coincidir com o `action_id` do gate atual. O `FilePatchRequest` corrigido é ligado ao mesmo `CHANGE/unknown`, e a proposta persiste workspace, caminho relativo, textos da substituição, `capability_detail`, Verification, Action anterior e status anterior. A CLI correspondente é `file-retry-propose`.

Nenhuma das duas propostas cria Action, escreve em arquivo ou inicia processo. No turno afirmativo posterior, o gateway revalida Goal, Plan, revisão, step, operação, `reason_code=retry_authorization_required`, Action anterior e request persistido. Só então chama os serviços antigos `retry_process_run()` ou `retry_file_patch()` com o `trace_id` de `user.turn.received`.

A autoridade real permanece `action.retry.authorized` com `source=user`. A proposta usa `source=system` e não constitui consentimento. Se uma tentativa posterior substituir a Action que motivou o gate, a proposta antiga não pode ser reutilizada. O retry cognitivo possui requisitos adicionais de modelo e evidência e é especificado na seção 33.17.

O SQLite permanece no schema 11.


### 33.17. Proposta concreta para analysis.retry

O retry de `cognition.analyze` usa o mesmo princípio de autorização concreta, mas não pode ser reduzido a uma Action anterior e parâmetros WORLD. A nova tentativa também depende do modelo escolhido e da visão epistemicamente atual das evidências anteriores. Por isso, `analysis.retry` possui um payload próprio em `executive.operation.proposed`.

`propose_cognition_analysis_retry()` exige uma Action `cognition.analyze` `FAILED` ou `INTERRUPTED` que seja exatamente o `action_id` do gate atual `NEEDS_OPERATION_AUTHORIZATION / analysis.retry`. O helper read-only `get_cognition_retry_context()` revalida que a Action pertence ao Plan ACTIVE, que continua sendo a tentativa mais recente do step e que o único blocker é `PREVIOUS_ATTEMPT_REQUIRES_REVIEW`.

A proposta persiste `proposal_type=analysis.retry`, Goal, Plan, revisão, step, `retry_of_action_id`, `previous_status`, critério de Verification, modelo explícito e a sequência ordenada de `evidence_event_ids` produzida por `_verified_prior_evidence`: somente evidências de tentativas anteriores `COMPLETED` cuja Verification mais recente continua `VERIFIED` podem entrar. O Event usa `source=system`; não chama `ModelProvider`, não cria Action e não registra autorização. A CLI é:

```powershell
uv run simon analysis-retry-propose --model <modelo> <action_id>
```

`find_current_cognition_analysis_retry_proposal()` só retorna a proposta operacional mais recente do Goal se o gate, Action anterior, status, Plan, revisão, Verification, modelo persistido e evidências ainda forem válidos. Alteração posterior da Verification de uma dependência, nova revisão de Plan ou nova tentativa no step invalida a proposta.

Quando um turno afirmativo explícito consome a proposta, o gateway exige um `ModelProvider` disponível, mas usa obrigatoriamente o modelo congelado na proposta. `retry_cognition_analysis()` recebe também a revisão do Plan e os IDs de evidência esperados. Ele reconstrói o contexto novamente e recusa a nova Action se a revisão ou a evidência tiverem mudado; `_execute_cognition_analysis_attempt()` repete a comparação imediatamente antes de criar o retry.

A autoridade real continua sendo o Event `action.retry.authorized` criado pelo executor existente com `source=user` e `trace_id` de `user.turn.received`. Seu payload registra `retry_of_action_id`, `previous_status`, capability, modelo e evidências consumidas. O Event de proposta nunca substitui esse grant.

Na CLI, `user-turn` pode construir o adapter Ollama sem um `--model` explícito no turno para permitir o consumo de uma proposta cognitiva já materializada; construir o adapter não chama o runtime. O modelo autorizado continua vindo da proposta. Operações cognitivas seguras posteriores ainda param em `MODEL_REQUIRED` caso o turno não tenha fornecido um modelo ao condutor.

O SQLite permanece no schema 11.

### 33.18. Apresentação read-only do gate operacional

A camada Executive deve tornar um gate operacional compreensível antes de qualquer nova automação de parâmetros. `describe_operation_gate()` recebe a `ExecutiveDecision` já reconstruída e produz uma `OperationGatePresentation` sem persistir Event, criar Action ou alterar qualquer lifecycle. `describe_current_operation_gate()` apenas combina `decide_next()` com essa leitura.

Os estados da apresentação são:

- `NOT_OPERATION_GATE`: a decisão atual não pede autorização operacional;
- `PROPOSAL_REQUIRED`: o gate é suportado, mas ainda não existe proposta concreta válida;
- `READY_FOR_AUTHORIZATION`: existe uma proposta atual que pode ser apresentada ao usuário;
- `UNSUPPORTED_GATE`: fallback explícito para uma futura operação de autorização ainda sem apresentação conhecida.

`PROPOSAL_REQUIRED` deve declarar os inputs concretos ausentes e pode fornecer um comando de materialização, mas não pode inferir os valores. Para `process.run` e `process.retry`, faltam executável, argumentos, working directory e timeout. Para `file.patch` e `file.retry`, faltam workspace, caminho relativo, trecho esperado e substituição. Para `analysis.retry`, o único input de proposta que falta é o modelo explícito; a Action anterior já vem do gate.

`READY_FOR_AUTHORIZATION` deve usar os mesmos validadores de proposta corrente do gateway natural. A apresentação inclui o ID de `executive.operation.proposed`, parâmetros congelados, Verification esperada e exemplos de respostas afirmativas aceitas, mas continua read-only. A presença dessa visão não constitui autorização e não muda `source=user`.

A CLI `executive-gate [goal_id]` expõe a visão diretamente. Comandos que já produzem uma decisão final, incluindo `executive-next`, `executive-step`, `executive-continue` e `user-turn`, podem imprimir a mesma apresentação automaticamente ao parar em `NEEDS_OPERATION_AUTHORIZATION`. O SQLite permanece no schema 11.

### 33.19. Materialização conversacional de process.run

A primeira materialização operacional por turno humano deve ser limitada a `process.run` e `process.retry`, que compartilham `ProcessRunRequest`. O gateway não usa modelo para esta etapa e não transforma texto livre em comando. A gramática inicial reconhece somente formas foreground explícitas equivalentes a `Rode <executável> [args...] neste projeto` e `Execute <executável> [args...] neste projeto`.

`neste projeto` precisa ser resolvido por um `working_directory` fornecido pelo chamador. Na CLI, o valor é o `Path.cwd()` da invocação e deve ser persistido em `user.turn.received` como `foreground_working_directory`. A resolução é contextual e determinística; não é inferência de caminho pelo modelo.

O parser precisa produzir `ProcessRunRequest` com `shell=False` implícito pelo executor existente. O primeiro corte não suporta operadores de shell, múltiplas linhas ou argumentos com aspas; nesses casos a entrada deve permanecer sem efeito e o usuário pode usar a CLI técnica de proposta.

Se a decisão atual for `NEEDS_OPERATION_AUTHORIZATION / plan.run / process.run`, a materialização chama `propose_process_run()` com `trace_id=user.turn.received.id`. Se for `NEEDS_OPERATION_AUTHORIZATION / process.retry`, o `action_id` deve vir da própria `ExecutiveDecision` e a materialização chama `propose_process_retry()`. Nenhum ID de Action pode ser extraído do texto humano.

Uma materialização bem-sucedida registra `executive.user_turn.routed` com `intent=MATERIALIZE`, `authority_scope=CURRENT_OPERATION_GATE_MATERIALIZATION_ONLY` e `effect_type=operation.proposal`. O efeito referenciado é o Event `executive.operation.proposed`; ele continua com `source=system` e não constitui grant.

Após criar a proposta, o gateway pode reconstruir o Executive para apresentar `READY_FOR_AUTHORIZATION`, mas não pode consumir a autorização no mesmo turno. Materialização e autorização exigem dois turnos semanticamente separados. A apresentação read-only de `PROPOSAL_REQUIRED` pode mostrar exemplos da gramática conversacional suportada para `process.run` e `process.retry` sem remover os comandos técnicos de fallback.

`file.patch`, `file.retry` e `analysis.retry` permanecem fora desta gramática até existir um contrato textual próprio que preserve seus parâmetros concretos sem ambiguidade. Nenhuma migration é necessária e o SQLite permanece no schema 11.
