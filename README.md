# Milu Chat Assistant API

API FastAPI do assistente virtual Milu, criada para responder perguntas sobre o portfólio **Minha História na Web** e sobre o desenvolvedor Alexandre Langa. A resposta é gerada pelo Gemini, mas os dados do portfólio são selecionados localmente antes de cada chamada usando RAG (Retrieval-Augmented Generation).

## Visão geral

Em vez de enviar todo o conteúdo do portfólio em cada pergunta, a aplicação localiza somente as seções relacionadas ao assunto perguntado. Isso reduz o contexto enviado ao modelo, deixa a resposta mais focada e diminui a chance de informações sem relação influenciarem a geração.

```text
Cliente
  │ POST /chat
  ▼
FastAPI (main.py)
  ▼
MiluService
  ├─ seleciona idioma e índice do portfólio
  ├─ recupera até 3 seções relevantes (RAG local)
  ├─ monta prompt-base + contexto recuperado + pergunta
  ▼
Gemini 2.5 Flash Lite
  ▼
Resposta JSON
```

## Estrutura do projeto

```text
.
├── main.py                         # Aplicação FastAPI e rota HTTP
├── api_documentation.py             # Metadados do Swagger/OpenAPI
├── requirements.txt                 # Dependências Python
├── prompts/
│   ├── personality_pt.py            # Personalidade fixa em português
│   ├── personality_en.py            # Personalidade fixa em inglês
│   ├── portifolio_context_pt.py     # Conhecimento do portfólio em português
│   └── portifolio_context_en.py     # Conhecimento do portfólio em inglês
└── services/
    ├── RateLimitMiddleware.py       # Rate limit para HTTP e WebSocket
    ├── MiluService.py               # Orquestra RAG, prompt e Gemini
    └── RagService.py                # Índice e algoritmo de recuperação
```

## RAG: como funciona

RAG significa *Retrieval-Augmented Generation*: primeiro recuperar conhecimento relevante; depois gerar a resposta com esse conhecimento. Nesta API, a recuperação é local, em memória, e não exige banco vetorial ou uma segunda chamada à API de IA.

### 1. Criação dos índices

Quando a aplicação é iniciada, `MiluService.py` cria dois objetos `PortfolioRetriever`:

- `PORTUGUESE_RETRIEVER`, a partir de `CONTEXTO_PORTFOLIO`;
- `ENGLISH_RETRIEVER`, a partir de `PORTFOLIO_CONTEXT`.

Os contextos são documentos Markdown organizados por títulos iniciados com `#`. O `RagService` separa cada título e seu conteúdo em um `DocumentChunk`. Por exemplo, a seção `# TECNOLOGIAS UTILIZADAS NO PROJETO` torna-se um trecho independente.

### 2. Normalização da pergunta e dos documentos

O algoritmo executa os mesmos passos nos textos do contexto e na pergunta:

1. Converte o texto para minúsculas.
2. Remove acentos usando normalização Unicode. Assim, `tecnologias` e `tecnológias` são tratados da mesma forma.
3. Extrai palavras e termos técnicos com expressão regular. Caracteres como `#`, `+` e `.` são preservados para termos como `C#`, `C++` e `.NET`.
4. Remove palavras muito comuns em português e inglês, como `de`, `para`, `the` e `with`.
5. Conta a frequência de cada termo em cada trecho com `Counter`.

### 3. Pontuação e seleção dos contextos

Para uma pergunta, cada trecho recebe uma pontuação:

- uma palavra da pergunta encontrada no conteúdo soma pontos;
- ocorrências repetidas têm ganho limitado a três ocorrências, evitando que documentos longos dominem apenas pelo tamanho;
- uma correspondência no título da seção recebe peso adicional de 5, pois o título representa o assunto principal do trecho.

Somente trechos com pontuação maior que zero participam do resultado. Eles são ordenados do maior para o menor valor, e os três primeiros são usados. Se não existir correspondência, nenhum dado factual é enviado como contexto e o modelo recebe uma mensagem explícita informando isso.

