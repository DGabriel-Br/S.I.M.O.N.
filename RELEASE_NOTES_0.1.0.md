# S.I.M.O.N. 0.1.0

Primeira versão estável do núcleo persistente do S.I.M.O.N.

## O que esta versão estabelece

O v0.1 transforma o projeto em um Core local capaz de manter estado fora do contexto do modelo. Goals, Plans, Actions, Events, VerificationResults, Experiences e Memories sobrevivem a reinicializações e permanecem auditáveis. O modelo participa de decisões cognitivas estruturadas, mas não é a fonte da persistência nem da verdade operacional do sistema.

A versão fecha o primeiro ciclo completo:

```text
USER
-> INTENT
-> GOAL
-> PLAN
-> ACT
-> OBSERVE
-> VERIFY
-> RETRY ou REPLAN
-> GOAL COMPLETED
-> EXPERIENCE
-> MEMORY
-> RESTART
-> CONTINUE
```

## Destaques

- persistência SQLite com schema 11 e migrations versionadas;
- Goals e Plans revisionados com critérios de sucesso explícitos;
- execução de processos sem shell implícito;
- análise cognitiva sobre evidência previamente verificada;
- patch localizado de arquivo dentro de workspace autorizado;
- Verification separada de execução e baseada na evidência mais recente;
- retries explícitos para falhas operacionais;
- replanejamento quando a evidência invalida a estratégia;
- retomada após restart sem depender da sessão anterior do modelo;
- lock exclusivo para impedir duas instâncias sobre o mesmo diretório de dados;
- Experience causal no fechamento do Goal;
- promoção explícita de Experience para Memory;
- wheel e sdist com entry point `simon` e migrations empacotadas.

## Validação da release

Antes da promoção, o release candidate `0.1.0rc1` passou no ambiente oficial Python 3.14.7 por:

```text
282 testes
Ruff: verde
mypy strict: verde em 42 módulos
smoke do wheel/sdist: verde
criação limpa: schema 11
upgrade real: schema 7 -> 11 preservando dados
```

A promoção para `0.1.0` não adiciona novas capabilities ou altera contratos do Core. Ela apenas congela e documenta o estado aprovado no RC.

## Limites conhecidos

O v0.1 ainda não possui Executive/Attention persistente, seleção automática de Memory, invalidação automática de Plans por assumptions, roteamento entre modelos, busca vetorial, visão, voz ou interface gráfica. O runtime é exclusivo por diretório de dados e efeitos externos interrompidos continuam exigindo decisão explícita antes de retry.

Esses itens são escopo da fase seguinte, não pendências necessárias para a estabilidade deste núcleo.

## Compatibilidade

- pacote: `simon-local==0.1.0`;
- Python: `>=3.14,<3.15`;
- SQLite schema: 11.
