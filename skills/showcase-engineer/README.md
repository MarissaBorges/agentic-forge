# Showcase Engineer

**Uma skill para transformar projetos em showcases profissionais no GitHub — com segurança, evidência e controle de publicação.**

`showcase-engineer` audita, prepara, cria, atualiza e mantém showcases para projetos Open Source, proprietários e híbridos. Seu foco é tornar o trabalho demonstrável sem expor código de produção, dados, segredos ou propriedade intelectual sem autorização.

## O que faz

- Auditoria read-only de projeto e repositório.
- Gate de titularidade, autorização e classificação de conteúdo.
- Auditoria de segredos, dados sensíveis e histórico Git.
- SBOM e revisão de licenças.
- Threat modeling contextual.
- Auditoria de README, documentação, links e estrutura.
- OCR e revisão de screenshots.
- Verificações de acessibilidade.
- Score de qualidade + checklist e bloqueios independentes.
- Preparação em staging, publicação aprovada e manutenção contínua.

## Instalação

Copie a pasta `showcase-engineer` para o diretório de skills do seu agente. Os scripts usam Python 3.10+ e priorizam a biblioteca padrão.

```bash
python scripts/showcase.py --help
python scripts/showcase.py inspect /caminho/do/projeto
python scripts/showcase.py audit /caminho/do/projeto
```

Dependências opcionais são descritas em `scripts/requirements.txt`.

## Filosofia de segurança

- Read-only por padrão.
- Nenhuma publicação automática.
- Aprovação por etapas.
- Projeto original preservado; mudanças em staging.
- Ferramenta ausente = `NOT RUN`, nunca `PASS`.
- Score nunca sobrepõe bloqueios de titularidade, segredos ou dados sensíveis.

## Estrutura

```text
showcase-engineer/
├── SKILL.md
├── README.md
├── scripts/
│   ├── showcase.py
│   ├── validators/
│   ├── analyzers/
│   ├── utils/
│   └── tests/
├── templates/
├── checklists/
├── workflows/
└── scoring/
```

## Escopo e limitações

Os validadores locais são heurísticos. Não substituem revisão humana, análise jurídica, ferramentas especializadas nem autorização do titular. A skill não presume que tenha acesso ao browser, GitHub ou serviços externos: deve descobrir as capacidades disponíveis e registrar limitações.

## Nome

**Showcase Engineer** é o nome de produto; `showcase-engineer` é o slug. É suficientemente específico para ser encontrado em um repositório maior de skills e não limita a skill a apenas escrever READMEs.