Exemplo: para a pergunta `Quais tecnologias Alexandre usa?`, a seção `TECNOLOGIAS UTILIZADAS NO PROJETO` ganha prioridade por conter o termo no título e é adicionada ao prompt.

### 4. Montagem do prompt

O serviço monta um prompt por idioma contendo:

1. A personalidade fixa da Milu;
2. As regras de resposta: idioma, linguagem simples, sem Markdown e sem inventar informações;
3. Os até três trechos recuperados;
4. A pergunta original do usuário.

O modelo é instruído a usar exclusivamente o contexto recuperado. Se a informação não estiver presente, deve explicar educadamente que sua especialidade é o projeto Minha História na Web.

### Limitações e evolução

O recuperador atual é lexical: ele busca termos em comum, não significado semântico. Perguntas que usam sinônimos muito diferentes do texto podem não recuperar a melhor seção. Para uma base maior ou busca semântica, a evolução natural é trocar/combinar este índice por embeddings e um banco vetorial. O contrato do `PortfolioRetriever` permite essa troca sem alterar o endpoint.

## Contextos e personalidades

Os arquivos em `prompts/` são a fonte de conhecimento editável da API:

| Arquivo | Finalidade |
| --- | --- |
| `personality_pt.py` | Tom, limites e comportamento da Milu em português. |
| `personality_en.py` | Equivalente em inglês. |
| `portifolio_context_pt.py` | Seções do portfólio usadas pelo RAG em português. |
| `portifolio_context_en.py` | Seções do portfólio usadas pelo RAG em inglês. |

Para adicionar conhecimento novo, inclua uma nova seção iniciada por `# ` no arquivo de contexto correspondente. Mantenha os dois idiomas alinhados. Após reiniciar a API, a nova seção será indexada automaticamente.

Exemplo:

```python
CONTEXTO_PORTFOLIO = """
# NOVO PROJETO

Nome: Projeto Exemplo
Tecnologias: Python e FastAPI
"""
```

## Requisitos

- Python 3.10 ou superior;
- uma chave da API Gemini;
- dependências listadas em `requirements.txt`.

## Configuração e execução

1. Crie e ative um ambiente virtual (opcional, mas recomendado):

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Instale as dependências:

   ```powershell
   pip install -r requirements.txt
   ```

3. Crie o arquivo `.env` na raiz do projeto e configure a chave:

   ```env
   GEMINI_API_KEY=sua_chave_aqui
   ```

4. Inicie o servidor:

   ```powershell
   uvicorn main:app --reload
   ```

Por padrão, a API estará disponível em `http://127.0.0.1:8000`. A documentação interativa do FastAPI estará em `http://127.0.0.1:8000/docs`.

O rate limit usa memória local do processo e não depende de Redis. A variável `RATE_LIMIT_REDIS_URL`, se ainda estiver cadastrada no Render, é ignorada:

```env
MAX_GEMINI_CONCURRENT_REQUESTS=5
```

Esse modo é adequado para a implantação atual de instância única. Os contadores são reiniciados quando o processo reinicia ou desperta após ficar inativo; para múltiplas instâncias, use um rate limit no gateway ou reavalie um armazenamento compartilhado.

## API

### `POST /chat`

Gera uma resposta da Milu para uma pergunta sobre o portfólio.

**Cabeçalhos**

```http
Content-Type: application/json
```

**Corpo da requisição**

| Campo | Tipo | Obrigatório | Regras |
| --- | --- | --- | --- |
| `message` | string | Sim | Entre 1 e 1000 caracteres. |
| `language` | string | Sim | Apenas `pt` ou `en`. Define a resposta e o contexto usado. |

Exemplo em português:

```json
{
  "message": "Quais tecnologias Alexandre usa?",
  "language": "pt"
}
```

