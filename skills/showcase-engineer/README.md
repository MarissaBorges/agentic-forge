<!-- BADGES -->

<p align="center">
  <img src="https://img.shields.io/badge/Status-Est%C3%A1vel-brightgreen?style=for-the-badge" alt="Status: Estável">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3670A0?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/Git-Auditoria-F05032?style=for-the-badge&logo=git&logoColor=white" alt="Git">
  <img src="https://img.shields.io/badge/AI%20Skill-Showcase%20Engineering-6C5CE7?style=for-the-badge" alt="AI Skill">
</p>

<h1 align="center">Showcase Engineer 🛡️</h1>

<p align="center">
  <strong>Transforme projetos de software em showcases profissionais, documentados e seguros para publicação.</strong>
</p>

<p align="center">
  <a href="#-visão-geral">Visão geral</a> •
  <a href="#-funcionalidades">Funcionalidades</a> •
  <a href="#-arquitetura">Arquitetura</a> •
  <a href="#-como-executar">Como executar</a> •
  <a href="#-segurança-e-publicação">Segurança</a> •
  <a href="#-roadmap">Roadmap</a> •
  <a href="#-colaboradores">Colaboradores</a>
</p>

---

## 📌 Visão geral

A **Showcase Engineer** é uma skill para agentes de IA que auxilia no processo de transformar projetos de software em showcases públicos no GitHub.

Seu objetivo é permitir que desenvolvedores apresentem projetos a recrutadores, clientes e comunidades técnicas sem expor indevidamente código de produção, credenciais, dados pessoais, informações empresariais ou propriedade intelectual de terceiros.

A skill cobre o ciclo de vida do showcase: auditoria inicial, classificação do conteúdo, preparação de uma cópia de publicação, documentação, captura e revisão de evidências visuais, validação, publicação aprovada e manutenção contínua.

Ela foi projetada para três modelos de distribuição:

- **Open Source:** projetos publicados sob uma licença aprovada pelo titular, com possibilidade de contribuições.
- **Proprietário/comercial:** projetos cuja implementação, regras de negócio ou infraestrutura devem permanecer privadas.
- **Híbrido:** projetos que disponibilizam componentes selecionados, mantendo outros módulos privados.

> Um repositório público não é automaticamente Open Source. A publicação depende de titularidade, autorização e escolha explícita de licença.

---

## 🚀 Funcionalidades

### Auditoria e classificação do projeto

- Inventário de arquivos, diretórios e extensões.
- Identificação de possíveis credenciais, tokens e chaves privadas.
- Detecção heurística de possíveis dados pessoais, como e-mails, CPFs e telefones.
- Inspeção inicial de referências e caminhos presentes no histórico Git.
- Verificação básica da documentação, links locais e estrutura do repositório.
- Classificação do conteúdo como publicável, sanitizável, privado ou bloqueado.

### Preparação do showcase

- Planejamento de um repositório público separado do ambiente de produção.
- Preparação de documentação baseada em funcionalidades verificáveis.
- Template de README com visão geral, funcionalidades, demonstração, arquitetura, stack, execução, testes, roadmap e licenças.
- Organização de checklists e relatórios de auditoria.
- Orientação para screenshots reais obtidas em ambientes autorizados e com dados sintéticos.

### Segurança e conformidade

A metodologia prevê verificações complementares que podem ser realizadas por ferramentas especializadas, conforme disponibilidade:

- Threat modeling para identificar ativos, fronteiras de confiança e cenários de abuso.
- Geração de SBOM nos formatos CycloneDX ou SPDX.
- Auditoria de licenças de dependências e assets.
- Análise do histórico Git com scanners especializados.
- OCR de screenshots para auxiliar na identificação de informações sensíveis.
- Verificações automatizadas e manuais de acessibilidade.

Quando uma ferramenta não estiver disponível ou uma verificação não for executada, o resultado é registrado como `NOT RUN`, nunca como aprovado.

### Avaliação e prontidão para publicação

A abordagem combina dois mecanismos:

1. **Quality Score (0–100):** indicador de qualidade do showcase, considerando segurança, documentação, evidências técnicas, apresentação visual, reprodutibilidade e acessibilidade.
2. **Checklist:** resultados individuais `PASS`, `WARN`, `FAIL`, `N/A` ou `NOT RUN`, acompanhados de evidências e limitações.

A pontuação não substitui os bloqueios obrigatórios. Uma credencial exposta, autorização pendente ou dado sensível pode impedir a publicação independentemente da nota.

---

## 🧭 Fluxo de trabalho

```text
Descoberta e definição do escopo
              │
              ▼
Verificação de titularidade e autorização
              │
              ▼
Inventário e classificação dos arquivos
              │
              ▼
Auditoria técnica e análise de ameaças
              │
              ▼
Plano do showcase e aprovação
              │
              ▼
Preparação isolada em staging
              │
              ▼
Documentação, browser e screenshots
              │
              ▼
Validação, score e checklist
              │
              ▼
Aprovação para repositório e publicação
              │
              ▼
Manutenção e reauditorias
```

