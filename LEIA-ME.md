# fiscal-data-mirror

Mirror versionado de dados fiscais brasileiros (CONFAZ + 27 SEFAZ) para
consumo público via `raw.githubusercontent.com`.

**Arquitetura:**

```
CONFAZ + 27 SEFAZ  ──►  scraper.py (semanal)  ──►  data/fiscal-data.json
                                                       │
                                                       ▼
                                          App Lovable (useFiscalData)
                                          + P9 (sync → Supabase)
```

**Quem atualiza:** GitHub Action toda **segunda 06:00 UTC**.
**Quem lê:** Qualquer consumidor que fizer `fetch` do
`raw.githubusercontent.com/SEU_USUARIO/fiscal-data-mirror/main/data/fiscal-data.json`.

## Estrutura

```
fiscal-data-mirror/
├── .github/workflows/update.yml      # Cron + dispatch + fallback
├── config/sefaz_urls.json            # 27 UFs × 1-3 fontes cada
├── scripts/scraper.py                # 3 coletores + retry + diff
├── data/
│   ├── fiscal-data.json              # Output (gerado)
│   └── .last_hash                    # Para diff detection
├── requirements.txt
└── LEIA-ME.md                        # Este arquivo
```

## Setup no GitHub (1 vez)

### 1) Criar o repo

```bash
# Opção A: criar via CLI
gh repo create fiscal-data-mirror --public --description "Mirror fiscal CONFAZ + 27 SEFAZ"
cd fiscal-data-mirror
git init
git branch -M main

# Opção B: criar no github.com/new, depois:
git clone https://github.com/SEU_USUARIO/fiscal-data-mirror
cd fiscal-data-mirror
```

### 2) Colar os arquivos

Copie cada arquivo deste pacote para o path correspondente:

| Arquivo fonte | Destino no repo |
|---|---|
| `scripts/scraper.py` | `scripts/scraper.py` |
| `config/sefaz_urls.json` | `config/sefaz_urls.json` |
| `.github/workflows/update.yml` | `.github/workflows/update.yml` |
| `requirements.txt` | `requirements.txt` |
| `data/fiscal-data.json` | `data/fiscal-data.json` (opcional, só pra evitar primeiro commit vazio) |

Crie o diretório `data/` se ainda não existir:
```bash
mkdir -p data
```

### 3) Primeiro commit (seed manual)

Para o scraper não começar do zero, faça o seed inicial copiando o
`data_fiscal_data_v1.json` que você já tem (ou deixe o scraper criar
um JSON mínimo no primeiro run):

```bash
# Se você já tem o JSON do outro projeto, use-o:
cp /caminho/do/data_fiscal_data_v1.json data/fiscal-data.json
echo "$(sha256sum data/fiscal-data.json | awk '{print $1}')" > data/.last_hash

# Senão, deixe vazio — o scraper criará no primeiro run
git add -A
git commit -m "feat: setup mirror + scraper (P8)"
git push -u origin main
```

### 4) Configurar permissão de escrita (Actions)

A Action precisa de permissão para fazer `git push`. Em
**Settings → Actions → General → Workflow permissions**, selecione:

- ✅ **Read and write permissions**
- ✅ **Allow GitHub Actions to create and approve pull requests** (opcional)

### 5) Testar manualmente

Vá em **Actions → "Atualizar fiscal-data.json" → Run workflow**.
Marque ou não "force_commit" e clique em **Run workflow**.

O log deve mostrar:

```
[CONFAZ] Coletando CESTs do Convênio 92/2015
[CONFAZ] N CESTs coletados
[MVA/BA] M MVAs extraídos de https://...
[ALIQ] Usando tabela de referência 2026 (27 UFs)
=== Escrito data/fiscal-data.json (hash abc123..., N CESTs, M UFs com MVA) em Y.Ys ===
```

Se aparecer "Sem mudanças (hash ...)" e force_commit=false, é porque o
JSON já estava igual ao último commit.

## URLs consumidas pelo app Lovable

Após o primeiro commit, o JSON fica disponível em:

```
https://raw.githubusercontent.com/SEU_USUARIO/fiscal-data-mirror/main/data/fiscal-data.json
```

No **app Lovable antigo (useFiscalData)**, aponte a env var:

```bash
# .env do Lovable
VITE_FISCAL_MIRROR_URL=https://raw.githubusercontent.com/SEU_USUARIO/fiscal-data-mirror/main/data/fiscal-data.json
```

No **app TanStack Start atual (P9)**, a mesma URL entra como
`process.env.VITE_FISCAL_MIRROR_URL` no `sync-mirror.functions.ts`.

## Configurando novas fontes SEFAZ

Edite `config/sefaz_urls.json`. Cada UF tem uma lista de fontes em
ordem de prioridade; o scraper aceita a primeira que responder 200 com
tabela válida.

Para descobrir a URL correta de uma UF, vá em
[sefaz.gov.br da UF] → Legislação → RICMS → Anexo [I/II/etc] (geralmente
tabela com CEST × MVA).

Depois edite:
```json
"AC": {
  "nome": "Acre",
  "status": "real",   // muda de "placeholder" para "real"
  "fontes": [
    {"tipo": "ricms", "url": "URL_REAL_AQUI"},
    {"tipo": "protocolo", "url": "URL_REAL_AQUI"}
  ]
}
```

Faça commit e push. A próxima execução da Action (ou run manual) vai
trazer os dados novos.

## Troubleshooting

### Scraper rodando 25min e nada

A Action tem `timeout-minutes: 30`. Se passou disso, cheque se algum
SEFAZ está fazendo redirect infinito. Edite `scripts/scraper.py` na
função `fetch()` e reduza `REQUEST_TIMEOUT` de 20 para 10s.

### CONFAZ retornando 403

O CONFAZ às vezes bloqueia requests de IPs de datacenter. Workaround:
use a versão HTML estática em
`https://www.confaz.fazenda.gov.br/legislacao/convenios` (lista de
anos, sem scraping agressivo).

### MVA por UF retornando 0 mesmo com fonte real

Geralmente é seletor de tabela errado. Adicione um log temporário em
`_parse_mva_tabela` para ver a estrutura HTML:

```python
log.debug("Tabela: %s", str(table)[:500])
```

### Commit não aparece no log da Action

Cheque **Settings → Actions → General → Workflow permissions**. O
default é "Read repository contents and packages permissions only",
o que não permite push.

## O que vem depois

- **P9** (mora no app Lovable TanStack) — consome este JSON e popula
  as tabelas Supabase via `sincronizarMirrorFiscal()` toda segunda
  08:00 UTC.
- **P10** (opcional) — painel no app mostrando status de freshness do
  mirror (última execução, contagens, hash).
- **v2.0** — quando CONFAZ publicar a próxima leva do Convênio 142/18
  (anexos IX-XII), adicionar `coletar_cest_convenio_142_anexo_X()`.
