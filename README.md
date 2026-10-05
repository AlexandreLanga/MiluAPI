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
| `500 Internal Server Error` | A variável `GEMINI_API_KEY` não foi configurada. |
| `502 Bad Gateway` | O Gemini retornou uma resposta vazia. |
| `503 Service Unavailable` | Falha no provedor, como limite de quota, timeout ou erro de autenticação. A API retorna uma mensagem amigável no idioma selecionado. |

## CORS

No estado atual, a API aceita requisições apenas da origem:

```text
https://alexandrelanga.github.io
```

Para desenvolvimento local ou outro frontend, ajuste `allow_origins` em `main.py` de forma restrita, adicionando somente as origens necessárias.

## Segurança

- Nunca versione o arquivo `.env` ou a chave `GEMINI_API_KEY`.
- Mantenha a lista de origens CORS específica em produção.
- O endpoint limita cada mensagem a 1000 caracteres e permite até 10 mensagens por IP a cada 60 segundos; respostas acima do limite usam HTTP `429` e informam quando tentar novamente pelo cabeçalho `Retry-After`.
- As chamadas ao Gemini têm timeout de 30 segundos. A rota HTTP síncrona é executada no thread pool do FastAPI para não bloquear o event loop.
- O rate limit em memória é local a cada processo e não substitui controles de borda. Em implantações com múltiplos workers ou réplicas, configure também um limite compartilhado no proxy ou gateway.
- A API não possui autenticação própria. Caso seja exposta publicamente, considere autenticação e controles adicionais no proxy ou gateway.
