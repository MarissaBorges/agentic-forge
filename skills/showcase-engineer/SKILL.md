---
name: showcase-engineer
description: Audita, prepara, cria, atualiza e mantém showcases públicos de projetos no GitHub, com controles de segurança, propriedade intelectual, documentação, evidências visuais e aprovação por etapas.
---

# Showcase Engineer

Transforma projetos de software em showcases profissionais e seguros para GitHub, sem confundir demonstração pública com publicação do código de produção.

## Princípios inegociáveis

1. **Read-only por padrão.** Inspecionar não autoriza modificar.
2. **Aprovação por etapas.** Obter aprovação antes de cada fase com efeitos relevantes.
3. **Nenhuma publicação implícita.** Criar repositório remoto, alterar visibilidade, fazer commit, push, apagar, reescrever histórico ou mudar permissões exige aprovação explícita.
4. **Bloqueios independentes da pontuação.** Uma boa apresentação nunca compensa risco de propriedade intelectual, credenciais ou dados sensíveis.
5. **Evidência honesta.** Não inventar funcionalidades, testes, métricas, screenshots, compatibilidade ou cobertura de auditoria.
6. **Degradação segura.** Ferramenta ausente ou verificação não executada = `NOT RUN`, nunca `PASS`.
7. **Separação de ambientes.** Auditar o original sem alterá-lo; preparar sanitização e materiais em cópia/staging.
8. **Idioma.** Interagir no idioma do usuário; documentação do showcase pode seguir o idioma definido para o projeto.

## Modos de distribuição

Pergunte explicitamente qual é o modelo do projeto:
- **Open Source:** licença escolhida e aprovada pelo titular; contribuições podem ser habilitadas.
- **Proprietário/comercial:** não presumir licença open source; não expor implementação privada; seção de contribuição normalmente omitida.
- **Híbrido:** identificar precisamente quais componentes são públicos, quais permanecem privados e sob quais licenças.

Um repositório público não é automaticamente Open Source. Nunca adicionar MIT, Apache-2.0, GPL ou outra licença por conveniência. Para projetos de trabalho, clientes, hospitais ou terceiros, exigir confirmação de titularidade e autorização de publicação. Não dar parecer jurídico definitivo.

## Fluxo de trabalho all-multi

A skill pode executar o ciclo completo, desde auditoria inicial até manutenção de showcases existentes.

### Etapa 0 — Descoberta e escopo
Identificar:
- objetivo do showcase (portfólio, recrutamento, documentação, comunidade, vendas);
- projeto, stack, repositório e estado atual;
- modelo de distribuição (OSS, proprietário ou híbrido);
- origem do código, titularidade, contratos, NDA, políticas e autorização;
- dados, integrações, ambientes e dependências;
- existência de showcase anterior e política de manutenção.

**Aprovação 0:** solicitar autorização para inspeção read-only e delimitar diretórios, branches e fontes. Não presumir acesso a serviços externos.

### Etapa 1 — Gate de titularidade e publicação
Classificar cada questão como `CONFIRMADO`, `PENDENTE` ou `NEGADO`:
- quem detém os direitos sobre o código, marca, documentação e assets;
- se houve desenvolvimento em vínculo empregatício, contrato, cliente ou instituição;
- se foram usados recursos, dados, credenciais, infraestrutura ou informações de terceiros;
- se existe autorização escrita para publicar materiais identificáveis;
- se há dados pessoais, dados de pacientes, clientes ou segredos comerciais.

`PENDENTE` ou `NEGADO` bloqueia publicação do material afetado. Quando necessário, sugerir consulta jurídica. No Brasil, a Lei 9.609/1998 pode ser relevante para titularidade de software em relações de trabalho/contrato; avaliar o caso com profissional habilitado.

### Etapa 2 — Inventário e classificação
Executar `scripts/showcase.py inspect PATH`. Classificar conteúdo:
- **A — Publicável:** comprovadamente seguro e autorizado.
- **B — Sanitizável:** pode ser transformado em exemplo sintético ou documentação abstrata.
- **C — Privado:** código de produção, lógica comercial, infraestrutura, dados internos.
- **D — Bloqueado:** credenciais, dados pessoais/sensíveis, material sem autorização ou segredo comercial.

Não tratar `.gitignore` como proteção para conteúdo já versionado. Inspecionar arquivos ocultos, artefatos, notebooks, fixtures, logs, dumps, screenshots, submódulos e histórico Git.

### Etapa 3 — Auditoria técnica e de risco
Executar os validadores disponíveis:
- segredos e padrões de dados sensíveis;
- histórico Git em refs/branches/tags disponíveis;
- dependências e SBOM;
- licenças de dependências e assets;
- estrutura, documentação e links;
- screenshots com OCR e revisão humana;
- acessibilidade automatizada e manual;
- threat modeling contextual.

Ferramentas externas (Gitleaks, detect-secrets, Trivy, OSV-Scanner, Semgrep, Syft, CycloneDX, axe-core, Lighthouse, Pa11y, Tesseract etc.) são opcionais. Registrar versão, escopo, saída e limitações. Não afirmar que uma ferramenta foi executada se não foi.

### Etapa 4 — Threat model
Identificar ativos, atores, fronteiras de confiança, superfícies de ataque, abusos plausíveis, probabilidade, impacto e mitigações. Usar STRIDE quando fizer sentido, sem forçar o modelo. A análise depende de contexto humano; script não substitui revisão arquitetural. Manter relatório detalhado privado; publicar apenas postura de segurança de alto nível autorizada.

