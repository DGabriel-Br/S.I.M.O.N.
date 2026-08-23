# Changelog

Todas as mudanças relevantes do S.I.M.O.N. serão registradas neste arquivo.

## [Unreleased]

### Adicionado

- início da linha de desenvolvimento `0.2.0.dev0` para a Fase 2, preservando `0.1.0` como release estável;
- primeiro `ExecutiveDecision` determinístico e read-only sobre `resume` e `PlanReadiness`;
- comando `executive-next` para inspecionar a próxima operação legítima ou o gate atual sem executá-lo;
- decisões estruturadas para seleção de Goal, input humano, confirmação, autorização operacional, retry, replanejamento, Verification e conclusão de Plan/Goal.
- runner foreground `executive-step` que executa no máximo uma decisão `PROCEED` segura por chamada e reavalia o estado sem continuar o ciclo;
- detecção de propostas de Plan pendentes, separando explicitamente `plan.propose` de `plan.materialize` em ciclos diferentes;
- serviço reutilizável de proposta de Plan, preservando o gate que impede chamada ao modelo quando um Plan ACTIVE saudável ainda possui resolução local.
- Golden Scenario integrado do Executive atravessando autorizações reais, Verifications automáticas, cognição, confirmações humanas e múltiplos restarts até `DONE`, sem loop monolítico ou nova migration.
- condutor foreground `executive-continue` que encadeia operações `PROCEED` seguras, reconstrói o estado entre transições e para no primeiro gate, falta de modelo, falha, `DONE` ou limite explícito.
- gateway `user-turn` para registrar um turno humano com provenance explícita e rotear somente o intent determinístico `CONTINUE` ao condutor seguro, sem converter linguagem natural em autorização operacional.
- respostas humanas vinculadas ao gate atual: texto livre responde somente a `user.ask` em `WAITING`, confirmações afirmativas explícitas confirmam somente o assessment ou Goal atualmente solicitado, e `NEEDS_OPERATION_AUTHORIZATION` continua exigindo comando operacional concreto.
- proposta concreta de `process.run` persistida antes da autorização natural: `process-propose` registra executável, argv, cwd e timeout sem criar Action; um turno afirmativo posterior só pode autorizar a proposta mais recente que ainda corresponda ao gate atual.
- proposta concreta de `file.patch` no mesmo contrato: `file-propose` registra workspace, arquivo relativo, trecho esperado e substituição sem modificar o filesystem; um turno afirmativo posterior só pode aplicar a proposta atual revalidada contra Goal, Plan, revisão e step.

## [0.1.0] - 2026-08-19

Primeira versão estável do núcleo persistente do S.I.M.O.N.

### Garantias do núcleo

- estado durável em SQLite com migrations contíguas até o schema 11;
- Goals persistentes com critérios de sucesso e lifecycle explícito;
- Plans revisionados, ligados à revisão do World em que foram criados;
- Actions e Events imutáveis com provenance entre Goal, Plan e step;
- Verification separada de execução, sempre considerando a tentativa e a conclusão epistemológica mais recentes;
- execução controlada de `process.run`, análise por `cognition.analyze` e alteração localizada por `file.patch`;
- retries explícitos para falhas operacionais de `process.run`, `cognition.analyze` e `file.patch`;
- replanejamento explícito quando evidência negativa ou inconclusiva invalida a estratégia atual;
- retomada após restart sem depender do contexto anterior do modelo;
- lock exclusivo por diretório de dados para impedir dois runtimes concorrentes sobre o mesmo estado;
- conclusão de Plan e Goal baseada em evidência atual, com revalidação antes do fechamento;
- consolidação de Experience ao concluir Goals e promoção explícita de Experience para Memory;
- `world_revision` monotônica para alterações na visão atual do World;
- adapter local para Ollama através do contrato `ModelProvider`;
- wheel e sdist instaláveis com migrations incluídas e entry point `simon`;
- criação limpa do banco e upgrade real de schema 7 para 11 preservando dados validados pelo smoke de distribuição.

### Qualidade validada antes da promoção

O release candidate `0.1.0rc1` foi aprovado no runtime oficial Python 3.14.7 com:

- 282 testes automatizados;
- Ruff sem erros;
- mypy strict sem erros em 42 módulos de código-fonte;
- smoke do wheel/sdist instalado em ambiente virtual temporário;
- validação de `simon`, `python -m simon`, migrations empacotadas, banco limpo e upgrade 7 -> 11.

### Limites deliberados do v0.1

- apenas um runtime por diretório de dados;
- nenhum retry automático de efeitos externos incertos;
- `world_revision` é informativa e ainda não invalida Plans automaticamente;
- Memories só são criadas por promoção explícita de uma Experience;
- não há Executive/Attention persistente;
- não há roteamento automático entre modelos;
- não há busca vetorial, visão, voz ou interface gráfica;
- `file.patch` continua sendo binding operacional especializado de `CHANGE/unknown`, e não uma capability genérica escolhida pelo Planner.

### Compatibilidade

- Python: `>=3.14,<3.15`;
- schema SQLite: 11;
- distribuição: `simon-local==0.1.0`.
