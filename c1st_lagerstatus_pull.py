#!/usr/bin/env python3
"""
Henter EL-kategori lagerdata fra Customers1st for Evoelsykler sine butikker
og lagrer resultatet som en JSON-fil.

Denne versjonen er laget for å kjore i GitHub Actions: den leser tokenene
fra miljovariabler (satt fra repo-hemmeligheter), ikke fra kildekoden.

Bruk:
    python3 c1st_lagerstatus_pull.py [utfil.json]
"""
import json
import os
import ssl
import sys
import urllib.request
from datetime import datetime, timezone

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = ssl.create_default_context()

STORES = {
    "nydverk": os.environ["NYDVERK_TOKEN"],
    "nydalen": os.environ["NYDALEN_TOKEN"],
    "stavanger": os.environ["STAVANGER_TOKEN"],
    "bergen": os.environ["BERGEN_TOKEN"],
}

HEADERS = [
    "productno", "serieno", "title", "stock", "costprice", "price", "vat",
    "color", "size", "styleno", "tags", "stock_value", "average_stock_price",
    "last_stock_update", "last_stock_reception", "days_since_last_sold",
    "sales", "reserved", "ordered", "available", "syncproductdatawebshop",
    "created",
]

API_BASE = "https://api.c1st.com"


def api_get(path, token):
    url = f"{API_BASE}{path}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CONTEXT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_el_tag_ids(token):
    data = api_get("/api/producttags?paginationPageLength=250", token)
    return [t["id"] for t in data["content"] if t["handle"].lower().startswith("el")]


def get_instock_products(token, tag_ids):
    all_products = []
    start = 0
    page_len = 250
    while True:
        qs = "&".join(f"tags[]={tid}" for tid in tag_ids)
        path = (
            f"/api/products?inStock=true&{qs}"
            f"&paginationPageLength={page_len}&paginationStart={start}"
        )
        d = api_get(path, token)
        content = d.get("content", [])
        all_products.extend(content)
        if not d.get("hasMore") or not content:
            break
        start += page_len
    return all_products


def to_row(p):
    vat = None
    if p.get("price") and p.get("pricewithoutvat"):
        vat = round((p["price"] / p["pricewithoutvat"] - 1) * 100)
    tag_str = ", ".join(t.get("title", "") for t in (p.get("tags") or []))
    stock_val = None
    if p.get("stockno") is not None and p.get("costprice") is not None:
        stock_val = round(p["stockno"] * p["costprice"] * 100) / 100
    return [
        p.get("productno"), p.get("serieno"), p.get("title"), p.get("stockno"),
        p.get("costprice"), p.get("price"), vat, p.get("color"), p.get("size"),
        p.get("styleno"), tag_str, stock_val, p.get("costprice"), p.get("updated_at"),
        None, None, None, p.get("reservedstock"), p.get("ordered"),
        p.get("totalavailablestock"), p.get("syncproductdatawebshop"), p.get("created"),
    ]


def pull_store(doc_id, token):
    tag_ids = get_el_tag_ids(token)
    if not tag_ids:
        raise RuntimeError(f"{doc_id}: fant ingen EL-kategorier")
    products = get_instock_products(token, tag_ids)
    rows = [to_row(p) for p in products]
    return {
        "headers": HEADERS,
        "rows": rows,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def main():
    result = {}
    had_error = False
    for doc_id, token in STORES.items():
        try:
            result[doc_id] = pull_store(doc_id, token)
            print(f"{doc_id}: {len(result[doc_id]['rows'])} varer OK")
        except Exception as e:
            had_error = True
            print(f"FEIL for {doc_id}: {e}", file=sys.stderr)

    out_path = sys.argv[1] if len(sys.argv) > 1 else "c1st_lagerstatus.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    print(f"Skrevet til {out_path}")

    if had_error:
        sys.exit(1)


if __name__ == "__main__":
    main()