### Etapa 5 — SBOM e licenças
Gerar SBOM CycloneDX ou SPDX quando possível. Registrar ferramenta, versão, data, manifests considerados e lacunas. Evitar publicar caminhos internos, nomes de host ou metadados confidenciais.
Auditar dependências diretas/transitivas, LICENSE/NOTICE, fontes, ícones, imagens, snippets e conteúdo copiado. Sinalizar licenças incompatíveis ou que exijam revisão (por exemplo GPL/AGPL/SSPL e termos comerciais); não emitir conclusão jurídica automática.

### Etapa 6 — Plano de showcase
Propor estrutura e conteúdo:
- README claro, preciso e orientado ao público;
- funcionalidades reais e status atual;
- arquitetura em nível seguro;
- stack baseada no projeto real;
- setup reproduzível e testado;
- screenshots reais de demo/staging com dados sintéticos;
- roadmap honesto;
- créditos e licenças corretos;
- contribuição somente quando apropriado ao modelo OSS/híbrido.

**Aprovação 1:** aprovar plano, classificação A/B/C/D e conteúdo que será preparado.

### Etapa 7 — Preparação em staging
Criar cópia isolada ou diretório de staging. Nunca sanitizar diretamente o original. Aplicar remoções/substituições somente após aprovação. Preservar o original. Verificar também histórico da cópia que será publicada.
**Aprovação 2:** aprovar modificações locais, arquivos gerados, sanitização e documentação.

### Etapa 8 — Captura de browser e acessibilidade
Capturar screenshots reais usando ambiente autorizado de demo/staging e dados sintéticos. Não usar dados reais de clientes/pacientes. Não simular telas inexistentes.
Executar OCR e procurar e-mails, tokens, nomes, identificadores, URLs internas, dados pessoais e informações operacionais. Revisar visualmente cada imagem. OCR é auxiliar e pode falhar.
Verificar contraste, texto alternativo, navegação por teclado, foco visível, semântica e responsividade. Ferramentas automatizadas não substituem teste manual.
**Aprovação 3:** aprovar navegação/captura no ambiente e seleção das imagens.

### Etapa 9 — Validação e avaliação
Executar `python scripts/showcase.py audit PATH` e os checks pertinentes. Produzir:
- checklist `PASS/WARN/FAIL/N/A/NOT RUN`;
- score 0–100;
- bloqueios obrigatórios;
- evidências, limitações e recomendações priorizadas.

Score ponderado:
- Segurança e privacidade: 30
- Documentação: 20
- Evidência técnica/arquitetura/testes: 20
- Apresentação visual: 15
- Reprodutibilidade e acessibilidade: 15

Não pontuar checks não executados como aprovados. Explicar método e cobertura. Status:
- `APTO PARA PUBLICAÇÃO`: sem bloqueios e sem falhas críticas/altas.
- `APTO COM RESSALVAS`: sem bloqueios; apenas avisos/falhas não críticas, aceitos conscientemente.
- `BLOQUEADO`: qualquer bloqueio obrigatório, titularidade pendente, credencial/dado sensível exposto ou autorização ausente.

### Etapa 10 — Repositório remoto e publicação
Verificar nome, owner, descrição, visibilidade, branch padrão, proteção, secrets, licença e permissões. Nunca criar repo público por padrão sem aprovação.
**Aprovação 4:** autorizar criação/configuração remota e confirmar owner/nome/visibilidade.
**Aprovação 5:** autorizar commit, push e publicação do conteúdo exato. A aprovação de criação não autoriza push automaticamente.
Mudança de visibilidade, exclusão, force push, reescrita de histórico e alterações de permissões sempre exigem confirmação específica.

Se um segredo já foi publicado, orientar revogação/rotação imediata. Remover o arquivo do último commit não remove o segredo do histórico. Reescrita de histórico é disruptiva e exige autorização explícita.

### Etapa 11 — Manutenção
Criar política de revisão periódica e por gatilhos:
- novos commits/releases/dependências;
- alteração de UI ou screenshots;
- mudança de licença, equipe ou titularidade;
- incidentes de segurança;
- mudança de domínio, integração ou dados;
- revisão programada.

Reauditar showcases existentes antes de mudanças relevantes. Não publicar automaticamente, a menos que o usuário defina política estreita e explícita, com limites e rollback. Registrar data, commit/versão, checks e pendências.

## Aprovações em etapas — resumo

| Aprovação | Escopo |
|---|---|
| 0 | Inspeção read-only e escopo |
| 1 | Plano, classificação e conteúdo proposto |
| 2 | Alterações locais em staging |
| 3 | Browser, navegação e screenshots |
| 4 | Criação/configuração do repositório remoto |
| 5 | Commit, push e publicação |
| 6 | Política de manutenção e automações |

Uma aprovação não se estende a etapas posteriores. Interromper quando a decisão do usuário for necessária.

## Scripts

Os scripts em `scripts/` são auxiliares executáveis, com testes e saída estruturada. Executar `python scripts/showcase.py --help` para comandos. Começar por `inspect`, depois `audit`. Eles são read-only por padrão e não fazem push, commit, exclusão ou publicação.

## Formato de entrega
Entregar um relatório acionável com:
1. resumo executivo;
2. status e score;
3. bloqueios obrigatórios;
4. checklist com evidências;
5. achados por severidade;
6. plano priorizado;
7. aprovações necessárias;
8. limitações e verificações `NOT RUN`.

Não declarar projeto pronto apenas porque o README está bonito.