A skill trabalha com aprovação por etapas. Autorizar uma fase não significa autorizar automaticamente as seguintes. Criação de repositório remoto, alteração de visibilidade, commit, push e publicação exigem aprovação explícita.

---

## 🏗️ Arquitetura

A skill é organizada em três camadas principais:

| Camada | Responsabilidade |
|---|---|
| Instruções e workflows | Definir decisões, etapas, aprovações e comportamento do agente |
| Scripts e validadores | Executar verificações locais e produzir resultados estruturados |
| Templates, checklists e scoring | Padronizar documentação, relatórios e critérios de avaliação |

### Estrutura do pacote

```text
showcase-engineer/
├── SKILL.md
├── README.md
├── scripts/
│   ├── showcase.py
│   ├── validators/
│   │   ├── project_inventory.py
│   │   ├── secrets_audit.py
│   │   ├── sensitive_data_audit.py
│   │   ├── git_history_audit.py
│   │   ├── documentation_audit.py
│   │   ├── link_checker.py
│   │   └── repository_structure.py
│   ├── analyzers/
│   │   └── quality_score.py
│   ├── utils/
│   ├── requirements.txt
│   └── tests/
├── templates/
│   ├── README-showcase-template.md
│   ├── AUDIT-REPORT-template.md
│   ├── THREAT-MODEL-template.md
│   └── SBOM-REPORT-template.md
├── checklists/
├── workflows/
└── scoring/
```

---

## 💻 Como executar

### Pré-requisitos

- Python 3.10 ou superior (biblioteca padrão).
- Git instalado para as verificações relacionadas a repositórios.

### Executar a CLI

A partir da raiz da skill ou repositório:

```bash
# Consultar comandos disponíveis
python scripts/showcase.py --help

# Inspecionar um projeto sem modificá-lo
python scripts/showcase.py inspect /caminho/do/projeto

# Executar auditoria completa com Quality Score
python scripts/showcase.py audit /caminho/do/projeto

# Inspecionar histórico Git nas referências acessíveis
python scripts/showcase.py audit-git /caminho/do/projeto

# Validar documentação e links locais
python scripts/showcase.py validate-docs /caminho/do/projeto
```

Para obter saída estruturada em JSON:

```bash
python scripts/showcase.py audit /caminho/do/projeto --json
```

### Testes

A suíte nativa pode ser executada sem dependências extras com o `unittest` padrão:

```bash
python -m unittest discover -s scripts/tests/
```

---

## 🔒 Segurança e publicação

A Showcase Engineer adota uma postura estritamente conservadora:

- **Read-only por padrão:** a auditoria não altera o projeto original.
- **Staging isolado:** sanitizações e materiais de publicação são preparados em uma cópia.
- **Aprovação humana:** nenhuma publicação ou alteração remota é implícita.
- **Sem segredos no showcase:** credenciais devem ser removidas e revogadas/rotacionadas.
- **Dados sintéticos:** demonstrações não contêm dados reais de clientes, pacientes ou usuários.
- **Histórico Git:** remover arquivo no commit atual não elimina conteúdo de commits antigos.
- **Licenças:** a skill nunca adiciona licença sem confirmação de titularidade e autorização.

---

## 🗺️ Roadmap

### Implementado na CLI inicial

- [x] Inventário estrutural do projeto.
- [x] Detecção heurística de padrões de segredos e tokens.
- [x] Detecção heurística de dados pessoais (CPF, e-mail, telefone BR).
- [x] Inspeção de referências e caminhos do Git.
- [x] Verificação de integridade de README e links locais.
- [x] Verificação estrutural simples do repositório.
- [x] Saída em texto formatado e JSON.
- [x] Cálculo calibrado de Quality Score e bloqueios obrigatórios.
- [x] Suíte de testes unitários com biblioteca padrão.

### Próximas evoluções

- [ ] Integração com Gitleaks para varredura profunda de blobs antigos.
- [ ] Geração de SBOM nos padrões CycloneDX e SPDX.
- [ ] Auditoria automatizada de licenças com ferramentas dedicadas.
- [ ] Suporte a OCR em imagens para detecção visual de credenciais/PII.
- [ ] Integração com ferramentas automatizadas de acessibilidade (axe-core, Pa11y).

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](../../LICENSE) para obter detalhes.

---

## 🤝 Colaboradores

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/MarissaBorges">
        <img src="https://github.com/MarissaBorges.png?size=100" width="100px;" alt="Foto de Marissa Borges"/><br>
        <sub>
          <b>Marissa Borges</b>
        </sub>
      </a>
    </td>
  </tr>
</table>

---

<p align="center">
  <sub>Showcase Engineer — documentação baseada no estado verificado da implementação.</sub>
</p>