Exemplo com cURL:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"Quais tecnologias Alexandre usa?\", \"language\": \"pt\"}"
```

**Resposta de sucesso — `200 OK`**

```json
{
  "success": true,
  "message": "Au au! Alexandre trabalha com tecnologias como C#, .NET, Angular, TypeScript, Java, Python e PL/SQL."
}
```

O campo `message` é texto gerado pelo modelo; portanto, seu conteúdo exato pode variar.

**Erros**

| Status | Quando acontece |
| --- | --- |
| `422 Unprocessable Entity` | Corpo ausente, `message` vazio/maior que 1000 caracteres ou `language` diferente de `pt`/`en`. |
| `413 Payload Too Large` | Corpo da requisição excede 16 KiB. |
| `500 Internal Server Error` | A variável `GEMINI_API_KEY` não foi configurada. |
| `502 Bad Gateway` | O Gemini retornou uma resposta vazia. |
| `503 Service Unavailable` | Falha no provedor ou limite de concorrência. A API retorna uma mensagem para tentar novamente mais tarde. |
| `429 Too Many Requests` | Mais de 10 chamadas por IP em uma janela móvel de 60 segundos; consulte `Retry-After`. |

### WebSocket `/chat`

O WebSocket aceita uma mensagem JSON com os mesmos campos `message` e `language`, e envia eventos `chunk`, `done` ou `error`. O limite de payload é 16 KiB por mensagem; uma mensagem maior encerra a conexão com o código `1009`.

### Health check

`GET /healthz` retorna `{"status":"ok"}` para verificações de disponibilidade do processo. Esse endpoint é de liveness e não garante que o Gemini esteja disponível.

## CORS

No estado atual, o navegador pode acessar a API apenas a partir da origem:

```text
https://alexandrelanga.github.io
```

Para desenvolvimento local ou outro frontend, ajuste `allow_origins` em `main.py` de forma restrita, adicionando somente as origens necessárias.

## Segurança e operação

- Nunca versione o arquivo `.env` ou a chave `GEMINI_API_KEY`; configure segredos no gerenciador de segredos da plataforma em produção.
- CORS restringe origens de navegador, mas não autentica clientes nem impede chamadas feitas por scripts. `allow_credentials` está desabilitado.
- Cada mensagem continua limitada a 1000 caracteres e o corpo HTTP/WebSocket a 16 KiB.
- O rate limit é de 10 chamadas por IP em 60 segundos e é local ao processo. Em Render Free, os contadores zeram quando o serviço desperta após inatividade ou reinicia; para múltiplas instâncias, aplique rate limit no gateway.
- O limite de chamadas simultâneas ao Gemini é configurável por `MAX_GEMINI_CONCURRENT_REQUESTS` (padrão: 5, por processo). Pedidos que não obtêm capacidade em um segundo recebem `503`; dimensione o valor de acordo com a quota do provedor e o número de workers.
- O cliente assíncrono Gemini é criado uma vez por processo e encerrado no shutdown. A chamada HTTP não bloqueia o event loop; ambas as rotas compartilham o limite de concorrência.
- Os limites por IP dependem do endereço que o servidor observa. Atrás de proxy, configure o encaminhamento de IPs confiáveis no servidor e no gateway; não confie indiscriminadamente em cabeçalhos enviados por clientes.
- Logs registram status e duração das requisições `/chat` e duração/sucesso das chamadas Gemini, sem registrar o texto das mensagens. Use os logs da plataforma para acompanhar latência, erros e saturação.
- A API não tem autenticação própria. Como o frontend hospedado publicamente não pode guardar um segredo, não coloque uma chave compartilhada no código JavaScript. Se forem necessários controle de acesso ou proteção contra abuso além do rate limit, aplique-os em um gateway/WAF ou use um fluxo de autenticação apropriado.
- Em produção, sirva a API somente por HTTPS e mantenha o rate limit do gateway como uma segunda barreira.
- Os testes automatizados podem ser executados com `pip install -r requirements-dev.txt` e `python -m pytest -q`; o mesmo comando é executado no GitHub Actions.
