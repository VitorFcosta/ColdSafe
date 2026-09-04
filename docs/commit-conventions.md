# Convenção de commits do ColdSafe

O histórico do projeto deve explicar decisões, não apenas registrar que arquivos mudaram.

## Formato obrigatório

```text
<tipo>(<escopo>): <descrição>
```

O escopo é recomendado quando deixa a área afetada mais clara, mas pode ser omitido em mudanças que abrangem o repositório inteiro.

## Tipos permitidos

| Tipo | Quando usar |
| --- | --- |
| `feat` | Nova capacidade observável do sistema. |
| `fix` | Correção de comportamento incorreto. |
| `refactor` | Mudança interna sem alterar comportamento. |
| `docs` | Documentação sem mudança de comportamento. |
| `test` | Inclusão ou correção de testes. |
| `chore` | Manutenção, configuração ou organização. |
| `perf` | Melhoria de desempenho. |
| `ci` | Pipeline de integração ou entrega contínua. |
| `revert` | Reversão explícita de um commit anterior. |

## Escopos sugeridos

- `repo`: estrutura e configuração geral.
- `contracts`: JSON Schema, OpenAPI e exemplos compartilhados.
- `backend`: FastAPI, MQTT, domínio e persistência.
- `frontend`: Vue, componentes e experiência do operador.
- `firmware`: ESP32, DHT22 e Wokwi.
- `infra`: Docker, Mosquitto, InfluxDB e operação.
- `docs`: documentação técnica e acadêmica.
- `deps`: dependências e versões.
- `qa`: integração, E2E e demonstração.
- `security`: credenciais, permissões e validações de segurança.

## Regras da descrição

1. Registrar uma única mudança lógica por commit.
2. Usar verbo no presente: `adiciona`, `corrige`, `define`, `remove`.
3. Começar com letra minúscula.
4. Não terminar com ponto final.
5. Manter a primeira linha com no máximo 72 caracteres.
6. Explicar o motivo no corpo quando ele não for óbvio pelo título.
7. Nunca usar mensagens vagas como `update`, `ajustes`, `mudanças` ou `WIP`.

## Exemplos válidos

```text
chore(repo): inicializa estrutura do ColdSafe
feat(contracts): define contratos MQTT e HTTP
test(contracts): valida respostas previstas pela API
fix(contracts): permite status em leituras históricas
docs(repo): registra convenção de commits
```

## Mudança incompatível

Uma alteração que quebra consumidores existentes usa `!` e explica a incompatibilidade no rodapé:

```text
feat(contracts)!: altera payload de telemetria

BREAKING CHANGE: o campo temperature foi substituído por temperature_c.
```

## Checklist antes do commit

- O commit contém apenas uma mudança lógica.
- Os testes relacionados passaram.
- `git diff --staged` foi revisado.
- Nenhum segredo, `.env` ou arquivo temporário foi incluído.
- A mensagem segue o formato desta página.

## Ativar o template local

Execute uma vez na raiz do projeto:

```bash
git config --local commit.template .gitmessage
```

Depois, `git commit` abrirá o editor com lembretes da convenção. O template orienta, mas ainda não bloqueia mensagens inválidas; essa validação será adicionada ao CI quando o pipeline do projeto existir.
