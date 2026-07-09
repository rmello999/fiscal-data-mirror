#!/usr/bin/env python3
"""
Fiscal Data Mirror — coletor de fontes públicas (CONFAZ, SEFAZ-UF, RFB).
Gera JSONs versionados em data/ para consumo pelo motor fiscal.

Uso:
    python scripts/scraper.py           # roda tudo
    python scripts/scraper.py --only confaz
    python scripts/scraper.py --only sefaz --uf SP
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
CONFIG = ROOT / "config" / "sefaz_urls.json"
UA = "fiscal-data-mirror/1.0 (+https://github.com/)"
TIMEOUT = 45
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "*/*"})

# ---------- utilidades ----------
def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)

def get(url: str, **kw) -> requests.Response:
    for attempt in range(3):
        try:
            r = SESSION.get(url, timeout=TIMEOUT, **kw)
            r.raise_for_status()
            return r
        except Exception as e:
            log(f"WARN GET {url} tentativa {attempt+1}: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"falhou GET {url}")

def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    envelope = {
        "_meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "sha256": sha,
            "source": payload.get("_source") if isinstance(payload, dict) else None,
        },
        "data": payload,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"OK {path.relative_to(ROOT)} ({len(body)} bytes, sha={sha[:12]})")

# ---------- CONFAZ ----------
CONFAZ_BASE = "https://www.confaz.fazenda.gov.br"

def scrape_confaz_convenios() -> dict:
    """Lista Convênios ICMS do ano corrente a partir da página oficial CONFAZ."""
    url = f"{CONFAZ_BASE}/legislacao/convenios"
    html = get(url).text
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("a[href*='/convenios/icms/']"):
        href = a.get("href", "")
        text = a.get_text(strip=True)
        m = re.search(r"(\d+)/(\d{2,4})", text)
        if not (href and m):
            continue
        items.append({
            "numero": m.group(1),
            "ano": m.group(2),
            "titulo": text,
            "url": href if href.startswith("http") else CONFAZ_BASE + href,
        })
    return {"_source": url, "convenios": items}

def scrape_confaz_protocolos() -> dict:
    url = f"{CONFAZ_BASE}/legislacao/protocolos"
    html = get(url).text
    soup = BeautifulSoup(html, "lxml")
    items = []
    for a in soup.select("a[href*='/protocolos/icms/']"):
        text = a.get_text(strip=True)
        m = re.search(r"(\d+)/(\d{2,4})", text)
        if not m:
            continue
        items.append({
            "numero": m.group(1),
            "ano": m.group(2),
            "titulo": text,
            "url": a["href"] if a["href"].startswith("http") else CONFAZ_BASE + a["href"],
        })
    return {"_source": url, "protocolos": items}

def scrape_confaz_cest() -> dict:
    """Anexos do Convênio ICMS 142/18 — tabela CEST oficial."""
    url = f"{CONFAZ_BASE}/legislacao/convenios/2018/CV142_18"
    html = get(url).text
    soup = BeautifulSoup(html, "lxml")
    anexos = []
    for a in soup.select("a[href$='.pdf'], a[href$='.xlsx'], a[href$='.ods']"):
        anexos.append({
            "titulo": a.get_text(strip=True),
            "url": a["href"] if a["href"].startswith("http") else CONFAZ_BASE + a["href"],
        })
    return {"_source": url, "anexos": anexos}

# ---------- SEFAZ por UF ----------
def load_sefaz_config() -> dict:
    if not CONFIG.exists():
        raise SystemExit(f"config ausente: {CONFIG}")
    return json.loads(CONFIG.read_text(encoding="utf-8"))

def scrape_sefaz_uf(uf: str, cfg: dict) -> dict:
    """
    Para cada UF, coleta:
      - página de alíquotas internas
      - página de MVA/IVA-ST (quando publicada)
      - página de protocolos ST vigentes
    A extração é conservadora: guarda links + texto bruto tabelado.
    """
    entry = cfg.get(uf)
    if not entry:
        raise ValueError(f"UF {uf} não configurada em {CONFIG}")

    result: dict = {"_source": entry, "uf": uf, "paginas": {}}
    for key in ("aliquotas", "mva_st", "protocolos"):
        url = entry.get(key)
        if not url:
            continue
        try:
            html = get(url).text
            soup = BeautifulSoup(html, "lxml")
            tables = []
            for t in soup.find_all("table"):
                rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["td","th"])]
                        for tr in t.find_all("tr")]
                rows = [r for r in rows if any(r)]
                if rows:
                    tables.append(rows)
            links = [{"texto": a.get_text(strip=True), "href": a.get("href")}
                     for a in soup.find_all("a", href=True)
                     if any(kw in a.get_text().lower()
                            for kw in ("mva","iva","alíquota","aliquota","protocolo","st"))]
            result["paginas"][key] = {"url": url, "tabelas": tables, "links": links}
        except Exception as e:
            result["paginas"][key] = {"url": url, "erro": str(e)}
    return result

# ---------- Receita Federal ----------
def scrape_rfb_ncm() -> dict:
    """Tabela TIPI/NCM publicada pela RFB (página de downloads)."""
    url = "https://www.gov.br/receitafederal/pt-br/assuntos/aduana-e-comercio-exterior/classificacao-fiscal-de-mercadorias/tipi"
    html = get(url).text
    soup = BeautifulSoup(html, "lxml")
    arquivos = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.lower().endswith((".pdf", ".xlsx", ".ods", ".csv")):
            arquivos.append({"titulo": a.get_text(strip=True), "url": href})
    return {"_source": url, "arquivos": arquivos}

# ---------- orquestração ----------
def run(only: str | None, uf_filter: str | None) -> int:
    DATA.mkdir(exist_ok=True)
    errors = 0

    if only in (None, "confaz"):
        try:
            write_json(DATA / "confaz" / "convenios.json", scrape_confaz_convenios())
            write_json(DATA / "confaz" / "protocolos.json", scrape_confaz_protocolos())
            write_json(DATA / "confaz" / "cest_142_18.json", scrape_confaz_cest())
        except Exception as e:
            log(f"ERRO CONFAZ: {e}"); errors += 1

    if only in (None, "sefaz"):
        cfg = load_sefaz_config()
        ufs = [uf_filter] if uf_filter else list(cfg.keys())
        for uf in ufs:
            try:
                write_json(DATA / "sefaz" / f"{uf}.json", scrape_sefaz_uf(uf, cfg))
            except Exception as e:
                log(f"ERRO SEFAZ {uf}: {e}"); errors += 1

    if only in (None, "rfb"):
        try:
            write_json(DATA / "rfb" / "ncm_tipi.json", scrape_rfb_ncm())
        except Exception as e:
            log(f"ERRO RFB: {e}"); errors += 1

    log(f"Finalizado com {errors} erro(s).")
    return 1 if errors else 0

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only", choices=["confaz","sefaz","rfb"])
    p.add_argument("--uf", help="Filtra uma UF quando --only sefaz")
    args = p.parse_args()
    sys.exit(run(args.only, args.uf.upper() if args.uf else None))

if __name__ == "__main__":
    main()
