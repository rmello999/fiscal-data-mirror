# fiscal-data-mirror

Espelho versionado de dados fiscais públicos (CONFAZ, 27 SEFAZ, Receita Federal)
consumido pelo motor fiscal do Global Precificação.

## Como rodar localmente
```bash
pip install -r requirements.txt
python scripts/scraper.py                 # tudo
python scripts/scraper.py --only confaz   # só CONFAZ
python scripts/scraper.py --only sefaz --uf SP
```

## Estrutura
- `scripts/scraper.py` — coletor único
- `config/sefaz_urls.json` — URLs por UF (editável)
- `data/confaz/*.json` — convênios, protocolos, CEST 142/18
- `data/sefaz/<UF>.json` — alíquotas, MVA-ST, protocolos por UF
- `data/rfb/ncm_tipi.json` — TIPI/NCM

Cada arquivo tem envelope `{_meta:{generated_at,sha256,source}, data:{...}}` para auditoria.

## Automação
Workflow `.github/workflows/update.yml` roda semanalmente (segunda 06:00 UTC) e comita o diff em `data/`.
